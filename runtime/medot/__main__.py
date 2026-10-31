"""Runtime lifecycle entrypoint (AC5):  python -m medot

Started by the Tauri shell as a sidecar. Prints the launch token on stdout
(JSON line) so the console can authenticate; binds to 127.0.0.1 only; handles
SIGTERM/CTRL_BREAK with a clean shutdown. Closing the desktop window does NOT
terminate this process — the shell hides the window; "Quit Medot" kills the
sidecar, which lands here.
"""
from __future__ import annotations

import json
import signal
import sys

import uvicorn

from .api.server import app, generate_launch_token, set_launch_token
from .config import get_settings
from .localstore import paths


def main() -> int:
    settings = get_settings()
    paths.ensure_layout()

    token = generate_launch_token()
    set_launch_token(token)
    # Single JSON line on stdout: the machine-readable handshake for the shell.
    print(json.dumps({
        "event": "runtime_ready",
        "host": settings.api_host,
        "port": settings.api_port,
        "launch_token": token,
        "pid": 0,
    }), flush=True)

    server = uvicorn.Server(uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="warning",
        access_log=False,
    ))

    def _shutdown(signum, _frame):
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _shutdown)
        except (ValueError, OSError):
            pass
    if sys.platform == "win32":
        try:
            signal.signal(signal.SIGBREAK, _shutdown)
        except (ValueError, OSError):
            pass

    server.run()
    print(json.dumps({"event": "runtime_stopped"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
