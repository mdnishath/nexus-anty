# Serial Login Sessions + Logout-Link Verification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-keystroke `TypingSlot` with a coarse `LoginSessionSlot` that serializes one worker's full email→password→2FA phase, and replace the 15s inbox URL wait with a logout-link DOM check on myaccount.google.com.

**Architecture:** Add one new threading-Lock class (`LoginSessionSlot`) and one new async helper (`_verify_login_via_logout`) to `src/login_flow.py`. Wrap the credential-entry section of `execute_login_flow` with the slot. Replace every `_wait_for_inbox_load` call with the new verifier. Update `screen_detector._is_logged_in` to lead with the logout-link selector. Delete the now-unused `TypingSlot`, `_wait_for_inbox_load`, `_is_inbox_url`, and `INBOX_URL` symbols. Per memory rule, copy modified files into the main directory after every worktree commit.

**Tech Stack:** Python 3, Playwright async API, threading.Lock + threading.Timer, pytest, loguru.

**Spec:** [docs/superpowers/specs/2026-05-25-serial-login-and-logout-verify-design.md](docs/superpowers/specs/2026-05-25-serial-login-and-logout-verify-design.md)

---

## File Structure

**New files:**
- `tests/test_login_session_slot.py` — unit tests for the new threading slot (mirrors `tests/test_typing_slot.py` style)
- `tests/test_verify_login_via_logout.py` — unit tests for the async helper with mocked Page

**Modified files:**
- `src/login_flow.py` — bulk of the work: add new class + helper + constants, wrap `execute_login_flow`, replace inbox-wait calls, delete old code, update recovery helper, add `inbox_accessible` field
- `src/screen_detector.py` — reorder `_is_logged_in()` to lead with logout-link selector and drop URL hints

**Deleted files:**
- `tests/test_typing_slot.py` — `TypingSlot` is removed in Task 9

**Sync convention:** This project uses worktrees. After every worktree commit, also copy the modified files into `E:\NST Anty Android\` (the main directory the user runs from). See Task 12.

---

## Task 1: Add `LoginSessionSlot` class with watchdog

**Files:**
- Create: `tests/test_login_session_slot.py`
- Modify: `src/login_flow.py` (insert new class after `TypingSlot`, around line 71)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_login_session_slot.py`:

```python
"""Unit tests for LoginSessionSlot — the global credential-phase serializer."""
import threading
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.login_flow import LoginSessionSlot


def _fresh_lock():
    """Reset class state so tests don't share state."""
    if LoginSessionSlot._lock.locked():
        try:
            LoginSessionSlot._lock.release()
        except RuntimeError:
            pass


def test_first_acquire_is_immediate():
    _fresh_lock()
    t0 = time.monotonic()
    with LoginSessionSlot.acquire("w-1"):
        pass
    assert time.monotonic() - t0 < 0.3


def test_second_acquire_waits_until_first_releases():
    _fresh_lock()
    enter = []

    def worker(wid, hold):
        with LoginSessionSlot.acquire(f"w-{wid}"):
            enter.append((wid, time.monotonic()))
            time.sleep(hold)

    t0 = time.monotonic()
    t1 = threading.Thread(target=worker, args=(1, 0.5))
    t2 = threading.Thread(target=worker, args=(2, 0.0))
    t1.start()
    time.sleep(0.05)  # ensure w-1 grabs lock first
    t2.start()
    t1.join(); t2.join()

    enter.sort(key=lambda x: x[1])
    gap = enter[1][1] - enter[0][1]
    assert gap >= 0.45, f"second worker should wait for first; gap was {gap:.2f}s"


def test_three_workers_serialize():
    _fresh_lock()
    enter = []
    lock = threading.Lock()

    def worker(wid):
        with LoginSessionSlot.acquire(f"w-{wid}"):
            with lock:
                enter.append(time.monotonic())
            time.sleep(0.2)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    enter.sort()
    for i in range(1, len(enter)):
        gap = enter[i] - enter[i - 1]
        assert gap >= 0.18, f"gap {i} too small: {gap:.2f}s"


def test_max_hold_constant_is_180():
    assert LoginSessionSlot.MAX_HOLD_SECONDS == 180


def test_watchdog_force_releases_after_max_hold():
    """If a worker holds the slot longer than MAX_HOLD_SECONDS the watchdog releases it."""
    _fresh_lock()
    original = LoginSessionSlot.MAX_HOLD_SECONDS
    LoginSessionSlot.MAX_HOLD_SECONDS = 0.3
    try:
        # Hold the slot from one thread; meanwhile another acquires.
        holder_done = threading.Event()

        def stuck_holder():
            with LoginSessionSlot.acquire("stuck"):
                time.sleep(1.0)  # holds 1s, well past 0.3s watchdog
            holder_done.set()

        t = threading.Thread(target=stuck_holder, daemon=True)
        t.start()
        time.sleep(0.05)  # let it acquire

        # Second worker should be able to acquire after ~0.3s thanks to watchdog
        t0 = time.monotonic()
        with LoginSessionSlot.acquire("w-2"):
            elapsed = time.monotonic() - t0
        assert elapsed < 0.8, f"watchdog should release within 0.3s, second worker waited {elapsed:.2f}s"

        t.join(timeout=2)
    finally:
        LoginSessionSlot.MAX_HOLD_SECONDS = original
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
pytest tests/test_login_session_slot.py -v
```

Expected: All 5 tests fail with `ImportError: cannot import name 'LoginSessionSlot'`.

- [ ] **Step 3: Add the `LoginSessionSlot` class to `src/login_flow.py`**

Insert this code **immediately after** the existing `TypingSlot` class definition (after line 70, before the `_value_matches` helper). Do not modify `TypingSlot` yet — it is removed in Task 9.

```python
class LoginSessionSlot:
    """Serializes the full credential entry phase across all batch workers.

    One worker holds the slot from start of email typing through end of 2FA
    (or password submit if no 2FA). Inbox/myaccount verification happens
    AFTER the slot is released, in parallel.

    Includes a watchdog: if a worker holds the slot longer than
    MAX_HOLD_SECONDS the lock is force-released so a single stuck account
    does not block the rest of the batch.
    """
    _lock = threading.Lock()
    MAX_HOLD_SECONDS = 180  # 3 min hard cap per worker session

    @classmethod
    @contextmanager
    def acquire(cls, worker_id="?"):
        t0 = time.monotonic()
        try:
            _log(worker_id, "LOGIN_SLOT: waiting for slot...")
        except Exception:
            pass
        cls._lock.acquire()  # blocks until previous holder releases
        try:
            _log(worker_id, f"LOGIN_SLOT: ACQUIRED after {time.monotonic()-t0:.1f}s wait")
        except Exception:
            pass

        released = {"done": False}

        def _watchdog():
            if not released["done"]:
                try:
                    cls._lock.release()
                    released["done"] = True
                    try:
                        _log(worker_id, f"LOGIN_SLOT: WATCHDOG force-released after {cls.MAX_HOLD_SECONDS}s")
                    except Exception:
                        pass
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
            try:
                _log(worker_id, f"LOGIN_SLOT: released after holding {time.monotonic()-held_t0:.1f}s")
            except Exception:
                pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```
pytest tests/test_login_session_slot.py -v
```

Expected: All 5 tests PASS. (The watchdog test takes ~1s due to its `time.sleep(1.0)`.)

- [ ] **Step 5: Commit**

```
git add src/login_flow.py tests/test_login_session_slot.py
git commit -m "feat(login): add LoginSessionSlot — serialize credential phase across workers"
```

---

## Task 2: Add login verification constants

**Files:**
- Modify: `src/login_flow.py` (top, near `INBOX_URL`)

- [ ] **Step 1: Add the constants**

In `src/login_flow.py`, find the line:
```python
INBOX_URL = "mail.google.com/mail"
```

Immediately below it, add:
```python
MYACCOUNT_URL = 'https://myaccount.google.com/'
LOGOUT_LINK_SELECTOR = 'a[href*="accounts.google.com/Logout"]'
```

(Do NOT remove `INBOX_URL` yet. It is removed in Task 10 after all callers are gone.)

- [ ] **Step 2: Sanity-check imports compile**

Run:
```
python -c "from src.login_flow import MYACCOUNT_URL, LOGOUT_LINK_SELECTOR; print(MYACCOUNT_URL, LOGOUT_LINK_SELECTOR)"
```

Expected output:
```
https://myaccount.google.com/ a[href*="accounts.google.com/Logout"]
```

- [ ] **Step 3: Commit**

```
git add src/login_flow.py
git commit -m "feat(login): add MYACCOUNT_URL + LOGOUT_LINK_SELECTOR constants"
```

---

## Task 3: Add `_verify_login_via_logout` helper

**Files:**
- Create: `tests/test_verify_login_via_logout.py`
- Modify: `src/login_flow.py` (add new helper after the existing `_wait_for_inbox_load`, around line 310)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verify_login_via_logout.py`:

```python
"""Unit tests for _verify_login_via_logout — the logout-link login check."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.login_flow import _verify_login_via_logout, MYACCOUNT_URL, LOGOUT_LINK_SELECTOR


def _make_page(*, post_goto_url: str, wait_for_selector_outcome: str,
               avatar_count: int = 0):
    """Build a mock Page that:
      - Records the navigation URL via goto().
      - Reports `post_goto_url` from .url after goto.
      - wait_for_selector_outcome: 'found' = returns immediately,
        'timeout' = raises TimeoutError-like Exception.
      - locator(...).first.count() returns `avatar_count` for the avatar fallback.
    """
    page = MagicMock()
    page.url = post_goto_url
    page.goto = AsyncMock(return_value=None)

    async def _wait(selector, state=None, timeout=None):
        if wait_for_selector_outcome == 'found':
            return None
        raise Exception("Timeout waiting for selector")

    page.wait_for_selector = AsyncMock(side_effect=_wait)

    locator_mock = MagicMock()
    first_mock = MagicMock()
    first_mock.count = AsyncMock(return_value=avatar_count)
    locator_mock.first = first_mock
    page.locator = MagicMock(return_value=locator_mock)
    return page


@pytest.mark.asyncio
async def test_returns_true_when_logout_link_found():
    page = _make_page(post_goto_url='https://myaccount.google.com/',
                      wait_for_selector_outcome='found')
    result = await _verify_login_via_logout(page, worker_id=1, timeout_s=1)
    assert result is True
    page.goto.assert_awaited_once_with(MYACCOUNT_URL, wait_until='domcontentloaded', timeout=15000)
    page.wait_for_selector.assert_awaited_once()
    args, kwargs = page.wait_for_selector.call_args
    assert args[0] == LOGOUT_LINK_SELECTOR


@pytest.mark.asyncio
async def test_returns_true_via_avatar_fallback_when_logout_link_missing():
    page = _make_page(post_goto_url='https://myaccount.google.com/',
                      wait_for_selector_outcome='timeout',
                      avatar_count=1)
    result = await _verify_login_via_logout(page, worker_id=1, timeout_s=1)
    assert result is True


@pytest.mark.asyncio
async def test_returns_false_when_redirected_to_signin():
    page = _make_page(post_goto_url='https://accounts.google.com/v3/signin/identifier',
                      wait_for_selector_outcome='timeout')
    result = await _verify_login_via_logout(page, worker_id=1, timeout_s=1)
    assert result is False


@pytest.mark.asyncio
async def test_returns_false_when_no_logged_in_signal():
    page = _make_page(post_goto_url='https://myaccount.google.com/',
                      wait_for_selector_outcome='timeout',
                      avatar_count=0)
    result = await _verify_login_via_logout(page, worker_id=1, timeout_s=1)
    assert result is False


@pytest.mark.asyncio
async def test_returns_security_redirect_string():
    """Account-rejected URL should return the security-redirect reason verbatim."""
    page = _make_page(post_goto_url='https://accounts.google.com/v3/signin/rejected/xyz',
                      wait_for_selector_outcome='timeout')
    result = await _verify_login_via_logout(page, worker_id=1, timeout_s=1)
    assert isinstance(result, str)
    assert 'ACCOUNT_LOCKED' in result


@pytest.mark.asyncio
async def test_returns_false_on_goto_exception():
    page = MagicMock()
    page.url = 'about:blank'
    page.goto = AsyncMock(side_effect=Exception("Net::ERR_TIMED_OUT"))
    result = await _verify_login_via_logout(page, worker_id=1, timeout_s=1)
    assert result is False
```

Note: requires `pytest-asyncio`. If not already installed, the project likely has it (check `pytest` runs work). If not, add `pytest-asyncio` via `pip install pytest-asyncio` and `pytest.ini` already has `asyncio_mode = auto` or similar — verify by running.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```
pytest tests/test_verify_login_via_logout.py -v
```

Expected: All 6 tests fail with `ImportError: cannot import name '_verify_login_via_logout'`.

- [ ] **Step 3: Implement the helper**

In `src/login_flow.py`, add this function **immediately after** `_wait_for_inbox_load` (after line 309, before `_check_password_changed_error`):

```python
async def _verify_login_via_logout(page, worker_id, timeout_s: int = 12):
    """Navigate to myaccount.google.com and confirm the user is authenticated.

    Looks for the global Sign-out anchor (href matches accounts.google.com/Logout)
    because that link appears on every Google product page once the user is
    signed in, including accounts whose Gmail is disabled. Falls back to
    [data-email] / avatar selectors if Google's menu has not yet hydrated.

    Returns:
        True  — logout link or account-avatar found = logged in.
        False — kicked to signin, or no logged-in signal within timeout.
        str   — security/help redirect reason (caller treats as terminal error).
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
        await page.wait_for_selector(
            LOGOUT_LINK_SELECTOR,
            state='attached',
            timeout=timeout_s * 1000,
        )
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

- [ ] **Step 4: Run tests to verify they pass**

Run:
```
pytest tests/test_verify_login_via_logout.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/login_flow.py tests/test_verify_login_via_logout.py
git commit -m "feat(login): add _verify_login_via_logout helper (myaccount + logout link)"
```

---

## Task 4: Update `screen_detector._is_logged_in` to lead with logout link

**Files:**
- Modify: `src/screen_detector.py:450-464`

- [ ] **Step 1: Replace the `_is_logged_in` method**

Find the existing method in `src/screen_detector.py` (around lines 450–464):

```python
async def _is_logged_in(self) -> bool:
    """Check if user is logged into Google account"""
    url = self.page.url
    # URL-based check first (fastest)
    if "mail.google.com/mail" in url:
        return True
    if "myaccount.google.com" in url and "signin" not in url:
        return True
    # Element check
    return await self._selector_visible_any([
        'a[aria-label*="Google Account"]',
        'img[alt*="profile picture" i]',
        '[data-email]',
        'a[href*="myaccount.google.com"]',
    ])
```

Replace it with:

```python
async def _is_logged_in(self) -> bool:
    """Check if user is logged into Google account.

    Leads with the global Sign-out anchor (href-based, survives Google's
    class hashing). Falls back to avatar / data-email selectors for pages
    where the account menu has not yet hydrated. URL-based hints removed
    because intermediate redirect pages produced false positives.
    """
    return await self._selector_visible_any([
        'a[href*="accounts.google.com/Logout"]',
        '[data-email]',
        'a[aria-label*="Google Account"]',
        'img[alt*="profile picture" i]',
        'a[href*="myaccount.google.com"]',
    ])
```

- [ ] **Step 2: Sanity-check the import**

Run:
```
python -c "from src.screen_detector import ScreenDetector; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```
git add src/screen_detector.py
git commit -m "fix(login): lead _is_logged_in with logout-link selector (drop URL hints)"
```

---

## Task 5: Wrap credential phase in `LoginSessionSlot`

**Files:**
- Modify: `src/login_flow.py` (`execute_login_flow`, lines ~501 through end of STEP 3 password submit at ~799)

This task brackets the existing STEP 2 (email) through end of STEP 3 (password submit + post-password wait) inside one `with LoginSessionSlot.acquire(...)` block. The slot is acquired BEFORE the email field is even looked up (so the "find email field" work is also serialized — short, but counts toward the holding time).

The slot is released BEFORE the post-password screen handling (STEP 4 polling loop). Two-factor entry happens inside STEP 4, so we need the slot to extend across STEP 4 until either LOGGED_IN is detected or a terminal failure raises. Strategy: instead of nesting STEP 4 inside the same `with` block (which would tangle the existing iteration loop), we use `slot_cm.__enter__()` manually at the start of STEP 2 and `slot_cm.__exit__()` at every exit point of STEP 4. To keep the code readable, we wrap that pattern in a tiny local helper.

- [ ] **Step 1: Insert slot acquisition before STEP 2**

In `src/login_flow.py`, find the comment line introducing STEP 2 (around line 500):

```python
        # ============================================================
        # STEP 2: Enter email (MANDATORY) — single-shot, human-typed
        # ============================================================
```

Immediately ABOVE that comment block (still inside the outer `try:` of `execute_login_flow`), insert:

```python
        # ============================================================
        # ACQUIRE LoginSessionSlot — serialize credential entry across workers
        # ============================================================
        # Held from here through email -> password -> 2FA -> LOGGED_IN.
        # Released by every exit branch in STEP 4 (success or raise).
        # Watchdog inside the slot force-releases after MAX_HOLD_SECONDS
        # so a single stuck account does not block the batch.
        _login_slot_cm = LoginSessionSlot.acquire(worker_id)
        _login_slot_cm.__enter__()
        _slot_released = {"done": False}

        def _release_slot():
            if not _slot_released["done"]:
                _slot_released["done"] = True
                try:
                    _login_slot_cm.__exit__(None, None, None)
                except Exception:
                    pass

```

- [ ] **Step 2: Release slot on success paths in STEP 4**

For each `return {'success': True, ...}` inside the post-password code (STEP 3 quick-inbox check, STEP 4 polling loop, FINAL CHECK block), insert a call to `_release_slot()` on the line immediately above the return. There are 9 such success returns in the current file:

Lines to modify (immediately above each line, add `_release_slot()`):
- Line 829 (`return {'success': True, 'forced_new_password': forced_new_password}` in STEP 3 quick inbox)
- Line 919 (`return {'success': True, ...}` in recovery options branch, Step 2 mode)
- Line 936 (`return {'success': True, ...}` in inbox URL success in poll loop)
- Line 952 (`return {'success': True, ...}` in LOGGED_IN + inbox success)
- Line 961 (`return {'success': True, ...}` in LOGGED_IN, Step 2 mode)
- Line 967 (`return {'success': True, ...}` in SUCCESS_SCREEN Step 2)
- Line 984 (`return {'success': True, ...}` in SUCCESS_SCREEN inbox redirect)
- Line 1025 (`return {'success': True, ...}` in brain success + inbox)
- Line 1028 (`return {'success': True, 'forced_new_password': fp}` in brain success Step 2)
- Line 1054 (`return {'success': True, ...}` in FINAL CHECK inbox)
- Line 1057 (`return {'success': True, ...}` in FINAL CHECK Step 1 final screen)
- Line 1061 (`return {'success': True, ...}` in FINAL CHECK Step 2 final screen)

Also there's an early return at line 820 from recovery success — `return recovery`. The `recovery` dict's `success` may be True; add `_release_slot()` above `return recovery` too. The same applies to the two other `return recovery` calls inside the polling loop (lines 915, 927, 978).

Pattern for each — example for line 829:

Before:
```python
            if inbox_result is True:
                _log(worker_id, "LOGIN SUCCESS: Inbox reached directly after password!")
                _log(worker_id, f"LOGIN SUCCESS: Final URL = {page.url}")
                return {'success': True, 'forced_new_password': forced_new_password}
```

After:
```python
            if inbox_result is True:
                _log(worker_id, "LOGIN SUCCESS: Inbox reached directly after password!")
                _log(worker_id, f"LOGIN SUCCESS: Final URL = {page.url}")
                _release_slot()
                return {'success': True, 'forced_new_password': forced_new_password}
```

Apply the same pattern to **every** `return` listed above (15 returns total: 12 explicit success dicts + 3 `return recovery` paths). The exact line numbers will drift as edits are applied — search for `return {'success': True` and `return recovery` to find them all.

- [ ] **Step 3: Release slot in the outer exception handler**

The outer `except Exception as e:` at line 1068 handles all raised failures. Add `_release_slot()` as the first line inside this handler so failures also release the slot.

Find:
```python
    except Exception as e:
        _log(worker_id, f"LOGIN ERROR: {e}")
        _log(worker_id, f"LOGIN ERROR: URL at error = {page.url}")
        return {'success': False, 'error': str(e)}
```

Replace with:
```python
    except Exception as e:
        # Slot is released here on any unhandled raise from the credential phase.
        try:
            _release_slot()
        except Exception:
            pass
        _log(worker_id, f"LOGIN ERROR: {e}")
        _log(worker_id, f"LOGIN ERROR: URL at error = {page.url}")
        return {'success': False, 'error': str(e)}
```

- [ ] **Step 4: Release slot at the LOGIN FAILED raise**

Just before line 1066's `raise Exception(f"LOGIN_TIMEOUT - ...")`, add `_release_slot()`:

Find:
```python
        _log(worker_id, f"LOGIN FAILED: Final screen = {final_screen.name}")
        raise Exception(f"LOGIN_TIMEOUT - Could not reach login success after {max_iterations} iterations. Final: screen={final_screen.name}, URL={final_url[:100]}")
```

Replace with:
```python
        _log(worker_id, f"LOGIN FAILED: Final screen = {final_screen.name}")
        _release_slot()
        raise Exception(f"LOGIN_TIMEOUT - Could not reach login success after {max_iterations} iterations. Final: screen={final_screen.name}, URL={final_url[:100]}")
```

(The outer exception handler will catch this raise and try `_release_slot()` again, but `_slot_released["done"]` guards against double release.)

- [ ] **Step 5: Run unit tests to verify nothing regressed**

Run:
```
pytest tests/test_login_session_slot.py tests/test_verify_login_via_logout.py tests/test_typing_slot.py -v
```

Expected: All passing. The `TypingSlot` tests still pass because we haven't removed it yet.

- [ ] **Step 6: Smoke-import the module**

Run:
```
python -c "from src.login_flow import execute_login_flow, LoginSessionSlot; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```
git add src/login_flow.py
git commit -m "feat(login): wrap credential phase in LoginSessionSlot — serial typing across workers"
```

---

## Task 6: Replace `_wait_for_inbox_load` calls with `_verify_login_via_logout`

**Files:**
- Modify: `src/login_flow.py` — 5 call sites: 824, 933, 949, 981, 1023, 1052

For each call site, swap the function and translate the result handling. The new helper has the same return contract: `True` / `False` / `str` (security redirect reason).

The semantic shift: the old code only ran inbox-wait on the `require_inbox=True` branch (or in the SUCCESS_SCREEN Step-2 branch that nonetheless required inbox). The new code calls `_verify_login_via_logout` regardless of `require_inbox` — when `require_inbox=False`, a logout-link check on myaccount is exactly the right Step 2 success signal too. So a handful of `if require_inbox and ...` branches collapse.

- [ ] **Step 1: STEP 3 quick inbox check (around line 822-831)**

Find:
```python
        if require_inbox and _is_inbox_url(current_url):
            _log(worker_id, "STEP[3/4] PASSWORD: Already at inbox URL! Waiting for full load...")
            inbox_result = await _wait_for_inbox_load(page, worker_id)
            _log(worker_id, f"STEP[3/4] PASSWORD: Inbox load result = {inbox_result}")
            if inbox_result is True:
                _log(worker_id, "LOGIN SUCCESS: Inbox reached directly after password!")
                _log(worker_id, f"LOGIN SUCCESS: Final URL = {page.url}")
                _release_slot()
                return {'success': True, 'forced_new_password': forced_new_password}
            elif isinstance(inbox_result, str):
                raise Exception(inbox_result)
```

Replace with:
```python
        # Quick verify: if myaccount logout link is reachable, login is done.
        verify_result = await _verify_login_via_logout(page, worker_id)
        if verify_result is True:
            _log(worker_id, "LOGIN SUCCESS: Logout link verified directly after password!")
            _release_slot()
            return _build_success(forced_new_password, require_inbox, page, worker_id)
        elif isinstance(verify_result, str):
            raise Exception(verify_result)
```

The new `_build_success` helper is introduced in Task 8 (it adds `inbox_accessible` when `require_inbox=True`). For now, leave `_build_success` undefined — Task 8 will create it. Mark this step as relying on Task 8.

For the interim (so this commit compiles), replace `_build_success(...)` with a literal:
```python
            return {'success': True, 'forced_new_password': forced_new_password}
```

and add a `# TODO(Task 8): replace with _build_success for inbox_accessible` comment.

- [ ] **Step 2: STEP 4 inbox URL success branch (around line 930-939)**

Find:
```python
            # Step 1: inbox URL = success
            if require_inbox and _is_inbox_url(current_url):
                _log(worker_id, f"  INBOX URL detected! Waiting for full load...")
                loaded = await _wait_for_inbox_load(page, worker_id)
                if loaded is True:
                    _log(worker_id, "LOGIN SUCCESS: Inbox URL confirmed and loaded!")
                    _release_slot()
                    return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}
                elif isinstance(loaded, str):
                    raise Exception(loaded)
                _log(worker_id, "  Inbox URL but load failed, continuing...")
```

Delete this entire block (5 lines). It is replaced by the LOGGED_IN screen branch handling that follows (Task 6 Step 3), which now runs verify-via-logout for both `require_inbox` modes.

- [ ] **Step 3: LOGGED_IN screen branch (around line 945-961)**

Find:
```python
            # ── Special handling for SUCCESS screens (login_flow-specific inbox logic) ──
            if screen == LoginScreen.LOGGED_IN:
                _log(worker_id, f"  LOGGED_IN detected. require_inbox={require_inbox}")
                if require_inbox:
                    _log(worker_id, "  Waiting for inbox to fully load...")
                    inbox_result = await _wait_for_inbox_load(page, worker_id)
                    if inbox_result is True:
                        _log(worker_id, "LOGIN SUCCESS: LOGGED_IN + inbox confirmed!")
                        _release_slot()
                        return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}
                    elif isinstance(inbox_result, str):
                        raise Exception(inbox_result)
                    else:
                        raise Exception(
                            f"LOGIN_TIMEOUT - LOGGED_IN but inbox never loaded. "
                            f"Final URL = {page.url[:100]}"
                        )
                _log(worker_id, "LOGIN SUCCESS: LOGGED_IN screen confirmed!")
                _release_slot()
                return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}
```

Replace with:
```python
            # ── LOGGED_IN screen detected — verify via myaccount logout link ──
            if screen == LoginScreen.LOGGED_IN:
                _log(worker_id, "  LOGGED_IN detected — verifying via logout link...")
                verify_result = await _verify_login_via_logout(page, worker_id)
                if verify_result is True:
                    _log(worker_id, "LOGIN SUCCESS: LOGGED_IN + logout link verified!")
                    _release_slot()
                    return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}
                elif isinstance(verify_result, str):
                    raise Exception(verify_result)
                _log(worker_id, "  LOGGED_IN screen detected but logout-link verify failed, continuing...")
```

- [ ] **Step 4: SUCCESS_SCREEN branch (around line 963-988)**

Find:
```python
            if screen == LoginScreen.SUCCESS_SCREEN:
                _log(worker_id, f"  SUCCESS_SCREEN detected. require_inbox={require_inbox}")
                if not require_inbox:
                    _log(worker_id, "LOGIN SUCCESS: SUCCESS_SCREEN (Step 2)")
                    _release_slot()
                    return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}
                # Step 1: wait for redirect to inbox
                _log(worker_id, "  Waiting 3s for inbox redirect...")
                await asyncio.sleep(3)
                redirect_url = page.url
                sec_reason = _is_google_security_redirect(redirect_url)
                if sec_reason:
                    if 'ACCOUNT_RECOVERY_REDIRECT' in sec_reason:
                        recovery = await _try_recover_from_support_redirect(
                            page, worker_id, require_inbox, brain.forced_new_password or forced_new_password)
                        if recovery:
                            _release_slot()
                            return recovery
                    raise Exception(sec_reason)
                if _is_inbox_url(redirect_url):
                    inbox_result = await _wait_for_inbox_load(page, worker_id)
                    if inbox_result is True:
                        _log(worker_id, "LOGIN SUCCESS: Redirected to inbox after success screen!")
                        _release_slot()
                        return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}
                    elif isinstance(inbox_result, str):
                        raise Exception(inbox_result)
                _log(worker_id, "  No inbox redirect yet, continuing loop...")
                continue
```

Replace with:
```python
            if screen == LoginScreen.SUCCESS_SCREEN:
                _log(worker_id, "  SUCCESS_SCREEN detected — verifying via logout link...")
                verify_result = await _verify_login_via_logout(page, worker_id)
                if verify_result is True:
                    _log(worker_id, "LOGIN SUCCESS: SUCCESS_SCREEN + logout link verified!")
                    _release_slot()
                    return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}
                elif isinstance(verify_result, str):
                    if 'ACCOUNT_RECOVERY_REDIRECT' in verify_result:
                        recovery = await _try_recover_from_support_redirect(
                            page, worker_id, require_inbox, brain.forced_new_password or forced_new_password)
                        if recovery:
                            _release_slot()
                            return recovery
                    raise Exception(verify_result)
                _log(worker_id, "  SUCCESS_SCREEN but no logout link yet, continuing loop...")
                continue
```

- [ ] **Step 5: Brain success branch (around line 1015-1028)**

Find:
```python
            if result.action == "success":
                fp = (result.data or {}).get('forced_new_password', '') or forced_new_password
                _log(worker_id, f"LOGIN SUCCESS via brain: {screen.name}")
                if require_inbox:
                    # Brain says success but we need inbox for Step 1
                    _log(worker_id, "  Waiting for inbox...")
                    await asyncio.sleep(3)
                    if _is_inbox_url(page.url):
                        inbox_result = await _wait_for_inbox_load(page, worker_id)
                        if inbox_result is True:
                            _release_slot()
                            return {'success': True, 'forced_new_password': fp}
                    # Continue loop — inbox not yet reached
                    continue
                _release_slot()
                return {'success': True, 'forced_new_password': fp}
```

Replace with:
```python
            if result.action == "success":
                fp = (result.data or {}).get('forced_new_password', '') or forced_new_password
                _log(worker_id, f"LOGIN SUCCESS via brain: {screen.name} — verifying via logout link...")
                verify_result = await _verify_login_via_logout(page, worker_id)
                if verify_result is True:
                    _release_slot()
                    return {'success': True, 'forced_new_password': fp}
                elif isinstance(verify_result, str):
                    raise Exception(verify_result)
                # Verify failed — continue loop, brain may have more screens to handle
                _log(worker_id, "  Brain said success but logout link not yet visible, continuing...")
                continue
```

- [ ] **Step 6: FINAL CHECK block (around line 1049-1061)**

Find:
```python
        if require_inbox:
            if _is_inbox_url(final_url):
                _log(worker_id, "FINAL CHECK: Inbox URL found! Waiting for load...")
                await _wait_for_inbox_load(page, worker_id)
                _log(worker_id, "LOGIN SUCCESS: Final inbox check passed!")
                _release_slot()
                return {'success': True, 'forced_new_password': fp}
            if final_screen in [LoginScreen.LOGGED_IN, LoginScreen.SUCCESS_SCREEN]:
                _log(worker_id, f"LOGIN SUCCESS: Final screen = {final_screen.name}")
                _release_slot()
                return {'success': True, 'forced_new_password': fp}
        else:
            if final_screen in [LoginScreen.LOGGED_IN, LoginScreen.SUCCESS_SCREEN]:
                _log(worker_id, f"LOGIN SUCCESS: Final screen = {final_screen.name} (Step 2)")
                _release_slot()
                return {'success': True, 'forced_new_password': fp}
```

Replace with:
```python
        # FINAL CHECK: one last logout-link verification before declaring failure.
        final_verify = await _verify_login_via_logout(page, worker_id)
        if final_verify is True:
            _log(worker_id, "LOGIN SUCCESS: Final logout-link verify passed!")
            _release_slot()
            return {'success': True, 'forced_new_password': fp}
        if isinstance(final_verify, str):
            _release_slot()
            raise Exception(final_verify)
        if final_screen in [LoginScreen.LOGGED_IN, LoginScreen.SUCCESS_SCREEN]:
            _log(worker_id, f"LOGIN SUCCESS: Final screen = {final_screen.name}")
            _release_slot()
            return {'success': True, 'forced_new_password': fp}
```

- [ ] **Step 7: Run unit tests + import smoke check**

Run:
```
pytest tests/test_verify_login_via_logout.py tests/test_login_session_slot.py -v
python -c "from src.login_flow import execute_login_flow; print('ok')"
```

Expected: tests pass, import succeeds.

- [ ] **Step 8: Commit**

```
git add src/login_flow.py
git commit -m "feat(login): replace inbox-URL waits with myaccount logout-link verification"
```

---

## Task 7: Update `_try_recover_from_support_redirect` to use logout verify

**Files:**
- Modify: `src/login_flow.py:199-236`

- [ ] **Step 1: Replace the function body**

Find the existing `_try_recover_from_support_redirect` function (lines 199–236):

```python
async def _try_recover_from_support_redirect(page, worker_id, require_inbox, forced_new_password):
    """
    When Google redirects to support.google.com (ACCOUNT_RECOVERY_REDIRECT),
    try navigating to myaccount/inbox to check if the session is still valid.
    Returns success dict or None if recovery failed.
    """
    target = 'https://mail.google.com/mail/' if require_inbox else 'https://myaccount.google.com/'
    _log(worker_id, f"  RECOVERY: Support-page redirect detected — navigating to {target}...")
    try:
        await page.goto(target, wait_until='domcontentloaded', timeout=PAGE_LOAD_TIMEOUT)
        await asyncio.sleep(3)
        url = page.url
        _log(worker_id, f"  RECOVERY: After navigation URL = {url[:100]}")

        # Step 1/3: need inbox
        if require_inbox and _is_inbox_url(url):
            _log(worker_id, "  RECOVERY SUCCESS: Inbox reached!")
            return {'success': True, 'forced_new_password': forced_new_password}

        # Step 2: myaccount page is enough
        if not require_inbox and ('myaccount.google.com' in url
                                  or 'accounts.google.com/b/' in url):
            _log(worker_id, "  RECOVERY SUCCESS: MyAccount page reached!")
            return {'success': True, 'forced_new_password': forced_new_password}

        # Kicked back to login → session dead
        if 'accounts.google.com/v3/signin' in url or 'accounts.google.com/signin' in url:
            _log(worker_id, "  RECOVERY FAILED: Redirected back to login — session expired")
            return None

        # Step 2: any Google page that isn't login is acceptable
        if not require_inbox and 'google.com' in url and 'signin' not in url:
            _log(worker_id, "  RECOVERY SUCCESS: On Google page (not login) — session likely valid")
            return {'success': True, 'forced_new_password': forced_new_password}

    except Exception as e:
        _log(worker_id, f"  RECOVERY FAILED: Navigation error: {str(e)[:60]}")
    return None
```

Replace with:

```python
async def _try_recover_from_support_redirect(page, worker_id, require_inbox, forced_new_password):
    """
    When Google redirects to support.google.com (ACCOUNT_RECOVERY_REDIRECT),
    navigate to myaccount and verify via the logout link to check if the
    session is still valid.

    Returns success dict or None if recovery failed.
    """
    _log(worker_id, "  RECOVERY: Support-page redirect detected — verifying session via logout link...")
    verify_result = await _verify_login_via_logout(page, worker_id)
    if verify_result is True:
        _log(worker_id, "  RECOVERY SUCCESS: Logout link verified — session is valid")
        return {'success': True, 'forced_new_password': forced_new_password}
    if isinstance(verify_result, str):
        _log(worker_id, f"  RECOVERY FAILED: Security redirect during verify -> {verify_result}")
        return None
    _log(worker_id, "  RECOVERY FAILED: No logout-link signal — session expired")
    return None
```

- [ ] **Step 2: Sanity-check the import**

Run:
```
python -c "from src.login_flow import _try_recover_from_support_redirect; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```
git add src/login_flow.py
git commit -m "fix(login): recovery from support-redirect uses logout-link verify (not inbox URL)"
```

---

## Task 8: Add `_build_success` helper with optional `inbox_accessible` field

**Files:**
- Modify: `src/login_flow.py` — add helper near the other top-level helpers (after `_verify_login_via_logout`)

- [ ] **Step 1: Add the helper**

In `src/login_flow.py`, immediately after `_verify_login_via_logout` (added in Task 3), add:

```python
async def _build_success(forced_new_password: str, require_inbox: bool, page, worker_id) -> dict:
    """Build the success result dict.

    When require_inbox=True, additionally probes mail.google.com to record
    whether Gmail is actually reachable for this account. Sets
    inbox_accessible=False (but success=True) if Gmail is disabled or
    redirects elsewhere — callers that strictly need Gmail can branch on it.
    """
    result = {'success': True, 'forced_new_password': forced_new_password}
    if require_inbox:
        try:
            await page.goto('https://mail.google.com/mail/', wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)
            url = page.url
            result['inbox_accessible'] = 'mail.google.com/mail' in url
            _log(worker_id, f"  INBOX PROBE: inbox_accessible={result['inbox_accessible']} (URL={url[:80]})")
        except Exception as e:
            _log(worker_id, f"  INBOX PROBE: failed: {str(e)[:60]} — inbox_accessible=False")
            result['inbox_accessible'] = False
    return result
```

- [ ] **Step 2: Replace the TODO from Task 6 Step 1**

Search for `# TODO(Task 8): replace with _build_success` in `src/login_flow.py`. There should be 1 occurrence (the line in STEP 3 quick verify). Replace the lines:
```python
            # TODO(Task 8): replace with _build_success for inbox_accessible
            return {'success': True, 'forced_new_password': forced_new_password}
```

with:
```python
            return await _build_success(forced_new_password, require_inbox, page, worker_id)
```

Also update the **other** success returns to use `_build_success` so the field is consistent across all success paths. Search for `return {'success': True, 'forced_new_password': ` — there should be 11+ occurrences after prior tasks. For each one, swap to `return await _build_success(<the_forced_new_password_expr>, require_inbox, page, worker_id)`.

Examples:

Before:
```python
                _release_slot()
                return {'success': True, 'forced_new_password': brain.forced_new_password or forced_new_password}
```

After:
```python
                _release_slot()
                return await _build_success(brain.forced_new_password or forced_new_password, require_inbox, page, worker_id)
```

Apply to every occurrence (including the FINAL CHECK and brain-success returns). The result dict for the recovery branches (`return recovery`) is left as-is — `_try_recover_from_support_redirect` builds its own dict that does not need `inbox_accessible` (it never reached the post-login state where Gmail might be probed).

- [ ] **Step 3: Sanity-check the import**

Run:
```
python -c "from src.login_flow import execute_login_flow, _build_success; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Run all unit tests**

Run:
```
pytest tests/test_login_session_slot.py tests/test_verify_login_via_logout.py -v
```

Expected: All passing.

- [ ] **Step 5: Commit**

```
git add src/login_flow.py
git commit -m "feat(login): success dict now reports inbox_accessible when require_inbox=True"
```

---

## Task 9: Remove `TypingSlot` class and its two `with` wrappers

**Files:**
- Modify: `src/login_flow.py` (delete class definition + 2 `with` blocks)
- Delete: `tests/test_typing_slot.py`

- [ ] **Step 1: Remove the `TypingSlot` `with` wrapper around email fill**

Find the email-fill block (around lines 575–589):

```python
        else:
            # Focus INSIDE the TypingSlot. The slot may block for up to
            # GAP_SECONDS (2s) waiting for the previous worker to finish;
            # if we focused before acquire, focus could drift during that
            # gap, sending the keystrokes to the wrong element (or to
            # nothing) and producing the "Could not enter password" cascade
            # downstream when the form never actually submitted.
            with TypingSlot.acquire(worker_id, "email"):
                try: await elem.click()
                except Exception: pass
                try: await elem.focus()
                except Exception: pass
                try: await elem.fill('')
                except Exception: pass
                await _human_type(page, email)
            _log(worker_id, f"STEP[2/4] EMAIL: Typed email via '{sel}' (humanized)")
```

Replace with (un-indent contents one level, drop `with TypingSlot.acquire(...)` and the focus-drift comment):

```python
        else:
            try: await elem.click()
            except Exception: pass
            try: await elem.focus()
            except Exception: pass
            try: await elem.fill('')
            except Exception: pass
            await _human_type(page, email)
            _log(worker_id, f"STEP[2/4] EMAIL: Typed email via '{sel}' (humanized)")
```

- [ ] **Step 2: Remove the `TypingSlot` `with` wrapper around password fill**

Find the password-fill block (around lines 770–783):

```python
        if await _value_matches(elem, password):
            _log(worker_id, f"STEP[3/4] PASSWORD: Already filled via '{sel}' — skipping retype")
        else:
            # Focus INSIDE the TypingSlot to avoid focus drift during the
            # slot gap (the slot can block for GAP_SECONDS waiting on
            # another worker; if we focused before acquire, keystrokes
            # could land on the wrong element).
            with TypingSlot.acquire(worker_id, "password"):
                try: await elem.click()
                except Exception: pass
                try: await elem.focus()
                except Exception: pass
                try: await elem.fill('')
                except Exception: pass
                await _human_type(page, password)
            _log(worker_id, f"STEP[3/4] PASSWORD: Typed password via '{sel}' (humanized)")
```

Replace with:

```python
        if await _value_matches(elem, password):
            _log(worker_id, f"STEP[3/4] PASSWORD: Already filled via '{sel}' — skipping retype")
        else:
            try: await elem.click()
            except Exception: pass
            try: await elem.focus()
            except Exception: pass
            try: await elem.fill('')
            except Exception: pass
            await _human_type(page, password)
            _log(worker_id, f"STEP[3/4] PASSWORD: Typed password via '{sel}' (humanized)")
```

- [ ] **Step 3: Delete the `TypingSlot` class definition**

Find the `TypingSlot` class definition (lines 33–70):

```python
class TypingSlot:
    """Global gate that serializes field-typing across all batch-login workers.
    ...
    """
    _lock = threading.Lock()
    _last_release = 0.0
    GAP_SECONDS = 2.0

    @classmethod
    @contextmanager
    def acquire(cls, worker_id="?", what="field"):
        ...
```

Delete the entire class (`class TypingSlot:` through the closing of the `acquire` method, roughly 38 lines).

- [ ] **Step 4: Delete the `TypingSlot` test file**

Run:
```
git rm tests/test_typing_slot.py
```

- [ ] **Step 5: Verify no stragglers reference `TypingSlot`**

Run:
```
git grep TypingSlot
```

Expected: no matches (or only matches inside `docs/` which are historical and can stay).

- [ ] **Step 6: Smoke-import**

Run:
```
python -c "from src.login_flow import execute_login_flow; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```
git add src/login_flow.py
git commit -m "refactor(login): remove TypingSlot — LoginSessionSlot subsumes its job"
```

---

## Task 10: Delete `_wait_for_inbox_load`, `_is_inbox_url`, `INBOX_URL`

**Files:**
- Modify: `src/login_flow.py`

- [ ] **Step 1: Verify no remaining callers**

Run:
```
git grep _wait_for_inbox_load
git grep _is_inbox_url
git grep INBOX_URL
```

Expected: only matches in `src/login_flow.py` (the definitions themselves). If any other file references them, STOP and update those callers first.

- [ ] **Step 2: Delete `INBOX_URL` constant**

In `src/login_flow.py`, find:
```python
INBOX_URL = "mail.google.com/mail"
```
Delete this line.

- [ ] **Step 3: Delete `_is_inbox_url` function**

Find:
```python
def _is_inbox_url(url: str) -> bool:
    return INBOX_URL in url
```
Delete it (2 lines).

- [ ] **Step 4: Delete `_wait_for_inbox_load` function**

Find the function starting at:
```python
async def _wait_for_inbox_load(page, worker_id: int, timeout: int = 15):
    """Wait for Gmail inbox to fully load before returning success."""
    ...
```

Delete the entire function body (roughly 70 lines, through `return False`).

- [ ] **Step 5: Smoke-import + tests**

Run:
```
python -c "from src.login_flow import execute_login_flow; print('ok')"
pytest tests/test_login_session_slot.py tests/test_verify_login_via_logout.py -v
```

Expected: import succeeds, all tests pass.

- [ ] **Step 6: Commit**

```
git add src/login_flow.py
git commit -m "chore(login): remove dead INBOX_URL / _is_inbox_url / _wait_for_inbox_load"
```

---

## Task 11: Update `execute_login_flow` docstring + `require_inbox` semantics

**Files:**
- Modify: `src/login_flow.py:393-412` (the docstring of `execute_login_flow`)

- [ ] **Step 1: Update the docstring**

Find the docstring of `execute_login_flow`:

```python
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
        require_inbox: True (Step 1) = inbox URL is success.
                       False (Step 2) = LOGGED_IN/SUCCESS_SCREEN is success.

    Returns:
        dict: {'success': True/False, 'error': 'msg', 'forced_new_password': '...'}
    """
```

Replace with:

```python
    """
    Executes the common Google login flow.

    Success is detected by the global Sign-out anchor on myaccount.google.com,
    not by reaching mail.google.com/mail. This works for accounts whose
    Gmail product is disabled.

    The credential entry phase (email -> password -> 2FA) is wrapped in a
    process-global LoginSessionSlot so only one worker is typing into a
    Google login form at a time across the whole batch.

    Args:
        page: Playwright page object
        account: Dict with Email, Password, TOTP Secret, Backup Code
        worker_id: Worker ID for logging
        login_url: Login URL
        detector: ScreenDetector (optional)
        totp_gen: TOTPGenerator (optional)
        require_inbox: When True, additionally probes mail.google.com after
                       login succeeds and records inbox_accessible in the
                       result. Login success itself is still based on the
                       logout-link check; inbox_accessible is informational
                       for callers that strictly need Gmail.

    Returns:
        dict: On success: {'success': True, 'forced_new_password': '...',
                           'inbox_accessible': bool (only when require_inbox=True)}
              On failure: {'success': False, 'error': 'msg'}
    """
```

- [ ] **Step 2: Update the STEP[1/4] log line**

Find:
```python
    _log(worker_id, f"  Mode: {'Step 1 (require_inbox=True)' if require_inbox else 'Step 2 (require_inbox=False)'}")
```

Replace with:
```python
    _log(worker_id, f"  Mode: {'Step 1 (will probe inbox)' if require_inbox else 'Step 2 (logout-link only)'}")
```

- [ ] **Step 3: Smoke-import + tests**

Run:
```
python -c "from src.login_flow import execute_login_flow; print('ok')"
pytest tests/test_login_session_slot.py tests/test_verify_login_via_logout.py -v
```

Expected: import succeeds, all tests pass.

- [ ] **Step 4: Commit**

```
git add src/login_flow.py
git commit -m "docs(login): update execute_login_flow docstring + require_inbox semantics"
```

---

## Task 12: Sync to main directory + final manual verification

Per the project's memory rule "Always sync fixes into main directory", every file changed in the worktree must also be copied into `E:\NST Anty Android\` so the user can test from the main directory.

**Files to sync (after all earlier tasks):**
- `src/login_flow.py`
- `src/screen_detector.py`
- `tests/test_login_session_slot.py` (new)
- `tests/test_verify_login_via_logout.py` (new)
- `tests/test_typing_slot.py` (DELETED — remove from main directory too)

- [ ] **Step 1: Identify worktree path**

Run from the worktree root:
```
git rev-parse --show-toplevel
```

The path is the worktree root. The main directory is `E:\NST Anty Android\`.

- [ ] **Step 2: Copy modified + new files into main directory**

From the worktree root:
```
copy src\login_flow.py "E:\NST Anty Android\src\login_flow.py"
copy src\screen_detector.py "E:\NST Anty Android\src\screen_detector.py"
copy tests\test_login_session_slot.py "E:\NST Anty Android\tests\test_login_session_slot.py"
copy tests\test_verify_login_via_logout.py "E:\NST Anty Android\tests\test_verify_login_via_logout.py"
```

(On PowerShell use `Copy-Item -Force`. Bash equivalent: `cp -f`.)

- [ ] **Step 3: Delete the obsolete test from main directory**

```
del "E:\NST Anty Android\tests\test_typing_slot.py"
```

(PowerShell: `Remove-Item -Force`. Bash: `rm -f`.)

- [ ] **Step 4: Smoke-import from main directory**

Run from `E:\NST Anty Android\`:
```
python -c "from src.login_flow import execute_login_flow, LoginSessionSlot, _verify_login_via_logout; print('ok')"
pytest tests/test_login_session_slot.py tests/test_verify_login_via_logout.py -v
```

Expected: `ok` and all tests pass from the main directory.

- [ ] **Step 5: Manual verification — batch login with 5 workers (8+ accounts)**

Per the spec's testing section:

1. Open the Electron app from main directory.
2. Start a batch login with `num_workers=5` on 8 accounts.
3. Watch logs and confirm:
   - At least one `LOGIN_SLOT: waiting for slot...` followed by `LOGIN_SLOT: ACQUIRED after Xs wait` (X > 0) for workers 2..5.
   - `LOGIN_SLOT: released after holding Ys` lines, all `Y < 60` for healthy accounts.
   - No `TYPING_SLOT:` lines anywhere (class removed).
   - For each success: `VERIFY: Navigating to myaccount...` then `VERIFY: SUCCESS — logout link found`.
   - No `INBOX_WAIT:` lines anywhere (function deleted).
4. Final result: success count matches what manual sequential login would give.

- [ ] **Step 6: Manual verification — Gmail-disabled account**

1. Pick an account known to have Gmail product disabled (or simulate).
2. Run login solo. Expect: `VERIFY: SUCCESS — logout link found` AND `success=True` AND (if `require_inbox=True`) `inbox_accessible=False`.

- [ ] **Step 7: Manual verification — stuck worker**

1. Trigger a CAPTCHA on one account (use a flagged proxy).
2. Wait for the watchdog message: `LOGIN_SLOT: WATCHDOG force-released after 180s`. Confirm the next worker proceeds.

- [ ] **Step 8: Manual verification — concurrent typing check**

Run a batch login with `num_workers=3` on 6 accounts. Grep the log:
```
grep -E "STEP\[(2|3)/4\] (EMAIL|PASSWORD): Typed" debug.log.1
```

Confirm no two consecutive lines share a timestamp within 1 second across different workers. (Within the same worker, email → password may be close together; that is fine.)

- [ ] **Step 9: Final commit (worktree only, no code change)**

If any of the manual verification steps surfaced an issue, fix it in the worktree and resync via Step 2. Otherwise this task ends with the existing commits from prior tasks; no extra commit is needed here.

---

## Self-Review Summary

**Spec coverage:**
- LoginSessionSlot class (spec Part 1) → Task 1.
- LoginSessionSlot wraps credential phase → Tasks 5, plus integration with verify in Task 6.
- TypingSlot removal → Task 9.
- LOGOUT_LINK_SELECTOR + MYACCOUNT_URL constants → Task 2.
- `_verify_login_via_logout` helper → Task 3.
- `_is_logged_in` reordering → Task 4.
- Replace `_wait_for_inbox_load` calls → Task 6.
- `_try_recover_from_support_redirect` update → Task 7.
- `_build_success` + `inbox_accessible` field → Task 8.
- Delete dead INBOX_URL / `_is_inbox_url` / `_wait_for_inbox_load` → Task 10.
- Updated docstring + require_inbox semantics → Task 11.
- Sync to main directory → Task 12.
- Manual testing (spec's 5 manual tests) → Task 12 Steps 5–8.

All spec sections covered.

**Placeholder scan:** Task 6 Step 1 contains a temporary placeholder `# TODO(Task 8): replace with _build_success ...` which is explicitly resolved in Task 8 Step 2. This is intentional cross-task scaffolding, not a planning placeholder.

**Type consistency:**
- `LoginSessionSlot.acquire(worker_id)` — consistent across Task 1 (definition) and Task 5 (use).
- `_verify_login_via_logout(page, worker_id, timeout_s=12)` — consistent across Tasks 3 (definition), 6, 7, 8 (uses).
- `_build_success(forced_new_password, require_inbox, page, worker_id)` — consistent across Tasks 8 (definition) and 6 (use).
- `_release_slot()` — local closure defined in Task 5 Step 1, used in Task 5 Steps 2–4 and Task 6 Steps 1–6.
- Result dict shape: `{'success': bool, 'forced_new_password': str, 'inbox_accessible': bool?}` consistent.

All consistent.
