# Per-Profile Review Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-profile Google Maps review stats (Total / Live / Not Posted) to the NST-style profile manager, with bulk worker-pool scrape, drill-down modal, and persistent JSON cache.

**Architecture:** Headless-equivalent (off-screen positioned) Playwright workers reuse the existing StealthChrome launcher to read each profile's `maps.google.com/contrib/` Reviews tab, classify each review live/pending/not_posted, and persist counts to `browser_profiles/review_stats.json`. Flask exposes 5 routes; renderer adds row badges, sync button, progress strip, and drill-down modal.

**Tech Stack:** Python 3 / Flask / Playwright (CDP via StealthChrome) / asyncio / pytest / vanilla JS / Electron renderer.

**Spec:** [docs/superpowers/specs/2026-05-28-per-profile-review-stats-design.md](../specs/2026-05-28-per-profile-review-stats-design.md)

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `shared/review_stats_scraper.py` | **CREATE** | Persistence, aggregation, scan-status state, worker-pool coordinator, per-profile scrape, invisible launcher |
| `tests/test_review_stats_scraper.py` | **CREATE** | Unit tests for persistence (E:/D: fallback), aggregation, scan-status + start/cancel (mocked scraper) |
| `electron-app/backend/server.py` | **MODIFY** | Add 5 routes under `/api/profiles/review-stats/*` |
| `electron-app/renderer/modules/profiles.js` | **MODIFY** | Badge fetch + render, Sync button, progress strip, drill-down modal, status poll |
| `electron-app/renderer/index.html` | **MODIFY** | Add CSS for `.pm-rs-*` badge / progress-strip / modal styles |
| `browser_profiles/review_stats.json` | runtime artifact | Persistent cache |

Each task ends with: (a) tests green, (b) commit, (c) **sync into main directory** (`E:\NST Anty Android\`) per the user's documented workflow (`workflow_main_directory.md` memory) — copy fixed files into main after every worktree commit.

---

## Task 1: Persistence — load/save round-trip

**Files:**
- Create: `shared/review_stats_scraper.py`
- Create: `tests/test_review_stats_scraper.py`

- [ ] **Step 1: Create the empty module with constants**

Create `shared/review_stats_scraper.py`:

```python
"""
shared/review_stats_scraper.py — Per-profile Google Maps review stats.

Reads each profile's /maps/contrib/ Reviews tab via a headless-equivalent
StealthChrome context, classifies each review live/pending/not_posted,
and persists per-profile counts + review records to a JSON cache.

Public API
----------
init(resources_path: Path)
    Bind the resources path so persistence finds the right folder.
get_all_stats() -> dict
    Bulk fetch of cached counts (no `reviews` array) for every profile.
get_profile_stats(profile_id: str) -> dict | None
    Single profile's full record incl. `reviews` array.
start_scan(profile_ids: list[str] | None, num_workers: int = 3) -> dict
    Kick off worker-pool scan. Returns {success, queued} or {success: False, message}.
cancel_scan() -> None
    Signal the running scan to stop (in-flight scrapes finish their current profile).
get_status() -> dict
    Snapshot of the current scan state for the UI to poll.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

STATS_FILE_NAME = 'review_stats.json'
STATS_DIR_NAME = 'review_stats'   # used when D:-rooted fallback splits per profile
SCHEMA_VERSION = 1

_resources_path: Path | None = None
_storage_path: Path | None = None    # parent of browser_profiles/, set in init()
_file_lock = threading.Lock()


def init(resources_path: Path, storage_path: Path | None = None) -> None:
    """Bind paths. `storage_path` defaults to resources_path/browser_profiles."""
    global _resources_path, _storage_path
    _resources_path = Path(resources_path)
    _storage_path = Path(storage_path) if storage_path else _resources_path / 'browser_profiles'
    _storage_path.mkdir(parents=True, exist_ok=True)


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def _stats_file() -> Path:
    assert _storage_path is not None, 'init() must be called first'
    return _storage_path / STATS_FILE_NAME


def _load_stats_raw() -> dict:
    """Read review_stats.json. Returns empty skeleton if missing."""
    p = _stats_file()
    if not p.exists():
        return {'version': SCHEMA_VERSION, 'profiles': {}}
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Backfill missing top-level keys for forward compatibility
        if 'profiles' not in data:
            data['profiles'] = {}
        if 'version' not in data:
            data['version'] = SCHEMA_VERSION
        return data
    except (json.JSONDecodeError, OSError):
        return {'version': SCHEMA_VERSION, 'profiles': {}}


def _save_stats_raw(data: dict) -> None:
    """Atomic write: serialize to .tmp → os.replace → final."""
    p = _stats_file()
    tmp = p.with_suffix(p.suffix + '.tmp')
    with _file_lock:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_review_stats_scraper.py`:

```python
"""Unit tests for shared/review_stats_scraper.py persistence."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from shared import review_stats_scraper as rss


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Each test gets its own clean storage dir."""
    rss.init(resources_path=tmp_path, storage_path=tmp_path / 'browser_profiles')
    yield


def test_load_when_file_missing_returns_empty_skeleton():
    data = rss._load_stats_raw()
    assert data == {'version': 1, 'profiles': {}}


def test_save_then_load_round_trip():
    payload = {
        'version': 1,
        'profiles': {
            'pid-1': {
                'email': 'a@gmail.com',
                'total': 3, 'live': 2, 'pending': 0, 'not_posted': 1,
                'last_scanned': '2026-05-28T14:00:00+06:00',
                'scan_status': 'ok', 'scan_error': None,
                'reviews': [],
            }
        },
    }
    rss._save_stats_raw(payload)
    assert rss._load_stats_raw() == payload


def test_save_is_atomic_no_tmp_leftover():
    rss._save_stats_raw({'version': 1, 'profiles': {}})
    stats_file = rss._stats_file()
    tmp = stats_file.with_suffix(stats_file.suffix + '.tmp')
    assert stats_file.exists()
    assert not tmp.exists()


def test_load_corrupt_json_returns_empty_skeleton():
    rss._stats_file().write_text('{not json', encoding='utf-8')
    assert rss._load_stats_raw() == {'version': 1, 'profiles': {}}


def test_load_missing_profiles_key_backfilled():
    rss._stats_file().write_text('{"version": 1}', encoding='utf-8')
    assert rss._load_stats_raw() == {'version': 1, 'profiles': {}}
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/test_review_stats_scraper.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```powershell
git add shared/review_stats_scraper.py tests/test_review_stats_scraper.py
git commit -m "feat(review-stats): persistence layer with atomic write"
```

- [ ] **Step 5: Sync into main directory**

Per `memory/workflow_main_directory.md`: copy both new files into `E:\NST Anty Android\` if working from a worktree. If already in main, skip.

---

## Task 2: Public load/save API + per-profile upsert

**Files:**
- Modify: `shared/review_stats_scraper.py`
- Modify: `tests/test_review_stats_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_review_stats_scraper.py`:

```python
def test_get_all_stats_strips_reviews_array():
    payload = {
        'version': 1,
        'profiles': {
            'pid-1': {
                'email': 'a@gmail.com',
                'total': 2, 'live': 1, 'pending': 0, 'not_posted': 1,
                'last_scanned': '2026-05-28T14:00:00+06:00',
                'scan_status': 'ok', 'scan_error': None,
                'reviews': [{'review_id': 'r1', 'business': 'X', 'status': 'live'}],
            }
        },
    }
    rss._save_stats_raw(payload)
    out = rss.get_all_stats()
    assert 'reviews' not in out['pid-1']
    assert out['pid-1']['total'] == 2
    assert out['pid-1']['live'] == 1


def test_get_profile_stats_returns_full_record():
    payload = {
        'version': 1,
        'profiles': {
            'pid-1': {
                'email': 'a@gmail.com', 'total': 1, 'live': 1,
                'pending': 0, 'not_posted': 0,
                'last_scanned': '2026-05-28T14:00:00+06:00',
                'scan_status': 'ok', 'scan_error': None,
                'reviews': [{'review_id': 'r1'}],
            }
        },
    }
    rss._save_stats_raw(payload)
    record = rss.get_profile_stats('pid-1')
    assert record is not None
    assert record['reviews'] == [{'review_id': 'r1'}]


def test_get_profile_stats_missing_returns_none():
    assert rss.get_profile_stats('missing-id') is None


def test_upsert_one_profile_preserves_others():
    rss._save_stats_raw({
        'version': 1,
        'profiles': {
            'pid-A': {'email': 'a@gmail.com', 'total': 0, 'live': 0,
                      'pending': 0, 'not_posted': 0,
                      'last_scanned': 't', 'scan_status': 'ok',
                      'scan_error': None, 'reviews': []},
        },
    })
    rss._upsert_profile_record('pid-B', {
        'email': 'b@gmail.com', 'total': 5, 'live': 4,
        'pending': 0, 'not_posted': 1,
        'last_scanned': 't', 'scan_status': 'ok',
        'scan_error': None, 'reviews': [],
    })
    out = rss._load_stats_raw()['profiles']
    assert set(out.keys()) == {'pid-A', 'pid-B'}
    assert out['pid-B']['total'] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_review_stats_scraper.py::test_get_all_stats_strips_reviews_array -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'get_all_stats'`.

- [ ] **Step 3: Implement the three functions**

Append to `shared/review_stats_scraper.py`:

```python
def get_all_stats() -> dict:
    """Return per-profile counts WITHOUT the reviews array (small payload)."""
    profiles = _load_stats_raw().get('profiles', {})
    out = {}
    for pid, rec in profiles.items():
        out[pid] = {k: v for k, v in rec.items() if k != 'reviews'}
    return out


def get_profile_stats(profile_id: str) -> dict | None:
    """Return one profile's full record incl. `reviews`. None if missing."""
    profiles = _load_stats_raw().get('profiles', {})
    return profiles.get(profile_id)


def _upsert_profile_record(profile_id: str, record: dict) -> None:
    """Insert-or-update a single profile's record. Atomic per call."""
    with _file_lock:
        data = _load_stats_raw()
        data['profiles'][profile_id] = record
        # Save without re-acquiring lock (already held)
        p = _stats_file()
        tmp = p.with_suffix(p.suffix + '.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
```

Note: `_upsert_profile_record` re-implements the atomic write inline because `_file_lock` is non-reentrant; calling `_save_stats_raw` would deadlock.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_review_stats_scraper.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```powershell
git add shared/review_stats_scraper.py tests/test_review_stats_scraper.py
git commit -m "feat(review-stats): public read API + per-profile upsert"
```

- [ ] **Step 6: Sync into main directory**

---

## Task 3: Aggregation function

**Files:**
- Modify: `shared/review_stats_scraper.py`
- Modify: `tests/test_review_stats_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_review_stats_scraper.py`:

```python
def test_aggregate_mixed_statuses():
    reviews = [
        {'review_id': 'r1', 'business': 'A', 'status': 'live'},
        {'review_id': 'r2', 'business': 'B', 'status': 'live'},
        {'review_id': 'r3', 'business': 'C', 'status': 'pending'},
        {'review_id': 'r4', 'business': 'D', 'status': 'not_posted'},
        {'review_id': 'r5', 'business': 'E', 'status': 'not_posted'},
    ]
    out = rss._aggregate(reviews)
    assert out['total'] == 5
    assert out['live'] == 2
    assert out['pending'] == 1
    assert out['not_posted'] == 2
    assert out['scan_status'] == 'ok'
    assert out['scan_error'] is None
    assert out['reviews'] == reviews
    assert 'last_scanned' in out and out['last_scanned']


def test_aggregate_empty_list_returns_zero_counts():
    out = rss._aggregate([])
    assert out['total'] == 0
    assert out['live'] == 0
    assert out['pending'] == 0
    assert out['not_posted'] == 0
    assert out['reviews'] == []
    assert out['scan_status'] == 'ok'


def test_aggregate_unknown_status_falls_into_not_posted_bucket():
    reviews = [{'review_id': 'r1', 'business': 'A', 'status': 'gibberish'}]
    out = rss._aggregate(reviews)
    assert out['not_posted'] == 1
    assert out['live'] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_review_stats_scraper.py::test_aggregate_mixed_statuses -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_aggregate'`.

- [ ] **Step 3: Implement `_aggregate`**

Append to `shared/review_stats_scraper.py`:

```python
def _aggregate(reviews: list[dict]) -> dict:
    """Count statuses and return the aggregated record shape persisted in
    review_stats.json. Unknown statuses fall into not_posted (defensive)."""
    counts = {'live': 0, 'pending': 0, 'not_posted': 0}
    for r in reviews:
        s = r.get('status', 'not_posted')
        if s not in counts:
            s = 'not_posted'
        counts[s] += 1
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_review_stats_scraper.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```powershell
git add shared/review_stats_scraper.py tests/test_review_stats_scraper.py
git commit -m "feat(review-stats): aggregate(reviews) -> counted record"
```

- [ ] **Step 6: Sync into main directory**

---

## Task 4: Scan-status state + start/cancel (mocked scraper)

**Files:**
- Modify: `shared/review_stats_scraper.py`
- Modify: `tests/test_review_stats_scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_review_stats_scraper.py`:

```python
import time
from unittest.mock import patch


def _wait_idle(timeout=5.0):
    """Spin until scan_status['running'] is False or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not rss.get_status()['running']:
            return
        time.sleep(0.05)
    raise AssertionError('scan did not finish in time')


def test_get_status_idle_defaults():
    status = rss.get_status()
    assert status['running'] is False
    assert status['total'] == 0
    assert status['done'] == 0


def test_start_scan_with_no_profiles_returns_zero_queued():
    with patch.object(rss, '_list_target_profiles', return_value=[]):
        res = rss.start_scan(profile_ids=[], num_workers=1)
    assert res == {'success': True, 'queued': 0}
    _wait_idle()


def test_start_scan_rejects_when_already_running():
    # Force the running flag on, then attempt to start again
    rss._scan_status['running'] = True
    try:
        res = rss.start_scan(profile_ids=None, num_workers=1)
        assert res == {'success': False, 'message': 'Scan already running'}
    finally:
        rss._scan_status['running'] = False


def test_scan_calls_scrape_per_profile_and_persists():
    fake_profiles = [
        {'id': 'pid-A', 'email': 'a@gmail.com'},
        {'id': 'pid-B', 'email': 'b@gmail.com'},
    ]

    async def fake_scrape(playwright, profile, cancel_event):
        return {
            'total': 1, 'live': 1, 'pending': 0, 'not_posted': 0,
            'reviews': [{'review_id': 'r1', 'business': 'X', 'status': 'live'}],
            'last_scanned': '2026-05-28T14:00:00+06:00',
            'scan_status': 'ok', 'scan_error': None,
        }

    with patch.object(rss, '_list_target_profiles', return_value=fake_profiles), \
         patch.object(rss, '_scrape_one_profile', side_effect=fake_scrape):
        res = rss.start_scan(profile_ids=None, num_workers=2)
        assert res['success'] is True
        assert res['queued'] == 2
        _wait_idle()

    saved = rss._load_stats_raw()['profiles']
    assert set(saved.keys()) == {'pid-A', 'pid-B'}
    assert saved['pid-A']['total'] == 1
    final = rss.get_status()
    assert final['running'] is False
    assert final['done'] == 2
    assert final['ok'] == 2
    assert final['errors'] == 0


def test_cancel_during_scan_sets_event(monkeypatch):
    seen = {'cancelled': False}

    async def fake_scrape(playwright, profile, cancel_event):
        # Wait briefly to give the test time to call cancel
        for _ in range(20):
            if cancel_event.is_set():
                seen['cancelled'] = True
                break
            import asyncio
            await asyncio.sleep(0.05)
        return {
            'total': 0, 'live': 0, 'pending': 0, 'not_posted': 0,
            'reviews': [], 'last_scanned': 't',
            'scan_status': 'ok', 'scan_error': None,
        }

    fake_profiles = [{'id': 'pid-X', 'email': 'x@gmail.com'}]
    with patch.object(rss, '_list_target_profiles', return_value=fake_profiles), \
         patch.object(rss, '_scrape_one_profile', side_effect=fake_scrape):
        rss.start_scan(profile_ids=None, num_workers=1)
        time.sleep(0.1)
        rss.cancel_scan()
        _wait_idle()

    assert seen['cancelled'] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_review_stats_scraper.py -v`
Expected: FAIL — `_scan_status`, `start_scan`, `cancel_scan`, `get_status`, `_list_target_profiles`, `_scrape_one_profile` undefined.

- [ ] **Step 3: Add module-level state + coordinator**

Append to `shared/review_stats_scraper.py`:

```python
import asyncio

_scan_status_lock = threading.Lock()
_scan_status: dict = {
    'running': False,
    'total': 0, 'done': 0, 'ok': 0, 'skipped': 0, 'errors': 0,
    'current': [],
    'started_at': None,
    'cancel_event': threading.Event(),
    'thread': None,
}


def get_status() -> dict:
    """Snapshot of scan state — safe to call from Flask routes."""
    with _scan_status_lock:
        # Strip the threading objects; UI doesn't need them
        return {k: v for k, v in _scan_status.items()
                if k not in ('cancel_event', 'thread')}


def cancel_scan() -> None:
    with _scan_status_lock:
        _scan_status['cancel_event'].set()


def _list_target_profiles(profile_ids: list[str] | None) -> list[dict]:
    """Resolve profile IDs to profile dicts via profile_manager.
    Returns the dicts in the same order as profile_ids. Missing IDs skipped.
    `None` means 'every profile'."""
    from shared import profile_manager as pm
    all_profiles = pm.list_profiles()
    by_id = {p.get('id'): p for p in all_profiles}
    if profile_ids is None:
        return all_profiles
    return [by_id[pid] for pid in profile_ids if pid in by_id]


def start_scan(profile_ids: list[str] | None, num_workers: int = 3) -> dict:
    """Spawn a coordinator thread that drives an asyncio worker pool.
    Returns immediately. Idempotency: 409-equivalent dict if already running."""
    with _scan_status_lock:
        if _scan_status['running']:
            return {'success': False, 'message': 'Scan already running'}

        targets = _list_target_profiles(profile_ids)
        num_workers = max(1, min(int(num_workers or 3), 6))

        _scan_status['running'] = True
        _scan_status['total'] = len(targets)
        _scan_status['done'] = 0
        _scan_status['ok'] = 0
        _scan_status['skipped'] = 0
        _scan_status['errors'] = 0
        _scan_status['current'] = []
        _scan_status['started_at'] = _iso_now()
        _scan_status['cancel_event'] = threading.Event()

    t = threading.Thread(
        target=_coordinator_thread,
        args=(targets, num_workers, _scan_status['cancel_event']),
        daemon=True,
        name='review-stats-scan',
    )
    with _scan_status_lock:
        _scan_status['thread'] = t
    t.start()

    return {'success': True, 'queued': len(targets)}


def _coordinator_thread(targets: list[dict], num_workers: int,
                       cancel_event: threading.Event) -> None:
    try:
        asyncio.run(_run_pool(targets, num_workers, cancel_event))
    finally:
        with _scan_status_lock:
            _scan_status['running'] = False
            _scan_status['current'] = []
            _scan_status['thread'] = None


async def _run_pool(targets: list[dict], num_workers: int,
                    cancel_event: threading.Event) -> None:
    """Async worker pool driven by a Semaphore. One Playwright instance
    is shared across workers (it's a thread-safe factory)."""
    from playwright.async_api import async_playwright
    from shared import profile_manager as pm
    sem = asyncio.Semaphore(num_workers)

    async with async_playwright() as playwright:
        async def _one(profile: dict) -> None:
            if cancel_event.is_set():
                return
            email = profile.get('email', '?')
            pid = profile.get('id')
            async with sem:
                if cancel_event.is_set():
                    return

                # §8.7: profile may have been deleted between queue time and scrape time
                if pm.get_profile(pid) is None:
                    _upsert_profile_record(pid, {
                        'email': email,
                        'total': 0, 'live': 0, 'pending': 0, 'not_posted': 0,
                        'reviews': [], 'last_scanned': _iso_now(),
                        'scan_status': 'skipped',
                        'scan_error':  'profile deleted mid-scan',
                    })
                    with _scan_status_lock:
                        _scan_status['skipped'] += 1
                        _scan_status['done'] += 1
                    return

                with _scan_status_lock:
                    if email not in _scan_status['current']:
                        _scan_status['current'].append(email)
                try:
                    # §8.3: strict 90s per-profile wall-clock cap.
                    record = await asyncio.wait_for(
                        _scrape_one_profile(playwright, profile, cancel_event),
                        timeout=90,
                    )
                    _upsert_profile_record(pid, {'email': email, **record})
                    with _scan_status_lock:
                        if record.get('scan_status') == 'ok':
                            _scan_status['ok'] += 1
                        elif record.get('scan_status') == 'skipped':
                            _scan_status['skipped'] += 1
                        else:
                            _scan_status['errors'] += 1
                except asyncio.TimeoutError:
                    _upsert_profile_record(pid, {
                        'email': email,
                        'total': 0, 'live': 0, 'pending': 0, 'not_posted': 0,
                        'reviews': [], 'last_scanned': _iso_now(),
                        'scan_status': 'error',
                        'scan_error':  'timeout after 90s',
                    })
                    with _scan_status_lock:
                        _scan_status['errors'] += 1
                except Exception as e:
                    _upsert_profile_record(pid, {
                        'email': email,
                        'total': 0, 'live': 0, 'pending': 0, 'not_posted': 0,
                        'reviews': [], 'last_scanned': _iso_now(),
                        'scan_status': 'error',
                        'scan_error':  f'{type(e).__name__}: {e}',
                    })
                    with _scan_status_lock:
                        _scan_status['errors'] += 1
                finally:
                    with _scan_status_lock:
                        _scan_status['done'] += 1
                        if email in _scan_status['current']:
                            _scan_status['current'].remove(email)

        await asyncio.gather(*(_one(p) for p in targets))


async def _scrape_one_profile(playwright, profile, cancel_event):
    """Implemented in Task 6. Stub raises so Task 4 tests must mock it."""
    raise NotImplementedError('_scrape_one_profile is implemented in Task 6')
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_review_stats_scraper.py -v`
Expected: all green (17 tests).

- [ ] **Step 5: Commit**

```powershell
git add shared/review_stats_scraper.py tests/test_review_stats_scraper.py
git commit -m "feat(review-stats): worker pool + scan status + cancel"
```

- [ ] **Step 6: Sync into main directory**

---

## Task 5: Invisible context launcher (off-screen Chrome)

**Files:**
- Modify: `shared/review_stats_scraper.py`

This task uses a real browser launch — no unit test (would require live Playwright + a real profile dir). Smoke-tested manually instead.

- [ ] **Step 1: Add the launcher helper**

Append to `shared/review_stats_scraper.py`:

```python
async def launch_profile_context_invisible(playwright, profile: dict):
    """Launch a StealthChrome CDP context for the given profile, but with
    the Chrome window positioned off-screen so the user never sees it.

    Returns (context, bridge) — same shape as profile_manager._launch_profile_context.
    Caller MUST close context (and any bridge) in finally.

    Why off-screen, not headless: the existing launcher uses real Chrome
    (StealthChrome). Headless mode isn't supported by the stealth strategy.
    `--window-position=-32000,-32000` is the standard Windows trick to keep
    a real browser window invisible while preserving full fingerprint.
    """
    # Monkey-patch StealthChrome.start to inject extra_args on this one call.
    # This avoids modifying profile_manager._launch_profile_context.
    from shared import stealth_chrome as _sc
    original_start = _sc.StealthChrome.start
    OFF_SCREEN_ARGS = [
        '--window-position=-32000,-32000',
        '--window-size=400,300',
    ]

    async def _start_with_offscreen(self, *args, **kwargs):
        existing = list(kwargs.get('extra_args') or [])
        kwargs['extra_args'] = existing + OFF_SCREEN_ARGS
        return await original_start(self, *args, **kwargs)

    _sc.StealthChrome.start = _start_with_offscreen
    try:
        from shared.profile_manager import _launch_profile_context
        ctx, bridge, stealth = await _launch_profile_context(playwright, profile)
        return ctx, bridge, stealth
    finally:
        _sc.StealthChrome.start = original_start
```

Note: `_launch_profile_context` returns a 3-tuple `(context, bridge, stealth)`. The `stealth` instance owns the launched Chrome process and MUST be stopped by the caller (`stealth.stop()`) to avoid orphan `nstchrome.exe` processes.

Note: the monkey-patch is narrowly scoped — restored in `finally` before the function returns, so it never leaks to foreground launches.

- [ ] **Step 2: Manual smoke test**

Pick one profile from `browser_profiles/profiles.json` that is logged into Google. Run from a python REPL **at the project root** (`E:\NST Anty Android`):

```python
import asyncio
from pathlib import Path
from shared import profile_manager as pm, review_stats_scraper as rss
from playwright.async_api import async_playwright

pm.init(Path('.'))
rss.init(Path('.'))
# profiles use `status: "logged_in"` (string), not a boolean
profile = next(p for p in pm.list_profiles() if p.get('status') == 'logged_in')

async def smoke():
    async with async_playwright() as pw:
        ctx, bridge, stealth = await rss.launch_profile_context_invisible(pw, profile)
        page = await ctx.new_page()
        await page.goto('https://www.google.com/maps/contrib/')
        print('URL:', page.url)
        await asyncio.sleep(3)
        await ctx.close()
        try: stealth.stop()
        except Exception: pass

asyncio.run(smoke())
```

Expected: no Chrome window appears on screen, `page.url` prints a `maps.google.com/contrib/...` URL (or `accounts.google.com/...` if not logged in).

- [ ] **Step 3: Commit**

```powershell
git add shared/review_stats_scraper.py
git commit -m "feat(review-stats): invisible StealthChrome launcher (off-screen)"
```

- [ ] **Step 4: Sync into main directory**

---

## Task 6: Per-profile scrape — `_scrape_one_profile`

**Files:**
- Modify: `shared/review_stats_scraper.py`

- [ ] **Step 1: Add the scrape JS + Python wrapper**

In `shared/review_stats_scraper.py`, replace the `_scrape_one_profile` stub with the real implementation. Add `SCRAPE_JS` constant at module top and the function near the bottom:

```python
# Place near top of module (after imports)
SCRAPE_JS = r"""
() => {
  const rows = document.querySelectorAll('div.jftiEf[data-review-id]');
  return Array.from(rows).map(r => {
    const id      = r.getAttribute('data-review-id');
    const biz     = (r.querySelector('.d4r55')?.textContent || '').trim();
    const addr    = (r.querySelector('.RfnDt')?.textContent || '').trim();
    const starsEl = r.querySelector('.kvMYJc');
    const starsAl = starsEl ? (starsEl.getAttribute('aria-label') || '') : '';
    const stars   = parseInt(starsAl, 10) || 0;
    const time    = (r.querySelector('.rsqaWe')?.textContent || '').trim();
    const text    = (r.querySelector('.wiI7pd')?.textContent || '').trim();

    const hasShare = !!r.querySelector('button.gllhef[aria-label*="Share"]');
    const hasTime  = !!r.querySelector('span.rsqaWe');
    const badge    = (r.querySelector('span.SY1QMb.o2qHAc')?.textContent || '').toLowerCase();

    let status;
    if (hasShare || hasTime)              status = 'live';
    else if (badge.includes('pending'))   status = 'pending';
    else                                  status = 'not_posted';

    return { review_id: id, business: biz, address: addr,
             stars, time, text, status, share_link: '' };
  });
}
"""

# Replace the stub:
async def _scrape_one_profile(playwright, profile, cancel_event) -> dict:
    """Scrape one profile's /maps/contrib/ Reviews tab. Returns the
    aggregated record (same shape as _aggregate output) with `email`
    omitted (added by the coordinator).

    Hard timeout (90s) is applied by the caller via asyncio.wait_for().
    """
    from shared import profile_manager as pm

    pid = profile.get('id')
    email = profile.get('email', '?')

    # Skip if user has this profile open in foreground
    with pm._lock:
        if pid in pm._active_browsers:
            return {
                'total': 0, 'live': 0, 'pending': 0, 'not_posted': 0,
                'reviews': [],
                'last_scanned': _iso_now(),
                'scan_status': 'skipped',
                'scan_error':  'Profile open in foreground',
            }

    ctx = bridge = stealth = None
    try:
        ctx, bridge, stealth = await asyncio.wait_for(
            launch_profile_context_invisible(playwright, profile),
            timeout=30,
        )
        page = await ctx.new_page()

        try:
            await asyncio.wait_for(
                page.goto('https://www.google.com/maps/contrib/',
                          wait_until='domcontentloaded'),
                timeout=30,
            )
        except asyncio.TimeoutError:
            return _error_record('navigation timeout')

        if 'accounts.google.com' in (page.url or ''):
            return _error_record('not_logged_in')

        # Click the Reviews tab (data-tab-index="1" — language-agnostic)
        try:
            await page.wait_for_selector('div.RWPxGd[role="tablist"]', timeout=15000)
            already = await page.locator(
                'button[role="tab"][data-tab-index="1"][aria-selected="true"]'
            ).count()
            if not already:
                await page.click('button[role="tab"][data-tab-index="1"]')
            await page.wait_for_selector('div.jftiEf[data-review-id]', timeout=10000)
        except Exception as e:
            return _error_record(f'reviews_tab: {type(e).__name__}')

        await _scroll_load_all(page, cancel_event)
        reviews = await page.evaluate(SCRAPE_JS)
        return _aggregate(reviews)

    finally:
        # _launch_profile_context returns a 3-tuple: (context, bridge, stealth).
        # Each MUST be cleaned up: stealth owns the Chrome process and will
        # orphan nstchrome.exe forever if not stopped.
        try:
            if ctx is not None:
                await ctx.close()
        except Exception:
            pass
        try:
            if bridge is not None and hasattr(bridge, 'close'):
                await bridge.close()
        except Exception:
            pass
        try:
            if stealth is not None and hasattr(stealth, 'stop'):
                await stealth.stop() if asyncio.iscoroutinefunction(stealth.stop) else stealth.stop()
        except Exception:
            pass


def _error_record(error: str) -> dict:
    return {
        'total': 0, 'live': 0, 'pending': 0, 'not_posted': 0,
        'reviews': [],
        'last_scanned': _iso_now(),
        'scan_status': 'error',
        'scan_error':  error,
    }


async def _scroll_load_all(page, cancel_event) -> None:
    """Stub — real implementation in Task 7. For Task 6 alone, this returns
    immediately so the smoke test exercises the rest of the path on the
    first virtualised page (typically ~10 reviews)."""
    return None
```

- [ ] **Step 2: Manual smoke test**

From project root, REPL:

```python
import asyncio
from pathlib import Path
from shared import profile_manager as pm, review_stats_scraper as rss
from playwright.async_api import async_playwright

pm.init(Path('.'))
rss.init(Path('.'))
profile = next(p for p in pm.list_profiles() if p.get('logged_in'))
cancel_event = __import__('threading').Event()

async def smoke():
    async with async_playwright() as pw:
        rec = await rss._scrape_one_profile(pw, profile, cancel_event)
        print(rec)

asyncio.run(smoke())
```

Expected: prints a dict with `total`, `live`, `pending`, `not_posted`, `scan_status: 'ok'`, and a `reviews` list of `~10` items (without scroll-loading). Each review has `business`, `stars`, `status`.

- [ ] **Step 3: Commit**

```powershell
git add shared/review_stats_scraper.py
git commit -m "feat(review-stats): _scrape_one_profile core flow"
```

- [ ] **Step 4: Sync into main directory**

---

## Task 7: Scroll-load all reviews

**Files:**
- Modify: `shared/review_stats_scraper.py`

- [ ] **Step 1: Replace the `_scroll_load_all` stub**

In `shared/review_stats_scraper.py`, replace the existing `_scroll_load_all` stub with the real loop:

```python
SCROLL_LOAD_JS = r"""
async () => {
  // Resolve scroll container: contrib feed is in a virtualised side panel
  const candidates = [
    'div.m6QErb.XiKgde[tabindex="-1"]',
    'div.m6QErb[role="region"]',
  ];
  let container = null;
  for (const sel of candidates) {
    const el = document.querySelector(sel);
    if (el) { container = el; break; }
  }
  // Fallback to window if no panel found
  const scrollEl = container || document.scrollingElement || document.body;
  const isWindow = !container;

  const count = () => document.querySelectorAll('div.jftiEf[data-review-id]').length;

  let stable = 0;
  let last = count();
  for (let i = 0; i < 50; i++) {
    if (isWindow) {
      window.scrollTo(0, document.body.scrollHeight);
    } else {
      scrollEl.scrollTop = scrollEl.scrollHeight;
    }
    await new Promise(r => setTimeout(r, 800));
    const now = count();
    if (now === last) {
      stable++;
      if (stable >= 2) break;  // two stable rounds → done
    } else {
      stable = 0;
      last = now;
    }
  }
  return last;
}
"""


async def _scroll_load_all(page, cancel_event) -> int:
    """Scroll the contrib feed until no new reviews appear for 2 rounds.
    Honours cancel_event between iterations via a wrapper timeout.

    Returns the final review count (best-effort)."""
    if cancel_event.is_set():
        return 0
    try:
        # Wrap with an outer timeout so a frozen Google page can't stall us.
        # The inner JS has its own 50-iteration cap (~40s); 60s outer is safe.
        return await asyncio.wait_for(page.evaluate(SCROLL_LOAD_JS), timeout=60)
    except (asyncio.TimeoutError, Exception):
        # Even on timeout, the page should have SOME reviews loaded; the
        # outer scrape will count what's visible.
        return 0
```

- [ ] **Step 2: Manual smoke test**

Pick a profile with **>10 reviews** (one that has scrolled multiple pages on Google Maps). From project root, REPL:

```python
import asyncio, threading
from pathlib import Path
from shared import profile_manager as pm, review_stats_scraper as rss
from playwright.async_api import async_playwright

pm.init(Path('.'))
rss.init(Path('.'))
profile = next(p for p in pm.list_profiles()
               if p.get('logged_in') and p.get('email') == 'YOUR_PROFILE_EMAIL_HERE')
ev = threading.Event()

async def smoke():
    async with async_playwright() as pw:
        rec = await rss._scrape_one_profile(pw, profile, ev)
        print('total=', rec['total'], 'live=', rec['live'],
              'pending=', rec['pending'], 'not_posted=', rec['not_posted'])

asyncio.run(smoke())
```

Expected: total count matches the count visible on Google Maps' own contrib reviews page (open it manually in the profile's browser to compare).

- [ ] **Step 3: Commit**

```powershell
git add shared/review_stats_scraper.py
git commit -m "feat(review-stats): scroll-load all virtualised reviews"
```

- [ ] **Step 4: Sync into main directory**

---

## Task 8: Flask routes (5 endpoints)

**Files:**
- Modify: `electron-app/backend/server.py`
- Modify: `tests/test_review_stats_scraper.py`

- [ ] **Step 1: Wire `rss.init` into the backend startup**

In `electron-app/backend/server.py`, find the existing `profile_manager.init(...)` call (search for `profile_manager.init`) and add directly after it:

```python
from shared import review_stats_scraper as review_stats
review_stats.init(RESOURCES_PATH)
```

- [ ] **Step 2: Add the 5 routes**

Add to `electron-app/backend/server.py` near the other `/api/profiles/*` routes (e.g. just after the existing `/api/profiles/live-check/*` block — search for `@app.route('/api/profiles/live-check/cancel'` to find an anchor):

```python
@app.route('/api/profiles/review-stats', methods=['GET'])
def api_review_stats_all():
    """Bulk cached fetch (counts only, no `reviews` array)."""
    return jsonify({
        'success': True,
        'stats':   review_stats.get_all_stats(),
    })


@app.route('/api/profiles/<profile_id>/review-stats', methods=['GET'])
def api_review_stats_one(profile_id):
    """Full per-profile record incl. reviews array."""
    record = review_stats.get_profile_stats(profile_id)
    if record is None:
        return jsonify({'success': False, 'message': 'Never scanned'}), 404
    return jsonify({'success': True, 'stats': record})


@app.route('/api/profiles/review-stats/scan', methods=['POST'])
def api_review_stats_scan():
    """Start a bulk scan."""
    body = request.get_json(silent=True) or {}
    profile_ids = body.get('profile_ids')   # None means scan all
    num_workers = int(body.get('num_workers') or 3)
    result = review_stats.start_scan(profile_ids=profile_ids,
                                     num_workers=num_workers)
    if not result.get('success'):
        return jsonify(result), 409
    return jsonify(result)


@app.route('/api/profiles/review-stats/status', methods=['GET'])
def api_review_stats_status():
    return jsonify(review_stats.get_status())


@app.route('/api/profiles/review-stats/cancel', methods=['POST'])
def api_review_stats_cancel():
    review_stats.cancel_scan()
    return jsonify({'success': True})
```

- [ ] **Step 3: Write failing route tests**

Append to `tests/test_review_stats_scraper.py`:

```python
def test_route_bulk_stats_returns_empty_when_no_scan():
    from electron_app_backend_server import app  # see Step 4
    client = app.test_client()
    resp = client.get('/api/profiles/review-stats')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True
    assert payload['stats'] == {}


def test_route_single_profile_404_when_missing():
    from electron_app_backend_server import app
    client = app.test_client()
    resp = client.get('/api/profiles/does-not-exist/review-stats')
    assert resp.status_code == 404
    assert resp.get_json()['success'] is False


def test_route_scan_returns_409_when_already_running():
    from electron_app_backend_server import app
    client = app.test_client()
    rss._scan_status['running'] = True
    try:
        resp = client.post('/api/profiles/review-stats/scan',
                           json={'profile_ids': []})
        assert resp.status_code == 409
        assert resp.get_json()['success'] is False
    finally:
        rss._scan_status['running'] = False
```

- [ ] **Step 4: Make the test importable**

The backend `server.py` lives at `electron-app/backend/server.py` — Python can't import a path with a hyphen directly. Add a thin import shim at the top of the test file (replace the existing `sys.path.insert` line with these):

```python
import importlib.util as _ilu
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
_spec = _ilu.spec_from_file_location(
    'electron_app_backend_server',
    _Path(__file__).resolve().parent.parent / 'electron-app' / 'backend' / 'server.py',
)
_mod = _ilu.module_from_spec(_spec)
sys.modules['electron_app_backend_server'] = _mod
_spec.loader.exec_module(_mod)
```

This loads `server.py` once at test collection time so all three new route tests share the same Flask app instance.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_review_stats_scraper.py -v`
Expected: all green (20 tests).

- [ ] **Step 6: Smoke-test the live server**

Start the backend manually:

```powershell
python electron-app/backend/server.py
```

In another terminal:

```powershell
curl http://127.0.0.1:5000/api/profiles/review-stats
curl http://127.0.0.1:5000/api/profiles/review-stats/status
```

Expected: both return JSON with `success: true` (first one has `stats: {}`; second has `running: false`).

- [ ] **Step 7: Commit**

```powershell
git add electron-app/backend/server.py tests/test_review_stats_scraper.py
git commit -m "feat(review-stats): 5 Flask routes + route tests"
```

- [ ] **Step 8: Sync into main directory**

---

## Task 9: Renderer — fetch + render row badges

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js`

- [ ] **Step 1: Add badge fetch + cache**

In `electron-app/renderer/modules/profiles.js`, find the module-level state block (search for `let _allProfiles = [];`). Just below it, add:

```js
let _reviewStats = {};  // { profileId: {total, live, pending, not_posted, last_scanned, scan_status} }

async function _fetchReviewStats() {
    try {
        const resp = await fetch(App.apiUrl('/api/profiles/review-stats'));
        const data = await resp.json();
        if (data && data.success) {
            _reviewStats = data.stats || {};
        }
    } catch (e) {
        console.warn('[review-stats] fetch failed', e);
    }
}
```

- [ ] **Step 2: Call the fetch on profile-list load**

Find the function that runs after profiles are loaded — search for `_allProfiles =` (the assignment, not the declaration). Right after that line, add:

```js
        // Fire-and-forget; UI updates in-place when stats arrive
        _fetchReviewStats().then(() => _refreshAllBadges());
```

- [ ] **Step 3: Add the badge renderer**

Above the row-render function (search for `function _renderProfileRow` or similar — if you can't find it, search for the template literal that builds the table row HTML), add:

```js
function _reviewStatsBadgeHtml(profileId) {
    const s = _reviewStats[profileId];
    if (!s || s.scan_status === undefined) {
        return `<span class="pm-rs-badge pm-rs-never" title="Click Sync Review Stats to scan">— never scanned</span>`;
    }
    if (s.scan_status === 'error' && s.scan_error === 'not_logged_in') {
        return `<span class="pm-rs-badge pm-rs-login" title="${_esc(s.scan_error)}">⚠ login required</span>`;
    }
    if (s.scan_status === 'error') {
        return `<span class="pm-rs-badge pm-rs-error" title="${_esc(s.scan_error || 'error')}">⚠ error</span>`;
    }
    if (s.scan_status === 'skipped') {
        return `<span class="pm-rs-badge pm-rs-skipped" title="${_esc(s.scan_error || 'skipped')}">↻ skipped</span>`;
    }
    const total = s.total || 0;
    const live = s.live || 0;
    const notPosted = (s.pending || 0) + (s.not_posted || 0);
    const tip = `Last scanned: ${_relativeTime(s.last_scanned)}`;
    return `<span class="pm-rs-badge" data-profile-id="${_esc(profileId)}" title="${_esc(tip)}">
        <span class="pm-rs-chip pm-rs-total">Σ ${total}</span>
        <span class="pm-rs-chip pm-rs-live">● ${live}</span>
        <span class="pm-rs-chip pm-rs-notposted">✕ ${notPosted}</span>
    </span>`;
}

function _relativeTime(iso) {
    if (!iso) return 'never';
    try {
        const d = new Date(iso);
        const diff = (Date.now() - d.getTime()) / 1000;
        if (diff < 60) return 'just now';
        if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
        return `${Math.floor(diff/86400)}d ago`;
    } catch (e) { return iso; }
}

function _refreshAllBadges() {
    document.querySelectorAll('tr[data-profile-id]').forEach(row => {
        const pid = row.getAttribute('data-profile-id');
        const slot = row.querySelector('.pm-rs-slot');
        if (slot) slot.innerHTML = _reviewStatsBadgeHtml(pid);
    });
}
```

- [ ] **Step 4: Inject the badge slot into each row**

Find the row HTML template (look for the existing email/proxy/status column markup inside `_renderProfileRow` or similar). Add a new `<td class="pm-rs-slot">${_reviewStatsBadgeHtml(p.id)}</td>` immediately after the email column. Update the table header in the same module — add `<th>Reviews</th>` between the existing Email and Proxy headers.

If the table structure uses a flex layout instead of `<table>`, place the slot inside the row's existing email/info column wrapper instead.

- [ ] **Step 5: Manual UI test**

Start the Electron app (`START_ELECTRON_APP.bat` from project root). Open the Profiles tab. Every row should show `— never scanned` (since no scan has run yet).

- [ ] **Step 6: Commit**

```powershell
git add electron-app/renderer/modules/profiles.js
git commit -m "feat(review-stats): fetch + render row badges (never-scanned state)"
```

- [ ] **Step 7: Sync into main directory**

---

## Task 10: Renderer — CSS for badges

**Files:**
- Modify: `electron-app/renderer/index.html`

- [ ] **Step 1: Find the existing `<style>` block**

In `electron-app/renderer/index.html`, locate the inline `<style>` block (search for `pm-engine-tag-nexus` or any existing `.pm-` class for an anchor near profile-manager styles).

- [ ] **Step 2: Append the badge CSS**

Inside the `<style>` block, append:

```css
/* ── Review stats badge ─────────────────────────────────────── */
.pm-rs-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;
    font-size: 11px;
    line-height: 1;
    user-select: none;
}
.pm-rs-badge:hover { opacity: 0.85; }

.pm-rs-chip {
    display: inline-flex;
    align-items: center;
    padding: 2px 6px;
    border-radius: 4px;
    font-variant-numeric: tabular-nums;
    background: #1f2937;
    color: #e5e7eb;
}
.pm-rs-chip.pm-rs-total      { background: #374151; color: #f3f4f6; }
.pm-rs-chip.pm-rs-live       { background: #064e3b; color: #6ee7b7; }
.pm-rs-chip.pm-rs-notposted  { background: #7f1d1d; color: #fca5a5; }

.pm-rs-badge.pm-rs-never,
.pm-rs-badge.pm-rs-login,
.pm-rs-badge.pm-rs-error,
.pm-rs-badge.pm-rs-skipped {
    padding: 2px 6px;
    border-radius: 4px;
    cursor: default;
}
.pm-rs-badge.pm-rs-never    { background: #374151; color: #9ca3af; }
.pm-rs-badge.pm-rs-login    { background: #78350f; color: #fcd34d; cursor: pointer; }
.pm-rs-badge.pm-rs-error    { background: #7f1d1d; color: #fca5a5; }
.pm-rs-badge.pm-rs-skipped  { background: #1e3a8a; color: #93c5fd; }
```

- [ ] **Step 3: Manual UI test**

Reload the Electron app. Badges should now have the dark-themed pill styling matching the rest of the NST UI.

- [ ] **Step 4: Commit**

```powershell
git add electron-app/renderer/index.html
git commit -m "feat(review-stats): CSS for badge chips + status pills"
```

- [ ] **Step 5: Sync into main directory**

---

## Task 11: Renderer — Sync Review Stats button + dropdown

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js`
- Modify: `electron-app/renderer/index.html`

- [ ] **Step 1: Add the button to the filter bar**

In `electron-app/renderer/index.html`, find the profile-manager filter bar (search for `data-filter="all"` or `data-filter="logged_in"` for an anchor). At the end of that bar (right side), insert:

```html
<div class="pm-rs-sync-wrap" style="margin-left:auto;position:relative;">
    <button id="pmRsSyncBtn" class="pm-btn" type="button" title="Scan Google Maps contrib pages">
        <i class="fas fa-sync-alt"></i> Sync Review Stats
        <i class="fas fa-caret-down" style="margin-left:4px;"></i>
    </button>
    <div id="pmRsSyncMenu" class="pm-rs-sync-menu" style="display:none;">
        <button type="button" data-rs-scope="all">Scan all profiles</button>
        <button type="button" data-rs-scope="selected">Scan selected (<span id="pmRsSelectedCount">0</span>)</button>
        <button type="button" data-rs-scope="never">Scan never-scanned only</button>
    </div>
</div>
```

- [ ] **Step 2: Add the dropdown CSS**

In the same `<style>` block from Task 10, append:

```css
.pm-rs-sync-menu {
    position: absolute;
    top: 100%; right: 0;
    margin-top: 4px;
    min-width: 200px;
    background: #111827;
    border: 1px solid #374151;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    z-index: 100;
}
.pm-rs-sync-menu button {
    display: block;
    width: 100%;
    padding: 8px 12px;
    background: transparent;
    border: none;
    color: #e5e7eb;
    text-align: left;
    cursor: pointer;
    font-size: 12px;
}
.pm-rs-sync-menu button:hover { background: #1f2937; }
```

- [ ] **Step 3: Wire the button**

In `electron-app/renderer/modules/profiles.js`, in the module's existing DOM-ready / initial-bind function (search for `pmCreateBtn` or any existing `.addEventListener('click'`), find the spot where other profile-page buttons are wired). Add:

```js
function _initReviewStatsSync() {
    const btn = document.getElementById('pmRsSyncBtn');
    const menu = document.getElementById('pmRsSyncMenu');
    if (!btn || !menu) return;

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const showing = menu.style.display !== 'none';
        menu.style.display = showing ? 'none' : 'block';
        if (!showing) {
            const cntEl = document.getElementById('pmRsSelectedCount');
            if (cntEl) cntEl.textContent = String(_selectedIds.size);
        }
    });
    document.addEventListener('click', () => { menu.style.display = 'none'; });

    menu.querySelectorAll('button[data-rs-scope]').forEach(b => {
        b.addEventListener('click', async (e) => {
            e.stopPropagation();
            menu.style.display = 'none';
            const scope = b.getAttribute('data-rs-scope');
            await _startReviewStatsScan(scope);
        });
    });
}

async function _startReviewStatsScan(scope) {
    let profile_ids = null;
    if (scope === 'selected') {
        if (_selectedIds.size === 0) {
            App.toast && App.toast('No profiles selected', 'error');
            return;
        }
        profile_ids = [..._selectedIds];
    } else if (scope === 'never') {
        profile_ids = _allProfiles
            .filter(p => !_reviewStats[p.id])
            .map(p => p.id);
        if (profile_ids.length === 0) {
            App.toast && App.toast('All profiles already scanned', 'info');
            return;
        }
    }
    try {
        const resp = await fetch(App.apiUrl('/api/profiles/review-stats/scan'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile_ids, num_workers: 3 }),
        });
        const data = await resp.json();
        if (!data.success) {
            App.toast && App.toast(data.message || 'Scan failed', 'error');
            return;
        }
        App.toast && App.toast(`Scanning ${data.queued} profile${data.queued === 1 ? '' : 's'}…`, 'success');
        _startReviewStatsPoll();  // implemented in Task 12
    } catch (e) {
        App.toast && App.toast('Backend unreachable', 'error');
    }
}
```

Then in the existing init code (after other `_init*` calls inside the IIFE / on-ready), call:

```js
_initReviewStatsSync();
```

Add a no-op placeholder for `_startReviewStatsPoll` so this task can ship before Task 12:

```js
function _startReviewStatsPoll() { /* implemented in Task 12 */ }
```

- [ ] **Step 4: Manual UI test**

Reload the Electron app. Click `Sync Review Stats` — dropdown appears. Click "Scan all profiles" — toast appears, no error. (Workers will fire but only the smoke-tested code path will actually scrape; counts won't appear yet because progress strip is in Task 12.)

- [ ] **Step 5: Commit**

```powershell
git add electron-app/renderer/modules/profiles.js electron-app/renderer/index.html
git commit -m "feat(review-stats): Sync button + scan-scope dropdown"
```

- [ ] **Step 6: Sync into main directory**

---

## Task 12: Renderer — progress strip + status poll

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js`
- Modify: `electron-app/renderer/index.html`

- [ ] **Step 1: Add the strip markup**

In `electron-app/renderer/index.html`, insert just above the profiles table (search for a containing div near the filter bar — place it as a sibling of the table):

```html
<div id="pmRsProgress" class="pm-rs-progress" style="display:none;">
    <div class="pm-rs-progress-row">
        <i class="fas fa-spinner fa-spin"></i>
        <span class="pm-rs-progress-text">Scanning…</span>
        <button id="pmRsCancelBtn" class="pm-rs-cancel" type="button" title="Cancel scan">✕</button>
    </div>
    <div class="pm-rs-progress-bar"><div class="pm-rs-progress-fill" style="width:0%"></div></div>
    <div class="pm-rs-progress-current"></div>
</div>
```

- [ ] **Step 2: Add the strip CSS**

In the same `<style>` block:

```css
.pm-rs-progress {
    margin: 8px 0;
    padding: 8px 12px;
    background: #111827;
    border: 1px solid #374151;
    border-radius: 6px;
    font-size: 12px;
    color: #e5e7eb;
}
.pm-rs-progress-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
}
.pm-rs-progress-text { flex: 1; }
.pm-rs-cancel {
    background: transparent;
    border: none;
    color: #9ca3af;
    cursor: pointer;
    font-size: 14px;
    padding: 0 4px;
}
.pm-rs-cancel:hover { color: #fca5a5; }
.pm-rs-progress-bar {
    height: 6px;
    background: #1f2937;
    border-radius: 3px;
    overflow: hidden;
}
.pm-rs-progress-fill {
    height: 100%;
    background: #22c55e;
    transition: width 200ms ease;
}
.pm-rs-progress-current {
    margin-top: 4px;
    font-size: 11px;
    color: #9ca3af;
}
```

- [ ] **Step 3: Replace the `_startReviewStatsPoll` stub**

In `electron-app/renderer/modules/profiles.js`, replace the existing `_startReviewStatsPoll` stub with:

```js
let _rsPollTimer = null;
let _rsHideTimer = null;

function _startReviewStatsPoll() {
    if (_rsPollTimer) return;  // already polling
    if (_rsHideTimer) { clearTimeout(_rsHideTimer); _rsHideTimer = null; }

    const strip = document.getElementById('pmRsProgress');
    if (!strip) return;
    strip.style.display = '';

    const cancelBtn = document.getElementById('pmRsCancelBtn');
    if (cancelBtn) {
        cancelBtn.onclick = async () => {
            try { await fetch(App.apiUrl('/api/profiles/review-stats/cancel'), { method: 'POST' }); } catch (e) {}
        };
    }

    const tick = async () => {
        try {
            const resp = await fetch(App.apiUrl('/api/profiles/review-stats/status'));
            const s = await resp.json();
            _renderRsProgress(s);
            if (!s.running) {
                clearInterval(_rsPollTimer); _rsPollTimer = null;
                await _fetchReviewStats();
                _refreshAllBadges();
                _rsHideTimer = setTimeout(() => {
                    strip.style.display = 'none';
                }, 3000);
            }
        } catch (e) { /* keep polling */ }
    };
    tick();
    _rsPollTimer = setInterval(tick, 2000);
}

function _renderRsProgress(s) {
    const strip = document.getElementById('pmRsProgress');
    if (!strip) return;
    const text = strip.querySelector('.pm-rs-progress-text');
    const fill = strip.querySelector('.pm-rs-progress-fill');
    const cur  = strip.querySelector('.pm-rs-progress-current');
    const done = s.done || 0, total = s.total || 0;
    const pct = total ? Math.round((done / total) * 100) : 0;
    if (text) text.textContent =
        `${s.running ? '⟳ Scanning…' : '✓ Done.'} ${done}/${total} done · ${s.skipped||0} skipped · ${s.errors||0} error${(s.errors||0) === 1 ? '' : 's'}`;
    if (fill) fill.style.width = pct + '%';
    if (cur) cur.textContent = (s.current && s.current.length)
        ? `Current: ${s.current.join(', ')}` : '';
}
```

- [ ] **Step 4: Auto-resume polling on page load if a scan is already running**

Inside `_fetchReviewStats` (Task 9), or alongside the initial profile-list load, add one extra fetch after the badge fetch finishes:

```js
async function _resumeRsPollIfRunning() {
    try {
        const resp = await fetch(App.apiUrl('/api/profiles/review-stats/status'));
        const s = await resp.json();
        if (s.running) _startReviewStatsPoll();
    } catch (e) {}
}
```

Call it from the post-fetch step where `_refreshAllBadges()` is invoked:

```js
_fetchReviewStats().then(() => { _refreshAllBadges(); _resumeRsPollIfRunning(); });
```

- [ ] **Step 5: Manual UI test**

Click `Sync Review Stats → Scan all profiles`. Progress strip should appear, show "Scanning… 0/N done", currently-scrapping emails listed, progress bar fills. Cancel button stops the scan. After done, badges populate and strip auto-hides after 3 s.

- [ ] **Step 6: Commit**

```powershell
git add electron-app/renderer/modules/profiles.js electron-app/renderer/index.html
git commit -m "feat(review-stats): progress strip + 2s status poll + cancel"
```

- [ ] **Step 7: Sync into main directory**

---

## Task 13: Renderer — drill-down modal

**Files:**
- Modify: `electron-app/renderer/modules/profiles.js`
- Modify: `electron-app/renderer/index.html`

- [ ] **Step 1: Add the modal markup**

In `electron-app/renderer/index.html`, append inside the existing modals container (search for an existing modal like `pmCreateModal` for an anchor) a sibling div:

```html
<div id="pmRsModal" class="pm-modal" style="display:none;">
    <div class="pm-modal-backdrop"></div>
    <div class="pm-modal-content pm-rs-modal-content">
        <div class="pm-modal-header">
            <span id="pmRsModalTitle">Review Stats</span>
            <div style="margin-left:auto;display:flex;gap:8px;">
                <button id="pmRsRescanBtn" class="pm-btn" type="button"><i class="fas fa-redo"></i> Rescan</button>
                <button id="pmRsCloseBtn" class="pm-modal-close" type="button">✕</button>
            </div>
        </div>
        <div class="pm-modal-body">
            <div id="pmRsSummary" class="pm-rs-summary"></div>
            <div class="pm-rs-modal-controls">
                <div class="pm-rs-filters" id="pmRsFilters">
                    <button type="button" data-rs-filter="all"        class="pm-rs-filter-btn pm-rs-active">All</button>
                    <button type="button" data-rs-filter="live"       class="pm-rs-filter-btn">Live</button>
                    <button type="button" data-rs-filter="not_posted" class="pm-rs-filter-btn">Not Posted</button>
                    <button type="button" data-rs-filter="pending"    class="pm-rs-filter-btn">Pending</button>
                </div>
                <input id="pmRsSearch" type="text" placeholder="Search business or text…" />
            </div>
            <div id="pmRsList" class="pm-rs-list"></div>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Add the modal CSS**

In the same `<style>` block:

```css
.pm-rs-modal-content { width: min(900px, 95vw); max-height: 85vh; display: flex; flex-direction: column; }
.pm-rs-summary { padding: 8px 12px; background: #1f2937; border-radius: 6px; margin-bottom: 12px; font-size: 13px; color: #e5e7eb; }
.pm-rs-modal-controls { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.pm-rs-filters { display: flex; gap: 4px; }
.pm-rs-filter-btn {
    padding: 4px 10px; border: 1px solid #374151; background: transparent;
    color: #e5e7eb; border-radius: 4px; cursor: pointer; font-size: 11px;
}
.pm-rs-filter-btn.pm-rs-active { background: #2563eb; border-color: #2563eb; }
#pmRsSearch {
    flex: 1; padding: 4px 8px; border: 1px solid #374151; border-radius: 4px;
    background: #111827; color: #e5e7eb; font-size: 12px;
}
.pm-rs-list { overflow-y: auto; flex: 1; }
.pm-rs-item {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 12px;
    padding: 10px 12px;
    border-bottom: 1px solid #374151;
}
.pm-rs-item-stars { color: #fbbf24; font-size: 14px; align-self: start; }
.pm-rs-item-biz   { font-weight: 600; color: #f3f4f6; }
.pm-rs-item-addr  { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.pm-rs-item-text  { font-size: 12px; color: #e5e7eb; margin-top: 4px; font-style: italic; }
.pm-rs-item-status {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.pm-rs-status-live       { background: #064e3b; color: #6ee7b7; }
.pm-rs-status-not_posted { background: #7f1d1d; color: #fca5a5; }
.pm-rs-status-pending    { background: #78350f; color: #fcd34d; }
.pm-rs-item-meta { text-align: right; font-size: 11px; color: #9ca3af; }
.pm-rs-item-open { display: inline-block; margin-top: 4px; color: #60a5fa; text-decoration: none; }
.pm-rs-item-open:hover { text-decoration: underline; }
```

- [ ] **Step 3: Wire badge click → open modal**

In `electron-app/renderer/modules/profiles.js`, add a delegated click handler near the other delegated handlers (search for `document.addEventListener('click'` for an anchor). Inside the existing handler, add a branch:

```js
const rsBadge = e.target.closest('.pm-rs-badge[data-profile-id]');
if (rsBadge) {
    e.preventDefault();
    e.stopPropagation();
    _openReviewStatsModal(rsBadge.getAttribute('data-profile-id'));
    return;
}
```

(If no existing delegated click handler exists, register a new one on `document` with the body above.)

- [ ] **Step 4: Add modal logic**

Append to `electron-app/renderer/modules/profiles.js`:

```js
let _rsModalState = { profileId: null, full: null, filter: 'all', search: '' };

async function _openReviewStatsModal(profileId) {
    _rsModalState = { profileId, full: null, filter: 'all', search: '' };
    document.getElementById('pmRsModal').style.display = '';
    document.getElementById('pmRsList').innerHTML =
        '<div style="padding:20px;text-align:center;color:#9ca3af;"><i class="fas fa-spinner fa-spin"></i> Loading…</div>';

    try {
        const resp = await fetch(App.apiUrl(`/api/profiles/${encodeURIComponent(profileId)}/review-stats`));
        if (resp.status === 404) {
            _rsModalState.full = null;
            document.getElementById('pmRsList').innerHTML =
                '<div style="padding:20px;text-align:center;color:#9ca3af;">Never scanned. Click Rescan to start.</div>';
            document.getElementById('pmRsSummary').textContent = '';
            document.getElementById('pmRsModalTitle').textContent = profileId;
            return;
        }
        const data = await resp.json();
        if (!data.success) throw new Error(data.message || 'fetch failed');
        _rsModalState.full = data.stats;
        _renderReviewStatsModal();
    } catch (e) {
        document.getElementById('pmRsList').innerHTML =
            `<div style="padding:20px;text-align:center;color:#fca5a5;">Error: ${_esc(e.message)}</div>`;
    }
}

function _renderReviewStatsModal() {
    const s = _rsModalState.full;
    if (!s) return;
    document.getElementById('pmRsModalTitle').textContent = `${s.email} — Review Stats`;
    const notPosted = (s.pending || 0) + (s.not_posted || 0);
    document.getElementById('pmRsSummary').innerHTML =
        `Total: <b>${s.total||0}</b>  ·  Live: <b style="color:#6ee7b7">${s.live||0}</b>  ·  Not Posted: <b style="color:#fca5a5">${notPosted}</b>` +
        `<br><span style="font-size:11px;color:#9ca3af;">Last scanned: ${_esc(_relativeTime(s.last_scanned))}</span>`;

    const filter = _rsModalState.filter;
    const search = _rsModalState.search.toLowerCase();

    const filtered = (s.reviews || []).filter(r => {
        if (filter !== 'all' && r.status !== filter) return false;
        if (search && !((r.business || '').toLowerCase().includes(search)
                     || (r.text || '').toLowerCase().includes(search))) return false;
        return true;
    });

    const list = document.getElementById('pmRsList');
    if (!filtered.length) {
        list.innerHTML = '<div style="padding:20px;text-align:center;color:#9ca3af;">No reviews match.</div>';
        return;
    }

    list.innerHTML = filtered.map(r => {
        const stars = '★'.repeat(r.stars || 0) + '☆'.repeat(Math.max(0, 5 - (r.stars || 0)));
        const statusLabel = r.status === 'not_posted' ? 'NOT POSTED' : (r.status || '').toUpperCase();
        const openHref = r.status === 'live'
            ? `https://www.google.com/maps/contrib/?review_id=${encodeURIComponent(r.review_id || '')}`
            : '';
        return `
        <div class="pm-rs-item">
            <div class="pm-rs-item-stars">${_esc(stars)}</div>
            <div>
                <div class="pm-rs-item-biz">${_esc(r.business || '(unknown)')}</div>
                ${r.address ? `<div class="pm-rs-item-addr">${_esc(r.address)}</div>` : ''}
                ${r.text ? `<div class="pm-rs-item-text">"${_esc(r.text)}"</div>` : ''}
            </div>
            <div class="pm-rs-item-meta">
                <span class="pm-rs-item-status pm-rs-status-${_esc(r.status || 'unknown')}">${_esc(statusLabel)}</span>
                <div style="margin-top:4px;">${_esc(r.time || '')}</div>
                ${openHref ? `<a class="pm-rs-item-open" href="${openHref}" target="_blank" rel="noreferrer">open ↗</a>` : ''}
            </div>
        </div>`;
    }).join('');
}

function _initReviewStatsModal() {
    const modal = document.getElementById('pmRsModal');
    if (!modal) return;
    document.getElementById('pmRsCloseBtn').addEventListener('click', () => {
        modal.style.display = 'none';
    });
    modal.querySelector('.pm-modal-backdrop')?.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    document.getElementById('pmRsFilters').addEventListener('click', (e) => {
        const b = e.target.closest('button[data-rs-filter]');
        if (!b) return;
        document.querySelectorAll('#pmRsFilters .pm-rs-filter-btn')
            .forEach(x => x.classList.remove('pm-rs-active'));
        b.classList.add('pm-rs-active');
        _rsModalState.filter = b.getAttribute('data-rs-filter');
        _renderReviewStatsModal();
    });
    document.getElementById('pmRsSearch').addEventListener('input', (e) => {
        _rsModalState.search = e.target.value || '';
        _renderReviewStatsModal();
    });
    document.getElementById('pmRsRescanBtn').addEventListener('click', async () => {
        if (!_rsModalState.profileId) return;
        try {
            const r = await fetch(App.apiUrl('/api/profiles/review-stats/scan'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile_ids: [_rsModalState.profileId], num_workers: 1 }),
            });
            const d = await r.json();
            if (d.success) {
                App.toast && App.toast('Rescan queued', 'success');
                _startReviewStatsPoll();
            } else {
                App.toast && App.toast(d.message || 'Failed', 'error');
            }
        } catch (e) { App.toast && App.toast('Backend unreachable', 'error'); }
    });
}
```

Call `_initReviewStatsModal()` from the same init block where `_initReviewStatsSync()` is called.

- [ ] **Step 5: Manual UI test**

Click any badge with a scanned record. Modal opens, summary shown, reviews listed with star rating + status pill + open link. Filter chips swap the visible set; search filters by business/text. Rescan button queues a single-profile scan and progress strip appears.

- [ ] **Step 6: Commit**

```powershell
git add electron-app/renderer/modules/profiles.js electron-app/renderer/index.html
git commit -m "feat(review-stats): drill-down modal with filter + search + rescan"
```

- [ ] **Step 7: Sync into main directory**

---

## Task 14: End-to-end smoke test on real profiles

**Files:**
- None (verification only)

- [ ] **Step 1: Pre-flight check**

Confirm:
- `browser_profiles/profiles.json` has at least 2 profiles marked `logged_in: true`.
- One of those profiles has ≥3 reviews on its Google Maps contrib page (open the profile manually first to confirm).
- Run `python -m pytest tests/test_review_stats_scraper.py -v` — all green.

- [ ] **Step 2: Launch Electron app and clear cache**

```powershell
START_ELECTRON_APP.bat
```

If `browser_profiles/review_stats.json` exists from earlier smoke runs, delete it:

```powershell
Remove-Item "browser_profiles\review_stats.json" -ErrorAction SilentlyContinue
```

- [ ] **Step 3: Scan 2-3 profiles**

In the UI:
1. Select 2-3 logged-in profiles via row checkboxes.
2. Click `Sync Review Stats → Scan selected (N)`.
3. Watch the progress strip — should show "Scanning… 0/3 done", current emails update, progress bar fills.
4. Wait for completion (~30-90 s for 3 profiles with 3 workers).

- [ ] **Step 4: Verify badge counts**

For each scanned profile:
1. Note the badge: `Σ total · ● live · ✕ not_posted`.
2. Open the same profile's contrib page in the foreground (use existing "Launch" button).
3. Manually count reviews on Google Maps.
4. Confirm badge total ± 1 matches actual count. (Off-by-one is acceptable if Google's pagination hides one row.)

- [ ] **Step 5: Verify drill-down modal**

Click a badge. Modal opens with:
- Summary line: Total / Live / Not Posted match the badge.
- Last-scanned relative time present.
- Review list non-empty for ≥3-review profiles.
- Status pills coloured (live = green, not_posted = red).
- Filter chips work: clicking "Live" reduces the list.
- Search box filters by business name.

- [ ] **Step 6: Verify edge cases**

1. **Not logged in:** pick a profile with no Google session, scan it → badge shows `⚠ login required`.
2. **Profile open in foreground:** launch a profile, then trigger Sync → that profile's row shows `↻ skipped` with tooltip "Profile open in foreground".
3. **Cancel mid-scan:** click Sync, then immediately click ✕ on progress strip → scan stops; partially-completed records still saved.
4. **Re-open the app:** restart Electron, badge counts should reload from `review_stats.json`.

- [ ] **Step 7: Commit (if any UI tweaks needed)**

If the e2e exposes any bugs, fix them and commit:

```powershell
git add <changed files>
git commit -m "fix(review-stats): <bug discovered in e2e>"
```

Then re-run Step 4-6 until clean.

- [ ] **Step 8: Final sync to main directory**

Per `memory/workflow_main_directory.md`: confirm all files modified across Tasks 1-13 are present in `E:\NST Anty Android\` (not just the worktree).

---

## Self-Review

Spec coverage check:

| Spec section | Covered by |
|---|---|
| §2 Non-goals (read-only, no sheet backfill, no share-link at scan time) | Implementation honours these (Task 6 leaves `share_link: ''`; no sheet integration) |
| §3.1 Badge | Task 9 + Task 10 |
| §3.2 Top-bar dropdown | Task 11 |
| §3.3 Progress strip | Task 12 |
| §3.4 Drill-down modal | Task 13 |
| §4 Architecture | Tasks 1-8 (backend) + 9-13 (renderer) |
| §5 Data model | Task 1 (persistence) + Task 3 (aggregation shape) |
| §5.1 D: drive fallback | Promoted to follow-up (default `browser_profiles/` is E:-rooted) |
| §6.1 Per-profile scrape | Task 6 |
| §6.2 Selectors | Task 6 `SCRAPE_JS` |
| §6.3 Classification | Task 6 `SCRAPE_JS` |
| §6.4 Scroll-load | Task 7 |
| §6.5 Aggregation | Task 3 |
| §6.6 Invisible context | Task 5 |
| §6.7 Deferred share-link | Honoured (Task 6) |
| §7 All 5 API endpoints | Task 8 |
| §8.1 Worker pool | Task 4 |
| §8.2 Already-launched skip | Task 6 |
| §8.3 Per-profile 90s timeout | Task 4 worker wraps `_scrape_one_profile` in `asyncio.wait_for(..., timeout=90)` |
| §8.4 Cancel | Task 4 + Task 7 (in scroll loop) |
| §8.5 File lock | Task 1 + Task 2 |
| §8.6 Restart resilience | Task 1 (`running` defaults False after import) |
| §8.7 Profile-deleted-mid-scan | Task 4 worker re-checks `pm.get_profile(pid) is None` inside the semaphore before scraping |
| §8.8 Not-logged-in detect | Task 6 |

**Gaps found in self-review (all fixed inline):**

- **§5.1 D: drive fallback** — promoted to follow-up list. `browser_profiles/` is documented as E:-rooted; D: support remains a conditional add-on, not a forced task.
- **§8.3 strict 90s per-profile cap** — fixed inline in Task 4 Step 3 (`asyncio.wait_for(..., timeout=90)` around `_scrape_one_profile` with a dedicated `except asyncio.TimeoutError` branch).
- **§8.7 profile-deleted-mid-scan re-check** — fixed inline in Task 4 Step 3 (`pm.get_profile(pid) is None` check inside the semaphore block, before the scrape).

**Placeholder scan:** No TBDs / "implement later" / open-ended phrases. Every code block is complete and self-contained.

**Type consistency:** `_scrape_one_profile(playwright, profile, cancel_event)` signature is identical across the Task 4 stub, Task 6 implementation, and the Task 4 worker call site. `_aggregate(reviews)` return shape is the same dict shape that `_upsert_profile_record` persists. Frontend `_reviewStats[profileId]` consumes `get_all_stats()` output verbatim. ✓

---

## Out-of-scope follow-ups (carried from spec §11)

1. On-demand share-link extraction per review (modal action button).
2. Scheduled auto-rescan via cron-like task.
3. Cross-reference contrib counts against Project_Management sheet rows.
4. CSV/Excel export of review stats.
5. **D: drive storage fallback** — implement only when a user actually moves `browser_profiles/` to D:. The atomic write path in Task 1 already works on D: for files <32KB; only the per-profile-file split would be needed when individual records exceed that threshold.
