"""
shared/sms_service.py — Unified SMS verification service for Gmail creation.

Supports multiple SMS providers with a common interface:
- 5sim.net
- sms-activate.org
- smspva.com
- daisysms.com

Public API
----------
SMSService(provider, api_key)
    Create a service instance.

get_number(country, service='google') -> SMSOrder
    Buy a phone number for verification.

wait_for_code(order_id, timeout=120) -> str
    Wait for SMS code arrival.

cancel(order_id)
    Cancel/release an unused number.

get_balance() -> float
    Check account balance.
"""

from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import Optional

_LOG_PREFIX = '[SMS]'


class SMSProvider(Enum):
    FIVESIM = '5sim'
    SMSACTIVATE = 'smsactivate'
    SMSPVA = 'smspva'
    DAISYSMS = 'daisysms'


@dataclass
class SMSOrder:
    """Represents an active SMS order."""
    order_id: str
    phone_number: str
    provider: str
    country: str
    status: str = 'pending'
    code: str = ''


# ── Provider Configs ─────────────────────────────────────────────────────────

_PROVIDER_CONFIGS = {
    '5sim': {
        'base_url': 'https://5sim.net/v1',
        'service_name': 'google',
        # Top countries for Gmail (5sim codes from PVA Creator reference)
        'countries': {
            'russia': 0, 'india': 22, 'indonesia': 6, 'philippines': 4,
            'vietnam': 10, 'usa': 12, 'uk': 16, 'brazil': 73,
            'bangladesh': 60, 'pakistan': 66, 'nigeria': 19, 'kenya': 8,
            'mexico': 54, 'colombia': 33, 'egypt': 21, 'thailand': 52,
        },
    },
    'smsactivate': {
        'base_url': 'https://api.sms-activate.org/stubs/handler_api.php',
        'service_code': 'go',  # Gmail service code
        'countries': {
            'russia': 0, 'india': 22, 'indonesia': 6, 'philippines': 4,
            'vietnam': 10, 'usa': 12, 'uk': 16, 'brazil': 73,
            'bangladesh': 60, 'pakistan': 66, 'nigeria': 19, 'kenya': 8,
        },
    },
    'smspva': {
        'base_url': 'http://smspva.com/priemnik.php',
        'service_code': 'opt16',  # Gmail
        'countries': {
            'russia': 0, 'india': 48, 'indonesia': 16, 'philippines': 29,
            'vietnam': 36, 'usa': 35, 'uk': 34, 'brazil': 5,
            'bangladesh': 14, 'pakistan': 54, 'nigeria': 53, 'kenya': 18,
        },
    },
    'daisysms': {
        'base_url': 'https://daisysms.com/stubs/handler_api.php',
        'service_code': 'go',
        'countries': {
            'russia': 0, 'india': 22, 'indonesia': 6, 'usa': 12,
            'uk': 16, 'brazil': 73, 'philippines': 4, 'vietnam': 10,
        },
    },
}


class SMSService:
    """Unified SMS verification service."""

    def __init__(self, provider: str, api_key: str):
        """
        Args:
            provider: '5sim', 'smsactivate', 'smspva', or 'daisysms'
            api_key: API key for the provider
        """
        self.provider = provider.lower().replace('-', '')
        self.api_key = api_key
        self.config = _PROVIDER_CONFIGS.get(self.provider, {})

        if not self.config:
            raise ValueError(f'Unknown SMS provider: {provider}. '
                           f'Supported: {", ".join(_PROVIDER_CONFIGS.keys())}')

    def _request(self, url: str, method: str = 'GET',
                 headers: dict | None = None, data: bytes | None = None) -> dict | str:
        """Make HTTP request to provider API."""
        hdrs = {'User-Agent': 'NexusAnty/1.0'}
        if headers:
            hdrs.update(headers)

        req = urllib.request.Request(url, headers=hdrs, method=method, data=data)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode('utf-8')
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return body
        except Exception as e:
            print(f'{_LOG_PREFIX} API error ({self.provider}): {e}')
            raise

    # ── Balance ──────────────────────────────────────────────────────────

    def get_balance(self) -> float:
        """Check account balance. Returns balance as float."""
        try:
            if self.provider == '5sim':
                url = f'{self.config["base_url"]}/user/profile'
                data = self._request(url, headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Accept': 'application/json',
                })
                return float(data.get('balance', 0))

            elif self.provider in ('smsactivate', 'daisysms'):
                url = (f'{self.config["base_url"]}'
                       f'?api_key={self.api_key}&action=getBalance')
                data = self._request(url)
                if isinstance(data, str) and ':' in data:
                    return float(data.split(':')[1])
                return 0.0

            elif self.provider == 'smspva':
                url = (f'{self.config["base_url"]}'
                       f'?metession={self.api_key}&method=get_balance')
                data = self._request(url)
                return float(data.get('balance', 0))

        except Exception as e:
            print(f'{_LOG_PREFIX} Balance check failed: {e}')
            return -1.0

    # ── Get Number ───────────────────────────────────────────────────────

    def get_number(self, country: str = 'india') -> Optional[SMSOrder]:
        """Buy a phone number for Gmail verification.

        Args:
            country: Country name (lowercase) — see _PROVIDER_CONFIGS for mapping

        Returns:
            SMSOrder with phone number, or None on failure
        """
        country = country.lower()
        country_code = self.config.get('countries', {}).get(country)
        if country_code is None:
            # Try first available country
            countries = self.config.get('countries', {})
            if countries:
                country = list(countries.keys())[0]
                country_code = countries[country]
            else:
                print(f'{_LOG_PREFIX} No country codes for {self.provider}')
                return None

        try:
            if self.provider == '5sim':
                url = (f'{self.config["base_url"]}/user/buy/activation'
                       f'/{country}/any/{self.config["service_name"]}')
                data = self._request(url, headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Accept': 'application/json',
                })
                return SMSOrder(
                    order_id=str(data.get('id', '')),
                    phone_number=str(data.get('phone', '')),
                    provider=self.provider,
                    country=country,
                )

            elif self.provider in ('smsactivate', 'daisysms'):
                url = (f'{self.config["base_url"]}'
                       f'?api_key={self.api_key}&action=getNumber'
                       f'&service={self.config["service_code"]}'
                       f'&country={country_code}')
                data = self._request(url)
                if isinstance(data, str) and ':' in data:
                    parts = data.split(':')
                    return SMSOrder(
                        order_id=parts[1],
                        phone_number=parts[2],
                        provider=self.provider,
                        country=country,
                    )

            elif self.provider == 'smspva':
                url = (f'{self.config["base_url"]}'
                       f'?metession={self.api_key}'
                       f'&method=get_number'
                       f'&service={self.config["service_code"]}'
                       f'&country={country_code}')
                data = self._request(url)
                if data.get('response') == 1:
                    return SMSOrder(
                        order_id=str(data.get('id', '')),
                        phone_number=str(data.get('number', '')),
                        provider=self.provider,
                        country=country,
                    )

        except Exception as e:
            print(f'{_LOG_PREFIX} Get number failed ({self.provider}): {e}')

        return None

    # ── Wait for Code ────────────────────────────────────────────────────

    def wait_for_code(self, order_id: str, timeout: int = 120) -> str:
        """Poll for SMS verification code.

        Args:
            order_id: Order ID from get_number()
            timeout: Max wait time in seconds

        Returns:
            SMS code string, or '' if timeout/failed
        """
        start = time.time()
        poll_interval = 5  # seconds between polls

        while time.time() - start < timeout:
            try:
                code = self._check_code(order_id)
                if code:
                    print(f'{_LOG_PREFIX} Code received: {code}')
                    return code
            except Exception as e:
                print(f'{_LOG_PREFIX} Poll error: {e}')

            time.sleep(poll_interval)

        print(f'{_LOG_PREFIX} Timeout waiting for code (order {order_id})')
        return ''

    def _check_code(self, order_id: str) -> str:
        """Single poll attempt to check for SMS code."""
        if self.provider == '5sim':
            url = f'{self.config["base_url"]}/user/check/{order_id}'
            data = self._request(url, headers={
                'Authorization': f'Bearer {self.api_key}',
            })
            sms_list = data.get('sms', [])
            if sms_list:
                code = sms_list[0].get('code', '')
                return code

        elif self.provider in ('smsactivate', 'daisysms'):
            url = (f'{self.config["base_url"]}'
                   f'?api_key={self.api_key}&action=getStatus'
                   f'&id={order_id}')
            data = self._request(url)
            if isinstance(data, str) and data.startswith('STATUS_OK:'):
                return data.split(':')[1]

        elif self.provider == 'smspva':
            url = (f'{self.config["base_url"]}'
                   f'?metession={self.api_key}'
                   f'&method=get_sms'
                   f'&id={order_id}')
            data = self._request(url)
            if data.get('response') == 1:
                return str(data.get('sms', ''))

        return ''

    # ── Cancel Number ────────────────────────────────────────────────────

    def cancel(self, order_id: str) -> bool:
        """Cancel/release an unused phone number."""
        try:
            if self.provider == '5sim':
                url = f'{self.config["base_url"]}/user/cancel/{order_id}'
                self._request(url, headers={
                    'Authorization': f'Bearer {self.api_key}',
                })
                return True

            elif self.provider in ('smsactivate', 'daisysms'):
                url = (f'{self.config["base_url"]}'
                       f'?api_key={self.api_key}&action=setStatus'
                       f'&id={order_id}&status=8')  # 8 = cancel
                self._request(url)
                return True

            elif self.provider == 'smspva':
                # smspva auto-cancels after timeout
                return True

        except Exception as e:
            print(f'{_LOG_PREFIX} Cancel failed: {e}')
            return False
