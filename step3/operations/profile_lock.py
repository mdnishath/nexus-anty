"""
Step 3 - R4/R5: Profile Lock toggle.

Flow:
  1. Go to https://www.google.com/maps/contrib/?hl=en (force English UI)
  2. Wait for full load + settle for the heavy Maps SPA pane
  3. Click "Profile settings" gear:
       button[aria-label="Profile settings"]
     (also matches French "Paramètres du profil" + the language-independent
      jsaction="pane.wfvdle28" hook, so it works on French/bilingual accounts)
  4. Popup appears with toggle:
       button[role="switch"][aria-label="Show your posts on your profile"]
       aria-checked="true"  -> posts shown  -> profile visible  (NOT locked)
       aria-checked="false" -> posts hidden  -> profile locked
  5. R4 (locked=True)  -> want aria-checked="false" -> click if currently "true"
     R5 (locked=False) -> want aria-checked="true"  -> click if currently "false"

Never crashes. Returns True on success or already-in-state, False on error.
On failure it saves a screenshot + dumps visible button aria-labels for diagnosis.
"""

import asyncio
from pathlib import Path

from shared.logger import _log
from shared.robust import robust_goto, find_element

CONTRIB_URL = "https://www.google.com/maps/contrib/?hl=en"

# Profile settings gear — multilingual + language-independent fallbacks.
# The jsaction hook is taken from the real button and is the same in every
# language, so it rescues French/other-locale accounts when aria-label differs.
GEAR_SELECTORS = [
    'button[aria-label="Profile settings"]',        # EN exact
    'button[aria-label*="Profile settings"]',       # EN partial
    'button[data-tooltip="Profile settings"]',      # EN tooltip
    'button[aria-label*="aramètres du profil"]',    # FR (no leading accent)
    'button[data-tooltip*="aramètres du profil"]',  # FR tooltip
    'button[jsaction*="wfvdle28"]',                 # language-independent feature id
]

# "Show your posts on your profile" toggle. aria-checked is language-independent,
# so even the bare role="switch" fallback yields a correct lock/unlock decision.
TOGGLE_SELECTORS = [
    'button[role="switch"][aria-label="Show your posts on your profile"]',  # EN
    'button[role="switch"][aria-label*="Show your posts"]',                 # EN partial
    'button[role="switch"][aria-label*="Afficher vos posts"]',             # FR
    'button[role="switch"][aria-label*="osts sur votre profil"]',          # FR partial
    'button[role="switch"]',                                               # fallback: first switch
]


async def _force_english(page, worker_id):
    """Best-effort: set PREF=hl=en cookie so Maps renders in English."""
    try:
        await page.context.add_cookies([{
            "name": "PREF", "value": "hl=en", "domain": ".google.com", "path": "/",
        }])
        _log(worker_id, "[PROFILE_LOCK] English UI cookie set (hl=en)")
    except Exception as e:
        _log(worker_id, f"[PROFILE_LOCK] Could not set hl=en cookie (non-fatal): {e}")


async def _robust_click(elem, worker_id, label) -> bool:
    """Click via normal -> force -> JS; return True on first success."""
    try:
        await elem.scroll_into_view_if_needed()
    except Exception:
        pass
    for strategy in ("normal", "force", "js"):
        try:
            if strategy == "normal":
                await elem.click(timeout=8000)
            elif strategy == "force":
                await elem.click(force=True, timeout=8000)
            else:
                await elem.evaluate("el => el.click()")
            _log(worker_id, f"[PROFILE_LOCK] Clicked {label} via {strategy}")
            return True
        except Exception as e:
            _log(worker_id, f"[PROFILE_LOCK] {label} {strategy}-click failed: {str(e)[:80]}")
    return False


async def _dump_debug(page, worker_id, tag):
    """Save a screenshot + list visible button aria-labels for diagnosis."""
    try:
        shot_dir = Path(__file__).resolve().parents[2] / "screenshots"
        shot_dir.mkdir(exist_ok=True)
        shot = shot_dir / f"profile_lock_{tag}_w{worker_id}.png"
        await page.screenshot(path=str(shot))
        _log(worker_id, f"[PROFILE_LOCK] Saved debug screenshot: {shot}")
    except Exception as e:
        _log(worker_id, f"[PROFILE_LOCK] Screenshot failed: {e}")
    try:
        labels = await page.eval_on_selector_all(
            "button[aria-label]",
            "els => els.slice(0, 40).map(e => e.getAttribute('aria-label'))",
        )
        _log(worker_id, f"[PROFILE_LOCK] Page button aria-labels: {labels}")
    except Exception as e:
        _log(worker_id, f"[PROFILE_LOCK] Could not dump aria-labels: {e}")


async def set_profile_lock(page, worker_id, locked: bool = True) -> bool:
    """
    Set Google Maps profile visibility.

    locked=True  (R4 Profile Lock ON)  -> hide posts  -> toggle OFF (aria-checked=false)
    locked=False (R5 Profile Lock OFF) -> show posts  -> toggle ON  (aria-checked=true)

    Returns:
        bool: True on success or already in desired state, False on error.
    """
    state_label   = "LOCKED" if locked else "UNLOCKED"
    desired_check = "false"  if locked else "true"

    try:
        _log(worker_id, f"[PROFILE_LOCK] Setting profile to {state_label}...")

        await _force_english(page, worker_id)

        # Navigate to contributor page and wait for full load
        await robust_goto(page, CONTRIB_URL, worker_id=worker_id)
        # Heavy Maps SPA — give the contributor pane time to render the gear
        await asyncio.sleep(3)

        # --- Find the Profile settings gear (wait + multilingual selectors) ---
        gear = await find_element(page, GEAR_SELECTORS, worker_id=worker_id,
                                  label="Profile settings button", max_retries=5)
        if not gear:
            _log(worker_id, "[PROFILE_LOCK] Profile settings button not found")
            await _dump_debug(page, worker_id, "no_gear")
            return False

        if not await _robust_click(gear, worker_id, "Profile settings button"):
            _log(worker_id, "[PROFILE_LOCK] Could not click Profile settings button")
            await _dump_debug(page, worker_id, "gear_click_fail")
            return False

        _log(worker_id, "[PROFILE_LOCK] Clicked Profile settings - waiting for popup...")
        await asyncio.sleep(2)

        # --- Find the toggle in the popup (with retry) ------------------------
        toggle = await find_element(page, TOGGLE_SELECTORS, worker_id=worker_id,
                                    label="Profile lock toggle", max_retries=5)
        if not toggle:
            _log(worker_id, "[PROFILE_LOCK] Toggle switch not found in popup")
            await _dump_debug(page, worker_id, "no_toggle")
            return False

        current = await toggle.get_attribute("aria-checked")
        _log(worker_id,
             f"[PROFILE_LOCK] Toggle aria-checked={current!r} | Want: {desired_check!r}")

        # --- Already in desired state ----------------------------------------
        if current == desired_check:
            _log(worker_id, f"[PROFILE_LOCK] Already {state_label} - no action needed")
            return True

        # --- Click to change state -------------------------------------------
        if not await _robust_click(toggle, worker_id, "lock toggle"):
            _log(worker_id, "[PROFILE_LOCK] Could not click toggle")
            await _dump_debug(page, worker_id, "toggle_click_fail")
            return False
        _log(worker_id, f"[PROFILE_LOCK] Clicked toggle -> now {state_label}")
        await asyncio.sleep(2)

        # --- Verify final state ----------------------------------------------
        try:
            toggle_verify = await find_element(page, TOGGLE_SELECTORS, worker_id=worker_id,
                                               label="Profile lock toggle (verify)")
            if toggle_verify:
                new_state = await toggle_verify.get_attribute("aria-checked")
                if new_state == desired_check:
                    _log(worker_id, f"[PROFILE_LOCK] SUCCESS - Profile is now {state_label}")
                else:
                    _log(worker_id,
                         f"[PROFILE_LOCK] WARNING - Final state: {new_state!r} "
                         f"(expected {desired_check!r})")
            else:
                _log(worker_id,
                     "[PROFILE_LOCK] Could not re-find toggle for verification - assuming success")
        except Exception:
            _log(worker_id,
                 "[PROFILE_LOCK] Could not re-read toggle state - assuming success")

        return True

    except Exception as e:
        _log(worker_id, f"[PROFILE_LOCK] ERROR: {e}")
        try:
            await _dump_debug(page, worker_id, "exception")
        except Exception:
            pass
        return False
