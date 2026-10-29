from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

if "--apply-update" in sys.argv:
    import updater

    raise SystemExit(updater.helper_main())

if '--auto-resume-watch' in sys.argv:
    import auto_resume
    raise SystemExit(auto_resume.background_main(sys.argv[1:]))

PROJECT = Path(__file__).resolve().parent.parent
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(PROJECT / "dialog-mover"))
    sys.path.insert(0, str(PROJECT / "dialog-mover" / "vendor"))
    sys.path.insert(0, str(PROJECT / "auto-resume" / "src"))

if '--memory-service' in sys.argv:
    sys.argv.remove('--memory-service')
    from core.memory_server import main as memory_main
    memory_main()
    raise SystemExit(0)

if '--reset-monitor' in sys.argv:
    import reset_notices
    raise SystemExit(reset_notices.background_main())

if len(sys.argv) == 3 and sys.argv[1] in {'--reset-monitor-audit', '--reset-launcher-audit'}:
    from reset_audit import monitor_child, launcher_child
    action = monitor_child if sys.argv[1] == '--reset-monitor-audit' else launcher_child
    raise SystemExit(action(Path(sys.argv[2])))

if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--copilot-refresh-child':
    from copilot_refresh_audit import fixture_child
    raise SystemExit(fixture_child(Path(sys.argv[2])))

import webview

from core import common, mover
from core.common import appdata, open_external
from main import Api
import updates
import updater
import auto_resume
import reset_notices

ROOT = Path(getattr(sys, "_MEIPASS", PROJECT / "artifacts" / "macos" / "resources"))


def version_info() -> dict:
    return json.loads((ROOT / "version.json").read_text(encoding="utf-8"))


class MacApi(Api):
    def reset_news_control(self, operation: str = 'status') -> dict:
        if operation not in {'status', 'refresh', 'enable', 'disable'}:
            return {'error': '未知的提醒操作。'}
        if self._smoke:
            if not hasattr(self, '_notice_fixture'):
                self._notice_fixture = {'enabled': True, 'fresh': False, 'partial': False,
                    'today': '2026-10-23', 'events': [], 'lastCheckedLabel': '10-23 09:00',
                    'statusText': '合成重置消息检查', 'detailText': '不联网、不读取真实资料。'}
            if operation in {'enable', 'disable'}: self._notice_fixture['enabled'] = operation == 'enable'
            return {**self._notice_fixture, 'ok': True}
        try:
            client = reset_notices.Client()
            if operation in {'enable', 'disable'}:
                value = client.request('enabled', enabled=operation == 'enable')
                if operation == 'enable' and getattr(sys, 'frozen', False): reset_notices.Monitor(client=client).ensure()
            else:
                value = client.request('refresh', manual=True) if operation == 'refresh' else client.request()
            if value['enabled'] and getattr(sys, 'frozen', False):
                monitor = reset_notices.Monitor(client=client)
                if monitor.live_owner() is None: monitor.ensure()
                value['monitorReady'] = monitor.live_owner() is not None
                if not value['monitorReady']:
                    value.update(fresh=False, statusText='提醒正在准备，稍后会自动更新状态',
                                 detailText='已有历史仍可查看；若一直没有恢复，可以关闭提醒后再重新开启。')
            return value
        except Exception:
            return {'error': '重置消息暂时无法更新，请稍后再试。'}

    def open_reset_post(self, identity: str) -> dict:
        if self._smoke: return {'ok': True}
        try: return reset_notices.Client().open_post(identity)
        except Exception: return {'error': '暂时无法打开原帖，请稍后再试。'}

    def auto_resume_control(self, operation: str = 'status') -> dict:
        if self._smoke:
            if not hasattr(self,'_resume_fixture'): self._resume_fixture={'installed':True,'running':False,'autostart':False,'watcherCount':0,'error':'','resumeEnabled':False,'autoRedeem':False,'autoStartWindow':False,'timerStatus':'waiting','nextResetAt':0}
            value=self._resume_fixture
            if operation=='start': value['running']=True
            elif operation=='stop': value.update(running=False,autostart=False)
            elif operation in ('autostart-on','autostart-off'): value['autostart']=operation=='autostart-on'
            elif operation in ('resume-on','resume-off'):
                value['resumeEnabled']=operation=='resume-on'
                value['autoRedeem']=False
                value['running']=value['resumeEnabled'] or value['autoStartWindow']
                if not value['running']: value['autostart']=False
            elif operation in ('credit-on','credit-off'): value['autoRedeem']=operation=='credit-on'
            elif operation in ('timer-on','timer-off'):
                value['autoStartWindow']=operation=='timer-on'
                value['running']=value['resumeEnabled'] or value['autoStartWindow']
                if not value['running']: value['autostart']=False
            value['watcherCount']=int(value['running'])
            return dict(value)
        if not getattr(sys,'frozen',False): return {'error':'请使用完整工具箱安装包中的自动续跑功能。'}
        self._resume_busy=True
        try:
            return auto_resume.Controller().action(operation)
        except Exception as error:
            return {'error':str(error) if isinstance(error,auto_resume.ControlError) else '操作没有完成，请刷新确认运行状态。',
                    'errorCode':error.code if isinstance(error,auto_resume.ControlError) else 'control_unavailable'}
        finally:
            self._resume_busy=False

    def __init__(self, smoke: bool = False) -> None:
        super().__init__()
        self._smoke = smoke
        self._smoke_check_calls = 0
        self._release = None
        self._update_lock = threading.Lock()
        self._update_gate = threading.RLock()
        self._package = None
        self._prepared = None
        self._update_cancel = threading.Event()
        self._update_state = {"phase": "idle", "progress": 0}
        self._handing_off = False
        self._update_closing = False
        self._update_download = None
        self._update_audit = False
        self._update_trace = []
        self._update_ui_ready = None
        self._update_handoff_id = None
        self._update_failure = None
        self._release_highlights = None

    def release_notes(self) -> dict:
        return self._release_highlights.info() if self._release_highlights else {}

    def acknowledge_release_notes(self, release: str) -> dict:
        return {'ok':bool(self._release_highlights and self._release_highlights.acknowledge(release))}

    def open_release_notes(self) -> dict:
        if self._release_highlights and self._release_highlights.content:
            try:
                open_external('https://github.com/feifeigong/ai-first-tools/releases/tag/v'+self._release_highlights.version)
                return {'ok':True}
            except (OSError,subprocess.SubprocessError): pass
        return {'ok':False}

    def workspace_info(self) -> dict:
        message = None
        info = version_info()
        receipt = updater.state_root() / "result.json"
        if info.get('developmentPreview') is not True and receipt.is_file():
            try:
                result = json.loads(receipt.read_text(encoding="utf-8"))
                if result.get("version") == version_info()["release"]:
                    message = result.get("message")
                    receipt.unlink()
            except (OSError, ValueError):
                pass
        return {**info, "platform": "macOS", "architecture": platform.machine(), "automaticChecks": self._smoke or self._update_audit or info.get('developmentPreview') is not True,
                "smokeAudit": self._smoke, "updateAudit": self._update_audit, "updateMessage": message}

    def check_update(self) -> dict:
        if self._update_audit:
            return {"available": True, "version": self._package["version"], "canInstall": True}
        if self._smoke:
            self._smoke_check_calls += 1
            return {"available": True, "version": "synthetic-reminder-only", "canInstall": True}
        if version_info().get('developmentPreview') is True:
            return {'available': False, 'localPreview': True, 'canInstall': False}
        if not self._update_lock.acquire(blocking=False):
            return {"error": "正在检查更新，请稍等。"}
        try:
            result = updates.check(version_info()["release"])
            package = updater.package_from_release(result) if result.get("available") else None
            self._release = result.get("url")
            self._package = package
            return {**{key: value for key, value in result.items() if key != "assets"},
                    "canInstall": self._package is not None and bool(getattr(sys, "frozen", False))}
        except (OSError, ValueError, TypeError, ImportError) as error:
            result = updates.failure(error)
            retained = self._package is not None and result["errorCode"] in ("timeout", "dns", "network", "http", "rate_limit", "tls", "certificate")
            if not retained:
                self._release = None
                self._package = None
            return {**result, "retainedUpdate": retained}
        finally:
            self._update_lock.release()

    def open_update(self) -> dict:
        try:
            open_external(self._release or updates.DOWNLOADS_URL)
            return {"ok": True}
        except (OSError, subprocess.SubprocessError):
            return {"error": "无法打开浏览器，请到本项目的 GitHub 发布页面下载。"}

    def start_move(self, source: str, ids: list[str], target: str, directory: str) -> dict:
        with self._update_gate:
            if self._handing_off:
                return {"error": "正在更新并重启，请稍等。"}
            return super().start_move(source, ids, target, directory)

    def prepare_memory(self, source, ids, target, directory=''):
        with self._update_gate:
            if self._handing_off: return {'error': '正在更新并重启，请稍等。'}
            return super().prepare_memory(source, ids, target, directory)

    def deploy_memory(self):
        with self._update_gate:
            if self._handing_off: return {'error': '正在更新并重启，请稍等。'}
            return super().deploy_memory()

    def rollback_memory(self):
        with self._update_gate:
            if self._handing_off: return {'error': '正在更新并重启，请稍等。'}
            return super().rollback_memory()

    def start_full_from_memory(self, target, directory):
        with self._update_gate:
            if self._handing_off: return {'error': '正在更新并重启，请稍等。'}
            return super().start_full_from_memory(target, directory)

    def start_update(self) -> dict:
        with self._update_gate:
            if not self._update_audit and version_info().get('developmentPreview') is True:
                return {'error': '这是独立本地预览，请在正式版中检查更新。'}
            if self._update_state["phase"] in ("downloading", "preparing", "ready", "starting", "restarting"):
                return {"ok": True}
            if self._package is None:
                return {"error": "请先检查更新。此版本没有完整的自动更新包时，可以打开下载页。"}
            try:
                target = updater.running_bundle()
            except updater.UpdateError as error:
                return {"error": str(error)}
            package = dict(self._package)
            self._update_cancel.clear()
            self._update_state = {"phase": "downloading", "progress": 0}
            threading.Thread(target=self._prepare_update, args=(target, package), daemon=True).start()
            return {"ok": True}

    def _prepare_update(self, target: Path, package: dict) -> None:
        def progress(phase, value, step=None):
            with self._update_gate:
                self._update_state = {"phase": phase, "progress": value, "step": step,
                                      "cancelRequested": self._update_cancel.is_set()}
                if self._update_audit and step:
                    self._update_trace.append(step)
        try:
            job = updater.prepare(target, package, version_info()["release"], progress, self._update_cancel,
                                  download_asset=self._update_download)
            if self._update_audit:
                data = updater.read_job(job)
                data["audit"] = True
                updater.write_json(job, data)
            with self._update_gate:
                if self._update_cancel.is_set():
                    updater.discard(job)
                    raise updater.Cancelled("已取消下载，当前版本可以继续使用。")
                self._prepared = job
                self._update_state = {"phase": "ready", "progress": 100}
        except Exception as error:
            message = str(error) if isinstance(error, updater.UpdateError) else updates.failure(error)["error"] if isinstance(error, (OSError, ValueError, ImportError)) else "更新准备未完成，请检查文件权限和磁盘空间。当前版本未改动。"
            with self._update_gate:
                self._update_state = {"phase": "error", "progress": 0, "error": message}

    def update_status(self) -> dict:
        with self._update_gate:
            return dict(self._update_state)

    def cancel_update(self) -> dict:
        with self._update_gate:
            if self._handing_off:
                return {"error": "正在安全重启，请稍等。"}
            self._update_cancel.set()
            self._update_state["cancelRequested"] = True
            if self._prepared is not None:
                updater.discard(self._prepared)
                self._prepared = None
                self._update_state = {"phase": "error", "error": "已取消更新，当前版本可以继续使用。"}
            return {"ok": True}

    def apply_update(self) -> dict:
        with self._update_gate:
            if self._handing_off:
                return {"ok": True, "starting": True}
            if self._prepared is None or self._update_cancel.is_set():
                return {"error": "更新尚未准备好。"}
            if not super().can_close():
                return {"waiting": True}
            self._handing_off = True
            self._update_closing = False
            self._update_ui_ready = None
            self._update_failure = None
            self._update_handoff_id = handoff_id = object()
            self._update_state = {"phase": "starting", "progress": 100}
            threading.Thread(target=self._launch_update, args=(self._prepared, handoff_id), daemon=True).start()
        return {"ok": True, "starting": True}

    def _launch_update(self, job: Path, handoff_id) -> None:
        process = None
        phase = "starting_helper"
        acknowledged = threading.Event()

        def close_after_bridge_drains(result):
            # This is pywebview's one-way async callback: it needs no JS reply
            # after the window is gone. The page first drains its update calls.
            if not isinstance(result, dict) or result.get("ready") is not True or result.get("pendingUpdates") != 0:
                acknowledged.set()
                return
            with self._update_gate:
                if not self._handing_off or self._update_handoff_id is not handoff_id:
                    return
                self._update_ui_ready = result
                self._update_closing = True
                self._update_state = {"phase": "restarting", "progress": 100}
            self._window.destroy()
            acknowledged.set()

        try:
            process = updater.start_helper(job)
            phase = "draining_bridge"
            self._window.evaluate_js("window.aiFirstFinishUpdate()", callback=close_after_bridge_drains)
            if not acknowledged.wait(10) or not self._update_closing:
                raise updater.UpdateError("更新窗口未完成重启交接，当前版本未改动。请重试。")
            phase = "closing_window"
            if not self._window.events.closed.wait(10):
                raise updater.UpdateError("窗口尚未安全关闭，当前版本未改动。请重试。")
        except Exception as error:
            if process is not None:
                updater.stop_helper(process)
            with self._update_gate:
                if self._update_handoff_id is not handoff_id:
                    return
                self._update_handoff_id = None
                self._update_failure = {"phase": phase, "errorCode": type(error).__name__}
                self._handing_off = self._update_closing = False
                self._update_state = {"phase": "error", "progress": 0,
                                      "error": "更新重启交接未完成，当前版本未改动。可以重试或打开下载页。"}
            if not self._window.events.closed.is_set():
                try:
                    self._window.evaluate_js("window.aiFirstResumeUpdate()")
                except Exception:
                    pass

    def can_close(self) -> bool:
        if getattr(self,'_resume_busy',False): return False
        permitted = super().can_close()
        if not permitted: return False
        with self._update_gate:
            if self._handing_off:
                return permitted and self._update_closing
            if permitted:
                self._update_cancel.set()
        return permitted


def self_check(report: Path) -> bool:
    info = version_info()
    required = ("ui/index.html", "ui/app.js", "ui/workspace.js", "ui/workspace.css", "ui/assets/ai-first.png", "bin/txcript", 'ui/auto-resume.js','ui/reset-notices.js','ui/reset-notices.css','ui/assets/codex.png','reset-news/AI.First.ResetBridge','reset-news/AI.First.ResetBridge.deps.json','auto-resume-native/LICENSE','auto-resume-native/NOTICE')
    checks = {name: (ROOT / name).is_file() for name in required}
    from codex_auto_resume.paths import bundled_codex
    checks['bundledAutoResumeRuntime'] = bundled_codex().is_file()
    from codex_auto_resume.automation_checks import run as automation_checks
    checks.update(automation_checks())
    native_help = subprocess.run([str(bundled_codex()), 'exec', '--help'], capture_output=True, timeout=20)
    checks['nativeEphemeralSupport'] = native_help.returncode == 0 and all(flag in native_help.stdout for flag in (b'--ephemeral', b'--ignore-user-config', b'--sandbox', b'--json'))
    from codex_auto_resume.quota import QuotaSnapshot, QuotaWindow, should_redeem_weekly_reset
    checks['weeklyCreditRequiresExhaustion'] = all(
        should_redeem_weekly_reset(QuotaSnapshot(primary=QuotaWindow(used_percent=100, window_minutes=300),
            secondary=QuotaWindow(used_percent=used, window_minutes=10080), reset_credit_count=1), 1.0)[0] is expected
        for used, expected in ((99.0, False), (99.9, False), (100.0, True)))
    from branding import display_name
    from Foundation import NSBundle, NSFileManager, NSProcessInfo
    expected_name = display_name(info.get('developmentPreview') is True)
    bundle = NSBundle.mainBundle()
    bundle_path = Path(sys.executable).parents[2]
    canonical = 'AI一手工具工作台预览.app' if info.get('developmentPreview') is True else 'AI一手工具工作台.app'
    finder_scope = ('product' if bundle_path.name == canonical else
                    'update-staging' if bundle_path.name == 'candidate.app' and bundle_path.parent.name.startswith('.ai-first-update-') else 'unknown')
    # Finder deliberately uses the physical name after an .app is renamed.
    # Update preflight runs in candidate.app; published app checks must still
    # prove the actual new product name at its canonical installation identity.
    finder_expected = 'candidate' if finder_scope == 'update-staging' else expected_name
    checks['localizedProductName'] = bundle.localizedInfoDictionary().get('CFBundleDisplayName') == expected_name
    finder_observed = str(NSFileManager.defaultManager().displayNameAtPath_(str(bundle_path))).removesuffix('.app')
    checks['finderDisplayName'] = finder_scope != 'unknown' and finder_observed == finder_expected
    checks['nativeProcessName'] = NSProcessInfo.processInfo().processName() == expected_name
    from release_highlights import parse as parse_highlights
    try:
        parse_highlights((ROOT/'ui/whats-new.json').read_text(encoding='utf-8'),info['release'])
        checks['bundledReleaseHighlights']=all((ROOT/'ui'/name).is_file() for name in ('whats-new.js','whats-new.html'))
    except (OSError,ValueError,TypeError): checks['bundledReleaseHighlights']=False
    result = subprocess.run([str(ROOT / "bin" / "txcript"), "--version"], capture_output=True, text=True, timeout=30)
    checks["native_engine"] = result.returncode == 0 and "txcript" in result.stdout
    if info.get('developmentPreview') is True:
        import plistlib
        with (Path(sys.executable).parents[1]/'Info.plist').open('rb') as stream:
            bundle = plistlib.load(stream)
        checks['developmentPreviewIsolation'] = (bundle.get('CFBundleIdentifier') == 'cn.aifirst.tools.preview'
            and Path(sys.executable).parents[2].name == 'AI一手工具工作台预览.app'
            and MacApi().workspace_info()['automaticChecks'] is False)
    report.parent.mkdir(parents=True, exist_ok=True)
    passed = all(checks.values())
    report.write_text(json.dumps({"passed": passed, "checks": checks, "version": info, "architecture": platform.machine(), "finderScope": finder_scope,
                                  "finderName": finder_observed, "expectedFinderName": finder_expected,
                                  "scope": "bundle resources and native engine; no real conversation access"}, indent=2), encoding="utf-8")
    return passed


def memory_check(report: Path) -> int:
    from core.memory_audit import run as audit_memory
    code = audit_memory(report)
    result = json.loads(report.read_text(encoding='utf-8'))
    details = result['checks']
    result.update(checks={item['name']: item['passed'] for item in details}, details=details,
                  architecture=platform.machine(), version=version_info())
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return code


def codex_import_check(report: Path) -> int:
    """Exercise the packaged shared converter/decoder, not a developer Python."""
    from core.codex_audit import run as audit_history
    code = audit_history(report)
    result = json.loads(report.read_text(encoding='utf-8'))
    result.update(architecture=platform.machine(), version=version_info(),
                  host=platform.system(), frozen=bool(getattr(sys, 'frozen', False)))
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return code


def network_check(report: Path) -> bool:
    checks = {}
    token = os.environ.get("AI_FIRST_CI_UPDATE_TOKEN")
    try:
        context = updates.tls_context()
        checks["verifiedTls"] = context.verify_mode == updates.ssl.CERT_REQUIRED and context.check_hostname
        result = updates.check(version_info()["release"], token=token)
        checks["githubReleaseFeed"] = isinstance(result.get("available"), bool)
        checks["nativeSystemProxy"] = __import__("_scproxy") is not None
        error = None
    except (OSError, ValueError, TypeError, ImportError) as exception:
        error = updates.failure(exception)["errorCode"]
    passed = error is None and bool(checks) and all(checks.values())
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"passed": passed, "checks": checks, "errorCode": error, "authenticatedProbe": bool(token),
                                  "architecture": platform.machine(), "version": version_info(),
                                  "scope": "frozen HTTPS with native macOS trust and proxy support; public GitHub feed only"}, indent=2), encoding="utf-8")
    return passed


def smoke_check(window, api: MacApi, report: Path) -> None:
    result = {"passed": False, "error": "UI bridge did not become ready"}
    try:
        if not window.events.loaded.wait(45):
            raise TimeoutError("Cocoa page did not finish loading")
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            value = window.evaluate_js("JSON.stringify(window.__AI_FIRST_SMOKE__ || null)")
            if value and value != "null":
                result = json.loads(value)
                result["checks"]["nativeContentAttached"] = getattr(window, "_ai_first_content_attached", False) is True
                result["checks"]["bundledFileNavigation"] = getattr(window, "_ai_first_bundled_file_load", False) is True
                reminder = window.evaluate_js("!document.getElementById('workspace-download').hidden && document.getElementById('workspace-message').textContent.includes('synthetic-reminder-only')")
                if reminder:
                    result["checks"]["automaticUpdateReminder"] = api._smoke_check_calls == 1
                    result["checks"]["noUnrequestedDownload"] = api.update_status()["phase"] == "idle"
                    window.evaluate_js('''(async()=>{
                      const poll=async(fn)=>{for(let i=0;i<200;i++){if(fn())return;await new Promise(r=>setTimeout(r,50));}throw Error('resume_ui_timeout');};
                      const run=document.getElementById('resume-running'),boot=document.getElementById('resume-startup'),credit=document.getElementById('resume-credit'),timer=document.getElementById('resume-timer');
                      document.getElementById('workspace-resume').click();await poll(()=>!run.disabled);
                      if(!credit.disabled||credit.getAttribute('aria-checked')!=='false')throw Error('inactive_credit');
                      run.click();await poll(()=>!run.disabled&&run.getAttribute('aria-checked')==='true');
                      credit.click();await poll(()=>!credit.disabled&&credit.getAttribute('aria-checked')==='true');
                      credit.click();await poll(()=>!credit.disabled&&credit.getAttribute('aria-checked')==='false'&&run.getAttribute('aria-checked')==='true');
                      timer.click();await poll(()=>!timer.disabled&&timer.getAttribute('aria-checked')==='true');
                      boot.click();await poll(()=>!boot.disabled&&boot.getAttribute('aria-checked')==='true');
                      run.click();await poll(()=>!run.disabled&&run.getAttribute('aria-checked')==='false'&&boot.getAttribute('aria-checked')==='true'&&credit.disabled&&credit.getAttribute('aria-checked')==='false');
                      timer.click();await poll(()=>!timer.disabled&&timer.getAttribute('aria-checked')==='false'&&boot.getAttribute('aria-checked')==='false');
                      document.getElementById('workspace-mover').click();window.__RESUME_SMOKE__=true;
                    })().catch(()=>window.__RESUME_SMOKE__=false);''')
                    for _ in range(80):
                        resume_ui=window.evaluate_js('window.__RESUME_SMOKE__===true')
                        if resume_ui: break
                        time.sleep(.25)
                    result['checks']['autoResumeControlBridge']=bool(resume_ui)
                    result['checks']['independentAutomationBridge']=bool(resume_ui)
                    window.evaluate_js('''(async()=>{
                      const poll=async(fn)=>{for(let i=0;i<200;i++){if(fn())return;await new Promise(r=>setTimeout(r,50));}throw Error('reset_ui_timeout');};
                      document.getElementById('workspace-resume').click();
                      const toggle=document.getElementById('reset-enabled');await poll(()=>!toggle.disabled);
                      toggle.click();await poll(()=>!toggle.disabled&&toggle.getAttribute('aria-checked')==='false');
                      if(document.getElementById('resume-running').getAttribute('aria-checked')!=='false')throw Error('unexpected_resume');
                      toggle.click();await poll(()=>!toggle.disabled&&toggle.getAttribute('aria-checked')==='true');
                      document.getElementById('reset-today').click();
                      window.__RESET_SMOKE__=document.querySelectorAll('.reset-day').length===42&&!!document.querySelector('.reset-day[aria-pressed="true"]');
                      document.getElementById('workspace-mover').click();
                    })().catch(()=>window.__RESET_SMOKE__=false);''')
                    reset_ui=False
                    for _ in range(80):
                        reset_ui=window.evaluate_js('window.__RESET_SMOKE__===true')
                        if reset_ui: break
                        time.sleep(.25)
                    result['checks']['resetCalendarBridge']=reset_ui is True
                    notice_state=getattr(api,'_notice_fixture',None)
                    resume_state=getattr(api,'_resume_fixture',None)
                    result['checks']['independentReminderSwitch']=(reset_ui is True and isinstance(notice_state,dict)
                        and notice_state.get('enabled') is True and isinstance(resume_state,dict) and resume_state.get('running') is False)
                    window.evaluate_js('''(async()=>{
                      const diagnostic=window.__RELEASE_NOTES_DIAGNOSTICS__={phase:'opening'};
                      const poll=async(fn)=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,50));}throw Error('notes_timeout');};
                      const trigger=document.getElementById('workspace-version'),dialog=document.getElementById('release-highlights');
                      trigger.click();await poll(()=>dialog.open);
                      diagnostic.phase='opened';diagnostic.rows=document.querySelectorAll('.release-item').length;diagnostic.focus=document.activeElement.id;
                      const rendered=document.querySelectorAll('.release-item').length>0&&document.activeElement.id==='release-done';
                      document.getElementById('release-done').click();await poll(()=>!dialog.open);
                      trigger.click();await poll(()=>dialog.open);document.getElementById('release-close').click();
                      await poll(()=>!dialog.open&&document.activeElement===trigger);
                      diagnostic.phase='closed';diagnostic.finalFocus=document.activeElement.id;diagnostic.closed=!dialog.open;
                      window.__RELEASE_NOTES_SMOKE__=rendered&&!dialog.open&&document.activeElement===trigger;
                    })().catch(error=>{window.__RELEASE_NOTES_SMOKE__=false;window.__RELEASE_NOTES_DIAGNOSTICS__={...(window.__RELEASE_NOTES_DIAGNOSTICS__||{}),errorName:error.name};});''')
                    release_ui=False
                    for _ in range(80):
                        release_ui=window.evaluate_js('window.__RELEASE_NOTES_SMOKE__===true')
                        if release_ui and api._release_highlights and api._release_highlights.has_seen():break
                        time.sleep(.25)
                    result['checks']['nativeReleaseHighlightsDialog']=release_ui is True
                    result['checks']['releaseHighlightsAcknowledgement']=bool(release_ui and api._release_highlights and api._release_highlights.has_seen())
                    result['releaseHighlightsDiagnostics']=json.loads(window.evaluate_js('JSON.stringify(window.__RELEASE_NOTES_DIAGNOSTICS__||{})'))
                    result["passed"] = all(result["checks"].values())
                    break
            time.sleep(0.25)
        else:
            result["passed"] = False
            result.setdefault("checks", {})["automaticUpdateReminder"] = False
    except Exception as error:
        result = {"passed": False, "error": type(error).__name__,
                  "checks": {"windowShown": window.events.shown.is_set() is True, "pageLoaded": window.events.loaded.is_set() is True,
                             "nativeContentAttached": getattr(window, "_ai_first_content_attached", False) is True}}
        try:
            from urllib.request import ProxyHandler, build_opener

            if window.real_url.startswith("http://127.0.0.1:"):
                with build_opener(ProxyHandler({})).open(window.real_url, timeout=5) as response:
                    result["diagnostics"] = {"localPageStatus": response.status, "localPageBytes": len(response.read(1024 * 1024)),
                                             "bridgeInjectionStarted": window.events.before_load.is_set()}
        except Exception as diagnostic:
            result["diagnostics"] = {"localPageError": type(diagnostic).__name__}
    finally:
        result.setdefault("diagnostics", {})["navigation"] = vars(window).get("_ai_first_navigation")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        window.destroy()


def isolate_profile(scratch: Path) -> None:
    common._isolated_home = scratch / "home"
    common._isolated_home.mkdir()
    updater._audit_state = scratch / "updates"
    for name in ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "COWORK_SESSIONS_DIR",
                 "WORKBUDDY_DIR", "WORKBUDDY_AI_DIR", "QWENWORK_DIR", "DOUBAO_WORK_DIR", "CURSOR_DESKTOP_USER_DIR",
                 "HERMES_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        os.environ[name] = str(scratch / name.lower())


def start_cocoa(worker) -> None:
    webview.settings["DEFAULT_HTTP_PORT"] = None
    webview.start(worker, gui="cocoa", private_mode=False)


def signal_bridge_ready(window) -> None:
    window.run_js("window.__AI_FIRST_BRIDGE_READY__=true;window.dispatchEvent(new CustomEvent('ai-first-ready'));")


def load_bundled_content(window) -> None:
    # The UI is static bundled content. Cocoa can read it directly, with read access
    # limited to the UI directory, rather than using a loopback HTTP navigation.
    from Foundation import NSURL
    from PyObjCTools import AppHelper
    from WebKit import WKNavigationActionPolicyAllow, WKNavigationActionPolicyCancel
    from webview.platforms.cocoa import BrowserView

    host = BrowserView.instances[window.uid]
    ui = (ROOT / "ui").resolve()
    page = ui / "index.html"
    url = page.as_uri()

    class AIFirstBundledPageDelegate(BrowserView.BrowserDelegate):
        def webView_decidePolicyForNavigationAction_decisionHandler_(self, view, action, handler):
            requested = action.request().URL()
            # File navigation has no HTTP headers. Only our exact bundled page
            # may navigate in the window that receives the privileged Python bridge.
            allowed = requested.isFileURL() and str(requested.path()) == str(page)
            handler(WKNavigationActionPolicyAllow if allowed else WKNavigationActionPolicyCancel)

    host._ai_first_file_delegate = AIFirstBundledPageDelegate.alloc().init()
    host.webview.setNavigationDelegate_(host._ai_first_file_delegate)

    def load_file(requested):
        if requested != url:
            raise ValueError("Only the bundled workspace page can use this loader")

        def navigate():
            host.webview.loadFileURL_allowingReadAccessToURL_(NSURL.fileURLWithPath_(str(page)),
                                                             NSURL.fileURLWithPath_(str(ui)))
            window._ai_first_bundled_file_load = True

        AppHelper.callAfter(navigate)

    host.load_url = load_file
    window.real_url = url
    if not host.webview.window():
        host.window.setContentView_(host.webview)
        host.window.makeFirstResponder_(host.webview)
    window._ai_first_content_attached = host.webview.window() is not None


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--network-test", action="store_true")
    parser.add_argument("--update-test", action="store_true")
    parser.add_argument('--resume-test', action='store_true')
    parser.add_argument('--memory-test', action='store_true')
    parser.add_argument('--codex-import-test', action='store_true')
    parser.add_argument('--reset-test', action='store_true')
    parser.add_argument('--copilot-refresh-test', action='store_true')
    parser.add_argument("--update-ui-audit", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
        from branding import apply_process_name
        apply_process_name(version_info().get('developmentPreview') is True)
    if sys.platform != "darwin":
        parser.error("This entry point runs on macOS. Windows uses workspace/AIFirst.Workspace.csproj.")
    if (args.self_test or args.smoke_test or args.network_test or args.update_test or args.resume_test or args.memory_test or args.codex_import_test or args.reset_test or args.copilot_refresh_test or args.update_ui_audit) and args.report is None:
        parser.error("Tests require --report")
    if args.self_test:
        return 0 if self_check(args.report) else 1
    if args.resume_test:
        from auto_resume_audit import audit
        return audit(args.report)
    if args.memory_test:
        return memory_check(args.report)
    if args.codex_import_test:
        return codex_import_check(args.report)
    if args.reset_test:
        from reset_audit import audit
        return audit(args.report)
    if args.copilot_refresh_test:
        from copilot_refresh_audit import audit
        return audit(args.report)
    if args.network_test:
        return 0 if network_check(args.report) else 1
    if args.update_test:
        updater.audit_update(updater.running_bundle(), args.report)
        return 0 if json.loads(args.report.read_text()).get("passed") is True else 1
    fixture = None
    if args.update_ui_audit:
        import update_audit

        fixture = update_audit.load_fixture(args.update_ui_audit, updater.running_bundle(), args.report)
    with tempfile.TemporaryDirectory(prefix="ai-first-macos-") as temporary:
        if args.smoke_test or fixture:
            # Canonicalize only our fresh synthetic root; /var is a system alias on Mac.
            isolate_profile(Path(temporary).resolve())
        import fcntl

        state = appdata() / "AI一手工具工作台"
        development = version_info().get('developmentPreview') is True
        if development and not args.smoke_test and not fixture:
            state = state / 'memory-preview'
            os.environ['AI_FIRST_MOVER_PREVIEW_DATA'] = str(state / 'mover')
        if fixture:
            state = fixture["root"] / "isolated-state"
            updater._audit_state = state / "updates"
        state.mkdir(parents=True, exist_ok=True)
        with (state / "workspace.lock").open("a") as instance:
            try:
                fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            api = MacApi(args.smoke_test)
            from release_highlights import Highlights
            api._release_highlights = Highlights(ROOT/'ui/whats-new.json', state, version_info()['release'])
            if getattr(sys,'frozen',False) and not args.smoke_test and not fixture:
                if not development: api.auto_resume_control('finish-update')
                try: reset_notices.Monitor().ensure()
                except (reset_notices.NoticeError, OSError, ValueError): pass
            if fixture:
                update_audit.configure(api, fixture)
            window = webview.create_window("AI一手工具箱", js_api=api,
                                           width=1280, height=820, min_size=(960, 640), background_color="#F6F8FB", text_select=False)
            api.bind(window)
            window.events.before_show += load_bundled_content
            if args.smoke_test or fixture:
                from cocoa_audit import observe_navigation

                window.events.before_show += observe_navigation
            window.events.loaded += signal_bridge_ready
            window.events.closing += lambda: window.evaluate_js("window.aiFirstBusyNotice && window.aiFirstBusyNotice()") if not api.can_close() else None
            worker = (lambda: smoke_check(window, api, args.report)) if args.smoke_test else None
            if fixture:
                worker = lambda: update_audit.click_update(window, api, fixture["root"])
            start_cocoa(worker)
            if fixture:
                return 0 if update_audit.finish_ui_report(window, api, args.report) else 1
    if args.smoke_test:
        return 0 if args.report.is_file() and json.loads(args.report.read_text(encoding="utf-8")).get("passed") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
