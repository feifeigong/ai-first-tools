"""Reproduce process ownership checks across launchd time zones, synthetic only."""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'auto-resume/src'))
from codex_auto_resume import watch_control as watch


def main():
    assert sys.platform=='darwin' and os.environ.get('GITHUB_ACTIONS')=='true'
    output=Path('artifacts/launch-agent-probe.json');output.parent.mkdir(exist_ok=True)
    domain='gui/'+str(os.getuid());label='cn.aifirst.synthetic-watch-probe'
    result={}
    with tempfile.TemporaryDirectory(prefix='synthetic-watch-zone-') as temporary:
        root=Path(temporary).resolve();runner=root/'run.py';state=root/'watch.pid'
        source=Path(__file__).resolve().parents[1]/'auto-resume/src'
        (root/'src').symlink_to(source,target_is_directory=True)
        # The control layer intentionally refuses source symlinks. Use real
        # fixture files, rather than weakening its production package checks.
        (root/'src').unlink()
        import shutil
        shutil.copytree(source,root/'src',ignore=shutil.ignore_patterns('__pycache__'))
        runner.write_text("import os,time,sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).parent/'src'))\nfrom codex_auto_resume.watch_control import claim,release\np=Path(os.environ['SYNTHETIC_WATCH_PATH'])\nif claim(p):\n try:\n  while not p.with_name('stop.request').exists():time.sleep(.1)\n finally:release(p)\n")
        plist=root/'agent.plist'
        plist.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':[sys.executable,str(runner),'watch','--quiet'],
            'RunAtLoad':True,'KeepAlive':False,'EnvironmentVariables':{'PATH':'/usr/bin:/bin','TZ':'America/Los_Angeles','SYNTHETIC_WATCH_PATH':str(state)}}))
        os.environ['TZ']='UTC'
        boot=subprocess.run(['/bin/launchctl','bootstrap',domain,str(plist)],capture_output=True)
        result['bootstrapSucceeded']=boot.returncode==0
        try:
            deadline=time.monotonic()+12
            while not state.with_name('watch.owner.json').exists() and time.monotonic()<deadline:time.sleep(.1)
            result['ownerPublished']=state.with_name('watch.owner.json').exists()
            if result['ownerPublished']:
                owner=json.loads(state.with_name('watch.owner.json').read_text())
                actual=watch._inspect_process(owner['pid'])
                result['sameKernelProcess']=actual is not None and watch._watcher(actual)
                result['sameStartIdentity']=actual is not None and owner['started_at']==actual['started_at']
                result['lifetimeLockHeld']=watch._lock_held(state)
                try:result['recognizedRunning']=watch.inspect_watch(state)['running']
                except watch.WatchStateError as e:result['recognitionError']=e.code
        finally:
            state.with_name('stop.request').write_text('stop\n')
            time.sleep(.5)
            subprocess.run(['/bin/launchctl','bootout',domain+'/'+label],capture_output=True)
    output.write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()
