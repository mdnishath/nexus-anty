# Profile Row UI Polish + Batch-Login Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the Profile Manager row (status-as-dot, click-to-copy on email/pass/totp, spacing between Status and Group), and make batch login deterministic by serializing field-typing across workers with a 2-second gap and skipping re-typing when the field already holds the right value.

**Architecture:** Two independent surfaces. Frontend changes are confined to `electron-app/renderer/modules/profiles.js` (row template + event wiring) and `electron-app/renderer/styles.css` (dot styles, column gap, copyable hover). Backend change is one new `TypingSlot` thread-safe gate plus one `_value_matches` helper in `src/login_flow.py`, applied at every Google-login field fill (email initial, email reload-retype, password). No API, IPC, or schema changes.

**Tech Stack:** Vanilla JS + CSS in the Electron renderer; Python 3 + Playwright async API on the backend; `threading.Lock` for cross-worker coordination (each batch-login worker runs its own asyncio loop in its own thread, so a thread-level lock is the right primitive).

**Spec:** [docs/superpowers/specs/2026-05-23-profile-row-and-batch-login-reliability-design.md](docs/superpowers/specs/2026-05-23-profile-row-and-batch-login-reliability-design.md)

---

## Task 1: `TypingSlot` class + unit test

**Files:**
- Modify: `src/login_flow.py` (add class near top of module, after existing imports)
- Create: `tests/test_typing_slot.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_typing_slot.py`:

```python
"""Unit tests for TypingSlot — the global typing gate in src/login_flow.py."""
import threading
import time
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.login_flow import TypingSlot


def _reset_slot():
    """Make each test independent by clearing the class-level state."""
    TypingSlot._last_release = 0.0


def test_first_acquire_does_not_wait():
    _reset_slot()
    t0 = time.monotonic()
    with TypingSlot.acquire("worker-1", "email"):
        pass
    assert time.monotonic() - t0 < 0.5, "First acquire should be immediate"


def test_second_acquire_waits_two_seconds():
    _reset_slot()
    with TypingSlot.acquire("worker-1", "email"):
        pass
    t0 = time.monotonic()
    with TypingSlot.acquire("worker-2", "email"):
        elapsed = time.monotonic() - t0
    assert 1.8 <= elapsed <= 2.3, f"Second acquire should wait ~2s, waited {elapsed:.2f}s"


def test_serializes_concurrent_workers():
    """Three threads acquire concurrently — total time ≥ 4s (2 gaps)."""
    _reset_slot()
    enter_times = []
    lock = threading.Lock()

    def worker(wid):
        with TypingSlot.acquire(f"w{wid}", "email"):
            with lock:
                enter_times.append(time.monotonic())
            time.sleep(0.05)  # simulate brief typing

    t0 = time.monotonic()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = time.monotonic() - t0
    assert total >= 3.9, f"3 workers with 2s gap should take ≥4s, took {total:.2f}s"
    enter_times.sort()
    for i in range(1, len(enter_times)):
        gap = enter_times[i] - enter_times[i - 1]
        assert gap >= 1.9, f"Gap between worker {i} and {i-1} was {gap:.2f}s, expected ≥2s"


def test_gap_constant_is_two_seconds():
    assert TypingSlot.GAP_SECONDS == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_typing_slot.py -v
```

Expected: `ImportError` or `AttributeError: module 'src.login_flow' has no attribute 'TypingSlot'`.

- [ ] **Step 3: Add the `TypingSlot` class**

In `src/login_flow.py`, find the imports block at the top and add (or merge into existing imports) these lines if not already present:

```python
import threading
import time
from contextlib import contextmanager
```

Then immediately after the imports block (before the first function or constant definition), add:

```python
class TypingSlot:
    """Global gate that serializes field-typing across all batch-login workers.

    Each batch-login worker runs in its own thread with its own asyncio loop.
    Without this gate, multiple workers can hit Google's email/password input
    in the same instant — Google then occasionally drops keystrokes or returns
    "invalid email format" because the field was repainted mid-fill.

    Usage:
        with TypingSlot.acquire(worker_id, "email"):
            await elem.fill(email)

    Guarantees:
        - Only one worker may be inside the block at a time.
        - There is a minimum GAP_SECONDS gap between successive blocks across
          all workers, measured from the release of one to the acquire of
          the next.
    """
    _lock = threading.Lock()
    _last_release = 0.0
    GAP_SECONDS = 2.0

    @classmethod
    @contextmanager
    def acquire(cls, worker_id="?", what="field"):
        cls._lock.acquire()
        try:
            wait = cls.GAP_SECONDS - (time.monotonic() - cls._last_release)
            if wait > 0:
                try:
                    _log(worker_id, f"TYPING_SLOT: waiting {wait:.1f}s before typing {what}")
                except Exception:
                    pass
                time.sleep(wait)
            yield
        finally:
            cls._last_release = time.monotonic()
            cls._lock.release()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_typing_slot.py -v
```

Expected: All four tests pass. `test_serializes_concurrent_workers` will take ~4s — that's correct.

- [ ] **Step 5: Commit**

```bash
git add src/login_flow.py tests/test_typing_slot.py
git commit -m "feat(login): add TypingSlot global gate with 2s gap between field typings"
```

---

## Task 2: `_value_matches` helper + unit test

**Files:**
- Modify: `src/login_flow.py` (add helper near top, after `TypingSlot`)
- Create: `tests/test_value_matches.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_value_matches.py`:

```python
"""Unit tests for _value_matches helper."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.login_flow import _value_matches


def _run(coro):
    return asyncio.run(coro)


def _mock_elem(value):
    elem = MagicMock()
    elem.input_value = AsyncMock(return_value=value)
    return elem


def test_exact_match_returns_true():
    elem = _mock_elem("foo@example.com")
    assert _run(_value_matches(elem, "foo@example.com")) is True


def test_whitespace_difference_still_matches():
    elem = _mock_elem("  foo@example.com  ")
    assert _run(_value_matches(elem, "foo@example.com")) is True


def test_empty_field_does_not_match_non_empty_expected():
    elem = _mock_elem("")
    assert _run(_value_matches(elem, "foo@example.com")) is False


def test_different_value_returns_false():
    elem = _mock_elem("other@example.com")
    assert _run(_value_matches(elem, "foo@example.com")) is False


def test_input_value_exception_returns_false():
    elem = MagicMock()
    elem.input_value = AsyncMock(side_effect=RuntimeError("element detached"))
    assert _run(_value_matches(elem, "foo@example.com")) is False


def test_none_expected_matches_empty():
    elem = _mock_elem("")
    assert _run(_value_matches(elem, None)) is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_value_matches.py -v
```

Expected: `ImportError: cannot import name '_value_matches'`.

- [ ] **Step 3: Add the helper**

In `src/login_flow.py`, immediately after the `TypingSlot` class added in Task 1, add:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_value_matches.py -v
```

Expected: All six tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/login_flow.py tests/test_value_matches.py
git commit -m "feat(login): add _value_matches helper for pre-fill value check"
```

---

## Task 3: Apply `TypingSlot` + `_value_matches` to initial email fill

**Files:**
- Modify: `src/login_flow.py:431-446` (the initial email-fill `for sel in email_selectors:` loop)

- [ ] **Step 1: Read the current block**

```bash
sed -n '430,450p' src/login_flow.py
```

You should see the loop that ends with `await elem.fill(email)` at line 437.

- [ ] **Step 2: Wrap the fill with TypingSlot + pre-check**

Replace lines 431-443 (the inner `for sel in email_selectors:` loop body inside the `for email_attempt in range(1, 4):` loop) with:

```python
            for sel in email_selectors:
                try:
                    elem = page.locator(sel).first
                    count = await elem.count()
                    visible = await elem.is_visible() if count > 0 else False
                    if count > 0 and visible:
                        if await _value_matches(elem, email):
                            _log(worker_id, f"STEP[2/4] EMAIL: Already filled via '{sel}' — skipping retype")
                            email_filled = True
                            break
                        with TypingSlot.acquire(worker_id, "email"):
                            await elem.fill('')
                            await elem.fill(email)
                        _log(worker_id, f"STEP[2/4] EMAIL: Filled email via '{sel}' (attempt {email_attempt})")
                        email_filled = True
                        break
                except Exception as e:
                    _log(worker_id, f"STEP[2/4] EMAIL: Error with '{sel}': {str(e)[:60]}")
                    continue
```

The key changes:
1. `_value_matches` check before fill — if already filled, skip and break.
2. `with TypingSlot.acquire(worker_id, "email"):` wraps the two fill calls (clear then write) as one atomic typing event from the gate's perspective.

- [ ] **Step 3: Smoke-check the syntax**

```bash
python -c "import ast; ast.parse(open('src/login_flow.py').read())"
```

Expected: no output (success). If there's a `SyntaxError`, indentation is off — re-check.

- [ ] **Step 4: Run existing tests**

```bash
python -m pytest tests/test_typing_slot.py tests/test_value_matches.py -v
```

Expected: all tests still pass (we haven't changed those helpers' behavior).

- [ ] **Step 5: Commit**

```bash
git add src/login_flow.py
git commit -m "feat(login): gate initial email fill with TypingSlot + pre-check value"
```

---

## Task 4: Apply `TypingSlot` + `_value_matches` to reload-retype email loop

**Files:**
- Modify: `src/login_flow.py:561-580` (the inner `while … not _refilled:` loop that retypes email after a page reload)

- [ ] **Step 1: Read the current block**

```bash
sed -n '558,595p' src/login_flow.py
```

You should see a `while asyncio.get_event_loop().time() < _deadline and not _refilled:` loop that calls `_el.fill('')` then `page.keyboard.type(email, delay=25)`.

- [ ] **Step 2: Wrap the retype with TypingSlot + pre-check**

Replace the inner-loop body (the `for _sel in (...)` block, currently lines ~562-577) with:

```python
            while asyncio.get_event_loop().time() < _deadline and not _refilled:
                for _sel in ('input[type="email"]', 'input#identifierId',
                             'input[name="identifier"]', 'input[autocomplete="username"]'):
                    try:
                        _el = page.locator(_sel).first
                        if (await _el.count() > 0
                                and await _el.is_visible(timeout=400)
                                and await _el.is_enabled(timeout=400)):
                            if await _value_matches(_el, email):
                                _log(worker_id, f"STEP[2/4] EMAIL: Reload retry — '{_sel}' already has correct value, skipping retype")
                                _refilled = True
                                break
                            try: await _el.click(timeout=2000)
                            except Exception: pass
                            with TypingSlot.acquire(worker_id, "email (reload retry)"):
                                try: await _el.fill('')
                                except Exception: pass
                                await page.keyboard.type(email, delay=25)
                            _refilled = True
                            break
                    except Exception:
                        continue
                if not _refilled:
                    await asyncio.sleep(0.5)
```

Key changes:
1. `_value_matches` check before clear/retype — if the previous attempt already landed (perhaps the page just took longer to navigate), skip and proceed.
2. `with TypingSlot.acquire(...)` wraps the clear + `keyboard.type` together.
3. Click is left *outside* the gate — clicking doesn't race; only typing does.

- [ ] **Step 3: Smoke-check the syntax**

```bash
python -c "import ast; ast.parse(open('src/login_flow.py').read())"
```

Expected: no output.

- [ ] **Step 4: Run existing tests**

```bash
python -m pytest tests/test_typing_slot.py tests/test_value_matches.py -v
```

Expected: all tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/login_flow.py
git commit -m "feat(login): gate reload-retype email loop with TypingSlot + pre-check"
```

---

## Task 5: Apply `TypingSlot` + `_value_matches` to password fill

**Files:**
- Modify: `src/login_flow.py:690-704` (the `for pwd_attempt in range(1, 4):` outer loop, inner `for sel in pwd_selectors:` block)

- [ ] **Step 1: Read the current block**

```bash
sed -n '688,708p' src/login_flow.py
```

You should see `await elem.fill(password)` around line 697.

- [ ] **Step 2: Wrap the password fill with TypingSlot + pre-check**

Replace the inner `for sel in pwd_selectors:` block (lines 691-702) with:

```python
            for sel in pwd_selectors:
                try:
                    elem = page.locator(sel).first
                    count = await elem.count()
                    visible = await elem.is_visible() if count > 0 else False
                    if count > 0 and visible:
                        if await _value_matches(elem, password):
                            _log(worker_id, f"STEP[3/4] PASSWORD: Already filled via '{sel}' — skipping retype")
                            pwd_filled = True
                            break
                        with TypingSlot.acquire(worker_id, "password"):
                            await elem.fill('')
                            await elem.fill(password)
                        _log(worker_id, f"STEP[3/4] PASSWORD: Filled password via '{sel}' (attempt {pwd_attempt})")
                        pwd_filled = True
                        break
                except:
                    continue
```

- [ ] **Step 3: Smoke-check the syntax**

```bash
python -c "import ast; ast.parse(open('src/login_flow.py').read())"
```

Expected: no output.

- [ ] **Step 4: Run all backend tests**

```bash
python -m pytest tests/test_typing_slot.py tests/test_value_matches.py -v
```

Expected: all six tests still pass.

- [ ] **Step 5: Commit**

```bash
git add src/login_flow.py
git commit -m "feat(login): gate password fill with TypingSlot + pre-check value"
```

---

## Task 6: Status column — replace pill with dot

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:463-466` (statusCls/statusLbl computation)
- Modify: `electron-app/renderer/modules/profiles.js:491-495` (status column markup)

- [ ] **Step 1: Replace the status class + label computation**

Find lines 463-466:

```js
                const statusCls = p.status === 'logged_in' ? 'pm-status-ok' :
                                  p.status === 'login_failed' ? 'pm-status-fail' : 'pm-status-none';
                const statusLbl = p.status === 'logged_in' ? 'Logged In' :
                                  p.status === 'login_failed' ? 'Failed' : 'Not Logged In';
```

Replace with:

```js
                const dotCls = p.status === 'logged_in' ? 'pm-dot-ok' :
                               p.status === 'login_failed' ? 'pm-dot-fail' : 'pm-dot-none';
                const dotTitle = p.status === 'logged_in' ? 'Logged In' :
                                 p.status === 'login_failed' ? 'Failed' : 'Not Logged In';
```

- [ ] **Step 2: Replace the status column markup**

Find lines 491-495 (inside the row template literal):

```js
                    <div class="pm-col-status">
                        <span class="pm-status ${statusCls}">${statusLbl}</span>
                        ${isOpen ? '<span class="pm-status pm-status-running" style="margin-left:4px;"><i class="fas fa-circle"></i> Open</span>'
                            : isStarting ? '<span class="pm-status pm-status-starting" style="margin-left:4px;"><i class="fas fa-spinner fa-spin"></i> Launching</span>' : ''}
                    </div>
```

Replace with:

```js
                    <div class="pm-col-status">
                        <span class="pm-dot ${dotCls}" title="${dotTitle}"></span>
                        ${isOpen ? '<span class="pm-dot pm-dot-open" title="Browser open"></span>'
                            : isStarting ? '<span class="pm-dot pm-dot-starting" title="Launching"></span>' : ''}
                    </div>
```

- [ ] **Step 3: Manual verify in browser**

Run the Electron app:

```bash
cd electron-app && npm run dev
```

Or (Windows PowerShell):

```powershell
Set-Location electron-app; npm run dev
```

Open Profile Manager. Confirm:
- Each row's status column shows a single colored dot (green / red / gray) instead of the old pill.
- Hovering the dot shows tooltip with "Logged In" / "Failed" / "Not Logged In".
- Open status (running browser) shows a second dot next to the main one.

The dots may be unstyled at this point (no CSS yet — that's Task 9). The HTML being correct is the success criterion for this task.

- [ ] **Step 4: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(profiles): replace status pill with dot + tooltip"
```

---

## Task 7: Credentials cell — make email and password clickable, drop copy buttons

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:213-225` (`_credentialsCellHTML`)

- [ ] **Step 1: Rewrite `_credentialsCellHTML`**

Replace the entire function (lines 213-225):

```js
    function _credentialsCellHTML(p) {
        const email = p.email || '';
        const hasPass = !!p.password;
        const emailLine = `<div class="pm-cred-line">
            <span class="pm-cred-text" title="${_esc(email)}">${_esc(email || '—')}</span>
            ${email ? `<button class="pm-copy-btn pm-copy-email" data-id="${p.id}" title="Copy email"><i class="fas fa-copy"><\i><\button>` : ''}
        </div>`;
        const passLine = hasPass ? `<div class="pm-cred-line">
            <span class="pm-cred-text" style="letter-spacing:2px;">••••••••</span>
            <button class="pm-copy-btn pm-copy-pass" data-id="${p.id}" title="Copy password"><i class="fas fa-copy"></i></button>
        <\div>` : '';
        return `<div class="pm-col-creds">${emailLine}${passLine}</div>`;
    }
```

with:

```js
    function _credentialsCellHTML(p) {
        const email = p.email || '';
        const hasPass = !!p.password;
        const emailLine = email ? `<div class="pm-cred-line">
            <span class="pm-cred-text pm-copyable" data-copy-value="${_esc(email)}" data-copy-label="Email" title="Click to copy email">${_esc(email)}</span>
        </div>` : `<div class="pm-cred-line"><span class="pm-cred-text" style="color:var(--text-muted);">—</span></div>`;
        const passLine = hasPass ? `<div class="pm-cred-line">
            <span class="pm-cred-text pm-copyable" data-copy-value="${_esc(p.password)}" data-copy-label="Password" title="Click to copy password" style="letter-spacing:2px;">••••••••</span>
        </div>` : '';
        return `<div class="pm-col-creds">${emailLine}${passLine}</div>`;
    }
```

Notes:
- The copy buttons are gone.
- Email and password text spans now carry `pm-copyable` + `data-copy-value` + `data-copy-label`.
- The "no email" case still renders a dash so the column has consistent height.
- The original code has two backtick-escape typos (`<\i><\button>`, `<\div>`) — those are preserved as fixed (proper closing tags) in the rewrite.

- [ ] **Step 2: Manual verify in browser**

Reload the Electron app or hot-reload the renderer. Confirm:
- The `📄` copy icons next to email and password are gone.
- Hovering email/password shows pointer cursor (after CSS in Task 9 — for now just confirm the markup is right by inspecting one row in DevTools).
- The masked password still renders as `••••••••`.

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(profiles): make email and password text click-to-copy, drop copy buttons"
```

---

## Task 8: TOTP cell — make code clickable, drop copy button

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:227-254` (`_proxyTotpCellHTML`)

- [ ] **Step 1: Rewrite the TOTP line inside `_proxyTotpCellHTML`**

Find the `totpHTML` block (lines 247-251):

```js
        const totpHTML = totp ? `<div class="pm-totp-line" data-totp-row="${p.id}">
            <span class="pm-totp-code" data-totp-code data-totp-secret="${_esc(totp)}">------</span>
            <span class="pm-totp-countdown" data-totp-countdown>—s</span>
            <button class="pm-copy-btn pm-copy-totp" data-id="${p.id}" title="Copy 2FA code"><i class="fas fa-copy"></i></button>
        <\div>` : '';
```

Replace with:

```js
        const totpHTML = totp ? `<div class="pm-totp-line" data-totp-row="${p.id}">
            <span class="pm-totp-code pm-copyable" data-totp-code data-totp-secret="${_esc(totp)}" data-copy-from-totp="${p.id}" data-copy-label="2FA" title="Click to copy 2FA code">------</span>
            <span class="pm-totp-countdown" data-totp-countdown>—s</span>
        </div>` : '';
```

Notes:
- The copy button is gone.
- The code span now carries `pm-copyable` + `data-copy-from-totp="<id>"` + `data-copy-label="2FA"`.
- The value to copy is *dynamic* (the ticker rewrites `data-totp-code` every second), so we use `data-copy-from-totp` to mark "read the live code from this row's ticker output" rather than a static `data-copy-value`.
- Closing tag fixed (`</div>`).

- [ ] **Step 2: Manual verify in browser**

Reload the Electron app. Confirm:
- The `📄` copy button next to each 2FA code is gone.
- Hovering the 6-digit code shows pointer cursor (visual styling lands in Task 9).
- The code itself still updates every second via the TOTP ticker.

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(profiles): make TOTP code click-to-copy, drop copy button"
```

---

## Task 9: Wire delegated `.pm-copyable` click handler in `_attachRowEvents`

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:542-564` (the three `pm-copy-email` / `pm-copy-pass` / `pm-copy-totp` handler blocks)

- [ ] **Step 1: Find and replace the three handler blocks**

Find lines 542-564 — three separate `listEl.querySelectorAll('.pm-copy-*').forEach(...)` blocks:

```js
        // Credential copy buttons
        listEl.querySelectorAll('.pm-copy-email').forEach(b => b.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = b.dataset.id;
            const p = _allProfiles.find(x => x.id === id);
            if (p) _copyWithToast(p.email, b, 'Email copied');
        }));
        listEl.querySelectorAll('.pm-copy-pass').forEach(b => b.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = b.dataset.id;
            const p = _allProfiles.find(x => x.id === id);
            if (p) _copyWithToast(p.password, b, 'Password copied');
        }));

        // 2FA copy — reads the current rendered code (kept in data-totp-code by the ticker)
        listEl.querySelectorAll('.pm-copy-totp').forEach(b => b.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = b.dataset.id;
            const codeEl = listEl.querySelector(`[data-totp-row="${id}"] [data-totp-code]`);
            const code = codeEl ? (codeEl.dataset.totpCode || '') : '';
            if (code) _copyWithToast(code, b, '2FA copied');
            else if (App.toast) App.toast('2FA code not ready yet', 'warn');
        }));
```

Replace all three blocks with one delegated handler:

```js
        // Unified click-to-copy on .pm-copyable spans (email, password, TOTP code)
        listEl.querySelectorAll('.pm-copyable').forEach(el => el.addEventListener('click', (e) => {
            e.stopPropagation();
            const label = el.dataset.copyLabel || 'Value';
            let val = el.dataset.copyValue || '';
            // TOTP case: value is dynamic, read live from the row's ticker output
            const totpRowId = el.dataset.copyFromTotp;
            if (totpRowId) {
                const codeEl = listEl.querySelector(`[data-totp-row="${totpRowId}"] [data-totp-code]`);
                val = codeEl ? (codeEl.dataset.totpCode || '') : '';
                if (!val || val === '------') {
                    if (App.toast) App.toast('2FA code not ready yet', 'warn');
                    return;
                }
            }
            if (val) _copyWithToast(val, el, `${label} copied`);
        }));
```

- [ ] **Step 2: Manual verify in browser**

Reload the Electron app. Confirm:
- Click on an email → toast appears: "Email copied". Paste into a text field — clipboard has the email.
- Click on a masked password → toast: "Password copied". Paste — clipboard has the actual password.
- Click on a live 2FA code → toast: "2FA copied". Paste — 6 digits.
- Click on a 2FA code that still shows `------` → toast: "2FA code not ready yet". No crash.
- Clicking the email/password/code does NOT toggle the row's checkbox selection (because of `stopPropagation`).

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(profiles): unified .pm-copyable click handler for email/pass/totp"
```

---

## Task 10: CSS — dot styles, column spacing, copyable hover

**Files:**
- Modify: `electron-app/renderer/styles.css:2030-2031` (column widths)
- Modify: `electron-app/renderer/styles.css:2443-2456` (`.pm-status*` rules — keep but no longer used in row, leave for now)
- Add: New `.pm-dot*` and `.pm-copyable` rules at the end of the same `pm-status` block

- [ ] **Step 1: Update column widths and add gap**

Find lines 2030-2031:

```css
.pm-col-status { width: 90px; flex-shrink: 0; }
.pm-col-group { width: 160px; flex-shrink: 0; display: flex; align-items: center; }
```

Replace with:

```css
.pm-col-status { width: 36px; flex-shrink: 0; display: flex; align-items: center; gap: 6px; }
.pm-col-group { width: 160px; flex-shrink: 0; display: flex; align-items: center; margin-left: 12px; }
```

- [ ] **Step 2: Add `.pm-dot*` and `.pm-copyable` rules**

At the end of the file (or right after the existing `.pm-status-starting` rule on line 2456), add:

```css
/* ── Status dots (replaces pill labels) ──────────────────────────────── */
.pm-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    vertical-align: middle;
}
.pm-dot-ok      { background: #34d399; box-shadow: 0 0 6px rgba(52, 211, 153, 0.7); }
.pm-dot-fail    { background: #f87171; box-shadow: 0 0 6px rgba(248, 113, 113, 0.7); }
.pm-dot-none    { background: #94a3b8; box-shadow: none; }
.pm-dot-open    { background: #a5b4fc; box-shadow: 0 0 6px rgba(165, 180, 252, 0.8); animation: pm-dot-pulse 1.4s ease-in-out infinite; }
.pm-dot-starting{ background: #fbbf24; box-shadow: 0 0 6px rgba(251, 191, 36, 0.7); animation: pm-dot-pulse 0.9s ease-in-out infinite; }

@keyframes pm-dot-pulse {
    0%, 100% { transform: scale(0.85); opacity: 0.85; }
    50%      { transform: scale(1.15); opacity: 1; }
}

/* ── Click-to-copy affordance ────────────────────────────────────────── */
.pm-copyable {
    cursor: pointer;
    border-radius: 4px;
    padding: 1px 4px;
    margin: -1px -4px;
    transition: background 0.15s ease;
}
.pm-copyable:hover  { background: rgba(99, 102, 241, 0.14); }
.pm-copyable:active { background: rgba(99, 102, 241, 0.28); }
.pm-copyable.pm-copied { background: rgba(52, 211, 153, 0.25); }
```

- [ ] **Step 3: Manual verify in browser**

Reload the Electron app. Confirm:
- Status column is now narrow (~36px) and the Group dropdown has visible breathing room.
- Each dot has the right color and Open/Launching dots pulse.
- Hovering email/password/TOTP shows a soft indigo highlight + pointer cursor.
- Click → brief flash + toast appears (the `pm-copied` class will fire only if added by `_copyWithToast`; if not, hover/active states alone are enough).

- [ ] **Step 4: Patch `_copyWithToast` to flash text spans without overwriting their content**

The existing `_copyWithToast` at `electron-app/renderer/modules/profiles.js:77-93` does:

```js
    function _copyWithToast(text, btn, label) {
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            if (btn) {
                const prev = btn.innerHTML;
                btn.classList.add('copied');
                btn.innerHTML = '<i class="fas fa-check"></i>';
                setTimeout(() => {
                    btn.classList.remove('copied');
                    btn.innerHTML = prev;
                }, 1200);
            }
            if (App.toast) App.toast((label || 'Copied') + ' ✓', 'success');
        }).catch(() => {
            if (App.toast) App.toast('Copy failed', 'error');
        });
    }
```

That replaces `innerHTML` with a check icon — fine for an icon button, but it would erase the email/password/code text in the new copyable spans. Replace the whole function with:

```js
    function _copyWithToast(text, el, label) {
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            if (el) {
                // Text span (.pm-copyable) — flash background only, don't touch innerHTML
                if (el.classList && el.classList.contains('pm-copyable')) {
                    el.classList.add('pm-copied');
                    setTimeout(() => el.classList.remove('pm-copied'), 350);
                } else {
                    // Icon button — swap to check glyph briefly
                    const prev = el.innerHTML;
                    el.classList.add('copied');
                    el.innerHTML = '<i class="fas fa-check"></i>';
                    setTimeout(() => {
                        el.classList.remove('copied');
                        el.innerHTML = prev;
                    }, 1200);
                }
            }
            if (App.toast) App.toast((label || 'Copied') + ' ✓', 'success');
        }).catch(() => {
            if (App.toast) App.toast('Copy failed', 'error');
        });
    }
```

This preserves the button behavior for any remaining icon-button copy targets and adds the `pm-copied` flash for the new text spans.

- [ ] **Step 5: Commit**

```bash
git add electron-app/renderer/styles.css electron-app/renderer/modules/profiles.js
git commit -m "feat(profiles): dot status styles, group column gap, copyable hover/flash"
```

---

## Task 11: End-to-end batch login verification

**Files:** none modified — this is a verification task.

- [ ] **Step 1: Prepare a small test sheet**

Create or reuse a `.xlsx` with 4-6 rows. Required columns: `Email`, `Password`. Optional: `TOTP Secret`, `Proxy`. Pick accounts you can safely re-login (or that have never been logged in by this build).

- [ ] **Step 2: Run batch login with 3 workers**

In the Electron UI: Batch Login → select the sheet → workers = 3 → start.

While it's running, open the dev logs (Logs tab or `debug.log.1` / `debug.log.2`).

- [ ] **Step 3: Verify expected log lines appear**

In the logs, you must see:

```
TYPING_SLOT: waiting X.Xs before typing email
TYPING_SLOT: waiting X.Xs before typing password
```

You should see at least 2 of these per batch (the first worker won't wait; subsequent ones will).

If the page reloads on the `/identifier` screen, you should also see:

```
STEP[2/4] EMAIL: Already filled via 'input[type="email"]' — skipping retype
```

or similar.

- [ ] **Step 4: Verify no garbled-email failures**

Check each account's result in the Profile Manager. None should fail with "Couldn't find your Google Account" or "Enter a valid email" if the email is correct. If any does, capture the log section for that account and investigate before moving on.

- [ ] **Step 5: Verify throughput**

Total batch time for N accounts with W workers should be roughly:

```
T ≈ max(per-account login time, 2s * (N / W))
```

For 6 accounts with 3 workers, expect ~30-90s depending on Google's response times. The 2s gates contribute a maximum of `6 * 2s = 12s` total across the whole batch — well within tolerance.

- [ ] **Step 6: No commit unless changes**

This task only verifies; no commit unless you discovered an issue and had to tweak something. If you did tweak, commit with `fix(login): <description>`.

---

## Task 12: Manual UI walkthrough

**Files:** none modified — this is a verification task.

- [ ] **Step 1: Open Profile Manager**

Confirm the row is rendering cleanly with the new layout.

- [ ] **Step 2: Walk through every interactive bit**

| Action | Expected |
|---|---|
| Hover status dot | Tooltip: "Logged In" / "Failed" / "Not Logged In" |
| Click on email | Toast "Email copied", clipboard has email |
| Click on password (masked dots) | Toast "Password copied", clipboard has plain password |
| Click on live TOTP code | Toast "2FA copied", clipboard has 6 digits |
| Click on TOTP code while still `------` | Toast "2FA code not ready yet", no crash |
| Launch a browser from a row | Open dot (pulsing blue) appears alongside login dot |
| Close the browser | Open dot disappears, just login dot remains |
| Filter "Logged In" | All visible rows have green dot |
| Filter "Failed" | All visible rows have red dot |
| Filter "Not Logged In" | All visible rows have gray dot |
| Group column dropdown | Still functional, no overlap with status |

- [ ] **Step 3: Inspect rendering at smallest reasonable window width**

Resize the Electron window narrower. Confirm no overlap between Status and Group, no horizontal scroll inside a row.

- [ ] **Step 4: No commit**

This is verification only. If something looks wrong, fix in a follow-up commit referencing the specific issue.

---

## Self-Review Notes

After writing this plan, ran the spec coverage / placeholder scan / type-consistency checks:

- **Spec section 1 (status dot)** → Tasks 6, 10
- **Spec section 2 (click-to-copy)** → Tasks 7, 8, 9, 10
- **Spec section 3 (TypingSlot semaphore)** → Tasks 1, 3, 4, 5
- **Spec section 4 (value pre-check)** → Tasks 2, 3, 4, 5
- **Spec section 5 (files changed list)** → matches Tasks 1-10
- **Testing (UI walkthrough)** → Task 12
- **Testing (batch login)** → Task 11

No placeholders. No "similar to Task N". Class names: `TypingSlot.GAP_SECONDS`, `_value_matches`, `.pm-copyable`, `.pm-dot-ok`/`.pm-dot-fail`/`.pm-dot-none`/`.pm-dot-open`/`.pm-dot-starting`, `data-copy-value`/`data-copy-label`/`data-copy-from-totp` — all referenced consistently across tasks.
