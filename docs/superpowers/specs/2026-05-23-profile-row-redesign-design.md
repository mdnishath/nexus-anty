# Profile Row Redesign — Design Spec

**Date:** 2026-05-23
**Scope:** Profile Manager table row layout — credentials inline, proxy country, live 2FA, editable group dropdown.

## Goal

Reduce the friction of opening the edit modal for routine read/copy tasks. Make email, password, country, and the current 2FA code one click away from every row, and make group reassignment a single dropdown change with no page flash.

## Current vs. proposed columns

Current row (defined in `electron-app/renderer/modules/profiles.js` ~line 211):

| Col | Width | Content |
|---|---|---|
| Check | 24px | Selection checkbox |
| Profile | flex 2 | OS badge + engine tag + name; email subtitle underneath |
| Proxy | flex 1.5 | `host:port` or `No proxy` |
| Status | auto | Logged In / Failed / Not Logged In + Open/Launching |
| Group | 80px | Static group pill |
| Activity | 160px | Last appeal + last health |
| Actions | auto | Launch / Re-login / Edit / Delete / More |

Proposed row:

| Col | Width | Content |
|---|---|---|
| Check | 24px | Unchanged |
| **Profile** | flex 1.4 | OS badge + engine tag + name **only** (no email subtitle) |
| **Credentials** (new) | flex 1.8 | Email + copy button on row 1; masked password + copy button on row 2 |
| **Proxy / 2FA** | flex 1.5 | Country (flag + name) on row 1; 6-digit TOTP code + 30s countdown + copy on row 2 |
| Status | auto | Unchanged |
| **Group** (editable) | 160px | `<select>` dropdown of existing groups, at the previous Activity position |
| Actions | auto | Unchanged |

`pm-col-updated` (Activity) column is removed entirely. The old narrow `pm-col-group` pill column is removed; the editable dropdown takes the wider 160px slot.

## Credentials cell

Two stacked rows inside one flex column, similar to the existing `pm-name` / `pm-email` stack but with copy affordances:

```
nishat@example.com         [📋]
••••••••••                 [📋]
```

- Email line: full text, truncated with ellipsis if needed, full value in `title` tooltip. Copy button copies `p.email` to clipboard via `navigator.clipboard.writeText`, with `App.toast('Email copied')` confirmation.
- Password line: always shows 8 bullet characters regardless of actual length. Copy button copies `p.password` plaintext. Same toast pattern.
- Missing values: if `p.email` is empty show `—`; if `p.password` is empty hide the second line.
- Copy buttons are small `<button class="pm-copy-btn">` with `<i class="fas fa-copy">`, stop event propagation so they don't trigger row selection.

## Proxy / 2FA cell

Two stacked rows in one flex column:

```
🇺🇸 United States
123 456    ⏱ 18s    [📋]
```

### Country line

- Source: `p.proxy.country` and `p.proxy.country_code` (new fields, populated by backend lookup).
- Renderer logic:
  - If `p.proxy` is empty/missing → render `No proxy` (current behavior, single line, no 2FA row below).
  - Else if `p.proxy.country` is cached → render flag emoji + country name.
  - Else → render `<i class="fas fa-spinner fa-spin"></i> Looking up…` placeholder and enqueue a lazy lookup (see "Country lookup throttle" below).
- Flag emoji derived from ISO-2 country code by mapping each letter to a Regional Indicator Symbol (`A` = U+1F1E6, etc.) in JS — no flag image assets needed.

### Country lookup throttle

To stay under ip-api.com's 45 req/min free-tier limit, the renderer maintains a single FIFO queue of profile IDs needing lookup. A worker pulls one ID at a time, calls `GET /api/profiles/<id>/proxy-country`, updates the in-memory profile and the visible cell, then waits 1500 ms before the next call (≈40 req/min ceiling, leaving headroom). The queue persists across re-renders — pending IDs are not re-enqueued, and the worker stops naturally when the queue drains. Cached profiles never enter the queue.

### 2FA line

- Source: `p.totp_secret` (already in API response from `/api/profiles` GET — `list_profiles()` returns decrypted profiles).
- If `p.totp_secret` is empty, hide this line.
- Code computation: client-side, HMAC-SHA1 via Web Crypto API, 30-second period, 6 digits — matches `pyotp.TOTP` defaults used by `src/utils.py::TOTPGenerator`.
- Display format: 6 digits with a single space in the middle (`123 456`) for readability.
- Countdown: shows `⏱ Xs` where X = `30 - (now / 1000) % 30`, rounded down.
- Copy button copies the current code (no space) to clipboard.

### Shared timer (performance)

One `setInterval(_, 1000)` lives at the module level. Each tick:

1. Compute `secondsLeft = 30 - Math.floor(Date.now() / 1000) % 30`.
2. Update every `[data-totp-countdown]` element's text.
3. If `secondsLeft === 30` (i.e., we just crossed a boundary), recompute codes by walking `[data-totp-secret]` elements and updating `[data-totp-code]` siblings.

Code recomputation only happens once every 30 seconds across all rows. Countdown text updates are cheap (`textContent` on small spans). With 1100 rows this is well within budget.

The interval starts when the profile list is first rendered and runs until the page unloads. It is idempotent — re-rendering the list does not create extra intervals.

## Group dropdown

- `<select class="pm-group-select" data-id="...">` populated from `/api/profiles/groups` GET response (called once when the page loads, cached in module state). The profile's current group is the selected option.
- A final `+ New group…` option opens a prompt to enter a new name; on confirm, the new group is selected and persisted to the profile (the new group only exists once at least one profile is in it, so no separate "create group" call is needed — `PUT /api/profiles/<id>` with `{group: "new-name"}` is sufficient).
- On change:
  1. **Optimistically** update the in-memory profile object (`_allProfiles` entry) and the visible select; do not re-render the row.
  2. Fire `PUT /api/profiles/<id>` with `{group: newGroup}` in the background.
  3. On success, refresh the group dropdown options cache (so new groups appear in other rows).
  4. On failure, revert the select value and `App.toast(err, 'error')`.
- "No blink" means: do NOT call `loadProfiles()` after a group change. The existing implementation does this for many mutations; the new code path must not.

## Backend changes

### New endpoint: `GET /api/profiles/<id>/proxy-country`

Response (success):
```json
{
  "success": true,
  "country": "United States",
  "country_code": "US",
  "cached": false
}
```

Behavior:
- If `profile.proxy.country` and `profile.proxy.country_code` are already set, return them with `cached: true`.
- Else, resolve `profile.proxy.host` (or extract host from `profile.proxy.server`) and call `http://ip-api.com/json/<host>?fields=status,country,countryCode` over plain HTTP (free tier, no key, 45 req/min).
- On success, write `country` and `country_code` into `profile.proxy` via `profile_manager.update_profile()` and return them.
- On failure (timeout, rate limit, non-success status), return `{success: true, country: "Unknown", country_code: ""}` and **do not** cache the failure — next call retries.
- HTTP timeout: 5 seconds. Single retry on connection error.

### Optional: `POST /api/profiles/proxy-country-refresh`

For future bulk refresh; not required for the initial release. Spec deferred.

## Edge cases

- **No proxy:** Single-line "No proxy" in the cell, no 2FA row.
- **Proxy host is a hostname, not IP:** ip-api.com accepts hostnames and resolves them server-side. Works.
- **TOTP secret with spaces or dashes:** Strip both before base32 decode (matches `TOTPGenerator.generate_code` behavior).
- **Invalid TOTP secret:** Show `—` instead of the code line; log to console once per profile, don't toast.
- **Clipboard API unavailable:** Fall back to a hidden `<textarea>` + `document.execCommand('copy')` shim.
- **Group rename / delete elsewhere:** The dropdown options cache is invalidated and refreshed after any successful group mutation.
- **Sort columns:** `Activity` sort option is removed (column gone). `Group`, `Status`, `Name` sorts retained.

## Files touched

- `electron-app/renderer/modules/profiles.js` — row template (line ~190), event wiring (`_attachRowEvents`), new TOTP module, copy helpers, optimistic group update, lazy country fetch, shared timer setup.
- `electron-app/renderer/index.html` — table header columns (lines 564–571).
- `electron-app/renderer/styles.css` — new `.pm-col-creds`, `.pm-col-proxy-info` (renamed/expanded), `.pm-copy-btn`, `.pm-totp-code`, `.pm-totp-countdown`, `.pm-group-select` rules; remove `.pm-col-updated` and old `.pm-col-group` width rules.
- `electron-app/backend/server.py` — new `/api/profiles/<id>/proxy-country` route.
- `shared/profile_manager.py` — extend allowed update fields if needed so `proxy.country` / `proxy.country_code` persist via `update_profile`.

## Out of scope

- Bulk country refresh UI.
- "Hide all 2FA codes" privacy toggle.
- Multi-group display in the dropdown (current model: one selected group at a time; `groups[]` array still exists but the dropdown reads/writes only the primary group).
- Reverse: showing exit-IP country (would require routing requests through each proxy).
