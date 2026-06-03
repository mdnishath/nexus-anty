# Serial Login Sessions + Logout-Link Verification — Design

Date: 2026-05-25
Status: Approved (pending spec review)

## Goal

Two related changes to the batch login flow:

1. **Serial credential phase.** Today multiple workers can be in the middle of typing email/password/2FA at the same instant — Google's anti-bot stack sometimes interprets that as scripted spam and stalls or rejects sessions. Hold a single "login session slot" so only one worker is inside the credential entry phase (email → password → 2FA) at a time, while all browsers stay open in parallel.
2. **Logout-link based login verification.** Replace the inbox-URL success check with "does the page contain `a[href*="accounts.google.com/Logout"]` on myaccount.google.com?". Inbox URL is a poor success signal because accounts whose Gmail is disabled can still be fully authenticated, and the existing 15-second inbox wait is the dominant per-account cost.

The user-stated goal is: serialize login flow per worker so Google does not see concurrent typing/credential events from one IP/proxy cluster, and verify success via a signal that works even when Gmail is disabled.

## Non-goals

- No change to selectors used during email/password/2FA typing (existing humanized typing parameters stay).
- No change to screen detection logic beyond `_is_logged_in()`.
- No change to profile creation, proxy assignment, OS rotation, fingerprinting.
- No change to the existing `TypingSlot` per-key gate's design — but it becomes redundant under the outer slot and is removed.
- No change to dispatch concurrency (`ThreadPoolExecutor` worker count stays). Throughput is controlled by the slot's hold time, not worker count.

## Current state (reference)

- Top-of-file constants and helpers in [src/login_flow.py](src/login_flow.py:15): `INBOX_URL = "mail.google.com/mail"`, `_is_inbox_url()`, `_wait_for_inbox_load()`.
- Existing per-key gate: `TypingSlot` at [src/login_flow.py:33](src/login_flow.py:33) with `GAP_SECONDS = 2.0`, used at lines 581 (email) and 775 (password).
- Login entry point: `execute_login_flow(page, account, worker_id, login_url, detector=None, totp_gen=None, require_inbox=True)` at [src/login_flow.py:393](src/login_flow.py:393).
- Inbox wait usage: lines 824, 933, 1018, 1049 — each one polls for up to 15s and is the main slow path.
- Inbox-URL early success: lines 822, 931 short-circuit before any verification.
- Recovery navigation: `_try_recover_from_support_redirect` at line 199 uses `'https://mail.google.com/mail/' if require_inbox else 'https://myaccount.google.com/'`.
- Screen detector `_is_logged_in()` at [src/screen_detector.py:450](src/screen_detector.py:450) currently checks `mail.google.com/mail` URL, `myaccount.google.com` URL, and avatar selectors.
- Callers of `execute_login_flow`:
  - [linked/runner.py:209](linked/runner.py:209) — Step 1, `require_inbox=True`.
  - [linked/runner.py:325](linked/runner.py:325) — Step 2 fallback, `require_inbox=False`.
  - [shared/base_runner.py:528](shared/base_runner.py:528) — generic operations runner.
  - `step2/runner.py:90` — passes `require_inbox=False`.
  - `src/gmail_authenticator.py:202` — `require_inbox=False`.

## Design

### Part 1 — `LoginSessionSlot`: serialize whole credential phase

A coarse-grained lock that one worker holds for its entire credential entry phase. All other workers wait. The slot is acquired only AFTER the worker has finished pre-credential work (navigate to login URL, screen-detect "already logged in"); if a profile is already authenticated, no slot is taken.

```python
import threading, time
from contextlib import contextmanager

class LoginSessionSlot:
    """Serializes the full credential entry phase across all batch workers.

    One worker holds the slot from start of email typing through end of 2FA
    (or password submit if no 2FA). Inbox/myaccount verification happens
    AFTER the slot is released, in parallel.

    Includes a watchdog: if a worker holds longer than MAX_HOLD_SECONDS the
    lock is force-released so a single stuck account can not block the batch.
    """
    _lock = threading.Lock()
    MAX_HOLD_SECONDS = 180  # 3 min hard cap per worker session

    @classmethod
    @contextmanager
    def acquire(cls, worker_id="?"):
        t0 = time.monotonic()
        _log(worker_id, "LOGIN_SLOT: waiting for slot...")
        cls._lock.acquire()  # blocks until previous holder releases
        _log(worker_id, f"LOGIN_SLOT: ACQUIRED after {time.monotonic()-t0:.1f}s wait")

        released = {"done": False}
        def _watchdog():
            if not released["done"]:
                try:
                    cls._lock.release()
                    released["done"] = True
                    _log(worker_id, f"LOGIN_SLOT: WATCHDOG force-released after {cls.MAX_HOLD_SECONDS}s")
                except RuntimeError:
                    pass
        timer = threading.Timer(cls.MAX_HOLD_SECONDS, _watchdog)
        timer.daemon = True
        timer.start()

        held_t0 = time.monotonic()
        try:
            yield
        finally:
            timer.cancel()
            if not released["done"]:
                try:
                    cls._lock.release()
                    released["done"] = True
                except RuntimeError:
                    pass
            _log(worker_id, f"LOGIN_SLOT: released after holding {time.monotonic()-held_t0:.1f}s")
```

#### Where `LoginSessionSlot` wraps inside `execute_login_flow`

The acquire point is **just before the first iteration of the screen-detect loop that actually types something** — i.e. after the initial navigation to the login URL and after we've checked "already logged in?". The release point is **once we observe success or fail** of the credential entry (LOGGED_IN screen detected, or terminal error, or watchdog).

Pseudocode pattern (overlaid on the real loop):

```python
async def execute_login_flow(page, account, worker_id, login_url, ...):
    # Phase A — navigation + already-logged-in fast-path (NO SLOT)
    await page.goto(login_url, ...)
    screen = await detector.detect_current_screen()
    if screen == LoginScreen.LOGGED_IN:
        # No credential entry needed → no slot
        return await _post_login_finalize(page, worker_id, require_inbox)

    # Phase B — credential entry (HOLD SLOT)
    with LoginSessionSlot.acquire(worker_id):
        # existing screen-detect / handler loop runs here:
        #   email screen → fill+submit
        #   password screen → fill+submit
        #   2FA challenge screen → fill+submit
        # Loop exits when:
        #   - LOGGED_IN detected, OR
        #   - terminal failure (ACCOUNT_LOCKED, TOO_MANY_ATTEMPTS, etc.), OR
        #   - MAX_LOGIN_ITERATIONS reached
        login_outcome = await _credential_loop(page, ...)

    # Phase C — verify + optional inbox nav (NO SLOT, parallel across workers)
    if login_outcome.failed:
        return {'success': False, 'error': login_outcome.error}
    return await _post_login_finalize(page, worker_id, require_inbox)
```

#### Existing `TypingSlot` removal

`TypingSlot` (lines 33–70, used at 581 and 775) becomes redundant: only one worker is ever inside the slot block at a time, so the per-keystroke gate has no contention to manage. Remove the class definition and both `with TypingSlot.acquire(...)` wrappers; leave the `await elem.fill(...)` calls in place.

### Part 2 — Logout-link verification

#### New constants

```python
MYACCOUNT_URL = 'https://myaccount.google.com/'
LOGOUT_LINK_SELECTOR = 'a[href*="accounts.google.com/Logout"]'
```

`LOGOUT_LINK_SELECTOR` is href-based, so it survives Google's class hashing. The user's reference markup also has `[data-sol]` and `[jsname="L8VV9b"]` — these are useful tiebreakers if the href check ever misses, but the href is the most stable single signal.

#### New verification helper

```python
async def _verify_login_via_logout(page, worker_id, timeout_s: int = 12):
    """Navigate to myaccount and confirm the user is authenticated.

    Returns:
        True              — logout link or account-avatar found = logged in.
        False             — kicked to signin, or no logged-in signal within timeout.
        str               — security/help redirect (returned verbatim, callers treat as error).
    """
    _log(worker_id, "VERIFY: Navigating to myaccount to check for logout link...")
    try:
        await page.goto(MYACCOUNT_URL, wait_until='domcontentloaded', timeout=15000)
    except Exception as e:
        _log(worker_id, f"VERIFY: Nav to myaccount failed: {str(e)[:80]}")
        return False

    redirect_reason = _is_google_security_redirect(page.url)
    if redirect_reason and 'RECOVERY_OPTIONS_REDIRECT' not in redirect_reason:
        _log(worker_id, f"VERIFY: SECURITY REDIRECT -> {redirect_reason}")
        return redirect_reason

    if 'accounts.google.com' in page.url and 'signin' in page.url:
        _log(worker_id, "VERIFY: Redirected back to signin — NOT logged in")
        return False

    try:
        await page.wait_for_selector(LOGOUT_LINK_SELECTOR,
                                     state='attached',
                                     timeout=timeout_s * 1000)
        _log(worker_id, "VERIFY: SUCCESS — logout link found")
        return True
    except Exception:
        try:
            avatar_count = await page.locator(
                '[data-email], a[aria-label*="Google Account"], img[alt*="profile picture" i]'
            ).first.count()
        except Exception:
            avatar_count = 0
        if avatar_count > 0:
            _log(worker_id, "VERIFY: SUCCESS — account avatar found (logout link not visible yet)")
            return True
        _log(worker_id, f"VERIFY: FAILED — no logged-in signal at {page.url[:80]}")
        return False
```

#### Replace inbox-URL success paths

Every place that currently calls `_wait_for_inbox_load(page, worker_id)` is replaced by `_verify_login_via_logout(page, worker_id)`:

- [src/login_flow.py:824](src/login_flow.py:824) — quick inbox check after password.
- [src/login_flow.py:933](src/login_flow.py:933) — inbox URL success branch in main loop.
- [src/login_flow.py:1018](src/login_flow.py:1018) — final inbox wait at loop end.
- [src/login_flow.py:1049](src/login_flow.py:1049) — last-chance inbox wait.

Every place that currently uses `_is_inbox_url(current_url)` as a success short-circuit before calling `_wait_for_inbox_load`:

- [src/login_flow.py:822](src/login_flow.py:822), [src/login_flow.py:931](src/login_flow.py:931) — drop the short-circuit; always go through `_verify_login_via_logout`.

`_wait_for_inbox_load` and `_is_inbox_url` are deleted after the last caller is gone. The `INBOX_URL` constant is also removed.

#### `require_inbox` parameter — kept, repurposed

The parameter remains on `execute_login_flow` for backward compatibility but its meaning changes:

- `require_inbox=False` (default new behavior): success = logout link verified on myaccount. Returns immediately.
- `require_inbox=True`: after logout-link success, additionally `page.goto('https://mail.google.com/mail/')`. The result includes a new boolean `inbox_accessible`. If Gmail is reachable, `inbox_accessible=True`; if Gmail redirects to a disabled-mail page or error, `inbox_accessible=False`, but `success` stays True (the account is logged in, Gmail is just unavailable).

Callers that strictly need Gmail (linked/runner.py Step 1, gmail_health, etc.) can branch on `inbox_accessible`. Callers that only need account access (Step 2, appeals, etc.) ignore it.

#### Update `screen_detector._is_logged_in`

Reorder the checks so the href-based logout selector is tried first; avatar/data-email become fallbacks:

```python
async def _is_logged_in(self) -> bool:
    return await self._selector_visible_any([
        'a[href*="accounts.google.com/Logout"]',  # primary
        '[data-email]',
        'a[aria-label*="Google Account"]',
        'img[alt*="profile picture" i]',
        'a[href*="myaccount.google.com"]',
    ])
```

URL-based hints (`mail.google.com/mail`, `myaccount.google.com`) are removed from `_is_logged_in` — they were the cause of false positives on intermediate redirect pages.

### Recovery-from-support-redirect

`_try_recover_from_support_redirect` (line 199) currently navigates to inbox or myaccount based on `require_inbox`. Updated:

- Always navigate to `MYACCOUNT_URL`.
- Verify via `_verify_login_via_logout` instead of URL matching.
- If `require_inbox=True` AND verification succeeded, follow up with the Gmail navigation described above (sets `inbox_accessible`).

## Files changed (summary)

| File | What changes |
| --- | --- |
| `src/login_flow.py` | Add `LoginSessionSlot` class. Wrap credential phase of `execute_login_flow` with `with LoginSessionSlot.acquire(worker_id)`. Remove `TypingSlot` class and its two `with` usages. Add `MYACCOUNT_URL`, `LOGOUT_LINK_SELECTOR`, `_verify_login_via_logout`. Replace all `_wait_for_inbox_load` calls with `_verify_login_via_logout`. Remove `_wait_for_inbox_load`, `_is_inbox_url`, `INBOX_URL`. Update `_try_recover_from_support_redirect`. Add `inbox_accessible` to result dict in `require_inbox=True` path. |
| `src/screen_detector.py` | Reorder `_is_logged_in()` to lead with `a[href*="accounts.google.com/Logout"]`. Remove URL-based checks. |

After the worktree commit, copy both files into the main directory `E:\NST Anty Android\` per the project convention.

No changes to `shared/profile_manager.py`, `shared/base_runner.py`, `linked/runner.py`, `step*/runner.py`, or any UI module. Callers that read `inbox_accessible` from the result will be added in a follow-up only if a concrete need surfaces; for now their existing behavior on `success=True` is unchanged because they don't read the new field.

## Testing

### Manual — batch login

1. Run a batch login with `num_workers = 5` on a sheet of 8+ accounts.
2. Watch logs:
   - Expect `LOGIN_SLOT: waiting for slot...` then `LOGIN_SLOT: ACQUIRED after Xs wait` for workers 2..N.
   - Expect `LOGIN_SLOT: released after holding Ys` lines, with `Y < 60` for healthy accounts.
   - Expect zero `TYPING_SLOT:` lines (class removed).
3. Watch a successful account: expect `VERIFY: Navigating to myaccount...` then `VERIFY: SUCCESS — logout link found`.
4. Confirm no `INBOX_WAIT:` lines anywhere (function deleted).

### Manual — Gmail-disabled account

1. Pick an account known to have Gmail disabled (or simulate by revoking Gmail product access).
2. Run login. Expect: `VERIFY: SUCCESS — logout link found` AND result dict has `success=True`. If `require_inbox=True` was passed, expect `inbox_accessible=False` in the result but `success=True`.

### Manual — stuck worker

1. Trigger a CAPTCHA challenge on one account (use a flagged proxy).
2. Wait for the watchdog: expect `LOGIN_SLOT: WATCHDOG force-released after 180s` then the next worker proceeds.
3. Confirm the stuck worker's result eventually completes (fail or success) without blocking the rest of the batch.

### Manual — already-logged-in fast-path

1. Pre-warm one profile (log in manually, close, re-open).
2. Run batch login. Expect that profile to skip the slot entirely (no `LOGIN_SLOT:` lines for it) and report success quickly.

### Manual — concurrent timing check

1. Run batch login with `num_workers = 3` on 6 accounts.
2. Check that at no two timestamps in the log do two workers print "EMAIL_FILL" or "PASSWORD_FILL" within 1 second of each other. (Quick grep proves the serialization is working.)

## Risks

- **Logout link rendering delay on myaccount.** The link is sometimes deferred until the account menu finishes hydrating. Mitigated by 12s timeout + `[data-email]`/avatar fallback. If false-negatives occur in production, bump timeout to 20s.
- **Slot serialization halves throughput at high worker counts.** With `num_workers = 10` and 30s credential phase, total login time is ~5 min per 10 accounts rather than ~30s parallel. Acceptable because Google was rejecting the parallel attempts anyway; net wall time should improve or stay the same.
- **Watchdog race.** Force-release sets `released["done"] = True` after release, but a `finally` block could observe `released["done"] = False` between the timer firing and `done` being set. Mitigated by `try: release(); except RuntimeError: pass` on both paths — releasing twice raises `RuntimeError` which is caught.
- **`require_inbox=True` callers not reading `inbox_accessible`.** Today they only check `success`. They'll get `success=True` for accounts where Gmail is unavailable, then their downstream Gmail operation will fail with its own error. This is no worse than current behavior, because today those accounts fail at the inbox-wait step with `success=False`. Net change: one extra failure mode shifted later in the pipeline, with a clearer error origin.
- **`_is_logged_in` losing URL hint.** Some intermediate redirect pages briefly show `mail.google.com/mail` URL before fully loading; we no longer count this as logged in. Replaced by the more reliable DOM selector. Should not regress real cases.

## Out of scope

- Per-worker rate limiting separate from the slot (e.g. "max 5 logins per minute per proxy") — not needed under the new serial regime.
- Visual UI indicator showing which worker currently holds the slot — log-only.
- Re-introducing inbox health checks as a separate health probe for accounts where Gmail matters — possible follow-up after `inbox_accessible` data accumulates.
- Adapting the slot for other field-typing flows (appeals, 2FA enable, etc.) — those are not concurrent-spam vectors per current evidence; revisit if reports emerge.
