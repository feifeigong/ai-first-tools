"""Offline frozen-runtime checks; never inspect a user's account or conversations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .app_server import AppServerClient
from .paths import bundled_codex
from .procutil import hidden_popen


def run(report: Path) -> int:
    results = []
    def check(name, test):
        try:
            test()
            results.append({"name": name, "passed": True})
        except Exception as error:
            results.append({"name": name, "passed": False, "errorType": type(error).__name__})
    def require(value):
        if not value:
            raise AssertionError()
    with tempfile.TemporaryDirectory(prefix="ai-first-resume-runtime-") as temporary:
        root = Path(temporary)
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(root / "local")
        env["APPDATA"] = str(root / "roaming")
        env["CODEX_HOME"] = str(root / "codex")
        env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        env.pop("CODEX_BIN", None)
        env.pop("PYTHONPATH", None)
        env["AI_FIRST_MANUAL_WATCH"] = "1"
        codex_home = Path(env["CODEX_HOME"])
        codex_home.mkdir()
        (codex_home / "config.toml").write_text('cli_auth_credentials_store = "file"\n[features]\nplugins = false\n', encoding="utf-8")
        check("Frozen Python and package-native Codex exist", lambda: require(getattr(sys, "frozen", False) and bundled_codex().is_file()))
        def credit_boundary():
            from .quota import QuotaSnapshot, QuotaWindow, should_redeem_weekly_reset
            for used, expected in ((99.0, False), (99.9, False), (100.0, True)):
                snapshot = QuotaSnapshot(primary=QuotaWindow(used_percent=100, window_minutes=300),
                    secondary=QuotaWindow(used_percent=used, window_minutes=10080), reset_credit_count=1)
                require(should_redeem_weekly_reset(snapshot, 1.0)[0] is expected)
        check("Frozen credit policy never spends before full weekly exhaustion", credit_boundary)
        def automation_policy():
            from .automation_checks import run as audit
            require(all(audit().values()))
        check("Frozen independent automation preserves timer deduplication and spending permissions", automation_policy)
        def native_version():
            process = hidden_popen([str(bundled_codex()), "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            output, _ = process.communicate(timeout=20)
            require(process.returncode == 0 and b"codex" in output.lower())
        check("Native Codex runs without external Python Node or CLI", native_version)
        def native_ephemeral():
            process = hidden_popen([str(bundled_codex()), 'exec', '--help'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            output, _ = process.communicate(timeout=20)
            require(process.returncode == 0 and all(flag in output for flag in (b'--ephemeral', b'--ignore-user-config', b'--sandbox', b'--json')))
        check("Native Codex supports the isolated ephemeral request flags without model requests", native_ephemeral)
        def isolated_bridge():
            with AppServerClient([str(bundled_codex())], env=env, timeout=20) as client:
                result = client.request("account/read", {"refreshToken": False})
                require(result.get("account") is None)
        check("Native app-server handshakes with an isolated signed-out profile", isolated_bridge)
        def background_lifecycle():
            state = Path(env["LOCALAPPDATA"]) / "vibcoding" / "codex-auto-resume"
            state.mkdir(parents=True)
            (state / "config.json").write_text(json.dumps({"enabled": False, "poll_seconds": 5, "codex_home": str(codex_home), "state_dir": str(state)}), encoding="utf-8")
            process = hidden_popen([sys.executable, "watch", "--quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline and not (state / "state.json").exists() and process.poll() is None:
                    time.sleep(0.1)
                require(process.poll() is None and (state / "watch.pid").read_text().strip() == str(process.pid))
                require(json.loads((state / "state.json").read_text())["last_status"] == "disabled")
                status_report = root / "watch-status.json"
                protected = {name: (state / name).read_bytes() for name in ("config.json", "watch.pid", "watch.owner.json")}
                probe = hidden_popen([sys.executable, "--watch-status", str(status_report)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                require(probe.wait(timeout=10) == 0)
                status = json.loads(status_report.read_text(encoding="utf-8"))
                require(status["ok"] and status["running"] and status["ready"] and status["pid"] == process.pid)
                require(Path(status["executable"]).resolve() == Path(sys.executable).resolve())
                require(all((state / name).read_bytes() == content for name, content in protected.items()))
                stop = hidden_popen([sys.executable, "--request-stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                require(stop.wait(timeout=10) == 0)
                require(process.wait(timeout=10) == 0)
                require(not (state / "watch.pid").exists())
                probe = hidden_popen([sys.executable, "--watch-status", str(status_report)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                require(probe.wait(timeout=10) == 0 and not json.loads(status_report.read_text(encoding="utf-8"))["running"])
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
        check("Frozen background starts single instance and stops gracefully using synthetic disabled work", background_lifecycle)
    passed = sum(item["passed"] for item in results)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"passed": passed, "failed": len(results) - passed, "scope": "isolated synthetic profile, no model request, no external runtime", "results": results}, indent=2), encoding="utf-8")
    return 0 if passed == len(results) else 1
