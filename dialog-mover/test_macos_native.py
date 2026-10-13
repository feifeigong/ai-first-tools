from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from audit_import_targets import isolated_env
from core import doubao, imports, mover, sources
from test_imports import CODEX_SCHEMA, QWEN_SCHEMA


@unittest.skipUnless(sys.platform == "darwin", "Uses the real macOS engine in isolated synthetic stores")
class NativeMacImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ai-first-native-mac-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.env = isolated_env(self.base)
        self.directory = self.base / "项目 with spaces $ and ;"
        self.directory.mkdir()
        for database, schema in ((Path(self.env["CODEX_HOME"]) / "state_5.sqlite", CODEX_SCHEMA), (imports.qwen_db(self.env), QWEN_SCHEMA)):
            database.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript(schema)
        (Path(self.env["COWORK_SESSIONS_DIR"]) / str(uuid.uuid4()) / str(uuid.uuid4())).mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.env, clear=True).start()
        patch.object(mover, "TEST_ENV", self.env).start()
        self.document = {"id": str(uuid.uuid4()), "title": "Mac synthetic import", "cwd": str(self.directory),
                         "messages": [{"role": "user", "content": "Mac synthetic question"}, {"role": "assistant", "content": "Mac synthetic answer"}]}
        self.path = self.base / "input.json"
        self.path.write_text(json.dumps(self.document), encoding="utf-8")

    def test_all_builtin_file_destinations_import_and_reread_without_changing_source(self):
        before = self.path.read_bytes()
        for target in imports.TARGETS:
            if target == "opencode":
                continue
            with self.subTest(target=target):
                details = {}
                result = mover._import_document(self.path, self.document, target, details)
                self.assertEqual(result[0], "ok", result)
                self.assertNotEqual(details["importedId"], self.document["id"])
                self.assertTrue(Path(details["location"]).resolve().is_relative_to(self.base.resolve()))
                self.assertEqual(self.path.read_bytes(), before)

    def test_incompatible_codex_database_is_rejected_before_writing_rollout(self):
        database = Path(self.env["CODEX_HOME"]) / "state_5.sqlite"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("DROP TABLE threads")
        with self.assertRaisesRegex(ValueError, "格式发生变化"):
            mover._import_document(self.path, self.document, "codex", {})
        self.assertEqual(list((Path(self.env["CODEX_HOME"]) / "sessions").glob("**/*.jsonl")), [])

    def test_doubao_mac_source_moves_native_trajectory_from_default_profile_readonly(self):
        os.environ.pop("DOUBAO_WORK_DIR")
        profile = Path(self.env["LOCALAPPDATA"]) / "DoubaoWork/Default"
        workspace = profile / doubao.WORKSPACE_SUFFIX
        session_id = str(uuid.uuid4())
        trajectory = workspace / ".sessions" / session_id / "agents/main/system/trajectory.jsonl"
        trajectory.parent.mkdir(parents=True)
        trajectory.write_text('\n'.join(json.dumps(record) for record in [
            {"role": "user", "content": "Synthetic Mac Doubao question"},
            {"role": "assistant", "content": "Synthetic Mac Doubao answer"}]), encoding="utf-8")
        before = trajectory.read_bytes()
        self.assertTrue(sources.installed("doubao_work"))
        self.assertEqual(sources._doubao_base(), profile)
        snapshots = {"conversation-list-data-non-project-v2": {"conversations": [
            {"conversation_id": session_id, "name": "Synthetic Mac Doubao task"}]}}
        with patch.object(sources, "_doubao_snapshots", return_value=snapshots):
            session = sources.doubao_groups()[0]["sessions"][0]
        self.assertTrue(session["movable"])
        details = {}
        result = mover.move_one("doubao_work", session, "claude_code", str(self.directory), details)
        self.assertEqual(result[0], "ok", result)
        output = self.base / "doubao-reread.json"
        exported = mover._run(["export", details["importedId"], "--from", "claude_code", "--out", str(output)], mover.destination_env("claude_code"))
        self.assertEqual(exported.returncode, 0)
        document = json.loads(output.read_text())
        self.assertIn("Synthetic Mac Doubao question", json.dumps(document))
        self.assertIn("Synthetic Mac Doubao answer", json.dumps(document))
        self.assertEqual(trajectory.read_bytes(), before)
        self.assertEqual(list(trajectory.parent.iterdir()), [trajectory])


if __name__ == "__main__":
    unittest.main()
