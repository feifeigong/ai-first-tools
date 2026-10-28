"""Actual frozen Mac notifier checks, exclusively in marked synthetic temporary data."""
from __future__ import annotations
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import reset_notices as notices


class SyntheticClient:
    def __init__(self, root): self.root = root
    def request(self, operation='snapshot', **arguments):
        state = notices.read_json(self.root / 'settings.json')
        result = {'enabled': state['enabled'], 'events': []}
        if operation == 'take' and not (self.root / 'claimed.json').exists():
            notices.write_json(self.root / 'claimed.json', {'claimed': True})
            result['alert'] = {'id': '2113162413008884099', 'url': 'https://x.com/thsottiaux/status/2113162413008884099',
                'summary': 'Codex 额度重置预告', 'description': '这是一条隔离合成提醒。',
                'timeText': '北京时间 10 月 23 日 02:00 前', 'timeNote': '不联网，不操作真实额度。'}
        return result


def monitor(root: Path):
    notices.Monitor.check_audit_root(root, root / 'state')
    return notices.Monitor(directory=root / 'state', client=SyntheticClient(root), audit_root=root)


def monitor_child(root: Path):
    deadline = time.monotonic() + 120
    def notify(alert):
        notices.write_json(root / 'delivered.json', alert)
        def configure(dialog):
            from AppKit import NSModalPanelRunLoopMode
            from Foundation import NSRunLoop, NSTimer
            def visible(timer):
                notices.write_json(root / 'popup-visible.json', {'visible': bool(dialog.window().isVisible())})
            timer = NSTimer.timerWithTimeInterval_repeats_block_(.2, False, visible)
            NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSModalPanelRunLoopMode)
        notices.show_notice(alert, configure)
    return notices.background_main(monitor(root), notify,
        stopped=lambda: not root.exists() or time.monotonic() >= deadline)


def launcher_child(root: Path):
    monitor(root).ensure()
    return 0


def audit(report: Path) -> int:
    if sys.platform != 'darwin' or not getattr(sys, 'frozen', False):
        raise RuntimeError('Run this audit with the actual frozen Mac application')
    checks = {}
    def require(value):
        if not value: raise AssertionError('Synthetic notifier assertion failed')
    def wait(test):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                if test(): return
            except (notices.NoticeError, OSError, ValueError): pass
            time.sleep(.1)
        require(False)
    failure = None
    with tempfile.TemporaryDirectory(prefix='ai-first-reset-audit-') as temporary:
        root = Path(temporary).resolve()
        notices.write_json(root / 'audit.json', {'scope': 'reset-monitor-audit', 'root': str(root)})
        notices.write_json(root / 'settings.json', {'enabled': True})
        service = monitor(root)
        try:
            actual = notices.Client(root / 'rule-state')
            first = actual.request()
            require(first['enabled'] and first['events'] == [] and not actual.directory.exists())
            require(not actual.request('enabled', enabled=False)['enabled'])
            require(not actual.request('refresh', manual=True)['enabled'])
            require(actual.request('enabled', enabled=True)['enabled'])
            checks['frozenSharedRuleBridgeAndSwitch'] = True
            environment = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
            launcher = subprocess.run([sys.executable, '--reset-launcher-audit', str(root)], env=environment, timeout=20)
            require(launcher.returncode == 0)
            wait(lambda: service.live_owner() is not None and (root / 'delivered.json').is_file()
                and (root / 'popup-visible.json').is_file() and notices.read_json(root / 'popup-visible.json')['visible'])
            first_owner = service.live_owner()
            with patch.dict(os.environ, {'TZ':'Asia/Shanghai'}):
                require(service.live_owner() == first_owner)
            checks['independentAfterLauncherExit'] = True
            service.ensure()
            require(service.live_owner() == first_owner)
            checks['singleOwnedNotifier'] = True
            from AppKit import NSApplication, NSWindow, NSWindowStyleMaskTitled, NSBackingStoreBuffered, NSModalPanelRunLoopMode
            from Foundation import NSRunLoop, NSDate, NSTimer
            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(1)
            window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(((0, 0), (400, 140)), NSWindowStyleMaskTitled, NSBackingStoreBuffered, False)
            window.setReleasedWhenClosed_(False)
            window.setTitle_('AI一手 · 合成窗口关闭检查')
            window.makeKeyAndOrderFront_(None)
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(.2))
            require(window.isVisible())
            window.close()
            require(not window.isVisible() and service.live_owner() == first_owner)
            checks['nativeWindowClosePreservesNotifier'] = True
            alert = notices.read_json(root / 'delivered.json')
            dialog_visible = []
            def configure(dialog):
                require(str(dialog.messageText()) == alert['summary'])
                require([str(button.title()) for button in dialog.buttons()] == ['知道了', '查看原帖', '关闭自动用卡'])
                def abort(timer):
                    dialog_visible.append(bool(dialog.window().isVisible()))
                    app.abortModal()
                timer = NSTimer.timerWithTimeInterval_repeats_block_(.25, False, abort)
                NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSModalPanelRunLoopMode)
            with patch('core.common.open_external', side_effect=AssertionError('No unrequested navigation')), \
                 patch('auto_resume.Controller.action', side_effect=AssertionError('No automatic pause')):
                notices.show_notice(alert, configure)
            require(dialog_visible == [True])
            checks['nativeChinesePopupHasNoAutomaticResumeAction'] = True
            foreign = notices.Monitor(root / 'another' / notices.APP, root / 'state', SyntheticClient(root), root)
            foreign.stop_owned()
            require(service.live_owner() == first_owner)
            checks['anotherPackageCannotStopNotifier'] = True
            service.stop_owned('update')
            require(service.live_owner() is None and service.receipt.exists())
            service.restore()
            wait(lambda: service.live_owner() is not None)
            require(not service.receipt.exists())
            checks['cooperativeUpdateRestoresNotifier'] = True
            service.stop_owned('uninstall')
            require(service.live_owner() is None and (root / 'settings.json').exists())
            checks['stopPreservesPreferences'] = True
        except Exception as error:
            failure = type(error).__name__
        finally:
            try: service.stop_owned('uninstall')
            except (notices.NoticeError, OSError, ValueError): pass
    passed = failure is None and len(checks) == 8 and all(checks.values())
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'passed': passed, 'checks': checks, 'errorType': failure,
        'architecture': platform.machine(), 'version': json.loads((Path(sys._MEIPASS) / 'version.json').read_text()),
        'syntheticOnly': True, 'modelRequests': 0,
        'scope': 'Actual native window, popup and owned frozen processes; synthetic public posts; no online request'}, ensure_ascii=False), encoding='utf-8')
    return 0 if passed else 1
