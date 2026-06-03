"""
shared/geo_matcher.py — Auto-match proxy IP to timezone, locale, and language.

Uses ip-api.com (free, no key needed, 45 req/min) to resolve proxy IP
geolocation, then maps that to consistent browser identity parameters.

Public API
----------
get_geo_info(ip: str) -> GeoInfo
    Returns timezone, locale, language, country for a given IP.

match_profile_geo(profile: dict) -> dict
    Auto-fills timezone/locale in a profile based on its proxy IP.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, asdict
from functools import lru_cache
from threading import Lock

_LOG_PREFIX = '[GEO]'
_API_URL = 'http://ip-api.com/json/{ip}?fields=status,country,countryCode,timezone,query'
_RATE_LIMIT_DELAY = 1.5  # seconds between API calls (45/min limit)
_last_call_time = 0.0
_rate_lock = Lock()


# ── Timezone → Locale / Language mapping ─────────────────────────────────────

_TZ_LOCALE_MAP: dict[str, tuple[str, str]] = {
    # Americas
    'America/New_York':      ('en-US', 'en-US,en;q=0.9'),
    'America/Chicago':       ('en-US', 'en-US,en;q=0.9'),
    'America/Denver':        ('en-US', 'en-US,en;q=0.9'),
    'America/Los_Angeles':   ('en-US', 'en-US,en;q=0.9'),
    'America/Anchorage':     ('en-US', 'en-US,en;q=0.9'),
    'Pacific/Honolulu':      ('en-US', 'en-US,en;q=0.9'),
    'America/Toronto':       ('en-CA', 'en-CA,en;q=0.9,fr;q=0.8'),
    'America/Vancouver':     ('en-CA', 'en-CA,en;q=0.9'),
    'America/Sao_Paulo':     ('pt-BR', 'pt-BR,pt;q=0.9,en;q=0.8'),
    'America/Argentina/Buenos_Aires': ('es-AR', 'es-AR,es;q=0.9,en;q=0.8'),
    'America/Mexico_City':   ('es-MX', 'es-MX,es;q=0.9,en;q=0.8'),
    'America/Bogota':        ('es-CO', 'es-CO,es;q=0.9'),
    'America/Lima':          ('es-PE', 'es-PE,es;q=0.9'),
    'America/Santiago':      ('es-CL', 'es-CL,es;q=0.9'),
    # Europe
    'Europe/London':         ('en-GB', 'en-GB,en;q=0.9'),
    'Europe/Paris':          ('fr-FR', 'fr-FR,fr;q=0.9,en;q=0.8'),
    'Europe/Berlin':         ('de-DE', 'de-DE,de;q=0.9,en;q=0.8'),
    'Europe/Madrid':         ('es-ES', 'es-ES,es;q=0.9,en;q=0.8'),
    'Europe/Rome':           ('it-IT', 'it-IT,it;q=0.9,en;q=0.8'),
    'Europe/Amsterdam':      ('nl-NL', 'nl-NL,nl;q=0.9,en;q=0.8'),
    'Europe/Brussels':       ('fr-BE', 'fr-BE,fr;q=0.9,nl;q=0.8,en;q=0.7'),
    'Europe/Lisbon':         ('pt-PT', 'pt-PT,pt;q=0.9,en;q=0.8'),
    'Europe/Warsaw':         ('pl-PL', 'pl-PL,pl;q=0.9,en;q=0.8'),
    'Europe/Prague':         ('cs-CZ', 'cs-CZ,cs;q=0.9,en;q=0.8'),
    'Europe/Vienna':         ('de-AT', 'de-AT,de;q=0.9,en;q=0.8'),
    'Europe/Zurich':         ('de-CH', 'de-CH,de;q=0.9,fr;q=0.8,en;q=0.7'),
    'Europe/Stockholm':      ('sv-SE', 'sv-SE,sv;q=0.9,en;q=0.8'),
    'Europe/Oslo':           ('nb-NO', 'nb-NO,nb;q=0.9,en;q=0.8'),
    'Europe/Copenhagen':     ('da-DK', 'da-DK,da;q=0.9,en;q=0.8'),
    'Europe/Helsinki':       ('fi-FI', 'fi-FI,fi;q=0.9,en;q=0.8'),
    'Europe/Moscow':         ('ru-RU', 'ru-RU,ru;q=0.9,en;q=0.8'),
    'Europe/Kiev':           ('uk-UA', 'uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7'),
    'Europe/Bucharest':      ('ro-RO', 'ro-RO,ro;q=0.9,en;q=0.8'),
    'Europe/Athens':         ('el-GR', 'el-GR,el;q=0.9,en;q=0.8'),
    'Europe/Istanbul':       ('tr-TR', 'tr-TR,tr;q=0.9,en;q=0.8'),
    # Asia
    'Asia/Tokyo':            ('ja-JP', 'ja-JP,ja;q=0.9,en;q=0.8'),
    'Asia/Seoul':            ('ko-KR', 'ko-KR,ko;q=0.9,en;q=0.8'),
    'Asia/Shanghai':         ('zh-CN', 'zh-CN,zh;q=0.9,en;q=0.8'),
    'Asia/Hong_Kong':        ('zh-HK', 'zh-HK,zh;q=0.9,en;q=0.8'),
    'Asia/Taipei':           ('zh-TW', 'zh-TW,zh;q=0.9,en;q=0.8'),
    'Asia/Singapore':        ('en-SG', 'en-SG,en;q=0.9,zh;q=0.8'),
    'Asia/Kolkata':          ('hi-IN', 'hi-IN,hi;q=0.9,en;q=0.8'),
    'Asia/Karachi':          ('ur-PK', 'ur-PK,ur;q=0.9,en;q=0.8'),
    'Asia/Dhaka':            ('bn-BD', 'bn-BD,bn;q=0.9,en;q=0.8'),
    'Asia/Bangkok':          ('th-TH', 'th-TH,th;q=0.9,en;q=0.8'),
    'Asia/Jakarta':          ('id-ID', 'id-ID,id;q=0.9,en;q=0.8'),
    'Asia/Manila':           ('en-PH', 'en-PH,en;q=0.9,fil;q=0.8'),
    'Asia/Dubai':            ('ar-AE', 'ar-AE,ar;q=0.9,en;q=0.8'),
    'Asia/Riyadh':           ('ar-SA', 'ar-SA,ar;q=0.9,en;q=0.8'),
    'Asia/Tehran':           ('fa-IR', 'fa-IR,fa;q=0.9,en;q=0.8'),
    # Africa
    'Africa/Lagos':          ('en-NG', 'en-NG,en;q=0.9'),
    'Africa/Cairo':          ('ar-EG', 'ar-EG,ar;q=0.9,en;q=0.8'),
    'Africa/Johannesburg':   ('en-ZA', 'en-ZA,en;q=0.9'),
    'Africa/Nairobi':        ('en-KE', 'en-KE,en;q=0.9,sw;q=0.8'),
    'Africa/Casablanca':     ('fr-MA', 'fr-MA,fr;q=0.9,ar;q=0.8'),
    # Oceania
    'Australia/Sydney':      ('en-AU', 'en-AU,en;q=0.9'),
    'Australia/Melbourne':   ('en-AU', 'en-AU,en;q=0.9'),
    'Pacific/Auckland':      ('en-NZ', 'en-NZ,en;q=0.9'),
}

# Country code → default timezone (fallback when timezone not in map)
_COUNTRY_DEFAULT_TZ: dict[str, str] = {
    'US': 'America/New_York', 'CA': 'America/Toronto', 'GB': 'Europe/London',
    'FR': 'Europe/Paris', 'DE': 'Europe/Berlin', 'IN': 'Asia/Kolkata',
    'JP': 'Asia/Tokyo', 'BR': 'America/Sao_Paulo', 'AU': 'Australia/Sydney',
    'BD': 'Asia/Dhaka', 'PK': 'Asia/Karachi', 'RU': 'Europe/Moscow',
}


@dataclass
class GeoInfo:
    """Geolocation result for a proxy IP."""
    ip: str
    country: str
    country_code: str
    timezone: str
    locale: str           # e.g. 'en-US'
    accept_language: str   # e.g. 'en-US,en;q=0.9'

    def to_dict(self) -> dict:
        return asdict(self)


# ── IP Geolocation Lookup ────────────────────────────────────────────────────

@lru_cache(maxsize=512)
def get_geo_info(ip: str) -> GeoInfo | None:
    """Lookup geolocation for an IP address. Returns None on failure.

    Results are cached in-memory (LRU 512 entries) to avoid redundant API calls.
    Rate-limited to ~40 requests/minute (ip-api.com free tier).
    """
    global _last_call_time

    if not ip or ip in ('', '0.0.0.0', 'localhost', '127.0.0.1'):
        return None

    # Rate limiting
    with _rate_lock:
        elapsed = time.time() - _last_call_time
        if elapsed < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - elapsed)
        _last_call_time = time.time()

    try:
        url = _API_URL.format(ip=ip)
        req = urllib.request.Request(url, headers={'User-Agent': 'NexusAnty/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        if data.get('status') != 'success':
            print(f'{_LOG_PREFIX} Lookup failed for {ip}: {data.get("message", "unknown")}')
            return None

        tz = data.get('timezone', '')
        country_code = data.get('countryCode', '')

        # Resolve locale and accept-language from timezone
        if tz in _TZ_LOCALE_MAP:
            locale, accept_lang = _TZ_LOCALE_MAP[tz]
        else:
            # Fallback: use country code to find a default
            fallback_tz = _COUNTRY_DEFAULT_TZ.get(country_code)
            if fallback_tz and fallback_tz in _TZ_LOCALE_MAP:
                locale, accept_lang = _TZ_LOCALE_MAP[fallback_tz]
            else:
                locale, accept_lang = 'en-US', 'en-US,en;q=0.9'

        return GeoInfo(
            ip=ip,
            country=data.get('country', ''),
            country_code=country_code,
            timezone=tz,
            locale=locale,
            accept_language=accept_lang,
        )

    except Exception as e:
        print(f'{_LOG_PREFIX} Error looking up {ip}: {e}')
        return None


def extract_proxy_ip(proxy: dict | None) -> str | None:
    """Extract the host/IP from a profile proxy dict."""
    if not proxy:
        return None
    host = proxy.get('host', '') or proxy.get('server', '')
    if not host:
        return None
    # Strip protocol prefix if present
    for prefix in ('http://', 'https://', 'socks5://', 'socks4://'):
        if host.startswith(prefix):
            host = host[len(prefix):]
    # Strip port suffix
    if ':' in host:
        host = host.split(':')[0]
    return host or None


def match_profile_geo(profile: dict) -> dict:
    """Auto-fill geo fields (timezone, locale, accept_language) in a profile
    based on its proxy IP. Returns the profile dict (modified in-place).

    Safe to call on profiles without proxy — returns unchanged.
    """
    proxy_ip = extract_proxy_ip(profile.get('proxy'))
    if not proxy_ip:
        return profile

    geo = get_geo_info(proxy_ip)
    if not geo:
        return profile

    # Store geo info in profile's overview section
    overview = profile.get('overview', {})
    overview['timezone'] = geo.timezone
    overview['locale'] = geo.locale
    overview['accept_language'] = geo.accept_language
    overview['geo_country'] = geo.country
    overview['geo_country_code'] = geo.country_code
    profile['overview'] = overview

    print(f'{_LOG_PREFIX} Matched {proxy_ip} → {geo.timezone} / {geo.locale}')
    return profile
