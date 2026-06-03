"""
shared/browser_warmup.py — Browser warm-up & cookie pre-farming engine.

Before Gmail account creation, profiles need to build "trust signals":
- Google cookies (NID, CONSENT, __Secure-ENID)
- Browsing history (diverse site visits)
- Realistic session duration

This module automates a warm-up sequence that makes a fresh browser
profile appear as an established user to Google's anti-bot systems.

Public API
----------
warmup_profile(page, profile, worker_id, config) -> bool
    Run full warm-up sequence on an open browser page.

quick_warmup(page, worker_id) -> bool
    Minimal warm-up (Google search + 1 site visit, ~60s).
"""

from __future__ import annotations

import asyncio
import random

from shared.human_behavior import (
    human_click, human_type, human_scroll, human_wait,
    human_navigate, human_idle, human_read_pause, human_short_wait,
)

_LOG_PREFIX = '[WARMUP]'


def _log(msg, log_type='info'):
    """Log via profile_manager's _log so messages appear in UI."""
    try:
        from shared.profile_manager import _log as _pm_log
        _pm_log(msg, log_type)
    except Exception:
        print(msg)


# ── Search Queries (diverse, realistic) ──────────────────────────────────────

_SEARCH_QUERIES = [
    'weather today', 'latest news', 'best restaurants near me',
    'how to make pasta', 'python tutorial', 'stock market today',
    'movie releases 2026', 'world cup schedule', 'best laptop 2026',
    'recipe for chocolate cake', 'gym workout plan', 'travel tips europe',
    'what time is it', 'currency converter', 'translate hello to spanish',
    'how does wifi work', 'benefits of drinking water', 'best books to read',
    'upcoming holidays', 'dog breeds', 'cat videos', 'funny memes',
    'online shopping deals', 'phone comparison', 'car reviews 2026',
    'healthy breakfast ideas', 'yoga for beginners', 'home office setup',
    'gardening tips', 'diy home projects', 'music playlist',
]

_YOUTUBE_SEARCHES = [
    'how to cook', 'funny animals', 'music mix 2026', 'travel vlog',
    'tech review', 'workout motivation', 'cooking recipe', 'nature documentary',
    'life hacks', 'top 10 movies',
]

_POPULAR_SITES = [
    'https://en.wikipedia.org/wiki/Special:Random',
    'https://www.reddit.com/r/popular/',
    'https://stackoverflow.com/questions',
    'https://www.bbc.com/news',
    'https://www.cnn.com/',
    'https://medium.com/',
    'https://www.amazon.com/',
    'https://www.ebay.com/',
    'https://www.weather.com/',
    'https://www.imdb.com/',
]


# ── Warm-up Steps ────────────────────────────────────────────────────────────

async def _step_google_search(page, worker_id: int, query: str) -> bool:
    """Perform a Google search and click a result."""
    try:
        _log(f'[OPS][W{worker_id}][WARMUP] Google search: "{query}"')

        await human_navigate(page, 'https://www.google.com/')
        await human_wait(1.0, 2.0)

        # Accept cookies/consent if shown
        try:
            consent_btn = page.locator('button:has-text("Accept all"), button:has-text("I agree")')
            if await consent_btn.count() > 0 and await consent_btn.first.is_visible():
                await human_click(page, 'button:has-text("Accept all"), button:has-text("I agree")')
                await human_wait(1.0, 2.0)
        except Exception:
            pass

        # Type search query
        search_selectors = ['textarea[name="q"]', 'input[name="q"]']
        typed = False
        for sel in search_selectors:
            try:
                if await page.locator(sel).first.count() > 0:
                    await human_type(page, sel, query)
                    typed = True
                    break
            except Exception:
                continue

        if not typed:
            _log(f'[OPS][W{worker_id}][WARMUP] Could not find search input')
            return False

        # Press Enter
        await page.keyboard.press('Enter')
        await human_wait(2.0, 4.0)

        # Click a random search result (not ad)
        try:
            results = page.locator('#search a[href]:not([href*="google"]):not([href*="ad"])')
            count = await results.count()
            if count > 0:
                idx = random.randint(0, min(count - 1, 4))
                await results.nth(idx).click()
                await human_wait(2.0, 5.0)
                # Read the page
                await human_scroll(page, 'down', random.randint(200, 500))
                await human_read_pause()
        except Exception:
            pass

        return True

    except Exception as e:
        _log(f'[OPS][W{worker_id}][WARMUP] Google search failed: {e}')
        return False


async def _step_youtube_watch(page, worker_id: int) -> bool:
    """Visit YouTube and watch a video briefly."""
    try:
        query = random.choice(_YOUTUBE_SEARCHES)
        _log(f'[OPS][W{worker_id}][WARMUP] YouTube: "{query}"')

        await human_navigate(page, 'https://www.youtube.com/')
        await human_wait(2.0, 4.0)

        # Accept consent if shown
        try:
            consent = page.locator('button:has-text("Accept all"), tp-yt-paper-button:has-text("Accept all")')
            if await consent.count() > 0 and await consent.first.is_visible():
                await consent.first.click()
                await human_wait(1.5, 3.0)
        except Exception:
            pass

        # Search on YouTube
        try:
            search_input = page.locator('input#search, input[name="search_query"]')
            if await search_input.count() > 0:
                await human_type(page, 'input#search, input[name="search_query"]', query)
                await page.keyboard.press('Enter')
                await human_wait(2.0, 4.0)
        except Exception:
            pass

        # Click first video result
        try:
            videos = page.locator('ytd-video-renderer a#video-title, a#video-title')
            if await videos.count() > 0:
                await videos.first.click()
                # Watch for 20-45 seconds
                watch_time = random.randint(20, 45)
                _log(f'[OPS][W{worker_id}][WARMUP] Watching video for {watch_time}s')
                await asyncio.sleep(watch_time)
        except Exception:
            # Even just visiting YouTube builds cookies
            await asyncio.sleep(random.randint(10, 20))

        return True

    except Exception as e:
        _log(f'[OPS][W{worker_id}][WARMUP] YouTube failed: {e}')
        return False


async def _step_visit_site(page, worker_id: int, url: str) -> bool:
    """Visit a popular website and browse briefly."""
    try:
        _log(f'[OPS][W{worker_id}][WARMUP] Visiting: {url[:60]}')
        await human_navigate(page, url)
        await human_wait(1.5, 3.0)

        # Scroll around
        scrolls = random.randint(1, 3)
        for _ in range(scrolls):
            await human_scroll(page, 'down', random.randint(150, 400))
            await human_wait(1.0, 3.0)

        # Stay on page briefly
        await human_read_pause()
        return True

    except Exception as e:
        _log(f'[OPS][W{worker_id}][WARMUP] Visit failed ({url[:40]}): {e}')
        return False


async def _step_google_maps(page, worker_id: int) -> bool:
    """Visit Google Maps and search for something — builds Google cookies."""
    try:
        _log(f'[OPS][W{worker_id}][WARMUP] Google Maps search')

        await human_navigate(page, 'https://www.google.com/maps')
        await human_wait(3.0, 5.0)

        # Search for a place
        places = ['restaurant', 'coffee shop', 'park', 'hotel', 'museum',
                  'grocery store', 'gym', 'library', 'airport', 'hospital']
        place = random.choice(places)

        try:
            search_box = page.locator('#searchboxinput, input[name="q"]')
            if await search_box.count() > 0:
                await human_type(page, '#searchboxinput, input[name="q"]', place + ' near me')
                await page.keyboard.press('Enter')
                await human_wait(3.0, 5.0)
                await human_scroll(page, 'down', random.randint(100, 300))
                await human_read_pause()
        except Exception:
            await asyncio.sleep(random.randint(5, 10))

        return True

    except Exception as e:
        _log(f'[OPS][W{worker_id}][WARMUP] Google Maps failed: {e}')
        return False


# ── Main Warm-up Functions ───────────────────────────────────────────────────

async def warmup_profile(page, profile: dict, worker_id: int = 0,
                         duration_minutes: int = 5) -> bool:
    """Run a full warm-up sequence on a browser profile.

    Sequence (~5 minutes default):
    1. Google Search x2-3 (builds Google cookies)
    2. YouTube video watch (builds Google cookies + engagement)
    3. Google Maps search (Google cross-service cookies)
    4. Random popular sites x2-3 (diverse browsing pattern)

    Args:
        page: Playwright Page (already open with profile)
        profile: Profile dict (for geo info)
        worker_id: Worker ID for logging
        duration_minutes: Approximate warm-up duration

    Returns:
        True if warm-up completed successfully
    """
    _log(f'[OPS][W{worker_id}][WARMUP] Starting full warm-up (~{duration_minutes} min)')
    steps_done = 0
    steps_failed = 0

    try:
        # 1. Google searches (2-3 queries)
        queries = random.sample(_SEARCH_QUERIES, k=random.randint(2, 3))
        for q in queries:
            ok = await _step_google_search(page, worker_id, q)
            steps_done += 1 if ok else 0
            steps_failed += 0 if ok else 1
            await human_wait(2.0, 5.0)

        # 2. YouTube
        ok = await _step_youtube_watch(page, worker_id)
        steps_done += 1 if ok else 0
        await human_wait(2.0, 4.0)

        # 3. Google Maps
        ok = await _step_google_maps(page, worker_id)
        steps_done += 1 if ok else 0
        await human_wait(2.0, 4.0)

        # 4. Random popular sites (2-3)
        sites = random.sample(_POPULAR_SITES, k=random.randint(2, 3))
        for site in sites:
            ok = await _step_visit_site(page, worker_id, site)
            steps_done += 1 if ok else 0
            await human_wait(1.5, 3.0)

        # 5. Final: go back to Google (leave Google cookie as most recent)
        await human_navigate(page, 'https://www.google.com/')
        await human_wait(2.0, 3.0)

        _log(f'[OPS][W{worker_id}][WARMUP] Complete! {steps_done} steps OK, {steps_failed} failed')
        return steps_failed < steps_done  # At least half succeeded

    except Exception as e:
        _log(f'[OPS][W{worker_id}][WARMUP] Warm-up error: {e}')
        return False


async def quick_warmup(page, worker_id: int = 0) -> bool:
    """Deep Google-trust warmup (~3-4 min) — minimizes QR verification.

    Key Google trust cookies needed BEFORE signup:
    - NID, CONSENT     → set by google.com
    - HSID, SSID, APISID → set by gmail.com / accounts.google.com
    - YSC, VISITOR_INFO → set by youtube.com

    Strategy: visit Google properties in the right ORDER so that by the
    time we reach signup, the browser looks like an established user.
    """
    _log(f'[OPS][W{worker_id}][WARMUP] Deep Google warmup starting...')

    async def _safe_visit(url, wait_min=2.0, wait_max=4.0, scroll=True):
        try:
            _log(f'[OPS][W{worker_id}][WARMUP] → {url[:60]}')
            await human_navigate(page, url)
            await human_wait(wait_min, wait_max)
            if scroll:
                await human_scroll(page, 'down', random.randint(150, 350))
                await human_wait(1.0, 2.5)
        except Exception as _e:
            _log(f'[OPS][W{worker_id}][WARMUP] Visit error: {_e}')

    async def _accept_consent():
        """Click any consent/accept button if visible."""
        try:
            for sel in [
                'button:has-text("Accept all")', 'button:has-text("Accept")',
                'button:has-text("I agree")', 'button:has-text("Reject all")',
                'tp-yt-paper-button:has-text("Accept all")',
            ]:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await human_wait(1.0, 2.0)
                    return
        except Exception:
            pass

    try:
        # ── Step 1: Non-Google site (establish browsing pattern) ──────
        safe_site = random.choice([
            'https://en.wikipedia.org/wiki/Special:Random',
            'https://www.bbc.com/news',
            'https://stackoverflow.com/questions',
        ])
        await _safe_visit(safe_site, 2.0, 4.0)

        # ── Step 2: Google.com (sets NID + CONSENT cookies) ──────────
        _log(f'[OPS][W{worker_id}][WARMUP] Google.com → NID/CONSENT cookies')
        await _safe_visit('https://www.google.com/', 2.0, 3.0, scroll=False)
        await _accept_consent()
        # Search something simple (builds trust, avoids CAPTCHA with proxy)
        try:
            search_sel = 'textarea[name="q"], input[name="q"]'
            if await page.locator(search_sel).first.count() > 0:
                query = random.choice(['weather today', 'news', 'wikipedia', 'youtube'])
                await page.locator(search_sel).first.click()
                await asyncio.sleep(0.5)
                await page.locator(search_sel).first.type(query, delay=random.randint(80, 140))
                await asyncio.sleep(0.8)
                await page.keyboard.press('Enter')
                await human_wait(2.0, 3.5)
                # Scroll search results, don't click (avoids redirects)
                await human_scroll(page, 'down', random.randint(200, 400))
                await human_wait(1.5, 2.5)
        except Exception:
            pass

        # ── Step 3: YouTube (sets YSC/VISITOR_INFO + Google session) ─
        _log(f'[OPS][W{worker_id}][WARMUP] YouTube → session/YSC cookies')
        await _safe_visit('https://www.youtube.com/', 3.0, 5.0)
        await _accept_consent()
        # Watch homepage for 25-40 seconds (builds engagement signal)
        await human_scroll(page, 'down', random.randint(200, 400))
        watch_time = random.randint(25, 40)
        _log(f'[OPS][W{worker_id}][WARMUP] Idle on YouTube {watch_time}s (trust building)')
        await asyncio.sleep(watch_time)

        # ── Step 4: Gmail.com (sets HSID/SSID/APISID — critical!) ────
        # These session cookies make Google think this browser has visited
        # Gmail before → drastically reduces "new device" verification.
        _log(f'[OPS][W{worker_id}][WARMUP] Gmail.com → HSID/SSID cookies (KEY step)')
        await _safe_visit('https://mail.google.com/', 3.0, 5.0)
        # Gmail will redirect to accounts.google.com/signin — that's fine!
        # Just being redirected there sets the __Host-GAPS and GALX cookies.
        await human_wait(2.0, 3.0)
        await _accept_consent()

        # ── Step 5: accounts.google.com directly (sets __Host cookies) ─
        _log(f'[OPS][W{worker_id}][WARMUP] accounts.google.com → __Host cookies')
        await _safe_visit('https://accounts.google.com/', 3.0, 5.0)
        await _accept_consent()
        await human_wait(2.0, 3.0)

        _log(f'[OPS][W{worker_id}][WARMUP] Quick warm-up done ✓')
        return True

    except Exception as e:
        _log(f'[OPS][W{worker_id}][WARMUP] Quick warm-up failed: {e}')
        return False
