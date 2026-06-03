# Batch Login Skip Existing Profiles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before batch login, filter out any Excel row whose Gmail already has an existing profile — skip those silently and only login for new accounts.

**Architecture:** Filter happens in `batch_login()` after parsing the Excel rows and before dispatching the worker thread, so `total` only ever reflects new accounts. The preview endpoint also checks existing profiles and returns a `skipped` count so the UI can warn the user before they start.

**Tech Stack:** Python (Flask backend), JavaScript (Electron renderer)

---

## Files Modified

- `shared/profile_manager.py` — `batch_login()`: filter existing emails before dispatch
- `electron-app/backend/server.py` — `profiles_batch_login_preview()`: return `skipped` count
- `electron-app/renderer/modules/profiles.js` — `_setBatchPreview()`: show skipped count

---

### Task 1: Filter existing profiles in `batch_login()`

**Files:**
- Modify: `shared/profile_manager.py:1188-1211`

- [ ] **Step 1: Add email filter after accounts list is built**

In `profile_manager.py`, find this block (around line 1188):
```python
    if not accounts:
        return {'success': False, 'error': 'No valid accounts found in file'}

    _log(f"Batch login: {len(accounts)} accounts, ...")
```

Replace with:
```python
    if not accounts:
        return {'success': False, 'error': 'No valid accounts found in file'}

    # Skip accounts whose email already has an existing profile
    from shared import nexus_profile_manager as _npm
    existing_emails = {p.get('email', '').lower() for p in _npm.list_profiles()}
    skipped_accounts = [a for a in accounts if a['email'].lower() in existing_emails]
    accounts = [a for a in accounts if a['email'].lower() not in existing_emails]
    if skipped_accounts:
        _log(f"Batch login: skipping {len(skipped_accounts)} existing profiles: {[a['email'] for a in skipped_accounts]}")

    if not accounts:
        return {'success': False, 'error': 'All accounts already have existing profiles — nothing to login'}

    _log(f"Batch login: {len(accounts)} accounts, {num_workers} workers, engine={engine}, os={os_type}, group={group}")
```

- [ ] **Step 2: Verify manually**

Start the app, pick an Excel where 1+ emails already have profiles. Start batch login. Confirm those emails do not appear in the browser session log and `total` count is reduced.

- [ ] **Step 3: Commit**

```bash
git add shared/profile_manager.py
git commit -m "feat(batch-login): skip accounts whose email already has an existing profile"
```

---

### Task 2: Return `skipped` count from preview endpoint

**Files:**
- Modify: `electron-app/backend/server.py:2769-2788`

- [ ] **Step 1: Update preview route to check existing emails**

Find `profiles_batch_login_preview()` (line ~2769). Replace the entire function body:

```python
@app.route('/api/profiles/batch-login-preview', methods=['POST'])
def profiles_batch_login_preview():
    """Read Excel and return count of valid accounts without running login."""
    data = request.get_json(force=True, silent=True) or {}
    file_path = data.get('file_path', '').strip()
    if not file_path or not os.path.isfile(file_path):
        return jsonify({'success': False, 'message': 'File not found'})
    try:
        df = pd.read_excel(file_path)
        total = len(df)
        existing_emails = {p.get('email', '').lower() for p in profile_manager.list_profiles()}
        valid = 0
        skipped = 0
        for _, row in df.iterrows():
            email = str(row.get('Email', '')).strip()
            password = str(row.get('Password', '')).strip()
            if email and password and email.lower() != 'nan' and password.lower() != 'nan':
                valid += 1
                if email.lower() in existing_emails:
                    skipped += 1
        cols = list(df.columns)
        return jsonify({'success': True, 'total': total, 'valid': valid, 'skipped': skipped, 'columns': cols})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
```

- [ ] **Step 2: Commit**

```bash
git add electron-app/backend/server.py
git commit -m "feat(batch-login): include skipped count in preview endpoint"
```

---

### Task 3: Show skipped count in preview panel (UI)

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js:1533-1548`

- [ ] **Step 1: Update `_setBatchPreview()` to show skipped info**

Find `_setBatchPreview(info)` (line ~1533). Replace the `el.innerHTML = ...` assignment (the success branch, after `el.style.display = 'flex';`):

```javascript
        el.innerHTML = `
            <span style="color:#4ade80;"><i class="fas fa-file-excel"></i> <strong>${info.valid}</strong> valid accounts</span>
            ${(info.skipped > 0) ? `<span style="color:#f59e0b;font-size:11px;">· ${info.skipped} already exist (will be skipped) · <strong>${info.valid - info.skipped}</strong> new</span>` : ''}
            ${info.valid !== info.total ? `<span style="color:#64748b;font-size:11px;">(${info.total} total rows, ${info.total - info.valid} skipped)</span>` : ''}
            <span style="color:#64748b;font-size:11px;">${info.columns && info.columns.includes('Proxy') ? '· Proxy column detected' : ''}</span>
        `;
```

- [ ] **Step 2: Commit**

```bash
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(batch-login): show already-exist skip count in preview panel"
```
