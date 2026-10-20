"""Adobe — Store desktop plugin. Ducky is the MCP server. COM talks to the Adobe apps,
PhotoCraft's and VectorCraft's loopback control servers to PhotoCraft and VectorCraft."""

from __future__ import annotations

import json
from typing import Any

from .com_runner import INTENT, execute_illustrator, execute_photoshop
from .heal import cheap_online, ensure_live
from .illustrator_tools import register_illustrator_tools
from .photoshop_tools import register_photoshop_tools
from .status import build_status

PLUGIN_ID = "adobe"


def _connection_row() -> dict[str, Any]:
    online, detail = cheap_online()
    return {"online": online, "detail": detail}


def register(api: Any) -> None:
    # Never launch Adobe or COM-ping during register — host has a 20s watchdog.
    connect = getattr(api, "connection", None)
    if callable(connect):
        try:
            connect(_connection_row, label="Adobe MCP", program="adobe")
        except Exception:
            pass

    @api.tool(name="adobe_status", intent=INTENT, listener=False)
    def adobe_status(app: str = "") -> str:
        """Report Illustrator / Photoshop readiness. Only the named app is launched; omit to never launch."""
        return json.dumps(build_status(app=app), indent=2, default=str)

    @api.tool(name="adobe_list_tools", intent=INTENT, listener=False)
    def adobe_list_tools() -> str:
        """List Illustrator and Photoshop tools this plugin registers."""
        from . import catalogs

        return json.dumps(
            {"ok": True, "count": len(catalogs.list_entries()), "tools": catalogs.list_entries()},
            indent=2,
        )

    @api.tool(name="adobe_redeploy", intent=INTENT, listener=False)
    def adobe_redeploy(app: str = "") -> str:
        """Re-detect Adobe installs and ping COM. Only the named app is launched; omit to never launch."""
        live = ensure_live(app)
        return json.dumps(build_status(live), indent=2, default=str)

    @api.tool(name="adobe_execute_jsx", intent=INTENT, listener=False)
    def adobe_execute_jsx(app: str, code: str, params: dict[str, Any] | None = None) -> str:
        """Run raw ExtendScript in illustrator or photoshop."""
        target = (app or "").strip().lower()
        try:
            if target.startswith("ill"):
                result = execute_illustrator(code, params or {}, activate=True)
            elif target.startswith("pho") or target == "ps":
                result = execute_photoshop(code)
            else:
                return json.dumps({"ok": False, "error": "app must be illustrator or photoshop"})
        except Exception as exc:
            return json.dumps({"ok": False, "error": str(exc)}, indent=2)
        return json.dumps(result, indent=2, default=str)

    try:
        register_illustrator_tools(api)
    except Exception as exc:
        api.log(f"Adobe Illustrator tools skipped: {exc}")
    try:
        register_photoshop_tools(api)
    except Exception as exc:
        api.log(f"Adobe Photoshop tools skipped: {exc}")
    try:
        from .photocraft import register_photocraft_tools

        register_photocraft_tools(api)
    except Exception as exc:
        api.log(f"PhotoCraft tools skipped: {exc}")
    try:
        from .vectorcraft import register_vectorcraft_tools

        register_vectorcraft_tools(api)
    except Exception as exc:
        api.log(f"VectorCraft tools skipped: {exc}")
    try:
        from .automations import register_nodes

        register_nodes(api)
    except Exception as exc:
        api.log(f"Adobe automation nodes skipped: {exc}")
    api.log("Adobe plugin registered")
