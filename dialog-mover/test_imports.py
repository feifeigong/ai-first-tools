from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

from audit_import_targets import isolated_env
from core import chatgpt, codex_import, imports, mover, sources
from main import Api
from test_copilot_import import desktop_index


QWEN_SCHEMA = """
CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,path TEXT UNIQUE NOT NULL,created_at INTEGER,updated_at INTEGER);
CREATE TABLE local_projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,root_paths TEXT NOT NULL DEFAULT '[]',created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,deleted_at INTEGER,icon TEXT DEFAULT 'newfolder-close',icon_color TEXT DEFAULT 'black');
CREATE TABLE chats(id TEXT PRIMARY KEY,name TEXT,project_id TEXT NOT NULL REFERENCES projects(id),local_project_id TEXT,chat_type TEXT DEFAULT 'task',worktree_path TEXT,output_directory TEXT,created_at INTEGER,updated_at INTEGER,ext TEXT,archived_at INTEGER,deleted_at INTEGER);
CREATE TABLE sub_chats(id TEXT PRIMARY KEY,chat_id TEXT NOT NULL REFERENCES chats(id),session_id TEXT,messages TEXT NOT NULL DEFAULT '[]',created_at INTEGER,updated_at INTEGER);
CREATE TABLE messages(id TEXT PRIMARY KEY,message_id TEXT NOT NULL,chat_id TEXT NOT NULL,sub_chat_id TEXT NOT NULL,sequence INTEGER NOT NULL,role TEXT NOT NULL,parts TEXT NOT NULL DEFAULT '[]',metadata TEXT NOT NULL DEFAULT '{}',searchable_text TEXT,created_at INTEGER,updated_at INTEGER,UNIQUE(sub_chat_id,sequence),UNIQUE(sub_chat_id,message_id));
CREATE TABLE app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at INTEGER);
"""

CODEX_SCHEMA = """
CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}',position INTEGER NOT NULL,created_at_ms INTEGER NOT NULL,updated_at_ms INTEGER NOT NULL);
CREATE TABLE project_roots(project_id TEXT NOT NULL REFERENCES projects(id),position INTEGER NOT NULL,path TEXT NOT NULL,PRIMARY KEY(project_id,position));
CREATE TABLE threads(id TEXT PRIMARY KEY,rollout_path TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,source TEXT NOT NULL,model_provider TEXT NOT NULL,cwd TEXT NOT NULL,title TEXT NOT NULL,sandbox_policy TEXT NOT NULL,approval_mode TEXT NOT NULL,tokens_used INTEGER DEFAULT 0,has_user_event INTEGER DEFAULT 0,archived INTEGER DEFAULT 0,first_user_message TEXT NOT NULL DEFAULT '',preview TEXT NOT NULL DEFAULT '',created_at_ms INTEGER,updated_at_ms INTEGER,recency_at INTEGER DEFAULT 0,recency_at_ms INTEGER DEFAULT 0,thread_source TEXT,history_mode TEXT DEFAULT 'legacy',name TEXT,originator TEXT,project_id TEXT REFERENCES projects(id));
"""


@contextmanager
def connect(path, **kwargs):
    with closing(sqlite3.connect(path, **kwargs)) as connection, connection:
        yield connection


class ImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database = sources._qwen_db()
        cls.native_schema = []
        cls.native_codex_schema = []
        root = sources.codex_home()
        if root and (root / "state_5.sqlite").is_file():
            with connect((root / "state_5.sqlite").as_uri() + "?mode=ro", uri=True) as original:
                cls.native_codex_schema = [original.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
                                          for table in ("thread_sections", "projects", "project_roots", "threads")]
        if database.is_file():
            with connect(database.as_uri() + "?mode=ro", uri=True) as original:
                cls.native_schema = [original.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[0]
                                     for table in [*imports.QWEN_COLUMNS, "app_settings"]]

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dm-target-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.env = isolated_env(self.base)
        self.env["COPILOT_HOME"] = str(self.base / "copilot")
        desktop_index(Path(self.env["COPILOT_HOME"]))
        self.env.pop("ANTIGRAVITY_DIR")
        self.directory = self.base / "目的地"
        self.directory.mkdir()
        self.codex_database = Path(self.env["CODEX_HOME"]) / "state_5.sqlite"
        with connect(self.codex_database) as connection:
            connection.executescript(CODEX_SCHEMA)
        self.database = imports.qwen_db(self.env)
        self.database.parent.mkdir(parents=True)
        with connect(self.database) as connection:
            connection.executescript(QWEN_SCHEMA)
            layout = {"schemaVersion": 2, "revision": 1, "preferences": {"projects": "manual", "recent": "recency", "pinned": "recency"},
                      "orders": {"projects": {}, "recent": []}, "pinnedByScope": {}}
            connection.execute("INSERT INTO app_settings VALUES(?,?,?)", ("sidebarTaskLayout", json.dumps(layout), 1))
            connection.execute("INSERT INTO app_settings VALUES(?,?,?)", ("sidebarProjectOrder", json.dumps({"schemaVersion": 1, "revision": 1, "projectIds": [], "pinnedProjectIds": []}), 1))
        account = Path(self.env["COWORK_SESSIONS_DIR"]) / str(uuid.uuid4()) / str(uuid.uuid4())
        account.mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.env).start()
        patch.object(mover, "TEST_ENV", self.env).start()
        patch.object(mover, "_history_file", return_value=self.base / "history.json").start()
        patch.object(sources, "claude_body", return_value=[{"role": "user", "content": "迁移问题"}, {"role": "assistant", "content": "迁移回答"}]).start()
        patch.object(sources, "_cowork_root", return_value=Path(self.env["COWORK_SESSIONS_DIR"])).start()
        self.session = {"id": str(uuid.uuid4()), "title": "完整迁移标题", "movable": True}

    def move(self, target):
        details = {}
        result = mover.move_one("claude_desktop", self.session, target, str(self.directory), details)
        return result, details

    def test_all_gui_destinations_write_and_read_back(self):
        for target in imports.TARGETS:
            with self.subTest(target=target):
                result, details = self.move(target)
                self.assertEqual(result[0], "ok", result)
                self.assertNotEqual(details["importedId"], self.session["id"])
                self.assertTrue(mover.already_moved("claude_desktop", self.session["id"], target, str(self.directory)))
                if imports.TARGETS[target]["mode"] == "cli":
                    self.assertIn(details["importedId"], details["resumeCommand"])
                if target in ("antigravity", "antigravity_cli"):
                    self.assertTrue(Path(details["location"]).is_relative_to(sources._gemini_root(target)))

    def test_native_qwen_registration_and_project_reuse(self):
        result, details = self.move("qwen_work")
        self.assertEqual(result[0], "ok", result)
        with connect(self.database) as connection:
            chat = connection.execute("SELECT id,name,local_project_id FROM chats").fetchone()
            self.assertEqual(chat[1], self.session["title"])
            sub = connection.execute("SELECT session_id,messages FROM sub_chats").fetchone()
            self.assertEqual(sub, (details["importedId"], "[]"))
            body = connection.execute("SELECT role,parts,metadata FROM messages ORDER BY sequence").fetchall()
            self.assertEqual(len(body), 2)
            self.assertEqual(json.loads(body[0][1])[0]["text"], "迁移问题")
            layout = json.loads(connection.execute("SELECT value FROM app_settings WHERE key='sidebarTaskLayout'").fetchone()[0])
            self.assertEqual(layout["orders"]["projects"][chat[2]], [chat[0]])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        listed = [item for group in sources.qwen_groups() for item in group["sessions"]]
        self.assertEqual(listed[0]["title"], self.session["title"])
        self.assertTrue(listed[0]["movable"])
        self.assertEqual(listed[0]["folder"], str(self.directory))
        self.session["id"] = str(uuid.uuid4())
        self.assertEqual(self.move("qwen_work")[0][0], "ok")
        with connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM local_projects").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM chats").fetchone()[0], 2)
        self.assertEqual(len(list((Path(self.env["APPDATA"]) / "对话搬家" / "backups").glob("*.db"))), 2)

    def test_native_qwen_schema_matches_installed_version(self):
        if not self.native_schema:
            self.skipTest("Installed Qwen schema unavailable")
        actual = self.base / "native-schema.db"
        with connect(actual) as connection:
            for definition in self.native_schema:
                connection.execute(definition)
        native_env = {**self.env, "APPDATA": str(self.base / "native-roaming")}
        native_db = imports.qwen_db(native_env)
        native_db.parent.mkdir(parents=True)
        actual.replace(native_db)
        with patch.object(mover, "TEST_ENV", native_env):
            self.assertEqual(self.move("qwen_work")[0][0], "ok")

    def test_deduplicates_and_does_not_change_original(self):
        original = dict(self.session)
        self.assertEqual(self.move("workbuddy")[0][0], "ok")
        self.assertEqual(self.move("workbuddy")[0][0], "skipped")
        self.assertEqual(self.session, original)

    def test_read_only_targets_are_rejected(self):
        for target in imports.READ_ONLY:
            self.assertEqual(self.move(target)[0][0], "failed")
        self.assertFalse((self.base / "history.json").exists())

    def test_qwen_missing_or_unknown_schema_never_records_success(self):
        with connect(self.database) as connection:
            connection.execute("DROP TABLE messages")
        result, _ = self.move("qwen_work")
        self.assertEqual(result[0], "failed")
        self.assertIn("格式发生变化", result[1])
        self.assertFalse((self.base / "history.json").exists())
        self.assertEqual(list(Path(self.env["QWENWORK_DIR"]).rglob("*.jsonl")), [])

    def test_registration_failure_rolls_back_and_removes_new_file(self):
        with patch.object(imports, "_place_qwen_task", side_effect=ValueError("simulated registration failure")):
            result, _ = self.move("qwen_work")
        self.assertEqual(result[0], "failed")
        with connect(self.database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM chats").fetchone()[0], 0)
        self.assertEqual(list(Path(self.env["QWENWORK_DIR"]).rglob("*.jsonl")), [])
        self.assertFalse((self.base / "history.json").exists())

    def test_invalid_component_report_does_not_record_success(self):
        with patch.object(mover, "_run", return_value=subprocess.CompletedProcess([], 0, "old component output", "")):
            result, _ = self.move("claude_code")
        self.assertEqual(result[0], "failed")
        self.assertIn("版本不匹配", result[1])
        self.assertFalse((self.base / "history.json").exists())

    def test_empty_session_is_rejected_before_any_target_write(self):
        with patch.object(sources, "claude_body", return_value=[{"role": "user", "content": ""}]), patch.object(mover, "_run") as component:
            result, _ = self.move("cursor_desktop")
        self.assertEqual(result[0], "failed")
        self.assertIn("没有可搬运的对话正文", result[1])
        component.assert_not_called()
        self.assertFalse((self.base / "history.json").exists())

    def test_tool_only_log_is_not_treated_as_a_conversation(self):
        self.assertFalse(imports.has_conversation_body({"messages": [{"role": "user", "content": [{"type": "tool_use", "name": "Read", "id": "tool1", "input": {}}]}]}))
        self.assertFalse(imports.has_conversation_body({"messages": [{"role": "user", "content": [{"type": "text", "text": "  "}]}]}))
        self.assertTrue(imports.has_conversation_body({"messages": [{"role": "assistant", "content": [{"type": "text", "text": "有效正文"}]}]}))

    def test_empty_cli_session_is_not_offered_for_migration(self):
        rows = [{"id": "empty-session", "title": "", "ts": 2}, {"id": "normal-session", "title": "正常对话", "ts": 1}]
        details = {"empty-session": (str(self.directory), "", False), "normal-session": (str(self.directory), "问题", True)}
        with patch.object(sources, "_txcript_rows", return_value=rows), patch.object(sources, "_details_by_export", return_value=details):
            items = [item for group in sources.list_groups("claude_code") for item in group["sessions"]]
        self.assertEqual([item["id"] for item in items], ["empty-session", "normal-session"])
        self.assertFalse(items[0]["movable"])
        self.assertTrue(items[1]["movable"])

    def test_api_exposes_existing_targets_and_separate_cli_source_only(self):
        with patch.object(sources, "installed", return_value=True), patch.object(sources, "unsupported_found", return_value=[]):
            result = Api().agents()
        targets = {item["id"]: item for item in result["targets"]}
        for target in imports.TARGETS:
            self.assertTrue(targets[target]["canTarget"], target)
        for target in imports.READ_ONLY:
            self.assertFalse(targets[target]["canTarget"], target)
            self.assertTrue(targets[target]["readOnlyReason"])
        self.assertEqual([item["id"] for item in result["agents"]].count("chatgpt"), 1)
        self.assertNotIn("codex", [item["id"] for item in result["agents"]])
        self.assertEqual([item["id"] for item in result["agents"]].count("codex_cli"), 1)
        self.assertNotIn("codex_cli", targets)

    def test_api_validation_blocks_invalid_folder_and_uninstalled_targets(self):
        api = Api()
        with patch.object(sources, "installed", return_value=True):
            self.assertIn("error", api.start_move("claude_desktop", [self.session["id"]], "claude_code", "missing-directory"))
        with patch.object(sources, "installed", return_value=False):
            self.assertIn("error", api.start_move("claude_desktop", [self.session["id"]], "claude_code", str(self.directory)))

    def test_chatgpt_local_modes_preserve_title_directory_and_native_origin(self):
        for target, origin, kind in (("chatgpt_work", "codex_work_desktop", "work"), ("codex", "Codex Desktop", "codex")):
            result, details = self.move(target)
            self.assertEqual(result[0], "ok", result)
            with connect(self.codex_database) as connection:
                row = connection.execute("SELECT name,cwd,originator,source,thread_source,project_id FROM threads WHERE id=?", (details["importedId"],)).fetchone()
                self.assertEqual(row[:5], (self.session["title"], str(self.directory), origin, "vscode", "user"))
                self.assertEqual(connection.execute("SELECT path FROM project_roots WHERE project_id=?", (row[5],)).fetchone()[0], str(self.directory))
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            meta = json.loads(Path(details["location"]).read_text(encoding="utf-8").splitlines()[0])["payload"]
            self.assertEqual(meta["originator"], origin)
            data = chatgpt.local_data(Path(self.env["CODEX_HOME"]))
            # ChatGPT's own sidebar does not list a project that only the state database knows,
            # so the app shows the imported thread under 最近 -- and so does this tool.
            in_projects = [item for project in data["projects"] for item in project["sessions"] if item["id"] == details["importedId"]]
            listed = [item for item in data["recent"] if item["id"] == details["importedId"]]
            self.assertEqual(in_projects, [])
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["kind"], kind)
            self.assertEqual(listed[0]["title"], self.session["title"])
        with connect(self.codex_database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
        self.assertEqual(len(list((Path(self.env["APPDATA"]) / "对话搬家" / "backups").glob("chatgpt-*.db"))), 2)

    def test_chatgpt_registration_matches_installed_native_schema(self):
        if not self.native_codex_schema:
            self.skipTest("Installed ChatGPT local schema unavailable")
        self.codex_database.unlink()
        with connect(self.codex_database) as connection:
            for definition in self.native_codex_schema:
                connection.execute(definition)
        for target in ("chatgpt_work", "codex"):
            self.assertEqual(self.move(target)[0][0], "ok")

    def test_chatgpt_registration_failure_rolls_back_new_project_and_file(self):
        with patch.object(codex_import, "_project", side_effect=ValueError("simulated registration failure")):
            result, _details = self.move("chatgpt_work")
        self.assertEqual(result[0], "failed")
        with connect(self.codex_database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM threads").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 0)
        self.assertFalse((self.base / "history.json").exists())
        self.assertEqual(list(Path(self.env["CODEX_HOME"]).rglob("rollout-*.jsonl")), [])

    def test_chatgpt_unknown_schema_rejects_before_writing(self):
        with connect(self.codex_database) as connection:
            connection.execute("ALTER TABLE threads RENAME COLUMN originator TO unknown_originator")
        with patch.object(mover, "_run") as component:
            result, _details = self.move("codex")
        self.assertEqual(result[0], "failed")
        self.assertIn("格式发生变化", result[1])
        component.assert_not_called()

    def test_imported_cowork_is_listed_in_its_local_folder(self):
        result, details = self.move("cowork")
        self.assertEqual(result[0], "ok", result)
        sessions = [item for group in sources.cowork_groups() for item in group["sessions"]]
        imported = next(item for item in sessions if item["id"] == details["importedId"])
        self.assertEqual(imported["title"], self.session["title"])
        self.assertEqual(imported["folder"], str(self.directory))
        self.assertTrue(imported["movable"])

    def test_chatgpt_reuses_native_extended_path_project(self):
        project_id = str(uuid.uuid4())
        with connect(self.codex_database) as connection:
            connection.execute("INSERT INTO projects VALUES(?,?,?,?,?,?)", (project_id, "原有项目", "{}", 0, 1, 1))
            connection.execute("INSERT INTO project_roots VALUES(?,?,?)", (project_id, 0, "\\\\?\\" + str(self.directory)))
        result, details = self.move("chatgpt_work")
        self.assertEqual(result[0], "ok", result)
        with connect(self.codex_database) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT project_id FROM threads WHERE id=?", (details["importedId"],)).fetchone()[0], project_id)


if __name__ == "__main__":
    unittest.main()
