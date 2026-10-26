"""Native AX integration against a separate, disposable synthetic Cocoa app."""
from __future__ import annotations
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch


def _write(path, value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value),encoding='utf-8');temporary.replace(path)


def _root(root):
    if root.is_symlink() or (root/'audit.json').is_symlink() or (root/'ui').is_symlink():
        raise ValueError('Synthetic fixture link rejected')
    root=root.resolve()
    if (not root.name.startswith('ai-first-refresh-audit-')
            or not root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            or json.loads((root/'audit.json').read_text()) != {'scope':'native-refresh-fixture-v1','root':str(root)}):
        raise ValueError('Dedicated synthetic fixture required')
    return root


def fixture_child(root: Path) -> int:
    root=_root(root)
    import webview
    import entry
    from AppKit import NSApplication, NSMenu, NSMenuItem
    from Foundation import NSObject
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView
    window=webview.create_window('合成窗口刷新保护检查',width=480,height=300)
    outcome={'calls':0,'loads':0}; installed=threading.Event()

    class AIFirstSyntheticReloadTarget(NSObject):
        def reloadSynthetic_(self, sender):
            outcome['calls']+=1;_write(root/'reload.json',{'count':outcome['calls']})
            BrowserView.instances[window.uid].webview.reload()

    target=AIFirstSyntheticReloadTarget.alloc().init()

    def attach(window):
        with patch.object(entry,'ROOT',root): entry.load_bundled_content(window)

    def add_menu():
        submenu=NSMenu.alloc().initWithTitle_('Developer');submenu.setAutoenablesItems_(False)
        reload=NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Reload Window','reloadSynthetic:','')
        reload.setTarget_(target);reload.setEnabled_(True);submenu.addItem_(reload)
        item=NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Developer',None,'')
        item.setSubmenu_(submenu);NSApplication.sharedApplication().mainMenu().addItem_(item)
        installed.set()

    def loaded(): outcome['loads']+=1

    def worker():
        try:
            if not window.events.loaded.wait(25): return
            AppHelper.callAfter(add_menu)
            if not installed.wait(10): return
            window.show();window.restore();_write(root/'ready.json',{'pid':os.getpid()})
            last=0;deadline=time.monotonic()+110
            while root.exists() and time.monotonic()<deadline:
                command=root/'action.json'
                if command.is_file():
                    value=json.loads(command.read_text())
                    if value['id']>last:
                        last=value['id']
                        if value['action']=='stop': break
                        if value['action']=='clear':window.evaluate_js('document.querySelector("[role=textbox]").textContent=""')
                        else:raise ValueError('Unknown synthetic action')
                value=window.evaluate_js('document.querySelector("[role=textbox]").textContent')
                _write(root/'state.json',{'draft':value=='synthetic unsent draft','loads':outcome['loads']})
                time.sleep(.1)
        finally: window.destroy()

    window.events.before_show+=attach;window.events.loaded+=loaded
    entry.start_cocoa(worker)
    return 0


def audit(report: Path, *, frozen_required: bool = True) -> int:
    if sys.platform!='darwin' or frozen_required and not getattr(sys,'frozen',False):
        raise RuntimeError('Run the frozen Mac app')
    import entry
    from AppKit import NSRunningApplication
    from core import copilot_refresh_macos as native
    checks={};outcome={'trace':[]};failure=None
    with tempfile.TemporaryDirectory(prefix='ai-first-refresh-audit-') as temporary:
        root=Path(temporary).resolve();(root/'ui').mkdir()
        _write(root/'audit.json',{'scope':'native-refresh-fixture-v1','root':str(root)})
        (root/'ui/index.html').write_text('<!doctype html><html><meta charset="utf-8"><title>Synthetic guard</title>'
            '<body><div role="textbox" contenteditable="true" aria-label="Message">synthetic unsent draft</div></body></html>',encoding='utf-8')
        command=([sys.executable,'--copilot-refresh-child',str(root)] if getattr(sys,'frozen',False) else
            [sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/probe_refresh_guard.py'),'--child',str(root)])
        child=subprocess.Popen(command,env={**os.environ,'PYINSTALLER_RESET_ENVIRONMENT':'1'},
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def require(value):
            if not value: raise AssertionError('Native external fixture assertion failed')
        def wait(probe):
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                require(child.poll() is None)
                try:
                    if probe(): return
                except (native.Unavailable,FileNotFoundError,json.JSONDecodeError): pass
                time.sleep(.1)
            require(False)
        def composer():
            with native.Accessibility() as ax:
                app=ax.ax.AXUIElementCreateApplication(child.pid);ax.owned.append(app)
                ax.ax.AXUIElementSetMessagingTimeout(app,.3)
                windows=ax.children(app,'AXWindows')
                if len(windows)!=1: raise native.Unavailable('window_count')
                return native._draft(ax,windows[0])
        try:
            wait(lambda:(root/'ready.json').is_file());wait(lambda:composer() is True)
            app=NSRunningApplication.runningApplicationWithProcessIdentifier_(child.pid)
            with patch.object(native,'_application',return_value=app),patch.object(native,'_phase',side_effect=outcome['trace'].append):
                outcome['draftState']=native.refresh(busy=lambda:'idle')
                require(outcome['draftState']=='draft');require(not(root/'reload.json').exists())
                checks['nativeDraftPreserved']=True
                _write(root/'action.json',{'id':1,'action':'clear'});wait(lambda:composer() is False)
                checks['nativeEmptyComposerRecognized']=True
                outcome['busyState']=native.refresh(busy=lambda:'busy')
                require(outcome['busyState']=='busy');require(not(root/'reload.json').exists())
                checks['nativeBusyPreserved']=True
                outcome['reloadState']=native.refresh(busy=lambda:'idle');require(outcome['reloadState']=='requested')
                wait(lambda:(root/'reload.json').exists());require(json.loads((root/'reload.json').read_text())['count']==1)
                checks['explicitNativeReloadExecuted']=True
                wait(lambda:json.loads((root/'state.json').read_text())['loads']>=2 and composer() is True)
                checks['actualWebKitDocumentReloaded']=True
                require(child.poll() is None and not app.isTerminated());checks['sameApplicationKeptRunning']=True
        except Exception as error:
            failure=type(error).__name__;outcome['errorCode']=str(error)[:120]
        finally:
            _write(root/'action.json',{'id':2,'action':'stop'})
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:failure='FixtureCloseTimeout'
    result={'passed':failure is None and len(checks)==6,'checks':checks,'errorType':failure,
        'architecture':platform.machine(),'version':entry.version_info(),'host':platform.system(),'frozen':bool(getattr(sys,'frozen',False)),
        'modelRequests':0,'officialLoggedInSidebarVerified':False,'errorCode':outcome.get('errorCode'),
        'nativePhases':outcome['trace'],'nativeStates':{key:value for key,value in outcome.items() if key.endswith('State')},
        'scope':'Actual external synthetic Cocoa/WebKit process, native AX guards and labelled reload; vendor identity and logged-in Copilot sidebar remain separate.'}
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1
