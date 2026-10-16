from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_auto_resume.state import load_state, save_state, upsert_thread


class StateTests(unittest.TestCase):
    def test_roundtrip_and_write_ahead_fields(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = load_state(root)
            upsert_thread(
                state,
                "abc",
                phase="submitting",
                status="resuming",
                resumes=0,
                handled_mark="mark-1",
                failed_mark="",
            )
            save_state(root, state)
            again = load_state(root)
            self.assertEqual(again.threads["abc"].phase, "submitting")
            self.assertEqual(again.threads["abc"].status, "resuming")
            self.assertEqual(again.threads["abc"].handled_mark, "mark-1")
            self.assertEqual(again.threads["abc"].failed_mark, "")

    def test_all_zero_state_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            broken = root / "state.json"
            broken.write_bytes(b"\x00" * 32)
            state = load_state(root)
            self.assertEqual(state.threads, {})
            self.assertFalse(broken.exists())
            quarantined = list(root.glob("state.json.broken-*"))
            self.assertEqual(len(quarantined), 1)
            self.assertIn("已损坏", (root / "daemon.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
