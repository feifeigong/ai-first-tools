from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_auto_resume.resume import spawn_resume


class FakeProc:
    def __init__(self, pid: int, hang: bool = True) -> None:
        self.pid = pid
        self._code = None if hang else 0

    def poll(self):
        return self._code

    def wait(self, timeout=None):
        return self._code

    def terminate(self) -> None:
        self._code = 1

    def kill(self) -> None:
        self._code = 1


class ResumeBusyTests(unittest.TestCase):
    def test_active_writer_falls_back_to_queue_even_if_exec_hangs(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            log_file = Path(raw) / "resume.log"
            calls: list[list[str]] = []

            def fake_popen(args, **kwargs):
                calls.append(list(args))
                if "resume" in args:
                    handle = kwargs["stdout"]
                    handle.write(
                        "Error: thread/resume failed: thread abc already has an active writer (code -32600)\n"
                    )
                    handle.flush()
                    return FakeProc(111)
                return FakeProc(222, hang=False)

            with patch("codex_auto_resume.resume.resolve_codex_command", return_value=["codex"]):
                with patch("codex_auto_resume.resume.hidden_popen", side_effect=fake_popen):
                    pid, mode = spawn_resume(
                        thread_id="abc",
                        prompt="继续",
                        cwd=raw,
                        log_file=log_file,
                        extra_args=[],
                        skip_git_repo_check=True,
                        prefer_queue_if_busy=True,
                        codex_bin=None,
                        extra_env=None,
                    )

            self.assertEqual(mode, "queue")
            self.assertEqual(pid, 222)
            self.assertEqual(len(calls), 2)
            self.assertIn("queue", calls[1])
            self.assertIn("--thread", calls[1])
            text = log_file.read_text(encoding="utf-8")
            self.assertIn("fallback to queue", text)

    def test_old_active_writer_log_does_not_force_queue(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as raw:
            log_file = Path(raw) / "resume.log"
            log_file.write_text(
                "old run: already has an active writer (code -32600)\n",
                encoding="utf-8",
            )

            def fake_popen(args, **kwargs):
                return FakeProc(333, hang=False)

            with patch("codex_auto_resume.resume.resolve_codex_command", return_value=["codex"]):
                with patch("codex_auto_resume.resume.hidden_popen", side_effect=fake_popen):
                    pid, mode = spawn_resume(
                        thread_id="abc",
                        prompt="继续",
                        cwd=raw,
                        log_file=log_file,
                        extra_args=[],
                        skip_git_repo_check=True,
                        prefer_queue_if_busy=True,
                        codex_bin=None,
                        extra_env=None,
                    )

            self.assertEqual(mode, "exec-resume-finished")
            self.assertEqual(pid, 333)


if __name__ == "__main__":
    unittest.main()
