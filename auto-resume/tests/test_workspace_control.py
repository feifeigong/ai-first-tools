from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from codex_auto_resume.workspace_control import allow_background_watch


class WorkspaceControlTests(unittest.TestCase):
    def test_absent_preference_keeps_existing_startup(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(allow_background_watch(["watch", "--quiet"], {"LOCALAPPDATA": root}))

    def test_background_gate_and_explicit_manual_start(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "AI一手工具工作台" / "auto-resume-startup.json"
            path.parent.mkdir()
            env = {"LOCALAPPDATA": root}
            path.write_text(json.dumps({"autostart": False}), encoding="utf-8-sig")
            self.assertFalse(allow_background_watch(["watch", "--quiet"], env))
            self.assertTrue(allow_background_watch(["watch", "--quiet"], {**env, "AI_FIRST_MANUAL_WATCH": "1"}))
            self.assertTrue(allow_background_watch(["watch"], env))
            self.assertTrue(allow_background_watch(["doctor"], env))
            path.write_text('{"autostart":true}', encoding="utf-8")
            self.assertTrue(allow_background_watch(["watch", "--quiet"], env))

    def test_malformed_preference_never_starts_background_work(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "AI一手工具工作台" / "auto-resume-startup.json"
            path.parent.mkdir()
            for value in ('null', '[]', '{}', '{"autostart":"false"}', 'broken'):
                path.write_text(value, encoding="utf-8")
                self.assertFalse(allow_background_watch(["watch", "--quiet"], {"LOCALAPPDATA": root}))


if __name__ == "__main__":
    unittest.main()
