# Run Ops Modal Redesign + Name Change Operation — Design

**Date:** 2026-05-13
**Status:** Draft, awaiting user sign-off

## Goal

1. Redesign the Run Operations modal in the Electron app for better UX — current layout (left profile rail + right scrolling list of all op steps) gets cluttered as more ops land. Move to a tabbed three-column layout that scales.
2. Add the **Name Change** operation (Op 8) to the redesigned modal's UI. Backend, runner, and parameter handling already exist; only UI wiring + write-back to profile are missing.
3. Persist the resulting First/Last Name into the profile's Credentials tab so the value sticks across runs.

## Non-goals

- Adding new step2 operations beyond Op 8.
- Changing the name-change Playwright flow itself (already implemented in `step2/operations/name_change.py` → `test_operations.change_name`).
- Changing other modals (Health Activity, Write Review, Drive Backup).
- Changing the Excel-driven step2 runner (this is the per-profile UI-driven path).

## Current state (what already works)

- `step2/operations/name_change.py` — re-exports `change_name`.
- `step2/runner.py:392-401` — Op 8 dispatcher reads `account['First Name']` / `account['Last Name']`.
- `shared/profile_manager.py:2911-2918` — parses `params.name_list` textarea into `_op_first_name` / `_op_last_name` per profile (currently round-robin; will become 1:1 in-order).
- `shared/profile_manager.py:3058-3060` — feeds those into the `account` dict for the runner.
- `electron-app/backend/server.py:3186-3209` — `/api/profiles/run-ops` endpoint forwards `params` untouched.
- `electron-app/renderer/modules/profiles.js:1730,1777-1792,1814-1817` — Op 8 visibility, file-load button, and param collection are already wired BUT reference DOM IDs (`runOpsParamNames`, `runOpsNameList`, `runOpsLoadNamesBtn`, `runOpsNameFileInput`, `runOpsNameCountry`) that don't exist in `index.html`.

## What's missing

1. **HTML for the redesigned Run Ops modal**, including:
   - Three-column layout (tab rail / center / profile selector).
   - Identity tab containing the Op 8 checkbox, country select, names textarea, file-load button, live mismatch counter, mapping preview.
   - Footer summary chip row + workers/stagger moved out of left column.
2. **Profile schema fields**: `first_name`, `last_name`.
3. **Credentials tab fields**: `pmFirstName`, `pmLastName` inputs + load/save wiring in `profiles.js`.
4. **Op 8 write-back** in `_run_operations_for_profile` (profile_manager.py) so successful runs save the name to the profile.
5. **Mapping logic fix**: change round-robin to 1:1 in-order, skipping extra profiles when fewer names are provided.
6. **Op 8 textarea fallback**: when blank, fall back to the profile's stored `first_name`/`last_name` so a re-run reapplies the saved value.

---

## Section 1 — Modal layout

Three-column, ~1200px wide.

```
┌──────────────────────────── Run Operations ─────────────────────────── × ─┐
│ ┌────────────┐ ┌──────────────────────────────┐ ┌─────────────────────┐ │
│ │ 🌐 Language│ │  ACTIVE TAB CONTENT           │ │ Profiles (5 / 24)   │ │
│ │ 🛡 Security│ │                               │ │ [search…]  [grp ▾]  │ │
│ │ ⭐ Reviews │ │  ☐ Op X1 — ...                │ │ [All] [None]        │ │
│ │ 👤 Identity│ │  ☐ Op X2 — ...                │ │ ─────────────────── │ │
│ │            │ │  ─ Parameters ─               │ │ ☑ profile-1         │ │
│ │            │ │  [params here]                │ │ ☑ profile-2         │ │
│ │            │ │                               │ │ ☐ profile-3 …       │ │
│ └────────────┘ └──────────────────────────────┘ └─────────────────────┘ │
│ Selected: [L1] [2a] [8]            Workers:[5]  Stagger:[3]s             │
│                                       [Cancel]   [▶ Run Operations]      │
└──────────────────────────────────────────────────────────────────────────┘
```

### Tabs

| Tab          | Icon              | Operations contained                          |
|--------------|-------------------|-----------------------------------------------|
| Language     | `fa-language`     | L1, L3                                        |
| Security     | `fa-shield-alt`   | 2a, 2b, 3a, 3b                                |
| Reviews      | `fa-star`         | R2                                            |
| Identity     | `fa-user`         | Op 8 (Name Change)                            |

- Active tab: left accent bar in `var(--primary)`, background `rgba(99,102,241,0.08)`.
- Inactive tab hover: background `rgba(99,102,241,0.04)`.
- Per-tab badge (top-right of tab label) shows count of checked ops in that tab; hidden when zero.
- Tab switch is purely a visibility toggle — checked state of ops in other tabs is preserved.

### Center pane

- Shows only the active tab's panel (one of four panels, others `display:none`).
- Each panel: an ops checkbox list at top, then a `─ Parameters ─` divider, then any params relevant to checked ops in that tab.
- Params for ops in other tabs are NOT shown here even when checked — keeps each tab self-contained.

### Right pane (profiles)

- Unchanged from today functionally: search input, group filter dropdown, All/None buttons, scrollable checkbox list, pagination.
- Header shows `Profiles (selected / total)` instead of the old "X selected" footer text.

### Footer

- **Op summary row**: small chips for each currently-checked op across all tabs, one chip per op showing the op code (e.g. `[L1] [2a] [8]`). Empty state: dimmed "No operations selected".
- **Workers / Stagger inputs**: moved here from the old left column (always visible regardless of active tab).
- Cancel / Run buttons on the right.

---

## Section 2 — Identity tab (Op 8)

```
┌────────────────────────────────────────────────┐
│ 👤 Identity                                    │
│  ☑ Op 8 — Change Display Name                  │
│     Changes First + Last name on Google        │
│     Account. Each profile gets one line.       │
│                                                │
│  ─── Names (one per line) ─────────────────────│
│  Country: [United States ▾]                    │
│  ┌──────────────────────────────────────────┐  │
│  │ John Smith                               │  │
│  │ Maria Garcia                             │  │
│  │ Ahmed Khan                               │  │
│  └──────────────────────────────────────────┘  │
│  [📂 Load from .txt]    3 names · 5 profiles   │
│  ⚠ Will run on 3/5 — last 2 skipped            │
│                                                │
│  Mapping preview:                              │
│  ┌──────────────────────────────────────────┐  │
│  │ 1. john.doe@gmail.com    → John Smith    │  │
│  │ 2. mary.acct@gmail.com   → Maria Garcia  │  │
│  │ 3. ahmed.k@gmail.com     → Ahmed Khan    │  │
│  │ 4. user4@gmail.com       → SKIP          │  │
│  │ 5. user5@gmail.com       → SKIP          │  │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

### DOM IDs

- `runOpsTabIdentity` — tab button in the rail.
- `runOpsPanelIdentity` — panel container in the center.
- `runOpsOp8` — the Op 8 checkbox (class `runops-op`, value `8`).
- `runOpsNameCountry` — `<select>` of country codes (US, FR, UK, IN, …). Same options as the existing `change_name` flow expects.
- `runOpsNameList` — `<textarea>` for one name per line.
- `runOpsLoadNamesBtn` + `runOpsNameFileInput` — load from `.txt` (existing handler stays).
- `runOpsNameCounter` — `<span>` showing "N names · M profiles".
- `runOpsNameMismatch` — warning text, visible only when `N != M`.
- `runOpsNameMapping` — `<details open>` collapsible table; populated live.

### Mapping rules

- Order = the current order of the profile list on the right (post-search, post-group filter, current page included as well as other pages — full filtered list, not just visible page).
- `effective = min(name_count, profile_count)` — only the first `effective` profiles receive a name; the rest are excluded from this run.
- Each name line: split on the first whitespace. `parts[0]` = First Name, `parts[1..]` joined = Last Name (so "John von Neumann" → First="John", Last="von Neumann").
- Empty lines ignored.

### Live updates

- Listeners: textarea `input`, profile checkbox change, search input change, group filter change → all trigger `_updateNameMapping()`.
- `_updateNameMapping()` rebuilds the counter, mismatch warning, and mapping table.

### Submit-time payload

`/api/profiles/run-ops` body when Op 8 is checked:
```json
{
  "profile_ids": ["id-1","id-2","id-3","id-4","id-5"],
  "operations": "8",
  "params": {
    "name_list": "John Smith\nMaria Garcia\nAhmed Khan",
    "name_country": "US"
  },
  "num_workers": 5,
  "stagger_delay": 3
}
```

**The frontend sends ALL selected profile IDs.** Skip logic is purely a UI preview — the backend trims to `min(names, profiles)` itself when distributing.

---

## Section 3 — Credentials tab (profile edit popup)

### New fields in `electron-app/renderer/index.html`

Inserted right after `pmEmail` (line 840), before the Password/TOTP row:

```html
<div class="form-group" style="border:1px solid rgba(99,102,241,0.18);
     border-radius:6px;padding:8px 10px;margin-bottom:10px;">
  <label style="font-size:11px;color:#94a3b8;
         text-transform:uppercase;letter-spacing:0.5px;">
     Account Holder Name
  </label>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:6px;">
    <div>
      <label style="font-size:11px;color:#64748b;">First Name</label>
      <input type="text" id="pmFirstName" placeholder="John">
    </div>
    <div>
      <label style="font-size:11px;color:#64748b;">Last Name</label>
      <input type="text" id="pmLastName" placeholder="Smith">
    </div>
  </div>
</div>
```

### JS wiring (`electron-app/renderer/modules/profiles.js`)

- **Open profile** (~line 761): `_setVal('pmFirstName', p.first_name || ''); _setVal('pmLastName', p.last_name || '');`
- **Save profile** (~line 1045 create, plus the equivalent update block): include `first_name: _val('pmFirstName').trim(), last_name: _val('pmLastName').trim()`.
- **Reset form** (~line 798): clear both new inputs.

### Backend schema

`shared/profile_manager.py`:

1. `create_profile()` (~line 778): add `'first_name': '',  'last_name': '',` to the profile dict.
2. `update_profile()` allowed-set (line 818): add `'first_name', 'last_name'`.
3. `_run_operations_for_profile` account-building block (line 3059-3060): fall back to profile's stored name when textarea didn't supply one:
   ```python
   'First Name': profile.get('_op_first_name', '') or profile.get('first_name', ''),
   'Last Name':  profile.get('_op_last_name', '')  or profile.get('last_name', ''),
   ```
4. `_run_operations_for_profile` op-result write-back (after the op 6a branch at ~line 3160): add
   ```python
   elif op == '8' and result_str is True:
       fn = account.get('First Name', '')
       ln = account.get('Last Name', '')
       if fn:
           credentials_changed['first_name'] = fn
       if ln:
           credentials_changed['last_name'] = ln
   ```
   The existing `update_profile(profile['id'], **credentials_changed)` at line 3183 persists it.

### Distribution-logic fix (profile_manager.py:2911-2918)

Replace round-robin with truncating 1:1:
```python
if params and params.get('name_list'):
    name_lines = [ln.strip() for ln in
                  params['name_list'].strip().split('\n') if ln.strip()]
    if name_lines:
        n = min(len(name_lines), len(available))
        for i in range(n):
            name = name_lines[i]
            parts = name.split(None, 1)
            available[i]['_op_first_name'] = parts[0] if parts else ''
            available[i]['_op_last_name']  = parts[1] if len(parts) > 1 else ''
        # Trim profiles beyond the name count when Op 8 is in the op set
        if '8' in (operations or '').split(','):
            available = available[:n]
```

The `'8' in ops` guard ensures other ops (e.g. running `2a` alongside `8`) don't drop profiles when the name list is short — but the docstring will note that mixing Op 8 with other ops while supplying fewer names than profiles will drop the trailing profiles for ALL ops in the run. That's the simplest correct behavior; users who don't want that should run Op 8 separately. (UI will surface this in the mismatch warning text when other ops are also checked.)

---

## Section 4 — Files touched

| File                                                   | Change                                                                 |
|--------------------------------------------------------|------------------------------------------------------------------------|
| `electron-app/renderer/index.html`                     | Replace Run Ops modal body; add `pmFirstName`/`pmLastName` in Credentials tab |
| `electron-app/renderer/modules/profiles.js`            | Tab-switch handler; live mapping updater; Op 8 panel wiring; load/save First/Last Name in profile popup |
| `electron-app/renderer/styles.css`                     | Tab rail styles (`.runops-tab`, `.runops-tab.active`); chip styles (`.runops-op-chip`); mapping table styles |
| `shared/profile_manager.py`                            | Add `first_name`/`last_name` to schema + allowed-fields; Op 8 write-back; 1:1 truncating distribution |
| `E:/NST Anty Android/` (mirror copy)                   | After committing in worktree, copy the four files above to the main directory per `MEMORY.md` workflow_main_directory rule |

No backend route changes — `/api/profiles/run-ops` already accepts `name_list`/`name_country` in `params`.

## Section 5 — Error handling

- **Op 8 checked, textarea empty, no profile has stored name** → block submit, toast "Op 8 needs at least one name (textarea is empty and selected profiles have no stored name)".
- **Op 8 checked, textarea has names, no profiles selected** → existing "No profiles selected" toast covers it.
- **Op 8 checked, name count > profile count** → silently truncate names (no warning needed; user gave more names than profiles, extras simply unused).
- **Op 8 checked alongside other ops, name count < profile count** → mismatch warning mentions all ops will run only on first N profiles. UI: yellow background warning, not a block.
- **Profile-level Op 8 failure** → existing `op_results[op] = 'FAILED'` path. `credentials_changed['first_name']` NOT set, so profile JSON is not touched for that row.

## Section 6 — Testing

- **Manual UI**: open modal, switch each tab, check ops in different tabs, verify summary chip row updates, verify only relevant params show per tab, verify mapping preview updates live.
- **Manual flow**: select 3 profiles, check Op 8, type 2 names, verify warning + preview show "1 SKIP", click Run, verify profile JSON for the two run profiles has updated `first_name`/`last_name`, verify the Credentials tab on profile open shows the new value.
- **Re-run with empty textarea**: profile with stored `first_name="John"` → Op 8 runs using "John" from profile, no toast about empty textarea.
- **Mixed ops**: Op 2a + Op 8 with 3 names + 5 profiles → run truncates to 3 profiles for the entire batch (both ops run on the same 3 profiles).
- **Profile create**: new profile defaults `first_name=""`, `last_name=""` in JSON.

## Open assumptions

- Country select options match what `change_name` Playwright flow expects. Confirmed by existing code reading `params.get('name_country', 'US')` (default US); will reuse the country list from the existing health-activity country picker if available, else hardcode US/FR/UK/IN/DE/ES.
- Profile list order on the right panel = current-filter order. If user changes search/filter after typing names, the mapping shifts (this is shown live in the preview).
