"""Invalidate Copilot Desktop's in-memory chat list after an external import.

The desktop app reads its session list once per page load, so an external write
stays invisible until the page is reloaded. Use the WebView's own reload
accelerator (F5), then confirm the page tree really was rebuilt. No process
termination, no protocol links (a second instance cannot share the profile and
fails with an access error), no developer tools, no credentials, no chat content.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
import sqlite3
from contextlib import closing
from pathlib import Path

RELOAD_WAIT = 6.0


def _document(parent: int):
    """The visible web document, or None when the browser tree is unreadable."""
    import clr
    from System.Runtime.InteropServices import RuntimeEnvironment
    runtime = Path(str(RuntimeEnvironment.GetRuntimeDirectory()))
    for assembly in ("UIAutomationClient", "UIAutomationTypes"):
        clr.AddReference(str(runtime / "WPF" / (assembly + ".dll")))
    from System import IntPtr
    from System.Windows.Automation import AutomationElement, ControlType, PropertyCondition, TreeScope
    root = AutomationElement.FromHandle(IntPtr(parent))
    return root, root.FindFirst(TreeScope.Descendants, PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Document))


def _has_draft(parent: int) -> bool | None:
    """Inspect only the visible composer; never log or persist its contents."""
    try:
        root, document = _document(parent)
        if document is None:
            return None  # An unavailable browser tree is not an empty composer.
        from System.Windows.Automation import AutomationElement, ControlType, PropertyCondition, TreeScope, ValuePattern, TextPattern
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


def _fingerprint(parent: int) -> str:
    """A page-load marker: the runtime ids of the document and its session list.

    Chromium rebuilds these ids on every page load and keeps them stable
    otherwise, so a change proves the reload happened rather than a repaint.
    """
    try:
        root, document = _document(parent)
        if document is None:
            return ""
        from System.Windows.Automation import AutomationElement, ControlType, PropertyCondition, TreeScope, AndCondition
        parts = ["-".join(str(part) for part in document.GetRuntimeId())]
        tree = root.FindFirst(TreeScope.Descendants, AndCondition(
            PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Tree),
            PropertyCondition(AutomationElement.NameProperty, "Sessions")))
        if tree is not None:
            parts.append("-".join(str(part) for part in tree.GetRuntimeId()))
        return "|".join(parts)
    except Exception:
        return ""


def _reloaded(parent: int, before: str, timeout: float = RELOAD_WAIT) -> bool:
    """Only report a reload after the page tree was actually rebuilt."""
    if not before:
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(.12)
        after = _fingerprint(parent)
        if after and after != before:
            return True
    return False


def _busy() -> str:
    # A reload only reconnects the UI, but do not do it while a task is active.
    # Read a boolean from the destination index, never any conversation body.
    from . import copilot_local
    try:
        with closing(sqlite3.connect((copilot_local.root() / "data.db").as_uri() + "?mode=ro", uri=True)) as connection:
            if connection.execute("SELECT EXISTS(SELECT 1 FROM sessions WHERE is_running = 1)").fetchone()[0]:
                return "busy"
    except (OSError, sqlite3.Error, ValueError):
        return "unavailable"
    return 'idle'


def refresh(*, passive: bool = False) -> str:
    if sys.platform not in {'win32', 'darwin'}:
        return 'unsupported'
    state = _busy()
    if state != 'idle': return state
    if sys.platform == 'darwin':
        from .copilot_refresh_macos import refresh as mac_refresh
        return mac_refresh(passive=passive, busy=_busy)
    return _windows(passive=True) if passive else _windows()


def _running(executable: Path) -> bool:
    """Whether the desktop app's process exists, with or without a window.

    Closing the window only hides Copilot to the tray, so "no window" must never
    be read as "not running": launching the ghapp:// link would then start a
    second instance that cannot share the profile and fails with an access error.
    """
    from ctypes import wintypes as w

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class Entry(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                    ("heap", ctypes.c_void_p), ("module", w.DWORD), ("threads", w.DWORD),
                    ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD),
                    ("name", w.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot == w.HANDLE(-1).value or not snapshot:
        return False
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(Entry)
        if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
            return False
        while True:
            if os.path.normcase(entry.name) == os.path.normcase(executable.name):
                return True
            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                return False
    finally:
        kernel.CloseHandle(snapshot)


def _windows(*, passive: bool = False) -> str:
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
        # Visibility is deliberately not required: a minimised window and the
        # tray have no visible webview until the window is restored again.
        if owned(hwnd):
            windows.append(hwnd)
        return True
    user.EnumWindows(top, 0)
    if not windows:
        return "not-running" if not _running(expected) else "no-window"
    hosts = {}
    for parent in windows:
        found = []
        @callback
        def child(hwnd, _):
            name = ctypes.create_unicode_buffer(256)
            user.GetClassNameW(hwnd, name, len(name))
            if name.value == "Chrome_WidgetWin_0":
                found.append(hwnd)
            return True
        user.EnumChildWindows(parent, child, 0)
        if found:
            hosts[parent] = found
    if len(hosts) != 1:
        # No window, or more than one: never guess which one to type into.
        return "no-window" if not hosts else "unavailable"
    parent = next(iter(hosts))
    if not owned(parent):
        return "unavailable"
    if user.IsIconic(parent):
        # Restoring a waiting window must not take the keyboard away from the user.
        user.ShowWindow(parent, 4 if passive else 9)
        deadline = time.monotonic() + 2
        while not any(user.IsWindowVisible(handle) for handle in hosts[parent]):
            if time.monotonic() >= deadline:
                return "unavailable"
            time.sleep(.05)
    if passive:
        # Waiting for a draft to be sent must not repeatedly steal keyboard focus.
        draft = _has_draft(parent)
        if draft is not False:
            return "draft" if draft else "unavailable"
    user.SetForegroundWindow(parent)
    deadline = time.monotonic() + 1.2
    while user.GetForegroundWindow() != parent and time.monotonic() < deadline:
        time.sleep(.02)
    if user.GetForegroundWindow() != parent or not owned(parent):
        return "unavailable"
    draft = _has_draft(parent)
    if draft is not False:
        return "draft" if draft else "unavailable"
    before = _fingerprint(parent)
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
    return "requested" if _reloaded(parent, before) else "unavailable"
