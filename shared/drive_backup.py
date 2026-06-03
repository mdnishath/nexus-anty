"""
shared/drive_backup.py — Profile registry backup/restore via Google Drive.

Backs up profiles.json (the local registry that holds emails, passwords,
TOTP secrets, proxies, and group assignments) to a dedicated folder on
the user's Google Drive. Restore pulls a chosen backup back down,
making a local safety-copy of the current state before overwriting.

Public API:
    backup_now(resources_path) -> dict
        {success, file_id, file_name, size, count, profiles_count}
    list_backups(resources_path) -> list[dict]
        [{id, name, created, size, profiles_count}, ...]
    restore(resources_path, file_id) -> dict
        {success, restored_count, local_backup}

The Drive folder is configured in config/gdrive.json (folder_id field).
We create a sub-folder named "ProfilesJsonBackups" inside it on first
use. Each backup file is named:
    profiles_backup_YYYYMMDD_HHMMSS_NNNprofiles.json
"""

from __future__ import annotations

import io
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/drive.file']
SUBFOLDER_NAME = 'ProfilesJsonBackups'


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _profiles_path() -> Path:
    """Resolve the active profiles.json location.

    Delegates to nexus_profile_manager._profiles_file() which respects the user's
    custom storage_path config (e.g. D:\\NST Profiles\\profiles.json). Falls back
    to APPDATA only if that import fails — historically the reason backups
    silently uploaded the wrong (mostly-empty) AppData copy.
    """
    try:
        from shared.nexus_profile_manager import _profiles_file
        return _profiles_file()
    except Exception:
        if os.name == 'nt':
            appdata = os.environ.get('APPDATA', '')
            if appdata:
                return Path(appdata) / 'MailNexusPro' / 'profiles' / 'profiles.json'
        return Path.cwd() / 'profiles.json'


def _local_backup_dir() -> Path:
    """Directory where we keep local copies of each Drive backup.

    Sits alongside profiles.json so it's on the same drive the user picked
    (typically D: for large profile stores). Created on demand.
    """
    p = _profiles_path().parent / 'LocalBackups'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_local_copy(body: str, filename: str, keep: int = 30) -> tuple[Path | None, str]:
    """Write `body` to <local_backup_dir>/<filename>. Returns (path, error).

    Also prunes the directory to the most recent `keep` backups so we don't
    silently fill the disk. D: drive constraint: single write must be <=32KB,
    so we chunk if needed (per project MEMORY.md).
    """
    try:
        outdir = _local_backup_dir()
        out = outdir / filename
        data = body.encode('utf-8')
        CHUNK = 16 * 1024  # under D:'s 32KB single-write cap
        with open(out, 'wb') as f:
            for i in range(0, len(data), CHUNK):
                f.write(data[i:i + CHUNK])

        # Rotate — keep newest `keep` profiles_backup_*.json files
        existing = sorted(
            (p for p in outdir.glob('profiles_backup_*.json') if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in existing[keep:]:
            try:
                old.unlink()
            except Exception:
                pass
        return out, ''
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'


def _gdrive_config_path(resources_path) -> Path:
    return Path(resources_path) / 'config' / 'gdrive.json'


def _load_gdrive_config(resources_path) -> dict:
    p = _gdrive_config_path(resources_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_gdrive_config(resources_path, cfg: dict):
    p = _gdrive_config_path(resources_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding='utf-8')


def _build_service(resources_path):
    """Build a Drive v3 client. Returns (service, error_msg)."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except Exception as e:
        return None, f'Google API libraries not installed: {e}'

    token_path = Path(resources_path) / 'config' / 'gdrive_token.json'
    if not token_path.exists():
        return None, ('Google Drive not authorized. Run '
                      '"python tools/gdrive_setup.py" once to authorize.')

    try:
        from shared.credential_vault import decrypt_json_file, encrypt_json_file, is_file_encrypted
        raw = decrypt_json_file(str(token_path))
        if not raw:
            raise ValueError("Token file empty or decryption failed")
        info = json.loads(raw)
        creds = Credentials.from_authorized_user_info(info, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding='utf-8')
            encrypt_json_file(str(token_path))
        elif not is_file_encrypted(str(token_path)):
            encrypt_json_file(str(token_path))
        return build('drive', 'v3', credentials=creds, cache_discovery=False), None
    except Exception as e:
        return None, f'Drive auth failed: {e}'


def _ensure_root_folder(service, resources_path) -> str:
    """Find or auto-create 'MailNexusPro Backups' in Drive root.
    Saves the folder_id to gdrive.json for future calls. Returns folder_id or ''."""
    cfg = _load_gdrive_config(resources_path)
    folder_id = (cfg.get('folder_id') or '').strip()
    if folder_id:
        return folder_id
    ROOT_FOLDER = 'MailNexusPro Backups'
    try:
        q = (f"name='{ROOT_FOLDER}' and "
             f"mimeType='application/vnd.google-apps.folder' and "
             f"'root' in parents and trashed=false")
        res = service.files().list(q=q, fields='files(id)', pageSize=5).execute()
        files = res.get('files') or []
        if files:
            fid = files[0]['id']
        else:
            meta = {'name': ROOT_FOLDER, 'mimeType': 'application/vnd.google-apps.folder'}
            new = service.files().create(body=meta, fields='id').execute()
            fid = new['id']
        cfg['folder_id'] = fid
        _save_gdrive_config(resources_path, cfg)
        return fid
    except Exception:
        return ''


def _ensure_subfolder(service, parent_id: str) -> str | None:
    """Find or create the ProfilesJsonBackups sub-folder. Returns its ID."""
    try:
        q = (f"name = '{SUBFOLDER_NAME}' and "
             f"mimeType = 'application/vnd.google-apps.folder' and "
             f"'{parent_id}' in parents and trashed = false")
        res = service.files().list(
            q=q, fields='files(id, name)', pageSize=10
        ).execute()
        items = res.get('files') or []
        if items:
            return items[0]['id']
        # Create
        meta = {
            'name': SUBFOLDER_NAME,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id],
        }
        new = service.files().create(body=meta, fields='id').execute()
        return new['id']
    except Exception as e:
        return None


def _profile_count(json_text: str) -> int:
    try:
        return len(json.loads(json_text))
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def status(resources_path) -> dict:
    """Quick check: is Drive auth working?"""
    cfg = _load_gdrive_config(resources_path)
    folder_id = cfg.get('folder_id', '').strip()
    has_token = (Path(resources_path) / 'config' / 'gdrive_token.json').exists()
    return {
        'configured': bool(folder_id) and has_token,
        'folder_id': folder_id,
        'has_token': has_token,
        'auto_backup': bool(cfg.get('auto_backup_profiles', False)),
        'auto_backup_interval_hours': cfg.get('auto_backup_interval_hours', 24),
    }


def backup_now(resources_path) -> dict:
    """Upload the current profiles.json to Google Drive AND save a local copy.

    The local copy is the safety net: even if Drive auth breaks or the upload
    is interrupted, the user still has an on-disk backup. Both copies share
    the same filename so they're easy to cross-reference.
    """
    pf = _profiles_path()
    if not pf.exists():
        return {'success': False, 'message': f'profiles.json not found at {pf}'}

    body = pf.read_text(encoding='utf-8')
    if len(body) <= 2:
        return {'success': False, 'message': 'profiles.json is empty — nothing to back up'}

    count = _profile_count(body)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'profiles_backup_{ts}_{count}profiles.json'

    # Step 1 — local copy first. Cheap, always succeeds when disk has space,
    # and gives us a fallback if Drive upload throws.
    local_path, local_err = _save_local_copy(body, filename)
    local_info = {
        'local_saved': bool(local_path),
        'local_path': str(local_path) if local_path else '',
        'local_error': local_err,
    }

    # Step 2 — Drive upload.
    service, err = _build_service(resources_path)
    if not service:
        return {
            'success': bool(local_path),
            'message': (err or 'Drive auth failed') + (' (local copy saved)' if local_path else ''),
            'profiles_count': count,
            **local_info,
        }

    folder_id = _ensure_root_folder(service, resources_path)
    if not folder_id:
        return {
            'success': bool(local_path),
            'message': 'Could not create/find backup folder in Drive' + (' (local copy saved)' if local_path else ''),
            'profiles_count': count,
            **local_info,
        }

    sub_id = _ensure_subfolder(service, folder_id)
    if not sub_id:
        return {
            'success': bool(local_path),
            'message': 'Could not create/find backup sub-folder' + (' (local copy saved)' if local_path else ''),
            'profiles_count': count,
            **local_info,
        }

    try:
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(
            io.BytesIO(body.encode('utf-8')),
            mimetype='application/json',
            resumable=False,
        )
        meta = {'name': filename, 'parents': [sub_id]}
        result = service.files().create(
            body=meta, media_body=media,
            fields='id, name, size, createdTime',
        ).execute()
        return {
            'success': True,
            'file_id': result['id'],
            'file_name': result['name'],
            'size': int(result.get('size') or len(body)),
            'profiles_count': count,
            'created': result.get('createdTime'),
            **local_info,
        }
    except Exception as e:
        return {
            'success': bool(local_path),
            'message': f'Upload failed: {e}' + (' (local copy saved)' if local_path else ''),
            'profiles_count': count,
            **local_info,
        }


def list_backups(resources_path, limit: int = 50) -> dict:
    """List backup files in the Drive sub-folder, newest first."""
    service, err = _build_service(resources_path)
    if not service:
        return {'success': False, 'message': err, 'backups': []}

    folder_id = _ensure_root_folder(service, resources_path)
    if not folder_id:
        return {'success': True, 'backups': []}

    sub_id = _ensure_subfolder(service, folder_id)
    if not sub_id:
        return {'success': True, 'backups': []}

    try:
        q = (f"'{sub_id}' in parents and "
             f"name contains 'profiles_backup_' and "
             f"trashed = false")
        res = service.files().list(
            q=q,
            orderBy='createdTime desc',
            pageSize=limit,
            fields='files(id, name, size, createdTime)',
        ).execute()
        files = res.get('files') or []
        out = []
        for f in files:
            # Try to extract profile count from filename
            count = None
            try:
                m = f['name'].rsplit('_', 1)[1]   # "203profiles.json"
                count = int(m.split('profiles')[0])
            except Exception:
                pass
            out.append({
                'id': f['id'],
                'name': f['name'],
                'size': int(f.get('size') or 0),
                'created': f.get('createdTime'),
                'profiles_count': count,
            })
        return {'success': True, 'backups': out}
    except Exception as e:
        return {'success': False, 'message': f'List failed: {e}', 'backups': []}


def restore(resources_path, file_id: str) -> dict:
    """Download a backup from Drive and replace profiles.json with it.
    Saves the current profiles.json as a local backup first."""
    if not file_id:
        return {'success': False, 'message': 'file_id is required'}

    service, err = _build_service(resources_path)
    if not service:
        return {'success': False, 'message': err}

    pf = _profiles_path()
    pf.parent.mkdir(parents=True, exist_ok=True)

    # Local safety backup of current profiles.json (if present)
    local_backup_name = ''
    if pf.exists() and pf.stat().st_size > 2:
        local_backup_name = (
            f'profiles.json.bak.before_drive_restore.{int(time.time())}'
        )
        try:
            shutil.copy2(pf, pf.with_name(local_backup_name))
        except Exception:
            pass

    # Download the file
    try:
        from googleapiclient.http import MediaIoBaseDownload
        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        body = buf.getvalue().decode('utf-8')
    except Exception as e:
        return {'success': False, 'message': f'Download failed: {e}'}

    # Validate JSON
    try:
        data = json.loads(body)
        if not isinstance(data, list):
            raise ValueError('expected JSON array')
    except Exception as e:
        return {'success': False, 'message': f'Backup file is not valid: {e}'}

    pf.write_text(body, encoding='utf-8')
    return {
        'success': True,
        'restored_count': len(data),
        'local_backup': local_backup_name,
        'profiles_path': str(pf),
    }


def reauthorize(resources_path, port: int = 8599) -> dict:
    """Run the OAuth2 desktop flow — opens system browser, waits for the
    user to log in + consent, writes a fresh token to gdrive_token.json.
    Blocks until the user completes the flow (or closes the browser).
    Used when the existing token is expired/revoked (`invalid_grant`)."""
    cred_path = Path(resources_path) / 'config' / 'gdrive_credentials.json'
    if not cred_path.exists():
        return {'success': False,
                'message': ('config/gdrive_credentials.json missing — '
                            'this OAuth client file ships separately.')}
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception as e:
        return {'success': False,
                'message': f'google-auth-oauthlib not available: {e}'}

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
        creds = flow.run_local_server(port=port, prompt='consent', open_browser=True)
        token_path = Path(resources_path) / 'config' / 'gdrive_token.json'
        token_path.write_text(creds.to_json(), encoding='utf-8')
        from shared.credential_vault import encrypt_json_file
        encrypt_json_file(str(token_path))
        return {'success': True, 'message': 'Drive re-authorized successfully'}
    except Exception as e:
        return {'success': False, 'message': f'Re-auth failed: {e}'}


def set_auto_backup(resources_path, enabled: bool, interval_hours: int = 24) -> dict:
    cfg = _load_gdrive_config(resources_path)
    cfg['auto_backup_profiles'] = bool(enabled)
    cfg['auto_backup_interval_hours'] = max(1, int(interval_hours))
    _save_gdrive_config(resources_path, cfg)
    return {
        'success': True,
        'auto_backup': cfg['auto_backup_profiles'],
        'auto_backup_interval_hours': cfg['auto_backup_interval_hours'],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Auto-backup background loop
# ─────────────────────────────────────────────────────────────────────────────

_auto_backup_thread = None
_auto_backup_stop = False


def start_auto_backup_loop(resources_path):
    """If auto-backup is enabled in gdrive.json, start a daemon thread that
    uploads profiles.json every N hours. Idempotent — safe to call once at
    server startup."""
    global _auto_backup_thread

    cfg = _load_gdrive_config(resources_path)
    if not cfg.get('auto_backup_profiles', False):
        return

    if _auto_backup_thread and _auto_backup_thread.is_alive():
        return  # already running

    import threading

    def _loop():
        while not _auto_backup_stop:
            try:
                interval = max(1, int(_load_gdrive_config(resources_path)
                                      .get('auto_backup_interval_hours', 24)))
            except Exception:
                interval = 24
            try:
                if _load_gdrive_config(resources_path).get('auto_backup_profiles', False):
                    backup_now(resources_path)
            except Exception:
                pass
            # Sleep in small chunks so stop signal is responsive
            for _ in range(interval * 60):
                if _auto_backup_stop:
                    return
                time.sleep(60)

    t = threading.Thread(target=_loop, daemon=True, name='profile-drive-auto-backup')
    t.start()
    _auto_backup_thread = t
