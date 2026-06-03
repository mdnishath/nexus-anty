# Per-Profile Review Stats — Design

**Date:** 2026-05-28
**Status:** Approved (sections 1-6), awaiting written-spec review
**Owner:** mdnishath (`nishatbd3388@gmail.com`)

## 1. Problem

User runs 100+ Gmail profiles posting reviews to Google Maps. Today there is no per-profile visibility into how many reviews each account has on Google: how many are Live, how many are Not Posted (rejected / removed / pending). Users currently have to open each profile by hand and inspect Google Maps' contrib page. Goal: surface those counts directly in the existing NST-style profile manager UI, with a one-click bulk refresh and a drill-down modal.

## 2. Non-goals

- Per-review share-link extraction at scan time (too slow; deferred — see §6.7).
- Backfilling historical review state from the Project_Management Google Sheet. Source of truth is the Google Maps contrib page only.
- Posting / deleting / appealing reviews. This feature is read-only.
- Multi-account aggregation (org-wide totals).

## 3. UX

### 3.1 Badge in profile row

Inserted after the email/name column in the existing NST-style table row.

```
alice@gmail.com   [ Σ 12 · ● 9 · ✕ 3 ]   ← clickable, opens modal
```

| Chip | Meaning | Color |
|---|---|---|
| Σ N | Total = live + pending + not_posted | neutral gray |
| ● N | Live | green `#22c55e` |
| ✕ N | Not Posted = pending + not_posted | red `#ef4444` |

- Never scanned → `[ — never scanned ]` muted gray.
- Login required → `[ ⚠ login required ]` muted amber.
- Tooltip: `Last scanned: <relative time>`.

### 3.2 Top-bar control

A new dropdown button sits next to the existing filter chips:

```
[ All ] [ Logged In ] [ Failed ] ...   |   [🔄 Sync Review Stats ▾]
                                            └ Scan all profiles
                                              Scan selected (N)
                                              Scan never-scanned only
```

### 3.3 Progress strip

Shown at top of profiles tab while a scan is running. Polls `/status` every 2 s. Auto-hides 3 s after `running: false`.

```
┌──────────────────────────────────────────────────────────────────┐
│ ⟳ Scanning review stats… 12/45 done · 1 skipped · 1 error  [✕]   │
│ ████████░░░░░░░░░░░░░░  Current: alice@gmail.com, bob@gmail.com  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.4 Drill-down modal

Opens on badge click. Loads from `GET /api/profiles/<id>/review-stats`.

```
┌─ alice@gmail.com — Review Stats ───────────────── [↻ Rescan] [✕] ─┐
│  Total: 12   Live: 9   Not Posted: 3                              │
│  Last scanned: 28 May 2026, 14:32                                 │
│  Filter: [All] [Live] [Not Posted] [Pending]    Search: [____]    │
│  ─────────────────────────────────────────────────────────────    │
│  ★★★★★  Joty Hotel & Restaurant       LIVE ●     3 months ago    │
│         78VX+2PM                                  [open ↗]         │
│         "Good Food"                                                │
└───────────────────────────────────────────────────────────────────┘
```

- `[open ↗]` opens the contrib URL with `?review_id=<id>` in the system default browser.
- `[↻ Rescan]` posts a scan with `{profile_ids: [this_one]}`.

## 4. Architecture

```
┌─ Renderer (profiles.js) ─────────────────────────────────────┐
│  Badge in row · Sync Review Stats button · Progress strip     │
│  Drill-down modal · Polls /status while scan runs             │
└────────────┬─────────────────────────────────────────────────┘
             │ HTTP (Flask blueprint)
             ▼
┌─ Backend routes (server.py) ─────────────────────────────────┐
│  GET  /api/profiles/review-stats                              │
│  GET  /api/profiles/<id>/review-stats                         │
│  POST /api/profiles/review-stats/scan                         │
│  GET  /api/profiles/review-stats/status                       │
│  POST /api/profiles/review-stats/cancel                       │
└────────────┬─────────────────────────────────────────────────┘
             ▼
┌─ shared/review_stats_scraper.py  (NEW) ──────────────────────┐
│  Worker pool (default 3 parallel, cap 6)                      │
│  Each worker: launch headless Playwright with profile UDD →   │
│   goto contrib → Reviews tab → scroll-load → classify →       │
│   flush every 5 profiles to review_stats.json                 │
└────────────┬─────────────────────────────────────────────────┘
             ▼
┌─ Storage ────────────────────────────────────────────────────┐
│  browser_profiles/review_stats.json  (atomic .tmp → rename)  │
│  D:-rooted storage path: one file per profile under           │
│  browser_profiles/review_stats/<profile_id>.json              │
└──────────────────────────────────────────────────────────────┘
```

## 5. Data model

`browser_profiles/review_stats.json` (E:-rooted) — one file with all profiles:

```json
{
  "version": 1,
  "profiles": {
    "<profile_id>": {
      "email": "alice@gmail.com",
      "total": 12,
      "live": 9,
      "not_posted": 2,
      "pending": 1,
      "last_scanned": "2026-05-28T14:32:11+06:00",
      "scan_status": "ok",
      "scan_error": null,
      "reviews": [
        {
          "review_id": "Ci9DQUlRQUNvZ...",
          "business": "Joty Hotel & Restaurant",
          "address": "78VX+2PM",
          "stars": 5,
          "time": "3 months ago",
          "text": "Good Food",
          "status": "live",
          "share_link": ""
        }
      ]
    }
  }
}
```

| Field | Source |
|---|---|
| `total` | `len(reviews)` |
| `live` | count of `reviews[*].status == 'live'` |
| `pending` | count of `reviews[*].status == 'pending'` |
| `not_posted` | count of `reviews[*].status == 'not_posted'` |
| Badge "Not Posted" | `pending + not_posted` (UI-side sum) |
| `scan_status` | `ok` \| `error` \| `skipped` \| `never` (implied if no entry) |
| `scan_error` | reason string when `scan_status != 'ok'`. `"timeout after 90s"`, `"not_logged_in"`, `"Profile open in foreground"`, `"profile deleted mid-scan"`, etc. |

### 5.1 D:-rooted storage fallback

If `profile_manager.get_config()['storage_path']` resolves to a D: drive (matches the documented 32KB single-write / Errno 22 limit), the scraper switches to **one file per profile** under `browser_profiles/review_stats/<profile_id>.json` so no single write exceeds the 16KB safe ceiling. The reads transparently glob the directory back into the same dict shape.

## 6. Scraper logic

Module: `shared/review_stats_scraper.py` (new file).

### 6.1 Per-profile scrape

`launch_profile_context_invisible(playwright, profile)` is a new helper inside `shared/review_stats_scraper.py` that wraps the existing `_launch_profile_context` — same fingerprint, proxy, UDD — but adds off-screen window args (see §6.6) and does not register in `profile_manager._active_browsers` (so the foreground vs scanner state remains independent). Implementation detail; not a separate refactor of `profile_manager`.

```python
async def _scrape_one_profile(playwright, profile, cancel_event) -> dict:
    ctx, bridge = await launch_profile_context_invisible(playwright, profile)
    page = await ctx.new_page()
    try:
        await page.goto('https://www.google.com/maps/contrib/',
                        wait_until='domcontentloaded', timeout=30000)

        if 'accounts.google.com' in page.url:
            return {'scan_status': 'error', 'scan_error': 'not_logged_in', ...}

        await page.wait_for_selector('div.RWPxGd[role="tablist"]', timeout=15000)
        if not await page.locator('button[role="tab"][data-tab-index="1"][aria-selected="true"]').count():
            await page.click('button[role="tab"][data-tab-index="1"]')
        await page.wait_for_selector('div.jftiEf[data-review-id]', timeout=10000)

        await _scroll_load_all(page, cancel_event)
        reviews = await page.evaluate(SCRAPE_JS)
        return _aggregate(reviews)
    finally:
        await ctx.close()
```

Wrapped in `asyncio.wait_for(..., timeout=90)` by the caller.

### 6.2 Selectors

| Element | Selector | Notes |
|---|---|---|
| Tab list root | `div.RWPxGd[role="tablist"]` | language-agnostic |
| Reviews tab | `button[role="tab"][data-tab-index="1"]` | index 1 = Reviews per observed DOM |
| Review row | `div.jftiEf[data-review-id]` | virtualised; need scroll-load |
| Business name | `.d4r55` |  |
| Business address | `.RfnDt` |  |
| Stars (aria-label) | `.kvMYJc` | `"5 stars"` → parseInt |
| Time | `.rsqaWe` |  |
| Review text | `.wiI7pd` | absent for star-only reviews |
| Live indicator A | `button.gllhef[aria-label*="Share"]` | matches `write_review.py:1278` |
| Live indicator B | `span.rsqaWe` (visible timestamp) | matches `write_review.py:1283` |
| Pending/not-posted badge | `span.SY1QMb.o2qHAc` | text contains `'pending'` → pending else not_posted |

### 6.3 Classification (mirrors `step3/operations/write_review.py:1271-1296`)

```
if hasShare || hasTime           → live
else if badge contains 'pending' → pending
else                              → not_posted
```

### 6.4 Scroll-load

JS-side loop on the virtualised contrib feed:
- Resolve scroll container at runtime: first matching of `div.m6QErb.XiKgde[tabindex="-1"]`, `div.m6QErb[role="region"]`, then fall back to `window`. (Google rotates panel class suffixes occasionally; the multi-selector is a small price for resilience.)
- `scrollTo` bottom of the resolved container
- wait 800 ms
- if `document.querySelectorAll('div.jftiEf').length` unchanged for 2 consecutive rounds → done
- hard cap: 50 iterations OR `cancel_event` set OR 90 s wall-clock per profile

### 6.5 Aggregation

```python
def _aggregate(reviews) -> dict:
    counts = {'live': 0, 'pending': 0, 'not_posted': 0}
    for r in reviews:
        counts[r['status']] += 1
    return {
        'total':        len(reviews),
        'live':         counts['live'],
        'pending':      counts['pending'],
        'not_posted':   counts['not_posted'],
        'reviews':      reviews,
        'last_scanned': _iso_now(),
        'scan_status':  'ok',
        'scan_error':   None,
    }
```

### 6.6 Invisible context (StealthChrome reality)

The existing launcher uses `StealthChrome` (real NST Chrome via CDP, not Playwright-managed Chromium), so traditional `headless=True` does not apply. To keep the scrape user-invisible while preserving the same fingerprint that posted the reviews:

- Reuse `_launch_profile_context(playwright, profile)` from `profile_manager` but inject `extra_args=['--window-position=-32000,-32000', '--window-size=400,300']` via the StealthChrome `extra_args` parameter. The Chrome windows still launch but render off-screen — invisible to the user, stealth fingerprint intact, navigator.webdriver still undefined.
- Does **not** register in `_active_browsers` (transient context only).
- Closes deterministically in `finally`.
- Honours profile fingerprint (UA, viewport, locale) so Google sees the same client as when reviews were posted.

The new helper `launch_profile_context_invisible(playwright, profile)` lives inside `shared/review_stats_scraper.py` and wraps `_launch_profile_context` with the off-screen args.

### 6.7 Deferred: per-review share-link extraction

`share_link` is left `""` at scan time. Reason: extracting requires clicking each review's Share button (5-10 s × N reviews). Modal's `[open ↗]` button instead opens `https://www.google.com/maps/contrib/?review_id=<id>` which deep-links to the review in Google's own UI. On-demand share-link extraction is a future enhancement.

## 7. API endpoints

All under `/api/profiles/review-stats/*`. JSON in / JSON out, matching the existing route style in `server.py`.

### 7.1 `GET /api/profiles/review-stats`

Bulk cached fetch — fast, no scraping. Used on profile-list load.

```json
{
  "success": true,
  "stats": {
    "<profile_id>": {
      "total": 12, "live": 9, "not_posted": 2, "pending": 1,
      "last_scanned": "2026-05-28T14:32:11+06:00",
      "scan_status": "ok"
    }
  }
}
```

Counts only — no `reviews` array. Payload stays small even for 200 profiles.

### 7.2 `GET /api/profiles/<profile_id>/review-stats`

Single profile, full record incl. `reviews` array (for drill-down modal). Same shape as a single entry under `profiles.<profile_id>` in `review_stats.json` (see §5).

```json
{
  "success": true,
  "stats": {
    "email": "alice@gmail.com",
    "total": 12, "live": 9, "not_posted": 2, "pending": 1,
    "last_scanned": "2026-05-28T14:32:11+06:00",
    "scan_status": "ok",
    "scan_error": null,
    "reviews": [ { "review_id": "...", "business": "...", "stars": 5, "time": "...", "text": "...", "status": "live", "share_link": "" } ]
  }
}
```

Or `404 { "success": false, "message": "Never scanned" }` if missing.

### 7.3 `POST /api/profiles/review-stats/scan`

Start a bulk scan.

```json
// request
{ "profile_ids": ["id1","id2"] | null, "num_workers": 3 }
// 200
{ "success": true, "queued": 45 }
// 409
{ "success": false, "message": "Scan already running" }
```

- `profile_ids: null` → scan all profiles.
- `num_workers` clamped to `[1, 6]`. Default 3.

### 7.4 `GET /api/profiles/review-stats/status`

Polled by UI every 2 s while scan runs.

```json
{
  "running": true,
  "total": 45, "done": 12, "ok": 10, "skipped": 1, "errors": 1,
  "current": ["alice@gmail.com", "bob@gmail.com"],
  "started_at": "2026-05-28T14:30:00+06:00"
}
```

### 7.5 `POST /api/profiles/review-stats/cancel`

```json
{ "success": true }
```

Sets the cancel event. In-flight scrapes finish their current profile before stopping (no mid-scrape abort).

## 8. Concurrency & edge cases

### 8.1 Worker pool

Pattern matches `profile_manager.batch_login`:

```python
_scan_status = {
    'running': False, 'cancel_event': threading.Event(),
    'total': 0, 'done': 0, 'ok': 0, 'skipped': 0, 'errors': 0,
    'current': [], 'started_at': None, 'thread': None,
}
```

Single coordinator thread drives an `asyncio.Semaphore(num_workers)`. Each worker holds one headless context at a time and closes it before picking the next profile. Workers update `_scan_status` under a lock as they finish.

### 8.2 Profile already launched in foreground → SKIP

Before launching the headless context, check `profile_manager._active_browsers[profile_id]`. If present:

- `scan_status='skipped'`, `scan_error="Profile open in foreground"`
- Move on; do NOT contend for the user-data folder (Chromium can't share a UDD across two contexts → cookie corruption).

### 8.3 Per-profile timeout — 90 s

`asyncio.wait_for(_scrape_one_profile(...), timeout=90)`. On timeout:

- `scan_status='error'`, `scan_error='timeout after 90s'`
- Context force-closed in `finally`.

### 8.4 Cancel handling

`cancel_event.set()` checked at:
- Top of the coordinator loop before dispatching each new profile.
- Inside `_scroll_load_all` between iterations.

In-flight scrapes complete their current profile. Once the last worker returns, coordinator sets `running=false`.

### 8.5 File-lock on `review_stats.json`

- `threading.Lock` shared between read and write paths.
- Coordinator flushes every 5 completed profiles + at end of scan + on cancel.
- Atomic write: serialize to `review_stats.json.tmp` → `os.replace` → final.

### 8.6 Backend-restart resilience

`_scan_status` is in-memory only. On restart: `running=false`, partial results already flushed to JSON are preserved. User can re-click Sync to resume.

### 8.7 Race: profile deleted mid-scan

Each worker re-reads the profile by ID before launching. If `None`:

- `scan_status='skipped'`, `scan_error="profile deleted mid-scan"`

### 8.8 Not-logged-in detection

After `goto('/contrib/')`, if final URL contains `accounts.google.com`:

- `scan_status='error'`, `scan_error='not_logged_in'`
- UI badge: `[ ⚠ login required ]` amber.

## 9. Performance estimates

| Profiles | Workers | Per-profile avg | Wall time |
|---|---|---|---|
| 10 | 3 | 20 s | ~70 s |
| 50 | 3 | 20 s | ~5.5 min |
| 100 | 3 | 20 s | ~11 min |
| 100 | 6 | 20 s | ~6 min |
| 200 | 6 | 20 s | ~12 min |

(Assuming ~20 s per profile: 5 s navigation, 8 s scroll-load, 7 s extract+close. Real-world will vary with reviews-per-profile and proxy latency.)

## 10. Files touched

| File | Change |
|---|---|
| `shared/review_stats_scraper.py` | **NEW** — scraper + worker pool + status |
| `electron-app/backend/server.py` | **EDIT** — 5 new routes under `/api/profiles/review-stats/*` |
| `electron-app/renderer/modules/profiles.js` | **EDIT** — badge render, Sync button, progress strip, drill-down modal, status poll |
| `electron-app/renderer/styles.css` (or inline `<style>` in `index.html`) | **EDIT** — badge / progress-strip / modal styles |
| `browser_profiles/review_stats.json` | **NEW (runtime)** — persistent cache |
| `docs/superpowers/specs/2026-05-28-per-profile-review-stats-design.md` | **NEW** — this spec |

No changes to existing scraping code in `step3/operations/write_review.py` — its classification logic is mirrored, not invoked, so we don't perturb the live-posting flow.

## 11. Out-of-scope follow-ups

1. On-demand share-link extraction per review (modal action button).
2. Scheduled auto-rescan (e.g. every 24 h via cron-like task).
3. Cross-reference contrib counts against Project_Management sheet rows to detect "posted in sheet but missing on Google" anomalies.
4. CSV/Excel export of review stats.
