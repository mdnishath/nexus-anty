"""
shared/gmail_campaign.py — Gmail creation campaign orchestrator.

Manages bulk Gmail account creation with parallel workers,
warm-up scheduling, and progress tracking.

Public API
----------
GmailCampaign(name, config)
    Create a campaign instance.

campaign.add_accounts(identities)
    Add accounts to creation queue.

campaign.start(worker_count)
    Start creating accounts with parallel workers.

campaign.stop()
    Stop the campaign.

campaign.get_status() -> dict
    Get campaign progress status.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

_LOG_PREFIX = '[CAMPAIGN]'


def _log(msg, log_type='info'):
    try:
        from shared.profile_manager import _log as _pm_log
        _pm_log(msg, log_type)
    except Exception:
        print(msg)


class AccountStatus(Enum):
    PENDING = 'pending'
    WARMING = 'warming'
    CREATING = 'creating'
    VERIFYING = 'verifying'
    SUCCESS = 'success'
    FAILED = 'failed'


class CampaignStatus(Enum):
    IDLE = 'idle'
    RUNNING = 'running'
    PAUSED = 'paused'
    COMPLETED = 'completed'


@dataclass
class AccountEntry:
    """Single account in a campaign."""
    identity: dict
    status: str = 'pending'
    error: str = ''
    created_email: str = ''
    phone_number: str = ''
    started_at: str = ''
    finished_at: str = ''

    def to_dict(self) -> dict:
        return {
            'username': self.identity.get('username', ''),
            'first_name': self.identity.get('first_name', ''),
            'last_name': self.identity.get('last_name', ''),
            'status': self.status,
            'error': self.error,
            'created_email': self.created_email,
            'phone_number': self.phone_number,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
        }


class GmailCampaign:
    """Manages a batch Gmail account creation campaign."""

    def __init__(self, name: str, config: dict):
        """
        Args:
            name: Campaign name
            config: dict with:
                - sms_provider: '5sim', 'smsactivate', etc.
                - sms_api_key: API key
                - sms_country: 'india', 'usa', etc.
                - captcha_provider: '2captcha', etc. (optional)
                - captcha_api_key: API key (optional)
                - worker_count: parallel workers (default 1)
                - warmup_enabled: bool (default True)
                - stagger_delay: seconds between workers (default 30)
                - proxy_list: list of proxy dicts (optional)
        """
        self.name = name
        self.config = config
        self.accounts: list[AccountEntry] = []
        self.status = CampaignStatus.IDLE
        self.created_at = datetime.now().isoformat()
        self._stop_flag = False
        self._task: Optional[asyncio.Task] = None

    def add_accounts(self, identities: list[dict]):
        """Add accounts to the creation queue."""
        for identity in identities:
            self.accounts.append(AccountEntry(identity=identity))
        _log(f'{_LOG_PREFIX} Added {len(identities)} accounts to "{self.name}"')

    def get_status(self) -> dict:
        """Get campaign status summary."""
        total = len(self.accounts)
        by_status = {}
        for acc in self.accounts:
            by_status[acc.status] = by_status.get(acc.status, 0) + 1

        return {
            'name': self.name,
            'status': self.status.value,
            'total': total,
            'pending': by_status.get('pending', 0),
            'warming': by_status.get('warming', 0),
            'creating': by_status.get('creating', 0),
            'success': by_status.get('success', 0),
            'failed': by_status.get('failed', 0),
            'accounts': [acc.to_dict() for acc in self.accounts],
            'created_at': self.created_at,
        }

    def stop(self):
        """Signal the campaign to stop."""
        self._stop_flag = True
        self.status = CampaignStatus.PAUSED
        _log(f'{_LOG_PREFIX} Campaign "{self.name}" stopping...')

    async def start(self):
        """Start creating accounts with parallel workers.

        This is the main entry point — call from an async context.
        """
        self.status = CampaignStatus.RUNNING
        self._stop_flag = False
        worker_count = self.config.get('worker_count', 1)

        _log(f'{_LOG_PREFIX} Campaign "{self.name}" started with {worker_count} workers')

        # Create services
        sms_service = self._create_sms_service()
        captcha_solver = self._create_captcha_solver()

        # Process accounts with worker pool
        pending = [acc for acc in self.accounts if acc.status == 'pending']
        queue = asyncio.Queue()
        for acc in pending:
            await queue.put(acc)

        workers = []
        for i in range(min(worker_count, len(pending))):
            task = asyncio.create_task(
                self._worker(i + 1, queue, sms_service, captcha_solver)
            )
            workers.append(task)
            # Stagger worker starts
            stagger = self.config.get('stagger_delay', 30)
            if i < len(pending) - 1:
                await asyncio.sleep(stagger)
                if self._stop_flag:
                    break

        # Wait for all workers
        await asyncio.gather(*workers, return_exceptions=True)

        if not self._stop_flag:
            self.status = CampaignStatus.COMPLETED
            _log(f'{_LOG_PREFIX} Campaign "{self.name}" completed!')

    async def _worker(self, worker_id: int, queue: asyncio.Queue,
                      sms_service, captcha_solver):
        """Single worker that processes accounts from the queue."""
        while not self._stop_flag:
            try:
                acc = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            acc.started_at = datetime.now().isoformat()

            try:
                from shared.browser_warmup import quick_warmup
                from shared.gmail_creator import create_gmail_account
                from shared.stealth_chrome import StealthChrome
                from shared.geo_matcher import get_geo_info, extract_proxy_ip

                proxy = self._get_proxy_for_worker(worker_id)
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Starting: {acc.identity["username"]}')

                # ── Geo detection: match browser timezone to IP ────────
                # TZ env var is set at Chrome PROCESS level (undetectable!)
                # CDP Emulation.setTimezoneOverride IS detectable, so we avoid it
                geo = None
                proxy_dict = None
                ip_timezone = None
                locale = 'en-US'
                accept_lang = 'en-US,en;q=0.9'

                if proxy:
                    proxy_dict = {
                        'server': proxy.get('server', ''),
                        'username': proxy.get('username', ''),
                        'password': proxy.get('password', ''),
                    }
                    proxy_ip = extract_proxy_ip(proxy)
                    if proxy_ip:
                        geo = get_geo_info(proxy_ip)

                if not geo:
                    # No proxy or proxy geo failed — detect own IP timezone
                    try:
                        import urllib.request, json as _json
                        resp = urllib.request.urlopen(
                            'http://ip-api.com/json/?fields=status,timezone',
                            timeout=5
                        )
                        data = _json.loads(resp.read())
                        if data.get('status') == 'success':
                            ip_timezone = data.get('timezone')
                            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Own IP timezone: {ip_timezone}')
                    except Exception:
                        pass

                if geo:
                    ip_timezone = geo.timezone
                    locale = geo.locale
                    accept_lang = geo.accept_language
                    _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Geo: {geo.country} → {locale}')

                # Create temp profile directory for this account
                import tempfile
                profile_dir = tempfile.mkdtemp(prefix=f'gmail_w{worker_id}_')

                chrome = StealthChrome()

                try:
                    # Browser visibility
                    show_browser = self.config.get('show_browser', True)
                    win_w, win_h = 1280, 800

                    extra = []
                    if show_browser:
                        offset_x = (worker_id - 1) * 40
                        offset_y = (worker_id - 1) * 30
                        extra.append(f'--window-position={offset_x},{offset_y}')
                    else:
                        extra.append('--start-minimized')

                    # Only set language flags when using proxy (different country)
                    if proxy_dict and locale != 'en-US':
                        extra.append(f'--lang={locale}')
                        extra.append(f'--accept-lang={accept_lang}')

                    ws_url = await chrome.start(
                        profile_dir=profile_dir,
                        proxy=proxy_dict,
                        window_size=(win_w, win_h),
                        extra_args=extra,
                        # NOTE: timezone= (TZ env var) does NOT work on Windows Chrome.
                        # Windows Chrome always uses the Windows system timezone.
                        # We use CDP setTimezoneOverride after connect instead.
                    )

                    # Connect Playwright
                    from playwright.async_api import async_playwright
                    pw = await async_playwright().start()
                    browser = await pw.chromium.connect_over_cdp(ws_url)
                    context = browser.contexts[0]
                    page = context.pages[0] if context.pages else await context.new_page()

                    # ── Timezone JS spoof — persistent across ALL pages ──────
                    # CDP setTimezoneOverride resets on navigation — useless!
                    # context.add_init_script runs on EVERY page load, fixing
                    # Intl.DateTimeFormat().resolvedOptions().timeZone to match IP.
                    if ip_timezone:
                        tz_script = f"""
(function() {{
    const TARGET_TZ = '{ip_timezone}';

    // Override Intl.DateTimeFormat to always report TARGET_TZ
    const _OrigDTF = Intl.DateTimeFormat;
    function PatchedDTF(locales, options) {{
        options = Object.assign({{}}, options || {{}});
        if (!options.timeZone) {{
            options.timeZone = TARGET_TZ;
        }}
        return new _OrigDTF(locales, options);
    }}
    PatchedDTF.prototype = _OrigDTF.prototype;
    PatchedDTF.supportedLocalesOf = _OrigDTF.supportedLocalesOf;
    Object.defineProperty(PatchedDTF.prototype, 'resolvedOptions', {{
        value: function() {{
            const opts = _OrigDTF.prototype.resolvedOptions.call(this);
            opts.timeZone = TARGET_TZ;
            return opts;
        }}
    }});
    Intl.DateTimeFormat = PatchedDTF;

    // Also patch Date.prototype methods that expose timezone
    const _origGetTimezoneOffset = Date.prototype.getTimezoneOffset;
    Date.prototype.getTimezoneOffset = function() {{
        try {{
            const tzDate = new _OrigDTF('en', {{
                timeZone: TARGET_TZ,
                timeZoneName: 'shortOffset'
            }}).formatToParts(this);
            const tzStr = tzDate.find(p => p.type === 'timeZoneName')?.value || 'GMT+0';
            const m = tzStr.match(/GMT([+-])(\\d+)(?::(\\d+))?/);
            if (m) {{
                const sign = m[1] === '+' ? -1 : 1;
                return sign * (parseInt(m[2]) * 60 + parseInt(m[3] || 0));
            }}
        }} catch(e) {{}}
        return _origGetTimezoneOffset.call(this);
    }};
}})();
"""
                        try:
                            await context.add_init_script(tz_script)
                            # Also run on current page immediately
                            if context.pages:
                                await context.pages[0].evaluate(tz_script)
                            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} TZ spoof injected: {ip_timezone}')
                        except Exception as _tz_err:
                            _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} TZ spoof failed: {_tz_err}')

                    # ── Inject stealth scripts (UA metadata + Client Hints) ──
                    # inject_scripts handles: sec-ch-ua headers, SSL bypass,
                    # popup wake, and NexusBrowser stealth if available
                    try:
                        await chrome.inject_scripts(context, [])
                        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Stealth scripts injected OK')
                    except Exception as e:
                        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Stealth injection warning: {e}')

                    # Warm-up phase
                    if self.config.get('warmup_enabled', True):
                        acc.status = 'warming'
                        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Warming up profile...')
                        await quick_warmup(page, worker_id)

                    # Creation phase
                    acc.status = 'creating'
                    result = await create_gmail_account(
                        page, acc.identity,
                        sms_service=sms_service,
                        captcha_solver=captcha_solver,
                        worker_id=worker_id,
                    )

                    if result and result['status'] == 'success':
                        acc.status = 'success'
                        acc.created_email = result['email']
                        acc.phone_number = result.get('phone_number', '')
                        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} SUCCESS: {acc.created_email}')
                    else:
                        acc.status = 'failed'
                        acc.error = result.get('error', 'Unknown error') if result else 'No result'
                        _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} FAILED: {acc.error}')

                finally:
                    # Cleanup
                    try:
                        await chrome.stop()
                    except Exception:
                        pass
                    try:
                        await pw.stop()
                    except Exception:
                        pass

            except Exception as e:
                acc.status = 'failed'
                acc.error = str(e)
                _log(f'[OPS][W{worker_id}]{_LOG_PREFIX} Worker error: {e}', 'error')

            acc.finished_at = datetime.now().isoformat()

            # Random delay between accounts
            if not self._stop_flag:
                delay = random.randint(20, 60)
                await asyncio.sleep(delay)

    def _create_sms_service(self):
        """Create SMS service from config."""
        provider = self.config.get('sms_provider', '')
        api_key = self.config.get('sms_api_key', '')
        if provider and api_key:
            try:
                from shared.sms_service import SMSService
                return SMSService(provider, api_key)
            except Exception as e:
                _log(f'{_LOG_PREFIX} SMS service init failed: {e}', 'error')
        return None

    def _create_captcha_solver(self):
        """Create CAPTCHA solver from config."""
        provider = self.config.get('captcha_provider', '')
        api_key = self.config.get('captcha_api_key', '')
        if provider and api_key:
            try:
                from shared.captcha_solver import CaptchaSolver
                return CaptchaSolver(provider, api_key)
            except Exception as e:
                _log(f'{_LOG_PREFIX} CAPTCHA solver init failed: {e}', 'error')
        return None

    def _get_proxy_for_worker(self, worker_id: int) -> dict | None:
        """Get a proxy for a specific worker.

        Supports two config formats:
        - config['proxy']: single proxy dict from UI (all workers share it)
        - config['proxy_list']: pool of proxies (round-robin per worker)
        """
        # Single proxy from UI
        single = self.config.get('proxy')
        if single and single.get('server'):
            return single

        # Pool of proxies (round-robin)
        proxies = self.config.get('proxy_list', [])
        if not proxies:
            return None
        idx = (worker_id - 1) % len(proxies)
        return proxies[idx]


# ── Import needed for worker delay ───────────────────────────────────────────
import random
