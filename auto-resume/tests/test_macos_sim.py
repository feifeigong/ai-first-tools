from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_auto_resume.cli import cmd_autostart
from codex_auto_resume.paths import default_state_dir, resolve_codex_command, tool_root
from codex_auto_resume.procutil import hidden_kwargs, hidden_popen, process_running


ROOT = tool_root()
INSTALL_MAC = ROOT / "scripts" / "install-macos.sh"
UNINSTALL_MAC = ROOT / "scripts" / "uninstall-macos.sh"


def _git_bash() -> str | None:
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(candidate).exists():
            return candidate
    which = shutil.which("bash")
    if which and "WindowsApps" not in which and "wsl" not in which.lower():
        return which
    return None


class MacPathTests(unittest.TestCase):
    def test_state_dir_is_application_support(self) -> None:
        with patch("codex_auto_resume.paths.sys.platform", "darwin"):
            path = default_state_dir()
        self.assertEqual(
            path,
            Path.home() / "Library" / "Application Support" / "vibcoding" / "codex-auto-resume",
        )

    def test_hidden_start_has_no_windows_flags(self) -> None:
        with patch("codex_auto_resume.procutil.sys.platform", "darwin"):
            self.assertEqual(hidden_kwargs(), {})

    def test_process_running_uses_os_kill_not_tasklist(self) -> None:
        with (
            patch("codex_auto_resume.procutil.sys.platform", "darwin"),
            patch("codex_auto_resume.procutil.os.kill") as kill,
        ):
            self.assertTrue(process_running(os.getpid()))
            kill.assert_called_once_with(os.getpid(), 0)

        with (
            patch("codex_auto_resume.procutil.sys.platform", "darwin"),
            patch("codex_auto_resume.procutil.os.kill", side_effect=OSError),
        ):
            self.assertFalse(process_running(999_999_999))

    def test_finds_bundled_chatgpt_codex(self) -> None:
        bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")

        def fake_exists(self: Path) -> bool:
            return self == bundled

        with (
            patch("codex_auto_resume.paths.sys.platform", "darwin"),
            patch.dict(os.environ, {"CODEX_BIN": ""}, clear=False),
            patch("codex_auto_resume.paths.shutil.which", return_value=None),
            patch("codex_auto_resume.paths._find_native_codex", return_value=None),
            patch("codex_auto_resume.paths._find_node_js_codex", return_value=None),
            patch.object(Path, "exists", fake_exists),
        ):
            self.assertEqual(resolve_codex_command(None), [str(bundled)])

    def test_finds_path_codex_without_cmd_wrapper(self) -> None:
        unix = "/usr/local/bin/codex"
        with (
            patch("codex_auto_resume.paths.sys.platform", "darwin"),
            patch.dict(os.environ, {"CODEX_BIN": ""}, clear=False),
            patch("codex_auto_resume.paths.shutil.which", return_value=unix),
            patch("codex_auto_resume.paths._find_native_codex", return_value=None),
            patch("codex_auto_resume.paths._find_node_js_codex", return_value=None),
            patch.object(Path, "exists", lambda self: False),
        ):
            self.assertEqual(resolve_codex_command(None), [unix])
            self.assertFalse(unix.lower().endswith((".cmd", ".bat", ".ps1")))


class MacAutostartTests(unittest.TestCase):
    def test_cli_install_calls_macos_script(self) -> None:
        with (
            patch("codex_auto_resume.cli.sys.platform", "darwin"),
            patch("codex_auto_resume.cli.subprocess.run") as run,
        ):
            run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            self.assertEqual(cmd_autostart(True), 0)
            args = run.call_args[0][0]
            self.assertEqual(args[0], "/bin/bash")
            self.assertTrue(str(args[1]).endswith("install-macos.sh"))
            self.assertTrue(Path(args[1]).exists())

    def test_cli_uninstall_calls_macos_script(self) -> None:
        with (
            patch("codex_auto_resume.cli.sys.platform", "darwin"),
            patch("codex_auto_resume.cli.subprocess.run") as run,
        ):
            run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            self.assertEqual(cmd_autostart(False), 0)
            args = run.call_args[0][0]
            self.assertTrue(str(args[1]).endswith("uninstall-macos.sh"))

    def test_launchagent_runs_same_watch_quiet(self) -> None:
        text = INSTALL_MAC.read_text(encoding="utf-8")
        self.assertIn("watch", text)
        self.assertIn("--quiet", text)
        self.assertIn("run.py", text)
        self.assertIn("com.vibcoding.codex-auto-resume", text)
        self.assertIn("RunAtLoad", text)
        self.assertIn("KeepAlive", text)
        self.assertIn("CODEX_HOME", text)
        self.assertNotIn("tasklist", text)
        self.assertNotIn("pythonw", text)
        self.assertNotIn("codex.cmd", text)
        self.assertNotIn("Ctrl+C", text)

    def test_uninstall_removes_launchagent(self) -> None:
        text = UNINSTALL_MAC.read_text(encoding="utf-8")
        self.assertIn("bootout", text)
        self.assertIn("com.vibcoding.codex-auto-resume", text)
        self.assertIn("rm -f", text)

    def test_bash_syntax(self) -> None:
        bash = _git_bash()
        if bash is None:
            self.skipTest("本机没有 Git Bash，跳过脚本语法检查")
        for script in (INSTALL_MAC, UNINSTALL_MAC):
            completed = subprocess.run(
                [bash, "-n", script.as_posix()],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


class MacSharedLogicTests(unittest.TestCase):
    def test_new_features_live_in_shared_python(self) -> None:
        src = ROOT / "src" / "codex_auto_resume"
        for name in ("daemon.py", "redeem.py", "quota.py", "config.py", "app_server.py"):
            text = (src / name).read_text(encoding="utf-8")
            self.assertNotIn("sys.platform", text)
            self.assertNotIn("win32", text)
            self.assertNotIn("darwin", text)

    def test_hidden_popen_on_darwin_does_not_pass_create_no_window(self) -> None:
        with (
            patch("codex_auto_resume.procutil.sys.platform", "darwin"),
            patch("codex_auto_resume.procutil.subprocess.Popen") as popen,
            tempfile.TemporaryDirectory() as raw,
        ):
            marker = Path(raw) / "ok.txt"
            popen.return_value = object()
            hidden_popen(["python", "-c", "pass"], cwd=raw)
            kwargs = popen.call_args.kwargs
            self.assertNotIn("creationflags", kwargs)
            self.assertNotIn("startupinfo", kwargs)
            marker.write_text("ok", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
