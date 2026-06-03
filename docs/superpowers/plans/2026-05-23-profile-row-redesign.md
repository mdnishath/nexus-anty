# Profile Row Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Profile Manager table row so every profile shows email + masked password (with copy), country + live 2FA code (with copy), and an inline editable group dropdown — eliminating the Activity column and the need to open the edit modal for routine reads.

**Architecture:** Single-page changes inside the existing Electron renderer (`profiles.js`) plus one new Flask endpoint. Country lookups are server-side (ip-api.com) with results cached on `profile.proxy`. TOTP codes are computed client-side using the existing `App._generateTOTP` helper from `modules/totp.js`, driven by one shared `setInterval` (1 Hz) that updates a countdown each tick and recomputes codes on 30-second boundaries. Group changes apply optimistically (no row re-render) and persist via `PUT /api/profiles/<id>`.

**Tech Stack:** Vanilla JS (renderer), Flask (backend), `requests` (HTTP), Web Crypto API (HMAC-SHA1 for TOTP).

**Reference spec:** `docs/superpowers/specs/2026-05-23-profile-row-redesign-design.md`

---

## File Structure

- **Modify** `electron-app/backend/server.py` — add `GET /api/profiles/<id>/proxy-country` route.
- **Modify** `electron-app/renderer/styles.css` — add `.pm-col-creds`, expand `.pm-col-group`, restyle `.pm-col-profile` and `.pm-col-proxy`, add `.pm-copy-btn` / `.pm-country-*` / `.pm-totp-*` / `.pm-group-select`; remove `.pm-col-updated`.
- **Modify** `electron-app/renderer/index.html` — replace the table header row (~lines 564–571) with the new 6-column layout (drops Activity, adds Credentials).
- **Modify** `electron-app/renderer/modules/profiles.js` — biggest change: new helpers, country queue, group dropdown logic, TOTP shared timer, new row template, updated event wiring.
- **No change** `electron-app/renderer/modules/totp.js` — already provides `App._generateTOTP(secret)`.
- **No change** `shared/profile_manager.py` — `update_profile` already accepts the full `proxy` dict in its allowed-fields list.

---

## Task 1: Backend — proxy-country lookup endpoint

**Files:**
- Modify: `electron-app/backend/server.py` (add new route, after the `/api/profiles/<id>` PUT route around line 2338)

- [ ] **Step 1: Add the route**

Append after the `profiles_update` function (line ~2347, before `profiles_delete_all`):

```python
@app.route('/api/profiles/<profile_id>/proxy-country', methods=['GET'])
def profiles_proxy_country(profile_id):
    """Look up country for a profile's proxy host via ip-api.com.

    Caches the result on profile.proxy.country / .country_code so subsequent
    calls return instantly. Failures are not cached so they retry later.
    """
    import requests as _req
    profiles = profile_manager.list_profiles()
    profile = next((p for p in profiles if p['id'] == profile_id), None)
    if not profile:
        return jsonify({'success': False, 'message': 'Profile not found'}), 404

    proxy = dict(profile.get('proxy') or {})
    # Return cached value if present
    if proxy.get('country') and proxy.get('country_code'):
        return jsonify({
            'success': True,
            'country': proxy['country'],
            'country_code': proxy['country_code'],
            'cached': True,
        })

    # Extract host (from host field or from server URL)
    host = proxy.get('host') or ''
    if not host and proxy.get('server'):
        srv = proxy['server']
        host = srv.split('://', 1)[-1].split('@')[-1].split(':')[0].split('/')[0]
    if not host:
        return jsonify({'success': True, 'country': 'No proxy', 'country_code': ''})

    try:
        r = _req.get(
            f'http://ip-api.com/json/{host}',
            params={'fields': 'status,country,countryCode'},
            timeout=5,
        )
        data = r.json()
        if data.get('status') == 'success':
            country = data.get('country', 'Unknown')
            cc = data.get('countryCode', '')
            proxy['country'] = country
            proxy['country_code'] = cc
            profile_manager.update_profile(profile_id, proxy=proxy)
            return jsonify({
                'success': True,
                'country': country,
                'country_code': cc,
                'cached': False,
            })
    except Exception as e:
        _log(f"[proxy-country] lookup failed for {profile_id} ({host}): {e}")

    return jsonify({'success': True, 'country': 'Unknown', 'country_code': ''})
```

- [ ] **Step 2: Smoke-test with a profile that has no proxy**

Pick a real profile ID (from the running app's `/api/profiles?per_page=1`) and call:

```bash
curl -s "http://127.0.0.1:5000/api/profiles/<REAL_ID>/proxy-country"
```

Expected (no-proxy case): `{"success": true, "country": "No proxy", "country_code": ""}`

- [ ] **Step 3: Smoke-test with a manually-set proxy host**

Temporarily edit a profile to add `proxy: {host: "8.8.8.8", port: 80, type: "http"}` via the existing edit modal, save, then:

```bash
curl -s "http://127.0.0.1:5000/api/profiles/<REAL_ID>/proxy-country"
```

Expected: `{"success": true, "country": "United States", "country_code": "US", "cached": false}`

Call it again — expected: same response but `"cached": true`.

- [ ] **Step 4: Commit**

```bash
git add electron-app/backend/server.py
git commit -m "feat: add /api/profiles/<id>/proxy-country lookup endpoint"
```

---

## Task 2: CSS — column layout and new cell styles

**Files:**
- Modify: `electron-app/renderer/styles.css` (around lines 2026–2087)

- [ ] **Step 1: Update column-width rules**

Replace lines 2026–2031 (the block starting `.pm-col-check`):

```css
.pm-col-check { width: 32px; flex-shrink: 0; text-align: center; }
.pm-col-profile { flex: 1.4; min-width: 0; }
.pm-col-creds { flex: 1.8; min-width: 0; display: flex; flex-direction: column; gap: 4px; justify-content: center; font-size: 11px; }
.pm-col-proxy { flex: 1.5; min-width: 0; font-size: 11px; display: flex; flex-direction: column; gap: 4px; justify-content: center; }
.pm-col-status { width: 90px; flex-shrink: 0; }
.pm-col-group { width: 160px; flex-shrink: 0; display: flex; align-items: center; }
```

(`pm-col-updated` rule is gone. `pm-col-group` is now 160 px instead of 80 px and uses flex for the select.)

- [ ] **Step 2: Remove the old group-pill flex rule**

Delete line 2049 entirely (the second `.pm-col-group { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; }`). The new rule above replaces it. `.pm-group-pill` itself can stay — other parts of the app may use it elsewhere.

- [ ] **Step 3: Append new cell styles**

Append at the end of styles.css (after the last `.pm-os-badge` block around line 2093):

```css
/* === Profile row redesign (2026-05-23) === */

/* Credentials cell */
.pm-cred-line { display: flex; align-items: center; gap: 6px; white-space: nowrap; overflow: hidden; }
.pm-cred-text { font-family: monospace; overflow: hidden; text-overflow: ellipsis; flex: 1; min-width: 0; color: var(--text-secondary); }

/* Copy button (used in credentials and 2FA) */
.pm-copy-btn {
    flex-shrink: 0; background: transparent; border: 1px solid rgba(255,255,255,0.1);
    color: var(--text-muted); padding: 2px 6px; border-radius: 4px; font-size: 10px;
    cursor: pointer; transition: all 0.15s; line-height: 1;
}
.pm-copy-btn:hover { color: var(--text); background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.2); }
.pm-copy-btn.copied { color: #22c55e; border-color: rgba(34,197,94,0.4); }

/* Proxy / 2FA cell */
.pm-country-line { display: flex; align-items: center; gap: 6px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pm-country-flag { font-size: 14px; line-height: 1; }
.pm-totp-line { display: flex; align-items: center; gap: 8px; font-family: monospace; }
.pm-totp-code { color: #c7d2fe; font-weight: 600; letter-spacing: 1px; }
.pm-totp-countdown { font-size: 10px; color: var(--text-muted); min-width: 28px; }

/* Inline group dropdown */
.pm-group-select {
    width: 100%; background: rgba(99,102,241,0.10); color: #c7d2fe;
    border: 1px solid rgba(99,102,241,0.25); border-radius: 6px;
    padding: 4px 8px; font-size: 12px; cursor: pointer; outline: none;
    appearance: none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='%23a5b4fc' d='M0 0l5 6 5-6z'/></svg>");
    background-repeat: no-repeat; background-position: right 8px center; padding-right: 24px;
}
.pm-group-select:hover { background-color: rgba(99,102,241,0.18); }
.pm-group-select:focus { border-color: rgba(99,102,241,0.6); }
.pm-group-select option { background: #1a1d27; color: #e0e7ff; }
```

- [ ] **Step 4: Commit**

```bash
git add electron-app/renderer/styles.css
git commit -m "style: add profile row column classes (credentials, proxy/2fa, group select)"
```

---

## Task 3: HTML — table header

**Files:**
- Modify: `electron-app/renderer/index.html` (lines 564–572)

- [ ] **Step 1: Replace the header block**

Find the existing block at line 564:

```html
<div class="pm-table-header">
    <div class="pm-col-check"><input type="checkbox" id="pmSelectAll" title="Select all visible profiles"></div>
    <div class="pm-col-profile pm-sortable" data-sort="name">Profile <i class="fas fa-sort pm-sort-icon"></i></div>
    <div class="pm-col-proxy">Proxy</div>
    <div class="pm-col-status pm-sortable" data-sort="status">Status <i class="fas fa-sort pm-sort-icon"></i></div>
    <div class="pm-col-group pm-sortable" data-sort="group">Group <i class="fas fa-sort pm-sort-icon"></i></div>
    <div class="pm-col-updated pm-sortable" style="font-size:11px;" data-sort="updated">Activity <i class="fas fa-sort pm-sort-icon"></i></div>
    <div class="pm-col-actions">Actions</div>
</div>
```

Replace with:

```html
<div class="pm-table-header">
    <div class="pm-col-check"><input type="checkbox" id="pmSelectAll" title="Select all visible profiles"></div>
    <div class="pm-col-profile pm-sortable" data-sort="name">Profile <i class="fas fa-sort pm-sort-icon"></i></div>
    <div class="pm-col-creds">Credentials</div>
    <div class="pm-col-proxy">Proxy / 2FA</div>
    <div class="pm-col-status pm-sortable" data-sort="status">Status <i class="fas fa-sort pm-sort-icon"></i></div>
    <div class="pm-col-group pm-sortable" data-sort="group">Group <i class="fas fa-sort pm-sort-icon"></i></div>
    <div class="pm-col-actions">Actions</div>
</div>
```

- [ ] **Step 2: Commit**

```bash
git add electron-app/renderer/index.html
git commit -m "ui: update profile table header (drop Activity, add Credentials)"
```

---

## Task 4: JS — small helpers (flag, copy, format)

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js` — add helpers near other top-level helpers (just below the `_esc` function, search for `function _esc(`)

- [ ] **Step 1: Locate `_esc` and add helpers right below it**

Find the existing `_esc` definition (`function _esc(s) {`) inside the IIFE. Insert these helpers immediately after it:

```js
// === Profile row redesign helpers (2026-05-23) ===

// Convert ISO-2 country code (e.g. "US") to flag emoji (🇺🇸)
function _flagFromCC(cc) {
    if (!cc || cc.length !== 2) return '';
    const A = 0x1F1E6, ASCII_A = 65;
    return String.fromCodePoint(A + (cc.charCodeAt(0) - ASCII_A)) +
           String.fromCodePoint(A + (cc.charCodeAt(1) - ASCII_A));
}

// Format a 6-digit TOTP code as "123 456"
function _formatTotp(code) {
    if (!code || code.length !== 6) return '------';
    return code.substring(0, 3) + ' ' + code.substring(3);
}

// Copy text to clipboard, flash the button green, show a toast
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

- [ ] **Step 2: Sanity-check the helpers in DevTools**

Reload the app, open DevTools console, run (these expose nothing publicly, so test by triggering a render later). Skip — covered by integration in Task 10.

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat: add flag/copy/format helpers in profiles.js"
```

---

## Task 5: JS — country lookup queue

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js` — append the queue/worker right after the helpers from Task 4.

- [ ] **Step 1: Add module-level queue state and worker**

Insert immediately after the helpers added in Task 4:

```js
// === Country lookup queue (1500ms throttle, FIFO) ===
const _countryQueue = [];
const _countryInflight = new Set();
let _countryWorking = false;

function _enqueueCountry(profileId) {
    if (!profileId) return;
    if (_countryInflight.has(profileId)) return;
    if (_countryQueue.includes(profileId)) return;
    _countryQueue.push(profileId);
    _countryWorkerKick();
}

async function _countryWorkerKick() {
    if (_countryWorking) return;
    _countryWorking = true;
    while (_countryQueue.length > 0) {
        const id = _countryQueue.shift();
        _countryInflight.add(id);
        try {
            const data = await _api('/api/profiles/' + id + '/proxy-country');
            if (data && data.success) {
                const p = _allProfiles.find(x => x.id === id);
                if (p) {
                    p.proxy = p.proxy || {};
                    p.proxy.country = data.country;
                    p.proxy.country_code = data.country_code;
                }
                const cc = data.country_code || '';
                const flag = cc ? `<span class="pm-country-flag">${_flagFromCC(cc)}</span> ` : '';
                document.querySelectorAll(`[data-country-for="${id}"]`).forEach(el => {
                    el.innerHTML = flag + `<span>${_esc(data.country || 'Unknown')}</span>`;
                });
            }
        } catch (e) {
            // Swallow — row will retry on next render that sees no cache.
        } finally {
            _countryInflight.delete(id);
        }
        if (_countryQueue.length > 0) {
            await new Promise(r => setTimeout(r, 1500));
        }
    }
    _countryWorking = false;
}
```

- [ ] **Step 2: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat: add throttled country lookup queue in profiles.js"
```

---

## Task 6: JS — group options cache and optimistic change handler

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js` — append after Task 5 block.

- [ ] **Step 1: Add group cache and handlers**

Insert after the country queue block:

```js
// === Group dropdown ===
let _groupOptionsCache = null;

async function _loadGroupOptions(force) {
    if (_groupOptionsCache && !force) return _groupOptionsCache;
    try {
        const data = await _api('/api/profiles/groups');
        _groupOptionsCache = (data && data.groups) ? data.groups.slice() : [];
    } catch {
        _groupOptionsCache = [];
    }
    return _groupOptionsCache;
}

async function _onGroupChange(selectEl) {
    const id = selectEl.dataset.id;
    const prev = selectEl.dataset.prevValue || '';
    let newGroup = selectEl.value;

    if (newGroup === '__NEW__') {
        const name = (prompt('New group name:') || '').trim();
        if (!name) {
            selectEl.value = prev;
            return;
        }
        // Insert the new option above the __NEW__ entry and select it
        const newOpt = document.createElement('option');
        newOpt.value = name;
        newOpt.textContent = name;
        const newMarker = selectEl.querySelector('option[value="__NEW__"]');
        selectEl.insertBefore(newOpt, newMarker);
        selectEl.value = name;
        newGroup = name;
    }

    await _commitGroupChange(id, newGroup, selectEl, prev);
}

async function _commitGroupChange(id, newGroup, selectEl, prev) {
    // Optimistic local update — no row re-render, no blink
    const p = _allProfiles.find(x => x.id === id);
    if (p) {
        p.group = newGroup;
        p.groups = [newGroup];
    }
    selectEl.dataset.prevValue = newGroup;

    try {
        const res = await _api('/api/profiles/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ group: newGroup }),
        });
        if (!res || res.success === false) {
            throw new Error((res && res.message) || 'Update failed');
        }
        // Invalidate cache so any new group surfaces in other rows next render
        _groupOptionsCache = null;
    } catch (e) {
        // Revert
        if (p) {
            p.group = prev;
            p.groups = prev ? [prev] : [];
        }
        selectEl.value = prev;
        selectEl.dataset.prevValue = prev;
        if (App.toast) App.toast('Group change failed: ' + (e.message || e), 'error');
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat: add group options cache and optimistic group change in profiles.js"
```

---

## Task 7: JS — cell builders and row template replacement

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js` — add cell builder helpers, then replace the inline template inside `loadProfiles`.

- [ ] **Step 1: Add cell builder helpers**

Insert after the group block from Task 6:

```js
// === Cell builders for the new row layout ===

function _credentialsCellHTML(p) {
    const email = p.email || '';
    const hasPass = !!p.password;
    const emailLine = `<div class="pm-cred-line">
        <span class="pm-cred-text" title="${_esc(email)}">${_esc(email || '—')}</span>
        ${email ? `<button class="pm-copy-btn pm-copy-email" data-id="${p.id}" title="Copy email"><i class="fas fa-copy"></i></button>` : ''}
    </div>`;
    const passLine = hasPass ? `<div class="pm-cred-line">
        <span class="pm-cred-text" style="letter-spacing:2px;">••••••••</span>
        <button class="pm-copy-btn pm-copy-pass" data-id="${p.id}" title="Copy password"><i class="fas fa-copy"></i></button>
    </div>` : '';
    return `<div class="pm-col-creds">${emailLine}${passLine}</div>`;
}

function _proxyTotpCellHTML(p) {
    const proxy = p.proxy || {};
    const hasProxy = !!(proxy.host || proxy.server);
    const cc = proxy.country_code || '';
    const country = proxy.country || '';
    const totp = p.totp_secret || '';

    let countryHTML;
    if (!hasProxy) {
        countryHTML = `<div class="pm-country-line" style="color:var(--text-muted);">No proxy</div>`;
    } else if (country) {
        const flag = cc ? `<span class="pm-country-flag">${_flagFromCC(cc)}</span>` : '';
        countryHTML = `<div class="pm-country-line" data-country-for="${p.id}">${flag}<span>${_esc(country)}</span></div>`;
    } else {
        countryHTML = `<div class="pm-country-line" data-country-for="${p.id}">
            <i class="fas fa-spinner fa-spin"></i>
            <span style="color:var(--text-muted);">Looking up…</span>
        </div>`;
    }

    const totpHTML = totp ? `<div class="pm-totp-line" data-totp-row="${p.id}">
        <span class="pm-totp-code" data-totp-code data-totp-secret="${_esc(totp)}">------</span>
        <span class="pm-totp-countdown" data-totp-countdown>—s</span>
        <button class="pm-copy-btn pm-copy-totp" data-id="${p.id}" title="Copy 2FA code"><i class="fas fa-copy"></i></button>
    </div>` : '';

    return `<div class="pm-col-proxy">${countryHTML}${totpHTML}</div>`;
}

function _groupSelectHTML(p, groupOptions) {
    const cur = (p.groups && p.groups.length) ? p.groups[0] : (p.group || 'default');
    const options = groupOptions || [];
    const inCache = options.includes(cur);
    const curOpt = inCache ? '' : `<option value="${_esc(cur)}" selected>${_esc(cur)}</option>`;
    const opts = options.map(g => `<option value="${_esc(g)}"${g === cur ? ' selected' : ''}>${_esc(g)}</option>`).join('');
    return `<div class="pm-col-group"><select class="pm-group-select" data-id="${p.id}" data-prev-value="${_esc(cur)}">
        ${curOpt}${opts}
        <option disabled>──────────</option>
        <option value="__NEW__">+ New group…</option>
    </select></div>`;
}
```

- [ ] **Step 2: Replace the inline row template inside `loadProfiles`**

Find the existing template starting at the line `listEl.innerHTML = profiles.map(p => {` (around line 190). The block runs from there to the closing `}).join('');` around line 268.

**Just before** the `listEl.innerHTML = profiles.map(p => {` line, insert a single line that fetches group options:

```js
            const groupOptions = await _loadGroupOptions();
```

Then replace the entire `listEl.innerHTML = profiles.map(p => { ... }).join('');` block with:

```js
            listEl.innerHTML = profiles.map(p => {
                const statusCls = p.status === 'logged_in' ? 'pm-status-ok' :
                                  p.status === 'login_failed' ? 'pm-status-fail' : 'pm-status-none';
                const statusLbl = p.status === 'logged_in' ? 'Logged In' :
                                  p.status === 'login_failed' ? 'Failed' : 'Not Logged In';
                const isOpen = p.browser_open === 'running';
                const isStarting = p.browser_open === 'starting';
                const ov = p.overview || {};
                const fp = p.fingerprint || {};
                const osBase = (ov.os || fp.os_type || 'win').substring(0, 3).toUpperCase();
                const osVerRaw = ov.os_version || '';
                const osVerNum = osVerRaw.replace(/^Windows\s*/i, '').replace(/\.\d+\.\d+$/, '').trim();
                const os = osBase + (osVerNum ? ' ' + osVerNum : '');
                const engInfo = _engineInfo(p);
                const checked = _selectedIds.has(p.id) ? 'checked' : '';

                // Trigger lazy country lookup if needed
                const proxy = p.proxy || {};
                if ((proxy.host || proxy.server) && !proxy.country) {
                    _enqueueCountry(p.id);
                }

                return `<div class="pm-row ${isOpen ? 'pm-browser-open' : ''} ${isStarting ? 'pm-browser-starting' : ''} ${_selectedIds.has(p.id) ? 'pm-selected' : ''}" data-profile-id="${p.id}">
                    <div class="pm-col-check"><input type="checkbox" class="pm-row-check" data-id="${p.id}" ${checked}></div>
                    <div class="pm-col-profile">
                        <div class="pm-name"><span class="pm-os-badge" style="margin-right:6px;">${os}</span><span class="pm-engine-tag ${engInfo.tagClass}">${engInfo.badge}</span>${_esc(p.name || 'Unnamed')}</div>
                    </div>
                    ${_credentialsCellHTML(p)}
                    ${_proxyTotpCellHTML(p)}
                    <div class="pm-col-status">
                        <span class="pm-status ${statusCls}">${statusLbl}</span>
                        ${isOpen ? '<span class="pm-status pm-status-running" style="margin-left:4px;"><i class="fas fa-circle"></i> Open</span>'
                            : isStarting ? '<span class="pm-status pm-status-starting" style="margin-left:4px;"><i class="fas fa-spinner fa-spin"></i> Launching</span>' : ''}
                    </div>
                    ${_groupSelectHTML(p, groupOptions)}
                    <div class="pm-col-actions">
                        ${isOpen
                            ? `<button class="btn btn-danger btn-sm pm-close-btn" data-id="${p.id}" title="Close"><i class="fas fa-stop"></i></button>`
                            : isStarting
                            ? `<button class="btn btn-sm pm-launching-btn" disabled title="Launching..."><i class="fas fa-spinner fa-spin"></i></button>`
                            : `<button class="btn btn-primary btn-sm pm-launch-btn" data-id="${p.id}" title="Launch"><i class="fas fa-play"></i></button>`
                        }
                        <button class="btn btn-outline btn-sm pm-relogin-btn" data-id="${p.id}" title="Re-Login" style="color:#22c55e;border-color:rgba(34,197,94,0.4);"><i class="fas fa-sign-in-alt"></i></button>
                        <button class="btn btn-outline btn-sm pm-edit-btn" data-id="${p.id}" title="Edit"><i class="fas fa-pen"></i></button>
                        <button class="btn btn-danger-outline btn-sm pm-delete-btn" data-id="${p.id}" title="Delete"><i class="fas fa-trash"></i></button>
                        <button class="btn btn-outline btn-sm pm-ctx-btn" data-id="${p.id}" title="More"><i class="fas fa-ellipsis-v"></i></button>
                    </div>
                </div>`;
            }).join('');
```

Note: the Activity column (`<div class="pm-col-updated">…</div>`) and its `pm-act-tag` logic block are removed entirely. The `pm-col-group` slot now holds the editable dropdown via `_groupSelectHTML`. The email subtitle previously inside `pm-col-profile` is removed (it's now in the Credentials cell).

- [ ] **Step 3: Manual verification**

Restart the backend, open the app, load the Profile Manager page. Expected:
- Each row has 6 columns + checkbox: Profile (name only), Credentials (email + masked password each with copy), Proxy / 2FA, Status, Group (dropdown), Actions.
- Rows with no proxy show "No proxy" and no 2FA line.
- Rows with a proxy but no cached country show "Looking up…" briefly; after lookups complete (max ~1.5 s/row), country + flag appear.
- 2FA codes show `------` initially — they get populated in Task 8.

If anything renders broken, fix before committing.

- [ ] **Step 4: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat: replace profile row template with new 6-column layout"
```

---

## Task 8: JS — shared TOTP timer

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js` — add ticker functions; call `_totpTickerStart()` right after `_attachRowEvents(listEl)`.

- [ ] **Step 1: Add the ticker**

Insert after the cell-builder helpers from Task 7 (still inside the IIFE):

```js
// === Shared TOTP timer (one interval drives every visible code) ===
let _totpTickerHandle = null;
let _totpLastBoundary = -1;

function _totpTickerStart() {
    if (_totpTickerHandle) {
        // Re-render: force a re-compute on the next tick by clearing the boundary
        _totpLastBoundary = -1;
        return;
    }
    _totpTick();
    _totpTickerHandle = setInterval(_totpTick, 1000);
}

async function _totpTick() {
    const epoch = Math.floor(Date.now() / 1000);
    const boundary = Math.floor(epoch / 30);
    const remaining = 30 - (epoch % 30);

    document.querySelectorAll('[data-totp-countdown]').forEach(el => {
        el.textContent = remaining + 's';
    });

    if (boundary !== _totpLastBoundary) {
        _totpLastBoundary = boundary;
        const codeEls = document.querySelectorAll('[data-totp-code]');
        const cache = new Map();
        for (const el of codeEls) {
            const secret = el.dataset.totpSecret;
            if (!secret) continue;
            if (!cache.has(secret)) {
                try {
                    const code = await App._generateTOTP(secret);
                    cache.set(secret, code || '');
                } catch {
                    cache.set(secret, '');
                }
            }
            const code = cache.get(secret);
            el.textContent = _formatTotp(code);
            el.dataset.totpCode = code || '';
        }
    }
}
```

- [ ] **Step 2: Kick the ticker after rendering**

In `loadProfiles`, find the line `_attachRowEvents(listEl);` (just after the `listEl.innerHTML = …` block). Add a call right after it:

```js
            _attachRowEvents(listEl);
            _totpTickerStart();
```

- [ ] **Step 3: Manual verification**

Reload the app. For any profile that has `totp_secret` set, the 2FA cell should:
- Show a 6-digit code formatted `XXX XXX` within ~1 s of the page rendering.
- Show a countdown `Xs` next to it that decrements every second from 30 → 1.
- Code changes when countdown hits 0/wraps to 30.

- [ ] **Step 4: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat: shared TOTP timer drives all visible 2FA codes"
```

---

## Task 9: JS — event wiring and Activity-sort cleanup

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js` — extend `_attachRowEvents`; remove obsolete pill handler.

- [ ] **Step 1: Add copy and group handlers in `_attachRowEvents`**

Locate `function _attachRowEvents(listEl) {` (around line 282). After the existing `listEl.querySelectorAll('.pm-row-check')` block and before the `// Click on group pill` block, add:

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

        // Inline group dropdown
        listEl.querySelectorAll('.pm-group-select').forEach(sel => {
            sel.addEventListener('change', (e) => { e.stopPropagation(); _onGroupChange(sel); });
            sel.addEventListener('click', (e) => e.stopPropagation());
            sel.addEventListener('mousedown', (e) => e.stopPropagation());
        });
```

- [ ] **Step 2: Remove the obsolete `.pm-group-pill` click handler**

Inside `_attachRowEvents`, find and delete this existing block (around lines 300–307):

```js
        // Click on group pill → filter by that group
        listEl.querySelectorAll('.pm-group-pill').forEach(pill => pill.addEventListener('click', (e) => {
            e.stopPropagation();
            const g = pill.dataset.group;
            _currentGroup = g;
            const sel = document.getElementById('pmGroupFilter');
            if (sel) sel.value = g;
            loadProfiles();
        }));
```

The pills no longer render in rows. (Keep the existing `pmGroupFilter` top-bar filter — that's separate.)

- [ ] **Step 3: Defensive reset for `_currentSort === 'updated'`**

Find the sort block (lines 150–170) where `_currentSort.column === 'updated'` is referenced. Just before the `profiles.sort(...)` call, add a guard so an old saved sort doesn't fail silently. Insert at the top of the `if (_currentSort.column) {` block:

```js
            if (_currentSort.column === 'updated') {
                // Activity column was removed in the 2026-05-23 redesign — fall back to default order
                _currentSort.column = null;
            }
```

This sits inside the `if (_currentSort.column) {` block — the inner check resets the column and the subsequent sort logic becomes a no-op for that case.

- [ ] **Step 4: Manual verification**

Reload the app. Check:
- Click the copy button next to an email → toast "Email copied ✓"; paste somewhere → email text appears.
- Click the password copy button → toast "Password copied ✓"; paste → plaintext password.
- Click the 2FA copy button → toast "2FA copied ✓"; paste → 6-digit code (no space).
- Click the group dropdown on a row → the list of existing groups appears with the current one selected. Pick a different group → no row blink, the dropdown sits on the new group, a backend call fires, no toast (success path). Reload the page → the new group sticks.
- Pick `+ New group…` → prompt appears; type a name → dropdown shows it as selected, backend persists it, refreshing the page still shows it.
- Top-bar group filter still works (separate widget — unchanged).

- [ ] **Step 5: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat: wire copy/group handlers, drop group-pill handler, guard old sort"
```

---

## Task 10: Final integration check and cleanup

- [ ] **Step 1: Verify Activity column has no leftover references**

```bash
grep -n "pm-col-updated\|pm-act-tag\|data-sort=\"updated\"" electron-app/renderer/index.html electron-app/renderer/styles.css electron-app/renderer/modules/profiles.js
```

Expected: only matches inside `styles.css` for `.pm-act-tag` rules (leave those — other parts of the app may use the class) and the guard added in Task 9 Step 3. No matches in `index.html`. In `profiles.js`, the only reference should be the guard. If anything else turns up, remove it.

- [ ] **Step 2: Full UI smoke run**

1. Restart the backend.
2. Reload the renderer (Ctrl+R inside the app, or restart Electron).
3. Visit Profile Manager. Confirm:
   - Header shows the 6 columns including Credentials and Proxy / 2FA. No Activity column.
   - At least one row with email, password, and `totp_secret` shows: name, email + copy, masked password + copy, country (or "No proxy"), live 2FA + countdown + copy, status badge, group dropdown, action buttons.
   - 2FA countdown ticks down each second; code rotates at the 30-s boundary.
   - Group dropdown change is instant (no blink) and persists across reloads.
   - Top-bar group filter still works.
   - Status filter pills (`All / Logged In / …`) still work.
   - Status, Name, and Group sort headers still work.
   - Search, Launch, Edit, Delete, Re-login, More menu all still work.

- [ ] **Step 3: Sync to main directory (only if working in a worktree)**

Per `MEMORY.md` workflow, if this work was done in a worktree under `.claude/worktrees/`, copy the modified files to `E:\NST Anty Android\` after committing in the worktree:

```bash
cp electron-app/backend/server.py "E:/NST Anty Android/electron-app/backend/server.py"
cp electron-app/renderer/index.html "E:/NST Anty Android/electron-app/renderer/index.html"
cp electron-app/renderer/styles.css "E:/NST Anty Android/electron-app/renderer/styles.css"
cp electron-app/renderer/modules/profiles.js "E:/NST Anty Android/electron-app/renderer/modules/profiles.js"
```

If working directly in `E:\NST Anty Android\`, skip this step.

- [ ] **Step 4: Final commit (if anything was cleaned in Step 1)**

```bash
git add -A
git diff --cached --stat
git commit -m "chore: drop leftover Activity column references" || echo "nothing to clean"
```
