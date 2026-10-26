"""Actual frozen-runtime and launchd audit in an isolated synthetic profile."""
from __future__ import annotations
import contextlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import auto_resume
from auto_resume import Controller, LABEL, WATCH

def audit(report: Path) -> int:
    checks={}
    def require(value):
        if not value: raise AssertionError('Auto-resume native assertion failed')
    def wait(test, seconds=15):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                if test(): return
            except auto_resume.ControlError:
                pass
            time.sleep(.2)
        require(False)
    original_home=Path.home()
    real_plist=original_home/'Library/LaunchAgents'/(LABEL+'.plist')
    require(not real_plist.exists())
    with tempfile.TemporaryDirectory(prefix='ai-first-native-resume-') as temporary:
        root=Path(temporary)
        home=root/'synthetic-home'
        home.mkdir()
        bundle=root/'AI一手工具工作台.app'
        shutil.copytree(Path(sys.executable).parents[2],bundle,symlinks=True)
        codex_home=home/'.codex'
        codex_home.mkdir()
        (codex_home/'config.toml').write_text('cli_auth_credentials_store = "file"\n[features]\nplugins = false\n')
        state=home/'Library/Application Support/vibcoding/codex-auto-resume'
        state.mkdir(parents=True)
        (state/'config.json').write_text(json.dumps({'enabled':False,'poll_seconds':5,'state_dir':str(state),'codex_home':str(codex_home)}))
        old_env=os.environ.copy()
        os.environ.update({'HOME':str(home),'CODEX_HOME':str(codex_home),'PATH':'/usr/bin:/bin:/usr/sbin:/sbin'})
        for key in ('CODEX_BIN','PYTHONPATH'): os.environ.pop(key,None)
        controller=Controller(bundle,home)
        try:
            from codex_auto_resume.paths import bundled_codex
            from codex_auto_resume.app_server import AppServerClient
            native=bundled_codex()
            os.environ['CODEX_MANAGED_PACKAGE_ROOT']=str(Path(sys._MEIPASS)/'auto-resume-native')
            result=subprocess.run([str(native),'--version'],capture_output=True,timeout=20)
            require(result.returncode==0 and b'codex' in result.stdout.lower())
            with AppServerClient([str(native)],env=os.environ.copy()) as client:
                require(client.request('account/read',{'refreshToken':False}).get('account') is None)
            checks['nativeRuntimeWithoutExternalInstallation']=True
            require(controller.action('start')['watcherCount']==1)
            wait(lambda:(state/'state.json').exists())
            require(json.loads((state/'state.json').read_text())['last_status']=='disabled')
            require(controller.action('start')['watcherCount']==1)
            original=controller.watchers()
            duplicate=subprocess.run([str(controller.executable),WATCH,'--manual'],env={**os.environ,'PYINSTALLER_RESET_ENVIRONMENT':'1'},timeout=15)
            require(duplicate.returncode==0 and controller.watchers()==original)
            checks['singlePackagedWatcher']=True
            before=controller.watchers()
            require(controller.action('autostart-on')['autostart'])
            require(controller.action('autostart-off')['running'] and controller.watchers()==before)
            checks['startupSwitchIndependent']=True
            require(not controller.action('stop')['running'])
            result=subprocess.run([str(controller.executable),WATCH],env={**os.environ,'PYINSTALLER_RESET_ENVIRONMENT':'1'},timeout=15)
            require(result.returncode==0 and not controller.watchers())
            time.sleep(2)
            require(not controller.watchers())
            checks['stopBlocksStartupRelaunch']=True
            controller.action('start')
            controller.action('autostart-on')
            require(not controller.action('prepare-update')['running'])
            require(controller.action('finish-update')['watcherCount']==1 and controller.status()['autostart'])
            checks['updateRestoresRunningAndStartup']=True
            controller.stop()
            value=controller.registration()
            value['EnvironmentVariables'].update({'HOME':str(home),'CODEX_HOME':str(codex_home)})
            import plistlib
            with controller.plist.open('wb') as stream: plistlib.dump(value,stream)
            result=controller.launchctl('bootstrap',controller.domain,str(controller.plist))
            require(result.returncode==0)
            wait(lambda:len(controller.watchers())==1)
            require(not controller.action('stop')['running'] and not controller.plist.exists())
            checks['realLaunchAgentStopsWithoutRelaunch']=True
            controller.action('start')
            controller.action('autostart-on')
            moved=root/'Removed.app'
            bundle.rename(moved)
            wait(lambda:not controller.watchers() and not controller.plist.exists())
            require(not controller.enabled())
            checks['finderRemovalCleansBackgroundAndStartup']=True
            moved.rename(bundle)
            controller.action('start')
            controller.action('autostart-on')
            require(not controller.action('uninstall')['running'] and not controller.plist.exists())
            require((state/'config.json').exists())
            checks['cleanupPreservesUserSettings']=True
        except Exception as error:
            failure=type(error).__name__
        else: failure=None
        finally:
            with contextlib.suppress(Exception): controller.action('uninstall')
            os.environ.clear();os.environ.update(old_env)
    passed=failure is None and len(checks)==8 and all(checks.values())
    report.write_text(json.dumps({'passed':passed,'checks':checks,'errorType':failure,'architecture':platform.machine(),
                                 'version':json.loads((Path(sys._MEIPASS)/'version.json').read_text()),
                                 'scope':'real frozen process and launchd, isolated disabled workload and signed-out Codex profile; no model request'},indent=2))
    return 0 if passed else 1
