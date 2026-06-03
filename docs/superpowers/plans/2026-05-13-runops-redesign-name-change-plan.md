# Run Ops Redesign + Name Change Operation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Electron Run Ops modal as a three-column tabbed layout and wire Op 8 (Name Change) end-to-end so successful runs save the new First/Last Name into the profile's Credentials tab.

**Architecture:** UI lives in `electron-app/renderer/` (HTML/CSS/vanilla JS module). Backend operation already exists (`step2/operations/name_change.py` and `step2/runner.py:392-401`); the work is (1) HTML for a new Run Ops layout, (2) JS wiring for tabs + live name-mapping preview + First/Last Name field load/save, (3) backend tweaks to persist names + fix line-to-profile distribution from round-robin to 1:1.

**Tech Stack:** Vanilla JS (no framework), HTML, CSS, Python 3 backend (`shared/profile_manager.py`), Flask routes already in place.

**Spec:** `docs/superpowers/specs/2026-05-13-runops-redesign-name-change-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `shared/profile_manager.py` | Schema field + allowed-fields whitelist + Op 8 write-back + 1:1 distribution fix + fallback to stored name | Modify |
| `electron-app/renderer/index.html` | Add First/Last Name fields in Credentials tab; replace Run Ops modal body with new 3-column tabbed layout | Modify |
| `electron-app/renderer/styles.css` | Tab rail, op chip, mapping table styles | Modify |
| `electron-app/renderer/modules/profiles.js` | First/Last Name load/save, new tab switching, live op summary chips, live name mapping preview, updated Op 8 submit validation | Modify |

No new files. Tests are smoke scripts (project has no pytest harness).

---

## Task 1: Add `first_name` / `last_name` to profile schema and allowed-fields

**Files:**
- Modify: `shared/profile_manager.py:778-795` (schema in `create_profile`)
- Modify: `shared/profile_manager.py:818-823` (allowed-fields set in `update_profile`)

- [ ] **Step 1: Add the two fields to the new-profile schema**

In `shared/profile_manager.py`, find the `profile = { ... }` dict starting around line 778 inside `create_profile()`. Add `'first_name': '',` and `'last_name': '',` right after `'recovery_phone': recovery_phone or '',` (line 793). Final block:

```python
        profile = {
            'id': profile_id,
            'name': name,
            'email': email,
            'status': 'not_logged_in',
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'last_used': None,
            'profile_dir': profile_dir,
            'proxy': proxy,
            'notes': notes,
            'fingerprint': fingerprint,
            'password': password or '',
            'totp_secret': totp_secret or '',
            'backup_codes': backup_codes or [],
            'recovery_email': recovery_email or '',
            'recovery_phone': recovery_phone or '',
            'first_name': '',
            'last_name': '',
            'engine': engine or 'nexus',
        }
```

- [ ] **Step 2: Add the two fields to the `update_profile` allowed-fields set**

In `shared/profile_manager.py:818-823`, extend the `allowed` set:

```python
                allowed = {'name', 'email', 'proxy', 'notes', 'status', 'fingerprint',
                           'password', 'totp_secret', 'backup_codes', 'group', 'groups',
                           'startup_urls', 'os_type', 'engine',
                           'recovery_email', 'recovery_phone',
                           'first_name', 'last_name',
                           'overview', 'hardware', 'advanced', 'fingerprint_config',
                           'last_used', 'address', 'bookmarks_text'}
```

- [ ] **Step 3: Smoke-verify `update_profile` accepts the new fields**

Run this from `E:\NST Anty Android`:

```powershell
python -c "import sys; sys.path.insert(0, r'E:\NST Anty Android'); from shared import profile_manager as pm; profs = pm._read_profiles(); pid = profs[0]['id'] if profs else None; print('pid=', pid); r = pm.update_profile(pid, first_name='__SMOKE__', last_name='__TEST__') if pid else None; print('updated.first_name=', r.get('first_name') if r else None, 'last_name=', r.get('last_name') if r else None); pm.update_profile(pid, first_name='', last_name='') if pid else None"
```

Expected output:
```
pid= <some uuid>
updated.first_name= __SMOKE__ last_name= __TEST__
```

If `first_name=None` or absent, the allowed-set edit didn't land. Fix and re-run.

- [ ] **Step 4: Commit**

```bash
git add shared/profile_manager.py
git commit -m "feat(profiles): add first_name/last_name fields to profile schema"
```

---

## Task 2: Op 8 success — write-back First/Last Name to profile

**Files:**
- Modify: `shared/profile_manager.py:3155-3160` (after the Op 6a write-back branch in `_run_operations_for_profile`)

- [ ] **Step 1: Add the Op 8 write-back branch**

In `shared/profile_manager.py`, find the chain of `elif op == '...' and result_str is True:` blocks inside `_run_operations_for_profile`. The last branch today is `op == '6a'` (around line 3155-3160). Add this branch immediately after it (before the `result_label = op_results.get(op, '')` line):

```python
                    elif op == '8' and result_str is True:
                        fn = account.get('First Name', '')
                        ln = account.get('Last Name', '')
                        if fn:
                            credentials_changed['first_name'] = fn
                        if ln:
                            credentials_changed['last_name'] = ln
```

The existing `update_profile(profile['id'], **credentials_changed)` call at line 3183 will persist these because Task 1 added them to the allowed-fields set.

- [ ] **Step 2: Commit**

```bash
git add shared/profile_manager.py
git commit -m "feat(ops): persist first/last name to profile after successful Op 8"
```

---

## Task 3: 1:1 in-order distribution + stored-name fallback

**Files:**
- Modify: `shared/profile_manager.py:2910-2918` (name-list distribution loop in `run_operations_on_profiles`)
- Modify: `shared/profile_manager.py:3059-3060` (account-builder fallback in `_run_operations_for_profile`)

- [ ] **Step 1: Replace round-robin distribution with 1:1 truncating**

In `shared/profile_manager.py:2910-2918`, replace the existing block:

```python
    # Distribute name list to profiles (round-robin) if provided
    if params and params.get('name_list'):
        name_lines = [ln.strip() for ln in params['name_list'].strip().split('\n') if ln.strip()]
        if name_lines:
            for i, p in enumerate(available):
                name = name_lines[i % len(name_lines)]
                parts = name.split(None, 1)
                p['_op_first_name'] = parts[0] if parts else ''
                p['_op_last_name'] = parts[1] if len(parts) > 1 else ''
```

with the truncating, in-order version:

```python
    # Distribute name list to profiles (in selected-profile order, 1:1).
    # If fewer names than profiles AND Op 8 is in this run, trim the profile
    # list so the whole batch only runs on the first N profiles. Other ops
    # included in the same run will share that trimmed list — users wanting
    # different scopes should split the runs.
    if params and params.get('name_list'):
        name_lines = [ln.strip() for ln in params['name_list'].strip().split('\n') if ln.strip()]
        if name_lines:
            n = min(len(name_lines), len(available))
            for i in range(n):
                name = name_lines[i]
                parts = name.split(None, 1)
                available[i]['_op_first_name'] = parts[0] if parts else ''
                available[i]['_op_last_name'] = parts[1] if len(parts) > 1 else ''
            op_codes = [op.strip() for op in (operations or '').split(',') if op.strip()]
            if '8' in op_codes:
                available = available[:n]
```

- [ ] **Step 2: Fall back to stored name when textarea is empty**

In `shared/profile_manager.py:3059-3060` inside `_run_operations_for_profile`, replace:

```python
        'First Name': profile.get('_op_first_name', params.get('first_name', '')),
        'Last Name': profile.get('_op_last_name', params.get('last_name', '')),
```

with:

```python
        'First Name': profile.get('_op_first_name') or params.get('first_name') or profile.get('first_name', ''),
        'Last Name':  profile.get('_op_last_name')  or params.get('last_name')  or profile.get('last_name',  ''),
```

This means: if the textarea supplied a name → use it; else if the Excel-style legacy `params['first_name']` was supplied → use that; else fall back to the profile's previously stored `first_name`.

- [ ] **Step 3: Smoke-verify the distribution math**

Run from `E:\NST Anty Android`:

```powershell
python -c "names=['Alice A','Bob B','Carol C']; profs=[{'id':f'p{i}'} for i in range(5)]; n=min(len(names),len(profs)); [profs[i].update({'_fn':names[i].split(None,1)[0],'_ln':names[i].split(None,1)[1] if ' ' in names[i] else ''}) for i in range(n)]; profs=profs[:n]; print('after trim:', [(p['id'],p.get('_fn'),p.get('_ln')) for p in profs])"
```

Expected:
```
after trim: [('p0', 'Alice', 'A'), ('p1', 'Bob', 'B'), ('p2', 'Carol', 'C')]
```

- [ ] **Step 4: Commit**

```bash
git add shared/profile_manager.py
git commit -m "fix(ops): 1:1 in-order name distribution; fall back to stored name"
```

---

## Task 4: Add First/Last Name fields to the Credentials tab

**Files:**
- Modify: `electron-app/renderer/index.html:840` (insert immediately after the Email field, before the Password row)

- [ ] **Step 1: Insert the Account Holder Name group**

In `electron-app/renderer/index.html`, find this line (around line 840):

```html
                            <div class="form-group"><label>Email</label><input type="text" id="pmEmail" placeholder="user@gmail.com"></div>
```

Insert immediately after it (above the Password/TOTP grid `<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">`):

```html
                            <div class="form-group" style="border:1px solid rgba(99,102,241,0.18);border-radius:6px;padding:8px 10px;margin-bottom:10px;">
                                <label style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:6px;">Account Holder Name</label>
                                <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                                    <div>
                                        <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px;">First Name</label>
                                        <input type="text" id="pmFirstName" placeholder="John">
                                    </div>
                                    <div>
                                        <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px;">Last Name</label>
                                        <input type="text" id="pmLastName" placeholder="Smith">
                                    </div>
                                </div>
                            </div>
```

- [ ] **Step 2: Manually open the app and verify the fields render**

Run `npm start` (or however the user normally starts the app) in `electron-app/`. Open Profile Manager → click any existing profile → switch to Credentials tab. Verify "Account Holder Name" group appears between Email and Password with two empty text inputs. Typing into them should be possible but values won't persist until Task 7.

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/index.html
git commit -m "feat(ui): add First Name / Last Name inputs in Credentials tab"
```

---

## Task 5: Replace Run Ops modal body with three-column tabbed layout

**Files:**
- Modify: `electron-app/renderer/index.html:2338-2462` (entire `<div id="runOpsModal">` block)

- [ ] **Step 1: Replace the entire Run Ops modal**

In `electron-app/renderer/index.html`, find `<div id="runOpsModal" class="pm-modal-overlay" style="display:none;">` at line 2338 and replace everything through the matching closing `</div>` at line 2462 with this block:

```html
    <div id="runOpsModal" class="pm-modal-overlay" style="display:none;">
        <div class="pm-modal" style="max-width:1200px;max-height:92vh;display:flex;flex-direction:column;">
            <!-- Header -->
            <div class="pm-modal-header">
                <h3><i class="fas fa-cogs" style="color:#6366f1;margin-right:8px;"></i> Run Operations</h3>
                <button class="pm-modal-close" id="runOpsModalClose">&times;</button>
            </div>

            <!-- Body: 3-column (tab rail | center | profiles) -->
            <div style="display:flex;flex:1;overflow:hidden;min-height:0;">

                <!-- LEFT: Tab rail -->
                <div id="runOpsTabRail" style="width:150px;border-right:1px solid var(--border);display:flex;flex-direction:column;padding:8px 0;background:rgba(0,0,0,0.08);">
                    <button class="runops-tab active" data-tab="language" type="button">
                        <i class="fas fa-language"></i>
                        <span>Language</span>
                        <span class="runops-tab-badge" data-badge="language" style="display:none;">0</span>
                    </button>
                    <button class="runops-tab" data-tab="security" type="button">
                        <i class="fas fa-shield-alt"></i>
                        <span>Security</span>
                        <span class="runops-tab-badge" data-badge="security" style="display:none;">0</span>
                    </button>
                    <button class="runops-tab" data-tab="reviews" type="button">
                        <i class="fas fa-star"></i>
                        <span>Reviews</span>
                        <span class="runops-tab-badge" data-badge="reviews" style="display:none;">0</span>
                    </button>
                    <button class="runops-tab" data-tab="identity" type="button">
                        <i class="fas fa-user"></i>
                        <span>Identity</span>
                        <span class="runops-tab-badge" data-badge="identity" style="display:none;">0</span>
                    </button>
                </div>

                <!-- CENTER: Active tab content -->
                <div style="flex:1;display:flex;flex-direction:column;overflow:hidden;">
                    <div style="flex:1;overflow-y:auto;padding:12px 16px;">

                        <!-- TAB: Language -->
                        <div class="runops-tab-panel active" data-panel="language">
                            <div style="display:flex;flex-direction:column;gap:4px;">
                                <label class="runops-op-row">
                                    <input type="checkbox" value="L1" class="runops-op" data-tab="language">
                                    <span>Op L1 — Change Language to English (US)</span>
                                </label>
                                <label class="runops-op-row">
                                    <input type="checkbox" value="L3" class="runops-op" data-tab="language">
                                    <span>Op L3 — Change Language to Français (France)</span>
                                </label>
                            </div>
                        </div>

                        <!-- TAB: Security -->
                        <div class="runops-tab-panel" data-panel="security" style="display:none;">
                            <div style="display:flex;flex-direction:column;gap:4px;">
                                <label class="runops-op-row">
                                    <input type="checkbox" value="2a" class="runops-op" data-tab="security">
                                    <span>Op 2a — Add Recovery Phone</span>
                                </label>
                                <label class="runops-op-row">
                                    <input type="checkbox" value="2b" class="runops-op" data-tab="security">
                                    <span>Op 2b — Remove Recovery Phone</span>
                                </label>
                                <label class="runops-op-row">
                                    <input type="checkbox" value="3a" class="runops-op" data-tab="security">
                                    <span>Op 3a — Add Recovery Email</span>
                                </label>
                                <label class="runops-op-row">
                                    <input type="checkbox" value="3b" class="runops-op" data-tab="security">
                                    <span>Op 3b — Remove Recovery Email</span>
                                </label>
                            </div>
                            <div id="runOpsParams_security" style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px;">
                                <div style="display:flex;flex-wrap:wrap;gap:8px;">
                                    <div id="runOpsParamRecoveryPhone" style="flex:1;min-width:200px;display:none;">
                                        <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px;">Recovery Phone</label>
                                        <input type="text" id="runOpsRecoveryPhone" placeholder="+1234567890" style="width:100%;background:#0f1629;border:1px solid rgba(99,102,241,0.3);border-radius:5px;padding:6px 8px;color:#e2e8f0;font-size:12px;">
                                    </div>
                                    <div id="runOpsParamRecoveryEmail" style="flex:1;min-width:200px;display:none;">
                                        <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px;">Recovery Email</label>
                                        <input type="text" id="runOpsRecoveryEmail" placeholder="recovery@example.com" style="width:100%;background:#0f1629;border:1px solid rgba(99,102,241,0.3);border-radius:5px;padding:6px 8px;color:#e2e8f0;font-size:12px;">
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- TAB: Reviews -->
                        <div class="runops-tab-panel" data-panel="reviews" style="display:none;">
                            <div style="display:flex;flex-direction:column;gap:4px;">
                                <label class="runops-op-row">
                                    <input type="checkbox" value="R2" class="runops-op" data-tab="reviews">
                                    <span>Op R2 — Delete Draft Reviews (not-posted)</span>
                                </label>
                            </div>
                        </div>

                        <!-- TAB: Identity -->
                        <div class="runops-tab-panel" data-panel="identity" style="display:none;">
                            <div style="display:flex;flex-direction:column;gap:4px;">
                                <label class="runops-op-row">
                                    <input type="checkbox" value="8" class="runops-op" data-tab="identity" id="runOpsOp8">
                                    <span>Op 8 — Change Display Name</span>
                                </label>
                                <div style="font-size:11px;color:#64748b;margin:0 0 4px 28px;">Changes First + Last name on the Google Account. Each profile gets one line from the list below.</div>
                            </div>

                            <div id="runOpsParamNames" style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px;display:none;">
                                <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                                    <label style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Names (one per line)</label>
                                    <span style="margin-left:auto;font-size:11px;color:#94a3b8;">Country:</span>
                                    <select id="runOpsNameCountry" style="background:#0f1629;border:1px solid rgba(99,102,241,0.3);border-radius:5px;padding:4px 6px;color:#e2e8f0;font-size:12px;">
                                        <option value="US">United States</option>
                                        <option value="FR">France</option>
                                        <option value="UK">United Kingdom</option>
                                        <option value="DE">Germany</option>
                                        <option value="ES">Spain</option>
                                        <option value="IN">India</option>
                                    </select>
                                </div>
                                <textarea id="runOpsNameList" rows="6" placeholder="John Smith&#10;Maria Garcia&#10;Ahmed Khan" style="width:100%;background:#0f1629;border:1px solid rgba(99,102,241,0.3);border-radius:5px;padding:8px;color:#e2e8f0;font-family:'JetBrains Mono',monospace;font-size:12px;resize:vertical;"></textarea>
                                <div style="display:flex;align-items:center;gap:10px;margin-top:6px;">
                                    <button class="btn btn-secondary btn-sm" id="runOpsLoadNamesBtn" type="button" style="font-size:11px;padding:4px 10px;"><i class="fas fa-folder-open"></i> Load from .txt</button>
                                    <input type="file" id="runOpsNameFileInput" accept=".txt" style="display:none;">
                                    <span id="runOpsNameCounter" style="font-size:11px;color:#94a3b8;">0 names · 0 profiles</span>
                                </div>
                                <div id="runOpsNameMismatch" style="display:none;margin-top:6px;padding:6px 10px;background:rgba(245,158,11,0.12);border:1px solid rgba(245,158,11,0.35);border-radius:5px;font-size:11px;color:#fbbf24;"></div>
                                <details id="runOpsNameMappingDetails" style="margin-top:10px;" open>
                                    <summary style="cursor:pointer;font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Mapping preview</summary>
                                    <div id="runOpsNameMapping" style="margin-top:6px;background:#0f1629;border:1px solid var(--border);border-radius:5px;max-height:200px;overflow-y:auto;font-family:'JetBrains Mono',monospace;font-size:11px;"></div>
                                </details>
                            </div>
                        </div>

                    </div>
                </div>

                <!-- RIGHT: Profile selector -->
                <div style="width:310px;border-left:1px solid var(--border);display:flex;flex-direction:column;">
                    <div style="padding:8px 12px;border-bottom:1px solid var(--border);font-size:12px;color:#a5b4fc;font-weight:600;">
                        Profiles (<span id="runOpsSelectedCount">0</span> / <span id="runOpsTotalCount">0</span>)
                    </div>
                    <div style="padding:6px 8px;border-bottom:1px solid var(--border);display:flex;gap:6px;">
                        <input id="runOpsSearchInput" class="modal-search-input" placeholder="Search profiles..." style="flex:1;">
                        <select id="runOpsGroupFilter" style="background:#0f1629;border:1px solid var(--border);border-radius:5px;padding:4px;color:#e2e8f0;font-size:11px;max-width:100px;">
                            <option value="">All Groups</option>
                        </select>
                    </div>
                    <div style="padding:5px 8px;border-bottom:1px solid var(--border);display:flex;gap:6px;align-items:center;">
                        <button class="btn btn-sm" id="runOpsSelectAll" style="font-size:10px;padding:2px 8px;">All</button>
                        <button class="btn btn-sm" id="runOpsDeselectAll" style="font-size:10px;padding:2px 8px;">None</button>
                    </div>
                    <div id="runOpsProfileList" style="flex:1;overflow-y:auto;padding:4px;"></div>
                </div>
            </div>

            <!-- Footer: op summary + workers + run -->
            <div style="padding:8px 14px;border-top:1px solid var(--border);background:rgba(0,0,0,0.06);display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
                <div style="display:flex;align-items:center;gap:6px;flex:1;min-width:200px;">
                    <span style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Selected:</span>
                    <div id="runOpsOpSummary" style="display:flex;gap:4px;flex-wrap:wrap;align-items:center;">
                        <span style="font-size:11px;color:#64748b;font-style:italic;">no operations</span>
                    </div>
                </div>
                <label style="font-size:11px;color:#94a3b8;">Workers:</label>
                <input type="number" id="runOpsWorkers" value="5" min="1" max="100" style="background:#0f1629;border:1px solid rgba(99,102,241,0.3);border-radius:5px;padding:4px 6px;color:#e2e8f0;font-size:12px;width:60px;">
                <label style="font-size:11px;color:#94a3b8;">Stagger:</label>
                <input type="number" id="runOpsStagger" value="3" min="0" max="30" style="background:#0f1629;border:1px solid rgba(99,102,241,0.3);border-radius:5px;padding:4px 6px;color:#e2e8f0;font-size:12px;width:50px;" title="Seconds between worker launches">
                <span style="font-size:10px;color:#64748b;">sec</span>
            </div>
            <div class="pm-modal-footer">
                <button class="btn btn-secondary" id="runOpsModalCancelBtn">Cancel</button>
                <button class="btn btn-primary" id="runOpsModalStartBtn"><i class="fas fa-play"></i> Run Operations</button>
            </div>
        </div>
    </div>
```

- [ ] **Step 2: Open the app and visually verify the layout renders**

Start the app. Click "Run Ops" toolbar button (selector `#profileRunOpsBtn`). The modal should open with:
- Left rail: 4 vertical tabs (Language active by default).
- Center: just the two Language ops visible.
- Right: profile selector with search/group/All/None and the list.
- Footer: "Selected: no operations", Workers `5`, Stagger `3 sec`, Cancel + Run.

Clicking the other tabs in the rail won't switch yet — that's wired in Task 8. Op checkboxes won't update the footer chips yet — that's Task 9. Move on; visual structure is the only thing to confirm here.

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/index.html
git commit -m "feat(ui): redesign Run Ops modal as 3-column tabbed layout with Identity tab"
```

---

## Task 6: CSS for tab rail, op rows, chips, mapping table

**Files:**
- Modify: `electron-app/renderer/styles.css` (append at end of file, or near the existing `.runops-cat`/`.runops-step-tab` block around line 2429-2435)

- [ ] **Step 1: Add the new styles**

Append to `electron-app/renderer/styles.css`:

```css
/* ─── Run Ops modal: tab rail ─────────────────────────────────────── */
.runops-tab {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: #94a3b8;
    cursor: pointer;
    font-size: 12px;
    text-align: left;
    transition: background .15s, color .15s, border-color .15s;
    position: relative;
}
.runops-tab i {
    width: 16px;
    text-align: center;
}
.runops-tab:hover {
    background: rgba(99, 102, 241, 0.05);
    color: #c4b5fd;
}
.runops-tab.active {
    background: rgba(99, 102, 241, 0.10);
    color: #a5b4fc;
    border-left-color: var(--primary);
}
.runops-tab-badge {
    margin-left: auto;
    background: var(--primary);
    color: #fff;
    border-radius: 10px;
    padding: 1px 7px;
    font-size: 10px;
    font-weight: 700;
    min-width: 18px;
    text-align: center;
}

/* ─── Run Ops modal: op rows ──────────────────────────────────────── */
.runops-op-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    color: #e2e8f0;
    transition: background .15s;
}
.runops-op-row:hover {
    background: rgba(99, 102, 241, 0.10);
}
.runops-op-row input[type="checkbox"] {
    accent-color: #6366f1;
    width: 14px;
    height: 14px;
}

/* ─── Run Ops modal: op summary chips (footer) ────────────────────── */
.runops-op-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: rgba(99, 102, 241, 0.18);
    border: 1px solid rgba(99, 102, 241, 0.4);
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
    color: #a5b4fc;
    font-family: 'JetBrains Mono', monospace;
}

/* ─── Run Ops modal: name mapping table ───────────────────────────── */
#runOpsNameMapping .runops-map-row {
    display: grid;
    grid-template-columns: 24px 1fr 12px 1fr;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
#runOpsNameMapping .runops-map-row:last-child {
    border-bottom: none;
}
#runOpsNameMapping .runops-map-row .idx {
    color: #64748b;
    text-align: right;
}
#runOpsNameMapping .runops-map-row .email {
    color: #cbd5e1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
#runOpsNameMapping .runops-map-row .arrow {
    color: #475569;
}
#runOpsNameMapping .runops-map-row .name {
    color: #a5b4fc;
}
#runOpsNameMapping .runops-map-row.skip .name {
    color: #f87171;
    font-style: italic;
}
```

- [ ] **Step 2: Reload the app and verify hover/active states**

Restart the app (or use Ctrl+R / Cmd+R in the Electron renderer). Open Run Ops. Hover over the inactive tabs — they should light up purple. The active "Language" tab should have a primary-color left border. Hover over an op checkbox row — background should brighten.

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/styles.css
git commit -m "style(runops): tab rail, op rows, chips, mapping table styles"
```

---

## Task 7: Wire First/Last Name load/save in profile edit popup

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:760-770` (Credentials tab load block)
- Modify: `electron-app/renderer/modules/profiles.js:798-799` (form reset)
- Modify: `electron-app/renderer/modules/profiles.js:1048-1049` (save body)

- [ ] **Step 1: Load on profile open**

In `electron-app/renderer/modules/profiles.js`, find the Credentials-tab load block around line 760-770. After the `_setVal('pmRecoveryPhone', p.recovery_phone || '');` line (line 768), insert:

```javascript
            _setVal('pmFirstName', p.first_name || '');
            _setVal('pmLastName', p.last_name || '');
```

- [ ] **Step 2: Clear on form reset**

Find the form-reset block around line 798-799 (currently `_setVal('pmRecoveryEmail', ''); _setVal('pmRecoveryPhone', '');`). After that line, add:

```javascript
        _setVal('pmFirstName', ''); _setVal('pmLastName', '');
```

- [ ] **Step 3: Include in save payload**

Find the `body = { ... }` object in `saveProfile()` around line 1038-1063. After the line `recovery_phone: _val('pmRecoveryPhone').trim(),` (line 1049), insert:

```javascript
            first_name: _val('pmFirstName').trim(),
            last_name: _val('pmLastName').trim(),
```

- [ ] **Step 4: Manual round-trip verification**

Restart the app. Open any profile → Credentials → type "Test" / "User" in First/Last Name → Save. Reopen the same profile → verify both fields show "Test" / "User". Clear them → Save → reopen → both empty.

- [ ] **Step 5: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(ui): load/save First Name + Last Name on profile edit"
```

---

## Task 8: Wire the vertical tab rail

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:1734-1795` (`_setupRunOpsModal`)

- [ ] **Step 1: Replace the old tab-switch handler with the new rail handler**

In `electron-app/renderer/modules/profiles.js`, find `_setupRunOpsModal` (around line 1734). Locate the existing block that wires the old `.runops-step-tab` buttons (around line 1744-1750 — it loops `panel = document.getElementById('runOpsStep' + tab.dataset.step)`). Replace that loop with the new rail wiring:

```javascript
        // Vertical tab rail — toggle panel visibility
        document.querySelectorAll('#runOpsTabRail .runops-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const target = tab.dataset.tab;
                document.querySelectorAll('#runOpsTabRail .runops-tab').forEach(t => {
                    t.classList.toggle('active', t === tab);
                });
                document.querySelectorAll('.runops-tab-panel').forEach(panel => {
                    const match = panel.dataset.panel === target;
                    panel.classList.toggle('active', match);
                    panel.style.display = match ? '' : 'none';
                });
            });
        });
```

If nothing else in the `_setupRunOpsModal` function references `.runops-step-tab` or `#runOpsStep1`/`#runOpsStep2`/`#runOpsStep3`, that completes Step 1. (If a reference remains, delete it — the old step1/2/3 panels no longer exist in the DOM.)

- [ ] **Step 2: Manual verification**

Restart the app. Open Run Ops. Click each of the 4 tabs in the rail. The center pane should show only that tab's ops. The active-tab styling (left border + background) should follow your clicks.

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(ui): wire vertical tab rail in Run Ops modal"
```

---

## Task 9: Live op summary chips + tab badges + params visibility

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:1721-1732` (`_updateRunOpsParams`)

- [ ] **Step 1: Rewrite `_updateRunOpsParams` to also update chips + badges**

In `electron-app/renderer/modules/profiles.js`, find `_updateRunOpsParams` around line 1721. Replace the entire function with:

```javascript
    function _updateRunOpsParams() {
        const checked = document.querySelectorAll('.runops-op:checked');
        const ops = new Set([...checked].map(cb => cb.value));

        // Param visibility (security tab + identity tab)
        const show = (id, on) => { const el = document.getElementById(id); if (el) el.style.display = on ? '' : 'none'; };
        show('runOpsParamRecoveryPhone', ops.has('2a'));
        show('runOpsParamRecoveryEmail', ops.has('3a'));
        show('runOpsParamNames', ops.has('8'));

        // Footer chip summary
        const summary = document.getElementById('runOpsOpSummary');
        if (summary) {
            if (!ops.size) {
                summary.innerHTML = '<span style="font-size:11px;color:#64748b;font-style:italic;">no operations</span>';
            } else {
                summary.innerHTML = [...ops].map(op => `<span class="runops-op-chip">${op}</span>`).join('');
            }
        }

        // Per-tab badges
        const tabCounts = { language: 0, security: 0, reviews: 0, identity: 0 };
        checked.forEach(cb => {
            const t = cb.dataset.tab;
            if (t in tabCounts) tabCounts[t]++;
        });
        Object.entries(tabCounts).forEach(([t, n]) => {
            const badge = document.querySelector(`#runOpsTabRail .runops-tab-badge[data-badge="${t}"]`);
            if (badge) {
                badge.style.display = n > 0 ? '' : 'none';
                badge.textContent = String(n);
            }
        });

        // Identity tab — also refresh the mapping preview when toggled
        if (typeof _updateNameMapping === 'function') _updateNameMapping();
    }
```

- [ ] **Step 2: Manual verification**

Restart the app. Open Run Ops. Check Op L1 — footer should show `[L1]` chip and Language tab should show badge `1`. Switch to Security tab, check 2a and 3a — Recovery Phone + Recovery Email param inputs appear; footer chips become `[L1] [2a] [3a]`; Security badge shows `2`. Uncheck them all — chips revert to "no operations".

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(ui): live op summary chips + per-tab badges in Run Ops footer"
```

---

## Task 10: Live name mapping preview

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js` — add new function `_updateNameMapping`, wire it into existing event listeners

- [ ] **Step 1: Add the `_updateNameMapping` function**

In `electron-app/renderer/modules/profiles.js`, add this new function inside the IIFE near the other Run Ops helpers (e.g. right after `_updateRunOpsCount` around line 1719):

```javascript
    function _updateNameMapping() {
        const op8 = document.getElementById('runOpsOp8');
        if (!op8 || !op8.checked) return;

        const ta = document.getElementById('runOpsNameList');
        const counter = document.getElementById('runOpsNameCounter');
        const mismatch = document.getElementById('runOpsNameMismatch');
        const table = document.getElementById('runOpsNameMapping');
        if (!ta || !counter || !mismatch || !table) return;

        const names = ta.value.split('\n').map(l => l.trim()).filter(Boolean);
        const filtered = _filteredRunOpsProfiles();
        const selected = filtered.filter(p => _runOpsChecked.has(p.id));
        const n = Math.min(names.length, selected.length);

        counter.textContent = `${names.length} name${names.length === 1 ? '' : 's'} · ${selected.length} profile${selected.length === 1 ? '' : 's'}`;

        if (names.length === 0 || selected.length === 0) {
            mismatch.style.display = 'none';
            table.innerHTML = '<div style="padding:8px;color:#64748b;font-style:italic;">Add names and select profiles to preview the mapping.</div>';
            return;
        }

        if (names.length < selected.length) {
            const otherOps = [...document.querySelectorAll('.runops-op:checked')].map(cb => cb.value).filter(v => v !== '8');
            const extra = otherOps.length
                ? ` (other ops in this run — ${otherOps.join(', ')} — will also be limited to those ${n} profiles)`
                : '';
            mismatch.style.display = '';
            mismatch.textContent = `Will run on ${n}/${selected.length} — last ${selected.length - n} profile${selected.length - n === 1 ? '' : 's'} skipped${extra}.`;
        } else if (names.length > selected.length) {
            mismatch.style.display = '';
            mismatch.textContent = `${names.length - selected.length} extra name${names.length - selected.length === 1 ? '' : 's'} unused (only ${selected.length} profile${selected.length === 1 ? '' : 's'} selected).`;
        } else {
            mismatch.style.display = 'none';
        }

        const rows = [];
        for (let i = 0; i < selected.length; i++) {
            const p = selected[i];
            const email = p.email || p.name || p.id;
            if (i < n) {
                const name = names[i].replace(/</g, '&lt;');
                rows.push(`<div class="runops-map-row"><span class="idx">${i + 1}.</span><span class="email">${email}</span><span class="arrow">→</span><span class="name">${name}</span></div>`);
            } else {
                rows.push(`<div class="runops-map-row skip"><span class="idx">${i + 1}.</span><span class="email">${email}</span><span class="arrow">→</span><span class="name">SKIP</span></div>`);
            }
        }
        table.innerHTML = rows.join('');
    }
```

- [ ] **Step 2: Trigger `_updateNameMapping` from existing event paths**

Several existing listeners change the inputs that mapping depends on. Hook into them:

(a) In `_setupRunOpsModal`, find the existing block that wires op checkbox change to `_updateRunOpsParams` (around line 1751-1753, `cb.addEventListener('change', _updateRunOpsParams)`). Leave this — Task 9 already calls `_updateNameMapping` from inside `_updateRunOpsParams`. No change.

(b) Find the search input listener around line 1757-1759. Replace its callback to also call `_updateNameMapping`:

```javascript
        const searchEl = document.getElementById('runOpsSearchInput');
        if (searchEl) searchEl.addEventListener('input', () => {
            _runOpsSearch = searchEl.value; _runOpsPage = 1; _renderRunOpsProfiles(); _updateNameMapping();
        });
```

(c) Find the group filter listener around line 1762-1765. Same treatment:

```javascript
        const gfEl = document.getElementById('runOpsGroupFilter');
        if (gfEl) gfEl.addEventListener('change', () => {
            _runOpsGroupFilter = gfEl.value; _runOpsPage = 1; _renderRunOpsProfiles(); _updateNameMapping();
        });
```

(d) Find the textarea — add a listener inside `_setupRunOpsModal` (append it near the other input wirings, e.g. after the file-input handler around line 1792):

```javascript
        const nameListTa = document.getElementById('runOpsNameList');
        if (nameListTa) nameListTa.addEventListener('input', _updateNameMapping);
```

(e) In `_renderRunOpsProfiles` (around line 1700-1710), the inner profile checkbox handler currently calls `_updateRunOpsCount()`. Add `_updateNameMapping()` immediately after it.

(f) In the `runOpsSelectAll` and `runOpsDeselectAll` button handlers (around line 1768-1774), after `_updateRunOpsCount();` add `_updateNameMapping();`.

- [ ] **Step 3: Manual verification**

Restart the app. Open Run Ops → Identity tab → check Op 8 → the Names panel appears. Type 3 names. Select 5 profiles in the right rail. Verify:
- Counter shows `3 names · 5 profiles`.
- Yellow warning: `Will run on 3/5 — last 2 profiles skipped.`
- Mapping table shows 5 rows, last 2 red and labelled `SKIP`.

Add a 4th name → warning updates to "1 profile skipped". Add 5th → warning disappears. Add 6th → warning becomes "1 extra name unused". Deselect 2 profiles → counter + table update live.

- [ ] **Step 4: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(ui): live name-mapping preview with counter, mismatch warning, table"
```

---

## Task 11: Submit-time validation for Op 8

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:1797-1842` (`_submitRunOps`)

- [ ] **Step 1: Add the empty-names guard**

In `electron-app/renderer/modules/profiles.js`, find `_submitRunOps` (line 1797). Locate the existing validation block at line 1820 (the password check). Add a new check immediately after it, before the `try { ... }` (line 1822):

```javascript
        if (ops.includes('8')) {
            const nl = (_val('runOpsNameList') || '').trim();
            // Check at least one source has a name: textarea OR every selected profile has stored first_name
            if (!nl) {
                const allHaveStoredName = [..._runOpsChecked].every(id => {
                    const p = _runOpsProfiles.find(x => x.id === id);
                    return p && (p.first_name || '').trim();
                });
                if (!allHaveStoredName) {
                    App.toast('Op 8 needs at least one name (textarea is empty and some selected profiles have no stored First Name)', 'warn');
                    return;
                }
            }
        }
```

- [ ] **Step 2: Manual verification**

Restart the app. Open Run Ops → Identity → check Op 8 → leave textarea empty → select a profile that has no stored First Name in its Credentials tab → click Run. The toast warning should fire and the run should not start.

Now type a name in the textarea → Run should proceed (or, if no name is in the textarea but every selected profile does have a stored First Name, Run should also proceed).

- [ ] **Step 3: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(ui): validate Op 8 — block run if no name source available"
```

---

## Task 12: End-to-end manual verification + cleanup

**Files:** none — verification only.

- [ ] **Step 1: Full Op 8 happy path**

1. Restart the app fresh. Open Profile Manager → pick 2 profiles whose Gmail account you can actually log in to (or use throw-away test accounts).
2. Open their Credentials tabs in turn and confirm First/Last Name are empty.
3. Click Run Ops. Identity tab → Op 8. Type 2 names like `Alpha One` and `Beta Two`. Verify mapping preview shows `profile1 → Alpha One`, `profile2 → Beta Two`.
4. Workers: `2`, Stagger: `1`. Click Run.
5. Watch the ops progress complete.
6. Open profile 1's edit popup → Credentials tab → verify First Name = `Alpha`, Last Name = `One`. Same check for profile 2 (`Beta` / `Two`).
7. Bonus: open the actual Google Account page in the live browser for one of these profiles — confirm the display name was actually changed.

- [ ] **Step 2: Re-run with empty textarea (fallback path)**

1. Same 2 profiles. Open Run Ops → Identity → Op 8 → leave textarea empty.
2. The validation toast from Task 11 should NOT fire (both profiles now have stored First Names from Step 1).
3. Click Run. The runner should use `Alpha One` and `Beta Two` from the profiles' stored values.
4. Verify in profile JSON (`<resources>/profiles/profiles.json` or wherever `_read_profiles` reads from) that the names are unchanged after the run.

- [ ] **Step 3: Mismatch path (skip extras)**

1. Select 3 profiles. Type 2 names. Verify warning + table show `1 skipped`.
2. Run. Verify only the first 2 profiles in the right-panel order actually had Op 8 attempted (check the ops report or per-profile op_status).

- [ ] **Step 4: Mixed-ops path**

1. Select 3 profiles. Check Op 2a (Add Recovery Phone) + Op 8. Type only 2 names.
2. Verify the warning text now says other ops (`2a`) will also be limited to the 2 profiles.
3. Run. Verify both Op 2a AND Op 8 ran on the first 2 profiles only.

- [ ] **Step 5: Final sanity — no regressions on Language/Security/Reviews tabs**

1. Open Run Ops → Language → check L1. Footer chip `[L1]`. Run. Verify behavior matches pre-redesign.
2. Same for Security 2a (need recovery phone param) and Reviews R2.

- [ ] **Step 6: Final commit (only if any small fixes were made during verification)**

```bash
git status
# If anything changed, commit it; otherwise skip.
```

---

## Notes for the implementing engineer

- **Coding style**: vanilla JS module pattern, no build step. Stick to the existing `_underscorePrefixed` private-function convention inside the IIFE in `profiles.js`.
- **No build / no transpile**: the Electron renderer loads `index.html` directly. Save → reload (Ctrl+R) is the loop.
- **Backend changes** are picked up only when the Python backend is restarted. The Electron app launches `electron-app/backend/server.py` as a subprocess — restart the whole app to reload backend changes.
- **profiles.json schema migration**: existing profiles without `first_name`/`last_name` will simply return `undefined` from `p.first_name`; the `|| ''` fallbacks handle it. No migration script needed.
- **Op order assumption**: the right-panel order is `_filteredRunOpsProfiles()` (post-search, post-group-filter, all pages). Backend trims `available[:n]` from the same list because `profile_ids` is sent in that order from the frontend.
