"""
Final cleanup: keep only the 4-domain profiles that have valid login
credentials AND a proxy. Patch the 2 NST profiles missing proxy from
xlsx data. Verify proxy uniqueness.
"""
import json, os, re, shutil, time, sys
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

PF = Path(os.environ['APPDATA']) / 'MailNexusPro' / 'profiles' / 'profiles.json'
TARGET = {'beccaobergefell.com', 'kiteesurf.com',
          'banglaminute.com', 'cozblog.com'}

# ── Manually-located proxies for the 2 NST-missing-proxy profiles ────────
MANUAL_PROXY = {
    'blandine.duval@cozblog.com':
        'socks5://437dee9f2a569a71ecf2__cr.fr__sessid-7ccd14fe0b81:9182e8e0f3678824@74.81.81.81:10000',
    'julien.gautier@beccaobergefell.com':
        'socks5://437dee9f2a569a71ecf2__cr.fr__sessid-927629e6df5b4e29:9182e8e0f3678824@74.81.81.81:10000',
}


def parse_url(s: str) -> dict:
    """Parse 'socks5://user:pass@host:port' into proxy dict."""
    m = re.match(r'^(socks5|http|https)://([^:]+):([^@]+)@([^:]+):(\d+)$', s.strip())
    if not m:
        raise ValueError(f'Cannot parse proxy URL: {s!r}')
    return {
        'protocol': m.group(1),
        'host':     m.group(4),
        'port':     m.group(5),
        'username': m.group(2),
        'password': m.group(3),
    }


# ── Load current state ───────────────────────────────────────────────────
d = json.loads(PF.read_text('utf-8'))
print(f'Current total profiles: {len(d)}')

# Backup
backup = PF.with_suffix(f'.json.bak.before_finalize.{int(time.time())}')
shutil.copy2(PF, backup)
print(f'Backup saved: {backup.name}')

# ── Filter: keep only 4-domain profiles that have a password ─────────────
keep = []
dropped_no_creds = 0
dropped_other = 0
for p in d:
    em = (p.get('email') or '').strip().lower()
    domain = em.split('@', 1)[-1] if '@' in em else ''
    if domain not in TARGET:
        dropped_other += 1
        continue
    if not (p.get('password') or '').strip():
        dropped_no_creds += 1
        continue
    keep.append(p)

print(f'Kept (domain + has password) : {len(keep)}')
print(f'Dropped (no creds)           : {dropped_no_creds}')
print(f'Dropped (other domain)       : {dropped_other}')

# ── Patch missing proxies ────────────────────────────────────────────────
patched = 0
for p in keep:
    em = (p.get('email') or '').strip().lower()
    has_proxy = bool((p.get('proxy') or {}).get('host'))
    if not has_proxy and em in MANUAL_PROXY:
        p['proxy'] = parse_url(MANUAL_PROXY[em])
        patched += 1
        print(f'  Patched proxy for {em}')
print(f'Proxies patched from xlsx: {patched}')

# ── Verify proxy uniqueness ──────────────────────────────────────────────
sigs = []
no_proxy = []
for p in keep:
    px = p.get('proxy') or {}
    if px and px.get('host'):
        sig = (f"{px.get('protocol','')}://{px.get('username','')}:{px.get('password','')}"
               f"@{px.get('host','')}:{px.get('port','')}")
        sigs.append(sig)
    else:
        no_proxy.append(p.get('email'))

c = Counter(sigs)
duplicates = {k: v for k, v in c.items() if v > 1}
print()
print(f'Profiles with proxy   : {len(sigs)}')
print(f'Unique proxies        : {len(c)}')
print(f'Profiles without proxy: {len(no_proxy)}')
if duplicates:
    print(f'DUPLICATE proxies (count {len(duplicates)}):')
    for s, n in list(duplicates.items())[:5]:
        print(f'  {n}x  {s[:80]}...')
else:
    print('All proxies UNIQUE')

if no_proxy:
    print(f'No-proxy profiles still: {no_proxy}')

# ── Group breakdown ──────────────────────────────────────────────────────
print()
print('Final group breakdown:')
groups = Counter((p.get('group') or 'default') for p in keep)
for g, n in groups.most_common():
    print(f'  "{g}": {n}')

print()
print('Domain breakdown:')
domains = Counter((p.get('email') or '').split('@', 1)[-1].lower() for p in keep)
for dom, n in domains.most_common():
    print(f'  {dom}: {n}')

# ── Write ────────────────────────────────────────────────────────────────
PF.write_text(json.dumps(keep, indent=2, default=str), 'utf-8')
print()
print(f'OK Wrote {len(keep)} profiles to {PF}')
print('Restart the app to see them in Profile Manager.')
