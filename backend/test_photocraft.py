"""PhotoCraft client against a fake loopback control server. No PhotoCraft required."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from backend import photocraft

TOKEN = "ab" * 32


def _serve(listener: socket.socket, seen: list[dict]) -> None:
    while True:
        try:
            conn, _ = listener.accept()
        except OSError:
            return
        with conn, conn.makefile("rwb") as f:
            authed = False
            for line in f:
                req = json.loads(line)
                seen.append(req)
                if not authed:
                    authed = req.get("params", {}).get("token") == TOKEN
                    reply = {"id": req["id"], "ok": authed} if authed else {"id": req["id"], "ok": False, "error": "bad token"}
                elif req["method"] == "boom":
                    reply = {"id": req["id"], "ok": False, "error": "unknown tool `boom`"}
                else:
                    reply = {"id": req["id"], "ok": True, "result": {"echo": req}}
                f.write(json.dumps(reply).encode() + b"\n")
                f.flush()
                if not authed:
                    break


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    seen: list[dict] = []
    threading.Thread(target=_serve, args=(listener, seen), daemon=True).start()
    monkeypatch.setenv("PHOTOCRAFT_CONTROL_PORT", str(listener.getsockname()[1]))
    monkeypatch.setenv("PHOTOCRAFT_ROOT", str(tmp_path))
    monkeypatch.setattr(photocraft, "state_dir", lambda: tmp_path)
    (tmp_path / "control.token").write_text(TOKEN + "\n", encoding="utf-8")
    yield seen
    listener.close()


def test_call_authenticates_then_sends_the_request(server: list[dict]) -> None:
    result = photocraft.call("engine.execute", {"command": "file.new"}, start=False)
    assert server[0] == {"id": "auth", "method": "auth", "params": {"token": TOKEN}}
    assert result["echo"]["method"] == "engine.execute"
    assert result["echo"]["params"] == {"command": "file.new"}


def test_error_reply_raises(server: list[dict]) -> None:
    with pytest.raises(RuntimeError, match="unknown tool"):
        photocraft.call("boom", start=False)


def test_wrong_token_is_reported(server: list[dict], tmp_path: Path) -> None:
    (tmp_path / "control.token").write_text("cd" * 32, encoding="utf-8")
    with pytest.raises(RuntimeError, match="refused the token"):
        photocraft.call("ui.inspect", start=False)


def test_not_running_without_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(photocraft, "reachable", lambda: False)
    with pytest.raises(RuntimeError, match="not running"):
        photocraft.call("ui.inspect", start=False)


def test_relative_paths_stay_under_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHOTOCRAFT_ROOT", str(tmp_path))
    assert photocraft.relative(str(tmp_path / "art" / "a.psd")) == "art/a.psd"
    assert photocraft.relative("art/a.psd") == "art/a.psd"
    with pytest.raises(ValueError, match="outside"):
        photocraft.relative(str(tmp_path.parent / "elsewhere.psd"))


def test_register_tools() -> None:
    names: list[str] = []

    class Api:
        def tool(self, name, intent, listener):
            names.append(name)
            return lambda fn: fn

    photocraft.register_photocraft_tools(Api())
    assert names == [
        "photocraft_status",
        "photocraft_run",
        "photocraft_commands",
        "photocraft_inspect",
        "photocraft_open",
        "photocraft_save",
        "photocraft_screenshot",
        "photocraft_call",
    ]
