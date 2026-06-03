"""
shared/gmail_creator.py — Gmail account creation automation engine.

Orchestrates the full Gmail signup flow using human-like behavior,
SMS verification, and optional CAPTCHA solving.

Public API
----------
create_gmail_account(page, identity, sms, captcha, worker_id) -> dict | None
    Run the complete Gmail signup flow on an open browser page.
"""

from __future__ import annotations

import asyncio
import random
import re

from shared.human_behavior import (
    human_click, human_type, human_scroll, human_wait,
    human_navigate, human_short_wait, human_read_pause,
    human_fill_form,
)

_LOG_PREFIX = '[GMAIL-CREATE]'


def _log(msg, log_type='info'):
    try:
        from shared.profile_manager import _log as _pm_log
        _pm_log(msg, log_type)
    except Exception:
        print(msg)


# ── Selectors ────────────────────────────────────────────────────────────────

_SEL = {
    # Name page
    'first_name': 'input[name="firstName"]',
    'last_name': 'input[name="lastName"]',
    # DOB page
    'birth_month': 'select#month, select[name="month"], #month',
    'birth_day': 'input#day, input[name="day"]',
    'birth_year': 'input#year, input[name="year"]',
    'gender': 'select#gender, select[name="gender"], #gender',
    # Username page
    'username': 'input[name="Username"], input#username',
    'create_own': 'div[data-value="custom"], span:has-text("Create your own")',
    # Password page
    'password': 'input[name="Passwd"], input[type="password"]',
    'confirm_password': 'input[name="PasswdAgain"], input[name="ConfirmPasswd"]',
    # Phone verification
    'phone_input': 'input#phoneNumberId, input[type="tel"], input[name="phoneNumber"]',
    'code_input': 'input#code, input[name="code"], input[type="tel"]',
    # Recovery
    'recovery_email': 'input[name="recovery"], input[type="email"]',
    'skip_recovery': 'button:has-text("Skip"), span:has-text("Skip")',
    # Next button
    'next_btn': 'button:has-text("Next"), button[type="submit"], #next button',
    'verify_btn': 'button:has-text("Verify"), button:has-text("Get code")',
    # Terms
    'agree_btn': 'button:has-text("I agree"), button:has-text("Agree")',
    # Error detection
    'error_msg': 'div[class*="error"], div[aria-live="assertive"]',
    'username_taken': 'div:has-text("already taken"), div:has-text("not available")',
}


# ── Helper Functions ─────────────────────────────────────────────────────────

async def _wait_for_any(page, selectors: list[str], timeout: int = 10) -> str | None:
    """Wait for any of the given selectors to appear. Returns the matched selector."""
    for _ in range(timeout * 2):
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return sel
            except Exception:
                continue
        await asyncio.sleep(0.5)
    return None


async def _click_next(page, worker_id: int) -> bool:
    """Click the Next/Continue button — language independent.

    Google's signup uses Material Design buttons. The "Next" button text
    changes with locale (e.g. "পরবর্তী" in Bengali, "Siguiente" in Spanish).
    We use CSS class + jsname selectors instead of text matching.
    """
    next_selectors = [
        # 1. Google's primary action button (language-independent!)
        #    Class VfPpkd-LgbsSe-OWXEXe-k8QpJ = primary filled button
        'button.VfPpkd-LgbsSe-OWXEXe-k8QpJ',
        # 2. By jsname (Google internal, stable across locales)
        'div.VfPpkd-RLmnJb ~ span.VfPpkd-vQzf8d',
        # 3. Submit button
        'button[type="submit"]',
        # 4. Text fallbacks for common languages
        'button:has-text("Next")',
        'button:has-text("পরবর্তী")',      # Bengali
        'button:has-text("Siguiente")',    # Spanish
        'button:has-text("Далее")',        # Russian
        'button:has-text("Suivant")',      # French
        'button:has-text("Weiter")',       # German
        'button:has-text("次へ")',          # Japanese
        'button:has-text("Continue")',
        'button:has-text("Skip")',
    ]
    for sel in next_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                await human_wait(2.0, 4.0)
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Clicked next via: {sel[:50]}')
                return True
        except Exception:
            continue

    # Last resort: find any visible button that looks like a primary action
    try:
        buttons = page.locator('button')
        count = await buttons.count()
        for i in range(count):
            btn = buttons.nth(i)
            if await btn.is_visible():
                classes = await btn.get_attribute('class') or ''
                # Primary action buttons have these Google Material classes
                if 'k8QpJ' in classes or 'OWXEXe-k8QpJ' in classes:
                    await btn.click()
                    await human_wait(2.0, 4.0)
                    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Clicked next via class scan')
                    return True
    except Exception:
        pass

    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Next button not found')
    return False


async def _check_page_error(page) -> str:
    """Check if there's an error message on the page."""
    try:
        for sel in ['div[class*="error"]', 'div[aria-live="assertive"]',
                     'div[role="alert"]']:
            loc = page.locator(sel)
            if await loc.count() > 0 and await loc.first.is_visible():
                text = await loc.first.text_content()
                if text and len(text.strip()) > 3:
                    return text.strip()
    except Exception:
        pass
    return ''


# ── Signup Flow Steps ────────────────────────────────────────────────────────

async def _step_name(page, identity: dict, worker_id: int) -> bool:
    """Fill first name and last name."""
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Step: Name')

    # Wait for name fields
    found = await _wait_for_any(page, [_SEL['first_name']], timeout=15)
    if not found:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Name fields not found')
        return False

    await human_type(page, _SEL['first_name'], identity['first_name'])
    await human_short_wait()
    await human_type(page, _SEL['last_name'], identity['last_name'])
    await human_short_wait()

    return await _click_next(page, worker_id)


async def _step_dob_gender(page, identity: dict, worker_id: int) -> bool:
    """Fill date of birth and gender.

    Google's signup uses Material Design custom combobox widgets, NOT
    standard HTML <select> elements. The actual structure is:

    Month: div#month > div[role="combobox"] → click opens →
           ul[role="listbox"] > li[role="option"][data-value="1..12"]

    Gender: div#gender > div[role="combobox"] → click opens →
            ul[role="listbox"] > li[data-value="1"]=Male,
            li[data-value="2"]=Female, li[data-value="3"]=Rather not say

    Day/Year: standard input[type="tel"] fields (#day, #year)
    """
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Step: DOB/Gender')
    await human_wait(1.5, 3.0)

    month_val = str(identity['birth_month'])
    day_val = str(identity['birth_day'])
    year_val = str(identity['birth_year'])
    gender_val = str(identity['gender'])  # '1'=male, '2'=female

    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   DOB: {month_val}/{day_val}/{year_val}, Gender: {gender_val}')

    # ── Helper: click Material Design combobox and select option ──────
    async def _select_md_combobox(container_id: str, data_value: str, label: str) -> bool:
        """Click a Google Material Design combobox and select an option.

        Args:
            container_id: '#month' or '#gender'
            data_value: the data-value attribute of the <li> option
            label: human-readable label for logging
        """
        # Strategy 1: Click combobox to open dropdown, then click option
        try:
            combobox = page.locator(f'{container_id} [role="combobox"]').first
            if await combobox.count() > 0:
                await combobox.click()
                await asyncio.sleep(0.5)

                # Wait for listbox options to appear
                option_sel = f'{container_id} li[data-value="{data_value}"]'
                option = page.locator(option_sel).first
                await option.wait_for(state='visible', timeout=3000)
                await option.click()
                await asyncio.sleep(0.3)
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   {label}: combobox click OK')
                return True
        except Exception as e:
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   {label}: combobox click failed: {str(e)[:60]}')

        # Strategy 2: JavaScript — simulate the full Material Design flow
        try:
            result = await page.evaluate(f'''() => {{
                const container = document.querySelector('{container_id}');
                if (!container) return 'no-container';

                // Find and click the combobox to open menu
                const combobox = container.querySelector('[role="combobox"]');
                if (combobox) {{
                    combobox.click();
                }}

                // Small delay then find option
                return new Promise(resolve => {{
                    setTimeout(() => {{
                        const option = container.querySelector('li[data-value="{data_value}"]');
                        if (option) {{
                            option.click();
                            resolve('ok');
                        }} else {{
                            // Try listbox items by role
                            const items = container.querySelectorAll('[role="option"]');
                            for (const item of items) {{
                                if (item.getAttribute('data-value') === '{data_value}') {{
                                    item.click();
                                    resolve('ok-role');
                                    return;
                                }}
                            }}
                            resolve('no-option');
                        }}
                    }}, 400);
                }});
            }}''')
            if result and result.startswith('ok'):
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   {label}: JS click OK ({result})')
                await asyncio.sleep(0.3)
                return True
            else:
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   {label}: JS result: {result}')
        except Exception as e:
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   {label}: JS failed: {str(e)[:60]}')

        # Strategy 3: Focus combobox + keyboard
        try:
            combobox = page.locator(f'{container_id} [role="combobox"]').first
            if await combobox.count() > 0:
                await combobox.focus()
                await asyncio.sleep(0.2)
                # Open with Enter or Space
                await page.keyboard.press('Enter')
                await asyncio.sleep(0.4)
                # Navigate with arrows
                idx = int(data_value)
                for _ in range(idx):
                    await page.keyboard.press('ArrowDown')
                    await asyncio.sleep(0.08)
                await page.keyboard.press('Enter')
                await asyncio.sleep(0.3)
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   {label}: keyboard OK')
                return True
        except Exception as e:
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   {label}: keyboard failed: {str(e)[:60]}')

        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   {label}: ALL strategies failed!')
        return False

    # ── Wait for DOB page elements ────────────────────────────────────
    try:
        await page.locator('#month, #day, #year').first.wait_for(
            state='visible', timeout=10000
        )
    except Exception:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   DOB fields not found on page')
        return False

    # ── Month ─────────────────────────────────────────────────────────
    month_ok = await _select_md_combobox('#month', month_val, 'Month')
    await human_short_wait()

    # ── Day ───────────────────────────────────────────────────────────
    try:
        day_input = page.locator('#day').first
        await day_input.click()
        await asyncio.sleep(0.2)
        await day_input.fill('')
        await day_input.type(day_val, delay=random.randint(80, 150))
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Day: {day_val} OK')
    except Exception as e:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Day failed: {e}')
    await human_short_wait()

    # ── Year ──────────────────────────────────────────────────────────
    try:
        year_input = page.locator('#year').first
        await year_input.click()
        await asyncio.sleep(0.2)
        await year_input.fill('')
        await year_input.type(year_val, delay=random.randint(80, 150))
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Year: {year_val} OK')
    except Exception as e:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Year failed: {e}')
    await human_short_wait()

    # ── Gender ────────────────────────────────────────────────────────
    gender_ok = await _select_md_combobox('#gender', gender_val, 'Gender')
    await human_wait(0.5, 1.0)

    if not month_ok or not gender_ok:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Warning: month={month_ok} gender={gender_ok}')

    # Click Next
    clicked = await _click_next(page, worker_id)
    if not clicked:
        return False

    # Check if still on DOB page (error)
    await human_wait(1.5, 2.5)
    current_url = page.url.lower()
    if 'birthdaygender' in current_url:
        error = await _check_page_error(page)
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Still on DOB page! Error: {error[:80] if error else "none"}')
        return False

    return True


async def _step_username(page, identity: dict, worker_id: int) -> bool:
    """Choose Gmail username."""
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Step: Username ({identity["username"]})')
    await human_wait(1.5, 3.0)

    # Log current URL so we can debug page transitions
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Page URL: {page.url[:80]}')

    # Google may offer suggested usernames or "Create your own" option
    # This can be a radio button, a clickable div, or a text link
    create_own_selectors = [
        'div[data-value="custom"]',
        'div[role="radio"]:has-text("Create your own")',
        'div[role="radio"]:has-text("Create a Gmail")',
        'span:has-text("Create your own Gmail address")',
        'span:has-text("Create your own")',
        'label:has-text("Create your own")',
        '#selectionc4',  # Google internal ID for custom option
    ]
    for sel in create_own_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await human_click(page, sel)
                await human_wait(1.0, 2.0)
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Clicked "Create your own" via: {sel[:40]}')
                break
        except Exception:
            continue

    # Type username — try multiple selectors
    username_selectors = [
        'input[name="Username"]',
        'input#username',
        'input[aria-label*="username" i]',
        'input[aria-label*="Gmail address" i]',
        'input[type="text"][autocomplete="username"]',
    ]

    username_field = None
    for sel in username_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                username_field = sel
                break
        except Exception:
            continue

    if not username_field:
        # Last resort: wait longer and try again
        await human_wait(2.0, 3.0)
        for sel in username_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    username_field = sel
                    break
            except Exception:
                continue

    if not username_field:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Username field not found')
        # Debug: log all visible inputs
        try:
            inputs = await page.evaluate('''() => {
                return Array.from(document.querySelectorAll('input:not([type="hidden"])')).map(
                    i => ({name: i.name, id: i.id, type: i.type, visible: i.offsetParent !== null})
                );
            }''')
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Visible inputs: {inputs}')
        except Exception:
            pass
        return False

    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Username field: {username_field}')

    # Try original username + up to 3 retries with different patterns
    usernames_to_try = [identity['username']]
    base = identity['username'].rstrip('0123456789')  # strip trailing digits
    usernames_to_try.append(f'{base}{random.randint(1000, 9999)}')
    usernames_to_try.append(f'{base}.{random.randint(10, 99)}')
    usernames_to_try.append(f'{identity["first_name"].lower()}{identity["last_name"].lower()}{random.randint(100, 999)}')

    for attempt, uname in enumerate(usernames_to_try):
        try:
            # Clear and type username
            field = page.locator(username_field).first
            await field.click()
            await asyncio.sleep(0.2)
            await field.fill('')
            await asyncio.sleep(0.1)
            await human_type(page, username_field, uname)
            await human_short_wait()

            if not await _click_next(page, worker_id):
                return False

            # Wait for response
            await human_wait(1.5, 2.5)

            # Check for "taken" error
            error = await _check_page_error(page)
            taken_keywords = ['taken', 'not available', 'already', 'choose another', 'try another']
            is_taken = error and any(kw in error.lower() for kw in taken_keywords)

            if is_taken:
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Username "{uname}" taken (attempt {attempt+1}/{len(usernames_to_try)})')

                # Check if Google suggests usernames we can pick
                try:
                    suggestion = page.locator('div[data-value][role="radio"], li[data-value]').first
                    if await suggestion.count() > 0 and await suggestion.is_visible():
                        suggested_name = await suggestion.get_attribute('data-value') or ''
                        if suggested_name and '@' not in suggested_name:
                            await suggestion.click()
                            await human_wait(1.0, 2.0)
                            identity['username'] = suggested_name
                            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Using Google suggestion: {suggested_name}')
                            return await _click_next(page, worker_id)
                except Exception:
                    pass

                if attempt >= len(usernames_to_try) - 1:
                    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} All usernames taken, failed')
                    return False
                continue  # Try next username
            else:
                # No error — success!
                identity['username'] = uname
                return True

        except Exception as e:
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Username attempt error: {e}')
            if attempt >= len(usernames_to_try) - 1:
                return False

    return False


async def _step_password(page, identity: dict, worker_id: int) -> bool:
    """Set account password — fills both Password and Confirm fields.

    Google's password page structure:
    - #passwd > input[name="Passwd"]       (Password)
    - #confirm-passwd > input[name="PasswdAgain"]  (Confirm)
    """
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Step: Password')
    await human_wait(1.0, 2.0)

    password = identity['password']

    # Wait for password page to load
    try:
        await page.locator('#passwd input, input[name="Passwd"]').first.wait_for(
            state='visible', timeout=10000
        )
    except Exception:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Password field not found')
        return False

    # ── Fill Password field ───────────────────────────────────────────
    pwd_selectors = [
        '#passwd input[name="Passwd"]',
        '#passwd input[type="password"]',
        'input[name="Passwd"]',
    ]
    for sel in pwd_selectors:
        try:
            field = page.locator(sel).first
            if await field.count() > 0 and await field.is_visible():
                await field.click()
                await asyncio.sleep(0.2)
                await field.fill('')
                await field.type(password, delay=random.randint(60, 120))
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Password filled OK')
                break
        except Exception:
            continue
    await human_short_wait()

    # ── Fill Confirm Password field ───────────────────────────────────
    confirm_selectors = [
        '#confirm-passwd input[name="PasswdAgain"]',
        '#confirm-passwd input[type="password"]',
        'input[name="PasswdAgain"]',
    ]
    for sel in confirm_selectors:
        try:
            field = page.locator(sel).first
            if await field.count() > 0 and await field.is_visible():
                await field.click()
                await asyncio.sleep(0.2)
                await field.fill('')
                await field.type(password, delay=random.randint(60, 120))
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   Confirm password filled OK')
                break
        except Exception:
            continue
    await human_short_wait()

    return await _click_next(page, worker_id)


async def _step_phone_verify(page, identity: dict, sms_service,
                              worker_id: int) -> bool:
    """Handle phone/QR verification after password step.

    Google may show:
    1. mophoneverification → QR code page (no buttons → navigate to phoneverification)
    2. Phone number input → enter SMS number
    3. No verification needed (rare)
    """
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Step: Phone verification')
    await human_wait(2.0, 3.0)

    page_url = page.url
    page_url_lower = page_url.lower()

    # ── Case 1: mophoneverification QR page ──────────────────────────
    # This is the "Scan QR code" page — NO buttons to click.
    # Strategy: extract the TL token and navigate to the phone input page.
    if 'mophoneverification' in page_url_lower or (
        'verify' in page_url_lower and 'qr' in (await page.inner_text('body'))[:300].lower()
    ):
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} QR page detected — scanning for alternative buttons')

        # Scan ALL visible buttons and try to find phone/alternative option
        try:
            all_buttons = page.locator('button:visible, a[role="button"]:visible')
            count = await all_buttons.count()
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Buttons on page: {count}')
            for i in range(count):
                btn = all_buttons.nth(i)
                try:
                    txt = (await btn.inner_text()).strip()
                    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX}   [{i}] "{txt[:60]}"')
                    if any(kw in txt.lower() for kw in [
                        'phone', 'another', 'other', 'sms', 'code', 'number', 'text', 'call'
                    ]):
                        await btn.click()
                        await human_wait(2.0, 3.0)
                        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Clicked alternative: "{txt[:40]}"')
                        break
                except Exception:
                    continue
        except Exception as _e:
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Button scan error: {_e}')

    # ── Case 2: Check for phone input (direct or after redirect) ──────
    page_url_lower = page.url.lower()
    is_still_qr = 'mophoneverification' in page_url_lower

    phone_found = await _wait_for_any(page, [_SEL['phone_input']], timeout=10)
    if not phone_found:
        if is_still_qr:
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Still on QR page — SMS service required')
            return False
        # Not on any verification page → no verification needed
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} No phone verification required, continuing')
        return True

    if not sms_service:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} No SMS service configured')
        return False

    # Get phone number from SMS service
    country = identity.get('sms_country', 'india')
    order = sms_service.get_number(country)
    if not order:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Failed to get phone number')
        return False

    phone = order.phone_number
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Got number: {phone}')

    # Enter phone number
    await human_type(page, _SEL['phone_input'], phone)
    await human_short_wait()

    # Click Next/Verify
    if not await _click_next(page, worker_id):
        sms_service.cancel(order.order_id)
        return False

    # Wait for code
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Waiting for SMS code...')
    code = sms_service.wait_for_code(order.order_id, timeout=120)
    if not code:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} SMS code timeout')
        sms_service.cancel(order.order_id)
        return False

    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Got code: {code}')
    identity['phone_number'] = phone

    # Wait for code input to appear
    await human_wait(2.0, 4.0)
    code_found = await _wait_for_any(page, [_SEL['code_input']], timeout=15)
    if not code_found:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Code input field not found')
        return False

    # Enter verification code
    await human_type(page, _SEL['code_input'], code)
    await human_short_wait()
    return await _click_next(page, worker_id)


async def _step_recovery(page, identity: dict, worker_id: int) -> bool:
    """Handle recovery email (skip or fill)."""
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Step: Recovery')
    await human_wait(1.0, 2.5)

    # Try to skip
    try:
        skip = page.locator(_SEL['skip_recovery'])
        if await skip.count() > 0 and await skip.first.is_visible():
            await human_click(page, _SEL['skip_recovery'])
            await human_wait(1.5, 3.0)
            return True
    except Exception:
        pass

    # If recovery email field visible, fill or skip
    try:
        rec_field = page.locator(_SEL['recovery_email'])
        if await rec_field.count() > 0 and await rec_field.first.is_visible():
            if identity.get('recovery_email'):
                await human_type(page, _SEL['recovery_email'],
                                 identity['recovery_email'])
            # Click next regardless
            return await _click_next(page, worker_id)
    except Exception:
        pass

    # Not on recovery page — continue
    return await _click_next(page, worker_id)


async def _step_agree_terms(page, worker_id: int) -> bool:
    """Accept Google Terms of Service."""
    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Step: Terms')
    await human_wait(1.5, 3.0)

    # Scroll down to see terms
    await human_scroll(page, 'down', random.randint(200, 400))
    await human_wait(1.0, 2.0)

    # Click agree — use class-based selector first (language independent)
    agree_selectors = [
        # Google Material primary button (same class as Next)
        'button.VfPpkd-LgbsSe-OWXEXe-k8QpJ',
        # Text fallbacks for multiple languages
        'button:has-text("I agree")',
        'button:has-text("Agree")',
        'button:has-text("Accept")',
        'button:has-text("আমি সম্মত")',     # Bengali
        'button:has-text("Acepto")',        # Spanish
        'button:has-text("Согласен")',      # Russian
        'button:has-text("J\'accepte")',    # French
        'button:has-text("Ich stimme zu")', # German
        'button:has-text("同意する")',        # Japanese
    ]

    for sel in agree_selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await loc.click()
                await human_wait(3.0, 5.0)
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Agreed via: {sel[:40]}')
                return True
        except Exception:
            continue

    # Try clicking any remaining Next/Submit
    return await _click_next(page, worker_id)


# ── Main Entry Point ─────────────────────────────────────────────────────────

async def create_gmail_account(page, identity: dict, *,
                                sms_service=None,
                                captcha_solver=None,
                                worker_id: int = 0,
                                max_retries: int = 2) -> dict | None:
    """Run the complete Gmail account creation flow.

    Args:
        page: Playwright page (browser already open with profile)
        identity: dict from username_generator.generate_identity()
        sms_service: SMSService instance for phone verification
        captcha_solver: CaptchaSolver instance for CAPTCHA (optional)
        worker_id: worker ID for logging
        max_retries: max retry attempts for failed steps

    Returns:
        dict with created account info, or None on failure:
        {
            'email': 'username@gmail.com',
            'password': '...',
            'first_name': '...',
            'last_name': '...',
            'phone_number': '...',
            'status': 'success' | 'failed',
            'error': '...',
        }
    """
    result = {
        'email': f'{identity["username"]}@gmail.com',
        'password': identity['password'],
        'first_name': identity['first_name'],
        'last_name': identity['last_name'],
        'phone_number': '',
        'status': 'failed',
        'error': '',
    }

    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Starting: {identity["username"]}')

    try:
        # Navigate to signup
        await human_navigate(page, 'https://accounts.google.com/signup')
        await human_wait(2.0, 4.0)

        # Step 1: Name
        if not await _step_name(page, identity, worker_id):
            result['error'] = 'Name step failed'
            return result

        # Step 2: DOB + Gender
        if not await _step_dob_gender(page, identity, worker_id):
            result['error'] = 'DOB/Gender step failed'
            return result

        # Step 3: Username
        if not await _step_username(page, identity, worker_id):
            result['error'] = 'Username step failed'
            return result

        # Update email in result (may have changed if taken)
        result['email'] = f'{identity["username"]}@gmail.com'

        # Step 4: Password
        if not await _step_password(page, identity, worker_id):
            result['error'] = 'Password step failed'
            return result

        # Step 5: Phone verification
        if not await _step_phone_verify(page, identity, sms_service, worker_id):
            result['error'] = 'Phone verification failed'
            return result

        result['phone_number'] = identity.get('phone_number', '')

        # Step 6: Recovery (skip)
        await _step_recovery(page, identity, worker_id)

        # Step 7: Terms
        if not await _step_agree_terms(page, worker_id):
            result['error'] = 'Terms acceptance failed'
            return result

        # Check final URL — success if on myaccount or mail
        await human_wait(3.0, 5.0)
        url = page.url.lower()
        if any(kw in url for kw in ['myaccount', 'mail.google', 'accounts.google.com/b']):
            result['status'] = 'success'
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} SUCCESS: {result["email"]}')
        else:
            # May still be on intermediate pages
            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Final URL: {url[:80]}')
            # Try one more Next click
            await _click_next(page, worker_id)
            await human_wait(2.0, 3.0)
            if 'myaccount' in page.url.lower() or 'mail.google' in page.url.lower():
                result['status'] = 'success'
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} SUCCESS (delayed): {result["email"]}')
            else:
                result['error'] = f'Unexpected final page: {page.url[:60]}'

        return result

    except Exception as e:
        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Error: {e}', 'error')
        result['error'] = str(e)
        return result
