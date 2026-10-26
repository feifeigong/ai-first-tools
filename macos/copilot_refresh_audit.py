"""Frozen Mac AX guards and explicit reload action, against our own WebKit fixture."""
from __future__ import annotations
import json
import os
import platform
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch


def audit(report: Path) -> int:
    if sys.platform != 'darwin' or not getattr(sys, 'frozen', False):
        raise RuntimeError('Run the frozen Mac app')
    import webview
    import entry
    from core import copilot_refresh_macos as native
    from AppKit import NSApplication, NSMenu, NSMenuItem, NSRunningApplication
    from Foundation import NSObject
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    checks = {}; outcome = {'calls': 0}; installed = threading.Event()
    with tempfile.TemporaryDirectory(prefix='synthetic-mac-refresh-') as temporary:
        root = Path(temporary); (root/'ui').mkdir()
        (root/'ui/index.html').write_text('<!doctype html><html><meta charset="utf-8"><title>Synthetic guard</title>'
            '<body><div role="textbox" contenteditable="true" aria-label="Message">synthetic unsent draft</div></body></html>',encoding='utf-8')
        window = webview.create_window('合成窗口刷新保护检查',width=480,height=300)

        class AIFirstSyntheticReloadTarget(NSObject):
            def reloadSynthetic_(self, sender):
                outcome['calls'] += 1
                BrowserView.instances[window.uid].webview.reload()

        target = AIFirstSyntheticReloadTarget.alloc().init()

        def attach(window):
            with patch.object(entry, 'ROOT', root): entry.load_bundled_content(window)
            def add_menu():
                submenu = NSMenu.alloc().initWithTitle_('Synthetic window')
                reload = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Reload Window','reloadSynthetic:','')
                reload.setTarget_(target); submenu.addItem_(reload)
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Synthetic window',None,'')
                item.setSubmenu_(submenu); NSApplication.sharedApplication().mainMenu().addItem_(item)
                installed.set()
            AppHelper.callAfter(add_menu)

        def require(value):
            if not value: raise AssertionError('Native refresh fixture assertion failed')

        def check():
            failure = None
            try:
                require(installed.wait(10)); require(window.events.loaded.wait(25))
                window.show(); window.restore()
                app = NSRunningApplication.runningApplicationWithProcessIdentifier_(os.getpid())
                with patch.object(native, '_application', return_value=app):
                    outcome['draftState']=native.refresh(busy=lambda:'idle')
                    require(outcome['draftState'] == 'draft')
                    require(outcome['calls'] == 0); checks['nativeDraftPreserved'] = True
                    window.evaluate_js('document.querySelector("[role=textbox]").textContent=""')
                    with native.Accessibility() as ax:
                        application = ax.ax.AXUIElementCreateApplication(os.getpid()); ax.owned.append(application)
                        ax.ax.AXUIElementSetMessagingTimeout(application,.3)
                        windows = ax.children(application,'AXWindows')
                        require(len(windows)==1 and native._draft(ax,windows[0]) is False)
                    checks['nativeEmptyComposerRecognized'] = True
                    outcome['busyState']=native.refresh(busy=lambda:'busy')
                    require(outcome['busyState'] == 'busy')
                    require(outcome['calls'] == 0); checks['nativeBusyPreserved'] = True
                    outcome['reloadState']=native.refresh(busy=lambda:'idle')
                    require(outcome['reloadState'] == 'requested')
                    deadline = time.monotonic()+10
                    while not outcome['calls'] and time.monotonic()<deadline: time.sleep(.05)
                    require(outcome['calls']==1); checks['explicitNativeReloadExecuted'] = True
                    deadline = time.monotonic()+10
                    while time.monotonic()<deadline:
                        if window.evaluate_js('document.querySelector("[role=textbox]").textContent') == 'synthetic unsent draft': break
                        time.sleep(.1)
                    require(window.evaluate_js('document.querySelector("[role=textbox]").textContent') == 'synthetic unsent draft')
                    checks['actualWebKitDocumentReloaded'] = True
                    require(not app.isTerminated()); checks['sameApplicationKeptRunning'] = True
            except Exception as error:
                failure = type(error).__name__
            finally:
                result={'passed':failure is None and len(checks)==6,'checks':checks,'errorType':failure,
                    'architecture':platform.machine(),'version':entry.version_info(),'host':platform.system(),'frozen':True,
                    'modelRequests':0,'officialLoggedInSidebarVerified':False,
                    'nativeStates':{key:value for key,value in outcome.items() if key.endswith('State')},
                    'scope':'Actual frozen Cocoa/WebKit/AX controls; only our synthetic editor and labelled native reload menu. Vendor identity discovery and logged-in Copilot sidebar remain separate.'}
                report.parent.mkdir(parents=True,exist_ok=True)
                report.write_text(json.dumps(result,indent=2),encoding='utf-8')
                outcome['passed']=result['passed']; window.destroy()

        window.events.before_show += attach
        entry.start_cocoa(check)
    return 0 if outcome.get('passed') else 1
