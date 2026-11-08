"""Regression fixtures follow Codex's SessionMeta serde schema; no Codex runs."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from codex_auto_resume import daemon
from codex_auto_resume.config import AppConfig
from codex_auto_resume.quota import QuotaSnapshot, QuotaWindow
from codex_auto_resume.sessions import inspect_rollout, scan_waiting_sessions
from codex_auto_resume.state import AppState, ThreadState


ROOT_ID = "11111111-1111-4111-8111-111111111111"
LIMIT = {"timestamp": "2026-11-08T01:01:00Z", "type": "event_msg", "payload": {
    "type": "error", "codex_error_info": "usage_limit_exceeded",
    "message": "You've hit your usage limit"}}
PROGRESS = {"timestamp": "2026-11-08T01:02:00Z", "type": "response_item", "payload": {
    "type": "message", "role": "user", "content": "继续"}}


class IdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="resume-identity-synthetic-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Even a forgotten mock must not start a real process.
        guard = patch("subprocess.Popen", side_effect=AssertionError("Real process forbidden"))
        guard.start()
        self.addCleanup(guard.stop)
        clock = patch("codex_auto_resume.daemon.time.time", return_value=
                      datetime(2026, 11, 8, 2, 0, tzinfo=timezone.utc).timestamp())
        clock.start()
        self.addCleanup(clock.stop)

    def write(self, *, ident=ROOT_ID, source="cli", extra=None, events=None, name="rollout"):
        meta = {"id": ident, "cwd": str(self.root), "source": source,
                "originator": "codex_cli_rs"}
        meta.update(extra or {})
        rows = [{"timestamp": "2026-11-08T01:00:00Z", "type": "session_meta", "payload": meta}]
        rows.extend([LIMIT] if events is None else events)
        path = self.root / f"{name}-{ident}.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        return path

    def inspect(self, path):
        return inspect_rollout(path, since=0, ready_used_percent=99)

    def scan(self):
        return scan_waiting_sessions(self.root, since=0, ready_used_percent=99)

    def test_supported_main_sources_are_eligible(self):
        for source in ("cli", "vscode", "exec", "mcp"):
            with self.subTest(source=source):
                self.assertIsNotNone(self.inspect(self.write(source=source)))

    def test_independent_verified_main_tasks_are_not_arbitrarily_capped(self):
        other = "22222222-2222-4222-8222-222222222222"
        self.write()
        self.write(ident=other, source="vscode")
        self.assertEqual({item.thread_id for item in self.scan()}, {ROOT_ID, other})

    def test_main_with_unverified_inherited_history_is_not_automatically_resumed(self):
        for extra in (
            {"forked_from_id": "22222222-2222-4222-8222-222222222222"},
            {"history_base": {"thread_id": ROOT_ID, "end_ordinal_exclusive": 10}},
            {"forked_from_ordinal_exclusive": 10},
        ):
            with self.subTest(extra=extra):
                self.assertIsNone(self.inspect(self.write(extra={
                    "thread_source": "user", "agent_path": "/root", **extra})))

    def test_subagent_and_internal_sources_are_never_main(self):
        for source in (
            {"subagent": {"thread_spawn": {"parent_thread_id": ROOT_ID, "depth": 1}}},
            {"subagent": "review"}, {"subagent": "compact"},
            {"subagent": "memory_consolidation"}, {"subagent": {"other": "future"}},
            {"internal": "guardian"}, {"internal": "memory_consolidation"},
            {"internal": "future"},
        ):
            with self.subTest(source=source):
                self.assertIsNone(self.inspect(self.write(source=source)))

    def test_unknown_source_cannot_borrow_a_cli_originator(self):
        for source in (None, "", "unknown", "app-server", "guardian_review", "future", {}, [], True):
            with self.subTest(source=source):
                self.assertIsNone(self.inspect(self.write(source=source)))
        path = self.write()
        rows = [json.loads(row) for row in path.read_text().splitlines()]
        del rows[0]["payload"]["source"]
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        self.assertIsNone(self.inspect(path))

    def test_conflicting_provenance_overrides_main_source(self):
        for extra in (
            {"thread_source": "subagent"}, {"thread_source": "guardian_review"},
            {"thread_source": "memory_consolidation"}, {"thread_source": "future-feature"},
            {"parent_thread_id": ROOT_ID}, {"parent_thread_id": ""},
            {"agent_path": "/root/child"}, {"subagent_history_start_ordinal": 0},
        ):
            with self.subTest(extra=extra):
                self.assertIsNone(self.inspect(self.write(extra=extra)))

    def test_filename_only_and_invalid_metadata_id_fail_closed(self):
        path = self.write()
        path.write_text(json.dumps(LIMIT) + "\n")
        self.assertIsNone(self.inspect(path))
        self.assertIsNone(self.inspect(self.write(extra={"id": "not-a-uuid"})))

    def test_reverted_rollout_uses_canonical_id_not_filename_uuid(self):
        actual_id = "22222222-2222-4222-8222-222222222222"
        result = self.inspect(self.write(extra={"id": actual_id}))
        self.assertIsNotNone(result)
        self.assertEqual(result.thread_id, actual_id)

    def test_fork_history_cannot_override_canonical_first_metadata(self):
        for source in ("cli", {"internal": "guardian"}, None):
            with self.subTest(source=source):
                path = self.write(source=source)
                inherited = {"timestamp": "2026-11-08T00:00:00Z", "type": "session_meta",
                             "payload": {"id": "22222222-2222-4222-8222-222222222222",
                                         "source": "cli", "cwd": str(self.root)}}
                rows = path.read_text().splitlines()
                rows.insert(1, json.dumps(inherited))
                path.write_text("\n".join(rows) + "\n")
                result = self.inspect(path)
                self.assertIsNone(result)  # Own limit vs inherited limit is unverified.

    def test_corrupt_or_unreadable_rollout_never_authorizes_resume(self):
        path = self.write()
        path.write_bytes(path.read_bytes() + b'{"type":"response_item"')
        self.assertIsNone(self.inspect(path))
        path = self.write()
        path.write_bytes(path.read_bytes() + b'\xff\n')
        self.assertIsNone(self.inspect(path))
        path.unlink()
        self.assertIsNone(self.inspect(path))

    def test_six_waiters_dispatch_only_main_even_with_old_cached_children(self):
        self.write()
        children = []
        for number in range(2, 7):
            ident = f"{number:08d}-1111-4111-8111-111111111111"
            children.append(ident)
            source = ({"internal": "guardian"} if number == 6 else
                      {"subagent": {"thread_spawn": {"parent_thread_id": ROOT_ID, "depth": 1}}})
            self.write(ident=ident, source=source)
        self.assertEqual([item.thread_id for item in self.scan()], [ROOT_ID])
        cfg = AppConfig(codex_home=str(self.root / "unused-home"), state_dir=str(self.root / "state"),
                        auto_redeem_weekly_reset=False)
        state = AppState(threads={ident: ThreadState(thread_id=ident, status="waiting") for ident in children})

        class Quota:
            def read(self, now):
                return QuotaSnapshot(primary=QuotaWindow(0, int(now + 3600), 300),
                    secondary=QuotaWindow(10, int(now + 86400), 10080), source="app-server")

        with patch.object(daemon, "sessions_dir", return_value=self.root), \
                patch.object(daemon, "process_running", return_value=False), \
                patch.object(daemon, "spawn_resume", return_value=(999999, "mock-only")) as spawn:
            state = daemon.tick(cfg, state=state, quota_reader=Quota())
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.kwargs["thread_id"], ROOT_ID)
        self.assertTrue(all(state.threads[ident].resumes == 0 for ident in children))

    def test_child_waiting_does_not_wake_its_completed_parent(self):
        self.write(events=[LIMIT, PROGRESS])
        self.write(ident="22222222-2222-4222-8222-222222222222", source={
            "subagent": {"thread_spawn": {"parent_thread_id": ROOT_ID, "depth": 1}}})
        self.assertEqual(self.scan(), [])

    def test_inherited_parent_metadata_in_child_does_not_block_real_parent(self):
        self.write()
        path = self.write(ident="22222222-2222-4222-8222-222222222222", source={
            "subagent": {"thread_spawn": {"parent_thread_id": ROOT_ID, "depth": 1}}})
        rows = path.read_text().splitlines()
        rows.insert(1, json.dumps({"type": "session_meta", "timestamp": "2026-11-08T00:00:00Z",
                                  "payload": {"id": ROOT_ID, "source": "cli"}}))
        path.write_text("\n".join(rows) + "\n")
        self.assertEqual([item.thread_id for item in self.scan()], [ROOT_ID])

    def test_unknown_cached_thread_does_not_dispatch(self):
        self.write(source=None)
        cfg = AppConfig(codex_home=str(self.root / "unused-home"), state_dir=str(self.root / "state"),
                        auto_redeem_weekly_reset=False)
        state = AppState(threads={ROOT_ID: ThreadState(thread_id=ROOT_ID, status="waiting")})

        class Quota:
            def read(self, now):
                return QuotaSnapshot(primary=QuotaWindow(0, int(now + 3600), 300),
                    secondary=QuotaWindow(10, int(now + 86400), 10080), source="app-server")

        with patch.object(daemon, "sessions_dir", return_value=self.root), \
                patch.object(daemon, "process_running", return_value=False), \
                patch.object(daemon, "spawn_resume") as spawn:
            daemon.tick(cfg, state=state, quota_reader=Quota())
        spawn.assert_not_called()

    def test_newer_activity_beats_old_limit_even_if_old_file_was_touched(self):
        old = self.write(name="old")
        self.write(name="new", events=[LIMIT, PROGRESS])
        os.utime(old, (time.time() + 60, time.time() + 60))
        self.assertEqual(self.scan(), [])

    def test_unreadable_copy_with_unknown_canonical_id_blocks_scan_until_readable(self):
        other = "22222222-2222-4222-8222-222222222222"
        self.write(name="old")
        new = self.write(name="new", ident=other, extra={"id": ROOT_ID}, events=[LIMIT, PROGRESS])
        self.write(ident=other)
        real_open = Path.open

        def unreadable(path, *args, **kwargs):
            if path == new:
                raise PermissionError("Synthetic sharing violation")
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", unreadable):
            self.assertIsNone(self.inspect(new))
            self.assertEqual(self.scan(), [])
        self.assertEqual([item.thread_id for item in self.scan()], [other])

    def test_stat_failure_cannot_hide_a_conflicting_same_thread_copy(self):
        other = "22222222-2222-4222-8222-222222222222"
        self.write(name="old")
        new = self.write(name="new", ident=other, extra={"id": ROOT_ID}, events=[LIMIT, PROGRESS])
        self.write(ident=other)
        real_stat = Path.stat

        def unreadable(path, *args, **kwargs):
            if path == new:
                raise PermissionError("Synthetic metadata access failure")
            return real_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", unreadable):
            self.assertEqual([item.thread_id for item in self.scan()], [other])

    def test_missing_or_corrupt_first_identity_cannot_be_assigned_by_filename(self):
        other = "22222222-2222-4222-8222-222222222222"
        self.write()
        path = self.root / f"unknown-{other}.jsonl"
        for content in ("", "{broken\n", json.dumps(LIMIT) + "\n",
                        json.dumps({"type": "session_meta", "payload": {"source": "cli"}}) + "\n"):
            with self.subTest(content=content):
                path.write_text(content, encoding="utf-8")
                self.assertEqual(self.scan(), [])
        path.unlink()
        self.assertEqual([item.thread_id for item in self.scan()], [ROOT_ID])

    def test_known_canonical_id_with_unknown_source_does_not_block_other_main(self):
        other = "22222222-2222-4222-8222-222222222222"
        self.write()
        self.write(ident=other, source=None)
        self.assertEqual([item.thread_id for item in self.scan()], [ROOT_ID])

    def test_read_failure_after_canonical_header_blocks_only_its_stable_thread(self):
        other = "22222222-2222-4222-8222-222222222222"
        self.write(name="old")
        new = self.write(name="new", ident=other, extra={"id": ROOT_ID})
        self.write(ident=other)
        header = new.read_text().splitlines(keepends=True)[0]
        real_open = Path.open

        class FailedRead:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                yield header
                raise OSError("Synthetic failure after canonical header")

        def unreadable(path, *args, **kwargs):
            return FailedRead() if path == new else real_open(path, *args, **kwargs)

        with patch.object(Path, "open", unreadable):
            self.assertEqual([item.thread_id for item in self.scan()], [other])

    def test_incomplete_directory_listing_is_retried_without_using_partial_results(self):
        path = self.write()

        def partial_listing(root, *, onerror, followlinks):
            yield str(root), ["inaccessible"], [path.name]
            onerror(PermissionError("Synthetic subtree listing failure"))

        with patch("codex_auto_resume.sessions.os.walk", partial_listing):
            self.assertEqual(self.scan(), [])
        # The failure blocks this scan only; the next complete scan can recover.
        self.assertEqual([item.thread_id for item in self.scan()], [ROOT_ID])

    def test_progress_at_equal_timestamp_wins_over_waiting_copy(self):
        self.write(name="old")
        self.write(name="new", events=[LIMIT, {**PROGRESS, "timestamp": LIMIT["timestamp"]}])
        self.assertEqual(self.scan(), [])

    def test_contradictory_copy_cannot_become_main_by_using_newer_timestamp(self):
        self.write(source={"internal": "guardian"}, name="old")
        self.write(name="new", events=[{**LIMIT, "timestamp": "2026-11-08T02:00:00Z"}])
        self.assertEqual(self.scan(), [])

    def test_role_free_progress_and_successful_completion_cancel_wait(self):
        for kind in ("user_message", "agent_message", "task_started", "turn_started", "task_complete", "turn_complete", "turn_aborted"):
            with self.subTest(kind=kind):
                progress = {"timestamp": LIMIT["timestamp"], "type": "event_msg",
                            "payload": {"type": kind, "message": "继续或完成"}}
                self.assertIsNone(self.inspect(self.write(events=[LIMIT, progress])))

    def test_terminal_usage_error_still_allows_main_recovery(self):
        terminal = {"timestamp": "2026-11-08T01:02:00Z", "type": "event_msg", "payload": {
            "type": "task_complete", "error": {"codex_error_info": "usage_limit_exceeded"}}}
        self.assertIsNotNone(self.inspect(self.write(events=[LIMIT, terminal])))

    def test_ordinary_messages_quoting_limit_text_are_not_errors(self):
        for kind in ("user_message", "agent_message"):
            message = {"timestamp": LIMIT["timestamp"], "type": "event_msg", "payload": {
                "type": kind, "message": "Documentation says: You've hit your usage limit; try again at noon."}}
            with self.subTest(kind=kind):
                self.assertIsNone(self.inspect(self.write(events=[message])))


if __name__ == "__main__":
    unittest.main()
