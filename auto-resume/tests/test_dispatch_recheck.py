"""Exercise the final submission boundary using synthetic on-disk rollouts."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from codex_auto_resume import daemon
from codex_auto_resume.config import AppConfig
from codex_auto_resume.quota import QuotaSnapshot, QuotaWindow
from codex_auto_resume.sessions import scan_waiting_sessions
from codex_auto_resume.state import AppState, ThreadState, load_state, save_state


THREAD = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


class OfflineQuota:
    def read(self, now):
        return QuotaSnapshot(
            primary=QuotaWindow(0, int(now + 3600), 300),
            secondary=QuotaWindow(10, int(now + 86400), 10080),
            source="app-server", fetched_at=now,
        )

    def try_redeem(self, *args, **kwargs):
        raise AssertionError("No reset-credit request is permitted")


class DispatchRecheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="resume-dispatch-synthetic-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cfg = AppConfig(codex_home=str(self.root / "codex"),
                             state_dir=str(self.root / "state"),
                             auto_redeem_weekly_reset=False,
                             auto_start_five_hour=False)
        self.sessions = self.root / "codex" / "sessions"
        self.sessions.mkdir(parents=True)
        self.path = self.sessions / f"rollout-{THREAD}.jsonl"
        self.stamp = datetime.fromtimestamp(time.time() - 10, timezone.utc).isoformat()
        self.meta = {"id": THREAD, "source": "cli", "cwd": str(self.root),
                     "originator": "codex_cli_rs"}
        self.rows = [
            {"timestamp": self.stamp, "type": "session_meta", "payload": self.meta},
            {"timestamp": self.stamp, "type": "event_msg",
             "payload": {"type": "error", "codex_error_info": "usage_limit_exceeded",
                         "message": "You've hit your usage limit"}},
        ]
        self.write_rows()
        # A missed mock must fail before any native process or network client starts.
        process = patch("subprocess.Popen", side_effect=AssertionError("Real process forbidden"))
        process.start()
        self.addCleanup(process.stop)
        client = patch("codex_auto_resume.daemon.AppServerClient",
                       side_effect=AssertionError("Real quota client forbidden"))
        client.start()
        self.addCleanup(client.stop)

    def write_rows(self, *, newline="\n"):
        self.path.write_bytes((newline.join(json.dumps(row, ensure_ascii=False)
                                           for row in self.rows) + newline).encode("utf-8"))

    def test_identity_changed_after_scan_cannot_submit(self):
        def scan_then_change(*args, **kwargs):
            found = scan_waiting_sessions(*args, **kwargs)
            self.meta["source"] = {"internal": "guardian"}
            self.write_rows()
            return found

        with patch.object(daemon, "scan_waiting_sessions", side_effect=scan_then_change), \
                patch.object(daemon, "process_running", return_value=False), \
                patch.object(daemon, "spawn_resume") as spawn:
            state = daemon.tick(self.cfg, quota_reader=OfflineQuota())
        spawn.assert_not_called()
        task = state.threads[THREAD]
        self.assertEqual(task.resumes, 0)
        self.assertEqual(task.last_resume_at, 0)
        self.assertNotEqual(task.phase, "submitting")

    def test_user_activity_during_write_ahead_cancels_submission(self):
        def save_then_continue(directory, state):
            result = save_state(directory, state)
            if any(task.phase == "submitting" for task in state.threads.values()):
                self.rows.append({"timestamp": datetime.now(timezone.utc).isoformat(),
                                  "type": "response_item", "payload": {
                                      "type": "message", "role": "user", "content": "继续"}})
                self.write_rows()
            return result

        with patch.object(daemon, "save_state", side_effect=save_then_continue), \
                patch.object(daemon, "process_running", return_value=False), \
                patch.object(daemon, "spawn_resume") as spawn:
            state = daemon.tick(self.cfg, quota_reader=OfflineQuota())
        spawn.assert_not_called()
        task = load_state(self.cfg.resolved_state_dir()).threads[THREAD]
        self.assertEqual(task.resumes, 0)
        self.assertEqual(task.last_resume_at, 0)
        self.assertNotEqual(task.phase, "submitting")
        self.assertFalse(task.handled_mark)

    def test_valid_log_cannot_authorize_a_different_cached_thread(self):
        waiting = scan_waiting_sessions(self.sessions, since=0, ready_used_percent=99)[0]
        task = ThreadState(thread_id=OTHER)
        state = AppState(threads={OTHER: task})
        with patch.object(daemon, "spawn_resume") as spawn:
            daemon._resume_one(self.cfg, state, task, waiting, time.time())
        spawn.assert_not_called()
        self.assertEqual(task.resumes, 0)
        self.assertEqual(task.last_resume_at, 0)

    def test_stop_during_final_file_recheck_still_prevents_submission(self):
        stopped = False
        validate = daemon.validate_waiting_session

        def validate_then_stop(*args, **kwargs):
            nonlocal stopped
            result = validate(*args, **kwargs)
            stopped = True
            return result

        with patch.object(daemon, "validate_waiting_session", side_effect=validate_then_stop), \
                patch.object(daemon, "process_running", return_value=False), \
                patch.object(daemon, "spawn_resume") as spawn:
            state = daemon.tick(self.cfg, quota_reader=OfflineQuota(), should_stop=lambda: stopped)
        spawn.assert_not_called()
        self.assertEqual(state.last_status, "stopping")
        self.assertEqual(state.threads[THREAD].last_resume_at, 0)
        self.assertNotEqual(state.threads[THREAD].phase, "submitting")

    def test_new_continued_file_after_scan_supersedes_unchanged_old_path(self):
        def scan_then_create(*args, **kwargs):
            found = scan_waiting_sessions(*args, **kwargs)
            rows = [*self.rows, {"timestamp": datetime.now(timezone.utc).isoformat(),
                                "type": "response_item", "payload": {
                                    "type": "message", "role": "user", "content": "继续"}}]
            newer = self.sessions / f"new-rollout-{THREAD}.jsonl"
            newer.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            return found

        with patch.object(daemon, "scan_waiting_sessions", side_effect=scan_then_create), \
                patch.object(daemon, "process_running", return_value=False), \
                patch.object(daemon, "spawn_resume") as spawn:
            state = daemon.tick(self.cfg, quota_reader=OfflineQuota())
        spawn.assert_not_called()
        self.assertEqual(state.threads[THREAD].resumes, 0)
        self.assertEqual(state.threads[THREAD].last_resume_at, 0)

    def test_unreadable_new_copy_during_recheck_cannot_submit_old_waiting_copy(self):
        newer = self.sessions / f"new-rollout-{THREAD}.jsonl"
        real_open = Path.open

        def scan_then_create(*args, **kwargs):
            found = scan_waiting_sessions(*args, **kwargs)
            rows = [*self.rows, {"timestamp": datetime.now(timezone.utc).isoformat(),
                                "type": "event_msg", "payload": {
                                    "type": "task_complete", "error": None}}]
            newer.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            return found

        def unreadable(path, mode="r", *args, **kwargs):
            if path == newer and "r" in mode:
                raise PermissionError("Synthetic sharing violation after discovery")
            return real_open(path, mode, *args, **kwargs)

        with patch.object(daemon, "scan_waiting_sessions", side_effect=scan_then_create), \
                patch.object(Path, "open", unreadable), \
                patch.object(daemon, "process_running", return_value=False), \
                patch.object(daemon, "spawn_resume") as spawn:
            state = daemon.tick(self.cfg, quota_reader=OfflineQuota())
        spawn.assert_not_called()
        task = load_state(self.cfg.resolved_state_dir()).threads[THREAD]
        self.assertEqual(task.resumes, 0)
        self.assertEqual(task.last_resume_at, 0)
        self.assertNotEqual(task.phase, "submitting")
        self.assertFalse(task.handled_mark)

    def test_mac_and_windows_paths_resume_only_the_verified_thread_once(self):
        for platform, cwd, newline in (
            ("darwin", "/Users/测试/My Project", "\n"),
            ("win32", "C:\\Users\\测试\\My Project", "\r\n"),
        ):
            with self.subTest(platform=platform):
                self.meta["cwd"] = cwd
                self.write_rows(newline=newline)
                with patch("sys.platform", platform), \
                        patch.object(daemon, "process_running", return_value=False), \
                        patch.object(daemon, "spawn_resume", return_value=(999999, "mock-only")) as spawn:
                    state = daemon.tick(self.cfg, state=AppState(), quota_reader=OfflineQuota())
                    daemon.tick(self.cfg, state=state, quota_reader=OfflineQuota())
                spawn.assert_called_once()
                self.assertEqual(spawn.call_args.kwargs["thread_id"], THREAD)
                self.assertEqual(spawn.call_args.kwargs["cwd"], cwd)
                self.assertEqual(state.threads[THREAD].resumes, 1)


if __name__ == "__main__":
    unittest.main()
