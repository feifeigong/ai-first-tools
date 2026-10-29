"""Mac host for the exact Windows reset rules, with an independently owned notifier."""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

WATCH = '--reset-monitor'
FORMAT = 'ai-first-reset-monitor-v1'
APP = 'AI一手工具工作台.app'
APP_NAMES = {APP, 'AI一手工具工作台预览.app'}


class NoticeError(RuntimeError):
    pass


def plain(path: Path):
    if any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in (path, *path.parents)):
        raise NoticeError('提醒设置的位置发生变化，已保留原文件。')


def read_json(path: Path):
    plain(path)
    with path.open(encoding='utf-8') as stream:
        raw = stream.read(16385)
    if len(raw) > 16384: raise NoticeError('提醒设置暂时无法读取。')
    return json.loads(raw)


def write_json(path: Path, value):
    plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Lease:
    def __init__(self, path: Path):
        self.path, self.stream = path, None

    def acquire(self):
        plain(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open('a+b')
        if not self.path.stat().st_size: stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            if error.errno in (11, 13, 35, 36): return False
            raise
        self.stream = stream
        return True

    def close(self):
        if self.stream:
            self.stream.close()
            self.stream = None


def process_identity(pid: int):
    from codex_auto_resume.watch_control import _darwin_process_start, darwin_command, WatchStateError
    try:
        command = darwin_command(pid)
        started = _darwin_process_start(pid)
    except subprocess.CalledProcessError:
        return None
    except (OSError, subprocess.SubprocessError, WatchStateError) as error:
        raise NoticeError('暂时无法确认提醒状态。') from error
    if started is None or not command: return None
    return {'started': started, 'command': command}


def default_directory():
    from core.common import appdata
    root = appdata() / 'AI一手工具工作台'
    if getattr(sys, 'frozen', False):
        metadata = json.loads((Path(sys._MEIPASS) / 'version.json').read_text(encoding='utf-8'))
        if metadata.get('developmentPreview') is True: root = root / 'memory-preview'
    return root / 'reset-notices'


class Client:
    def __init__(self, directory: Path | None = None, command: list[str] | None = None):
        self.directory = directory or default_directory()
        if command is None:
            if getattr(sys, 'frozen', False):
                command = [str(Path(sys._MEIPASS) / 'reset-news/AI.First.ResetBridge')]
            else:
                dll = Path(__file__).parent / 'ResetBridge/bin/Release/net8.0/AI.First.ResetBridge.dll'
                command = ['dotnet', str(dll)]
        self.command = command

    def request(self, operation='snapshot', **arguments):
        if operation not in {'snapshot', 'refresh', 'enabled', 'take'}:
            raise NoticeError('未知的提醒操作。')
        if operation == 'enabled' and not isinstance(arguments.get('enabled'), bool):
            raise NoticeError('提醒开关状态不正确。')
        plain(self.directory)
        try:
            completed = subprocess.run([*self.command, '--state-directory', str(self.directory.absolute())],
                input=json.dumps({'operation': operation, **arguments}) + '\n', capture_output=True,
                encoding='utf-8', timeout=60, creationflags=0x08000000 if sys.platform == 'win32' else 0)
        except (OSError, subprocess.SubprocessError) as error:
            raise NoticeError('重置消息暂时无法更新，请稍后再试。') from error
        if len(completed.stdout) > 1024 * 1024: raise NoticeError('提醒消息暂时无法读取。')
        try: result = json.loads(completed.stdout)
        except ValueError as error: raise NoticeError('提醒消息暂时无法读取。') from error
        if not isinstance(result, dict) or completed.returncode or result.get('error'):
            raise NoticeError('重置消息暂时无法更新，请稍后再试。')
        if not isinstance(result.get('enabled'), bool) or not isinstance(result.get('events'), list):
            raise NoticeError('提醒消息格式暂时无法识别。')
        return result

    def open_post(self, identity: str):
        if not re.fullmatch(r'[1-9][0-9]{14,19}', identity): raise NoticeError('找不到这条重置消息。')
        result = self.request()
        event = next((e for e in result['events'] if e.get('id') == identity), None)
        if event is None or event.get('url') != 'https://x.com/thsottiaux/status/' + identity:
            raise NoticeError('这条消息的来源暂时无法核对。')
        from core.common import open_external
        open_external(event['url'])
        return {'ok': True}


class Monitor:
    def __init__(self, bundle: Path | None = None, directory: Path | None = None, client: Client | None = None, audit_root: Path | None = None):
        self.bundle = (bundle or Path(sys.executable).parents[2]).resolve()
        self.executable = self.bundle / 'Contents/MacOS/AI First Tools'
        self.directory = directory or default_directory()
        self.client = client or Client(self.directory)
        self.owner_path = self.directory / 'monitor-owner.json'
        self.stop_path = self.directory / 'monitor-stop.json'
        self.receipt = self.directory / 'monitor-update.json'
        self.arguments = [WATCH]
        if audit_root is not None:
            self.check_audit_root(audit_root, self.directory)
            self.arguments = ['--reset-monitor-audit', str(audit_root)]

    @staticmethod
    def check_audit_root(root: Path, directory: Path):
        import tempfile
        plain(root)
        if (not root.is_absolute() or not root.name.startswith('ai-first-reset-audit-')
                or not root.is_relative_to(Path(tempfile.gettempdir()).resolve())
                or directory != root / 'state'
                or read_json(root / 'audit.json') != {'scope': 'reset-monitor-audit', 'root': str(root)}):
            raise NoticeError('提醒检查只能使用专用的临时目录。')

    def live_owner(self):
        if not self.owner_path.exists(): return None
        owner = read_json(self.owner_path)
        if not isinstance(owner, dict) or not isinstance(owner.get('executable'), str):
            raise NoticeError('提醒状态暂时无法核对，已保留现有设置。')
        executable = Path(owner.get('executable', ''))
        if (owner.get('format') != FORMAT or type(owner.get('pid')) is not int or owner['pid'] <= 0
                or not isinstance(owner.get('token'), str) or not re.fullmatch(r'[0-9a-f]{32}', owner['token'])
                or not executable.is_absolute() or executable.name != 'AI First Tools'
                or executable.parent.name != 'MacOS' or executable.parent.parent.name != 'Contents'
                or executable.parent.parent.parent.name not in APP_NAMES):
            raise NoticeError('提醒状态暂时无法核对，已保留现有设置。')
        actual = process_identity(owner['pid'])
        if actual is None: return None
        if actual['started'] != owner.get('started'): return None  # A reused PID is no longer our notifier.
        arguments = owner.get('arguments', [WATCH])
        if arguments != [WATCH]:
            if not isinstance(arguments, list) or len(arguments) != 2 or arguments[0] != '--reset-monitor-audit' or not isinstance(arguments[1], str):
                raise NoticeError('提醒状态暂时无法核对。')
            self.check_audit_root(Path(arguments[1]), self.directory)
        if actual != {'started': owner.get('started'), 'command': ' '.join([str(executable), *arguments])}:
            raise NoticeError('提醒状态暂时无法核对，已保留现有设置。')
        return owner

    def ensure(self):
        if not self.client.request()['enabled']: return
        if self.live_owner(): return
        lease = Lease(self.directory / 'monitor.lock')
        if not lease.acquire(): return  # A second launch is still establishing ownership.
        lease.close()
        if not self.executable.is_file(): raise NoticeError('提醒组件不完整，请使用完整工具箱。')
        env = os.environ.copy()
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        subprocess.Popen([str(self.executable), *self.arguments], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=env, start_new_session=True, close_fds=True)

    def stop_owned(self, reason='update'):
        if reason not in {'update', 'uninstall'}: raise NoticeError('未知的提醒交接操作。')
        owner = self.live_owner()
        if owner is None or Path(owner['executable']) != self.executable: return
        if reason == 'update': write_json(self.receipt, {'executable': str(self.executable), 'restart': True})
        if self.live_owner() != owner: raise NoticeError('提醒状态刚发生变化，请稍后重试。')
        write_json(self.stop_path, {'token': owner['token'], 'executable': owner['executable']})
        deadline = time.monotonic() + 60
        expected = {'started': owner['started'], 'command': ' '.join([owner['executable'], *owner.get('arguments', [WATCH])])}
        while True:
            current = self.live_owner()
            physical = process_identity(owner['pid'])
            if current != owner and physical != expected: return
            if time.monotonic() >= deadline: raise NoticeError('提醒正在结束本次检查，请稍后重试。')
            time.sleep(.2)

    def restore(self):
        if self.receipt.is_file():
            receipt = read_json(self.receipt)
            if receipt.get('executable') != str(self.executable): return
            if receipt.get('restart') is True: self.ensure()
            self.receipt.unlink()

    def stopped(self, owner):
        if not self.bundle.exists(): return True
        if not self.stop_path.exists(): return False
        value = read_json(self.stop_path)
        return value == {'token': owner['token'], 'executable': owner['executable']}

    def run(self, notify, stopped=lambda: False, wait=time.sleep):
        lease = Lease(self.directory / 'monitor.lock')
        if not lease.acquire(): return 0
        owner = None
        try:
            if self.live_owner(): return 0
            identity = process_identity(os.getpid())
            if identity is None or identity['command'] != ' '.join([str(self.executable), *self.arguments]):
                raise NoticeError('提醒启动状态无法核对。')
            owner = {'format': FORMAT, 'pid': os.getpid(), 'token': uuid.uuid4().hex,
                     'executable': str(self.executable), 'started': identity['started'], 'arguments': self.arguments}
            write_json(self.owner_path, owner)
            while not stopped() and not self.stopped(owner):
                try:
                    snapshot = self.client.request('refresh', manual=False)
                    if not snapshot['enabled']: return 0
                    if stopped() or self.stopped(owner): return 0
                    result = self.client.request('take')
                    if result.get('alert') and not stopped() and not self.stopped(owner): notify(result['alert'])
                except (NoticeError, OSError, ValueError, subprocess.SubprocessError):
                    pass  # The shared rule service preserves cached history and applies retry backoff.
                for _ in range(60):
                    if stopped() or self.stopped(owner): return 0
                    wait(.5)
            return 0
        finally:
            if owner:
                for path in (self.owner_path, self.stop_path):
                    with contextlib.suppress(OSError, ValueError):
                        value = read_json(path)
                        if value.get('token') == owner['token'] and value.get('executable') == owner['executable']:
                            path.unlink()
            lease.close()


def notice_dialog(alert):
    from AppKit import NSAlert
    dialog = NSAlert.alloc().init()
    dialog.setMessageText_(alert['summary'])
    details = [alert.get('description', ''), alert.get('timeText', ''), alert.get('timeNote', ''),
               '想等这次重置又保留卡，关闭自动用卡即可。自动续跑可以继续开启，额度到账后接着做。']
    dialog.setInformativeText_('\n\n'.join(value for value in details if value))
    for title in ('知道了', '查看原帖', '关闭自动用卡'): dialog.addButtonWithTitle_(title)
    return dialog


def show_notice(alert, configure=None):
    """Only user clicks can open an original post or stop auto-resume."""
    from AppKit import NSAlert, NSApplication
    from PyObjCTools import AppHelper
    dialog = notice_dialog(alert)
    if configure: configure(dialog)
    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    response = dialog.runModal()
    dialog.window().orderOut_(None)
    if response == 1001:
        if re.fullmatch(r'[1-9][0-9]{14,19}', alert.get('id', '')) and alert.get('url') == 'https://x.com/thsottiaux/status/' + alert['id']:
            from core.common import open_external
            open_external(alert['url'])
    elif response == 1002:
        def pause():
            import auto_resume
            try:
                result = auto_resume.Controller().action('credit-off')
                message = '自动用卡已关闭，续跑和计时开关保持原样。' if result.get('autoRedeem') is False else '请打开工具箱确认用卡设置。'
            except Exception:
                message = '自动用卡尚未确认关闭，请打开工具箱刷新查看。'
            def report():
                feedback = NSAlert.alloc().init()
                feedback.setMessageText_(message)
                feedback.runModal()
            AppHelper.callAfter(report)
        threading.Thread(target=pause, daemon=True).start()


def background_main(monitor=None, notify=show_notice, stopped=lambda: False):
    from AppKit import NSApplication, NSModalPanelRunLoopMode
    from Foundation import NSObject, NSDefaultRunLoopMode
    from PyObjCTools import AppHelper
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # Accessory: reminders survive the main window without a second Dock icon.
    monitor = monitor or Monitor()
    class AIFirstResetMonitorDelegate(NSObject):
        def stop_(self, ignored):
            if app.modalWindow() is not None: app.abortModal()
            app.terminate_(None)
    delegate = AIFirstResetMonitorDelegate.alloc().init()
    def deliver(alert):
        try:
            owner = monitor.live_owner()
            if owner is None or owner['pid'] != os.getpid() or not monitor.client.request()['enabled']:
                return
        except (NoticeError, OSError, ValueError, subprocess.SubprocessError):
            return
        notify(alert)
    def worker():
        try: monitor.run(lambda alert: AppHelper.callAfter(deliver, alert), stopped=stopped)
        finally:
            # Include Cocoa's modal mode so an open reminder cannot prevent an
            # owned update/uninstall request from closing this notification app.
            delegate.performSelectorOnMainThread_withObject_waitUntilDone_modes_(
                'stop:', None, False, [NSDefaultRunLoopMode, NSModalPanelRunLoopMode])
    threading.Thread(target=worker, daemon=True).start()
    AppHelper.runEventLoop()
    return 0
