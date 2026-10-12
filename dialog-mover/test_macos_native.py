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
from core import imports, mover
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
                self.assertTrue(Path(details["location"]).is_relative_to(self.base))
                self.assertEqual(self.path.read_bytes(), before)

    def test_incompatible_codex_database_is_rejected_before_writing_rollout(self):
        database = Path(self.env["CODEX_HOME"]) / "state_5.sqlite"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("DROP TABLE threads")
        with self.assertRaisesRegex(ValueError, "格式发生变化"):
            mover._import_document(self.path, self.document, "codex", {})
        self.assertEqual(list((Path(self.env["CODEX_HOME"]) / "sessions").glob("**/*.jsonl")), [])


if __name__ == "__main__":
    unittest.main()
