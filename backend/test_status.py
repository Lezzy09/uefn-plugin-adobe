"""Status aggregation + register surface. No Adobe required."""

from __future__ import annotations

import json
from unittest.mock import patch

import backend as plugin
from backend.status import HINTS, build_status, classify


class FakeApi:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.tools: dict[str, object] = {}
        self.connection_fn = None
        self.connection_kwargs: dict[str, object] = {}

    def is_enabled(self) -> bool:
        return self.enabled

    def log(self, msg: str) -> None:
        return None

    def tool(self, **kwargs):  # type: ignore[no-untyped-def]
        def deco(fn):  # type: ignore[no-untyped-def]
            self.tools[kwargs.get("name") or fn.__name__] = fn
            return fn

        return deco

    def connection(self, fn: object, **kwargs: object) -> None:
        self.connection_fn = fn
        self.connection_kwargs = kwargs


def _apps(*, installed: bool, running: bool, com: bool, error: str = "") -> dict:
    row = {
        "installed": installed,
        "running": running,
        "exe": r"C:\Program Files\Adobe\x.exe" if installed else "",
        "com": com,
        "version": "29" if com else "",
        "error": error,
    }
    return {"illustrator": row, "photoshop": {**row, "com": False, "error": ""}}


def test_classify_missing() -> None:
    assert classify(_apps(installed=False, running=False, com=False)) == "missing_app"


def test_classify_ready() -> None:
    assert classify(_apps(installed=True, running=True, com=True)) == "ready"


def test_classify_error() -> None:
    apps = {
        "illustrator": {
            "installed": True,
            "running": True,
            "com": False,
            "error": "TYPE_E_LIBNOTREGISTERED",
            "exe": "x",
            "version": "",
        },
        "photoshop": {
            "installed": False,
            "running": False,
            "com": False,
            "error": "",
            "exe": "",
            "version": "",
        },
    }
    assert classify(apps) == "error"


def test_classify_launching() -> None:
    apps = {
        "illustrator": {
            "installed": True,
            "running": False,
            "com": False,
            "error": "not running",
            "exe": "x",
            "version": "",
        },
        "photoshop": {
            "installed": False,
            "running": False,
            "com": False,
            "error": "",
            "exe": "",
            "version": "",
        },
    }
    assert classify(apps) == "launching"


def test_build_status_ready() -> None:
    with patch("backend.heal.ensure_live", return_value=_apps(installed=True, running=True, com=True)):
        status = build_status()
    assert status["ok"] is True
    assert status["state"] == "ready"
    assert "illustrator_get_document_info" in status["hint"]
    assert status["tools"]["count"] > 60


def test_register_does_not_launch() -> None:
    api = FakeApi(enabled=True)
    with patch("backend.ensure_live") as mock:
        plugin.register(api)
    mock.assert_not_called()


def test_register_meta_and_art_tools() -> None:
    api = FakeApi()
    plugin.register(api)
    assert "adobe_status" in api.tools
    assert "adobe_list_tools" in api.tools
    assert "adobe_redeploy" in api.tools
    assert "adobe_execute_jsx" in api.tools
    assert "illustrator_get_document_info" in api.tools
    assert "illustrator_create_rectangle" in api.tools
    assert "illustrator_set_workflow" in api.tools
    assert "photoshop_get_state" in api.tools
    assert len([n for n in api.tools if n.startswith("illustrator_")]) >= 63
    assert api.connection_kwargs.get("label") == "Adobe MCP"


def test_adobe_status_tool_json() -> None:
    api = FakeApi()
    plugin.register(api)
    with patch(
        "backend.build_status",
        return_value={"ok": False, "state": "missing_app", "plugin_id": "adobe"},
    ):
        payload = json.loads(api.tools["adobe_status"]())
    assert payload["state"] == "missing_app"


def test_list_tools_ok() -> None:
    api = FakeApi()
    plugin.register(api)
    payload = json.loads(api.tools["adobe_list_tools"]())
    assert payload["ok"] is True
    assert payload["count"] == len(payload["tools"])


def test_hints_cover_states() -> None:
    assert set(HINTS) == {"missing_app", "launching", "ready", "error"}


def test_classify_ready_from_open_document_window() -> None:
    apps = {
        "illustrator": {
            "installed": True,
            "running": True,
            "com": False,
            "error": "empty Beta",
            "exe": "x",
            "version": "",
            "open_documents": ["ChatGPT Image [Recovered].ai"],
        },
        "photoshop": {
            "installed": False,
            "running": False,
            "com": False,
            "error": "",
            "exe": "",
            "version": "",
        },
    }
    assert classify(apps) == "ready"


def test_ensure_live_launches_only_named_app() -> None:
    from pathlib import Path

    from backend import heal

    ai = Path(r"C:\Program Files\Adobe\Adobe Illustrator 2026\Support Files\Contents\Windows\Illustrator.exe")
    ps = Path(r"C:\Program Files\Adobe\Adobe Photoshop 2026\Photoshop.exe")
    with (
        patch("backend.heal._launch") as launch,
        patch("backend.heal._win_exe_running", return_value=False),
        patch("backend.heal.ping_app") as ping,
        patch("backend.heal.illustrator_exes", return_value=[ai]),
        patch("backend.heal.photoshop_exes", return_value=[ps]),
    ):
        heal.ensure_live()
        launch.assert_not_called()
        ping.assert_not_called()

        heal.ensure_live("illustrator")
        assert launch.call_count == 1
        assert launch.call_args.args[0] == ai
        assert all(call.args[0] != ps for call in launch.call_args_list)
        assert all(call.args[0] != "Photoshop.Application" for call in ping.call_args_list)


def test_document_name_from_title() -> None:
    from backend.heal import document_name_from_title

    title = "ChatGPT Image Sep 16, 2026, 04_19_05 PM [Recovered].ai* @ 50 % (RGB/Preview)"
    assert document_name_from_title(title) == "ChatGPT Image Sep 16, 2026, 04_19_05 PM [Recovered].ai"
    assert document_name_from_title("Adobe Illustrator 2026 (Beta)") == ""
