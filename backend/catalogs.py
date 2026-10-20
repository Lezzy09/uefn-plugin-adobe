"""Load vendored tool catalogs."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .com_runner import plugin_root


def _load_catalog(rel: str) -> list[dict[str, Any]]:
    path = plugin_root() / rel
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def illustrator_catalog() -> list[dict[str, Any]]:
    return _load_catalog("assets/illustrator/catalog.json")


@lru_cache(maxsize=1)
def photoshop_catalog() -> list[dict[str, Any]]:
    return _load_catalog("assets/photoshop/catalog.json")


def list_entries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in illustrator_catalog():
        rows.append(
            {
                "name": f"illustrator_{row['name']}",
                "app": "illustrator",
                "description": row.get("description") or row["name"],
                "kind": row.get("kind") or "",
            }
        )
    for row in photoshop_catalog():
        rows.append(
            {
                "name": row["name"] if str(row["name"]).startswith("photoshop_") else f"photoshop_{row['name']}",
                "app": "photoshop",
                "description": row.get("description") or row["name"],
                "kind": "recipe" if row.get("recipe") else "atomic",
            }
        )
    rows.extend(
        [
            {"name": "adobe_status", "app": "adobe", "description": "Heal + connection state"},
            {"name": "adobe_list_tools", "app": "adobe", "description": "Tool census"},
            {"name": "adobe_redeploy", "app": "adobe", "description": "Re-detect COM and relaunch"},
            {"name": "adobe_execute_jsx", "app": "adobe", "description": "Raw ExtendScript escape hatch"},
            {"name": "photocraft_status", "app": "photocraft", "description": "Install + control connection state"},
            {"name": "photocraft_commands", "app": "photocraft", "description": "Engine command census"},
            {"name": "photocraft_run", "app": "photocraft", "description": "Run an engine command by id"},
            {"name": "photocraft_inspect", "app": "photocraft", "description": "Layer tree, history, selection"},
            {"name": "photocraft_open", "app": "photocraft", "description": "Open a file under the root"},
            {"name": "photocraft_save", "app": "photocraft", "description": "Save / export under the root"},
            {"name": "photocraft_screenshot", "app": "photocraft", "description": "Window PNG"},
            {"name": "photocraft_call", "app": "photocraft", "description": "Raw control-protocol escape hatch"},
            {"name": "vectorcraft_status", "app": "vectorcraft", "description": "Install + control connection state"},
            {"name": "vectorcraft_commands", "app": "vectorcraft", "description": "Engine command census"},
            {"name": "vectorcraft_run", "app": "vectorcraft", "description": "Run an engine command by id"},
            {"name": "vectorcraft_inspect", "app": "vectorcraft", "description": "Layer tree, selection, history"},
            {"name": "vectorcraft_open", "app": "vectorcraft", "description": "Open a file under the root"},
            {"name": "vectorcraft_save", "app": "vectorcraft", "description": "Save under the root"},
            {"name": "vectorcraft_export", "app": "vectorcraft", "description": "Export PNG/SVG/PDF… under the root"},
            {"name": "vectorcraft_screenshot", "app": "vectorcraft", "description": "Window PNG"},
            {"name": "vectorcraft_call", "app": "vectorcraft", "description": "Raw control-protocol escape hatch"},
        ]
    )
    return rows
