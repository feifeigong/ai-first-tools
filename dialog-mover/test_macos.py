from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from core import chatgpt, common, mover, sources

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "macos"))
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_macos import prepare
from updates import REPOSITORY, choose_release, release_key


class MacPathsTests(unittest.TestCase):
    def test_smoke_profile_is_empty_without_initializing_destination_stores(self):
        from entry import isolate_profile
        from main import AGENTS

        with tempfile.TemporaryDirectory() as temporary, patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {}, clear=True):
            isolate_profile(Path(temporary))
            self.assertTrue(common.home().is_dir())
            self.assertFalse(Path(os.environ["COWORK_SESSIONS_DIR"]).exists())
            self.assertFalse(any(sources.installed(agent["id"]) for agent in AGENTS))

    def test_application_support_not_windows_appdata(self):
        with patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {"HOME": "/Users/test", "USERPROFILE": "C:/wrong"}, clear=True):
            self.assertEqual(common.home(), Path("/Users/test"))
            self.assertEqual(common.appdata(), Path("/Users/test/Library/Application Support"))
            self.assertEqual(common.localappdata(), common.appdata())
            self.assertEqual(sources._cursor_db(), common.appdata() / "Cursor/User/globalStorage/state.vscdb")
            self.assertEqual(sources._claude_root(), common.appdata() / "Claude")
            self.assertEqual(sources._qwen_db(), common.appdata() / "QwenWorkCN/data/agents.db")

    def test_posix_file_uri_preserves_slashes_and_chinese_spaces(self):
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(common.uri_to_path("file:///Users/test/%E9%A1%B9%E7%9B%AE%20A"), "/Users/test/项目 A")
            self.assertEqual(chatgpt._norm("/Users/Test/Folder/../Project/"), "/Users/Test/Project")
            self.assertNotEqual(chatgpt._norm("/Users/test/A"), chatgpt._norm("/Users/test/a"))
            self.assertEqual(chatgpt._norm("/"), "/")

    def test_windows_project_paths_remain_compatible(self):
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(chatgpt._norm("C:/Project/Foo/"), "c:\\project\\foo")

    def test_native_engine_name_and_registration_environment(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {}, clear=True):
            root = Path(temporary)
            (root / "bin").mkdir()
            engine = root / "bin/txcript"
            engine.touch()
            with patch.object(mover, "app_dir", return_value=root), patch.object(common, "home", return_value=root), patch.object(mover, "codex_home", return_value=None):
                self.assertEqual(mover.txcript_path(), engine)
                self.assertEqual(mover._env()["APPDATA"], str(root / "Library/Application Support"))

    def test_open_folder_uses_argument_list_not_shell(self):
        with patch.object(sys, "platform", "darwin"), patch.object(common.subprocess, "run") as process:
            common.open_external("/Users/test/Folder $x; name")
            process.assert_called_once_with(["/usr/bin/open", "--", "/Users/test/Folder $x; name"], check=True, timeout=15)

    def test_readonly_database_with_uri_characters(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "项目 #问?.db"
            if sys.platform == "win32":
                path = Path(temporary) / "项目 #问.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE example(value)")
            connection.close()
            with closing(common.read_db(path)) as reader:
                with self.assertRaises(sqlite3.OperationalError):
                    reader.execute("INSERT INTO example VALUES (1)")

    def test_local_codex_history_visible_without_cloud_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sessions").mkdir()
            (root / "state_5.sqlite").touch()
            with patch.object(sources, "codex_home", return_value=root):
                self.assertTrue(sources.installed("chatgpt"))


class MacUpdatesTests(unittest.TestCase):
    def release(self, version="0.4.1", architecture="arm64"):
        tag = f"v{version}"
        name = f"AI-First-Tools-{version}-macos-{architecture}.dmg"
        return {"tag_name": tag, "draft": False, "html_url": f"{REPOSITORY}/releases/tag/{tag}", "assets": [
            {"name": name, "size": 100, "state": "uploaded", "browser_download_url": f"{REPOSITORY}/releases/download/{tag}/{name}"}]}

    def test_selects_matching_mac_architecture(self):
        self.assertEqual(choose_release([self.release()], "0.4.0-macos-preview.1", "arm64")["version"], "0.4.1")
        self.assertIsNone(choose_release([self.release()], "0.4.0", "x86_64"))

    def test_preview_and_stable_versions_sort_correctly(self):
        versions = ["0.4.0-macos-preview.1", "0.4.0-macos-preview.2", "0.4.0", "0.4.1"]
        self.assertEqual(sorted(versions, key=release_key), versions)
        self.assertIsNone(release_key("../../invalid"))

    def test_drafts_foreign_urls_missing_assets_and_old_releases_are_rejected(self):
        for attribute, value in (("draft", True), ("html_url", "https://example.com"), ("assets", [])):
            release = self.release()
            release[attribute] = value
            self.assertIsNone(choose_release([release], "0.4.0", "arm64"))
        self.assertIsNone(choose_release([self.release("0.3.6")], "0.4.0", "arm64"))
        release = self.release()
        release["assets"][0]["browser_download_url"] = "https://example.com/file.dmg"
        self.assertIsNone(choose_release([release], "0.4.0", "arm64"))


class MacResourceTests(unittest.TestCase):
    def test_cocoa_smoke_waits_for_loaded_event_before_evaluating_bridge(self):
        from entry import smoke_check

        window = Mock()
        window.events.loaded.wait.return_value = True
        window.evaluate_js.return_value = json.dumps({"passed": True})
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "smoke.json"
            smoke_check(window, report)
            self.assertTrue(json.loads(report.read_text())["passed"])
        self.assertEqual(window.mock_calls[0], unittest.mock.call.events.loaded.wait(45))
        window.destroy.assert_called_once()

    def test_unloaded_cocoa_window_fails_without_evaluating_javascript(self):
        from entry import smoke_check

        window = Mock()
        window.events.loaded.wait.return_value = False
        window.events.loaded.is_set.return_value = False
        window.events.shown.is_set.return_value = True
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "smoke.json"
            smoke_check(window, report)
            result = json.loads(report.read_text())
            self.assertFalse(result["passed"])
            self.assertFalse(result["checks"]["pageLoaded"])
        window.evaluate_js.assert_not_called()
        window.destroy.assert_called_once()

    def test_workspace_wraps_shared_ui_without_iframes_or_child_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            prepared = prepare(Path(temporary))
            html = (prepared / "ui/index.html").read_text(encoding="utf-8")
            for name in ("workspace-nav", "workspace-toggle", "agents", "bar", "sheet"):
                self.assertEqual(html.count(f'id="{name}"'), 1)
            self.assertNotIn("<iframe", html)
            self.assertIn('aria-controls="workspace-nav"', html)
            self.assertEqual((prepared / "ui/assets/dialog-mover.png").read_bytes(), (ROOT / "workspace/assets/dialog-mover.png").read_bytes())
            self.assertEqual((prepared / "ui/assets/ai-first.png").read_bytes(), (ROOT / "workspace/assets/ai-first-app-icon.png").read_bytes())
            self.assertEqual((prepared / "ui/app.js").read_bytes(), (ROOT / "dialog-mover/ui/app.js").read_bytes())
            self.assertEqual(json.loads((prepared / "version.json").read_text())["version"], "0.4.0")


if __name__ == "__main__":
    unittest.main()
