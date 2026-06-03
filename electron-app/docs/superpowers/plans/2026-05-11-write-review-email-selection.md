# Write Review: Email Selection & Tab Preview Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add group-filter + count-select + XL-import to Write Review profile picker, and debounce tab preview to eliminate 200+ API calls on "Select All".

**Architecture:** Two independent changes: (1) frontend toolbar HTML + JS logic + one new backend route for XL import; (2) a single debounce wrapper in `_wrToggleTab` to batch rapid tab preview API calls.

**Tech Stack:** Electron renderer JS, Flask (Python), pandas (already imported in server.py)

---

## Files Changed

| File | What changes |
|------|-------------|
| `renderer/index.html` | Add group/N/Apply/ImportXL toolbar HTML above `wrProfileSearch` |
| `renderer/modules/profiles.js` | Add `_wrGetFilteredProfiles`, `_wrPopulateGroupFilter`, Apply handler, XL import handler, debounce fix |
| `backend/server.py` | New `POST /api/profiles/write-review/import-emails` route |

---

## Task 1: Backend — XL Email Import Endpoint

**Files:**
- Modify: `backend/server.py` — add route after line 3552 (after `profiles_write_review_preview` function)

- [ ] **Step 1: Add the route to server.py**

Find the closing of `profiles_write_review_preview` (line ~3552, ends with `return jsonify({'success': False, 'message': str(e)})`). Insert this block immediately after:

```python
@app.route('/api/profiles/write-review/import-emails', methods=['POST'])
def profiles_write_review_import_emails():
    """Read an Excel file and return profile IDs whose email matches any row."""
    data = request.get_json(force=True, silent=True) or {}
    file_path = data.get('file_path', '').strip()
    if not file_path or not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': 'File not found'})
    try:
        df = pd.read_excel(file_path)
        if df.empty:
            return jsonify({'success': True, 'matched_ids': [], 'matched_count': 0, 'not_found': []})
        # Find email column: prefer one named "Email" (case-insensitive), else use first column
        email_col = next(
            (c for c in df.columns if str(c).strip().lower() == 'email'),
            df.columns[0]
        )
        emails_in_xl = set()
        for val in df[email_col]:
            e = str(val).strip().lower()
            if e and e != 'nan':
                emails_in_xl.add(e)
        all_profiles = profile_manager.list_profiles()
        matched_ids = []
        matched_emails = set()
        for p in all_profiles:
            e = (p.get('email') or '').strip().lower()
            if e in emails_in_xl:
                matched_ids.append(p['id'])
                matched_emails.add(e)
        not_found = sorted(emails_in_xl - matched_emails)
        return jsonify({
            'success': True,
            'matched_ids': matched_ids,
            'matched_count': len(matched_ids),
            'not_found': not_found,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
```

- [ ] **Step 2: Verify the backend starts without error**

Run: `cd "E:\NST Anty Android\electron-app\backend" && python -c "import server; print('OK')"` (or restart the app and check backend health endpoint `/api/health`).

Expected: no import errors.

- [ ] **Step 3: Commit**

```bash
git add backend/server.py
git commit -m "feat: add write-review/import-emails endpoint — XL email → profile ID match"
```

---

## Task 2: HTML — Add Toolbar Above Profile Search

**Files:**
- Modify: `renderer/index.html` — lines 2528–2529 (between the "Pick profiles" label row and `wrProfileSearch` input)

- [ ] **Step 1: Insert toolbar HTML**

Find this block in `renderer/index.html`:
```html
                            <input type="text" id="wrProfileSearch" placeholder="Search by email…" style="width:100%;background:#111;border:1px solid #475569;border-radius:6px;padding:6px 10px;color:#e2e8f0;font-size:12px;margin-bottom:6px;">
```

Insert the following **before** that `<input>` line:
```html
                            <!-- Group + Count + XL import toolbar -->
                            <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;">
                                <select id="wrGroupFilter" style="flex:1;min-width:0;background:#111;border:1px solid #475569;border-radius:6px;padding:4px 8px;color:#e2e8f0;font-size:12px;">
                                    <option value="">All groups</option>
                                </select>
                                <input type="number" id="wrSelectN" placeholder="First N" min="1"
                                    style="width:72px;background:#111;border:1px solid #475569;border-radius:6px;padding:4px 8px;color:#e2e8f0;font-size:12px;">
                                <button class="btn btn-sm" id="wrApplyGroupBtn" style="font-size:10px;padding:2px 10px;white-space:nowrap;">Apply</button>
                                <button class="btn btn-sm" id="wrImportXlBtn" style="font-size:10px;padding:2px 10px;white-space:nowrap;"><i class="fas fa-file-excel"></i> Import XL</button>
                            </div>
```

- [ ] **Step 2: Commit**

```bash
git add renderer/index.html
git commit -m "feat: add group/count/XL import toolbar HTML in Write Review modal"
```

---

## Task 3: JS — Group Filter + Filtered Profile Helper

**Files:**
- Modify: `renderer/modules/profiles.js`

These changes refactor `_wrRenderProfileList` to respect the group dropdown, and add `_wrGetFilteredProfiles` + `_wrPopulateGroupFilter`.

- [ ] **Step 1: Add `_wrGetFilteredProfiles` helper**

Find this line (~line 2017):
```js
    function _wrRenderProfileList() {
```

Insert immediately **before** it:
```js
    function _wrGetFilteredProfiles() {
        const q = ((_$('wrProfileSearch') || {}).value || '').toLowerCase().trim();
        const grp = (_$('wrGroupFilter') || {}).value || '';
        return _wrAllProfiles.filter(p => {
            if (grp && (p.group || '') !== grp) return false;
            if (!q) return true;
            return (p.email || '').toLowerCase().includes(q) ||
                   (p.name || '').toLowerCase().includes(q);
        });
    }

```

- [ ] **Step 2: Update `_wrRenderProfileList` to use the helper**

Find inside `_wrRenderProfileList` (lines ~2020–2024):
```js
        const q = ((_$('wrProfileSearch') || {}).value || '').toLowerCase().trim();
        const filtered = !q ? _wrAllProfiles
            : _wrAllProfiles.filter(p =>
                (p.email || '').toLowerCase().includes(q) ||
                (p.name || '').toLowerCase().includes(q));
```

Replace with:
```js
        const filtered = _wrGetFilteredProfiles();
```

- [ ] **Step 3: Add `_wrPopulateGroupFilter` function**

Find (line ~2001):
```js
    async function _wrLoadProfileList() {
```

Insert immediately **before** it:
```js
    function _wrPopulateGroupFilter() {
        const sel = _$('wrGroupFilter');
        if (!sel) return;
        const groups = [...new Set(_wrAllProfiles.map(p => p.group).filter(Boolean))].sort();
        sel.innerHTML = '<option value="">All groups</option>' +
            groups.map(g => `<option value="${_esc(g)}">${_esc(g)}</option>`).join('');
    }

```

- [ ] **Step 4: Call `_wrPopulateGroupFilter` after profiles load**

Find inside `_wrLoadProfileList` (line ~2011):
```js
            _wrRenderProfileList();
```

Replace with:
```js
            _wrPopulateGroupFilter();
            _wrRenderProfileList();
```

- [ ] **Step 5: Wire `wrGroupFilter` change event in the init block**

Find (line ~4240):
```js
        const wrPS = _$('wrProfileSearch');
        if (wrPS) wrPS.addEventListener('input', _wrRenderProfileList);
```

Add after that block:
```js
        const wrGF = _$('wrGroupFilter');
        if (wrGF) wrGF.addEventListener('change', _wrRenderProfileList);
```

- [ ] **Step 6: Commit**

```bash
git add renderer/modules/profiles.js
git commit -m "feat: group filter dropdown for Write Review profile picker"
```

---

## Task 4: JS — Apply (Group + Count Select)

**Files:**
- Modify: `renderer/modules/profiles.js` — init block

- [ ] **Step 1: Add Apply button handler in init block**

Find (line ~4242):
```js
        _btn('wrSelectAllProfilesBtn', () => {
```

Insert immediately **before** it:
```js
        _btn('wrApplyGroupBtn', () => {
            const n = parseInt((_$('wrSelectN') || {}).value, 10);
            if (!n || n < 1) { App.toast('Enter a count first', 'warn'); return; }
            const filtered = _wrGetFilteredProfiles();
            const pick = filtered.slice(0, n);
            _wrSelectedProfiles.clear();
            pick.forEach(p => _wrSelectedProfiles.add(p.id));
            _wrRenderProfileList();
            _wrUpdateProfileCount();
            App.toast(`${pick.length} profile${pick.length === 1 ? '' : 's'} selected`, 'success');
        });
```

- [ ] **Step 2: Commit**

```bash
git add renderer/modules/profiles.js
git commit -m "feat: Apply button selects first N profiles from filtered group"
```

---

## Task 5: JS — Import from XL Handler

**Files:**
- Modify: `renderer/modules/profiles.js` — init block

- [ ] **Step 1: Add Import XL button handler**

Find (line ~4242, now after the Apply handler you added in Task 4):
```js
        _btn('wrSelectAllProfilesBtn', () => {
```

Insert immediately **before** it:
```js
        _btn('wrImportXlBtn', async () => {
            const filePath = await window.electronAPI.selectFile();
            if (!filePath) return;
            const ext = filePath.split('.').pop().toLowerCase();
            if (ext !== 'xlsx' && ext !== 'xls') {
                App.toast('Select an .xlsx or .xls file', 'warn'); return;
            }
            try {
                const r = await App.apiFetch('/api/profiles/write-review/import-emails', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file_path: filePath }),
                });
                const d = await r.json();
                if (!d.success) { App.toast(d.message || 'Import failed', 'error'); return; }
                d.matched_ids.forEach(id => _wrSelectedProfiles.add(id));
                _wrRenderProfileList();
                _wrUpdateProfileCount();
                const suffix = d.not_found.length ? ` · ${d.not_found.length} not found` : '';
                App.toast(`${d.matched_count} profile${d.matched_count === 1 ? '' : 's'} selected${suffix}`, 'success');
            } catch (e) { App.toast('Import error: ' + e.message, 'error'); }
        });
```

- [ ] **Step 2: Commit**

```bash
git add renderer/modules/profiles.js
git commit -m "feat: Import XL button selects profiles by email from Excel file"
```

---

## Task 6: JS — Tab Preview Debounce (Performance Fix)

**Files:**
- Modify: `renderer/modules/profiles.js`

- [ ] **Step 1: Add debounce timer variable and wrapper function**

Find (line ~1854):
```js
    let _wrSearchTimer = null;
```

Add immediately after it:
```js
    let _wrPreviewDebounceTimer = null;
    function _wrPreviewTabsDebounced() {
        if (_wrPreviewDebounceTimer) clearTimeout(_wrPreviewDebounceTimer);
        _wrPreviewDebounceTimer = setTimeout(_wrPreviewTabs, 300);
    }
```

- [ ] **Step 2: Replace `_wrPreviewTabs()` calls inside `_wrToggleTab` with debounced version**

Find inside `_wrToggleTab` (line ~2067):
```js
            _wrPreviewTabs();
```
Replace with:
```js
            _wrPreviewTabsDebounced();
```

Then find the other call in the same function (line ~2072):
```js
            _wrUpdateSummary();
```
This one stays as-is (it's the "unchecked" branch that just updates UI with no API call).

- [ ] **Step 3: Verify fix — open modal, pick a sheet, click "All" tabs**

Expected: loading spinner appears once after 300ms, then result renders. Previously it would fire N API calls simultaneously.

- [ ] **Step 4: Commit**

```bash
git add renderer/modules/profiles.js
git commit -m "perf: debounce tab preview to batch 200+ rapid checkbox changes into one API call"
```

---

## Self-Review

**Spec coverage:**
- ✅ Group dropdown — Task 3
- ✅ First N count select — Task 4
- ✅ XL import — Task 5 (frontend) + Task 1 (backend)
- ✅ Tab preview debounce — Task 6

**No placeholders:** All steps have exact code.

**Type consistency:**
- `_wrGetFilteredProfiles()` defined in Task 3, used in Tasks 3 and 4 ✅
- `_wrPopulateGroupFilter()` defined and called in Task 3 ✅
- `_wrPreviewTabsDebounced()` defined and called in Task 6 ✅
- `_wrSelectedProfiles` (Set of string IDs) used consistently across all tasks ✅
