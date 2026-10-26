"""Mac window refresh through an explicitly labelled native reload command.

Never send a guessed reload shortcut, quit an app, use developer tools, or read tokens.
The command palette is considered only after all visible editors are empty.
"""
from __future__ import annotations

import ctypes
import subprocess
import time
from pathlib import Path

BUNDLE = 'com.github.githubapp'
TEAM = 'VEKTX9H2N7'
RELOAD = {'reload', 'reload window', 'reload app', 'reload application', 'reload main window',
          'developer: reload window', '重新加载', '重新加载窗口', '重新载入窗口'}
PALETTE = {'command palette', 'command menu', '命令面板', '命令菜单'}
VIEW_MENUS = {'view', 'window', 'developer', 'debug', '视图', '窗口', '开发者', '调试'}
LEAF_ROLES = {'AXStaticText', 'AXImage', 'AXLink', 'AXButton', 'AXCheckBox', 'AXRadioButton',
              'AXScrollBar', 'AXSlider', 'AXTextArea', 'AXTextField', 'AXSearchField', 'AXComboBox'}
_prompted = False


class Unavailable(RuntimeError):
    pass


class Accessibility:
    def __init__(self):
        self.ax = ctypes.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
        self.cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        pointer, integer = ctypes.c_void_p, ctypes.c_long
        functions = {
            'CFStringCreateWithCString': (pointer, [pointer, ctypes.c_char_p, ctypes.c_uint32]),
            'CFStringGetCString': (ctypes.c_bool, [pointer, pointer, integer, ctypes.c_uint32]),
            'CFGetTypeID': (ctypes.c_ulong, [pointer]), 'CFStringGetTypeID': (ctypes.c_ulong, []),
            'CFArrayGetTypeID': (ctypes.c_ulong, []), 'CFArrayGetCount': (integer, [pointer]),
            'CFArrayGetValueAtIndex': (pointer, [pointer, integer]), 'CFRelease': (None, [pointer]),
            'CFEqual': (ctypes.c_bool, [pointer, pointer]),
        }
        for name, (result, args) in functions.items():
            function = getattr(self.cf, name); function.restype = result; function.argtypes = args
        self.ax.AXIsProcessTrusted.restype = ctypes.c_bool
        self.ax.AXUIElementCreateApplication.restype = pointer
        self.ax.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
        self.ax.AXUIElementCopyAttributeValue.argtypes = [pointer, pointer, ctypes.POINTER(pointer)]
        self.ax.AXUIElementSetAttributeValue.argtypes = [pointer, pointer, pointer]
        self.ax.AXUIElementPerformAction.argtypes = [pointer, pointer]
        self.ax.AXUIElementSetMessagingTimeout.argtypes = [pointer, ctypes.c_float]
        self.owned = []
        self.deadline = time.monotonic() + 5

    def __enter__(self): return self

    def __exit__(self, *_):
        for value in reversed(self.owned):
            if value: self.cf.CFRelease(value)

    def string(self, text):
        value = self.cf.CFStringCreateWithCString(None, text.encode(), 0x08000100)
        if not value: raise Unavailable()
        self.owned.append(value); return value

    def attribute(self, element, name):
        if not element or time.monotonic() > self.deadline: raise Unavailable()
        value = ctypes.c_void_p()
        error = self.ax.AXUIElementCopyAttributeValue(element, self.string(name), ctypes.byref(value))
        if error in (-25205, -25212): return None  # Unsupported attribute / no value.
        if error: raise Unavailable(f'attribute_{name}_{error}')
        self.owned.append(value.value); return value.value

    def text(self, value):
        if not value or self.cf.CFGetTypeID(value) != self.cf.CFStringGetTypeID(): return None
        buffer = ctypes.create_string_buffer(8192)
        if not self.cf.CFStringGetCString(value, buffer, len(buffer), 0x08000100): raise Unavailable()
        return buffer.value.decode('utf-8')

    def label(self, element):
        return self.text(self.attribute(element, 'AXTitle')) or self.text(self.attribute(element, 'AXDescription')) or ''

    def children(self, element, name='AXChildren'):
        value = self.attribute(element, name)
        if value is None: return []
        if self.cf.CFGetTypeID(value) != self.cf.CFArrayGetTypeID(): raise Unavailable()
        count = self.cf.CFArrayGetCount(value)
        if count > 2000: raise Unavailable()
        return [self.cf.CFArrayGetValueAtIndex(value, i) for i in range(count)]

    def walk(self, element):
        pending = [(element, ())]; count = 0
        while pending:
            current, parents = pending.pop(); count += 1
            if count > 3000 or len(parents) > 25: raise Unavailable()
            role = self.text(self.attribute(current, 'AXRole'))
            yield current, role, parents
            if role not in LEAF_ROLES:
                try:
                    children = self.children(current)
                except Unavailable as error:
                    # AppKit leaf menu items report AX failure for AXChildren.
                    # Editors expose their complete value and are leaves above;
                    # unknown window/group failures still fail closed.
                    if role != 'AXMenuItem' or str(error) != 'attribute_AXChildren_-25200': raise
                    children = []
                pending.extend((child, (*parents, current)) for child in reversed(children))

    def press(self, element):
        if self.ax.AXUIElementPerformAction(element, self.string('AXPress')): raise Unavailable()

    def set_text(self, element, value):
        if self.ax.AXUIElementSetAttributeValue(element, self.string('AXValue'), self.string(value)): raise Unavailable()

    def request_permission_once(self):
        global _prompted
        if _prompted: return
        _prompted = True
        import objc
        from Foundation import NSDictionary
        options = NSDictionary.dictionaryWithObject_forKey_(True, 'AXTrustedCheckOptionPrompt')
        query = self.ax.AXIsProcessTrustedWithOptions
        query.argtypes = [ctypes.c_void_p]; query.restype = ctypes.c_bool
        query(objc.pyobjc_id(options))


def _name(text):
    return (text or '').casefold().strip().rstrip('….').strip()


def _application():
    from AppKit import NSRunningApplication
    applications = list(NSRunningApplication.runningApplicationsWithBundleIdentifier_(BUNDLE))
    if not applications: return None
    if len(applications) != 1: raise Unavailable()
    app = applications[0]
    bundle = Path(str(app.bundleURL().path()))
    executable = Path(str(app.executableURL().path()))
    if not bundle.is_absolute() or bundle.is_symlink() or executable != bundle / 'Contents/MacOS/github': raise Unavailable()
    requirement = f'anchor apple generic and identifier "{BUNDLE}" and certificate leaf[subject.OU] = "{TEAM}"'
    result = subprocess.run(['/usr/bin/codesign', '--verify', '--strict', '-R', requirement, str(bundle)],
                            capture_output=True, timeout=8)
    if result.returncode: raise Unavailable()
    return app


def _draft(ax, window):
    web = False
    for element, role, _ in ax.walk(window):
        if role == 'AXWebArea': web = True
        if role == 'AXButton' and _name(ax.label(element)).startswith(('remove attachment', 'remove image', '移除附件', '删除附件', '移除图片')):
            return True
        if role in {'AXTextArea', 'AXTextField', 'AXSearchField', 'AXComboBox'}:
            text = ax.text(ax.attribute(element, 'AXValue'))
            if text is None: raise Unavailable('editor_value_unavailable')
            if text.strip(): return True
    if not web: raise Unavailable('web_area_unavailable')
    return False


def _reload_command(ax, root):
    """Only exact user-visible reload names; no restart, retry or run commands."""
    for element, role, parents in ax.walk(root):
        if role not in {'AXMenuItem', 'AXButton', 'AXRow'}: continue
        if _name(ax.label(element)) in RELOAD: return element
    return None


def _view_menus(ax, menubar):
    # Never mistake a document called "Reload Window" in Apple's Recent Items
    # or File menu for an application command.
    return [menu for menu in ax.children(menubar) if _name(ax.label(menu)) in VIEW_MENUS]


def _reload_menu(ax, menubar):
    return next((command for menu in _view_menus(ax, menubar)
                 if (command := _reload_command(ax, menu)) is not None), None)


def _palette_menu(ax, menubar):
    return next((element for menu in _view_menus(ax, menubar) for element, role, _ in ax.walk(menu)
                 if role == 'AXMenuItem' and _name(ax.label(element)) in PALETTE), None)


def _dismiss_palette(ax, target, container, field, app):
    """Dismiss only the palette we opened, without changing a user's new input."""
    try:
        current = ax.attribute(target, 'AXFocusedUIElement')
        if not current or not ax.cf.CFEqual(current, field): return
        if ax.text(ax.attribute(field, 'AXValue')) not in {'', 'reload'}: return
        for element, role, _ in ax.walk(container):
            if role == 'AXButton' and _name(ax.label(element)) in {'close', 'cancel', '关闭', '取消'}:
                ax.press(element); return
        # Escape only dismisses this verified, focused palette. It is never
        # posted to a composer or used as an unverified refresh shortcut.
        from AppKit import NSWorkspace
        if NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier() != app.processIdentifier(): return
        quartz = ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        quartz.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_ushort, ctypes.c_bool]
        quartz.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
        quartz.CGEventPostToPid.argtypes = [ctypes.c_int, ctypes.c_void_p]
        for down in (True, False):
            event = quartz.CGEventCreateKeyboardEvent(None, 53, down)
            if not event: return
            try: quartz.CGEventPostToPid(app.processIdentifier(), event)
            finally: ax.cf.CFRelease(event)
    except (Unavailable, OSError, ValueError):
        pass  # Never disturb an element whose ownership/focus has changed.


def refresh(*, passive=False, busy):
    try:
        app = _application()
        if app is None: return 'not-running'
        with Accessibility() as ax:
            if not ax.ax.AXIsProcessTrusted():
                ax.request_permission_once()
                return 'permission-required'
            target = ax.ax.AXUIElementCreateApplication(app.processIdentifier()); ax.owned.append(target)
            ax.ax.AXUIElementSetMessagingTimeout(target, .3)
            windows = ax.children(target, 'AXWindows')
            if len(windows) != 1: return 'unavailable'
            if _draft(ax, windows[0]): return 'draft'
            state = busy()
            if state != 'idle': return state
            menu = ax.attribute(target, 'AXMenuBar')
            if menu is None: return 'unavailable'
            reload = _reload_menu(ax, menu)
            palette = _palette_menu(ax, menu) if reload is None else None
            if reload is None and palette is None: return 'unavailable'
            # Only bring forward a verified empty, idle window. Never use keys.
            app.activateWithOptions_(2)
            from AppKit import NSWorkspace
            deadline = time.monotonic() + 1
            while NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier() != app.processIdentifier():
                if time.monotonic() >= deadline: return 'unavailable'
                time.sleep(.02)
            if _draft(ax, windows[0]): return 'draft'
            state = busy()
            if state != 'idle': return state
            if reload is not None:
                ax.press(reload); return 'requested'
            ax.press(palette)
            time.sleep(.15)
            focused = ax.attribute(target, 'AXFocusedUIElement')
            role = ax.text(ax.attribute(focused, 'AXRole'))
            if role not in {'AXTextField', 'AXSearchField', 'AXComboBox'}: return 'unavailable'
            if ax.text(ax.attribute(focused, 'AXValue')) != '': return 'unavailable'
            container = focused
            for _ in range(12):
                container = ax.attribute(container, 'AXParent')
                if container is None: return 'unavailable'
                role = ax.text(ax.attribute(container, 'AXRole'))
                subrole = ax.text(ax.attribute(container, 'AXSubrole'))
                if (role == 'AXDialog' or subrole in {'AXDialog', 'AXApplicationDialog'}) and _name(ax.label(container)) in PALETTE: break
            else: return 'unavailable'
            # The verified palette search is separate from the chat composer.
            performed = False
            try:
                ax.set_text(focused, 'reload')
                time.sleep(.15)
                reload = _reload_command(ax, container)
                if reload is None: return 'unavailable'
                state = busy()
                if state != 'idle': return state
                if app.isTerminated(): return 'unavailable'
                ax.press(reload); performed = True
                return 'requested'
            finally:
                if not performed: _dismiss_palette(ax, target, container, focused, app)
    except (Unavailable, OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError, ImportError):
        return 'unavailable'
