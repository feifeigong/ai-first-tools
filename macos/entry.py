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

PROJECT = Path(__file__).resolve().parent.parent
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(PROJECT / "dialog-mover"))
    sys.path.insert(0, str(PROJECT / "dialog-mover" / "vendor"))

import webview

from core import common, mover
from core.common import appdata, open_external
from main import Api
import updates
import updater

ROOT = Path(getattr(sys, "_MEIPASS", PROJECT / "artifacts" / "macos" / "resources"))


def version_info() -> dict:
    return json.loads((ROOT / "version.json").read_text(encoding="utf-8"))


class MacApi(Api):
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

    def workspace_info(self) -> dict:
        message = None
        receipt = updater.state_root() / "result.json"
        if receipt.is_file():
            try:
                result = json.loads(receipt.read_text(encoding="utf-8"))
                if result.get("version") == version_info()["release"]:
                    message = result.get("message")
                    receipt.unlink()
            except (OSError, ValueError):
                pass
        return {**version_info(), "platform": "macOS", "architecture": platform.machine(), "automaticChecks": True,
                "smokeAudit": self._smoke, "updateMessage": message}

    def check_update(self) -> dict:
        if self._smoke:
            self._smoke_check_calls += 1
            return {"available": True, "version": "synthetic-reminder-only", "canInstall": True}
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

    def start_update(self) -> dict:
        with self._update_gate:
            if self._update_state["phase"] in ("downloading", "preparing", "ready", "restarting"):
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
        try:
            job = updater.prepare(target, package, version_info()["release"], progress, self._update_cancel)
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
                return {"ok": True}
            if self._prepared is None or self._update_cancel.is_set():
                return {"error": "更新尚未准备好。"}
            if not super().can_close():
                return {"waiting": True}
            try:
                updater.start_helper(self._prepared)
            except (OSError, ValueError, updater.UpdateError):
                return {"error": "暂时无法启动更新，当前版本可以继续使用。请稍后重试。"}
            self._handing_off = True
            self._update_state = {"phase": "restarting", "progress": 100}
        self._window.destroy()
        return {"ok": True}

    def can_close(self) -> bool:
        permitted = super().can_close()
        if permitted and not self._handing_off:
            self._update_cancel.set()
        return permitted


def self_check(report: Path) -> bool:
    info = version_info()
    required = ("ui/index.html", "ui/app.js", "ui/workspace.js", "ui/workspace.css", "ui/assets/ai-first.png", "bin/txcript")
    checks = {name: (ROOT / name).is_file() for name in required}
    result = subprocess.run([str(ROOT / "bin" / "txcript"), "--version"], capture_output=True, text=True, timeout=30)
    checks["native_engine"] = result.returncode == 0 and "txcript" in result.stdout
    report.parent.mkdir(parents=True, exist_ok=True)
    passed = all(checks.values())
    report.write_text(json.dumps({"passed": passed, "checks": checks, "version": info, "architecture": platform.machine(),
                                  "scope": "bundle resources and native engine; no real conversation access"}, indent=2), encoding="utf-8")
    return passed


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
                reminder = window.evaluate_js("!document.getElementById('workspace-download').hidden && document.getElementById('workspace-message').textContent.includes('synthetic-reminder-only')")
                if reminder:
                    result["checks"]["automaticUpdateReminder"] = api._smoke_check_calls == 1
                    result["checks"]["noUnrequestedDownload"] = api.update_status()["phase"] == "idle"
                    result["passed"] = all(result["checks"].values())
                    break
            time.sleep(0.25)
        else:
            result["passed"] = False
            result.setdefault("checks", {})["automaticUpdateReminder"] = False
    except Exception as error:
        result = {"passed": False, "error": type(error).__name__,
                  "checks": {"windowShown": window.events.shown.is_set(), "pageLoaded": window.events.loaded.is_set()}}
        try:
            from urllib.request import ProxyHandler, build_opener

            if window.real_url.startswith("http://127.0.0.1:"):
                with build_opener(ProxyHandler({})).open(window.real_url, timeout=5) as response:
                    result["diagnostics"] = {"localPageStatus": response.status, "localPageBytes": len(response.read(1024 * 1024)),
                                             "bridgeInjectionStarted": window.events.before_load.is_set()}
        except Exception as diagnostic:
            result["diagnostics"] = {"localPageError": type(diagnostic).__name__}
    finally:
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


def attach_cocoa_content(window) -> None:
    # before_show is synchronous on Cocoa's UI thread. Attach the view before navigation,
    # rather than depending on didFinishNavigation to make it part of the window.
    from webview.platforms.cocoa import BrowserView

    host = BrowserView.instances[window.uid]
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
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This entry point runs on macOS. Windows uses workspace/AIFirst.Workspace.csproj.")
    if (args.self_test or args.smoke_test or args.network_test or args.update_test) and args.report is None:
        parser.error("Tests require --report")
    if args.self_test:
        return 0 if self_check(args.report) else 1
    if args.network_test:
        return 0 if network_check(args.report) else 1
    if args.update_test:
        updater.audit_update(updater.running_bundle(), args.report)
        return 0 if json.loads(args.report.read_text()).get("passed") is True else 1
    with tempfile.TemporaryDirectory(prefix="ai-first-macos-") as temporary:
        if args.smoke_test:
            isolate_profile(Path(temporary))
        import fcntl

        state = appdata() / "AI一手工具工作台"
        state.mkdir(parents=True, exist_ok=True)
        with (state / "workspace.lock").open("a") as instance:
            try:
                fcntl.flock(instance, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            api = MacApi(args.smoke_test)
            window = webview.create_window("AI一手工具工作台", str((ROOT / "ui" / "index.html").resolve()), js_api=api,
                                           width=1280, height=820, min_size=(960, 640), background_color="#F6F8FB", text_select=False)
            api.bind(window)
            window.events.before_show += attach_cocoa_content
            window.events.loaded += signal_bridge_ready
            window.events.closing += lambda: window.evaluate_js("window.aiFirstBusyNotice && window.aiFirstBusyNotice()") if not api.can_close() else None
            worker = (lambda: smoke_check(window, api, args.report)) if args.smoke_test else None
            start_cocoa(worker)
    if args.smoke_test:
        return 0 if args.report.is_file() and json.loads(args.report.read_text(encoding="utf-8")).get("passed") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
