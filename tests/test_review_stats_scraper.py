"""Unit tests for shared/review_stats_scraper.py persistence."""
import sys
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / 'electron-app' / 'backend'))
if 'electron_app_backend_server' not in sys.modules:
    _spec = _ilu.spec_from_file_location(
        'electron_app_backend_server',
        _Path(__file__).resolve().parent.parent / 'electron-app' / 'backend' / 'server.py',
    )
    _mod = _ilu.module_from_spec(_spec)
    sys.modules['electron_app_backend_server'] = _mod
    _spec.loader.exec_module(_mod)

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

    async def fake_scrape(playwright, profile, cancel_event, launch_gate=None):
        return {
            'total': 1, 'live': 1, 'pending': 0, 'not_posted': 0,
            'reviews': [{'review_id': 'r1', 'business': 'X', 'status': 'live'}],
            'last_scanned': '2026-05-28T14:00:00+06:00',
            'scan_status': 'ok', 'scan_error': None,
        }

    from shared import nexus_profile_manager as pm
    with patch.object(rss, '_list_target_profiles', return_value=fake_profiles), \
         patch.object(rss, '_scrape_one_profile', side_effect=fake_scrape), \
         patch.object(pm, 'get_profile', side_effect=lambda pid: {'id': pid}):
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

    async def fake_scrape(playwright, profile, cancel_event, launch_gate=None):
        # Long polling window — outer test must call cancel within ~5s of entry.
        for _ in range(100):
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
    from shared import nexus_profile_manager as pm
    with patch.object(rss, '_list_target_profiles', return_value=fake_profiles), \
         patch.object(rss, '_scrape_one_profile', side_effect=fake_scrape), \
         patch.object(pm, 'get_profile', side_effect=lambda pid: {'id': pid}):
        rss.start_scan(profile_ids=None, num_workers=1)
        # Wait deterministically until the worker has entered the scrape
        # (it appends `email` to _scan_status['current']). 10s budget covers
        # the worst-case Playwright bootstrap on a cold start.
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if rss._scan_status['current']:
                break
            time.sleep(0.05)
        else:
            raise AssertionError('worker did not enter scrape within 10s')
        rss.cancel_scan()
        _wait_idle(timeout=10.0)

    assert seen['cancelled'] is True


def _auth_headers():
    import electron_app_backend_server as _srv
    return {'X-Api-Token': _srv._INTERNAL_TOKEN}


def test_route_bulk_stats_returns_empty_when_no_scan():
    from electron_app_backend_server import app
    client = app.test_client()
    resp = client.get('/api/profiles/review-stats', headers=_auth_headers())
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['success'] is True
    assert payload['stats'] == {}


def test_route_single_profile_404_when_missing():
    from electron_app_backend_server import app
    client = app.test_client()
    resp = client.get('/api/profiles/does-not-exist/review-stats',
                      headers=_auth_headers())
    assert resp.status_code == 404
    assert resp.get_json()['success'] is False


def test_route_scan_returns_409_when_already_running():
    from electron_app_backend_server import app
    client = app.test_client()
    rss._scan_status['running'] = True
    try:
        resp = client.post('/api/profiles/review-stats/scan',
                           json={'profile_ids': []},
                           headers=_auth_headers())
        assert resp.status_code == 409
        assert resp.get_json()['success'] is False
    finally:
        rss._scan_status['running'] = False
