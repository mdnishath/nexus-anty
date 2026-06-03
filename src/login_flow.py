import asyncio
import random
import re
import string
import threading
import time
import pandas as pd
from contextlib import contextmanager
from datetime import datetime
from src.screen_detector import ScreenDetector, LoginScreen
from src.gmail_authenticator import GmailAuthenticator
from src.login_brain import LoginBrain, HandlerResult
from src.utils import TOTPGenerator

# ── Timing / retry constants (centralized for easy tuning) ───────────────────
PAGE_LOAD_TIMEOUT     = 20000   # ms — default page.goto() timeout
LONG_PAGE_TIMEOUT     = 30000   # ms — login URL navigation timeout
NAV_TIMEOUT           = 15000   # ms — go_back / reload during polling
ELEMENT_WAIT_TIMEOUT  = 10000   # ms — waiting for a specific element
QUICK_CLICK_TIMEOUT   = 2000    # ms — fast click attempt
MAX_LOGIN_ITERATIONS  = 15      # max screen-detection poll loops before fail

# ── Human-typing parameters (used for email + password fields) ───────────────
# Mean ~110ms per keystroke ≈ 90 WPM = a believable fast human typist.
# Random jitter keeps Google's anti-bot from flagging perfectly-even cadence.
HUMAN_TYPE_BASE_MS    = 110     # mean inter-key delay (ms)
HUMAN_TYPE_JITTER_MS  = 60      # ± random jitter per keystroke (ms)
HUMAN_TYPE_MIN_MS     = 35      # floor — never type faster than this


async def _value_matches(elem, expected: str) -> bool:
    """True if the input's current value equals `expected` (whitespace-stripped).

    Used to skip re-typing on a reload retry when the previous fill already
    landed. Any exception (detached element, element not an input) → False
    so the caller falls through to its normal fill path.
    """
    try:
        cur = (await elem.input_value()) or ''
    except Exception:
        return False
    return cur.strip() == (expected or '').strip()


async def _wait_for_any(page, selectors: list[str], timeout: int = 10000) -> bool:
    """Wait until ONE of *selectors* is visible on *page*.

    Returns True as soon as any selector becomes visible, or False if
    *timeout* ms elapses without a match.  This replaces the pattern
    ``await asyncio.sleep(N)`` that previously hard-blocked for the full
    duration regardless of how fast the page actually responded.

    Args:
        page:      Playwright page object.
        selectors: CSS selectors tried in order; first visible wins.
        timeout:   Total wait budget in milliseconds (default 10 s).
    """
    import time as _time
    deadline = _time.monotonic() + timeout / 1000
    poll = 0.2   # seconds between checks
    while _time.monotonic() < deadline:
        for sel in selectors:
            try:
                if await page.locator(sel).first.is_visible(timeout=200):
                    return True
            except Exception:
                continue
        await asyncio.sleep(poll)
    return False


async def _human_type(page, text: str,
                      base_ms: int = HUMAN_TYPE_BASE_MS,
                      jitter_ms: int = HUMAN_TYPE_JITTER_MS) -> None:
    """Type *text* one character at a time with humanized variable delays.

    Each inter-key gap = base_ms ± uniform(-jitter, +jitter), floored at
    HUMAN_TYPE_MIN_MS. The target element MUST already be focused — call
    elem.click() / elem.focus() before this. Used for email + password
    fields so Google sees gradual typing instead of an instant-paste
    fill that its anti-bot can flag.
    """
    for i, ch in enumerate(text):
        await page.keyboard.type(ch)
        if i < len(text) - 1:
            d = base_ms + random.uniform(-jitter_ms, jitter_ms)
            await asyncio.sleep(max(HUMAN_TYPE_MIN_MS, d) / 1000.0)


async def _human_type_to_element(elem, text: str,
                                 base_ms: int = HUMAN_TYPE_BASE_MS,
                                 jitter_ms: int = HUMAN_TYPE_JITTER_MS) -> None:
    """Element-bound variant of _human_type.

    Types each character via the element's own press() so focus drift in
    the surrounding page CANNOT redirect keystrokes to a different input.
    Fixes the bug where if Google's identifier page stalled mid-transition
    (focus still on the email field), the password chars typed via
    page.keyboard.type() would land in the EMAIL field instead of the
    password field — which Google then read as the email "value" on
    re-submit, producing a garbled login that silently failed.

    Same humanized cadence as _human_type.
    """
    for i, ch in enumerate(text):
        # locator.press() sends the keystroke to THIS element regardless
        # of which element has document focus. Works for any printable
        # character because Playwright maps single chars to key codes.
        try:
            await elem.press(ch)
        except Exception:
            # Fallback: fill the remaining text in one shot rather than
            # raising. Better to land the rest of the password in the
            # right field than to abort mid-typing.
            try:
                cur = (await elem.input_value()) or ''
            except Exception:
                cur = ''
            await elem.fill(cur + text[i:])
            return
        if i < len(text) - 1:
            d = base_ms + random.uniform(-jitter_ms, jitter_ms)
            await asyncio.sleep(max(HUMAN_TYPE_MIN_MS, d) / 1000.0)


async def _first_visible_locator(page, selectors: list[str]):
    """Return (locator, selector_string) for the FIRST visible+enabled
    match among *selectors*, or (None, None) if none match. Lets callers
    probe several candidate field selectors without nesting try/except."""
    for s in selectors:
        try:
            c = page.locator(s).first
            if (await c.count() > 0
                    and await c.is_visible()
                    and await c.is_enabled()):
                return c, s
        except Exception:
            continue
    return None, None


def _generate_random_password(length=16):
    """Generate a random strong password (letters + digits + symbols)."""
    chars = string.ascii_letters + string.digits + '!@#$%&'
    # Ensure at least 1 upper, 1 lower, 1 digit, 1 symbol
    pw = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice('!@#$%&'),
    ]
    pw += [random.choice(chars) for _ in range(length - 4)]
    random.shuffle(pw)
    return ''.join(pw)


def _log(worker_id, msg):
    """Print a timestamped log line for the worker."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}][WORKER {worker_id}] {msg}")


def _is_chrome_error(url: str) -> bool:
    """True when Chrome shows its own error page (network failure, ERR_CONNECTION_RESET, etc.)"""
    return url.startswith('chrome-error://') or url == 'about:blank'


def _is_google_security_redirect(url: str) -> str | None:
    """
    Returns a human-readable reason string if Google redirected to a security/help page
    instead of the inbox, otherwise returns None.
    Known redirects:
      support.google.com/accounts/answer/32050  -> forced password change
      support.google.com/accounts               -> generic account issue
      accounts.google.com/v3/signin/rejected    -> account suspended/rejected
      gds.google.com/web/recoveryoptions        -> add recovery info (post-login, session valid)
    """
    if 'support.google.com/accounts/answer/32050' in url:
        return 'ACCOUNT_RECOVERY_REDIRECT - Google forced password-change page (account flagged)'
    if 'support.google.com/accounts' in url:
        return 'ACCOUNT_RECOVERY_REDIRECT - Google redirected to account support page'
    if 'accounts.google.com' in url and '/signin/rejected' in url:
        return 'ACCOUNT_LOCKED - Google rejected/suspended this account'
    if 'gds.google.com/web/recoveryoptions' in url:
        return 'RECOVERY_OPTIONS_REDIRECT - Google wants recovery info (session is valid)'
    return None


async def _try_recover_from_support_redirect(page, worker_id, require_inbox, forced_new_password):
    """
    When Google redirects to support.google.com (ACCOUNT_RECOVERY_REDIRECT),
    navigate to myaccount to check if the session is still valid.
    Returns success dict or None if recovery failed.

    `require_inbox` is kept in the signature for backward compatibility
    with callers across profile_manager / linked / step2 / gmail_authenticator,
    but is no longer used — the unified login flow always lands on
    myaccount.google.com, so the recovery target is always myaccount.
    """
    _log(worker_id, "  RECOVERY: Support-page redirect detected — navigating to myaccount...")
    try:
        await page.goto('https://myaccount.google.com/',
                        wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(3)
        url = page.url
        _log(worker_id, f"  RECOVERY: After navigation URL = {url[:100]}")

        # myaccount page is enough — session is valid
        if 'myaccount.google.com' in url or 'accounts.google.com/b/' in url:
            _log(worker_id, "  RECOVERY SUCCESS: MyAccount page reached!")
            return {'success': True, 'forced_new_password': forced_new_password}

        # Kicked back to login → session dead
        if 'accounts.google.com/v3/signin' in url or 'accounts.google.com/signin' in url:
            _log(worker_id, "  RECOVERY FAILED: Redirected back to login — session expired")
            return None

        # Any Google page that isn't login is acceptable
        if 'google.com' in url and 'signin' not in url:
            _log(worker_id, "  RECOVERY SUCCESS: On Google page (not login) — session likely valid")
            return {'success': True, 'forced_new_password': forced_new_password}

    except Exception as e:
        _log(worker_id, f"  RECOVERY FAILED: Navigation error: {str(e)[:60]}")
    return None


def _is_myaccount_url(url: str) -> bool:
    """STRICT myaccount detection — returns True only when the page is
    actually hosted on myaccount.google.com, NOT when myaccount appears
    inside a continue= query parameter on a /challenge/* page.

    The new login URL embeds `continue=https://myaccount.google.com/...`
    so Google preserves that query param through every signin step
    (challenge/pwd, challenge/totp, challenge/dp, etc.). A naive
    `'myaccount.google.com' in url` check would match all of those,
    causing premature 'logged in' verdicts WHILE 2FA was still pending
    — the browser would close mid-2FA and report success on an account
    that wasn't actually logged in.
    """
    if not url:
        return False
    return (url.startswith('https://myaccount.google.com')
            or url.startswith('http://myaccount.google.com'))


async def _verify_login_by_email(page, worker_id: int, expected_email: str) -> bool:
    """UNIVERSAL login verifier — used everywhere a 'is this profile logged
    in?' check is needed (post-login verification, pre-op session check, etc.).

    Strategy: navigate to https://myaccount.google.com/ and confirm the
    expected email appears on the page. Google renders the email in a
    <div class="kYZvBb">email@domain.com</div> element on the account
    page; we match by EMAIL TEXT rather than by class name (class names
    rotate across Google builds, the email text doesn't).

    Skips navigation if we're already on myaccount.google.com (post-login
    flow lands there directly when the login URL uses
    service=accountsettings&continue=myaccount).

    Returns:
        True  — expected_email found on the page = logged in as right profile.
        False — kicked to signin, or email not found within ~8s.
    """
    if not expected_email:
        return False
    email_lower = expected_email.lower().strip()

    # Navigate to myaccount if we're not actually there (strict check —
    # the continue= query param contains myaccount.google.com on signin
    # challenge pages, but those are NOT the myaccount page itself).
    if not _is_myaccount_url(page.url):
        try:
            await page.goto('https://myaccount.google.com/',
                            wait_until='domcontentloaded', timeout=15000)
        except Exception as e:
            _log(worker_id, f"VERIFY: nav to myaccount failed: {str(e)[:80]}")
            return False

    # Poll for email text in the page DOM. Short 2s cap — outer polling
    # loops (execute_login_flow's STEP 4, _check_gmail_session's caller)
    # will retry naturally, so double-polling here is wasted wall-time.
    _start = time.monotonic()
    deadline = _start + 2
    while time.monotonic() < deadline:
        url = page.url
        # Bounced back to signin = not logged in. ONLY treat strict
        # /v3/signin/identifier or /v3/signin paths as 'not logged in';
        # /v3/signin/challenge/* URLs are 2FA challenge steps where the
        # session is being completed, not a signin redirect.
        if ('accounts.google.com' in url
                and '/signin/' in url
                and '/challenge/' not in url):
            _log(worker_id, "VERIFY: redirected to signin — NOT logged in")
            return False
        try:
            # Look for any element whose text equals or contains the email.
            # get_by_text matches case-insensitively and traverses nested
            # text nodes — covers the kYZvBb div and any other surface where
            # Google might surface the email.
            if await page.get_by_text(expected_email, exact=False).first.count() > 0:
                _log(worker_id, f"VERIFY: SUCCESS in {time.monotonic()-_start:.1f}s "
                                f"(email '{expected_email}' matched in DOM)")
                return True
        except Exception:
            pass
        await asyncio.sleep(0.1)

    return False


import re as _pwd_re


# Multilingual keyword sets for detecting Google's "Your password was changed
# X days ago" security notice. We match three signals: a "password" word stem,
# a "changed/modified" verb, and a numeric "X days/jours/Tagen/…" interval —
# the combo unambiguously identifies the notice across any UI language without
# false-firing on wrong-password errors (which don't carry a time interval).
_PWD_CHANGED_PASSWORD_WORDS = (
    'password', 'mot de passe', 'contraseña', 'contrasena', 'senha', 'passwort',
    'parola', 'parol', 'wachtwoord', 'lösenord', 'losenord', 'adgangskode',
    'salasana', 'passord', 'şifre', 'sifre', 'パスワード', '비밀번호', '密码', '密碼',
    'पासवर्ड', 'পাসওয়ার্ড', 'پاسورڈ',
)
_PWD_CHANGED_VERB_WORDS = (
    'changed', 'modified', 'modifié', 'modifiée', 'modifie', 'modificada',
    'modificato', 'modificata', 'cambió', 'cambiada', 'cambiado', 'cambiata',
    'alterada', 'alterado', 'mudou', 'mudada',
    'geändert', 'geandert', 'gewijzigd', 'ändrats', 'andrats', 'ændret',
    'vaihdettu', 'endret', 'değiştirildi', 'degistirildi', 'zmieniono', 'zmieniona',
    '変更', '변경', '更改', '已更改', 'बदला', 'बदल', 'পরিবর্তন',
)
_PWD_CHANGED_TIME_WORDS = (
    'day', 'days', 'jour', 'jours', 'día', 'dia', 'dias', 'días',
    'giorni', 'giorno', 'Tag', 'Tage', 'Tagen', 'dag', 'dagen', 'dagar',
    'päivä', 'paiva', 'päivää', 'gün', 'günü', 'gunu', 'दिन', 'दिनों',
    'দিন', 'दिवस', 'दिनों', 'roku', 'lat', 'mois', 'minute', 'minutes',
    'minuto', 'minutos', 'minut', 'minuti', 'hour', 'hours', 'heure',
    'heures', 'hora', 'horas', 'ora', 'ore', 'Stunde', 'Stunden',
    '日', '時間', '시간', '분', '小时',
)


async def _check_password_changed_error(page, worker_id: int) -> str:
    """Detect Google's 'Your password was changed X days ago' notice.

    Returns:
        '' (empty)                  — no notice present
        'PASSWORD_RECENTLY_CHANGED' — multilingual notice matched (e.g.
                                      'Votre mot de passe a été modifié il y a 25 jours')
        'B34EJ_GENERIC'             — B34EJ container visible with text we
                                      couldn't classify (caller may still
                                      treat as failure but won't tag the
                                      "Password Changed" group)

    The change-vs-wrong-password distinction matters because the user wants
    these profiles moved to a "Password Changed" group — they signal that
    the account holder rotated the password and our stored copy is stale.
    """
    try:
        # Primary signal: <span jsslot=""> inside the B34EJ container. Google
        # uses jsslot="" as the slot for variable interpolation in its
        # localized strings, so the empty-jsslot pattern is consistent.
        candidates = [
            page.locator('[jsname="B34EJ"] span[jsslot]'),
            page.locator('[jsname="B34EJ"]'),
            # Some variants surface the notice in [jsname="h9d3hd"]
            # (the outer wrapper) when B34EJ isn't rendered.
            page.locator('[jsname="h9d3hd"] span[jsslot]'),
            page.locator('[jsname="h9d3hd"]'),
        ]
        text = ''
        for loc in candidates:
            try:
                if await loc.count() > 0 and await loc.first.is_visible():
                    t = (await loc.first.inner_text()) or ''
                    t = t.strip()
                    if t:
                        text = t
                        break
            except Exception:
                continue

        if not text:
            _log(worker_id, "CHECK_PASSWORD_CHANGED: No B34EJ/h9d3hd notice visible")
            return ''

        low = text.lower()
        # Detect all three signals: password noun + change verb + time interval
        has_pwd_word = any(w.lower() in low for w in _PWD_CHANGED_PASSWORD_WORDS)
        has_verb     = any(w.lower() in low for w in _PWD_CHANGED_VERB_WORDS)
        has_time     = any(w.lower() in low for w in _PWD_CHANGED_TIME_WORDS) or bool(_pwd_re.search(r'\d', text))

        if has_pwd_word and has_verb and has_time:
            _log(worker_id, f"CHECK_PASSWORD_CHANGED: ✗ recently-changed notice — '{text[:120]}'")
            return 'PASSWORD_RECENTLY_CHANGED'

        _log(worker_id, f"CHECK_PASSWORD_CHANGED: B34EJ visible (generic error) — '{text[:120]}'")
        return 'B34EJ_GENERIC'
    except Exception as e:
        _log(worker_id, f"CHECK_PASSWORD_CHANGED: Exception: {str(e)[:60]}")
    return ''


async def _check_captcha_screen(page, worker_id: int) -> bool:
    """Check for CAPTCHA/reCAPTCHA -> FAIL."""
    _log(worker_id, "CHECK_CAPTCHA: Scanning for CAPTCHA...")
    for text in ["Confirm you're not a robot", "confirm you're not a robot"]:
        try:
            elem = page.get_by_text(text, exact=False).first
            if await elem.count() > 0 and await elem.is_visible():
                _log(worker_id, f"CHECK_CAPTCHA: FOUND text = '{text}'")
                return True
        except Exception:
            continue
    for sel in ['iframe[title="reCAPTCHA"]', '.g-recaptcha', 'div[jsname="ySEIab"]']:
        try:
            elem = page.locator(sel).first
            if await elem.count() > 0 and await elem.is_visible():
                _log(worker_id, f"CHECK_CAPTCHA: FOUND selector = '{sel}'")
                return True
        except Exception:
            continue
    _log(worker_id, "CHECK_CAPTCHA: No CAPTCHA found")
    return False


async def _check_wrong_password(page, worker_id: int) -> bool:
    """Check for 'Wrong password' error."""
    _log(worker_id, "CHECK_WRONG_PWD: Scanning for wrong password...")
    for text in ["Wrong password", "Mot de passe incorrect", "The email or password you entered is incorrect"]:
        try:
            elem = page.get_by_text(text, exact=False).first
            if await elem.count() > 0 and await elem.is_visible():
                _log(worker_id, f"CHECK_WRONG_PWD: FOUND = '{text}'")
                return True
        except Exception:
            continue
    _log(worker_id, "CHECK_WRONG_PWD: No wrong password error")
    return False


async def _check_wrong_totp_code(page, worker_id: int) -> bool:
    """Check for 'Wrong code. Try again.' after TOTP -> FAIL (secret wrong/changed)."""
    _log(worker_id, "CHECK_WRONG_TOTP: Scanning for wrong TOTP code...")
    error_texts = ["Wrong code. Try again", "Wrong code", "That code didn't work", "Code erroné"]
    try:
        error_container = page.locator('[jsname="B34EJ"]').first
        if await error_container.count() > 0 and await error_container.is_visible():
            error_text = await error_container.inner_text()
            _log(worker_id, f"CHECK_WRONG_TOTP: B34EJ text = '{error_text.strip()}'")
            if error_text.strip():
                for expected in error_texts:
                    if expected.lower() in error_text.lower():
                        _log(worker_id, f"CHECK_WRONG_TOTP: MATCH = '{expected}'")
                        return True
        for text in error_texts:
            elem = page.get_by_text(text, exact=False).first
            if await elem.count() > 0 and await elem.is_visible():
                _log(worker_id, f"CHECK_WRONG_TOTP: FOUND visible text = '{text}'")
                return True
    except Exception as e:
        _log(worker_id, f"CHECK_WRONG_TOTP: Exception: {str(e)[:60]}")
    _log(worker_id, "CHECK_WRONG_TOTP: No wrong TOTP error")
    return False


async def execute_login_flow(page, account, worker_id, login_url, detector=None, totp_gen=None, require_inbox=True):
    """
    Executes the common Google login flow.

    MANDATORY: Email -> Password -> login success
    OPTIONAL: 2FA, recovery info, passkey, etc.

    Args:
        page: Playwright page object
        account: Dict with Email, Password, TOTP Secret, Backup Code
        worker_id: Worker ID for logging
        login_url: Login URL
        detector: ScreenDetector (optional)
        totp_gen: TOTPGenerator (optional)
        require_inbox: Deprecated — kept in the signature for backward
                       compatibility with callers across profile_manager /
                       linked / step2 / gmail_authenticator. The unified
                       login URL always lands on myaccount.google.com, so
                       success is always determined by `myaccount URL +
                       email match in DOM` (via _verify_login_by_email).
                       The flag has no effect on the success criteria.

    Returns:
        dict: {'success': True/False, 'error': 'msg', 'forced_new_password': '...'}
    """
    email = account.get('Email', 'unknown')
    password = account.get('Password', '')
    forced_new_password = ''  # Will be set if Google forces a password change

    # Flexible column reading — try multiple common name variants
    def _flex_get(acct, variants, default=''):
        for col in variants:
            val = acct.get(col, '')
            if val and not pd.isna(val) and str(val).strip() and str(val).strip().lower() != 'nan':
                return str(val).strip()
        return default

    totp_secret = _flex_get(account, [
        'TOTP Secret', 'totp_secret', 'TOTP', 'totp', 'Totp Secret',
        'TOTP Key', 'totp_key', 'Authenticator Key', 'authenticator_key',
        'Secret Key', 'secret_key', 'OTP Secret', 'otp_secret',
    ])

    backup_code_raw = _flex_get(account, [
        'Backup Code', 'backup_code', 'Backup', 'backup',
        'Backup Code 1', 'backup_code_1',
    ])

    recovery_email = _flex_get(account, [
        'Recovery Email', 'recovery_email', 'Recovery_Email',
        'RecoveryEmail', 'recovery email',
    ])

    recovery_phone = _flex_get(account, [
        'Recovery Phone', 'recovery_phone', 'Recovery_Phone',
        'RecoveryPhone', 'recovery phone', 'Phone', 'phone',
    ])

    if not detector:
        detector = ScreenDetector(page)
    if not totp_gen:
        totp_gen = TOTPGenerator()

    _log(worker_id, "=" * 60)
    _log(worker_id, f"LOGIN START: {email}")
    _log(worker_id, f"  Success: myaccount URL + email match (require_inbox={require_inbox} — no longer affects flow)")
    _log(worker_id, f"  TOTP Secret: {'YES' if totp_secret else 'NO'}")
    _log(worker_id, f"  Backup Code: {'YES' if backup_code_raw else 'NO'}")
    _log(worker_id, f"  Recovery Email: {'YES (' + recovery_email[:3] + '***' + ')' if recovery_email else 'NO'}")
    _log(worker_id, f"  Recovery Phone: {'YES (***' + recovery_phone[-2:] + ')' if recovery_phone else 'NO'}")
    _log(worker_id, f"  Login URL: {login_url[:80]}")
    _log(worker_id, "=" * 60)

    try:
        # ============================================================
        # STEP 1: Navigate to login URL — SINGLE load, no retry
        # ============================================================
        # User policy: the login URL must be loaded exactly once. The old
        # 3-attempt retry was masking real failures (network errors, proxy
        # issues, profile state problems) by repeatedly hammering Chrome
        # and giving an inconsistent picture of why a profile failed.
        # Single goto + fail-fast on chrome-error gives a clear signal.
        _log(worker_id, "STEP[1/4] NAVIGATE: Loading login page...")
        try:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as nav_err:
            _log(worker_id, f"STEP[1/4] NAVIGATE: goto() raised: {nav_err}")
        nav_url = page.url
        _log(worker_id, f"STEP[1/4] NAVIGATE: URL = {nav_url[:100]}")
        if _is_chrome_error(nav_url):
            raise Exception(
                f"NETWORK_ERROR - Chrome error page after loading login URL "
                f"(check proxy / network): {nav_url[:120]}"
            )

        # EARLY security-redirect check — if just loading the login URL
        # bounced us straight to accounts.google.com/v3/signin/rejected
        # (account disabled / suspended) or any other support/recovery
        # page, fail NOW before we waste cycles typing email + password.
        sec_reason = _is_google_security_redirect(nav_url)
        if sec_reason:
            _log(worker_id, f"STEP[1/4] NAVIGATE: ✗ {sec_reason}")
            raise Exception(sec_reason)

        try:
            title = await page.title()
            _log(worker_id, f"STEP[1/4] NAVIGATE: Page title = '{title}'")
        except Exception:
            pass
        await asyncio.sleep(3)
        _log(worker_id, f"STEP[1/4] NAVIGATE: After wait. URL = {page.url[:100]}")

        # ============================================================
        # ALREADY-LOGGED-IN SHORT-CIRCUIT
        # ============================================================
        # If the navigation landed us straight on myaccount.google.com or
        # mail.google.com, the profile's saved cookies were still valid —
        # Google bypassed the login screens entirely. Verify the active
        # account is the one we expected and return success without typing
        # anything. Without this, the email-field search below would fail
        # and Re-Login would wrongly mark the profile as login_failed even
        # though it's actually fine.
        try:
            from urllib.parse import urlparse as _urlparse
            _host = (_urlparse(page.url).netloc or '').lower()
            _on_inbox = (_host == 'mail.google.com'
                         or _host.endswith('.mail.google.com'))
            if _is_myaccount_url(page.url) or _on_inbox:
                _log(worker_id,
                     f"STEP[2/4] EMAIL: Already on logged-in page ({_host}) — "
                     f"verifying session belongs to {email}...")
                if await _verify_login_by_email(page, worker_id, email):
                    _log(worker_id,
                         "STEP[2/4] EMAIL: ✓ Already logged in (cookies valid) — skipping login flow")
                    return {'success': True, 'forced_new_password': forced_new_password}
                _log(worker_id,
                     "STEP[2/4] EMAIL: Logged-in page but verify-by-email failed — falling through to login flow")
        except Exception as _ali_err:
            _log(worker_id,
                 f"STEP[2/4] EMAIL: already-logged-in check error: {_ali_err}")

        # ============================================================
        # STEP 2: Enter email (MANDATORY) — single-shot, human-typed
        # ============================================================
        # No 3-attempt retry, no reload+retype loop. If the email field
        # is not visible within ELEMENT_WAIT_TIMEOUT we fail fast so the
        # caller can move on to the next profile — the old retries were
        # wasting up to ~140s per stuck profile and rarely recovered.
        _log(worker_id, "STEP[2/4] EMAIL: Looking for email input field...")

        # Pre-check: dismiss cookie / language consent if present
        try:
            await detector.dismiss_language_prompt()
        except Exception:
            pass

        email_selectors = [
            '#identifierId',
            'input[type="email"]',
            'input[name="identifier"]',
            'input[name="Email"]',              # Recovery page variant
            'input[aria-label*="Email" i]',     # Aria-label fallback
            'input[aria-label*="email" i]',
        ]

        # Wait briefly for the email field OR an account-picker landing page.
        await _wait_for_any(page, email_selectors + [
            'div[data-email]', '[data-identifier]',
        ], timeout=ELEMENT_WAIT_TIMEOUT)

        elem, sel = await _first_visible_locator(page, email_selectors)

        # If email field isn't there, the page may be the "Choose an
        # account" picker (already-logged-in state). Click "Use another
        # account" ONCE upfront, then look for the email field again.
        if elem is None:
            for ca_sel in ('div[data-email]', '[data-identifier]',
                           'li[role="link"][data-email]'):
                try:
                    ca = page.locator(ca_sel).first
                    if await ca.count() > 0 and await ca.is_visible():
                        _log(worker_id, "STEP[2/4] EMAIL: 'Choose an account' page — clicking 'Use another account'")
                        for ua_sel in ('li:has-text("Use another account")',
                                       'div[role="link"]:has-text("Use another account")',
                                       '#identifierLink',
                                       'button:has-text("Add another account")',
                                       ':text("Use another account")'):
                            try:
                                ua = page.locator(ua_sel).first
                                if await ua.count() > 0 and await ua.is_visible():
                                    await ua.click()
                                    _log(worker_id, f"STEP[2/4] EMAIL: Clicked: {ua_sel}")
                                    await _wait_for_any(page, email_selectors, timeout=5000)
                                    break
                            except Exception:
                                continue
                        break
                except Exception:
                    continue
            elem, sel = await _first_visible_locator(page, email_selectors)

        if elem is None:
            _log(worker_id, "STEP[2/4] EMAIL: FAILED - email field not visible")
            _log(worker_id, f"STEP[2/4] EMAIL: Final URL = {page.url[:100]}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            try:
                await page.screenshot(path=f"screenshots/email_input_error_{timestamp}.png", full_page=True)
                _log(worker_id, "STEP[2/4] EMAIL: Screenshot saved")
            except Exception as _ss_err:
                _log(worker_id, f"STEP[2/4] EMAIL: Screenshot failed — {_ss_err!s:.80}")
            raise Exception("Could not enter email - input field not found")

        # Skip retype if value already matches (browser autofill / re-entry)
        if await _value_matches(elem, email):
            _log(worker_id, f"STEP[2/4] EMAIL: Already filled via '{sel}' — skipping retype")
        else:
            try: await elem.click()
            except Exception: pass
            try: await elem.focus()
            except Exception: pass
            try: await elem.fill('')
            except Exception: pass
            # Element-bound typing so focus drift can't redirect chars
            # to a different input if the page is mid-transition.
            await _human_type_to_element(elem, email)
            _log(worker_id, f"STEP[2/4] EMAIL: Typed email via '{sel}' (humanized)")

        # ── Submit + advance-check loop ─────────────────────────────────
        # Under heavy parallel-login load Google's identifier page sometimes
        # accepts the Next click but never renders the password screen —
        # the page just sits on /identifier with the email typed in. The
        # symptom is "stack hoia jai" reported by the user.
        # Fix: after each Next/Enter submit, wait up to 5s for ONE of:
        #     - URL leaves /identifier (challenge/pwd, /challenge/pk,
        #       mail.google.com, etc.), AND
        #     - a real password input becomes visible (filtered against
        #       the hidden autofill-bait input that lives on /identifier
        #       and falsely reports is_visible()=True)
        # If neither shows up, reload the page and retype email. Repeat
        # up to MAX_EMAIL_SUBMIT_ATTEMPTS times.
        # Bumped to handle 10-worker batch-login through a single proxy gateway:
        # under that load the proxy serializes requests and Google's response
        # can take 7-9s for the first submit before the identifier page advances.
        # The old 5s deadline kept firing reload before Google actually responded,
        # cascading into "Couldn't sign you in" / "Try again" loops.
        MAX_EMAIL_SUBMIT_ATTEMPTS = 5
        ADVANCE_WAIT_SEC          = 12

        # CRITICAL: parse the URL with urllib so we check hostname / path
        # separately. A substring match like ('myaccount.google.com' in url)
        # falsely fires on the identifier page's URL itself —
        #   accounts.google.com/v3/signin/identifier?continue=https%3A%2F%2Fmyaccount.google.com%3F...
        # — because the `continue=` parameter ENCODES myaccount.google.com
        # as a return-to destination. We were treating the email page as
        # "already advanced" and skipping the reload. The reload-after-stall
        # the user asked for never fired.
        from urllib.parse import urlparse

        def _on_identifier_page() -> bool:
            try:
                p = urlparse(page.url)
                return p.netloc.endswith('accounts.google.com') and '/identifier' in p.path
            except Exception:
                return '/identifier' in page.url

        async def _password_visible_on_real_page() -> bool:
            # The autofill bait sits on /identifier with display:none-style
            # positioning that Playwright still calls visible. Requiring
            # the URL to have already left /identifier filters it out.
            if _on_identifier_page():
                return False
            for psel in ('input[name="Passwd"]', 'input[type="password"]'):
                try:
                    p = page.locator(psel).first
                    if await p.count() > 0 and await p.is_visible():
                        return True
                except Exception:
                    continue
            return False

        async def _email_step_advanced() -> bool:
            try:
                parsed = urlparse(page.url)
                host = parsed.netloc.lower()
                path = parsed.path.lower()
            except Exception:
                host, path = '', page.url.lower()

            # /challenge/ covers pwd, pk, totp, tel, dp, ipp, kpe etc.
            if '/challenge/' in path:
                return True
            # Terminal good states — check host, NOT substring of full URL,
            # because the identifier page's `continue=` query parameter
            # ENCODES these same hostnames.
            if host == 'mail.google.com' or host.endswith('.mail.google.com'):
                return True
            if host == 'myaccount.google.com' or host.endswith('.myaccount.google.com'):
                return True
            if '/signin/rejected' in path:
                return True
            # Fallback: real password input rendered on a non-identifier page.
            return await _password_visible_on_real_page()

        async def _detect_stuck_error() -> str:
            """Return a non-empty reason string when Google has rendered an
            error/retry banner that's blocking forward progress under heavy
            proxy load. Caller treats this as 'submission failed, hard-reload'.
            Empty string when page is just slow (not stuck)."""
            try:
                # Body text scan is robust across UI variants. Only check when
                # we're still on /identifier — these messages render there
                # after a failed POST.
                if not _on_identifier_page():
                    return ''
                txt = ''
                try:
                    txt = await page.locator('body').inner_text(timeout=1500)
                except Exception:
                    return ''
                t = (txt or '').lower()
                # Order matters slightly — pick the most specific message first
                if 'couldn’t find your google account' in t or "couldn't find your google account" in t:
                    return 'ACCOUNT_NOT_FOUND'
                if 'something went wrong' in t:
                    return 'TRANSIENT_ERROR'
                if 'couldn’t sign you in' in t or "couldn't sign you in" in t:
                    return 'TRANSIENT_ERROR'
                if 'try again' in t and ('error' in t or 'wrong' in t):
                    return 'TRANSIENT_ERROR'
            except Exception:
                pass
            return ''

        advanced = False
        for attempt in range(1, MAX_EMAIL_SUBMIT_ATTEMPTS + 1):
            # Pre-submit guard: if Google already redirected us to
            # /signin/rejected (account locked/suspended) between attempts,
            # bail immediately. No point clicking Next on a dead account —
            # waste of proxy bandwidth + worker time. The caller catches
            # this and tags the profile to the "Try to restore" group.
            pre_sec = _is_google_security_redirect(page.url)
            if pre_sec:
                _log(worker_id, f"STEP[2/4] EMAIL: ✗ pre-submit {pre_sec}")
                raise Exception(pre_sec)

            # Submit — Next button first (reliable), Enter as A/B fallback.
            try:
                await page.locator('button:has-text("Next")').first.click()
            except Exception as _click_err:
                _log(worker_id, f"STEP[2/4] EMAIL: Next button click failed ({str(_click_err)[:60]}) — trying Enter")
                try:
                    await page.keyboard.press('Enter')
                except Exception as _ne_err:
                    _log(worker_id, f"STEP[2/4] EMAIL: Submit failed — {str(_ne_err)[:80]}")

            _log(worker_id, f"STEP[2/4] EMAIL: Submitted (attempt {attempt}/{MAX_EMAIL_SUBMIT_ATTEMPTS}). "
                            f"Waiting up to {ADVANCE_WAIT_SEC}s for password input / challenge page...")

            # Poll for either advance OR a stuck-error banner — whichever
            # happens first. Banner short-circuits the wait so we don't burn
            # the full 12s deadline on a page that's clearly never advancing.
            deadline = time.monotonic() + ADVANCE_WAIT_SEC
            stuck_reason = ''
            error_check_t = 0.0  # rate-limit the body-text scan to once per 2s
            while time.monotonic() < deadline:
                # In-poll /signin/rejected fast-fail. The page can transition
                # to the rejection URL silently while we're still inside the
                # 12s wait — catch it the instant it happens so we don't
                # waste the rest of the deadline OR fall through into another
                # submit attempt against a known-locked account.
                cur_sec = _is_google_security_redirect(page.url)
                if cur_sec:
                    _log(worker_id, f"STEP[2/4] EMAIL: ✗ mid-wait {cur_sec}")
                    raise Exception(cur_sec)

                if await _email_step_advanced():
                    advanced = True
                    break
                now = time.monotonic()
                if now - error_check_t > 2.0:
                    error_check_t = now
                    stuck_reason = await _detect_stuck_error()
                    if stuck_reason == 'ACCOUNT_NOT_FOUND':
                        # Permanent failure — no point retrying.
                        raise Exception(f'ACCOUNT_NOT_FOUND - Google says the account does not exist ({email})')
                    if stuck_reason:
                        _log(worker_id, f"STEP[2/4] EMAIL: Stuck banner detected ({stuck_reason}) — short-circuiting wait")
                        break
                await asyncio.sleep(0.2)

            if advanced:
                _log(worker_id, f"STEP[2/4] EMAIL: Advanced past email step. URL = {page.url[:100]}")
                break

            if attempt >= MAX_EMAIL_SUBMIT_ATTEMPTS:
                _log(worker_id, f"STEP[2/4] EMAIL: Still stuck after {MAX_EMAIL_SUBMIT_ATTEMPTS} attempts — "
                                f"giving up (URL={page.url[:80]}, reason={stuck_reason or 'no-advance'})")
                break

            # Recovery escalation: page.reload() for the first stall, but a
            # full page.goto(login_url) for every subsequent failure. Reloads
            # share cookies/state and sometimes inherit the same proxy stall
            # that caused the first failure; a fresh navigation forces a new
            # connection and bypasses Google's "Something went wrong" page.
            use_hard_nav = (attempt >= 2) or (stuck_reason in ('TRANSIENT_ERROR',))
            _log(worker_id, f"STEP[2/4] EMAIL: No advance after {ADVANCE_WAIT_SEC}s "
                            f"(reason={stuck_reason or 'no-advance'}, attempt={attempt}/{MAX_EMAIL_SUBMIT_ATTEMPTS}) "
                            f"— {'HARD-NAV reload' if use_hard_nav else 'page.reload'}")
            try:
                if use_hard_nav:
                    await page.goto(login_url, wait_until='domcontentloaded', timeout=25000)
                else:
                    await page.reload(wait_until='domcontentloaded', timeout=20000)
                # Brief backoff scales with attempt — gives the proxy gateway
                # time to drain queued requests under multi-worker stress.
                await asyncio.sleep(min(2 + attempt, 6))
            except Exception as _r_err:
                _log(worker_id, f"STEP[2/4] EMAIL: Reload failed: {str(_r_err)[:80]} — trying hard-nav fallback")
                try:
                    await page.goto(login_url, wait_until='domcontentloaded', timeout=25000)
                    await asyncio.sleep(3)
                except Exception as _gerr:
                    _log(worker_id, f"STEP[2/4] EMAIL: Hard-nav also failed: {str(_gerr)[:80]}")

            await _wait_for_any(page, email_selectors, timeout=ELEMENT_WAIT_TIMEOUT)
            elem_retry, sel_retry = await _first_visible_locator(page, email_selectors)
            if elem_retry is None:
                _log(worker_id, "STEP[2/4] EMAIL: Email field not visible after reload — abandoning retries")
                break
            if await _value_matches(elem_retry, email):
                _log(worker_id, f"STEP[2/4] EMAIL: Field still filled after reload via '{sel_retry}' — re-submitting")
            else:
                _log(worker_id, f"STEP[2/4] EMAIL: Re-typing email after reload via '{sel_retry}'")
                try: await elem_retry.click()
                except Exception: pass
                try: await elem_retry.focus()
                except Exception: pass
                try: await elem_retry.fill('')
                except Exception: pass
                await _human_type_to_element(elem_retry, email)

        _log(worker_id, f"STEP[2/4] EMAIL: After Submit. URL = {page.url[:100]}")

        # Security-redirect check — if Google bounced us to /signin/rejected
        # (account disabled), the support/recovery page, or anything else
        # in _is_google_security_redirect, fail immediately rather than
        # marching into the password step on a dead account.
        sec_reason = _is_google_security_redirect(page.url)
        if sec_reason:
            _log(worker_id, f"STEP[2/4] EMAIL: ✗ {sec_reason}")
            raise Exception(sec_reason)

        # POST-EMAIL: CAPTCHA check
        _log(worker_id, "STEP[2/4] EMAIL: Checking for post-email CAPTCHA...")
        if await _check_captcha_screen(page, worker_id):
            raise Exception("CAPTCHA_REQUIRED - Google is showing CAPTCHA verification.")
        screen = await detector.detect_current_screen()
        _log(worker_id, f"STEP[2/4] EMAIL: Post-email screen = {screen.name}")
        if screen == LoginScreen.CAPTCHA_REQUIRED:
            raise Exception("CAPTCHA_REQUIRED - Google reCAPTCHA detected after email.")

        # POST-EMAIL: Passkey challenge ("Use your fingerprint, face, or screen lock")
        # Google may show this BEFORE the password screen — click "Try another way"
        # Also handles Google v3 /challenge/pk/presend screens
        if screen == LoginScreen.PASSKEY_PROMPT:
            _log(worker_id, f"STEP[2/4] EMAIL: Passkey challenge detected after email — URL = {page.url[:100]}")
            _log(worker_id, "STEP[2/4] EMAIL: Clicking 'Try another way' (NOT 'Continue')...")
            pk_clicked = False
            for pk_sel in [
                'button:has-text("Try another way")',
                'a:has-text("Try another way")',
                '[role="button"]:has-text("Try another way")',
                'div[role="link"]:has-text("Try another way")',
                # Google v3 passkey page: jsname-based selectors
                '[jsname="Njthtb"]',
                '[jsname="PvB1Bd"]',
                # Fallback: text-based broader match
                ':text("Try another way")',
                'button:has-text("Not now")',
                'a:has-text("Not now")',
            ]:
                try:
                    pk_btn = page.locator(pk_sel).first
                    if await pk_btn.count() > 0 and await pk_btn.is_visible():
                        await pk_btn.click()
                        _log(worker_id, f"STEP[2/4] EMAIL: Clicked: {pk_sel}")
                        pk_clicked = True
                        break
                except Exception:
                    continue
            if pk_clicked:
                _log(worker_id, "STEP[2/4] EMAIL: Waiting for password field after passkey skip...")
                await _wait_for_any(page, [
                    'input[type="password"]', 'input[name="Passwd"]',
                    'div[data-challengetype]', 'li:has-text("Enter your password")',
                ], timeout=7000)
                _log(worker_id, f"STEP[2/4] EMAIL: After passkey skip. URL = {page.url[:100]}")

                # After "Try another way", Google may show a METHOD SELECTION page
                # (challenge/selection) instead of the password page.
                # We need to click "Enter your password" to get to the password field.
                _log(worker_id, "STEP[2/4] EMAIL: Checking if method selection page appeared...")
                post_pk_screen = await detector.detect_current_screen()
                _log(worker_id, f"STEP[2/4] EMAIL: Post-passkey screen = {post_pk_screen.name}")

                if post_pk_screen in (LoginScreen.ACCOUNT_RECOVERY, LoginScreen.TRY_ANOTHER_WAY):
                    _log(worker_id, "STEP[2/4] EMAIL: Method selection page — looking for 'Enter your password' option...")
                    pw_option_clicked = False
                    for pw_opt_sel in [
                        'li:has-text("Enter your password")',
                        'div[role="link"]:has-text("Enter your password")',
                        '[data-challengetype]:has-text("Enter your password")',
                        '[jsname="EBHGs"]:has-text("password")',
                        'li:has-text("password")',
                        'div[role="link"]:has-text("password")',
                        # Also try clicking a password-related challenge type
                        '[data-challengetype]:has-text("Password")',
                    ]:
                        try:
                            opt = page.locator(pw_opt_sel).first
                            if await opt.count() > 0 and await opt.is_visible():
                                await opt.click()
                                _log(worker_id, f"STEP[2/4] EMAIL: Clicked password option: {pw_opt_sel}")
                                pw_option_clicked = True
                                break
                        except Exception:
                            continue
                    if pw_option_clicked:
                        _log(worker_id, "STEP[2/4] EMAIL: Waiting for password page...")
                        await _wait_for_any(page, [
                            'input[type="password"]', 'input[name="Passwd"]',
                        ], timeout=7000)
                        _log(worker_id, f"STEP[2/4] EMAIL: After password option. URL = {page.url[:100]}")
                    else:
                        _log(worker_id, "STEP[2/4] EMAIL: WARNING - Could not find 'Enter your password' option")
            else:
                _log(worker_id, "STEP[2/4] EMAIL: WARNING - Could not click 'Try another way' on passkey screen")

        # ============================================================
        # STEP 3: Enter password — single-shot, no retry
        # ============================================================
        # The post-email-Submit wait already parked us on a /challenge/*
        # page and gave the next input time to render. We find the
        # password field once and either fill it or fail fast — same
        # pattern as the email step. Passkey / method-selection edge
        # cases are handled upstream (post-email Passkey block); if for
        # some reason we land here on a non-password challenge, we fail
        # cleanly so the caller can move on.
        # URL guard — if we're STILL on the identifier page despite the
        # reload-retry above, the page is genuinely stuck. Do NOT try to
        # find a password field: Google's email page contains a HIDDEN
        # autofill password input that Playwright treats as visible, and
        # typing into it dumps the password into the focused EMAIL field
        # (silent data corruption). Fail cleanly so the caller can move on.
        if '/identifier' in page.url:
            _log(worker_id, f"STEP[3/4] PASSWORD: STILL on /identifier after reload-retry — page genuinely stuck")
            raise Exception(
                "EMAIL_PAGE_STUCK - Identifier page never advanced even after one reload. "
                f"Final URL: {page.url[:120]}"
            )

        _log(worker_id, "STEP[3/4] PASSWORD: Looking for password input field...")
        # Selectors ordered most-specific-and-stable → most-generic.
        # User-shared HTML for Google's v3 password input:
        #   <input type="password" class="whsOnd zHQkBf" jsname="YPqjbf"
        #          autocomplete="current-password webauthn" name="Passwd"
        #          aria-label="Enter your password" ...>
        # We target stable attributes; avoid the hashed CSS classes
        # (aCsJod / oJeWuf / Xb9hP) which rotate between Google builds.
        pwd_selectors = [
            'input[name="Passwd"][type="password"]',     # name + type — exact role match
            'input[jsname="YPqjbf"]',                    # Google's stable-ish jsname
            'input[autocomplete*="current-password"]',   # autocomplete attribute (stable)
            'input[name="Passwd"]',                      # name-only fallback
            'input[type="password"]',                    # generic fallback
        ]

        # Wait briefly for the password field to render on the current page.
        await _wait_for_any(page, pwd_selectors, timeout=ELEMENT_WAIT_TIMEOUT)

        elem, sel = await _first_visible_locator(page, pwd_selectors)

        if elem is None:
            _log(worker_id, "STEP[3/4] PASSWORD: FAILED - password field not visible")
            _log(worker_id, f"STEP[3/4] PASSWORD: Final URL = {page.url[:100]}")
            raise Exception("Could not enter password - input field not found")

        if await _value_matches(elem, password):
            _log(worker_id, f"STEP[3/4] PASSWORD: Already filled via '{sel}' — skipping retype")
        else:
            try: await elem.click()
            except Exception: pass
            try: await elem.focus()
            except Exception: pass
            try: await elem.fill('')
            except Exception: pass
            # Element-bound typing — critical here because if Google's
            # /identifier page stalled and never advanced to /challenge/pwd,
            # page.keyboard.type() would dump the password INTO THE EMAIL
            # FIELD (the user's reported bug). Press-on-element ensures
            # every char lands in the password input or raises cleanly.
            await _human_type_to_element(elem, password)
            _log(worker_id, f"STEP[3/4] PASSWORD: Typed password via '{sel}' (humanized)")

        _log(worker_id, "STEP[3/4] PASSWORD: Clicking Next button...")
        await page.locator('button:has-text("Next")').first.click()
        _log(worker_id, "STEP[3/4] PASSWORD: Clicked Next. Waiting for URL to leave /challenge/pwd...")
        # URL-based progress probe — returns the moment we move off the password
        # challenge URL (to /challenge/totp, /challenge/dp, myaccount, etc.).
        # Faster + more reliable than waiting for specific DOM elements (which
        # don't exist on myaccount and were forcing the full 9s timeout for
        # no-2FA accounts).
        post_pw_deadline = time.monotonic() + 6
        while time.monotonic() < post_pw_deadline:
            cu = page.url
            if 'challenge/pwd' not in cu:
                break
            await asyncio.sleep(0.2)
        _log(worker_id, f"STEP[3/4] PASSWORD: After Next. URL = {page.url[:100]}")

        # POST-PASSWORD: error checks
        _log(worker_id, "STEP[3/4] PASSWORD: Checking for post-password errors...")
        _pwd_notice = await _check_password_changed_error(page, worker_id)
        if _pwd_notice == 'PASSWORD_RECENTLY_CHANGED':
            # Distinct error string so _login_profile_impl can tag the profile
            # into the "Password Changed" group (the account holder rotated
            # their password; our stored copy is stale).
            raise Exception("PASSWORD_RECENTLY_CHANGED - Google reports the account password was changed (multilingual notice detected)")
        if _pwd_notice == 'B34EJ_GENERIC':
            # B34EJ visible but no recently-changed signature — fall through
            # to the wrong-password check which has its own visible-text
            # patterns. If neither matches, log and proceed.
            pass
        if await _check_wrong_password(page, worker_id):
            raise Exception("WRONG_PASSWORD - Google says password is incorrect.")
        _log(worker_id, "STEP[3/4] PASSWORD: No post-password errors detected")

        # Quick success check: if password directly landed us on myaccount
        # (no 2FA on this profile), short-circuit STEP 4 polling entirely.
        current_url = page.url
        _log(worker_id, f"STEP[3/4] PASSWORD: Post-password URL = {current_url[:100]}")

        # Security redirect check first
        redirect_reason = _is_google_security_redirect(current_url)
        if redirect_reason:
            if 'ACCOUNT_RECOVERY_REDIRECT' in redirect_reason:
                _log(worker_id, f"STEP[3/4] PASSWORD: {redirect_reason} — attempting recovery...")
                recovery = await _try_recover_from_support_redirect(
                    page, worker_id, require_inbox, forced_new_password)
                if recovery:
                    return recovery
            raise Exception(redirect_reason)

        # Quick myaccount short-circuit — skip STEP 4 entirely if already there.
        # STRICT URL check: continue= query on /challenge/* pages contains
        # myaccount.google.com too, but those aren't logged-in states.
        if _is_myaccount_url(current_url):
            if await _verify_login_by_email(page, worker_id, email):
                _log(worker_id, "LOGIN SUCCESS: myaccount + email matched (no 2FA needed)")
                return {'success': True, 'forced_new_password': forced_new_password}

        # ============================================================
        # STEP 4: Polling loop - handle all OPTIONAL screens
        # ============================================================
        _log(worker_id, "STEP[4/4] POLLING: Starting post-password screen handling loop...")
        _log(worker_id, f"STEP[4/4] POLLING: Max iterations = {MAX_LOGIN_ITERATIONS}")

        max_iterations = MAX_LOGIN_ITERATIONS
        stuck_url = None
        stuck_count = 0

        # ── Create LoginBrain with credentials from Excel ──
        # Read new password for forced password change scenario
        acct_new_pw = account.get('New Password', '')
        if pd.isna(acct_new_pw):
            acct_new_pw = ''
        acct_new_pw = str(acct_new_pw).strip()

        brain = LoginBrain(
            page=page,
            detector=detector,
            credentials={
                'email': email,
                'password': password,
                'totp_secret': totp_secret,
                'backup_code': backup_code_raw,
                'recovery_email': recovery_email,
                'recovery_phone': recovery_phone,
                'new_password': acct_new_pw,
                'new_recovery_phone': str(account.get('New Recovery Phone', '') or '').strip(),
                'new_recovery_email': str(account.get('New Recovery Email', '') or '').strip(),
            },
            config={'require_inbox': require_inbox},
            log_fn=lambda msg: _log(worker_id, msg),
        )

        for iteration in range(max_iterations):
            current_url = page.url
            _log(worker_id, f"--- POLL ITERATION {iteration+1}/{max_iterations} ---")
            _log(worker_id, f"  URL = {current_url[:100]}")

            # ── INSTANT myaccount URL success + email verify ──
            # First thing every iteration: if we're actually on myaccount
            # (STRICT — not the continue= query on a /challenge/ page),
            # verify the profile email is on the page and return success.
            if _is_myaccount_url(current_url):
                if await _verify_login_by_email(page, worker_id, email):
                    _log(worker_id, "LOGIN SUCCESS: myaccount URL + email matched")
                    return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}

            # ---- STUCK DETECTION: reload if URL unchanged for 3 iterations ----
            if current_url == stuck_url:
                stuck_count += 1
                if stuck_count >= 3:
                    if brain.totp_submitted and 'challenge/totp' in current_url:
                        _log(worker_id, f"  STUCK on TOTP page but code was submitted — waiting (no reload)...")
                        await asyncio.sleep(3)
                        stuck_count = 0
                    else:
                        _log(worker_id, f"  STUCK DETECTED: Same URL for {stuck_count} iterations, reloading...")
                        try:
                            await page.reload(wait_until="domcontentloaded", timeout=15000)
                            await asyncio.sleep(3)
                            stuck_count = 0
                        except Exception as reload_err:
                            _log(worker_id, f"  Reload failed: {str(reload_err)[:50]}")
            else:
                stuck_url = current_url
                stuck_count = 0

            # ---- Check for chrome error pages (network issues) ----
            if _is_chrome_error(current_url):
                _log(worker_id, f"  CHROME ERROR page detected, going back...")
                try:
                    await page.go_back(wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(3)
                    continue
                except Exception:
                    pass

            # ---- EARLY EXIT: Google redirected to a security/help page ----
            sec_reason = _is_google_security_redirect(current_url)
            if sec_reason:
                _log(worker_id, f"  SECURITY REDIRECT: {sec_reason} (URL: {current_url[:150]})")

                # gds.google.com/web/recoveryoptions = post-login "add recovery info" page.
                # Session IS valid — recovery helper navigates to myaccount.
                if 'RECOVERY_OPTIONS_REDIRECT' in sec_reason:
                    _log(worker_id, "  Recovery options page (post-login) — session valid, navigating away...")
                    recovery = await _try_recover_from_support_redirect(
                        page, worker_id, require_inbox, brain.forced_new_password or forced_new_password)
                    if recovery:
                        return recovery
                    # Recovery helper couldn't confirm myaccount — session likely still valid
                    _log(worker_id, "  LOGIN SUCCESS: Recovery options page = logged in")
                    return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}

                if 'ACCOUNT_RECOVERY_REDIRECT' in sec_reason:
                    recovery = await _try_recover_from_support_redirect(
                        page, worker_id, require_inbox, brain.forced_new_password or forced_new_password)
                    if recovery:
                        return recovery
                raise Exception(sec_reason)

            screen = await detector.detect_current_screen()
            _log(worker_id, f"  Screen detected = {screen.name}")

            # ── LOGGED_IN / SUCCESS_SCREEN: trust the screen detection ──
            # The unified login URL lands on myaccount; the strict URL check
            # at the top of every iteration (`_is_myaccount_url + email match`)
            # is the primary success signal. If we got here via screen
            # detection instead, the page is on a login-success surface
            # (myaccount.google.com / "Success!" page) but the email DOM
            # element wasn't visible during the URL-based verify above —
            # trust the screen and return success without another DOM probe.
            if screen == LoginScreen.LOGGED_IN:
                _log(worker_id, "LOGIN SUCCESS: LOGGED_IN screen confirmed!")
                return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}

            if screen == LoginScreen.SUCCESS_SCREEN:
                _log(worker_id, "LOGIN SUCCESS: SUCCESS_SCREEN confirmed!")
                return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}

            # ── Special handling for UNKNOWN screen (chrome error recovery + inbox direct) ──
            if screen == LoginScreen.UNKNOWN:
                # Chrome error recovery (needs login_url which brain doesn't have)
                if _is_chrome_error(current_url):
                    _log(worker_id, "  CHROME ERROR PAGE — recovering...")
                    try:
                        await page.go_back(wait_until="domcontentloaded", timeout=10000)
                        await asyncio.sleep(2)
                        if _is_chrome_error(page.url):
                            await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                            await asyncio.sleep(3)
                    except Exception:
                        pass
                    await asyncio.sleep(3)
                    continue

                # Error checks specific to login_flow
                if await _check_password_changed_error(page, worker_id):
                    raise Exception("PASSWORD_CHANGED - Google says password was changed.")
                if await _check_wrong_password(page, worker_id):
                    raise Exception("WRONG_PASSWORD - Google says password is incorrect.")

            # ── Delegate to LoginBrain for all screen handling ──
            result = await brain.handle_screen(screen)

            if result.action == "success":
                fp = (result.data or {}).get('forced_new_password', '') or forced_new_password
                _log(worker_id, f"LOGIN SUCCESS via brain: {screen.name}")
                # Tight URL poll (0.1s interval, 3s max) — returns the moment
                # the URL transitions to inbox. NO hardcoded 3s sleep — we
                # check 30x as often so most healthy logins return in <0.5s.
                inbox_deadline = time.monotonic() + 3
                while time.monotonic() < inbox_deadline:
                    cu = page.url
                    if _is_myaccount_url(cu):
                        _log(worker_id, "LOGIN SUCCESS: myaccount URL reached after brain success")
                        return {'success': True, 'forced_new_password': fp}
                    await asyncio.sleep(0.1)
                # URL didn't transition — trust the brain's success signal.
                _log(worker_id, "LOGIN SUCCESS: brain confirmed (URL not yet myaccount)")
                return {'success': True, 'forced_new_password': fp}

            elif result.action == "fail":
                raise Exception(result.error)

            elif result.action == "skip":
                # Brain has no handler — wait and retry
                _log(worker_id, f"  UNHANDLED screen: {screen.name}. Waiting 3s...")
                await asyncio.sleep(3)

            # "continue" → next iteration

        # ============================================================
        # FINAL CHECK (after all iterations exhausted)
        # ============================================================
        _log(worker_id, "FINAL CHECK: All iterations done. Doing final detection...")
        final_url = page.url
        final_screen = await detector.detect_current_screen()
        _log(worker_id, f"FINAL CHECK: Screen = {final_screen.name}, URL = {final_url[:100]}")
        fp = brain.forced_new_password or forced_new_password

        if final_screen in [LoginScreen.LOGGED_IN, LoginScreen.SUCCESS_SCREEN]:
            _log(worker_id, f"LOGIN SUCCESS: Final screen = {final_screen.name}")
            return {'success': True, 'forced_new_password': fp}
        if _is_myaccount_url(final_url):
            _log(worker_id, "LOGIN SUCCESS: Final URL is myaccount")
            return {'success': True, 'forced_new_password': fp}

        _log(worker_id, f"LOGIN FAILED: Timeout after {max_iterations} iterations")
        _log(worker_id, f"LOGIN FAILED: Final URL = {final_url}")
        _log(worker_id, f"LOGIN FAILED: Final screen = {final_screen.name}")
        raise Exception(f"LOGIN_TIMEOUT - Could not reach login success after {max_iterations} iterations. Final: screen={final_screen.name}, URL={final_url[:100]}")

    except Exception as e:
        _log(worker_id, f"LOGIN ERROR: {e}")
        _log(worker_id, f"LOGIN ERROR: URL at error = {page.url}")
        return {'success': False, 'error': str(e)}
