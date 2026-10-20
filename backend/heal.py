"""Find / launch Illustrator and Photoshop. No user Settings."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .com_runner import ping_app


def _win_exe_running(exe_name: str) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if snap in (-1, ctypes.c_void_p(-1).value):
        return False
    want = exe_name.lower()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == want:
                return True
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
        return False
    finally:
        kernel32.CloseHandle(snap)


_EXE_CACHE: dict[str, tuple[float, list[Path]]] = {}
_EXE_TTL_SEC = 30.0


def _glob_exes(pattern: str) -> list[Path]:
    now = time.time()
    hit = _EXE_CACHE.get(pattern)
    if hit and now - hit[0] < _EXE_TTL_SEC:
        return hit[1]
    found: list[Path] = []
    roots = [Path(r"C:\Program Files\Adobe"), Path(r"C:\Program Files (x86)\Adobe")]
    for root in roots:
        if not root.is_dir():
            continue
        found.extend(p for p in root.glob(pattern) if p.is_file())
    found = sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)
    _EXE_CACHE[pattern] = (now, found)
    return found


def illustrator_exes() -> list[Path]:
    return _prefer_release(_glob_exes("Adobe Illustrator*/Support Files/Contents/Windows/Illustrator.exe"))


def photoshop_exes() -> list[Path]:
    return _glob_exes("Adobe Photoshop*/Photoshop.exe")


def _prefer_release(exes: list[Path]) -> list[Path]:
    # Beta registers Illustrator.Application and steals COM from 2026.
    release = [p for p in exes if "(beta)" not in str(p).lower()]
    beta = [p for p in exes if "(beta)" in str(p).lower()]
    return release + beta


def _illustrator_pids() -> set[int]:
    if sys.platform != "win32":
        return set()
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if snap in (-1, ctypes.c_void_p(-1).value):
        return set()
    pids: set[int] = set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == "illustrator.exe":
                pids.add(int(entry.th32ProcessID))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return pids


def illustrator_window_titles() -> list[str]:
    """Visible Illustrator window titles. Cheap — no COM."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    pids = _illustrator_pids()
    if not pids:
        return []
    user32 = ctypes.windll.user32
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):  # type: ignore[no-untyped-def]
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in pids:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = (buf.value or "").strip()
        if title:
            titles.append(title)
        return True

    user32.EnumWindows(_cb, 0)
    return titles


def document_name_from_title(title: str) -> str:
    """'File.ai* @ 50 % (RGB/Preview)' → 'File.ai'."""
    raw = (title or "").strip()
    if " @ " in raw:
        raw = raw.split(" @ ", 1)[0].strip()
    raw = raw.rstrip("*").strip()
    if raw.lower().endswith(".ai") or "[recovered]" in raw.lower():
        return raw
    return ""


def illustrator_bind_targets() -> list[str]:
    """File names / paths COM can GetObject to reach the instance with the doc."""
    names = []
    for title in illustrator_window_titles():
        name = document_name_from_title(title)
        if name and name not in names:
            names.append(name)
    paths: list[str] = []
    roots = [Path.home() / "Documents", Path.home() / "Desktop", Path.home() / "Downloads"]
    for key in ("TEMP", "TMP"):
        if os.environ.get(key):
            roots.append(Path(os.environ[key]))
    if os.environ.get("LOCALAPPDATA"):
        roots.append(Path(os.environ["LOCALAPPDATA"]) / "Temp")
    if os.environ.get("APPDATA"):
        roots.append(Path(os.environ["APPDATA"]) / "Adobe")
    for name in names:
        for root in roots:
            hit = _find_named(root, name, depth=3)
            if hit:
                paths.append(str(hit))
                break
    return paths + names


def _find_named(root: Path, name: str, depth: int) -> Path | None:
    # ponytail: depth-capped walk. Recovered files in %TEMP% need a wider search.
    if not root.is_dir() or depth < 0:
        return None
    try:
        direct = root / name
        if direct.is_file():
            return direct
        if depth == 0:
            return None
        for child in root.iterdir():
            if child.is_dir():
                found = _find_named(child, name, depth - 1)
                if found:
                    return found
    except OSError:
        return None
    return None


def _launch(exe: Path) -> None:
    # GUI launch — do not hide the Adobe window.
    subprocess.Popen([str(exe)], close_fds=True)


def _ensure(app: str, exe_name: str, find, progid: str, *, launch: bool) -> dict[str, Any]:
    exes = find()
    running = _win_exe_running(exe_name)
    if not exes and not running:
        return {
            "installed": False,
            "running": False,
            "exe": "",
            "com": False,
            "version": "",
            "error": f"{app} not found under Program Files\\Adobe",
        }
    # Never launch a second edition (Beta vs 2026) — Beta steals Illustrator.Application.
    # Never launch an app the caller did not name — COM CreateObject would open it anyway.
    if launch and not running and exes:
        _launch(exes[0])
        for _ in range(20):
            time.sleep(0.5)
            if _win_exe_running(exe_name):
                break
    running = _win_exe_running(exe_name)
    if not running:
        return {
            "installed": bool(exes),
            "running": False,
            "exe": str(exes[0]) if exes else "",
            "com": False,
            "version": "",
            "open_documents": [],
            "error": "not running",
        }
    ok, detail = ping_app(progid)
    docs = _open_docs(exe_name)
    return {
        "installed": bool(exes) or running,
        "running": _win_exe_running(exe_name),
        "exe": str(exes[0]) if exes else "",
        "com": ok,
        "version": detail if ok else "",
        "open_documents": docs,
        "error": "" if ok else detail,
    }


def _open_docs(exe_name: str) -> list[str]:
    if exe_name.lower() != "illustrator.exe":
        return []
    seen: list[str] = []
    for title in illustrator_window_titles():
        name = document_name_from_title(title)
        if name and name not in seen:
            seen.append(name)
    return seen


def snapshot_apps() -> dict[str, Any]:
    """Process + install probe only. Never launch, never COM."""

    def _row(app: str, exe_name: str, find) -> dict[str, Any]:
        try:
            exes = find()
        except Exception:
            exes = []
        running = _win_exe_running(exe_name)
        return {
            "installed": bool(exes) or running,
            "running": running,
            "exe": str(exes[0]) if exes else "",
            "com": False,
            "version": "",
            "open_documents": _open_docs(exe_name) if running else [],
            "error": "" if (exes or running) else f"{app} not found under Program Files\\Adobe",
        }

    return {
        "illustrator": _row("Illustrator", "Illustrator.exe", illustrator_exes),
        "photoshop": _row("Photoshop", "Photoshop.exe", photoshop_exes),
    }


def _want_app(app: str) -> str:
    raw = (app or "").strip().lower()
    if raw.startswith("ill"):
        return "illustrator"
    if raw.startswith("pho") or raw == "ps":
        return "photoshop"
    return ""


def ensure_live(app: str = "") -> dict[str, Any]:
    """Probe both apps. Launch only the one named in ``app`` (illustrator / photoshop)."""
    want = _want_app(app)
    return {
        "illustrator": _ensure(
            "Illustrator",
            "Illustrator.exe",
            illustrator_exes,
            "Illustrator.Application",
            launch=want == "illustrator",
        ),
        "photoshop": _ensure(
            "Photoshop",
            "Photoshop.exe",
            photoshop_exes,
            "Photoshop.Application",
            launch=want == "photoshop",
        ),
    }


def cheap_online() -> tuple[bool, str]:
    from . import photocraft, vectorcraft

    ai = _win_exe_running("Illustrator.exe")
    ps = _win_exe_running("Photoshop.exe")
    pc = photocraft.reachable()
    vc = vectorcraft.reachable()
    if ai or ps or pc or vc:
        bits = []
        if ai:
            docs = [document_name_from_title(t) for t in illustrator_window_titles()]
            docs = [d for d in docs if d]
            bits.append("Illustrator (" + docs[0] + ")" if docs else "Illustrator")
        if ps:
            bits.append("Photoshop")
        if pc:
            bits.append("PhotoCraft")
        if vc:
            bits.append("VectorCraft")
        return True, "Connected · " + " + ".join(bits)
    # PhotoCraft and VectorCraft open on their first call, so installed counts as ready.
    crafts = [name for name, mod in (("PhotoCraft", photocraft), ("VectorCraft", vectorcraft)) if mod.find_exe()]
    if crafts:
        return True, "Ready · " + " + ".join(crafts) + " installed (opens on first use)"
    if illustrator_exes() or photoshop_exes():
        return False, "Offline · Illustrator / Photoshop installed, not running"
    return False, "Offline · Illustrator / Photoshop / PhotoCraft / VectorCraft not installed"
