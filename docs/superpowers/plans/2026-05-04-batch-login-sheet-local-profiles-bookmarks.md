# Batch Login Sheet Integration, Local Profile Fallback & Custom Bookmarks

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Google Sheet support for batch login (mirroring live-check pattern), make profile creation silently succeed when NST hits its limit by saving locally, and add custom bookmark management for all profiles.

**Architecture:** Three independent features touching the same file set (server.py, profiles.js, index.html, profile_manager.py, nexus_profile_manager.py). Each feature modifies different sections so they can be developed sequentially without conflicts.

**Tech Stack:** Python (Flask backend), JavaScript (vanilla frontend), Google Sheets API, Chrome Bookmarks JSON format.

---

## File Map

| File | Changes |
|------|---------|
| `electron-app/renderer/index.html` | Batch login modal: add Excel/Sheet source tabs, sheet picker, tab selector. Profile modal: add bookmarks textarea in overview tab. |
| `electron-app/renderer/modules/profiles.js` | Batch login: sheet source toggle, sheet list, tab picker, preview, startBatchLogin sheet branch. Profile modal: bookmark load/save. Progress polling: add `batch-login` sheet write-back status. |
| `electron-app/backend/server.py` | New endpoints: `/api/sheets/<id>/preview-batch-login` for account preview. Modify `/api/profiles/batch-login` to accept `sheet_id`+`tabs`. Fix `napi_create_profile` to return 201 on NST error. |
| `shared/profile_manager.py` | Add `batch_login_from_sheet()` that reads accounts from sheet tabs, runs login, writes Status column back. |
| `shared/sheets_integration.py` | Add `read_accounts_from_tabs()` to batch-read Email+Password columns from multiple tabs. Add `batch_update_column()` generic helper. |
| `shared/nexus_profile_manager.py` | Fix `create_profile()` to NOT set `_nst_create_error` when local fallback works. Add `bookmarks` field to profile schema. Add `_write_chrome_bookmarks()` helper. |

---

## Task 1: Google Sheet Source for Batch Login — Backend

**Files:**
- Modify: `shared/sheets_integration.py` (add `read_accounts_from_tabs`)
- Modify: `shared/profile_manager.py:1055-1144` (add `batch_login_from_sheet`, modify `_batch_login_worker` to write back status)
- Modify: `electron-app/backend/server.py:2778-2812` (add sheet preview + modify batch-login endpoint)

### Step-by-step:

- [ ] **Step 1: Add `read_accounts_from_tabs()` to sheets_integration.py**

Add after the `batch_count_links_by_header` function (around line 783). This function reads Email + Password columns from selected sheet tabs and returns account dicts.

```python
def read_accounts_from_tabs(resources_path, spreadsheet_id: str,
                            tab_names: list) -> dict:
    """Read Email + Password columns from multiple tabs.

    Returns {success, tabs: {tab_name: {accounts: [{email, password, row, ...}], ...}}}
    """
    s = _sheets(resources_path)
    if not s:
        return {'success': False, 'message': _why_no_service()}

    # batchGet all tabs at once
    ranges = [_quote_tab(t) for t in tab_names]
    try:
        res = s.spreadsheets().values().batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=ranges,
            valueRenderOption='UNFORMATTED_VALUE',
        ).execute()
    except Exception as e:
        return {'success': False, 'message': f'Batch read failed: {_format_error(e)}'}

    value_ranges = res.get('valueRanges', [])
    tabs_out = {}

    for vr in value_ranges:
        rng = vr.get('range', '')
        # Extract tab name from range like "'Tab Name'!A1:Z1000"
        tab_name = rng.split('!')[0].strip("'")
        rows = vr.get('values') or []

        # Find header row (row with most non-empty cells)
        if not rows:
            tabs_out[tab_name] = {'success': False, 'message': 'Empty tab'}
            continue

        h_row_idx = max(range(len(rows)), key=lambda i: sum(1 for c in (rows[i] or []) if c))
        headers = [str(c or '').strip().lower() for c in (rows[h_row_idx] or [])]
        headers_orig = [str(c or '').strip() for c in (rows[h_row_idx] or [])]

        # Find required columns
        email_col = None
        password_col = None
        for ci, h in enumerate(headers):
            if h == 'email':
                email_col = ci
            elif h == 'password':
                password_col = ci

        if email_col is None or password_col is None:
            tabs_out[tab_name] = {
                'success': False,
                'message': f"Missing columns: {', '.join(c for c, found in [('Email', email_col), ('Password', password_col)] if found is None)}",
                'available_headers': [h for h in headers_orig if h],
            }
            continue

        # Find optional columns
        col_map = {}
        for ci, h in enumerate(headers):
            if h == 'totp secret':
                col_map['totp_secret'] = ci
            elif h == 'proxy':
                col_map['proxy'] = ci
            elif h == 'address':
                col_map['address'] = ci
            elif h == 'status':
                col_map['status'] = ci
            elif h.startswith('backup code'):
                col_map.setdefault('backup_codes', []).append((ci, h))

        accounts = []
        for ri in range(h_row_idx + 1, len(rows)):
            row = rows[ri]
            email = str(row[email_col] if email_col < len(row) else '').strip()
            password = str(row[password_col] if password_col < len(row) else '').strip()
            if not email or not password or email.lower() == 'nan' or password.lower() == 'nan':
                continue

            acc = {
                'email': email,
                'password': password,
                'row': ri + 1,  # 1-based for sheet write-back
            }

            # Optional fields
            if 'totp_secret' in col_map:
                ci = col_map['totp_secret']
                v = str(row[ci] if ci < len(row) else '').strip()
                acc['totp_secret'] = v if v and v.lower() != 'nan' else ''
            else:
                acc['totp_secret'] = ''

            if 'proxy' in col_map:
                ci = col_map['proxy']
                v = str(row[ci] if ci < len(row) else '').strip()
                acc['proxy_str'] = v if v and v.lower() != 'nan' else ''
            else:
                acc['proxy_str'] = ''

            if 'address' in col_map:
                ci = col_map['address']
                v = str(row[ci] if ci < len(row) else '').strip()
                acc['address'] = v if v and v.lower() != 'nan' else ''
            else:
                acc['address'] = ''

            # Backup codes
            bc_list = []
            if 'backup_codes' in col_map:
                for ci, _ in col_map['backup_codes']:
                    v = str(row[ci] if ci < len(row) else '').strip().replace(' ', '')
                    if v and v.lower() != 'nan' and v.isdigit() and 6 <= len(v) <= 10:
                        bc_list.append(v)
            acc['backup_codes'] = bc_list

            accounts.append(acc)

        # Find status column index for write-back
        status_col = col_map.get('status')

        tabs_out[tab_name] = {
            'success': True,
            'accounts': accounts,
            'header_row': h_row_idx + 1,
            'status_col': (status_col + 1) if status_col is not None else None,  # 1-based
            'headers': headers_orig,
        }

    return {'success': True, 'tabs': tabs_out}
```

- [ ] **Step 2: Add sheet preview endpoint to server.py**

Add after the existing `/api/sheets/<sheet_id>/preview-batch` endpoint (around line 2667):

```python
@app.route('/api/sheets/<sheet_id>/preview-batch-login', methods=['POST'])
def sheets_preview_batch_login(sheet_id):
    """Probe tabs for Email+Password columns and return account counts."""
    body = request.get_json(silent=True) or {}
    tabs = body.get('tabs') or []
    if not isinstance(tabs, list):
        return jsonify({'success': False, 'message': 'tabs must be a list'}), 400
    clean = [str(t).strip() for t in tabs if str(t or '').strip()]
    result = _sheets_int.read_accounts_from_tabs(RESOURCES_PATH, sheet_id, clean)
    if not result.get('success'):
        return jsonify(result)
    # Summarize for preview
    tabs_summary = []
    total_valid = 0
    for tab_name, info in result['tabs'].items():
        count = len(info.get('accounts', [])) if info.get('success') else 0
        total_valid += count
        tabs_summary.append({
            'tab': tab_name,
            'success': info.get('success', False),
            'count': count,
            'message': info.get('message', ''),
            'has_proxy': 'Proxy' in (info.get('headers') or []),
        })
    return jsonify({'success': True, 'tabs': tabs_summary, 'total_valid': total_valid})
```

- [ ] **Step 3: Add `batch_login_from_sheet()` to profile_manager.py**

Add after the existing `batch_login()` function (around line 1144). This is the sheet-aware variant that reads from Google Sheets and writes back Status.

```python
def batch_login_from_sheet(sheet_id: str, tabs: list[str],
                           num_workers: int = 3, os_type: str = 'random',
                           group: str = 'default',
                           resources_path=None) -> dict:
    """Read accounts from Google Sheet tabs, create profiles, login, write Status back."""
    from shared import sheets_integration as _si

    rp = resources_path or _find_resources_path()
    result = _si.read_accounts_from_tabs(rp, sheet_id, tabs)
    if not result.get('success'):
        return {'success': False, 'error': result.get('message', 'Failed to read sheet')}

    # Flatten accounts from all tabs, track which tab+row each came from
    accounts = []
    tab_meta = {}  # track header_row and status_col per tab for write-back
    for tab_name, info in result['tabs'].items():
        if not info.get('success'):
            continue
        tab_meta[tab_name] = {
            'header_row': info.get('header_row'),
            'status_col': info.get('status_col'),
        }
        for acc in info.get('accounts', []):
            # Parse proxy string if present
            proxy_data = None
            if acc.get('proxy_str'):
                proxy_data = _parse_proxy_string(acc['proxy_str'])
            accounts.append({
                'email': acc['email'],
                'password': acc['password'],
                'totp_secret': acc.get('totp_secret', ''),
                'backup_codes': acc.get('backup_codes', []),
                'proxy': proxy_data,
                'address': acc.get('address', ''),
                '_sheet_tab': tab_name,
                '_sheet_row': acc['row'],
            })

    if not accounts:
        return {'success': False, 'error': 'No valid accounts found in selected tabs'}

    _log(f"Batch login (sheet): {len(accounts)} accounts from {len(tab_meta)} tabs, "
         f"{num_workers} workers, os={os_type}, group={group}")

    global _batch_login_progress
    _batch_login_progress.update({
        'running': True, 'status': 'processing',
        'total': len(accounts), 'success': 0, 'failed': 0, 'pending': len(accounts),
        'current_account': '', 'started_at': None,
    })

    t = threading.Thread(
        target=_batch_login_worker,
        args=(accounts, num_workers, 'nst', os_type, group),
        kwargs={
            'sheet_id': sheet_id,
            'tab_meta': tab_meta,
            'resources_path': rp,
        },
        daemon=True,
        name='batch-login-sheet',
    )
    t.start()

    return {'success': True, 'total': len(accounts)}


def _find_resources_path():
    """Resolve RESOURCES_PATH the same way server.py does."""
    import os
    from pathlib import Path
    return Path(os.environ.get('RESOURCES_PATH',
                               str(Path(__file__).parent.parent)))
```

- [ ] **Step 4: Modify `_batch_login_worker` to accept sheet write-back kwargs**

In `_batch_login_worker` (line 1152), add `**kwargs` to the signature and add write-back logic after all accounts are processed.

Change function signature from:
```python
def _batch_login_worker(accounts: list[dict], num_workers: int,
                        engine: str = 'nst', os_type: str = 'random',
                        group: str = 'default'):
```
to:
```python
def _batch_login_worker(accounts: list[dict], num_workers: int,
                        engine: str = 'nst', os_type: str = 'random',
                        group: str = 'default', *,
                        sheet_id: str = '', tab_meta: dict = None,
                        resources_path=None):
```

After the `ThreadPoolExecutor` block completes (around line 1322, after setting the final `_batch_login_progress`), add sheet write-back:

```python
    # ── Write back to Google Sheet ────────────────────────────────────
    if sheet_id and tab_meta:
        from shared import sheets_integration as _si
        from shared.sheets_integration import ensure_column, batch_update_status
        _log("[BATCH] Writing login status back to Google Sheet...")
        _batch_login_progress['current_account'] = 'Writing results to sheet...'

        # Group results by tab
        tab_results = {}  # tab_name -> {row: status_value}
        for r in results:
            tab = r.get('_sheet_tab')
            row = r.get('_sheet_row')
            if not tab or not row:
                continue
            status_val = 'Logged In' if r.get('success') else 'Login Failed'
            tab_results.setdefault(tab, {})[row] = status_val

        for tab_name, row_vals in tab_results.items():
            meta = tab_meta.get(tab_name, {})
            # Ensure Status column exists
            st_col = meta.get('status_col')
            if not st_col:
                ec = ensure_column(resources_path, sheet_id, tab_name, 'Status')
                if ec.get('success'):
                    st_col = ec['col']
            if st_col:
                res = batch_update_status(resources_path, sheet_id, tab_name, st_col, row_vals)
                _log(f"[BATCH] Sheet write-back {tab_name}: {res.get('updated', 0)} cells")

        _batch_login_progress['current_account'] = ''
```

Also update `login_single()` to pass through `_sheet_tab` and `_sheet_row` in the result dict. In each return statement inside `login_single()`, add these fields:

```python
return {'email': email, 'profile_id': profile_id, 'success': True,
        '_sheet_tab': account.get('_sheet_tab'), '_sheet_row': account.get('_sheet_row')}
```

(Same for the failure returns.)

- [ ] **Step 5: Modify the batch-login endpoint in server.py**

Change `/api/profiles/batch-login` endpoint (line 2800) to handle both Excel and Sheet sources:

```python
@app.route('/api/profiles/batch-login', methods=['POST'])
def profiles_batch_login():
    """Start batch login from Excel file or Google Sheet."""
    data = request.get_json(force=True, silent=True) or {}
    num_workers = int(data.get('workers', 3))
    engine = data.get('engine', 'nexus')
    os_type = data.get('os_type', 'random')
    group = data.get('group', 'default') or 'default'

    # Sheet source
    sheet_id = data.get('sheet_id', '').strip()
    tabs = data.get('tabs')
    if sheet_id and tabs:
        result = profile_manager.batch_login_from_sheet(
            sheet_id=sheet_id, tabs=tabs,
            num_workers=num_workers, os_type=os_type, group=group,
            resources_path=str(RESOURCES_PATH),
        )
        return jsonify(result)

    # Excel source (existing flow)
    file_path = data.get('file_path', '').strip()
    if not file_path:
        return jsonify({'success': False, 'message': 'File path or sheet_id required'}), 400
    result = profile_manager.batch_login(file_path, num_workers, engine=engine, os_type=os_type, group=group)
    return jsonify(result)
```

- [ ] **Step 6: Commit**

```bash
git add shared/sheets_integration.py shared/profile_manager.py electron-app/backend/server.py
git commit -m "feat: batch login Google Sheet integration — read accounts from tabs, write status back"
```

---

## Task 2: Google Sheet Source for Batch Login — Frontend

**Files:**
- Modify: `electron-app/renderer/index.html:830-873` (batch login modal)
- Modify: `electron-app/renderer/modules/profiles.js:981-1384` (batch login functions)

### Step-by-step:

- [ ] **Step 1: Rebuild the Batch Login modal HTML**

Replace the batch login modal (lines 830-873 in index.html) with an expanded version that includes Excel/Sheet source tabs (same pattern as live-check modal):

```html
        <!-- Batch Login Modal -->
        <div id="batchLoginModalOverlay" class="profile-modal-overlay">
            <div class="profile-modal" style="max-width:560px;padding:20px;">
                <h2 style="margin:0 0 6px;"><i class="fas fa-file-excel" style="color:#4ade80;"></i> Batch Login</h2>
                <p style="font-size:12px;color:#94a3b8;margin:0 0 16px;">
                    Provide an Excel file or Google Sheet with <b>Email</b> &amp; <b>Password</b> columns.
                    Profiles are created and logged in automatically.
                </p>
                <!-- Source tab switcher -->
                <div style="display:flex;gap:6px;margin-bottom:10px;background:#0f1629;border:1px solid var(--border);border-radius:8px;padding:4px;">
                    <button type="button" id="batchLoginSrcExcel" class="btn btn-sm" style="flex:1;background:rgba(99,102,241,0.25);">
                        <i class="fas fa-file-excel"></i> Excel File
                    </button>
                    <button type="button" id="batchLoginSrcSheet" class="btn btn-sm" style="flex:1;background:transparent;color:#94a3b8;">
                        <i class="fab fa-google"></i> Google Sheet
                    </button>
                </div>

                <!-- Excel input -->
                <div id="batchLoginExcelGroup" class="form-group">
                    <label>Excel File</label>
                    <div style="display:flex;gap:8px;"><input type="text" id="batchLoginFilePath" placeholder="accounts.xlsx" style="flex:1;"><button class="btn btn-secondary btn-sm" id="batchLoginBrowseBtn"><i class="fas fa-folder-open"></i></button></div>
                </div>

                <!-- Google Sheet picker (hidden by default) -->
                <div id="batchLoginSheetGroup" style="display:none;">
                    <div id="batchLoginSheetAuth" style="display:none;padding:10px 12px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);border-radius:6px;font-size:12px;color:#fde68a;margin-bottom:10px;">
                        <div style="margin-bottom:6px;">Google Sheets is not connected yet.</div>
                        <button class="btn btn-primary btn-sm" id="batchLoginSheetAuthBtn">
                            <i class="fas fa-key"></i> Connect Google Sheets
                        </button>
                    </div>
                    <div id="batchLoginSheetPicker" style="display:none;">
                        <div style="display:flex;justify-content:flex-end;margin-bottom:6px;">
                            <button type="button" class="btn btn-sm" id="batchLoginSheetReconnectBtn" style="padding:2px 10px;font-size:11px;background:transparent;color:#94a3b8;border:1px solid var(--border);" title="Re-authorize">
                                <i class="fas fa-redo-alt" style="font-size:10px;"></i> Reconnect
                            </button>
                        </div>
                        <div class="form-group">
                            <label>Spreadsheet</label>
                            <div style="display:flex;gap:8px;">
                                <input type="text" id="batchLoginSheetSearch" placeholder="Search by name..." style="flex:1;">
                                <button class="btn btn-secondary btn-sm" id="batchLoginSheetRefreshBtn" title="Refresh"><i class="fas fa-sync"></i></button>
                            </div>
                            <div id="batchLoginSheetList" style="margin-top:6px;max-height:180px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;background:#0f1629;"></div>
                        </div>
                        <div class="form-group" id="batchLoginTabGroup" style="display:none;">
                            <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;background:#0f1629;border:1px solid rgba(99,102,241,0.3);border-radius:6px 6px 0 0;border-bottom:none;font-size:12px;color:#cbd5e1;">
                                <span>Tabs (select tabs with Email &amp; Password columns)</span>
                                <span style="display:flex;gap:4px;">
                                    <button type="button" class="btn btn-sm" id="batchLoginTabAllBtn" style="padding:2px 8px;font-size:11px;">All</button>
                                    <button type="button" class="btn btn-sm" id="batchLoginTabNoneBtn" style="padding:2px 8px;font-size:11px;background:transparent;color:#94a3b8;">None</button>
                                </span>
                            </div>
                            <div id="batchLoginTabList" style="max-height:200px;overflow-y:auto;background:#0f1629;border:1px solid rgba(99,102,241,0.3);border-radius:0 0 6px 6px;padding:2px 0;"></div>
                        </div>
                    </div>
                </div>

                <!-- Preview bar (works for both) -->
                <div id="batchLoginPreview" style="display:none;align-items:center;gap:10px;margin-top:8px;padding:8px 12px;background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);border-radius:6px;font-size:12px;flex-wrap:wrap;"></div>

                <!-- Engine: NST API only -->
                <input type="hidden" name="batchEngine" value="nst">
                <!-- Device OS -->
                <div class="form-group">
                    <label>Device OS</label>
                    <div class="pm-os-pills">
                        <label class="pm-os-pill active" data-os="random"><input type="radio" name="batchOs" value="random" checked><i class="fas fa-random"></i> Random</label>
                        <label class="pm-os-pill" data-os="windows"><input type="radio" name="batchOs" value="windows"><i class="fab fa-windows"></i> Win</label>
                        <label class="pm-os-pill" data-os="macos"><input type="radio" name="batchOs" value="macos"><i class="fab fa-apple"></i> Mac</label>
                        <label class="pm-os-pill" data-os="linux"><input type="radio" name="batchOs" value="linux"><i class="fab fa-linux"></i> Linux</label>
                    </div>
                </div>
                <div style="display:flex;gap:12px;">
                    <div class="form-group" style="flex:1;"><label>Workers</label><input type="number" id="batchLoginWorkers" value="3" min="1" max="100" style="width:100px;"></div>
                    <div class="form-group" style="flex:1;">
                        <label>Stagger Delay (sec)</label>
                        <input type="number" id="batchLoginStagger" value="3" min="0" max="30" style="width:100px;" title="Delay between worker starts to avoid IP rate-limiting">
                    </div>
                    <div class="form-group" style="flex:2;">
                        <label>Assign Group</label>
                        <input type="text" id="batchLoginGroup" list="batchLoginGroupList" placeholder="default" autocomplete="off" style="width:100%;">
                        <datalist id="batchLoginGroupList"></datalist>
                    </div>
                </div>
                <div style="font-size:11px;color:#64748b;margin-top:-4px;margin-bottom:8px;">
                    <i class="fas fa-info-circle" style="margin-right:4px;"></i>
                    Stagger delay adds a pause between each worker start to prevent IP-based rate limiting.
                </div>
                <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px;">
                    <button class="btn btn-secondary" id="batchLoginCloseBtn">Cancel</button>
                    <button class="btn btn-primary" id="batchLoginStartBtn"><i class="fas fa-play"></i> Start</button>
                </div>
            </div>
        </div>
```

- [ ] **Step 2: Add batch login sheet JS logic in profiles.js**

Add after `openBatchLoginModal()` (around line 986). These functions mirror the live-check sheet picker pattern exactly.

```javascript
    // ── Batch Login: source switching ──────────────────────────────────
    let _batchLoginSource = 'excel';   // 'excel' | 'sheet'
    let _batchSheetId = '';
    let _batchSheetName = '';
    let _batchSelectedTabs = new Set();

    function _switchBatchLoginSource(src) {
        _batchLoginSource = src;
        const excel = _$('batchLoginSrcExcel'), sheet = _$('batchLoginSrcSheet');
        const eg = _$('batchLoginExcelGroup'), sg = _$('batchLoginSheetGroup');
        if (src === 'sheet') {
            if (excel) excel.style = 'flex:1;background:transparent;color:#94a3b8;';
            if (sheet) sheet.style = 'flex:1;background:rgba(99,102,241,0.25);';
            if (eg) eg.style.display = 'none';
            if (sg) sg.style.display = 'block';
            _refreshBatchSheetAuth();
        } else {
            if (excel) excel.style = 'flex:1;background:rgba(99,102,241,0.25);';
            if (sheet) sheet.style = 'flex:1;background:transparent;color:#94a3b8;';
            if (eg) eg.style.display = 'block';
            if (sg) sg.style.display = 'none';
        }
        _setBatchPreview(null);
    }

    async function _refreshBatchSheetAuth() {
        try {
            const r = await fetch('http://localhost:5000/api/sheets/status');
            const s = await r.json();
            const auth = _$('batchLoginSheetAuth');
            const picker = _$('batchLoginSheetPicker');
            if (s.configured) {
                if (auth) auth.style.display = 'none';
                if (picker) picker.style.display = 'block';
                _loadBatchSheetList();
            } else {
                if (auth) auth.style.display = 'block';
                if (picker) picker.style.display = 'none';
            }
        } catch (e) { /* ignore */ }
    }

    async function _doBatchSheetAuthorize() {
        const btn = _$('batchLoginSheetAuthBtn');
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Waiting...'; }
        App.toast('A browser tab will open — log in and grant access', 'info');
        try {
            const r = await fetch('http://localhost:5000/api/sheets/authorize', { method: 'POST' });
            const d = await r.json();
            if (d.success) {
                App.toast('Google Sheets connected', 'success');
                await _refreshBatchSheetAuth();
            } else {
                App.toast(d.message || 'Authorization failed', 'error');
            }
        } catch (e) {
            App.toast('Auth error: ' + e.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-key"></i> Connect Google Sheets'; }
        }
    }

    let _batchSheetSearchTimer = null;
    async function _loadBatchSheetList() {
        const list = _$('batchLoginSheetList');
        if (!list) return;
        const q = (_val('batchLoginSheetSearch') || '').trim();
        list.innerHTML = '<div style="padding:14px;text-align:center;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
        try {
            const url = 'http://localhost:5000/api/sheets/list' + (q ? `?q=${encodeURIComponent(q)}` : '');
            const r = await fetch(url);
            const d = await r.json();
            if (!d.success) { list.innerHTML = `<div style="padding:14px;color:#fca5a5;font-size:12px;">${d.message}</div>`; return; }
            const sheets = d.sheets || [];
            if (!sheets.length) { list.innerHTML = '<div style="padding:14px;text-align:center;color:#64748b;font-size:12px;">No spreadsheets found.</div>'; return; }
            list.innerHTML = sheets.map(s => {
                const mod = s.modified ? new Date(s.modified).toLocaleDateString() : '';
                const isSel = s.id === _batchSheetId ? 'background:rgba(99,102,241,0.18);' : '';
                return `<div class="sheet-row" data-id="${s.id}" data-name="${(s.name||'').replace(/"/g,'&quot;')}"
                            style="padding:8px 10px;border-bottom:1px solid #1e293b;cursor:pointer;${isSel}">
                    <div style="font-size:13px;color:#e2e8f0;">${s.name || '(unnamed)'}</div>
                    <div style="font-size:11px;color:#64748b;">Modified ${mod} · ${s.owner || ''}</div>
                </div>`;
            }).join('');
            list.querySelectorAll('.sheet-row').forEach(el => {
                el.addEventListener('click', () => _onBatchSheetPicked(el.getAttribute('data-id'), el.getAttribute('data-name')));
            });
        } catch (e) {
            list.innerHTML = `<div style="padding:14px;color:#fca5a5;font-size:12px;">${e.message}</div>`;
        }
    }

    async function _onBatchSheetPicked(id, name) {
        _batchSheetId = id;
        _batchSheetName = name || '';
        _batchSelectedTabs.clear();
        document.querySelectorAll('#batchLoginSheetList .sheet-row').forEach(el => {
            el.style.background = el.getAttribute('data-id') === id ? 'rgba(99,102,241,0.18)' : 'transparent';
        });
        const tabGroup = _$('batchLoginTabGroup');
        const tabList = _$('batchLoginTabList');
        if (tabGroup) tabGroup.style.display = 'block';
        if (tabList) tabList.innerHTML = '<div style="padding:10px 14px;text-align:center;color:#64748b;font-size:12px;"><i class="fas fa-spinner fa-spin"></i> Loading tabs...</div>';
        try {
            const r = await fetch(`http://localhost:5000/api/sheets/${encodeURIComponent(id)}/tabs`);
            const d = await r.json();
            if (!d.success) { if (tabList) tabList.innerHTML = `<div style="padding:10px 14px;color:#fca5a5;font-size:12px;">${d.message||'error'}</div>`; return; }
            const tabs = d.tabs || [];
            if (tabList) {
                if (!tabs.length) { tabList.innerHTML = '<div style="padding:10px 14px;text-align:center;color:#64748b;font-size:12px;">No tabs found.</div>'; return; }
                tabList.innerHTML = tabs.map(t => {
                    const eName = (t.title || '').replace(/"/g, '&quot;');
                    return `<label class="bl-tab-row" style="display:flex;align-items:center;gap:8px;padding:6px 10px;cursor:pointer;border-bottom:1px solid #1e293b;font-size:12px;color:#e2e8f0;" data-tab="${eName}">
                        <input type="checkbox" class="bl-tab-cb" value="${eName}" style="accent-color:#6366f1;">
                        <span style="flex:1;">${t.title || '(unnamed)'}</span>
                        <span class="bl-tab-count" style="font-size:11px;color:#64748b;"></span>
                    </label>`;
                }).join('');
                tabList.querySelectorAll('.bl-tab-cb').forEach(cb => {
                    cb.addEventListener('change', () => {
                        if (cb.checked) _batchSelectedTabs.add(cb.value);
                        else _batchSelectedTabs.delete(cb.value);
                        _previewBatchSheetTabs();
                    });
                });
                // Auto-select all
                tabList.querySelectorAll('.bl-tab-cb').forEach(cb => { cb.checked = true; _batchSelectedTabs.add(cb.value); });
                _previewBatchSheetTabs();
            }
        } catch (e) {
            App.toast('Could not load tabs: ' + e.message, 'error');
        }
    }

    function _batchLoginToggleAllTabs(selectAll) {
        const tabList = _$('batchLoginTabList');
        if (!tabList) return;
        _batchSelectedTabs.clear();
        tabList.querySelectorAll('.bl-tab-cb').forEach(cb => {
            cb.checked = selectAll;
            if (selectAll) _batchSelectedTabs.add(cb.value);
        });
        _previewBatchSheetTabs();
    }

    async function _previewBatchSheetTabs() {
        const id = _batchSheetId;
        const selectedTabs = [..._batchSelectedTabs];
        const prev = _$('batchLoginPreview');
        if (!prev) return;
        if (!id || selectedTabs.length === 0) { prev.style.display = 'none'; return; }
        prev.style.display = 'flex';
        prev.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Reading selected tabs...';
        try {
            const r = await fetch(`http://localhost:5000/api/sheets/${encodeURIComponent(id)}/preview-batch-login`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tabs: selectedTabs }),
            });
            const d = await r.json();
            if (d.success) {
                const tabsArr = d.tabs || [];
                let totalAccounts = d.total_valid || 0;
                // Update per-tab counts
                document.querySelectorAll('#batchLoginTabList .bl-tab-row').forEach(row => {
                    const tabName = row.getAttribute('data-tab');
                    const countEl = row.querySelector('.bl-tab-count');
                    const tabInfo = tabsArr.find(t => t.tab === tabName);
                    if (countEl && tabInfo) {
                        countEl.textContent = tabInfo.success ? `${tabInfo.count} accounts` : tabInfo.message;
                        countEl.style.color = tabInfo.count > 0 ? '#22c55e' : '#64748b';
                    }
                });
                const hasProxy = tabsArr.some(t => t.has_proxy);
                prev.innerHTML = `<span style="color:#4ade80;"><i class="fab fa-google"></i> <strong>${totalAccounts}</strong> valid accounts</span>` +
                    `<span style="color:#64748b;font-size:11px;">across ${selectedTabs.length} tab${selectedTabs.length===1?'':'s'}</span>` +
                    (hasProxy ? '<span style="color:#64748b;font-size:11px;">· Proxy column detected</span>' : '');
            } else {
                prev.innerHTML = `<span style="color:#f87171;"><i class="fas fa-exclamation-circle"></i> ${d.message || 'Could not read sheet'}</span>`;
            }
        } catch (e) {
            prev.innerHTML = `<span style="color:#f87171;"><i class="fas fa-times-circle"></i> ${e.message}</span>`;
        }
    }
```

- [ ] **Step 3: Modify `startBatchLogin()` to support sheet source**

Replace the existing `startBatchLogin()` function (line 1363):

```javascript
    async function startBatchLogin() {
        const workers = parseInt(_val('batchLoginWorkers')) || 3;
        const staggerDelay = parseInt(_val('batchLoginStagger')) || 3;
        const engine = 'nst';
        const osRadio = document.querySelector('input[name="batchOs"]:checked');
        const osType = osRadio ? osRadio.value : 'random';
        const group = (_val('batchLoginGroup') || 'default').trim() || 'default';

        let payload = { workers, engine, os_type: osType, group, stagger_delay: staggerDelay };

        if (_batchLoginSource === 'sheet') {
            const selectedTabs = [..._batchSelectedTabs];
            if (!_batchSheetId || selectedTabs.length === 0) {
                App.toast('Pick a Google Sheet and select at least one tab', 'error');
                return;
            }
            payload.sheet_id = _batchSheetId;
            payload.tabs = selectedTabs;
        } else {
            const filePath = _val('batchLoginFilePath').trim();
            if (!filePath) { App.toast('Select an Excel file first', 'error'); return; }
            payload.file_path = filePath;
        }

        try {
            const data = await _api('/api/profiles/batch-login', {
                method: 'POST', body: JSON.stringify(payload)
            });
            if (data.success) {
                App.toast(`Batch login started: ${data.total} accounts — group: ${group}`, 'success');
                closeBatchLoginModal();
                _startOpProgress('batch-login');
                _startStatusPolling();
                _loadGroups();
            } else App.toast(data.message || data.error || 'Batch login failed', 'error');
        } catch (e) { App.toast('Batch login error: ' + e.message, 'error'); }
    }
```

- [ ] **Step 4: Wire up event listeners for new batch login sheet UI**

Add in the event listener setup section (around lines 4150-4200 in profiles.js, wherever other batch login listeners are bound):

```javascript
    // Batch Login source tabs
    const blSrcExcel = _$('batchLoginSrcExcel');
    const blSrcSheet = _$('batchLoginSrcSheet');
    if (blSrcExcel) blSrcExcel.addEventListener('click', () => _switchBatchLoginSource('excel'));
    if (blSrcSheet) blSrcSheet.addEventListener('click', () => _switchBatchLoginSource('sheet'));

    // Batch Login sheet auth
    const blSheetAuthBtn = _$('batchLoginSheetAuthBtn');
    if (blSheetAuthBtn) blSheetAuthBtn.addEventListener('click', _doBatchSheetAuthorize);

    // Batch Login sheet search
    const blSheetSearch = _$('batchLoginSheetSearch');
    if (blSheetSearch) blSheetSearch.addEventListener('input', () => {
        if (_batchSheetSearchTimer) clearTimeout(_batchSheetSearchTimer);
        _batchSheetSearchTimer = setTimeout(_loadBatchSheetList, 400);
    });

    // Batch Login sheet refresh
    const blSheetRefresh = _$('batchLoginSheetRefreshBtn');
    if (blSheetRefresh) blSheetRefresh.addEventListener('click', _loadBatchSheetList);

    // Batch Login sheet reconnect
    const blSheetReconnect = _$('batchLoginSheetReconnectBtn');
    if (blSheetReconnect) blSheetReconnect.addEventListener('click', async () => {
        await fetch('http://localhost:5000/api/sheets/authorize', { method: 'POST' });
        await _refreshBatchSheetAuth();
    });

    // Batch Login tab All/None
    const blTabAll = _$('batchLoginTabAllBtn');
    const blTabNone = _$('batchLoginTabNoneBtn');
    if (blTabAll) blTabAll.addEventListener('click', () => _batchLoginToggleAllTabs(true));
    if (blTabNone) blTabNone.addEventListener('click', () => _batchLoginToggleAllTabs(false));
```

- [ ] **Step 5: Update `openBatchLoginModal` to reset sheet state**

```javascript
    function openBatchLoginModal() {
        _$('batchLoginModalOverlay').classList.add('active');
        _loadGroups();
        _setBatchPreview(null);
        _switchBatchLoginSource(_batchLoginSource);
    }
```

- [ ] **Step 6: Commit**

```bash
git add electron-app/renderer/index.html electron-app/renderer/modules/profiles.js
git commit -m "feat: batch login UI — Google Sheet source tab with spreadsheet/tab picker"
```

---

## Task 3: Profile Creation — Silent Local Fallback on NST Limit

**Files:**
- Modify: `electron-app/backend/server.py:3973-4008` (create profile endpoint)
- Modify: `shared/nexus_profile_manager.py:830-1035` (create_profile error handling)

### Step-by-step:

- [ ] **Step 1: Fix the backend endpoint to return 201 even on NST error**

The profile is already being created and saved locally when NST fails (lines 834-856 + 997-1029 in nexus_profile_manager.py). The only problem is the endpoint returns HTTP 400. Change `napi_create_profile` in server.py (line 3973):

```python
@nexus_api.route('/profiles', methods=['POST'])
def napi_create_profile():
    """Create a new profile."""
    data = request.get_json(force=True, silent=True) or {}
    name = data.get('name', f'Profile {secrets.token_hex(3)}')
    engine = data.get('engine', 'nexus')
    os_type = data.get('os_type', 'windows')

    # Parse proxy from string if given as string
    proxy = data.get('proxy')
    if isinstance(proxy, str) and proxy:
        from shared.nexus_proxy_manager import parse_proxy
        proxy = parse_proxy(proxy)

    try:
        profile = profile_manager.create_profile(
            name=name,
            email=data.get('email', ''),
            proxy=proxy,
            notes=data.get('notes', ''),
            fingerprint_prefs={'os_type': os_type},
            password=data.get('password', ''),
            totp_secret=data.get('totp_secret', ''),
            backup_codes=data.get('backup_codes', []),
            engine=engine,
            frontend_sections={
                'overview': data.get('overview', {}),
                'advanced': data.get('advanced', {}),
            },
        )
        nst_err = profile.pop('_nst_create_error', None)
        if nst_err:
            # Profile was created locally — return success with a warning
            return _napi(profile, msg=f'Profile created locally ({nst_err})', status=201)
        return _napi(profile, msg='Profile created', status=201)
    except Exception as e:
        return _napi(msg=str(e), err=True, status=500)
```

The key change: when NST fails, we still return `status=201` (success) instead of `status=400` (error), and `err=False` (implicit). The message includes the NST warning for info.

- [ ] **Step 2: Verify that `_napi` helper returns `success: True` for non-error responses**

Check the `_napi` helper to confirm it sets `success: True` when `err=False`:

Read `server.py` near the `_napi` definition to confirm the pattern. If `_napi(profile, msg=..., status=201)` sets `success: True` then we're done. If it checks `err` flag, make sure we're not passing `err=True`.

- [ ] **Step 3: Commit**

```bash
git add electron-app/backend/server.py
git commit -m "fix: profile creation succeeds locally when NST API limit is reached"
```

---

## Task 4: Custom Bookmarks for Profiles

**Files:**
- Modify: `electron-app/renderer/index.html` (overview tab — add bookmarks field)
- Modify: `electron-app/renderer/modules/profiles.js` (load/save bookmarks)
- Modify: `shared/nexus_profile_manager.py` (store bookmarks, write Chrome Bookmarks file)
- Modify: `shared/browser.py` or `shared/stealth_chrome.py` (write bookmarks before launch)

### Step-by-step:

- [ ] **Step 1: Add bookmarks textarea to the profile modal overview tab**

In `index.html`, after the Startup URLs field (line 705), add a bookmarks input:

```html
                            <div class="form-group">
                                <label>Bookmarks <span style="font-size:10px;color:#64748b;">(one per line: URL or Name|URL)</span></label>
                                <textarea id="pmBookmarks" rows="4" placeholder="https://mail.google.com&#10;YouTube|https://youtube.com&#10;Maps|https://maps.google.com" style="width:100%;font-size:12px;font-family:monospace;resize:vertical;"></textarea>
                            </div>
```

- [ ] **Step 2: Load bookmarks into edit modal**

In `profiles.js` `openEditModal()` (around line 637, after the startup_urls line), add:

```javascript
            // Bookmarks
            const bm = (ov.bookmarks || []).map(b => b.name && b.name !== b.url ? `${b.name}|${b.url}` : b.url).join('\n');
            _setVal('pmBookmarks', bm);
```

- [ ] **Step 3: Clear bookmarks in `_resetModal()`**

In `_resetModal()` (around line 689), add:

```javascript
        _setVal('pmBookmarks', '');
```

- [ ] **Step 4: Send bookmarks in `saveProfile()`**

In `saveProfile()` (around line 849, inside the `overview` object), add `bookmarks`:

```javascript
            overview: {
                os: os,
                browser_kernel: 'nstbrowser',
                startup_urls: _val('pmStartupUrls').split(',').map(s => s.trim()).filter(Boolean),
                bookmarks: _val('pmBookmarks').split('\n').map(line => {
                    line = line.trim();
                    if (!line) return null;
                    const pipe = line.indexOf('|');
                    if (pipe > 0) return { name: line.substring(0, pipe).trim(), url: line.substring(pipe + 1).trim() };
                    return { name: line, url: line };
                }).filter(Boolean),
            },
```

- [ ] **Step 5: Store bookmarks in profile data (nexus_profile_manager.py)**

In `create_profile()` at line 995 (where `overview` dict is built), add the bookmarks from `frontend_sections`:

```python
    _bookmarks = _ov.get('bookmarks', [])
    overview = {
        'os': raw_os,
        ...existing fields...,
        'bookmarks': _bookmarks,
    }
```

In `update_profile()` (line 1038+), ensure `overview.bookmarks` is updated when `overview` is passed:

The existing `update_profile` merges fields — check that it properly handles nested `overview` dict updates. If it does a shallow merge, bookmarks in `overview` will be included automatically.

- [ ] **Step 6: Add `_write_chrome_bookmarks()` helper to nexus_profile_manager.py**

Add near the bottom of the profile management section:

```python
def _write_chrome_bookmarks(profile_dir: str, bookmarks: list[dict]):
    """Write Chrome's Bookmarks JSON file to profile_dir/Default/Bookmarks.

    bookmarks: [{name: 'Gmail', url: 'https://...'}, ...]
    Merges with existing bookmarks (doesn't wipe user-added ones).
    """
    import json
    default_dir = os.path.join(profile_dir, 'Default')
    os.makedirs(default_dir, exist_ok=True)
    bm_path = os.path.join(default_dir, 'Bookmarks')

    # Load existing bookmarks if present
    existing = None
    if os.path.isfile(bm_path):
        try:
            with open(bm_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            existing = None

    if existing is None:
        existing = {
            'checksum': '',
            'roots': {
                'bookmark_bar': {'children': [], 'name': 'Bookmarks bar', 'type': 'folder'},
                'other': {'children': [], 'name': 'Other bookmarks', 'type': 'folder'},
                'synced': {'children': [], 'name': 'Mobile bookmarks', 'type': 'folder'},
            },
            'version': 1,
        }

    bar = existing.get('roots', {}).get('bookmark_bar', {})
    bar_children = bar.get('children', [])

    # Collect existing URLs to avoid duplicates
    existing_urls = set()
    for child in bar_children:
        if child.get('type') == 'url':
            existing_urls.add(child.get('url', '').rstrip('/').lower())

    # Add new bookmarks
    import time
    base_id = int(time.time())
    for i, bm in enumerate(bookmarks):
        url = bm.get('url', '').strip()
        if not url:
            continue
        if url.rstrip('/').lower() in existing_urls:
            continue
        bar_children.append({
            'date_added': str(int(time.time() * 1000000)),
            'date_last_used': '0',
            'id': str(base_id + i),
            'name': bm.get('name', url),
            'type': 'url',
            'url': url,
        })

    bar['children'] = bar_children
    existing['roots']['bookmark_bar'] = bar

    with open(bm_path, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=3)
```

- [ ] **Step 7: Call `_write_chrome_bookmarks` when launching a profile**

In `shared/browser.py`, in `_launch_persistent_context()` (around line 1091, after `stealth = StealthChrome()` and before `ws_url = await stealth.start(...)`), add:

```python
    # Write bookmarks to Chrome profile if configured
    from shared import nexus_profile_manager as _npm
    _profile_data = _npm.get_profile_by_dir(profile_dir)
    if _profile_data:
        bm_list = (_profile_data.get('overview') or {}).get('bookmarks', [])
        if bm_list:
            _npm._write_chrome_bookmarks(profile_dir, bm_list)
```

Also, add a `get_profile_by_dir()` helper to `nexus_profile_manager.py`:

```python
def get_profile_by_dir(profile_dir: str) -> dict | None:
    """Find a profile by its profile_dir path."""
    profiles = _read_profiles()
    norm = os.path.normpath(profile_dir)
    for p in profiles:
        if os.path.normpath(p.get('profile_dir', '')) == norm:
            return p
    return None
```

Alternatively, if `worker_id` is available and we can look up the profile through it, use that. But `get_profile_by_dir` is simpler and more reliable.

- [ ] **Step 8: Commit**

```bash
git add electron-app/renderer/index.html electron-app/renderer/modules/profiles.js shared/nexus_profile_manager.py shared/browser.py
git commit -m "feat: custom bookmarks for profiles — add/edit via UI, sync to Chrome Bookmarks file on launch"
```

---

## Verification Checklist

- [ ] Open Batch Login modal — verify Excel/Sheet source tabs render
- [ ] Switch to Sheet tab — verify sheet list loads
- [ ] Pick a sheet + tabs — verify preview shows account count per tab
- [ ] Start batch login from sheet — verify profiles are created and logged in
- [ ] Verify sheet Status column is updated with "Logged In" / "Login Failed"
- [ ] Create a profile when NST is at limit — verify profile is created locally (no error toast, profile appears in list)
- [ ] Add bookmarks to a new profile — verify they appear in Chrome when profile is opened
- [ ] Edit an existing profile to add bookmarks — verify they appear on next launch
- [ ] Verify existing bookmarks are not duplicated on subsequent launches
