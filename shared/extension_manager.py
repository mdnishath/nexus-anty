"""
shared/extension_manager.py — Chrome Extension Manager

Manages Chrome extensions for all profiles:
  - Download CRX from Chrome Web Store URL
  - Install from uploaded ZIP / CRX
  - Apply to all profiles or specific ones
  - Load at browser launch via --load-extension flag

Extensions are stored unpacked in:
    {resources_path}/extensions/{ext_id}/

Config is saved in:
    {resources_path}/config/extensions.json

Public API:
    list_extensions(resources_path) -> list[dict]
    install_from_url(resources_path, url) -> dict
    install_from_bytes(resources_path, data, filename, name) -> dict
    remove_extension(resources_path, ext_id) -> dict
    update_extension(resources_path, ext_id, **fields) -> dict
    get_extension_paths_for_profile(resources_path, profile) -> list[str]
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path
from typing import Optional


EXTENSIONS_DIR = 'extensions'
CONFIG_FILE = 'config/extensions.json'


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ext_root(resources_path: str) -> Path:
    p = Path(resources_path) / EXTENSIONS_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _config_path(resources_path: str) -> Path:
    return Path(resources_path) / CONFIG_FILE


def _load_config(resources_path: str) -> list:
    p = _config_path(resources_path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return []


def _save_config(resources_path: str, cfg: list):
    p = _config_path(resources_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding='utf-8')


def _extract_ext_id(url: str) -> str:
    """Extract 32-char extension ID from a CWS URL or return as-is if already an ID."""
    m = re.search(r'/detail/[^/]+/([a-z]{32})', url)
    if m:
        return m.group(1)
    m2 = re.search(r'\b([a-z]{32})\b', url)
    return m2.group(1) if m2 else ''


def _crx_to_zip(data: bytes) -> bytes:
    """Strip CRX2 or CRX3 header and return raw ZIP bytes."""
    if data[:4] != b'Cr24':
        # Maybe already a raw ZIP
        if data[:2] == b'PK':
            return data
        raise ValueError('Not a CRX or ZIP file')
    version = struct.unpack_from('<I', data, 4)[0]
    if version == 2:
        pubkey_len = struct.unpack_from('<I', data, 8)[0]
        sig_len = struct.unpack_from('<I', data, 12)[0]
        return data[16 + pubkey_len + sig_len:]
    elif version == 3:
        header_size = struct.unpack_from('<I', data, 8)[0]
        return data[12 + header_size:]
    else:
        raise ValueError(f'Unknown CRX version {version}')


def _read_manifest(ext_path: Path) -> dict:
    try:
        return json.loads((ext_path / 'manifest.json').read_text(encoding='utf-8'))
    except Exception:
        return {}


def _manifest_name(manifest: dict, fallback: str) -> str:
    name = manifest.get('name', fallback)
    if name.startswith('__MSG_'):
        # Try to resolve from _locales/en/messages.json
        return fallback
    return name or fallback


def _register(resources_path: str, ext_id: str, name: str,
               ext_path: Path, source: str) -> dict:
    cfg = _load_config(resources_path)
    existing = next((e for e in cfg if e['id'] == ext_id), None)
    entry = {
        'id': ext_id,
        'name': name,
        'source': source,
        'path': str(ext_path),
        'apply_to_all': existing.get('apply_to_all', True) if existing else True,
        'pinned': existing.get('pinned', False) if existing else False,
    }
    if existing:
        cfg[cfg.index(existing)] = entry
    else:
        cfg.append(entry)
    _save_config(resources_path, cfg)
    return {'success': True, 'ext_id': ext_id, 'name': name, 'path': str(ext_path)}


def _unpack_zip(zip_bytes: bytes, dest: Path) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(str(dest))
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def list_extensions(resources_path: str) -> list:
    """Return list of installed extension dicts."""
    cfg = _load_config(resources_path)
    # Annotate with existence check
    out = []
    for e in cfg:
        e = dict(e)
        e['installed'] = Path(e.get('path', '')).exists()
        out.append(e)
    return out


def install_from_url(resources_path: str, url: str) -> dict:
    """Download a Chrome extension from a CWS URL or bare extension ID."""
    ext_id = _extract_ext_id(url)
    if not ext_id:
        return {'success': False, 'message': 'Could not extract extension ID from URL. '
                'Expected a Chrome Web Store URL or a 32-character extension ID.'}

    download_url = (
        'https://clients2.google.com/service/update2/crx'
        f'?response=redirect&prodversion=130.0.0.0&acceptformat=crx3'
        f'&x=id%3D{ext_id}%26installsource%3Dondemand%26uc'
    )
    try:
        import requests as _req
        r = _req.get(download_url, timeout=30, allow_redirects=True,
                     headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 Chrome/130.0.0.0'})
        r.raise_for_status()
        crx_data = r.content
    except Exception as e:
        return {'success': False, 'message': f'Download failed: {e}'}

    return _install_crx(resources_path, ext_id, crx_data, source=url)


def install_from_bytes(resources_path: str, data: bytes,
                       filename: str = '', name: str = '') -> dict:
    """Install an extension from raw bytes (ZIP or CRX upload)."""
    fname_lower = filename.lower()
    if fname_lower.endswith('.crx') or data[:4] == b'Cr24':
        try:
            zip_bytes = _crx_to_zip(data)
        except Exception as e:
            return {'success': False, 'message': f'CRX parse failed: {e}'}
        # Try to get ext_id from filename
        ext_id = re.sub(r'\.crx$', '', filename.lower())
        if not re.fullmatch(r'[a-z]{32}', ext_id):
            import hashlib
            ext_id = 'local_' + hashlib.sha256(data[:128]).hexdigest()[:16]
        return _install_crx_zip(resources_path, ext_id, zip_bytes, name or filename, source='upload')
    else:
        # Treat as ZIP
        try:
            zf = zipfile.ZipFile(io.BytesIO(data))
        except Exception as e:
            return {'success': False, 'message': f'Invalid ZIP: {e}'}
        try:
            manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        except Exception:
            manifest = {}
        ext_name = name or _manifest_name(manifest, filename or 'Unknown')
        import hashlib
        ext_id = 'local_' + hashlib.sha256(data[:128]).hexdigest()[:16]
        return _install_crx_zip(resources_path, ext_id, data, ext_name, source='upload')


def _install_crx(resources_path: str, ext_id: str, crx_data: bytes, source: str = '') -> dict:
    try:
        zip_bytes = _crx_to_zip(crx_data)
    except Exception as e:
        return {'success': False, 'message': f'CRX parse error: {e}'}
    return _install_crx_zip(resources_path, ext_id, zip_bytes, name=ext_id, source=source)


def _install_crx_zip(resources_path: str, ext_id: str, zip_bytes: bytes,
                     name: str, source: str) -> dict:
    ext_path = _ext_root(resources_path) / ext_id
    if ext_path.exists():
        shutil.rmtree(ext_path, ignore_errors=True)
    ext_path.mkdir(parents=True, exist_ok=True)

    if not _unpack_zip(zip_bytes, ext_path):
        return {'success': False, 'message': 'Failed to extract extension files'}

    manifest = _read_manifest(ext_path)
    ext_name = _manifest_name(manifest, name)
    return _register(resources_path, ext_id, ext_name, ext_path, source)


def remove_extension(resources_path: str, ext_id: str) -> dict:
    """Remove an installed extension from disk and config."""
    cfg = _load_config(resources_path)
    entry = next((e for e in cfg if e['id'] == ext_id), None)
    if not entry:
        return {'success': False, 'message': 'Extension not found'}
    ext_path = Path(entry.get('path', ''))
    if ext_path.exists():
        try:
            shutil.rmtree(ext_path)
        except Exception as e:
            return {'success': False, 'message': f'Could not remove files: {e}'}
    cfg.remove(entry)
    _save_config(resources_path, cfg)
    return {'success': True}


def update_extension(resources_path: str, ext_id: str,
                     apply_to_all: Optional[bool] = None,
                     pinned: Optional[bool] = None) -> dict:
    """Update apply_to_all or pinned flag for an extension."""
    cfg = _load_config(resources_path)
    entry = next((e for e in cfg if e['id'] == ext_id), None)
    if not entry:
        return {'success': False, 'message': 'Extension not found'}
    if apply_to_all is not None:
        entry['apply_to_all'] = bool(apply_to_all)
    if pinned is not None:
        entry['pinned'] = bool(pinned)
    _save_config(resources_path, cfg)
    return {'success': True}


def get_extension_paths_for_profile(resources_path: str, profile: dict) -> list[str]:
    """Return list of extension directory paths to load for this profile.

    Includes extensions marked apply_to_all=True plus any in profile['extension_ids'].
    """
    cfg = _load_config(resources_path)
    profile_ext_ids = set(profile.get('extension_ids') or [])
    paths: list[str] = []
    for ext in cfg:
        ext_path = ext.get('path', '')
        if not ext_path or not Path(ext_path).exists():
            continue
        if ext.get('apply_to_all', True) or ext['id'] in profile_ext_ids:
            paths.append(ext_path)
    return paths


def chrome_unpacked_id(absolute_path: str) -> str:
    """Compute the runtime extension ID Chrome assigns to an unpacked
    extension loaded via --load-extension=<path>.

    Mirrors Chromium's crx_file::id_util::GenerateIdForPath():
      1. MaybeNormalizePath: on Windows, upper-case the drive letter.
      2. Encode the path as UTF-16-LE on Windows, UTF-8 elsewhere.
      3. SHA-256 → take first 16 bytes → 32 hex chars.
      4. Map each hex digit (0-9,a-f) to letters a-p.
    """
    p = absolute_path
    if sys.platform == 'win32':
        if len(p) >= 2 and p[1] == ':' and 'a' <= p[0] <= 'z':
            p = p[0].upper() + p[1:]
        path_bytes = p.encode('utf-16-le')
    else:
        path_bytes = p.encode('utf-8')
    digest_hex = hashlib.sha256(path_bytes).hexdigest()[:32]
    return ''.join(chr(ord('a') + int(c, 16)) for c in digest_hex)


def get_pinned_extension_ids_for_profile(resources_path: str, profile: dict) -> list[str]:
    """Return Chrome runtime IDs (path-derived) for extensions that should
    be pinned in the toolbar for this profile.

    An extension is pinned only if BOTH conditions hold:
      - it is loaded for this profile (apply_to_all OR in profile.extension_ids)
      - its config has pinned=True
    """
    cfg = _load_config(resources_path)
    profile_ext_ids = set(profile.get('extension_ids') or [])
    ids: list[str] = []
    for ext in cfg:
        if not ext.get('pinned'):
            continue
        ext_path = ext.get('path', '')
        if not ext_path or not Path(ext_path).exists():
            continue
        if not (ext.get('apply_to_all', True) or ext['id'] in profile_ext_ids):
            continue
        try:
            # Pass the same path string Chrome receives via --load-extension=
            # (no resolve() — that may alter casing/UNC prefix).
            ids.append(chrome_unpacked_id(str(ext_path)))
        except Exception:
            continue
    return ids
