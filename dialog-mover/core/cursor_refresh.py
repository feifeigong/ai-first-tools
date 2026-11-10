"""Ask a running Cursor window to re-read its session list after an import.

Cursor reads the session index once when a window opens and never watches
the database, so a record written from outside appears only after that
window reloads. The only in-place reload is Cursor's own command, reached
through its command palette. The palette is opened and verified through UI
Automation first; the command name is typed only once that palette is
confirmed, and Enter is pressed only when a reload entry is actually
listed. Every other outcome returns before any keystroke is sent, so an
unsent draft or a running agent is never disturbed.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time

# The glass window's command palette always lists these actions; a sidebar
# list of chat titles cannot, so their presence identifies an open palette.
PALETTE = {"go back", "go forward", "new agent", "select model",
           "后退", "前进", "新建 agent", "新建代理", "选择模型"}
RELOAD = ("reload window", "developer: reload window", "重新加载窗口", "重新加载")
BUSY = {"stop", "停止", "stop generating", "停止生成"}
PROMPT = "prompt"
PALETTE_WAIT = 2.5  # How long Cursor's palette may take to appear.
LIST_WAIT = 2.5  # How long the filtered list may take to list the command.


def _name(text: str) -> str:
    return (text or "").casefold().strip().rstrip("….").strip()


def _palette_open(names) -> bool:
    return len(PALETTE & {_name(name) for name in names}) >= 3


def _reload_entry(names) -> bool:
    """True only for Cursor's own reload command, with or without its shortcut."""
    for name in names:
        folded = _name(name)
        for entry in RELOAD:
            if folded == entry:
                return True
            if not folded.startswith(entry):
                continue
            rest = folded[len(entry):].strip()
            # Cursor appends the key binding to the row; a longer command name
            # (e.g. "Reload Window Settings") is a different command.
            if not rest or any(hint in rest for hint in ("+", "ctrl", "cmd", "alt", "shift", "⌘", "⌥")):
                return True
    return False


def _uia():
    import clr
    from pathlib import Path
    from System.Runtime.InteropServices import RuntimeEnvironment

    runtime = Path(str(RuntimeEnvironment.GetRuntimeDirectory()))
    for assembly in ("UIAutomationClient", "UIAutomationTypes"):
        clr.AddReference(str(runtime / "WPF" / (assembly + ".dll")))
    from System import IntPtr
    from System.Windows.Automation import (AutomationElement, ControlType, TreeWalker,
                                           ValuePattern)
    return IntPtr, AutomationElement, ControlType, TreeWalker, ValuePattern


def _windows() -> list:
    """Visible top-level windows owned by Cursor.exe, as (handle, title)."""
    from ctypes import wintypes as w

    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback, w.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    user.IsWindowVisible.argtypes = [w.HWND]
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]

    def image(hwnd):
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            name = ctypes.create_unicode_buffer(32768)
            size = w.DWORD(len(name))
            return name.value if kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)) else ""
        finally:
            kernel.CloseHandle(handle)

    found = []

    @callback
    def visit(hwnd, _):
        if user.IsWindowVisible(hwnd) and os.path.basename(image(hwnd)).casefold() == "cursor.exe":
            title = ctypes.create_unicode_buffer(512)
            user.GetWindowTextW(hwnd, title, 512)
            found.append((hwnd, title.value))
        return True

    user.EnumWindows(visit, 0)
    return found


def _walk(root):
    """Depth-first walk of the window's control tree, with hard limits."""
    _, _, _, TreeWalker, _ = _uia()
    walker = TreeWalker.RawViewWalker
    pending = [(root, 0)]
    seen = 0
    while pending and seen < 4000:
        element, depth = pending.pop()
        seen += 1
        try:
            kind = element.Current.ControlType.ProgrammaticName
        except Exception:
            continue
        yield element, kind
        if depth >= 34:
            continue
        children = []
        try:
            child = walker.GetFirstChild(element)
            while child is not None and len(children) < 90:
                children.append(child)
                child = walker.GetNextSibling(child)
        except Exception:
            children = []
        pending.extend((child, depth + 1) for child in reversed(children))


def _names(root) -> list:
    """Every list row the window currently exposes."""
    found = []
    for element, kind in _walk(root):
        if kind not in ("ControlType.ListItem", "ControlType.MenuItem"):
            continue
        try:
            name = element.Current.Name
        except Exception:
            continue
        if name:
            found.append(name)
    return found


def _inspect(root) -> str:
    """'ready', 'draft' (unsent text), 'busy' (agent working) or 'unavailable'."""
    _, _, _, _, ValuePattern = _uia()
    draft = False
    busy = False
    composers = 0
    for element, kind in _walk(root):
        if kind == "ControlType.Edit":
            try:
                klass = (element.Current.ClassName or "").casefold()
                name = _name(element.Current.Name)
            except Exception:
                continue
            if name != PROMPT and "prosemirror" not in klass:
                continue  # Some other field, not the message composer.
            composers += 1
            try:
                value = str(element.GetCurrentPattern(ValuePattern.Pattern).Current.Value or "")
            except Exception:
                return "unavailable"  # An unreadable composer is not an empty one.
            if value.strip():
                draft = True
        elif kind == "ControlType.Button" and _name(element.Current.Name) in BUSY:
            busy = True
    if draft:
        return "draft"
    if busy:
        return "busy"
    if not composers:
        return "unavailable"  # Cannot see the composer, so cannot promise it is empty.
    return "ready"


def _foreground(hwnd) -> bool:
    """True while the window we raised is still the one receiving keystrokes."""
    from ctypes import wintypes as w

    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetForegroundWindow.restype = w.HWND
    return user.GetForegroundWindow() == hwnd


def _lift(hwnd) -> bool:
    from ctypes import wintypes as w

    user = ctypes.WinDLL("user32", use_last_error=True)
    user.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [w.HWND]
    user.GetForegroundWindow.restype = w.HWND
    user.IsIconic.argtypes = [w.HWND]
    if user.IsIconic(hwnd):
        user.ShowWindow(hwnd, 9)  # SW_RESTORE
    user.SetForegroundWindow(hwnd)
    deadline = time.monotonic() + 1.2
    while user.GetForegroundWindow() != hwnd:
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)
    return True


class _Keyboard:
    """SendInput with explicit virtual keys; letters only, no layout guessing."""

    LETTERS = {"a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46, "g": 0x47,
               "h": 0x48, "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E,
               "o": 0x4F, "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54, "u": 0x55,
               "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A, " ": 0x20}
    VK_CONTROL, VK_SHIFT, VK_ESCAPE, VK_RETURN, VK_P = 0x11, 0x10, 0x1B, 0x0D, 0x50

    def __init__(self):
        from ctypes import wintypes as w

        class Key(ctypes.Structure):
            _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                        ("time", w.DWORD), ("extra", ctypes.c_size_t)]

        class Mouse(ctypes.Structure):
            _fields_ = [("x", w.LONG), ("y", w.LONG), ("data", w.DWORD), ("flags", w.DWORD),
                        ("time", w.DWORD), ("extra", ctypes.c_size_t)]

        class Payload(ctypes.Union):
            _fields_ = [("key", Key), ("mouse", Mouse)]

        class Input(ctypes.Structure):
            _fields_ = [("type", w.DWORD), ("payload", Payload)]

        self._types = (Input, Payload, Key)
        self._user = ctypes.WinDLL("user32", use_last_error=True)
        self._user.SendInput.argtypes = [w.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self._user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self._user.GetAsyncKeyState.restype = w.SHORT

    def _send(self, keys) -> bool:
        Input, Payload, Key = self._types
        events = [Input(1, Payload(key=Key(vk, 0, flags, 0, 0))) for vk, flags in keys]
        batch = (Input * len(events))(*events)
        return self._user.SendInput(len(events), batch, ctypes.sizeof(Input)) == len(events)

    def palette(self) -> bool:
        down, up = 0, 2
        modifiers = (self.VK_CONTROL, self.VK_SHIFT)
        if any(self._user.GetAsyncKeyState(vk) & 0x8000 for vk in modifiers):
            return False  # A held modifier would turn this into someone else's shortcut.
        return self._send([(vk, down) for vk in (*modifiers, self.VK_P)] +
                          [(vk, up) for vk in (self.VK_P, *reversed(modifiers))])

    def type(self, text: str) -> bool:
        keys = []
        for character in text.casefold():
            if character not in self.LETTERS:
                return False
            keys += [(self.LETTERS[character], 0), (self.LETTERS[character], 2)]
        return bool(keys) and self._send(keys)

    def enter(self) -> bool:
        return self._send([(self.VK_RETURN, 0), (self.VK_RETURN, 2)])

    def escape(self) -> bool:
        return self._send([(self.VK_ESCAPE, 0), (self.VK_ESCAPE, 2)])


def refresh() -> str:
    """'requested', 'not-running', 'draft', 'busy', 'unavailable' or 'unsupported'."""
    if sys.platform != "win32":
        return "unsupported"
    try:
        return _reload_window()
    except Exception:
        return "unavailable"


def _reload_window() -> str:
    found = _windows()
    if not found:
        return "not-running"
    if len(found) > 1:
        agents = [hwnd for hwnd, title in found if "agents" in (title or "").casefold()]
        if len(agents) != 1:
            return "unavailable"  # Never guess which window holds the list.
        hwnd = agents[0]
    else:
        hwnd = found[0][0]
    IntPtr, AutomationElement, *_ = _uia()
    root = AutomationElement.FromHandle(IntPtr(hwnd))
    state = _inspect(root)
    if state != "ready":
        return state
    keys = _Keyboard()
    if not _lift(hwnd):
        return "unavailable"
    root = AutomationElement.FromHandle(IntPtr(hwnd))
    state = _inspect(root)  # Re-check after raising: the user may have typed meanwhile.
    if state != "ready":
        return state
    if _palette_open(_names(root)):
        return "unavailable"  # A palette is already open; leave it to the user.
    if not keys.palette():
        return "unavailable"
    deadline = time.monotonic() + PALETTE_WAIT
    while time.monotonic() < deadline:
        if _palette_open(_names(root)):
            break
        time.sleep(0.05)
    else:
        return "unavailable"  # Nothing was typed, so nothing can be misplaced.
    if _inspect(root) != "ready":
        keys.escape()
        return "unavailable"
    if not _foreground(hwnd):
        return "unavailable"  # Focus moved away; typed keys would land elsewhere.
    if not keys.type("reload window"):
        keys.escape()
        return "unavailable"
    deadline = time.monotonic() + LIST_WAIT
    while time.monotonic() < deadline:
        listed = _names(root)
        if _reload_entry(listed):
            if not _foreground(hwnd):
                return "unavailable"  # Never confirm a command in another window.
            return "requested" if keys.enter() else "unavailable"
        if not _palette_open(listed):
            return "unavailable"  # The palette closed itself; never guess with Enter.
        time.sleep(0.05)
    keys.escape()
    return "unavailable"
