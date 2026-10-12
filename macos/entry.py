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

PROJECT = Path(__file__).resolve().parent.parent
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(PROJECT / "dialog-mover"))
    sys.path.insert(0, str(PROJECT / "dialog-mover" / "vendor"))

import webview

from core import mover
from core.common import appdata, open_external
from main import Api
import updates

ROOT = Path(getattr(sys, "_MEIPASS", PROJECT / "artifacts" / "macos" / "resources"))


def version_info() -> dict:
    return json.loads((ROOT / "version.json").read_text(encoding="utf-8"))


class MacApi(Api):
    def __init__(self, smoke: bool = False) -> None:
        super().__init__()
        self._smoke = smoke
        self._release = None
        self._update_lock = threading.Lock()

    def workspace_info(self) -> dict:
        return {**version_info(), "platform": "macOS", "architecture": platform.machine(), "automaticChecks": not self._smoke}

    def check_update(self) -> dict:
        if not self._update_lock.acquire(blocking=False):
            return {"error": "正在检查更新，请稍等。"}
        try:
            result = updates.check(version_info()["release"])
            self._release = result.get("url")
            return result
        except (OSError, ValueError, TypeError):
            return {"error": "暂时无法连接 GitHub，您可以继续使用，稍后再检查。"}
        finally:
            self._update_lock.release()

    def open_update(self) -> dict:
        if self._release is None:
            return {"error": "请先检查更新。"}
        try:
            open_external(self._release)
            return {"ok": True}
        except (OSError, subprocess.SubprocessError):
            return {"error": "无法打开浏览器，请到本项目的 GitHub 发布页面下载。"}


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


def smoke_check(window, report: Path) -> None:
    result = {"passed": False, "error": "UI bridge did not become ready"}
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            value = window.evaluate_js("JSON.stringify(window.__AI_FIRST_SMOKE__ || null)")
            if value and value != "null":
                result = json.loads(value)
                break
            time.sleep(0.25)
    except Exception as error:
        result = {"passed": False, "error": type(error).__name__}
    finally:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        window.destroy()


def isolate_profile(scratch: Path) -> None:
    for name in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "COWORK_SESSIONS_DIR",
                 "WORKBUDDY_DIR", "WORKBUDDY_AI_DIR", "QWENWORK_DIR", "DOUBAO_WORK_DIR", "CURSOR_DESKTOP_USER_DIR",
                 "HERMES_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        os.environ[name] = str(scratch / name.lower())
    Path(os.environ["HOME"]).mkdir()


def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This entry point runs on macOS. Windows uses workspace/AIFirst.Workspace.csproj.")
    if (args.self_test or args.smoke_test) and args.report is None:
        parser.error("Tests require --report")
    if args.self_test:
        return 0 if self_check(args.report) else 1
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
            window = webview.create_window("AI一手工具工作台", str(ROOT / "ui" / "index.html"), js_api=api,
                                           width=1280, height=820, min_size=(960, 640), background_color="#F6F8FB", text_select=False)
            api.bind(window)
            window.events.closing += lambda: window.evaluate_js("window.aiFirstBusyNotice && window.aiFirstBusyNotice()") if not api.can_close() else None
            worker = (lambda: smoke_check(window, args.report)) if args.smoke_test else None
            webview.start(worker, gui="cocoa", private_mode=True)
    if args.smoke_test:
        return 0 if args.report.is_file() and json.loads(args.report.read_text(encoding="utf-8")).get("passed") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
