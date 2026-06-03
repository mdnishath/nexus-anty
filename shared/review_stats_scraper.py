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

import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

STATS_FILE_NAME = 'review_stats.json'
STATS_DIR_NAME = 'review_stats'   # used when D:-rooted fallback splits per profile
SCHEMA_VERSION = 1

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

    // Extract a usable PUBLIC link to the place — the contrib URL needs login
    // to view, but /maps/place/ URLs work for everyone. Try the business
    // anchor first, then the share button's stored href, then empty.
    let share_link = '';
    const placeAnchor = r.querySelector(
      'a[href*="/maps/place/"], a[href*="/maps/@"], a[data-href*="/maps/place/"]'
    );
    if (placeAnchor) {
      const h = placeAnchor.getAttribute('href') || placeAnchor.getAttribute('data-href') || '';
      share_link = h.startsWith('/') ? ('https://www.google.com' + h) : h;
    }
    if (!share_link) {
      const shareBtn = r.querySelector('button.gllhef[data-href]');
      if (shareBtn) share_link = shareBtn.getAttribute('data-href') || '';
    }

    return { review_id: id, business: biz, address: addr,
             stars, time, text, status, share_link };
  });
}
"""

SCROLL_LOAD_JS = r"""
async () => {
  // Resolve scroll container: contrib feed is in a virtualised side panel.
  // Google rotates the class suffix occasionally; try a couple of selectors
  // before falling back to window scroll.
  const candidates = [
    'div.m6QErb.XiKgde[tabindex="-1"]',
    'div.m6QErb[role="region"]',
  ];
  let container = null;
  for (const sel of candidates) {
    const el = document.querySelector(sel);
    if (el) { container = el; break; }
  }
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
    if _storage_path is None:
        raise RuntimeError('review_stats_scraper.init() must be called first')
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


def _write_atomic_unlocked(data: dict) -> None:
    """Atomic write to review_stats.json. Caller MUST hold _file_lock."""
    p = _stats_file()
    tmp = p.with_suffix(p.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _save_stats_raw(data: dict) -> None:
    """Atomic write: serialize to .tmp → os.replace → final."""
    with _file_lock:
        _write_atomic_unlocked(data)


def get_all_stats() -> dict:
    """Return per-profile counts WITHOUT the reviews array (small payload)."""
    with _file_lock:
        profiles = _load_stats_raw().get('profiles', {})
    out = {}
    for pid, rec in profiles.items():
        out[pid] = {k: v for k, v in rec.items() if k != 'reviews'}
    return out


def get_profile_stats(profile_id: str) -> dict | None:
    """Return one profile's full record incl. `reviews`. None if missing."""
    with _file_lock:
        profiles = _load_stats_raw().get('profiles', {})
    return profiles.get(profile_id)


def _upsert_profile_record(profile_id: str, record: dict) -> None:
    """Insert-or-update a single profile's record. Atomic per call."""
    with _file_lock:
        data = _load_stats_raw()
        data['profiles'][profile_id] = record
        _write_atomic_unlocked(data)


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
    from shared import nexus_profile_manager as pm
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
        num_workers = max(1, min(int(num_workers or 5), 20))

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
    is shared across workers (it's a thread-safe factory).

    Launch-stagger lock: even with the semaphore at N workers, spinning
    up N chromium processes at the same wall-clock instant causes
    Playwright's transport setup to race on disk I/O and port allocation
    — Windows reports "browser launch failed" intermittently. Serialising
    just the launch_persistent_context() call (≈0.5–2s of cold start
    each) with a global lock + small jitter spreads the boot storm out so
    every worker gets a clean start. Once a context is up, the rest of
    each profile's scrape runs fully in parallel.
    """
    from playwright.async_api import async_playwright
    from shared import nexus_profile_manager as pm
    sem = asyncio.Semaphore(num_workers)
    launch_gate = asyncio.Lock()

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
                    # §8.3: strict per-profile wall-clock cap.
                    record = await asyncio.wait_for(
                        _scrape_one_profile(playwright, profile, cancel_event,
                                            launch_gate=launch_gate),
                        timeout=120,
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
                        'scan_error':  'timeout after 120s',
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


async def _scrape_one_profile(playwright, profile, cancel_event,
                              launch_gate=None) -> dict:
    """Scrape one profile's /maps/contrib/ Reviews tab. Returns the
    aggregated record (same shape as _aggregate output) with `email`
    omitted (added by the coordinator).

    Hard timeout (120s) is applied by the caller via asyncio.wait_for().

    launch_gate: optional asyncio.Lock used to serialise the launch step
    across concurrent workers — prevents the "browser launch failed"
    storm that hits when 5+ chromium processes try to boot at the same
    instant on Windows.
    """
    from shared import nexus_profile_manager as pm

    pid = profile.get('id')

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

    ctx = None
    bridge = None
    try:
        # Launch with retry — Windows occasionally reports a launch
        # failure during a boot storm (port collision, transient I/O
        # error). Serialising via launch_gate + retrying twice with a
        # short backoff turns nearly all of these into eventual successes.
        last_launch_err = None
        for attempt in range(1, 4):  # 3 tries total
            try:
                async def _do_launch():
                    if launch_gate is not None:
                        async with launch_gate:
                            return await launch_clean_context(playwright, profile)
                    return await launch_clean_context(playwright, profile)

                ctx, bridge = await asyncio.wait_for(_do_launch(), timeout=45)
                break  # success
            except asyncio.TimeoutError:
                last_launch_err = 'launch timeout (45s)'
            except Exception as e:
                last_launch_err = f'{type(e).__name__}: {str(e)[:120]}'
            if attempt < 3:
                await asyncio.sleep(1.5 * attempt)  # 1.5s, 3s backoff
                if cancel_event.is_set():
                    return _error_record('cancelled')
        if ctx is None:
            return _error_record(f'launch: {last_launch_err}')

        page = await ctx.new_page()
        # Auto-close any popups (consent dialogs, auth prompts) so they don't pile up
        page.on('popup', lambda p: asyncio.ensure_future(p.close()))

        try:
            await asyncio.wait_for(
                page.goto('https://www.google.com/maps/contrib/',
                          wait_until='domcontentloaded'),
                timeout=20,
            )
        except asyncio.TimeoutError:
            return _error_record('navigation timeout')
        except Exception as e:
            return _error_record(f'navigation: {type(e).__name__}: {e}')

        if 'accounts.google.com' in (page.url or ''):
            return _error_record('not_logged_in')

        # Click the Reviews tab (data-tab-index="1" — language-agnostic).
        # A missing tablist means the contrib page didn't render at all —
        # that's a real error.
        try:
            await page.wait_for_selector('div.RWPxGd[role="tablist"]', timeout=15000)
            already = await page.locator(
                'button[role="tab"][data-tab-index="1"][aria-selected="true"]'
            ).count()
            if not already:
                await page.click('button[role="tab"][data-tab-index="1"]')
        except Exception as e:
            return _error_record(f'tablist: {type(e).__name__}: {str(e)[:80]}')

        # Reviews tab is now selected. Wait briefly for review cards to
        # appear, but treat "no cards" as a valid empty state — some
        # logged-in profiles legitimately have zero reviews and should be
        # recorded as total=0 (not error).
        try:
            await page.wait_for_selector('div.jftiEf[data-review-id]', timeout=10000)
            await _scroll_load_all(page, cancel_event)
        except Exception:
            pass  # 0 reviews → _aggregate() returns all-zeros, scan_status='ok'

        reviews = await page.evaluate(SCRAPE_JS)
        return _aggregate(reviews)

    finally:
        try:
            if ctx is not None:
                await ctx.close()
        except Exception:
            pass
        # Stop the SOCKS5 auth bridge (if one was started) so its local
        # relay server doesn't leak across scans.
        if bridge is not None:
            try:
                await bridge.stop()
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


async def _scroll_load_all(page, cancel_event) -> int:
    """Scroll the contrib feed until no new reviews appear for 2 rounds.
    Honours cancel_event by bounding total wall-clock to 60s (the JS itself
    caps at 50 iterations × 800ms ≈ 40s; the outer wait_for is a safety net
    for a frozen Google page).

    Returns the final review count (best-effort, 0 on failure)."""
    if cancel_event.is_set():
        return 0
    try:
        return await asyncio.wait_for(page.evaluate(SCROLL_LOAD_JS), timeout=60)
    except (asyncio.TimeoutError, Exception):
        # Outer scrape still counts whatever rows DOM has — propagating
        # here would lose a partial result.
        return 0


def _build_pw_proxy(profile: dict) -> dict | None:
    """Convert profile.proxy → Playwright proxy dict, or None if no proxy.

    Playwright handles HTTP-proxy auth natively, so we don't need the
    custom proxy-bridge that the regular launch path uses.
    """
    p = profile.get('proxy') or {}
    if not p:
        return None
    server = p.get('server')
    if not server and p.get('host'):
        ptype = p.get('type', 'http')
        port = p.get('port', '')
        scheme = 'socks5' if ptype == 'socks5' else 'http'
        server = f'{scheme}://{p["host"]}:{port}' if port else f'{scheme}://{p["host"]}'
    if not server:
        return None
    out: dict = {'server': server}
    if p.get('username'):
        out['username'] = p['username']
    if p.get('password'):
        out['password'] = p['password']
    return out


async def launch_clean_context(playwright, profile: dict):
    """Launch a clean, headless persistent context for review-stats scraping.

    Same approach as Live Check: Playwright's launch_persistent_context with
    headless=True (no popup window ever) and the same nstchrome binary that
    owns the profile (so the on-disk cookie store decrypts correctly).

    Proxy: Playwright/Chromium handles HTTP-proxy auth natively, BUT it
    CANNOT do SOCKS5 *authentication* — passing socks5://user:pass straight
    to launch_persistent_context() fails with "Browser does not support
    socks5 proxy authentication". So for SOCKS5+auth proxies we route
    through a local SocksBridge (exactly like the foreground launch path,
    shared.browser._setup_proxy) and point the browser at an authless
    socks5://127.0.0.1:<port> relay.

    Returns (BrowserContext, socks_bridge_or_None). Caller MUST
    `await ctx.close()` AND, if a bridge is returned, `await bridge.stop()`
    in finally. On launch failure or cancellation this function cleans up
    its own ctx/bridge before re-raising, so nothing leaks on the retry.
    """
    from shared.nexus_profile_manager import _resolve_profile_dir
    from shared.stealth_chrome import _find_nexus_binary

    profile_dir = _resolve_profile_dir(profile)
    if not profile_dir:
        raise RuntimeError('profile has no profile_dir')

    executable_path = _find_nexus_binary()
    pw_proxy = _build_pw_proxy(profile)

    # Resolve SOCKS5+auth → local authless bridge (same as foreground path).
    bridge = None
    if pw_proxy:
        from shared.browser import _setup_proxy
        pw_proxy, bridge = await _setup_proxy(pw_proxy)

    launch_kwargs: dict = {
        'user_data_dir': profile_dir,
        'headless': True,
        'args': [
            '--disable-blink-features=AutomationControlled',
            '--no-default-browser-check',
            '--no-first-run',
            '--disable-features=Translate',
        ],
    }
    if executable_path:
        launch_kwargs['executable_path'] = executable_path
    if pw_proxy:
        launch_kwargs['proxy'] = pw_proxy

    ctx = None
    try:
        ctx = await playwright.chromium.launch_persistent_context(**launch_kwargs)
        return ctx, bridge
    except BaseException:
        # Launch failed OR the caller's wait_for() cancelled us mid-launch.
        # Tear down whatever we started so the next retry starts clean and
        # the local bridge server doesn't leak. BaseException also catches
        # asyncio.CancelledError.
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass
        if bridge is not None:
            try:
                await bridge.stop()
            except Exception:
                pass
        raise
