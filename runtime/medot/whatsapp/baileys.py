"""Baileys bridge (Route 2 — unofficial WhatsApp Web session): Python side.

The bridge is a Node 18+ process (`bridges/baileys/index.mjs`) that owns the
WhatsApp Web socket. This module spawns it, waits for its handshake line, and
speaks its loopback HTTP contract (token auth, long-poll updates) — the same
shape as the official Agent Platform path, so the transport manager treats
both uniformly.

UNOFFICIAL transport: small ban risk (WhatsApp Web emulation). A dedicated
number is recommended for bot mode; self-chat mode reads the user's own chat.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ..localstore import paths

BRIDGE_DIR_ENV = "MEDOT_BRIDGES_DIR"
MIN_NODE_MAJOR = 18
HANDSHAKE_RE = re.compile(r"^\{.*\"event\":\s*\"bridge_listening\".*\}$")


class BridgeError(RuntimeError):
    """Raised with a user-presentable message when the bridge can't run."""


@dataclass
class BridgeSettings:
    """User-chosen policy for the Baileys transport (persisted in user_settings)."""

    mode: str = "self"  # "self" (message yourself) | "bot" (dedicated number)
    allowed_users: list[str] = field(default_factory=list)  # phone numbers, country code, no +
    allow_all: bool = False
    group_policy: str = "pairing"  # "pairing" | "allowlist" | "open"
    group_allow: list[str] = field(default_factory=list)  # group JIDs 120363...@g.us
    require_mention: bool = False

    def validate(self) -> None:
        if self.mode not in ("self", "bot"):
            raise ValueError("mode must be 'self' or 'bot'")
        if self.group_policy not in ("pairing", "allowlist", "open"):
            raise ValueError("group_policy must be pairing, allowlist or open")
        if self.mode == "bot" and not (self.allow_all or self.allowed_users):
            raise ValueError(
                "bot mode needs at least one allowed phone number (or allow-all) — "
                "without it every inbound message is denied"
            )
        if self.mode == "self" and (self.allowed_users or self.allow_all):
            # Self-chat ignores the allowlist (it is your own messages).
            self.allowed_users = []
            self.allow_all = False

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "allowed_users": self.allowed_users,
            "allow_all": self.allow_all,
            "group_policy": self.group_policy,
            "group_allow": self.group_allow,
            "require_mention": self.require_mention,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> BridgeSettings:
        data = data or {}
        return cls(
            mode=data.get("mode", "self"),
            allowed_users=list(data.get("allowed_users") or []),
            allow_all=bool(data.get("allow_all", False)),
            group_policy=data.get("group_policy", "pairing"),
            group_allow=list(data.get("group_allow") or []),
            require_mention=bool(data.get("require_mention", False)),
        )


def bridge_dir() -> Path:
    """Locate bridges/baileys: env override first, then the repo layout."""
    override = os.environ.get(BRIDGE_DIR_ENV)
    if override:
        return Path(override) / "baileys"
    return Path(__file__).resolve().parents[3] / "bridges" / "baileys"


def check_node() -> str:
    """Return the node executable name, raising BridgeError when unusable."""
    node = shutil.which("node")
    if not node:
        raise BridgeError(
            "Node.js 18+ is required for the Baileys route (https://nodejs.org). "
            "The official Agent Platform route needs only WhatsApp itself."
        )
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=15, check=True)
        major = int((out.stdout.strip().lstrip("v")).split(".")[0])
    except Exception as exc:
        raise BridgeError(f"could not run Node.js ({exc})") from exc
    if major < MIN_NODE_MAJOR:
        raise BridgeError(f"Node.js {MIN_NODE_MAJOR}+ is required (found v{major})")
    return node


def ensure_deps(directory: Path, node: str | None = None) -> None:
    """`npm install --omit=dev` once, when node_modules is missing."""
    if (directory / "node_modules" / "@whiskeysockets" / "baileys").is_dir():
        return
    npm = shutil.which("npm")
    if not npm:
        raise BridgeError("npm is required to fetch the Baileys bridge dependencies (bundled with Node.js)")
    try:
        subprocess.run(
            [npm, "install", "--omit=dev", "--no-audit", "--no-fund"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise BridgeError("installing the Baileys bridge dependencies timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "")[-400:]
        raise BridgeError(f"npm install failed: {detail}") from exc


@dataclass
class BridgeHandle:
    """A running bridge process and its HTTP client."""

    settings: BridgeSettings
    session_dir: Path
    process: subprocess.Popen | None = None
    port: int = 0
    token: str = ""
    _http: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=httpx.Timeout(35.0, connect=5.0),
            )
        return self._http


class BaileysBridge:
    """Owns one bridge subprocess. Not thread-safe; used from the event loop."""

    def __init__(self, settings: BridgeSettings, session_dir: Path | None = None) -> None:
        settings.validate()
        self.settings = settings
        root = paths.ensure_layout()["state"]
        self.session_dir = session_dir or root / "whatsapp" / "baileys-session"
        self.handle: BridgeHandle | None = None
        self.node = check_node()

    async def start(self) -> None:
        """Spawn the bridge and wait for its listening handshake (up to 60 s)."""
        if self.handle and self.handle.process and self.handle.process.poll() is None:
            return
        directory = bridge_dir()
        if not (directory / "index.mjs").is_file():
            raise BridgeError(f"Baileys bridge not found at {directory}")
        await asyncio.to_thread(ensure_deps, directory)

        self.session_dir.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        args = [
            self.node,
            str(directory / "index.mjs"),
            "--port", "0",
            "--token", token,
            "--session", str(self.session_dir),
            "--mode", self.settings.mode,
            "--group-policy", self.settings.group_policy,
        ]
        if self.settings.allow_all:
            args += ["--allow", "*"]
        elif self.settings.allowed_users:
            args += ["--allow", ",".join(self.settings.allowed_users)]
        if self.settings.group_allow:
            args += ["--group-allow", ",".join(self.settings.group_allow)]
        if self.settings.require_mention:
            args.append("--require-mention")

        try:
            process = await asyncio.to_thread(
                subprocess.Popen,
                args,
                cwd=str(directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise BridgeError(f"could not start the Baileys bridge ({exc})") from exc

        handle = BridgeHandle(settings=self.settings, session_dir=self.session_dir, process=process, token=token)
        self.handle = handle
        try:
            port = await asyncio.wait_for(self._read_handshake(process), timeout=60)
        except TimeoutError as exc:
            await self.stop()
            raise BridgeError("the Baileys bridge did not report its port in time") from exc
        handle.port = port
        handle._client()  # warm the client now that the port is known

    async def _read_handshake(self, process: subprocess.Popen) -> int:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue()

        def _pump() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                queue.put_nowait(line.strip())
            queue.put_nowait("")  # EOF

        loop.run_in_executor(None, _pump)
        while True:
            line = await queue.get()
            if not line:
                await self.stop()
                raise BridgeError("the Baileys bridge exited during startup (is Node.js 18+ installed?)")
            if HANDSHAKE_RE.match(line):
                return int(json.loads(line)["port"])
            if '"event": "bridge_failed"' in line:
                detail = str(json.loads(line).get("error", ""))[:300]
                await self.stop()
                raise BridgeError(f"the Baileys bridge failed to start: {detail}")
            # other stdout lines (baileys noise) are ignored

    async def stop(self) -> None:
        handle, self.handle = self.handle, None
        if not handle:
            return
        if handle._http and not handle._http.is_closed:
            await handle._http.aclose()
        if handle.process and handle.process.poll() is None:
            handle.process.terminate()
            try:
                await asyncio.to_thread(handle.process.wait, 10)
            except subprocess.TimeoutExpired:
                handle.process.kill()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.handle:
            raise BridgeError("the Baileys bridge is not running")
        try:
            response = await self.handle._client().request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise BridgeError(f"the Baileys bridge is unreachable ({type(exc).__name__})") from exc
        if response.status_code == 401:
            raise BridgeError("the Baileys bridge rejected the runtime token")
        return response

    async def health(self) -> dict:
        response = await self._request("GET", "/health")
        return response.json()

    async def qr(self) -> dict:
        response = await self._request("GET", "/qr")
        return response.json()

    async def updates(self, cursor: int, timeout: int = 20) -> tuple[list[dict], int]:
        response = await self._request(
            "GET", "/updates", params={"cursor": cursor, "timeout": min(25, max(0, timeout))}
        )
        data = response.json()
        return data.get("updates", []), int(data.get("cursor", cursor))

    async def send(self, to: str, text: str) -> str:
        response = await self._request("POST", "/send", json={"to": to, "text": text})
        if response.status_code != 200:
            raise BridgeError(f"send failed ({response.status_code})")
        return str(response.json().get("id", ""))

    async def logout(self) -> None:
        """Unpair and wipe the session (bridge-side), then stop the process."""
        if self.handle:
            try:
                await self._request("POST", "/logout")
            except BridgeError:
                pass
        await self.stop()
        shutil.rmtree(self.session_dir, ignore_errors=True)

    @property
    def running(self) -> bool:
        return bool(self.handle and self.handle.process and self.handle.process.poll() is None)
