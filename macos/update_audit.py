"""Frozen, isolated native update-click audit; never uses installed apps or accounts."""
from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import updater
import updates

STEPS = ["mounting", "checking_current", "checking_package", "copying", "preparing_helper", "verifying", "fingerprinting", "unmounting"]


def load_fixture(path: Path, target: Path, report: Path) -> dict:
    root = path.parent.resolve()
    if path.is_symlink() or path.name != "fixture.json" or not root.name.startswith("ai-first-update-audit-") \
            or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()) \
            or target.resolve() != root / updater.APP_NAME or not report.resolve().is_relative_to(root):
        raise updater.UpdateError("更新审计必须使用隔离临时应用。")
    data = json.loads(path.read_text())
    if updates.release_key(data.get("version", "")) is None or data.get("architecture") != platform.machine() \
            or not re.fullmatch(r"[0-9a-f]{64}", data.get("digest", "")):
        raise updater.UpdateError("隔离更新样例无效。")
    for name in ("fixture.dmg", "fixture-sums.txt"):
        file = root / name
        if file.is_symlink() or not file.is_file() or file.resolve().parent != root:
            raise updater.UpdateError("隔离更新文件位置无效。")
    return {**data, "root": root}


def configure(api, fixture: dict) -> None:
    root = fixture["root"]
    api._update_audit = True
    api._package = {"version": fixture["version"], "architecture": fixture["architecture"],
                    "dmg": {"name": "fixture.dmg", "digest": fixture["digest"]}, "sums": {}}

    def download(asset, destination, progress, cancelled):
        if not destination.resolve().is_relative_to(root) or cancelled.is_set():
            raise updater.Cancelled("隔离更新已取消。")
        source = root / ("fixture.dmg" if asset is api._package["dmg"] else "fixture-sums.txt")
        shutil.copy2(source, destination)
        if source.name == "fixture.dmg":
            with destination.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != fixture["digest"]:
                    raise updater.UpdateError("隔离更新包完整性校验失败。")
        progress(100)

    # start_update takes a shallow package snapshot; nested asset identity is preserved.
    api._update_download = download
    api._update_audit_clicked = False


def click_update(window, api, root: Path) -> None:
    try:
        if not window.events.loaded.wait(45):
            return
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            ready = window.evaluate_js("Boolean(window.__AI_FIRST_BRIDGE_READY__ && !document.getElementById('workspace-update').disabled)")
            if ready:
                break
            time.sleep(0.2)
        else:
            return
        window.evaluate_js("document.getElementById('workspace-update').click()")
        while time.monotonic() < deadline:
            visible = window.evaluate_js("!document.getElementById('workspace-download').hidden")
            if visible:
                break
            time.sleep(0.2)
        else:
            return
        api._update_audit_clicked = True
        window.evaluate_js("document.getElementById('workspace-download').click()")
        # No evaluate_js requests race window closure after the click.
        while not window.events.closed.wait(0.2):
            state = api.update_status()
            updater.write_json(root / "progress.json", {"phase": state["phase"], "step": state.get("step")})
            if state["phase"] == "error":
                window.destroy()
                return
    except Exception:
        window.destroy()


def finish_ui_report(window, api, report: Path) -> bool:
    ready = api._update_ui_ready or {}
    checks = {"nativeUpdateClick": api._update_audit_clicked is True,
              "preparationStages": api._update_trace == STEPS,
              "bridgeDrained": ready.get("ready") is True and ready.get("pendingUpdates") == 0,
              "windowClosed": window.events.closed.is_set()}
    updater.write_json(report, {"passed": all(checks.values()), "checks": checks,
                                "job": str(api._prepared) if api._prepared else None,
                                "handoffFailure": api._update_failure,
                                "phase": api.update_status()["phase"]})
    return all(checks.values())


def audit_update(app: Path, report: Path) -> None:
    checks = dict.fromkeys(("preparationStages", "nativeUpdateClick", "bridgeDrained", "nativeParentExit", "replacement",
                            "nativeRelaunch", "backupPreserved", "version", "repeatNativeRelaunch"), False)
    diagnostics = {}
    version = json.loads((app / "Contents/Resources/version.json").read_text())["release"]
    with tempfile.TemporaryDirectory(prefix="ai-first-update-audit-") as temporary:
        root = Path(temporary).resolve()
        process = None
        try:
            diagnostics["phase"] = "fixture"
            target = root / updater.APP_NAME
            updater.command(["/usr/bin/ditto", str(app), str(target)])
            (target / "Contents/Resources/version.json").write_text(json.dumps({"version": "0.4.0", "release": "0.4.0-macos-preview.2"}))
            updater.command(["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(target)])
            fixture = root / "fixture"
            fixture.mkdir()
            updater.command(["/usr/bin/ditto", str(app), str(fixture / updater.APP_NAME)])
            dmg = root / "fixture.dmg"
            updater.command(["/usr/bin/hdiutil", "create", "-volname", "AI First Update Audit", "-srcfolder", str(fixture), "-format", "UDZO", str(dmg)])
            with dmg.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            (root / "fixture-sums.txt").write_text(f"{digest}  fixture.dmg\n")
            config = root / "fixture.json"
            updater.write_json(config, {"version": version, "architecture": platform.machine(), "digest": digest})
            ui_report = root / "ui-handoff.json"
            diagnostics["phase"] = "native_click"
            process = updater.start_app(target, ("--update-ui-audit", str(config), "--report", str(ui_report)))
            process.wait(timeout=120)
            diagnostics["parentReturnCode"] = process.returncode
            ui = json.loads(ui_report.read_text()) if ui_report.is_file() else {}
            diagnostics["uiChecks"] = ui.get("checks")
            diagnostics["handoffFailure"] = ui.get("handoffFailure")
            for key in ("preparationStages", "nativeUpdateClick", "bridgeDrained"):
                checks[key] = ui.get("checks", {}).get(key) is True
            checks["nativeParentExit"] = process.returncode == 0 and ui.get("checks", {}).get("windowClosed") is True
            if not all(checks[key] for key in ("nativeParentExit", "bridgeDrained", "preparationStages", "nativeUpdateClick")):
                raise updater.UpdateError("隔离窗口点击和退出检查失败。")
            job = Path(ui["job"])
            if job.resolve().parent.parent != root or not job.parent.name.startswith(".ai-first-update-"):
                raise updater.UpdateError("隔离交接任务位置无效。")
            data = updater.read_job(job)
            diagnostics["phase"] = "helper"
            completion = job.parent / "completion.json"
            deadline = time.monotonic() + 150
            while not completion.is_file() and time.monotonic() < deadline:
                time.sleep(0.25)
            completed = json.loads(completion.read_text()) if completion.is_file() else {}
            receipt = root / "isolated-state/updates/result.json"
            outcome = json.loads(receipt.read_text()) if receipt.is_file() else {}
            relaunch_report = job.parent / "relaunch.json"
            relaunched = json.loads(relaunch_report.read_text()) if relaunch_report.is_file() else {}
            diagnostics.update({"helperReturnCode": completed.get("returnCode"), "receipt": receipt.is_file(),
                                "preflightReport": (job.parent / "probe.json").is_file(), "relaunchChecks": relaunched.get("checks"),
                                "relaunchError": relaunched.get("error"), "relaunchDiagnostics": relaunched.get("diagnostics")})
            checks["replacement"] = completed.get("returnCode") == 0 and completed.get("nonce") == data["nonce"] and outcome.get("success") is True
            checks["nativeRelaunch"] = relaunched.get("passed") is True
            checks["backupPreserved"] = (job.parent / "backup.app").is_dir()
            checks["version"] = json.loads((target / "Contents/Resources/version.json").read_text())["release"] == version
            if checks["replacement"] and checks["nativeRelaunch"]:
                diagnostics["phase"] = "repeat_relaunch"
                repeated_report = job.parent / "repeat-relaunch.json"
                process = updater.start_app(target, ("--smoke-test", "--report", str(repeated_report)))
                process.wait(timeout=120)
                repeat = json.loads(repeated_report.read_text()) if repeated_report.is_file() else {}
                checks["repeatNativeRelaunch"] = process.returncode == 0 and repeat.get("passed") is True
                diagnostics["repeatRelaunch"] = repeat
            if all(checks.values()):
                diagnostics["phase"] = "complete"
        except Exception as error:
            diagnostics["errorCode"] = type(error).__name__
            if (root / "progress.json").is_file():
                diagnostics["lastUIState"] = json.loads((root / "progress.json").read_text())
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
            report.write_text(json.dumps({"passed": all(checks.values()), "checks": checks, "version": {"release": version},
                                          "architecture": platform.machine(), "diagnostics": diagnostics,
                                          "scope": "frozen Cocoa button click, real bridge handoff, native parent exit, helper, atomic replacement and two Cocoa relaunches; synthetic download fixture only"}, indent=2))
