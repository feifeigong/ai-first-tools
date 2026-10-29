"""Actual preview.25 helper and watcher, strictly within a synthetic HOME."""
import contextlib,hashlib,json,os,platform,shutil,subprocess,sys,time,tempfile
from pathlib import Path
import updater

def run(root: Path, app: Path) -> dict:
    from auto_resume import Controller,WATCH
    from reset_notices import Client,Monitor
    if sys.platform!='darwin' or not getattr(sys,'frozen',False) or os.environ.get('GITHUB_ACTIONS')!='true' or not root.name.startswith('ai-first-update-audit-') or not root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise RuntimeError('Run only with the frozen app in a dedicated native audit root')
    checks={};phase='fixture';watcher=helper=None
    original_env=os.environ.copy();old_state=updater._audit_state
    def require(value):
        if not value:raise AssertionError('Published updater regression failed')
    def wait(test,seconds=30):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if test():return
            time.sleep(.2)
        require(False)
    mount=root/'legacy-mount';mount.mkdir()
    try:
        lock=json.loads((Path(sys._MEIPASS)/'legacy-update.lock.json').read_text(encoding='utf8'))
        dmg=Path(os.environ['AI_FIRST_LEGACY_UPDATE_DMG']).resolve()
        require(dmg.is_file() and dmg.stat().st_size==lock[platform.machine()]['size'])
        with dmg.open('rb') as stream:require(hashlib.file_digest(stream,'sha256').hexdigest()==lock[platform.machine()]['sha256'])
        updater.command(['/usr/bin/hdiutil','attach','-readonly','-nobrowse','-mountpoint',str(mount),str(dmg)])
        target=root/updater.APP_NAME
        updater.command(['/usr/bin/ditto',str(mount/updater.APP_NAME),str(target)])
        updater.command(['/usr/bin/hdiutil','detach',str(mount)])
        current=lock['release'];new=json.loads((app/'Contents/Resources/version.json').read_text(encoding='utf8'))['release']
        updater.validate_app(target,current,platform.machine())
        # Every path is our new synthetic HOME, not a runner/user account.
        home=root/'profile';home.mkdir();support=home/'Library/Application Support';support.mkdir(parents=True)
        codex=home/'.codex';codex.mkdir();(codex/'config.toml').write_text('cli_auth_credentials_store = "file"\n[features]\nplugins=false\n')
        state=support/'vibcoding/codex-auto-resume';state.mkdir(parents=True)
        (state/'config.json').write_text(json.dumps({'enabled':False,'auto_start_five_hour':False,'auto_redeem_weekly_reset':False,'poll_seconds':1,'state_dir':str(state),'codex_home':str(codex)}))
        os.environ.update({'HOME':str(home),'USERPROFILE':str(home),'APPDATA':str(support),'LOCALAPPDATA':str(support),'CODEX_HOME':str(codex),'LANG':'C','LC_ALL':'C','LC_CTYPE':'C','PYINSTALLER_RESET_ENVIRONMENT':'1'})
        for name in ('CLAUDE_CONFIG_DIR','COWORK_SESSIONS_DIR','WORKBUDDY_DIR','WORKBUDDY_AI_DIR','QWENWORK_DIR','DOUBAO_WORK_DIR','CURSOR_DESKTOP_USER_DIR','HERMES_HOME','XDG_DATA_HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_STATE_HOME'):
            os.environ[name]=str(home/name.lower())
        os.environ.pop('CODEX_BIN',None);os.environ.pop('PYTHONPATH',None)
        updater._audit_state=support/'AI一手工具工作台/updates'
        Client(support/'AI一手工具工作台/reset-notices').request('enabled',enabled=False)
        watcher=updater.start_app(target,(WATCH,'--manual'))
        wait(lambda:(state/'watch.owner.json').is_file() and (state/'state.json').is_file())
        require(watcher.poll() is None and json.loads((state/'state.json').read_text())['last_status']=='disabled')
        incoming=root/'fixture'/updater.APP_NAME
        updater.command(['/usr/bin/ditto',str(app),str(incoming)])
        from update_audit import standard_fixture
        standard_fixture(incoming,root)
        updater.command(['/usr/bin/codesign','--force','--deep','--sign','-',str(incoming)])
        directory=root/'.ai-first-update-published';directory.mkdir(mode=0o700)
        job=updater.stage_bundle(target,incoming,new,current,platform.machine(),directory)
        data=updater.read_job(job)
        # Execute the real old helper first, not current code with an old label.
        shutil.rmtree(directory/'helper.app')
        updater.command(['/usr/bin/ditto',str(target),str(directory/'helper.app')])
        parent=subprocess.Popen(['/bin/sleep','1'])
        data['parentPid']=parent.pid;updater.write_json(job,data)
        helper=updater.start_app(directory/'helper.app',('--apply-update',str(job)))
        parent.wait(timeout=5);helper.wait(timeout=100)
        receipt=updater.state_root()/'result.json';outcome=json.loads(receipt.read_text(encoding='utf8'))
        require(helper.returncode!=0 and outcome.get('phase')=='replacement' and outcome.get('errorCode')=='ControlError')
        require(updater.fingerprint(target)==data['originalDigest'] and watcher.poll() is None)
        checks['published25FailureReproduced']=True
        phase='new_helper_recovery'
        shutil.rmtree(directory/'helper.app')
        updater.command(['/usr/bin/ditto',str(directory/'candidate.app'),str(directory/'helper.app')])
        for name in ('ready.json','completion.json'):(directory/name).unlink(missing_ok=True)
        parent=subprocess.Popen(['/bin/sleep','1']);data['parentPid']=parent.pid;updater.write_json(job,data)
        helper=updater.start_helper(job)
        require(json.loads((directory/'ready.json').read_text())['ready'] is True)
        parent.wait(timeout=5);helper.wait(timeout=120)
        outcome=json.loads(receipt.read_text(encoding='utf8'))
        require(helper.returncode==0 and outcome.get('success') is True and watcher.poll() is not None)
        checks['published25BackgroundRecovered']=True
        startup=json.loads((directory/'startup.json').read_text(encoding='utf8'))
        require(startup.get('ready') is True and startup['version']==new)
        time.sleep(3)
        os.kill(startup['pid'],0)
        checks['normalUpdatedWindowStaysReady']=True
        return {'checks':checks,'previousPublished':current,'phase':'complete','modelRequests':0,'signedOutSyntheticOnly':True}
    except Exception as error:
        return {'checks':checks,'previousPublished':'0.4.0-macos-preview.25','phase':phase,'errorCode':type(error).__name__,'modelRequests':0,'signedOutSyntheticOnly':True}
    finally:
        with contextlib.suppress(Exception):Controller(root/updater.APP_NAME,root/'profile').action('uninstall')
        with contextlib.suppress(Exception):Monitor(root/updater.APP_NAME,root/'profile/Library/Application Support/AI一手工具工作台/reset-notices').stop_owned('uninstall')
        startup=root/'.ai-first-update-published/startup.json'
        if startup.is_file():
            with contextlib.suppress(Exception):
                identity=json.loads(startup.read_text());pid=identity['pid']
                from codex_auto_resume.watch_control import _darwin_process_path
                if _darwin_process_path(pid)==(root/updater.APP_NAME/'Contents/MacOS'/updater.EXECUTABLE).resolve():os.kill(pid,15)
        for process in (helper,watcher):
            if process is not None and process.poll() is None:
                with contextlib.suppress(Exception):process.terminate();process.wait(timeout=10)
        with contextlib.suppress(Exception):
            if os.path.ismount(mount):updater.command(['/usr/bin/hdiutil','detach',str(mount)])
        os.environ.clear();os.environ.update(original_env);updater._audit_state=old_state
