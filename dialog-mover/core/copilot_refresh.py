"""Invalidate Copilot Desktop's in-memory chat list after an external import.

Use the native WebView's reload accelerator. No process
termination, developer tools, app credentials or executable chat content.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
import sqlite3
from contextlib import closing
from pathlib import Path


def _has_draft(parent: int) -> bool | None:
    """Inspect only the visible composer; never log or persist its contents."""
    try:
        import clr
        from System.Runtime.InteropServices import RuntimeEnvironment
        runtime = Path(str(RuntimeEnvironment.GetRuntimeDirectory()))
        for assembly in ("UIAutomationClient", "UIAutomationTypes"):
            clr.AddReference(str(runtime / "WPF" / (assembly + ".dll")))
        from System import IntPtr
        from System.Windows.Automation import AutomationElement, ControlType, PropertyCondition, TreeScope, ValuePattern, TextPattern
        root = AutomationElement.FromHandle(IntPtr(parent))
        document = root.FindFirst(TreeScope.Descendants, PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Document))
        if document is None:
            return None  # An unavailable browser tree is not an empty composer.
        editors = root.FindAll(TreeScope.Descendants, PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Edit))
        for editor in editors:
            if editor.Current.Name != "Message":
                continue
            patterns = list(editor.GetSupportedPatterns())
            if ValuePattern.Pattern in patterns:
                if str(editor.GetCurrentPattern(ValuePattern.Pattern).Current.Value or "").strip():
                    return True
            elif TextPattern.Pattern in patterns:
                if str(editor.GetCurrentPattern(TextPattern.Pattern).DocumentRange.GetText(-1) or "").strip():
                    return True
            else:
                return None
        return False
    except Exception:
        return None


def refresh() -> str:
    if sys.platform != "win32":
        return "unsupported"
    # A reload only reconnects the UI, but do not do it while a task is active.
    # Read a boolean from the destination index, never any conversation body.
    from . import copilot_local
    try:
        with closing(sqlite3.connect((copilot_local.root() / "data.db").as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute("SELECT EXISTS(SELECT 1 FROM sessions WHERE is_running = 1)").fetchone()[0]:
                return "busy"
    except (OSError, sqlite3.Error, ValueError):
        return "unavailable"
    return _windows()


def _windows() -> str:
    from ctypes import wintypes as w

    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback, w.LPARAM]
    user.EnumChildWindows.argtypes = [w.HWND, callback, w.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [w.HWND]
    user.GetForegroundWindow.restype = w.HWND
    user.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
    user.IsIconic.argtypes = [w.HWND]
    user.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user.GetAsyncKeyState.restype = w.SHORT
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    expected = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/GitHub Copilot/github.exe"
    if not expected.is_absolute() or not expected.is_file():
        return "unavailable"

    def owned(hwnd):
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return False
        try:
            name = ctypes.create_unicode_buffer(32768)
            size = w.DWORD(len(name))
            return bool(kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size))) and os.path.normcase(name.value) == os.path.normcase(str(expected))
        finally:
            kernel.CloseHandle(handle)

    windows = []
    @callback
    def top(hwnd, _):
        if user.IsWindowVisible(hwnd) and owned(hwnd):
            windows.append(hwnd)
        return True
    user.EnumWindows(top, 0)
    targets = []
    for parent in windows:
        @callback
        def child(hwnd, _):
            name = ctypes.create_unicode_buffer(256)
            user.GetClassNameW(hwnd, name, len(name))
            if name.value == "Chrome_WidgetWin_0" and user.IsWindowVisible(hwnd):
                targets.append((parent, hwnd))
            return True
        user.EnumChildWindows(parent, child, 0)
    if not targets:
        return "not-running" if not windows else "unavailable"
    if len(targets) != 1 or not owned(targets[0][0]):
        return "unavailable"
    parent, _ = targets[0]
    if user.IsIconic(parent):
        user.ShowWindow(parent, 9)
    user.SetForegroundWindow(parent)
    deadline = time.monotonic() + 1
    while user.GetForegroundWindow() != parent and time.monotonic() < deadline:
        time.sleep(.02)
    if user.GetForegroundWindow() != parent or not owned(parent):
        return "unavailable"
    draft = _has_draft(parent)
    if draft is not False:
        return "draft" if draft else "unavailable"
    class Keyboard(ctypes.Structure):
        _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD), ("time", w.DWORD), ("extra", ctypes.c_size_t)]
    class Mouse(ctypes.Structure):
        _fields_ = [("x", w.LONG), ("y", w.LONG), ("data", w.DWORD), ("flags", w.DWORD), ("time", w.DWORD), ("extra", ctypes.c_size_t)]
    class Payload(ctypes.Union):
        _fields_ = [("key", Keyboard), ("mouse", Mouse)]
    class Input(ctypes.Structure):
        _fields_ = [("type", w.DWORD), ("payload", Payload)]
    user.SendInput.argtypes = [w.UINT, ctypes.POINTER(Input), ctypes.c_int]
    keys = (Input * 2)(Input(1, Payload(key=Keyboard(0x74, 0, 0, 0, 0))), Input(1, Payload(key=Keyboard(0x74, 0, 2, 0, 0))))
    if any(user.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        return "unavailable"
    if user.GetForegroundWindow() != parent or user.SendInput(2, keys, ctypes.sizeof(Input)) != 2:
        return "unavailable"
    return "requested"
