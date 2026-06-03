"""One-shot: set every profile's proxy.type='http' and proxy.port='1000' in D:\\NST Profiles\\profiles.json.

D: drive write quirks (per project memory):
  - single write() > 32 KB → Errno 22
  - os.fsync() → Errno 9
So we write in 16 KB chunks and skip fsync.
"""
import json
import os
import shutil
from datetime import datetime

SRC = r"D:\NST Profiles\profiles.json"
CHUNK = 16 * 1024  # 16 KB — safely under the 32 KB D: limit


def chunked_write(path: str, data: str) -> None:
    """Write text to a D: path in <=16KB chunks, no fsync."""
    b = data.encode("utf-8")
    with open(path, "wb") as f:
        for i in range(0, len(b), CHUNK):
            f.write(b[i : i + CHUNK])


def main():
    # 1. Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = SRC.replace(".json", f"_backup_{ts}.json")
    shutil.copy2(SRC, backup)
    print(f"[backup] {backup}")

    # 2. Load
    with open(SRC, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    if not isinstance(profiles, list):
        raise SystemExit(f"Expected a JSON array at top level, got {type(profiles).__name__}")

    # 3. Patch every profile's proxy block (skip profiles without a proxy host)
    changed = 0
    type_was = {"socks5": 0, "http": 0, "https": 0, "other": 0, "missing": 0}
    for p in profiles:
        proxy = p.get("proxy")
        if not isinstance(proxy, dict) or not proxy.get("host"):
            type_was["missing"] += 1
            continue
        t = proxy.get("type", "")
        if t in ("socks5", "http", "https"):
            type_was[t] += 1
        else:
            type_was["other"] += 1
        proxy["type"] = "http"
        proxy["port"] = "10000"
        changed += 1

    # 4. Serialize
    out = json.dumps(profiles, indent=2, ensure_ascii=False)
    size_kb = len(out.encode("utf-8")) / 1024
    print(f"[stats] profiles_total={len(profiles)} patched={changed} prev_types={type_was}")
    print(f"[stats] new_size={size_kb:.1f} KB chunks={(len(out) + CHUNK - 1) // CHUNK}")

    # 5. Atomic-ish write: temp + replace
    tmp = SRC + ".tmp"
    chunked_write(tmp, out)
    os.replace(tmp, SRC)
    print(f"[done] {SRC}")


if __name__ == "__main__":
    main()
