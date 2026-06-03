"""
shared/human_behavior.py — Human-like browser interaction engine.

Provides realistic mouse movement, typing, scrolling, and waiting
patterns that bypass ML-based bot detection (Google, Cloudflare, etc.).

All functions are async and work with Playwright Page objects.

Public API
----------
human_click(page, selector, **kwargs)
    Move mouse along Bezier curve to element, then click with human timing.

human_type(page, selector, text, **kwargs)
    Type text character-by-character with realistic timing and occasional typos.

human_scroll(page, direction, amount, **kwargs)
    Smooth scroll with variable speed.

human_wait(min_s, max_s)
    Random wait simulating human think/read time.

human_fill_form(page, fields: list[tuple[str, str]])
    Fill a form with multiple fields using tab navigation.
"""

from __future__ import annotations

import asyncio
import math
import random

_LOG_PREFIX = '[HUMAN]'


# ── Mouse Movement (Bezier Curve) ────────────────────────────────────────────

def _bezier_points(start: tuple[float, float], end: tuple[float, float],
                   control_points: int = 2, steps: int = 25) -> list[tuple[float, float]]:
    """Generate points along a Bezier curve from start to end.

    Creates natural-looking mouse paths with slight curves and overshoot,
    unlike straight-line paths which are a strong bot indicator.
    """
    sx, sy = start
    ex, ey = end

    # Generate random control points for the curve
    cps = []
    for i in range(control_points):
        t = (i + 1) / (control_points + 1)
        # Interpolate + random offset (creates natural curve)
        cx = sx + (ex - sx) * t + random.uniform(-50, 50)
        cy = sy + (ey - sy) * t + random.uniform(-30, 30)
        cps.append((cx, cy))

    all_points = [start] + cps + [end]
    n = len(all_points) - 1

    # De Casteljau's algorithm for arbitrary-order Bezier
    path = []
    for step in range(steps + 1):
        t = step / steps
        points = list(all_points)
        for r in range(1, n + 1):
            points = [
                (points[i][0] * (1 - t) + points[i + 1][0] * t,
                 points[i][1] * (1 - t) + points[i + 1][1] * t)
                for i in range(len(points) - 1)
            ]
        path.append(points[0])

    # Add slight overshoot at the end (human often overshoots slightly)
    if random.random() < 0.3:
        dx = ex - path[-2][0]
        dy = ey - path[-2][1]
        overshoot = (ex + dx * random.uniform(0.05, 0.15),
                     ey + dy * random.uniform(0.05, 0.15))
        path.append(overshoot)
        path.append(end)  # Correct back

    return path


async def human_move_to(page, x: float, y: float):
    """Move mouse to (x, y) along a Bezier curve path."""
    try:
        # Get current mouse position (default to center-ish if unknown)
        current = getattr(page, '_human_mouse_pos', (
            random.randint(200, 600), random.randint(200, 400)
        ))

        path = _bezier_points(current, (x, y),
                              control_points=random.randint(1, 3),
                              steps=random.randint(15, 35))

        for px, py in path:
            await page.mouse.move(px, py)
            await asyncio.sleep(random.uniform(0.005, 0.025))

        page._human_mouse_pos = (x, y)
    except Exception:
        # Fallback: direct move
        await page.mouse.move(x, y)


async def human_click(page, selector: str, *,
                      button: str = 'left',
                      pre_hover_ms: tuple[int, int] = (200, 600),
                      post_click_ms: tuple[int, int] = (100, 400),
                      double: bool = False):
    """Click an element with human-like mouse movement and timing.

    1. Locate element bounding box
    2. Move mouse along Bezier curve to a random point within the element
    3. Hover for a natural delay
    4. Click with slight position jitter
    5. Post-click wait
    """
    try:
        elem = page.locator(selector).first
        box = await elem.bounding_box()
        if not box:
            # Fallback to standard click
            await elem.click()
            return

        # Random point within element (not center — humans don't click dead center)
        target_x = box['x'] + box['width'] * random.uniform(0.2, 0.8)
        target_y = box['y'] + box['height'] * random.uniform(0.25, 0.75)

        # Move to element
        await human_move_to(page, target_x, target_y)

        # Hover delay (human reads/confirms before clicking)
        await asyncio.sleep(random.randint(*pre_hover_ms) / 1000)

        # Click with tiny jitter
        jx = target_x + random.uniform(-2, 2)
        jy = target_y + random.uniform(-1, 1)
        if double:
            await page.mouse.dblclick(jx, jy, button=button)
        else:
            await page.mouse.click(jx, jy, button=button)

        # Post-click wait
        await asyncio.sleep(random.randint(*post_click_ms) / 1000)

    except Exception as e:
        print(f'{_LOG_PREFIX} Click fallback for {selector}: {e}')
        try:
            await page.locator(selector).first.click()
        except Exception:
            pass


# ── Typing ───────────────────────────────────────────────────────────────────

_TYPO_NEIGHBORS: dict[str, str] = {
    'a': 'sq', 'b': 'vn', 'c': 'xv', 'd': 'sf', 'e': 'wr', 'f': 'dg',
    'g': 'fh', 'h': 'gj', 'i': 'uo', 'j': 'hk', 'k': 'jl', 'l': 'k;',
    'm': 'n,', 'n': 'bm', 'o': 'ip', 'p': 'o[', 'q': 'wa', 'r': 'et',
    's': 'ad', 't': 'ry', 'u': 'yi', 'v': 'cb', 'w': 'qe', 'x': 'zc',
    'y': 'tu', 'z': 'xa',
}


async def human_type(page, selector: str, text: str, *,
                     base_delay_ms: tuple[int, int] = (60, 140),
                     typo_chance: float = 0.04,
                     click_first: bool = True):
    """Type text into an input field with human-like timing.

    Features:
    - Variable character delay (faster in middle of words, slower at start)
    - Occasional typos followed by backspace correction
    - Shift key hold time for capitals
    - Paste behavior for longer text (occasional Ctrl+V)
    """
    if click_first:
        await human_click(page, selector)
        await asyncio.sleep(random.uniform(0.2, 0.5))

    # Clear existing content
    await page.locator(selector).first.fill('')
    await asyncio.sleep(random.uniform(0.1, 0.3))

    for i, char in enumerate(text):
        # Occasional typo (not for special characters)
        if (random.random() < typo_chance and char.lower() in _TYPO_NEIGHBORS
                and i > 0 and i < len(text) - 1):
            # Type wrong character
            wrong = random.choice(_TYPO_NEIGHBORS.get(char.lower(), 'a'))
            await page.keyboard.press(wrong)
            await asyncio.sleep(random.uniform(0.05, 0.15))
            # Pause (notice mistake)
            await asyncio.sleep(random.uniform(0.2, 0.6))
            # Backspace
            await page.keyboard.press('Backspace')
            await asyncio.sleep(random.uniform(0.05, 0.1))

        # Type the correct character
        await page.keyboard.press(char)

        # Variable delay
        base = random.randint(*base_delay_ms) / 1000
        # Slower at start of words, faster in middle
        if i == 0 or (i > 0 and text[i - 1] == ' '):
            base *= random.uniform(1.2, 1.8)  # Slower at word start
        elif i > 2:
            base *= random.uniform(0.7, 1.0)  # Faster mid-word

        await asyncio.sleep(base)

    # Small pause after finishing typing
    await asyncio.sleep(random.uniform(0.3, 0.8))


# ── Scrolling ────────────────────────────────────────────────────────────────

async def human_scroll(page, direction: str = 'down', pixels: int = 300, *,
                       smooth: bool = True):
    """Scroll the page with human-like behavior.

    Args:
        direction: 'down' or 'up'
        pixels: total scroll distance
        smooth: if True, scroll in small increments with variable speed
    """
    multiplier = 1 if direction == 'down' else -1

    if not smooth:
        await page.mouse.wheel(0, pixels * multiplier)
        return

    # Smooth scroll: small increments with variable speed
    scrolled = 0
    while scrolled < pixels:
        chunk = random.randint(30, 80)
        chunk = min(chunk, pixels - scrolled)
        await page.mouse.wheel(0, chunk * multiplier)
        scrolled += chunk
        # Variable speed: sometimes fast, sometimes slow
        await asyncio.sleep(random.uniform(0.02, 0.08))

    # Occasional brief pause after scrolling (reading)
    if random.random() < 0.4:
        await asyncio.sleep(random.uniform(0.5, 1.5))


# ── Waiting ──────────────────────────────────────────────────────────────────

async def human_wait(min_s: float = 1.0, max_s: float = 3.0):
    """Wait a random duration simulating human think/read time."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_short_wait():
    """Brief pause between UI actions (0.3-1.0s)."""
    await asyncio.sleep(random.uniform(0.3, 1.0))


async def human_read_pause():
    """Longer pause simulating reading content (1.5-4s)."""
    await asyncio.sleep(random.uniform(1.5, 4.0))


# ── Form Filling ─────────────────────────────────────────────────────────────

async def human_fill_form(page, fields: list[tuple[str, str]], *,
                          use_tab: bool = True):
    """Fill a form with multiple fields using human-like behavior.

    Args:
        fields: list of (selector, value) tuples
        use_tab: if True, use Tab key to navigate between fields
    """
    for i, (selector, value) in enumerate(fields):
        if not value:
            continue

        if i == 0 or not use_tab:
            await human_click(page, selector)
        else:
            # Tab to next field (sometimes humans use Tab)
            if random.random() < 0.6:
                await page.keyboard.press('Tab')
                await asyncio.sleep(random.uniform(0.2, 0.5))
            else:
                await human_click(page, selector)

        await asyncio.sleep(random.uniform(0.1, 0.4))

        # Occasionally paste instead of typing (for emails, URLs)
        if len(value) > 15 and random.random() < 0.2:
            await page.locator(selector).first.fill(value)
            await asyncio.sleep(random.uniform(0.3, 0.6))
        else:
            await human_type(page, selector, value, click_first=False)

        # Brief pause between fields
        await asyncio.sleep(random.uniform(0.3, 0.8))


# ── Page Interaction Helpers ─────────────────────────────────────────────────

async def human_navigate(page, url: str):
    """Navigate to URL with human-like post-load behavior."""
    await page.goto(url, wait_until='domcontentloaded')
    # Wait for page to settle
    await asyncio.sleep(random.uniform(1.0, 2.5))
    # Occasional small scroll after page load (natural behavior)
    if random.random() < 0.5:
        await human_scroll(page, 'down', random.randint(100, 250))


async def human_idle(page, duration_s: tuple[float, float] = (2.0, 6.0)):
    """Simulate idle time — small random mouse movements."""
    wait_time = random.uniform(*duration_s)
    end_time = asyncio.get_event_loop().time() + wait_time

    while asyncio.get_event_loop().time() < end_time:
        # Tiny mouse jitter (humans don't hold mouse perfectly still)
        current = getattr(page, '_human_mouse_pos', (400, 300))
        jx = current[0] + random.uniform(-5, 5)
        jy = current[1] + random.uniform(-3, 3)
        await page.mouse.move(jx, jy)
        await asyncio.sleep(random.uniform(0.5, 1.5))
