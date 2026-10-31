#!/usr/bin/env python
"""AC4 guard: scan a desktop bundle/directory for privileged credentials.

Scans every file under the given paths for known secret-material markers.
Exit 1 when any marker is found. Run it as a release step after bundling:
    python scripts/scan_bundle.py desktop/src-tauri/target/release
"""
from __future__ import annotations

import sys
from pathlib import Path

MARKERS = [
    b"sb_secret_",
    b"service_role",
    b"SUPABASE_SERVICE_ROLE",
    b"SERVICE_ROLE_KEY",
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
]

SKIP_SUFFIXES = {".pdb", ".ilk", ".lib", ".exp"}


def scan(paths: list[Path]) -> int:
    hits: list[str] = []
    for root in paths:
        if not root.exists():
            print(f"[scan] path does not exist, skipping: {root}")
            continue
        for file in root.rglob("*"):
            if not file.is_file() or file.suffix in SKIP_SUFFIXES:
                continue
            try:
                data = file.read_bytes()
            except OSError:
                continue
            for marker in MARKERS:
                if marker in data:
                    hits.append(f"{file}: {marker.decode(errors='replace')}")
    if hits:
        print("PRIVILEGED KEY MATERIAL FOUND:")
        for h in hits:
            print(f"  {h}")
        return 1
    print("[scan] clean: no privileged key material found")
    return 0


if __name__ == "__main__":
    args = [Path(p) for p in sys.argv[1:]] or [Path("desktop/src-tauri/target/release")]
    raise SystemExit(scan(args))
