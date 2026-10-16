"""Current-user controls for the background built into the same application."""
from __future__ import annotations
import contextlib
import json
import os
import plistlib
import signal
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
        result=subprocess.run(['/bin/ps','-ax','-o','pid=,args='],capture_output=True,text=True,check=True,timeout=10)
        expected={str(self.executable)+' '+WATCH,str(self.executable)+' '+WATCH+' --manual'}
        found=[]
        for line in result.stdout.splitlines():
            parts=line.strip().split(None,1)
            if len(parts)==2 and parts[1] in expected: found.append(int(parts[0]))
        return found

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
        return {'installed':self.executable.is_file(),'running':bool(pids),'autostart':self.registration() is not None and self.enabled(),
                'watcherCount':len(pids),'error':''}

    def start(self):
        if self.watchers(): return
        if not self.executable.is_file(): raise ControlError('内置续跑组件缺失，请重新安装完整工作台。')
        env=os.environ.copy()
        env['PYINSTALLER_RESET_ENVIRONMENT']='1'
        subprocess.Popen([str(self.executable),WATCH,'--manual'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,env=env,start_new_session=True,close_fds=True)
        time.sleep(.9)
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if len(self.watchers())==1: return
            time.sleep(.2)
        raise ControlError('内置后台暂未保持运行，请刷新或重新安装完整工作台。')

    def stop(self):
        from codex_auto_resume.config import load_config
        state=load_config().resolved_state_dir()
        state.mkdir(parents=True,exist_ok=True)
        (state/'stop.request').write_text('stop\n')
        deadline=time.monotonic()+12
        while self.watchers() and time.monotonic()<deadline: time.sleep(.2)
        for pid in self.watchers():
            if pid in self.watchers():
                with contextlib.suppress(ProcessLookupError): os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+5
        while self.watchers() and time.monotonic()<deadline: time.sleep(.2)
        if self.watchers(): raise ControlError('后台尚未停止，请稍后刷新。')

    def legacy(self):
        path=self.home/'Library/LaunchAgents'/(LEGACY+'.plist')
        if not path.exists(): return None
        with path.open('rb') as stream: value=plistlib.load(stream)
        args=value.get('ProgramArguments',[])
        if value.get('Label')!=LEGACY or len(args)!=4 or args[2:]!=['watch','--quiet'] or Path(args[1]).name!='run.py' or Path(args[1]).parent.name!='codex-auto-resume':
            raise ControlError('检测到无法识别的旧开机设置，未做修改。')
        return path

    def act(self, operation):
        if operation=='status': return self.status()
        if operation=='start': self.start()
        elif operation=='stop':
            self.startup(False)
            self.stop()
            self.launchctl('bootout',self.domain+'/'+LABEL)
        elif operation in ('autostart-on','autostart-off'): self.startup(operation=='autostart-on')
        elif operation=='prepare-update':
            if self.watchers():
                self.write(self.receipt,{'program':str(self.executable),'restart':True})
                self.stop()
                self.launchctl('bootout',self.domain+'/'+LABEL)
        elif operation=='finish-update':
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
