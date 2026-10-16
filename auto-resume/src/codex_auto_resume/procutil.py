from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
SW_HIDE = 0


def hidden_kwargs() -> dict[str, Any]:
    if sys.platform != "win32":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = SW_HIDE
    return {
        "creationflags": CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def hidden_popen(args: list[str], **kwargs: Any) -> subprocess.Popen:
    merged = hidden_kwargs()
    merged.update(kwargs)
    return subprocess.Popen(args, **merged)


def claim_watch_pid(path: Path) -> bool:
    if path.exists():
        try:
            old = int(path.read_text(encoding="utf-8").strip().split()[0])
        except (OSError, ValueError):
            old = 0
        if process_running(old) and old != os.getpid():
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    return True


def release_watch_pid(path: Path) -> None:
    try:
        current = int(path.read_text(encoding="utf-8").strip().split()[0])
    except (OSError, ValueError):
        return
    if current == os.getpid():
        try:
            path.unlink()
        except OSError:
            pass


class _FILETIME(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


def _windows_process(pid: int) -> tuple[bool, float | None]:
    """返回进程是否还活着，以及它的启动时间。进程号被系统回收后，新进程的启动时间会对不上。"""
    process_query_limited = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited, False, int(pid))
    if not handle:
        # 5 = 没有权限打开进程，只能当成还在跑，避免误判后重复启动。
        return ctypes.get_last_error() == 5, None
    created = _FILETIME()
    exited = _FILETIME()
    kernel = _FILETIME()
    user = _FILETIME()
    code = ctypes.c_ulong()
    alive = True
    started: float | None = None
    try:
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            alive = code.value == still_active
        if kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            ticks = (created.hi << 32) | created.lo
            started = ticks / 10_000_000 - 11644473600
    finally:
        kernel32.CloseHandle(handle)
    return alive, started


def process_running(pid: int | None, started_at: float | None = None) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        alive, created = _windows_process(int(pid))
        if not alive:
            return False
        if started_at and created is not None and abs(created - started_at) > 30:
            return False
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
