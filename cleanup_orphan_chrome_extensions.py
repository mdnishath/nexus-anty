"""Remove orphan Chrome external-extension registry entries left behind by
Google Drive desktop (or similar) after uninstall.

Windows-only. Run as Administrator to clean HKLM entries.
"""
from __future__ import annotations

import sys
import os
import ctypes
import winreg
from pathlib import Path


# Extension IDs we want gone — the same ones nexus_profile_manager blocks.
BLOCKED_IDS = [
    'lmjegmlicamnimmfhcmpkclmigmmcbeh',  # Application Launcher for Drive
    'apdfllckaahabafndbhieahigkjlhalf',  # Google Drive web app
    'ghbmnnjooekpmoecnnnilnnbdlolhkhi',  # Google Docs Offline
    'nmmhkkegccagdldgiimedpiccmgmieda',  # Google Wallet / Pay
    'pkedcjkdefgpdelpbcmbmeomcjbeemfm',  # Chrome Cast
]

# Registry hives × subkey prefixes Chromium scans for external extensions.
# Both Google\Chrome and Chromium are checked because nstchrome (a Chromium
# fork) inherits Chrome's external-extension logic and may read either.
REG_TARGETS = [
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\Extensions"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Google\Chrome\Extensions"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Chromium\Extensions"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Chromium\Extensions"),
    (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\Extensions"),
    (winreg.HKEY_CURRENT_USER, r"Software\Chromium\Extensions"),
]


def _hive_name(h):
    return {winreg.HKEY_LOCAL_MACHINE: 'HKLM', winreg.HKEY_CURRENT_USER: 'HKCU'}.get(h, str(h))


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def delete_registry_extensions() -> tuple[int, int]:
    """Returns (deleted_count, skipped_for_perms)."""
    deleted = 0
    skipped = 0
    for hive, base in REG_TARGETS:
        try:
            # KEY_WOW64_64KEY ensures we hit the real 64-bit view when needed.
            with winreg.OpenKey(hive, base, 0, winreg.KEY_READ) as base_key:
                pass
        except FileNotFoundError:
            continue
        except PermissionError:
            print(f"  [skip] {_hive_name(hive)}\\{base} — permission denied (need admin?)")
            skipped += 1
            continue

        for ext_id in BLOCKED_IDS:
            sub = f"{base}\\{ext_id}"
            try:
                with winreg.OpenKey(hive, sub, 0, winreg.KEY_READ):
                    pass
            except FileNotFoundError:
                continue
            except PermissionError:
                skipped += 1
                print(f"  [skip] {_hive_name(hive)}\\{sub} — permission denied")
                continue

            try:
                winreg.DeleteKey(hive, sub)
                print(f"  [del]  {_hive_name(hive)}\\{sub}")
                deleted += 1
            except PermissionError:
                skipped += 1
                print(f"  [skip] {_hive_name(hive)}\\{sub} — permission denied (need admin?)")
            except OSError as e:
                # Has subkeys? Recursively delete.
                try:
                    _delete_tree(hive, sub)
                    print(f"  [del]  {_hive_name(hive)}\\{sub} (recursive)")
                    deleted += 1
                except Exception as e2:
                    print(f"  [err]  {_hive_name(hive)}\\{sub} — {e2}")
    return deleted, skipped


def _delete_tree(hive, subkey: str):
    """Recursively delete a registry key + all its children."""
    try:
        with winreg.OpenKey(hive, subkey, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    child = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(hive, subkey + '\\' + child)
    except FileNotFoundError:
        return
    winreg.DeleteKey(hive, subkey)


def cleanup_external_extension_files() -> int:
    """Delete leftover *.json files for the blocked extensions inside Chrome's
    install-time 'External Extensions' directories on disk."""
    candidates = []
    pf = os.environ.get('ProgramFiles', r'C:\Program Files')
    pf86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
    lad = os.environ.get('LOCALAPPDATA', '')
    for root in [pf, pf86]:
        candidates.append(Path(root) / 'Google' / 'Chrome' / 'Application')
    if lad:
        candidates.append(Path(lad) / 'Google' / 'Chrome' / 'User Data' / 'External Extensions')

    removed = 0
    for c in candidates:
        if not c.exists():
            continue
        # Recursively find <ext_id>.json files
        for ext_id in BLOCKED_IDS:
            for path in c.rglob(f'{ext_id}.json'):
                try:
                    path.unlink()
                    print(f"  [del]  {path}")
                    removed += 1
                except Exception as e:
                    print(f"  [err]  {path} — {e}")
    return removed


def main():
    if os.name != 'nt':
        print("Windows-only. Skipping.")
        return

    print(f"Admin: {'yes' if is_admin() else 'NO (HKLM entries may be skipped — re-run elevated)'}")
    print()
    print("Scanning registry for orphan Chrome external-extension entries...")
    d, s = delete_registry_extensions()
    print(f"  -> {d} deleted, {s} skipped")
    print()
    print("Scanning Chrome install dirs for leftover .json descriptors...")
    f = cleanup_external_extension_files()
    print(f"  -> {f} file(s) deleted")
    print()
    if s > 0 and not is_admin():
        print("Some entries were skipped due to permissions.")
        print("Right-click this script -> Run as administrator to fully clean.")
    elif d == 0 and f == 0:
        print("Nothing to clean — registry is already free of these extension entries.")
    else:
        print("Cleanup done. Restart any open browsers / profiles.")


if __name__ == '__main__':
    main()
