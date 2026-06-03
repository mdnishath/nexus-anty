# Write Review: Email Selection & Tab Preview Performance

Date: 2026-05-11

## Problem

1. **Email selection is tedious** — users with 300+ profiles in a group must search manually and check one by one to pick e.g. 200 accounts.
2. **Tab preview is slow** — "Select All" on 200+ tabs fires one API call per tab, causing severe lag.

---

## Feature 1: Profile Selection Toolbar

### UI Change

Add a compact toolbar row above the profile list in the Write Review modal (Sheet mode), between the "Pick profiles that will post" label and the existing search input:

```
[Group: All ▼]  [First N: ___ ]  [Apply]  [📁 Import from XL]
```

### Group Dropdown

- Populated from unique `group` values in `_wrAllProfiles` at load time.
- Default option: "All" (no group filter).
- Selecting a group filters the visible profile list (same effect as searching by group).

### N Input + Apply Button

- Number input. User types e.g. `200`.
- On Apply: clears `_wrSelectedProfiles`, then selects the first N profiles from the currently filtered group, adds their IDs to `_wrSelectedProfiles`, re-renders the list.
- If N > available profiles in group, selects all.

### Import from XL Button

- Opens Electron file dialog filtered to `.xlsx`, `.xls`.
- Sends selected file path to new backend endpoint: `POST /api/profiles/write-review/import-emails`
  - Body: `{ file_path: "..." }`
  - Backend reads the first column (or column named `Email`/`email`) from the first sheet.
  - Cross-references emails against all profiles in the DB.
  - Returns: `{ success: true, matched_ids: ["id1", ...], matched_count: N, not_found: ["x@y.com", ...] }`
- Frontend checks all `matched_ids` in `_wrSelectedProfiles`, re-renders list, shows toast: `"N profiles selected from XL (M emails not found)"`.

---

## Feature 2: Tab Preview Debounce

### Root Cause

`wrSelectAllTabsBtn` iterates every checkbox and calls `_wrToggleTab(cb)` synchronously. `_wrToggleTab` immediately calls `_wrPreviewTabs()`, which makes a POST API request. Result: 200 simultaneous API calls when "All" is clicked.

### Fix

Introduce a debounced wrapper around `_wrPreviewTabs`:

```js
let _wrPreviewDebounceTimer = null;
function _wrPreviewTabsDebounced() {
    if (_wrPreviewDebounceTimer) clearTimeout(_wrPreviewDebounceTimer);
    _wrPreviewDebounceTimer = setTimeout(_wrPreviewTabs, 300);
}
```

Replace all `_wrPreviewTabs()` calls inside `_wrToggleTab` with `_wrPreviewTabsDebounced()`.

Result: rapid checkbox changes (e.g. "Select All" on 200 tabs) batch into a single API call fired 300ms after the last change.

---

## Files Changed

| File | Change |
|------|--------|
| `renderer/modules/profiles.js` | Add group dropdown, N+Apply logic, XL import handler, debounce fix |
| `renderer/index.html` | Add toolbar HTML above `wrProfileSearch` |
| `backend/routes/tools.py` or new `backend/routes/reviews.py` | New `POST /api/profiles/write-review/import-emails` endpoint |

---

## Out of Scope

- Sorting profiles within a group before "First N" selection (uses existing sort: alphabetical by email).
- Persisting the selected group/count between modal opens.
