from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import doubao, imports, mover, sources


class DoubaoPathsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ai-first-doubao-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.environment = {"HOME": str(self.base), "USERPROFILE": str(self.base),
                            "LOCALAPPDATA": str(self.base / "Library/Application Support")}
        self.environment_patch = patch.dict(os.environ, self.environment, clear=True)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def test_mac_default_profile_is_detected_and_used_for_snapshots(self):
        profile = self.base / "Library/Application Support/DoubaoWork/Default"
        (profile / ".doubaowork").mkdir(parents=True)
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(sources._doubao_base(), profile)
            self.assertEqual(doubao.workspace(), profile / doubao.WORKSPACE_SUFFIX)
            self.assertTrue(sources.installed("doubao_work"))

    def test_windows_path_is_unchanged_and_mac_can_read_legacy_layout(self):
        profile = self.base / "Library/Application Support/DoubaoWork/User Data/Default"
        (profile / ".doubaowork").mkdir(parents=True)
        for platform_name in ("win32", "darwin"):
            with self.subTest(platform=platform_name), patch.object(sys, "platform", platform_name):
                self.assertEqual(doubao.profile(), profile)
                self.assertTrue(doubao.installed())

    def test_native_profile_wins_over_legacy_profile(self):
        base = self.base / "Library/Application Support/DoubaoWork"
        for suffix in ("Default", "User Data/Default"):
            (base / suffix / ".doubaowork").mkdir(parents=True)
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(doubao.profile(), base / "Default")

    def test_indexeddb_only_profile_is_visible_but_cloud_rows_are_not_movable(self):
        profile = self.base / "Library/Application Support/DoubaoWork/Default"
        (profile / "IndexedDB" / doubao.INDEX_NAME).mkdir(parents=True)
        snapshots = {"conversation-list-data-non-project-v2": {"conversations": [
            {"conversation_id": "cloud-only-123", "name": "Synthetic cloud task"}]}}
        with patch.object(sys, "platform", "darwin"), patch.object(sources, "_doubao_snapshots", return_value=snapshots):
            self.assertTrue(doubao.installed())
            session = sources.doubao_groups()[0]["sessions"][0]
            self.assertFalse(session["movable"])

    def test_ordinary_doubao_and_empty_directory_do_not_fake_work_support(self):
        (self.base / "Library/Application Support/Doubao/Default").mkdir(parents=True)
        (self.base / "Library/Application Support/DoubaoWork/Default").mkdir(parents=True)
        with patch.object(sys, "platform", "darwin"):
            self.assertFalse(doubao.installed())
            self.assertEqual(sources._doubao_snapshots(), {})

    def test_workspace_override_is_shared_by_detection_and_profile(self):
        workspace = self.base / "custom profile" / doubao.WORKSPACE_SUFFIX
        workspace.mkdir(parents=True)
        with patch.dict(os.environ, {"DOUBAO_WORK_DIR": str(workspace)}):
            self.assertEqual(doubao.workspace(), workspace)
            self.assertEqual(doubao.profile(), self.base / "custom profile")
            self.assertTrue(doubao.installed())

    def test_groups_keep_native_order_and_do_not_resurrect_unlisted_local_tasks(self):
        workspace = self.base / "workspace"
        for session_id in ("local-task-123", "unlisted-task-123"):
            (workspace / ".sessions" / session_id).mkdir(parents=True)
        snapshots = {"conversation-list-data-project-v4": {"projects": [{"name": "Synthetic project", "conversations": [
            {"conversation_id": "local-task-123", "name": "Synthetic local task"},
            {"conversation_id": "cloud-task-123", "name": "Synthetic cloud task"}]}]}}
        with patch.dict(os.environ, {"DOUBAO_WORK_DIR": str(workspace)}), patch.object(sources, "_doubao_snapshots", return_value=snapshots):
            sessions = [session for group in sources.doubao_groups() for session in group["sessions"]]
            self.assertEqual([session["id"] for session in sessions], ["local-task-123", "cloud-task-123"])
            self.assertEqual([session["movable"] for session in sessions], [True, False])
        self.assertNotIn("doubao_work", imports.TARGETS)

    def test_move_passes_discovered_mac_workspace_to_export_engine(self):
        workspace = self.base / "Library/Application Support/DoubaoWork/Default" / doubao.WORKSPACE_SUFFIX
        workspace.mkdir(parents=True)
        destination = self.base / "destination"
        destination.mkdir()
        calls = []

        def export(arguments, environment, timeout):
            calls.append(environment)
            Path(arguments[-1]).write_text(json.dumps({"messages": [{"role": "user", "content": "Synthetic"}]}), encoding="utf-8")
            return SimpleNamespace(returncode=0)

        with patch.object(sys, "platform", "darwin"), patch.object(mover, "already_moved", return_value=False), \
                patch.object(mover, "_run", side_effect=export), patch.object(mover, "_import_document", return_value=("failed", "test stops before write")):
            result = mover.move_one("doubao_work", {"id": "local-task-123"}, "claude_code", str(destination))
            self.assertEqual(result[0], "failed")
            self.assertEqual(calls, [{"DOUBAO_WORK_DIR": str(workspace)}])


if __name__ == "__main__":
    unittest.main()
