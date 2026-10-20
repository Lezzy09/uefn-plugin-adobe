"""VectorCraft client against a fake loopback control server. No VectorCraft required."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from backend import vectorcraft


def _serve(listener: socket.socket, seen: list[dict]) -> None:
    while True:
        try:
            conn, _ = listener.accept()
        except OSError:
            return
        with conn, conn.makefile("rwb") as f:
            for line in f:
                req = json.loads(line)
                seen.append(req)
                if req["method"] == "boom":
                    reply = {"id": req["id"], "ok": False, "error": "unknown method `boom`"}
                elif req["method"] == "app.export":
                    path = Path(req["params"]["path"])
                    if path.stem != "fails":
                        path.write_text("<svg/>", encoding="utf-8")
                    reply = {"id": req["id"], "ok": True, "result": {"background": True, "path": str(path), "status": "…"}}
                elif req["method"] == "ui.inspect":
                    reply = {"id": req["id"], "ok": True, "result": {"background": []}}
                else:
                    reply = {"id": req["id"], "ok": True, "result": {"echo": req}}
                f.write(json.dumps(reply).encode() + b"\n")
                f.flush()


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    seen: list[dict] = []
    threading.Thread(target=_serve, args=(listener, seen), daemon=True).start()
    monkeypatch.setenv("VECTORCRAFT_CONTROL_PORT", str(listener.getsockname()[1]))
    monkeypatch.setenv("VECTORCRAFT_ROOT", str(tmp_path))
    monkeypatch.setattr(vectorcraft, "state_dir", lambda: tmp_path)
    yield seen
    listener.close()


def test_call_sends_the_request_without_auth(server: list[dict]) -> None:
    result = vectorcraft.call("engine.execute", {"command": "file.new"}, start=False)
    assert server[0] == {"id": 1, "method": "engine.execute", "params": {"command": "file.new"}}
    assert result["echo"]["method"] == "engine.execute"


def test_error_reply_raises(server: list[dict]) -> None:
    with pytest.raises(RuntimeError, match="unknown method"):
        vectorcraft.call("boom", start=False)


def test_not_running_without_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vectorcraft, "reachable", lambda: False)
    with pytest.raises(RuntimeError, match="not running"):
        vectorcraft.call("ui.inspect", start=False)


def test_write_creates_the_folder_and_waits_for_the_file(server: list[dict], tmp_path: Path) -> None:
    target = tmp_path / "new" / "deeper" / "hud.svg"
    result = vectorcraft.write("app.export", {"path": str(target)})
    assert target.is_file()
    assert result == {"path": str(target)}


def test_write_reports_a_file_that_never_appeared(server: list[dict], tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="did not write"):
        vectorcraft.write("app.export", {"path": str(tmp_path / "fails.svg")})


def test_paths_resolve_under_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VECTORCRAFT_ROOT", str(tmp_path))
    want = str((tmp_path / "art" / "a.svg").resolve())
    assert vectorcraft.absolute(str(tmp_path / "art" / "a.svg")) == want
    assert vectorcraft.absolute("art/a.svg") == want
    with pytest.raises(ValueError, match="outside"):
        vectorcraft.absolute(str(tmp_path.parent / "elsewhere.svg"))


def test_register_tools() -> None:
    names: list[str] = []

    class Api:
        def tool(self, name, intent, listener):
            names.append(name)
            return lambda fn: fn

    vectorcraft.register_vectorcraft_tools(Api())
    assert names == [
        "vectorcraft_status",
        "vectorcraft_run",
        "vectorcraft_commands",
        "vectorcraft_inspect",
        "vectorcraft_open",
        "vectorcraft_save",
        "vectorcraft_export",
        "vectorcraft_screenshot",
        "vectorcraft_call",
    ]
