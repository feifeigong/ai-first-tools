from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_auto_resume.sessions import inspect_rollout, scan_waiting_sessions

THREAD = "11111111-1111-4111-8111-111111111111"


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


class SessionTests(unittest.TestCase):
    def test_waiting_when_last_window_is_full(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / f"rollout-{THREAD}.jsonl"
            _write(
                path,
                [
                    {
                        "timestamp": "2026-09-09T01:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": THREAD, "cwd": "/tmp/demo"},
                    },
                    {
                        "timestamp": "2026-09-09T01:10:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "rate_limits": {
                                "primary": {
                                    "used_percent": 100.0,
                                    "window_minutes": 300,
                                    "resets_at": 1789000000,
                                }
                            },
                        },
                    },
                ],
            )
            found = inspect_rollout(path, since=0, ready_used_percent=99.0)
            assert found is not None
            self.assertEqual(found.thread_id, THREAD)
            self.assertEqual(found.cwd, "/tmp/demo")
            self.assertEqual(found.resets_at, 1789000000)

    def test_ignore_after_user_continued(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / f"rollout-{THREAD}.jsonl"
            _write(
                path,
                [
                    {
                        "timestamp": "2026-09-09T01:00:00Z",
                        "type": "session_meta",
                        "payload": {"id": THREAD, "cwd": "/tmp/demo"},
                    },
                    {
                        "timestamp": "2026-09-09T01:10:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "rate_limits": {"primary": {"used_percent": 100.0, "resets_at": 1}},
                        },
                    },
                    {
                        "timestamp": "2026-09-09T02:00:00Z",
                        "type": "response_item",
                        "payload": {"type": "message", "role": "user", "content": "继续"},
                    },
                ],
            )
            found = inspect_rollout(path, since=0, ready_used_percent=99.0)
            self.assertIsNone(found)

    def test_scan_uses_newest_file_per_thread(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            old = root / f"rollout-old-{THREAD}.jsonl"
            new = root / f"rollout-new-{THREAD}.jsonl"
            _write(
                old,
                [
                    {"timestamp": "2026-09-09T01:00:00Z", "type": "session_meta", "payload": {"id": THREAD}},
                    {
                        "timestamp": "2026-09-09T01:10:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "rate_limits": {"primary": {"used_percent": 100.0, "resets_at": 10}},
                        },
                    },
                ],
            )
            _write(
                new,
                [
                    {"timestamp": "2026-09-09T03:00:00Z", "type": "session_meta", "payload": {"id": THREAD}},
                    {
                        "timestamp": "2026-09-09T03:10:00Z",
                        "type": "event_msg",
                        "payload": {
                            "type": "token_count",
                            "rate_limits": {"primary": {"used_percent": 100.0, "resets_at": 99}},
                        },
                    },
                ],
            )
            found = scan_waiting_sessions(root, since=0, ready_used_percent=99.0)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].resets_at, 99)


if __name__ == "__main__":
    unittest.main()
