"""PhotoCraft (open-source Photoshop clone) over its loopback JSON-lines control server.

PhotoCraft listens only when launched with ``--control``, so a copy the user opened by hand
can't be driven: the first call launches a controllable copy. One connection per call: auth
line, request line, reply line. Protocol: PhotoCraft ``docs/control-protocol.md``.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

PLUGIN_ID = "adobe"
INTENT = r"\b(photocraft|photo ?craft)\b"
DEFAULT_PORT = 47878
CONNECT_TIMEOUT = 2.0
# PhotoCraft replies within 60s or answers with a timeout error itself.
REPLY_TIMEOUT = 75.0
LAUNCH_WAIT = 30.0


def port() -> int:
    try:
        return int(os.environ.get("PHOTOCRAFT_CONTROL_PORT") or DEFAULT_PORT)
    except ValueError:
        return DEFAULT_PORT


def root() -> Path:
    """Read and write root granted to PhotoCraft: app.open / app.save stay under it."""
    return Path(os.environ.get("PHOTOCRAFT_ROOT") or Path.home()).resolve()


def state_dir() -> Path:
    try:
        from backend.uefn_plugins.panel_presence import plugin_local_dir

        path = Path(plugin_local_dir(PLUGIN_ID, "photocraft"))
    except Exception:
        path = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "UEFN-Ducky" / "photocraft"
    path.mkdir(parents=True, exist_ok=True)
    return path


def token_file() -> Path:
    # PhotoCraft creates it (256-bit token) on first launch and reuses it after.
    return state_dir() / "control.token"


def find_exe() -> Path | None:
    env = os.environ.get("PHOTOCRAFT_EXE")
    if env and Path(env).is_file():
        return Path(env)
    on_path = shutil.which("photocraft")
    if on_path:
        return Path(on_path)
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base and (Path(base) / "PhotoCraft" / "photocraft.exe").is_file():
            return Path(base) / "PhotoCraft" / "photocraft.exe"
    local = os.environ.get("LOCALAPPDATA")
    if local and (Path(local) / "Programs" / "PhotoCraft" / "photocraft.exe").is_file():
        return Path(local) / "Programs" / "PhotoCraft" / "photocraft.exe"
    return None


def reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port()), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def launch() -> None:
    exe = find_exe()
    if exe is None:
        raise RuntimeError(
            "PhotoCraft not found. Install it (github.com/storytold/photocraft releases) "
            "or set PHOTOCRAFT_EXE to photocraft.exe."
        )
    r = str(root())
    subprocess.Popen(
        [
            str(exe),
            "--control", str(port()),
            "--control-token-file", str(token_file()),
            "--automation-read-root", r,
            "--automation-write-root", r,
        ],
        close_fds=True,
    )
    deadline = time.monotonic() + LAUNCH_WAIT
    while time.monotonic() < deadline:
        if reachable() and token_file().is_file():
            return
        time.sleep(0.5)
    raise RuntimeError(f"PhotoCraft did not open its control port {port()} within {LAUNCH_WAIT:.0f}s")


def _exchange(method: str, params: dict[str, Any]) -> Any:
    token = token_file().read_text(encoding="utf-8").strip()
    with socket.create_connection(("127.0.0.1", port()), timeout=CONNECT_TIMEOUT) as sock:
        sock.settimeout(REPLY_TIMEOUT)
        stream = sock.makefile("rwb")
        for frame in (
            {"id": "auth", "method": "auth", "params": {"token": token}},
            {"id": 1, "method": method, "params": params},
        ):
            stream.write(json.dumps(frame).encode("utf-8") + b"\n")
            stream.flush()
            line = stream.readline()
            if not line:
                raise RuntimeError("PhotoCraft closed the connection")
            reply = json.loads(line)
            if not reply.get("ok"):
                if frame["id"] == "auth":
                    raise RuntimeError(
                        f"PhotoCraft refused the token ({reply.get('error')}). Something else may hold "
                        f"port {port()}, or PhotoCraft was started with another token: close it and retry."
                    )
                raise RuntimeError(str(reply.get("error") or "PhotoCraft error"))
        return reply.get("result")


def call(method: str, params: dict[str, Any] | None = None, *, start: bool = True) -> Any:
    """One control request. Launches a controllable PhotoCraft first when none is listening."""
    if not reachable():
        if not start:
            raise RuntimeError("PhotoCraft is not running with its control server")
        launch()
    return _exchange(method, params or {})


def relative(path: str) -> str:
    """A path for app.open / app.save: relative to root(), which PhotoCraft requires."""
    p = Path(path)
    if not p.is_absolute():
        return p.as_posix()
    try:
        return p.resolve().relative_to(root()).as_posix()
    except ValueError:
        raise ValueError(f"{path} is outside the PhotoCraft root {root()} (set PHOTOCRAFT_ROOT)") from None


def status() -> dict[str, Any]:
    exe = find_exe()
    up = reachable()
    out: dict[str, Any] = {
        "installed": exe is not None,
        "exe": str(exe) if exe else "",
        "running": up,
        "port": port(),
        "root": str(root()),
    }
    if up:
        try:
            out["document"] = call("engine.execute", {"command": "document.inspect", "params": {}}, start=False)
            out["ok"] = True
        except Exception as exc:
            out["ok"] = False
            out["error"] = str(exc)
    else:
        out["ok"] = exe is not None
        out["hint"] = (
            "Installed, not running: any photocraft_* call launches it."
            if exe
            else "Install PhotoCraft or set PHOTOCRAFT_EXE."
        )
    return out


def screenshot() -> str:
    """Capture the window to a PNG in the plugin's local folder; returns its path."""
    result = call("ui.screenshot", {})
    data = result.get("base64") if isinstance(result, dict) else None
    if not isinstance(data, str):
        raise RuntimeError(f"unexpected screenshot reply: {str(result)[:200]}")
    path = state_dir() / f"screenshot-{int(time.time() * 1000)}.png"
    path.write_bytes(base64.b64decode(data))
    return str(path)


def _out(fn, *args: Any) -> str:
    try:
        result = fn(*args)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, indent=2)
    if isinstance(result, dict) and "ok" in result:
        return json.dumps(result, indent=2, default=str)
    return json.dumps({"ok": True, "result": result}, indent=2, default=str)


def register_photocraft_tools(api: Any) -> None:
    @api.tool(name="photocraft_status", intent=INTENT, listener=False)
    def photocraft_status() -> str:
        """PhotoCraft install, control connection and open document. Never launches it."""
        return _out(status)

    @api.tool(name="photocraft_run", intent=INTENT, listener=False)
    def photocraft_run(command: str, params: dict[str, Any] | None = None) -> str:
        """Run a PhotoCraft engine command by id (engine.execute), e.g. file.new, layer.new.layer,
        paint.stroke, select.rect, layer.setProps. Find ids with photocraft_commands."""
        return _out(call, "engine.execute", {"command": command, "params": params or {}})

    @api.tool(name="photocraft_commands", intent=INTENT, listener=False)
    def photocraft_commands(filter: str = "", enabled_only: bool = False) -> str:
        """List PhotoCraft commands (id, label, params doc, enabled). filter matches id or label."""

        def rows() -> list[dict[str, Any]]:
            needle = filter.strip().lower()
            out = []
            for row in call("engine.commands") or []:
                if needle and needle not in f"{row.get('id', '')} {row.get('label', '')}".lower():
                    continue
                if enabled_only and not row.get("enabled"):
                    continue
                out.append({k: row.get(k) for k in ("id", "label", "params", "enabled", "disabledReason")})
            return out

        return _out(rows)

    @api.tool(name="photocraft_inspect", intent=INTENT, listener=False)
    def photocraft_inspect() -> str:
        """The active PhotoCraft document: layer tree, history, selection."""
        return _out(call, "engine.execute", {"command": "document.inspect", "params": {}})

    @api.tool(name="photocraft_open", intent=INTENT, listener=False)
    def photocraft_open(path: str) -> str:
        """Open an image or PSD in PhotoCraft. Path must be under the PhotoCraft root."""
        return _out(lambda: call("app.open", {"path": relative(path)}))

    @api.tool(name="photocraft_save", intent=INTENT, listener=False)
    def photocraft_save(path: str = "") -> str:
        """Save the active document; the extension picks the format (.psd, .png, .jpg…).
        No path writes back to its own PSD/PSB/.pcraft file."""
        return _out(lambda: call("app.save", {"path": relative(path)} if path else {}))

    @api.tool(name="photocraft_screenshot", intent=INTENT, listener=False)
    def photocraft_screenshot() -> str:
        """Capture the PhotoCraft window as a PNG and return its path."""
        return _out(lambda: {"ok": True, "path": screenshot()})

    @api.tool(name="photocraft_call", intent=INTENT, listener=False)
    def photocraft_call(method: str, params: dict[str, Any] | None = None) -> str:
        """Raw control-protocol request: ui.inspect, ui.set, ui.pointer, ui.menu.invoke,
        ui.dialog.*, ui.key… Escape hatch when photocraft_run is not enough."""
        return _out(call, method, params or {})
