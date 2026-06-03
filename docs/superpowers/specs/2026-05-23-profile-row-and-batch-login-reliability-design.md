# Profile Row UI Polish + Batch-Login Reliability — Design

Date: 2026-05-23
Status: Approved (pending spec review)

## Goal

Two related changes to the Profile Manager surface:

1. **UI polish.** Tighter, more readable rows: status as a colored dot only (no label text), real spacing between Status and Group columns, and one-click copy on email / password / 2FA without the dedicated copy buttons.
2. **Batch-login reliability.** Stop the field-typing race that lets two parallel workers (or one worker on a reloading page) hammer email/password into Google's input 2–3 times. Enforce a global 2-second gap between typing moments and skip re-typing when the field already holds the right value.

The user-stated goal for the login side is "100% kaj korbe… login adeo fail hobe na" — making the typing phase deterministic is the most leverage we have toward that.

## Non-goals

- No change to login *flow logic* (which selectors, which screens, retry counts).
- No change to profile creation, proxy assignment, OS rotation, fingerprinting.
- No change to the Run Ops / Appeal / Review code paths beyond what is shared with login typing.
- No new column or batch-login UI; the existing Batch Login dialog and progress toast stay.

## Current state (reference)

- Row template: [electron-app/renderer/modules/profiles.js:484](electron-app/renderer/modules/profiles.js) — six columns (check, profile, creds, proxy/2fa, status, group, actions).
- Status rendering: [profiles.js:491-495](electron-app/renderer/modules/profiles.js) builds `<span class="pm-status …">{label}</span>` plus an extra Open/Launching span.
- Credentials cell: `_credentialsCellHTML` [profiles.js:213-225](electron-app/renderer/modules/profiles.js) renders email text + `.pm-copy-email` button and a masked password + `.pm-copy-pass` button.
- 2FA cell: `_proxyTotpCellHTML` [profiles.js:247-251](electron-app/renderer/modules/profiles.js) renders the rolling code + `.pm-copy-totp` button.
- Copy handlers: [profiles.js:543-564](electron-app/renderer/modules/profiles.js) — `_copyWithToast` already exists and is the contract we keep.
- Column widths: `.pm-col-status { width: 90px }`, `.pm-col-group { width: 160px }` at [styles.css:2030-2031](electron-app/renderer/styles.css).
- Login typing: [src/login_flow.py:437](src/login_flow.py) (initial email fill), [src/login_flow.py:571-574](src/login_flow.py) (reload-retype email), and the password block at [src/login_flow.py:686+](src/login_flow.py).
- Batch worker pool: `ThreadPoolExecutor` at [shared/profile_manager.py:1599](shared/profile_manager.py) — each worker runs login in its own asyncio loop, so a thread-level lock is the right primitive for cross-worker coordination.

## Design

### 1. Status column — dot only

Replace the status pill with a colored dot. Drop the text label entirely. Browser-state (Open / Launching) remains visible as a small adjacent indicator only when active.

**HTML** (in the row template):
```html
<div class="pm-col-status">
  <span class="pm-dot pm-dot-{ok|fail|none}" title="{Logged In|Failed|Not Logged In}"></span>
  <!-- only when active: -->
  <span class="pm-dot pm-dot-open" title="Browser open"></span>     <!-- pulsing -->
  <span class="pm-dot pm-dot-starting" title="Launching…"></span>   <!-- spinner -->
</div>
```

**CSS:**
- `.pm-dot` — 10px circle, inline-flex, vertical-align middle.
- `.pm-dot-ok` — `#34d399` with soft glow.
- `.pm-dot-fail` — `#f87171` with soft glow.
- `.pm-dot-none` — `#94a3b8` flat.
- `.pm-dot-open` — `#a5b4fc`, pulsing animation (keyframe scale 0.8→1.2 + opacity).
- `.pm-dot-starting` — `#fbbf24`, `::after` with `fa-spinner fa-spin` glyph.
- `title` attribute carries the textual meaning for hover/accessibility — the label isn't gone, it's just on hover.
- `.pm-col-status { width: 28px; padding-right: 8px; display: flex; align-items: center; gap: 6px; }`
- `.pm-col-group { margin-left: 12px; }` — visible breathing room between the two columns. (The previous 90px status column gave incidental gap; explicit gap replaces it.)

### 2. Click-to-copy on credentials

Make the text itself the copy affordance; remove the dedicated copy buttons.

**`_credentialsCellHTML` rewrite:**
```js
const emailLine = email ? `<div class="pm-cred-line">
  <span class="pm-cred-text pm-copyable" data-copy-value="${_esc(email)}" data-copy-label="Email" title="Click to copy email">${_esc(email)}</span>
</div>` : '';
const passLine = hasPass ? `<div class="pm-cred-line">
  <span class="pm-cred-text pm-copyable" data-copy-value="${_esc(p.password)}" data-copy-label="Password" title="Click to copy password" style="letter-spacing:2px;">••••••••</span>
</div>` : '';
```

**`_proxyTotpCellHTML` rewrite:** drop `.pm-copy-totp`; add `pm-copyable` + `data-copy-from-totp="<id>"` to the `.pm-totp-code` span (value is dynamic, sourced from `data-totp-code` like today).

**Event wiring** in `_attachRowEvents` — replace the three `pm-copy-*` blocks with one delegated handler:
```js
listEl.querySelectorAll('.pm-copyable').forEach(el => el.addEventListener('click', (e) => {
  e.stopPropagation();
  let val = el.dataset.copyValue || '';
  // TOTP: read live code from the row's ticker-managed span
  if (el.dataset.copyFromTotp) {
    const codeEl = listEl.querySelector(`[data-totp-row="${el.dataset.copyFromTotp}"] [data-totp-code]`);
    val = codeEl ? (codeEl.dataset.totpCode || '') : '';
    if (!val) { App.toast && App.toast('2FA code not ready yet', 'warn'); return; }
  }
  if (val) _copyWithToast(val, el, `${el.dataset.copyLabel || 'Value'} copied`);
}));
```

**CSS:** `.pm-copyable { cursor: pointer; border-radius: 4px; transition: background 0.15s; }` and `.pm-copyable:hover { background: rgba(99,102,241,0.12); }`. A short `.pm-copied` flash class (180ms) for visual confirmation when a copy succeeds.

### 3. Global typing semaphore (2-second gap)

Add a thread-safe gate in `src/login_flow.py` that serializes the *moment of typing* across all workers, with a minimum 2-second gap between successive releases.

```python
# Top of src/login_flow.py
import threading, time
from contextlib import contextmanager

class TypingSlot:
    """Global gate: only one profile types into a login field at a time,
    with a minimum 2-second gap between typing events across all workers."""
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
                _log(worker_id, f"TYPING_SLOT: waiting {wait:.1f}s before typing {what}")
                time.sleep(wait)
            yield
        finally:
            cls._last_release = time.monotonic()
            cls._lock.release()
```

**Usage points** (every place we write into a Google login input):

1. Initial email fill — wrap [src/login_flow.py:437](src/login_flow.py):
   ```python
   with TypingSlot.acquire(worker_id, "email"):
       if not await _value_matches(elem, email):
           await elem.fill('')
           await elem.fill(email)
   ```
2. Reload-retype email — wrap [src/login_flow.py:571-574](src/login_flow.py).
3. Password fill — wrap [src/login_flow.py:697](src/login_flow.py).
4. Any password-retype path inside `execute_login_flow` (forced new password screen).

Lock is `threading.Lock`, held by *this* thread, around a `time.sleep` if needed. Each worker runs its own asyncio loop in its own thread, so `time.sleep` inside the gate blocks only that one worker — exactly what we want. The 2s wait is *before* typing; the lock then releases as soon as typing finishes, but `_last_release` ensures the *next* acquirer still waits its share.

Browser navigation, page-load waits, screen detection, OAuth callbacks — all of those run *outside* the gate, so the 2s serialization adds at most `2 × num_workers` seconds of throughput cost across a whole batch, not per-account.

### 4. Pre-check input value before typing

Helper at top of `src/login_flow.py`:
```python
async def _value_matches(elem, expected: str) -> bool:
    try:
        cur = (await elem.input_value()) or ''
    except Exception:
        return False
    return cur.strip() == (expected or '').strip()
```

Apply at every typing point above. If the field already holds the right value, log "already filled, skipping retype" and proceed straight to the Next/submit step. If the field has a different non-empty value (stale autofill), clear once then fill once.

This handles the user's specific complaint — when the page reloads mid-flow and the existing retype loop fired a second time before the field had actually been cleared, two consecutive `keyboard.type(email, delay=25)` calls would interleave keystrokes and produce a garbled string. With pre-check + semaphore, the second attempt will see the field already populated (or empty and ready) and not stack on top of an in-flight fill.

### 5. Files changed (summary)

| File | What changes |
| --- | --- |
| `electron-app/renderer/modules/profiles.js` | `_credentialsCellHTML`, `_proxyTotpCellHTML`, status section in row template, `_attachRowEvents` (replace 3 copy handlers with 1 delegated `.pm-copyable` handler) |
| `electron-app/renderer/styles.css` | New `.pm-dot*` rules, `.pm-col-status` width 90→28 + gap, `.pm-col-group` left margin, `.pm-copyable` cursor/hover/flash, remove unused `.pm-copy-btn` rules (kept if still used elsewhere) |
| `src/login_flow.py` | New `TypingSlot` class, `_value_matches` helper, wrap all login-field fills with `with TypingSlot.acquire(): if not await _value_matches(...): fill` |

No backend API changes. No `shared/profile_manager.py` or `shared/nexus_profile_manager.py` changes. Worker count and ThreadPoolExecutor stay; the semaphore is *inside* what each worker does, not at the dispatch layer.

## Testing

UI side — open the Electron app and the Profile Manager page:
- Status dot only, colors correct for each filter (All / Logged In / Not Logged In / Failed).
- Spacing between Status and Group columns visible.
- Click on an email → toast "Email copied", clipboard has the email.
- Click on the masked password → toast "Password copied", clipboard has the actual password.
- Click on a live 2FA code → toast "2FA copied", clipboard has the 6-digit code.
- Click before 2FA code is ready → toast "2FA code not ready yet", no crash.
- Hover state visible on all three copyable spans.

Login side — run a batch login with `num_workers ≥ 3` on a sheet of 5+ accounts:
- Logs show `TYPING_SLOT: waiting Xs` lines for every account beyond the first concurrent one.
- Logs show `Email already filled, skipping retype` whenever the reload loop fires.
- No account produces a "garbled email" or "invalid email format" error from Google.
- Final success/failed counts match what running the same sheet sequentially produces.

## Risks

- **Throughput impact.** A 2s gate per typing event ≈ 4 extra seconds per account (email + password). On a 1000-account sheet with 10 workers, that's ~400s ≈ 7 min added — acceptable given the goal of "100% kaj korbe."
- **TOTP timing.** Not gated; reading a 2FA code is local computation, no field typing. Confirmed not affected.
- **Status dot accessibility.** Without text the meaning lives in `title`; users on touch devices can long-press. If this becomes a complaint, we can add a tooltip-on-hover library or restore a single-letter label.
- **`pm-copyable` event bubbling.** The row itself has click behavior (selection); the `e.stopPropagation()` inside the handler is essential. Verified in test plan.

## Out of scope

- Status filter pill counts (already correct, no change).
- Group dropdown UX (separate work).
- Batch login skip-existing logic (already correct).
- 2FA copy from row template when the row is collapsed (rows never collapse today).
