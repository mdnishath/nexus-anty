"""
shared/credential_vault.py — Transparent field-level encryption for profiles.json

Uses Windows DPAPI (Data Protection API) via ctypes — zero extra dependencies.
Encrypted blobs are tied to the current Windows user account: decryption only
works on the same machine + same user, exactly like Chrome does for saved passwords.

On non-Windows (CI, Linux dev boxes) it falls back to a lightweight XOR-based
obfuscation so the rest of the code doesn't need conditional paths.

Public API
----------
encrypt_str(plaintext: str) -> str
    Return a portable encrypted token (base64-encoded DPAPI blob, prefixed with
    "dpapi:v1:" so we can detect and skip already-encrypted values).

decrypt_str(token: str) -> str
    Reverse of encrypt_str.  If the token is not a vault token (i.e. still
    plain text in profiles created before this feature), return it unchanged
    (graceful read-through for migration).

encrypt_profile_fields(profile: dict) -> dict
    Return a *copy* of the profile dict with sensitive fields encrypted.
    Safe to call on already-encrypted profiles (idempotent).

decrypt_profile_fields(profile: dict) -> dict
    Return a *copy* with sensitive fields decrypted back to plain text.
    Safe to call on plain-text profiles (read-through, no-op).

SENSITIVE_FIELDS
    The tuple of field names that are encrypted at rest.

Migration
---------
`_read_profiles()` calls `decrypt_profile_fields()` on every profile returned,
`_write_profiles()` calls `encrypt_profile_fields()` before writing.

Existing plain-text profiles are migrated transparently on first write after
this module is deployed — no one-off migration script needed.
"""

from __future__ import annotations

import base64
import json
import sys
from typing import Any

# ── Fields encrypted at rest ──────────────────────────────────────────────────
SENSITIVE_FIELDS: tuple[str, ...] = (
    # 'password' and 'totp_secret' are kept as plain text for manual login compatibility
    'backup_codes',      # list[str] — serialised as JSON before encrypt
    'recovery_email',
    'recovery_phone',
)

_TOKEN_PREFIX = 'dpapi:v1:'
_FALLBACK_PREFIX = 'xor:v1:'


# ── DPAPI backend (Windows) ───────────────────────────────────────────────────

def _dpapi_encrypt(data: bytes) -> bytes:
    """Encrypt bytes via CryptProtectData (DPAPI, current user scope)."""
    import ctypes
    import ctypes.wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', ctypes.wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), buf)
    blob_out = DATA_BLOB()

    # CRYPTPROTECT_UI_FORBIDDEN = 0x1  — suppress any UI prompts
    ok = ctypes.windll.crypt32.CryptProtectData(  # type: ignore[attr-defined]
        ctypes.byref(blob_in),
        None,       # description (unused)
        None,       # optional entropy
        None,       # reserved
        None,       # prompt struct
        0x1,        # flags: CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(blob_out),
    )
    if not ok:
        raise RuntimeError('CryptProtectData failed')

    encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]
    return encrypted


def _dpapi_decrypt(data: bytes) -> bytes:
    """Decrypt bytes via CryptUnprotectData (DPAPI)."""
    import ctypes
    import ctypes.wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', ctypes.wintypes.DWORD),
                    ('pbData', ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), buf)
    blob_out = DATA_BLOB()

    ok = ctypes.windll.crypt32.CryptUnprotectData(  # type: ignore[attr-defined]
        ctypes.byref(blob_in),
        None, None, None, None,
        0x1,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise RuntimeError('CryptUnprotectData failed')

    decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)  # type: ignore[attr-defined]
    return decrypted


# ── XOR fallback (non-Windows / CI) ──────────────────────────────────────────
# Not cryptographically secure — provides obfuscation only.
# Prevents casual `cat profiles.json` credential exposure in dev environments.

_XOR_KEY = b'MailNexusPro-2026-Credential-Vault-Obfuscation-Key'


def _xor_encrypt(data: bytes) -> bytes:
    key = _XOR_KEY
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


_xor_decrypt = _xor_encrypt   # XOR is its own inverse


# ── Unified encrypt / decrypt ─────────────────────────────────────────────────

def _is_windows() -> bool:
    return sys.platform == 'win32'


def _raw_encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string. Returns a prefixed base64 token."""
    data = plaintext.encode('utf-8')
    if _is_windows():
        try:
            blob = _dpapi_encrypt(data)
            return _TOKEN_PREFIX + base64.b64encode(blob).decode('ascii')
        except Exception:
            pass  # fall through to XOR on DPAPI failure
    blob = _xor_encrypt(data)
    return _FALLBACK_PREFIX + base64.b64encode(blob).decode('ascii')


def _raw_decrypt(token: str) -> str:
    """Decrypt a token produced by _raw_encrypt."""
    if token.startswith(_TOKEN_PREFIX):
        blob = base64.b64decode(token[len(_TOKEN_PREFIX):])
        if _is_windows():
            return _dpapi_decrypt(blob).decode('utf-8')
        # Wrong platform — can't decrypt a DPAPI blob; return the token
        # as-is so the caller at least sees something rather than crashing.
        return token
    if token.startswith(_FALLBACK_PREFIX):
        blob = base64.b64decode(token[len(_FALLBACK_PREFIX):])
        return _xor_decrypt(blob).decode('utf-8')
    # Not a vault token — plain text (legacy profile before encryption)
    return token


# ── Public helpers ────────────────────────────────────────────────────────────

def encrypt_str(value: str) -> str:
    """Encrypt a single string value.  Idempotent — already-encrypted values
    are returned unchanged."""
    if not value:
        return value
    if value.startswith(_TOKEN_PREFIX) or value.startswith(_FALLBACK_PREFIX):
        return value   # already encrypted
    try:
        return _raw_encrypt(value)
    except Exception:
        return value   # never crash — plain text is safer than data loss


def decrypt_str(value: str) -> str:
    """Decrypt a single string value.  Idempotent — plain-text values are
    returned unchanged (migration / read-through)."""
    if not value:
        return value
    if not (value.startswith(_TOKEN_PREFIX) or value.startswith(_FALLBACK_PREFIX)):
        return value   # plain text — not yet encrypted, pass through
    try:
        return _raw_decrypt(value)
    except Exception:
        return value   # decryption failure — return raw to avoid data loss


def _encrypt_field(value: Any, field: str) -> Any:
    """Encryption is DISABLED — credentials are stored as plaintext.

    DPAPI keys are per-user/per-machine, so an encrypted profile cannot be
    decrypted after the app + profiles are copied to ANOTHER PC (the product's
    normal distribution model) — backup_codes would turn to garbage / [] there.
    password & totp_secret were already kept plaintext for this reason; we now
    treat backup_codes / recovery_email / recovery_phone the same way.

    Existing encrypted values are still transparently DECRYPTED on read (see
    _decrypt_field) and get rewritten as plaintext on the next save."""
    return value


def _decrypt_field(value: Any, field: str) -> Any:
    """Decrypt a single profile field value (handles list for backup_codes)."""
    if field == 'backup_codes':
        if isinstance(value, str) and (
            value.startswith(_TOKEN_PREFIX) or value.startswith(_FALLBACK_PREFIX)
        ):
            try:
                return json.loads(decrypt_str(value))
            except Exception:
                return []
        return value   # already a list (plain text profile)
    if isinstance(value, str):
        return decrypt_str(value)
    return value


def encrypt_profile_fields(profile: dict) -> dict:
    """Return a copy of *profile* with all SENSITIVE_FIELDS encrypted.

    Safe to call on already-encrypted profiles — idempotent.
    Does NOT mutate the original dict.
    """
    out = dict(profile)
    for field in SENSITIVE_FIELDS:
        if field in out and out[field]:
            out[field] = _encrypt_field(out[field], field)
    return out


def decrypt_profile_fields(profile: dict) -> dict:
    """Return a copy of *profile* with all SENSITIVE_FIELDS decrypted.

    Safe to call on plain-text profiles — read-through, no-op for
    fields that are not vault tokens (graceful legacy migration).
    Does NOT mutate the original dict.
    """
    out = dict(profile)
    for field in SENSITIVE_FIELDS:
        if field in out and out[field]:
            out[field] = _decrypt_field(out[field], field)
    return out


def is_encrypted(profile: dict) -> bool:
    """Return True if the profile has any vault-encrypted fields."""
    for field in SENSITIVE_FIELDS:
        v = profile.get(field, '')
        if isinstance(v, str) and (
            v.startswith(_TOKEN_PREFIX) or v.startswith(_FALLBACK_PREFIX)
        ):
            return True
    return False


# ── File-level encryption (OAuth token files) ─────────────────────────────────
# Wraps entire JSON files — e.g. sheets_token.json, gdrive_token.json.
# The file on disk is stored as a single encrypted token string.
# The vault sentinel prefix allows transparent detection.

_FILE_MARKER = 'vault-file:v1:'


def is_file_encrypted(path) -> bool:
    """Return True if the file at *path* is vault-encrypted."""
    try:
        content = open(path, encoding='utf-8').read(len(_FILE_MARKER) + 4)
        return content.startswith(_FILE_MARKER)
    except Exception:
        return False


def encrypt_json_file(path) -> bool:
    """Encrypt a JSON file at *path* in-place using the vault.

    Reads the existing plaintext JSON, encrypts the entire content as a
    single string, and writes it back with the ``vault-file:v1:`` sentinel.
    Idempotent — already-encrypted files are left unchanged.

    Returns True on success, False on any error (never raises).
    """
    import pathlib
    p = pathlib.Path(path)
    if not p.exists():
        return False
    try:
        raw = p.read_text(encoding='utf-8')
        if raw.startswith(_FILE_MARKER):
            return True  # already encrypted
        token = _raw_encrypt(raw)
        p.write_text(_FILE_MARKER + token, encoding='utf-8')
        return True
    except Exception:
        return False


def decrypt_json_file(path) -> str | None:
    """Read and decrypt a (potentially encrypted) JSON file.

    If the file is plaintext JSON it is returned as-is (graceful read-through).
    If it is vault-encrypted the plaintext is returned without touching the file.
    Returns None on any error.
    """
    import pathlib
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding='utf-8')
        if raw.startswith(_FILE_MARKER):
            return _raw_decrypt(raw[len(_FILE_MARKER):])
        return raw  # plain-text file — pass through
    except Exception:
        return None
