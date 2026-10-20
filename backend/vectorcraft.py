"""VectorCraft (open-source Illustrator clone) over its loopback JSON-lines control server.

VectorCraft listens only when launched with ``--control``, so a copy the user opened by hand
can't be driven: the first call launches a controllable copy. Unlike PhotoCraft the port has no
token: one connection per call, request line, reply line. File access is confined to the root
with ``--automation-read-root`` / ``--automation-write-root``. Protocol: VectorCraft
``docs/control-protocol.md``.
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
INTENT = r"\b(vectorcraft|vector ?craft)\b"
# PhotoCraft holds 47878.
DEFAULT_PORT = 47879
CONNECT_TIMEOUT = 2.0
# VectorCraft replies within 60s or answers with a timeout error itself.
REPLY_TIMEOUT = 75.0
LAUNCH_WAIT = 30.0


def port() -> int:
    try:
        return int(os.environ.get("VECTORCRAFT_CONTROL_PORT") or DEFAULT_PORT)
    except ValueError:
        return DEFAULT_PORT


def root() -> Path:
    """Read and write root granted to VectorCraft: every path a request touches stays under it."""
    return Path(os.environ.get("VECTORCRAFT_ROOT") or Path.home()).resolve()


def state_dir() -> Path:
    try:
        from backend.uefn_plugins.panel_presence import plugin_local_dir

        path = Path(plugin_local_dir(PLUGIN_ID, "vectorcraft"))
    except Exception:
        path = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "UEFN-Ducky" / "vectorcraft"
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_exe() -> Path | None:
    env = os.environ.get("VECTORCRAFT_EXE")
    if env and Path(env).is_file():
        return Path(env)
    on_path = shutil.which("vectorcraft")
    if on_path:
        return Path(on_path)
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base and (Path(base) / "VectorCraft" / "vectorcraft.exe").is_file():
            return Path(base) / "VectorCraft" / "vectorcraft.exe"
    local = os.environ.get("LOCALAPPDATA")
    if local and (Path(local) / "Programs" / "VectorCraft" / "vectorcraft.exe").is_file():
        return Path(local) / "Programs" / "VectorCraft" / "vectorcraft.exe"
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
            "VectorCraft not found. Install it (github.com/storytold/vectorcraft releases) "
            "or set VECTORCRAFT_EXE to vectorcraft.exe."
        )
    r = str(root())
    subprocess.Popen(
        [
            str(exe),
            "--control", str(port()),
            "--automation-read-root", r,
            "--automation-write-root", r,
        ],
        close_fds=True,
    )
    deadline = time.monotonic() + LAUNCH_WAIT
    while time.monotonic() < deadline:
        if reachable():
            return
        time.sleep(0.5)
    raise RuntimeError(f"VectorCraft did not open its control port {port()} within {LAUNCH_WAIT:.0f}s")


def _exchange(method: str, params: dict[str, Any]) -> Any:
    with socket.create_connection(("127.0.0.1", port()), timeout=CONNECT_TIMEOUT) as sock:
        sock.settimeout(REPLY_TIMEOUT)
        stream = sock.makefile("rwb")
        stream.write(json.dumps({"id": 1, "method": method, "params": params}).encode("utf-8") + b"\n")
        stream.flush()
        line = stream.readline()
        if not line:
            raise RuntimeError("VectorCraft closed the connection")
        reply = json.loads(line)
        if not reply.get("ok"):
            raise RuntimeError(str(reply.get("error") or "VectorCraft error"))
        return reply.get("result")


def call(method: str, params: dict[str, Any] | None = None, *, start: bool = True) -> Any:
    """One control request. Launches a controllable VectorCraft first when none is listening."""
    if not reachable():
        if not start:
            raise RuntimeError("VectorCraft is not running with its control server")
        launch()
    return _exchange(method, params or {})


def absolute(path: str) -> str:
    """An absolute path under root(): VectorCraft refuses anything outside its automation roots."""
    p = Path(path)
    if not p.is_absolute():
        p = root() / p
    p = p.resolve()
    try:
        p.relative_to(root())
    except ValueError:
        raise ValueError(f"{path} is outside the VectorCraft root {root()} (set VECTORCRAFT_ROOT)") from None
    return str(p)


def write(method: str, params: dict[str, Any]) -> Any:
    """app.save / app.export that only report ok once the file is on disk.

    VectorCraft writes in the background and answers ok at once, even when the write later
    fails (a missing folder gives os error 3). So: create the folder first, wait for the
    background job to finish, then check every file it named.
    """
    if params.get("path"):
        Path(params["path"]).parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = call(method, params)
    if not (isinstance(result, dict) and result.get("background")):
        return result
    deadline = time.monotonic() + REPLY_TIMEOUT
    while time.monotonic() < deadline:
        if not (call("ui.inspect", start=False) or {}).get("background"):
            break
        time.sleep(0.25)
    paths = [str(p) for p in (result.get("files") or [result.get("path")]) if p]
    missing = [p for p in paths if not Path(p).is_file() or Path(p).stat().st_mtime < started - 1]
    if missing:
        raise RuntimeError(
            f"VectorCraft did not write {', '.join(missing)}. Its error may be open in a dialog: "
            "vectorcraft_call('ui.inspect') then ui.dialog.cancel."
        )
    return {k: v for k, v in result.items() if k not in ("background", "status")}


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
            out["document"] = call("document.inspect", {"depth": 1}, start=False)
            out["ok"] = True
        except Exception as exc:
            out["ok"] = False
            out["error"] = str(exc)
    else:
        out["ok"] = exe is not None
        out["hint"] = (
            "Installed, not running: any vectorcraft_* call launches it."
            if exe
            else "Install VectorCraft or set VECTORCRAFT_EXE."
        )
    return out


def screenshot() -> str:
    """Capture the window to a PNG in the plugin's local folder; returns its path.

    The window needs a presented frame (not minimized, covered or on a locked screen);
    without one this falls back to a headless render of the first artboard.
    """
    try:
        result = call("ui.screenshot", {"data": True})
    except RuntimeError as exc:
        if "frame" not in str(exc).lower():
            raise
        result = call("ui.render", {"data": True})
    data = result.get("pngBase64") if isinstance(result, dict) else None
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


def register_vectorcraft_tools(api: Any) -> None:
    @api.tool(name="vectorcraft_status", intent=INTENT, listener=False)
    def vectorcraft_status() -> str:
        """VectorCraft install, control connection and open document. Never launches it."""
        return _out(status)

    @api.tool(name="vectorcraft_run", intent=INTENT, listener=False)
    def vectorcraft_run(command: str, params: dict[str, Any] | None = None) -> str:
        """Run a VectorCraft engine command by id (engine.execute), e.g. file.new, shape.rectangle,
        path.create, text.create, paint.setFill, object.align. Find ids with vectorcraft_commands."""
        return _out(call, "engine.execute", {"command": command, "params": params or {}})

    @api.tool(name="vectorcraft_commands", intent=INTENT, listener=False)
    def vectorcraft_commands(filter: str = "", enabled_only: bool = False) -> str:
        """List VectorCraft commands. filter matches id or label and returns each match's params doc;
        without a filter only id and label come back (there are over 1000 commands)."""

        def rows() -> list[dict[str, Any]]:
            needle = filter.strip().lower()
            keys = ("id", "label", "params", "enabled", "disabledReason") if needle else ("id", "label")
            out = []
            for row in call("engine.commands") or []:
                if needle and needle not in f"{row.get('id', '')} {row.get('label', '')}".lower():
                    continue
                if enabled_only and not row.get("enabled"):
                    continue
                out.append({k: row.get(k) for k in keys})
            return out

        return _out(rows)

    @api.tool(name="vectorcraft_inspect", intent=INTENT, listener=False)
    def vectorcraft_inspect(params: dict[str, Any] | None = None) -> str:
        """The active VectorCraft document: layer tree, selection, history, paint defaults.
        params: depth, childLimit, ids, kind, limit, offset slice the tree."""
        return _out(call, "document.inspect", params or {})

    @api.tool(name="vectorcraft_open", intent=INTENT, listener=False)
    def vectorcraft_open(path: str) -> str:
        """Open a .ai, .svg, .pdf, .eps, .vcraft… in VectorCraft. Path must be under the VectorCraft root."""
        return _out(lambda: call("app.open", {"path": absolute(path)}))

    @api.tool(name="vectorcraft_save", intent=INTENT, listener=False)
    def vectorcraft_save(path: str = "") -> str:
        """Save the active document. No path writes back to its own file."""
        return _out(lambda: write("app.save", {"path": absolute(path)} if path else {}))

    @api.tool(name="vectorcraft_export", intent=INTENT, listener=False)
    def vectorcraft_export(path: str, format: str = "", use_artboards: bool = False) -> str:
        """Export the active document (PNG, JPEG, WebP, SVG, PDF…; the extension picks the format
        unless format is set). use_artboards writes one file per artboard."""

        def run() -> Any:
            params: dict[str, Any] = {"path": absolute(path)}
            if format:
                params["format"] = format
            if use_artboards:
                params["useArtboards"] = True
            return write("app.export", params)

        return _out(run)

    @api.tool(name="vectorcraft_screenshot", intent=INTENT, listener=False)
    def vectorcraft_screenshot() -> str:
        """Capture the VectorCraft window as a PNG and return its path (an artboard render when
        the window isn't on screen)."""
        return _out(lambda: {"ok": True, "path": screenshot()})

    @api.tool(name="vectorcraft_call", intent=INTENT, listener=False)
    def vectorcraft_call(method: str, params: dict[str, Any] | None = None) -> str:
        """Raw control-protocol request: ui.inspect, ui.render, ui.menu.invoke, ui.pointer,
        ui.dialog.*, ui.key… Escape hatch when vectorcraft_run is not enough."""
        return _out(call, method, params or {})
