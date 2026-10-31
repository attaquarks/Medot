"""Local filesystem layout (docs/medot/07 §5).

Everything the runtime keeps on disk lives under one workspace root. No
secrets ever land here — secrets go to the OS keystore (localstore.keystore).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def workspace_root(override: str | None = None) -> Path:
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / "Medot"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Medot"
    return Path.home() / ".local" / "share" / "medot"


def ensure_layout(root: Path | None = None) -> dict[str, Path]:
    root = root or workspace_root()
    dirs = {
        "workspace": root / "workspace",
        "documents": root / "workspace" / "documents",
        "identities": root / "workspace" / "identities",
        "downloads": root / "workspace" / "downloads",
        "browser_profiles": root / "workspace" / "browser",
        "state": root / "state",
        "checkpoints": root / "state" / "checkpoints",
        "logs": root / "state" / "logs",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs
