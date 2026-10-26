"""Current-user controls for the background built into the same application."""
from __future__ import annotations
import contextlib
import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

LABEL = 'cn.aifirst.tools.auto-resume'
LEGACY = 'com.vibcoding.codex-auto-resume'
APP = 'AI一手工具工作台.app'
WATCH = '--auto-resume-watch'

class ControlError(RuntimeError):
    pass

class Controller:
    def __init__(self, bundle: Path | None = None, home: Path | None = None):
        self.home = home or Path.home()
        self.bundle = (bundle or Path(sys.executable).parents[2]).resolve()
        self.executable = self.bundle / 'Contents/MacOS/AI First Tools'
        self.root = self.home / 'Library/Application Support/AI一手工具工作台/auto-resume'
        self.plist = self.home / 'Library/LaunchAgents' / (LABEL + '.plist')
        self.preference = self.root / 'startup.json'
        self.receipt = self.root / 'update.json'
        self.domain = 'gui/' + str(os.getuid()) if hasattr(os,'getuid') else 'gui/synthetic'
        self._foreign = None

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value), encoding='utf-8')
        temporary.replace(path)

    def enabled(self):
        if not self.preference.exists(): return True
        value = json.loads(self.preference.read_text())
        if not isinstance(value.get('autostart'), bool): raise ControlError('开机设置暂时无法读取。')
        return value['autostart']

    def registration(self):
        if not self.plist.exists(): return None
        with self.plist.open('rb') as stream: value = plistlib.load(stream)
        if value.get('Label') != LABEL or value.get('ProgramArguments') != [str(self.executable),WATCH]:
            raise ControlError('开机设置属于另一处工作台，请先在原工作台关闭开机自动开启。')
        return value

    def watchers(self):
        from codex_auto_resume.watch_control import inspect_watch, state_path, WatchStateError
        try: value = inspect_watch(state_path())
        except (WatchStateError, OSError, ValueError) as error:
            raise ControlError('续跑状态暂时无法确认，请稍后刷新。') from error
        self._foreign = None
        if not value['running']: return []
        if Path(value['executable']).resolve() != self.executable:
            executable = Path(value['executable']).resolve()
            if (executable.name != 'AI First Tools' or executable.parent.name != 'MacOS'
                    or executable.parent.parent.name != 'Contents' or executable.parent.parent.parent.name != APP):
                raise ControlError('现有续跑程序的归属暂时无法确认，请稍后刷新。')
            self._foreign = Controller(executable.parents[2], self.home)
        return [value['pid']]

    def launchctl(self, *args):
        return subprocess.run(['/bin/launchctl',*args],capture_output=True,timeout=15)

    def startup(self, enabled):
        self.registration() # Refuse to overwrite a foreign installation's registration.
        self.write(self.preference,{'autostart':enabled})
        if enabled:
            self.plist.parent.mkdir(parents=True,exist_ok=True)
            value={'Label':LABEL,'ProgramArguments':[str(self.executable),WATCH], 'RunAtLoad':True, 'KeepAlive':False,'AbandonProcessGroup':True,
                   'ProcessType':'Background','EnvironmentVariables':{'PATH':'/usr/bin:/bin:/usr/sbin:/sbin'}}
            temporary=self.plist.with_suffix('.tmp')
            with temporary.open('wb') as stream: plistlib.dump(value,stream)
            temporary.replace(self.plist)
        else:
            self.plist.unlink(missing_ok=True)
        # Registration is loaded by launchd on the next login. Saving the option
        # does not start or terminate the currently running watcher.

    def status(self):
        pids=self.watchers()
        if self._foreign is not None: return self._foreign.status()
        return {'installed':self.executable.is_file(),'running':bool(pids),'autostart':self.registration() is not None and self.enabled(),
                'watcherCount':len(pids),'error':''}

    def start(self):
        if self.watchers(): return
        if not self.executable.is_file(): raise ControlError('内置续跑组件缺失，请重新安装完整工作台。')
        env=os.environ.copy()
        env['PYINSTALLER_RESET_ENVIRONMENT']='1'
        subprocess.Popen([str(self.executable),WATCH,'--manual'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,env=env,start_new_session=True,close_fds=True)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            try:
                if len(self.watchers())==1: return
            except ControlError:
                pass  # Ownership is established before the watcher is reported ready.
            time.sleep(.2)
        raise ControlError('续跑暂时没能开启，请稍后重试。')

    def stop(self):
        from codex_auto_resume.watch_control import request_stop
        if not self.watchers(): return
        if request_stop() != 0: raise ControlError('暂时无法确认续跑状态，没有停止其他任务。请刷新后重试。')
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            try:
                if not self.watchers(): return
            except ControlError:
                pass
            time.sleep(.2)
        raise ControlError('续跑正在结束本次检查，请稍后刷新。不会强行停止正在处理的任务。')

    def legacy(self):
        path=self.home/'Library/LaunchAgents'/(LEGACY+'.plist')
        if not path.exists(): return None
        with path.open('rb') as stream: value=plistlib.load(stream)
        args=value.get('ProgramArguments',[])
        if value.get('Label')!=LEGACY or len(args)!=4 or args[2:]!=['watch','--quiet'] or Path(args[1]).name!='run.py' or Path(args[1]).parent.name!='codex-auto-resume':
            raise ControlError('检测到无法识别的旧开机设置，未做修改。')
        return path

    def act(self, operation):
        self.watchers()
        if self._foreign is not None and operation in {'start','stop','autostart-on','autostart-off'}:
            return self._foreign.act(operation)  # Only an explicit user switch controls the verified running copy.
        if operation=='status': return self.status()
        if operation=='start': self.start()
        elif operation=='stop':
            self.startup(False)
            self.stop()
            self.launchctl('bootout',self.domain+'/'+LABEL)
        elif operation in ('autostart-on','autostart-off'): self.startup(operation=='autostart-on')
        elif operation=='prepare-update':
            import reset_notices
            reset_notices.Monitor(self.bundle, self.root.parent / 'reset-notices').stop_owned('update')
            if self._foreign is not None: return self._foreign.status()
            if self.watchers():
                self.write(self.receipt,{'program':str(self.executable),'restart':True})
                self.stop()
                self.launchctl('bootout',self.domain+'/'+LABEL)
        elif operation=='finish-update':
            import reset_notices
            reset_notices.Monitor(self.bundle, self.root.parent / 'reset-notices').restore()
            if self._foreign is not None: return self._foreign.status()
            if self.receipt.exists():
                value=json.loads(self.receipt.read_text())
                if value.get('program')==str(self.executable) and value.get('restart') is True: self.start()
                self.receipt.unlink()
            else:
                old=self.legacy()
                if old:
                    self.launchctl('bootout',self.domain+'/'+LEGACY)
                    old.unlink()
                    self.startup(True)
                    self.start()
        elif operation=='uninstall':
            import reset_notices
            reset_notices.Monitor(self.bundle, self.root.parent / 'reset-notices').stop_owned('uninstall')
            if self._foreign is not None: return self._foreign.status()
            self.startup(False)
            self.stop()
            self.launchctl('bootout',self.domain+'/'+LABEL)
            self.receipt.unlink(missing_ok=True)
        else: raise ControlError('未知操作。')
        return self.status()

    def action(self, operation):
        import fcntl
        self.root.mkdir(parents=True,exist_ok=True)
        with (self.root/'control.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            return self.act(operation)

def background_main(argv):
    from codex_auto_resume.cli import main
    from codex_auto_resume.paths import bundled_codex
    controller=Controller()
    if '--manual' not in argv and not controller.enabled(): return 0
    import fcntl
    controller.root.mkdir(parents=True,exist_ok=True)
    watcher_lock=(controller.root/'watcher.lock').open('a')
    try: fcntl.flock(watcher_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        watcher_lock.close()
        return 0
    native=bundled_codex()
    root=Path(sys._MEIPASS)/'auto-resume-native'
    os.environ['CODEX_MANAGED_PACKAGE_ROOT']=str(root)
    os.environ['PATH']=str(native.parent.parent/'codex-path')+os.pathsep+os.environ.get('PATH','')
    for name in ('stdout','stderr'):
        if getattr(sys,name) is None: setattr(sys,name,open(os.devnull,'w'))
    # A lightweight monitor also handles Finder removal while quota I/O is idle.
    def removal():
        while controller.bundle.exists(): time.sleep(.5)
        from codex_auto_resume.config import load_config
        state=load_config().resolved_state_dir()
        state.mkdir(parents=True,exist_ok=True)
        (state/'stop.request').write_text('stop\n')
        with contextlib.suppress(OSError,ValueError,ControlError): controller.startup(False)
    import threading
    threading.Thread(target=removal,daemon=True).start()
    try: return main(['watch','--quiet'])
    finally:
        watcher_lock.close()
        if not controller.bundle.exists():
            with contextlib.suppress(OSError,ValueError,ControlError): controller.startup(False)
