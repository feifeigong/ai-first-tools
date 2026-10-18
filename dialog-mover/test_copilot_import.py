from __future__ import annotations

import copy
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from core import copilot_import, copilot_local, common, mover
from main import Api


def desktop_index(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(root / "data.db")) as connection, connection:
        connection.executescript("""
CREATE TABLE sessions(id TEXT PRIMARY KEY NOT NULL,title TEXT,session_type TEXT NOT NULL,
created_at TEXT NOT NULL,updated_at TEXT NOT NULL,is_running INTEGER DEFAULT 0,was_interrupted INTEGER DEFAULT 0,
mode TEXT,auto_approve INTEGER DEFAULT 1,permission_mode TEXT,remote_control_enabled INTEGER DEFAULT 0,
remote_session_mode TEXT,execution_location TEXT DEFAULT 'local',title_source TEXT DEFAULT 'auto',
provisional INTEGER DEFAULT 0,archived_at TEXT);
CREATE TABLE agents(session_id TEXT PRIMARY KEY REFERENCES sessions(id));
CREATE TABLE app_state(key TEXT PRIMARY KEY,value TEXT);
INSERT INTO app_state VALUES('synthetic-credential-canary','never-copy-this-test-value');
CREATE TRIGGER sessions_insert_agent AFTER INSERT ON sessions WHEN NEW.session_type = 'agent'
BEGIN INSERT INTO agents (session_id) VALUES (NEW.id); END;
""")


def conversation(directory: Path, rounds: int = 3) -> dict:
    messages = []
    for index in range(rounds):
        messages.extend([
            {"role": "user", "content": [{"type": "text", "text": f"合成用户 {index}\n" + "完整多行正文 " * 80}]},
            {"role": "assistant", "content": [{"type": "thinking", "text": f"完整思考 {index}"},
                                                {"type": "text", "text": f"合成回答 {index}\n" + "回答内容 " * 100}]},
        ])
    return {"id": "chatgpt-synthetic-source", "title": "从 ChatGPT 导入的合成长对话", "cwd": str(directory), "messages": messages}


class CopilotDestinationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="copilot-import-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "copilot"
        self.directory = self.base / "合成项目 with spaces"
        self.directory.mkdir()
        desktop_index(self.root)
        self.enterContext(patch.object(copilot_local, "root", return_value=self.root))

    def test_complete_long_body_and_desktop_chat_registration_without_permissions_or_credentials(self):
        document = conversation(self.directory, 125)
        original = copy.deepcopy(document)
        result = copilot_import.import_document(document)
        self.assertEqual(document, original)
        body = copilot_local.document(result["id"])
        self.assertEqual(len(body["messages"]), 375)
        for source in document["messages"]:
            for block in source["content"]:
                self.assertIn(block["text"], [entry["content"][0]["text"] for entry in body["messages"]])
        groups = copilot_local.groups()
        self.assertEqual(groups[0]["title"], "聊天")
        self.assertEqual(groups[0]["sessions"][0]["title"], document["title"])
        with closing(sqlite3.connect(self.root / "data.db")) as connection:
            self.assertEqual(connection.execute("SELECT session_type,auto_approve,permission_mode,is_running FROM sessions WHERE id=?", (result["id"],)).fetchone(), ("general_chat", 0, "on", 0))
            self.assertEqual(connection.execute("SELECT count(*) FROM agents").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT value FROM app_state").fetchone()[0], "never-copy-this-test-value")
        directory = Path(result["location"]).parent
        self.assertNotIn("never-copy-this-test-value", "".join(path.read_text(encoding="utf-8") for path in directory.iterdir()))
        self.assertEqual(json.loads((directory / "workspace.yaml").read_text(encoding="utf-8"))["cwd"], str(self.directory))
        self.assertFalse(any(self.root.rglob(".ai-first-import-*")))

    def test_foreign_tools_and_system_instructions_are_complete_historical_notes(self):
        document = conversation(self.directory)
        blocks = [{"type": "tool_use", "id": "foreign-call", "name": "dangerous_tool", "input": {"command": "synthetic command, never execute"}},
                  {"type": "tool_result", "tool_use_id": "foreign-call", "content": "完整工具返回\n" + "x" * 10000}]
        document["messages"].insert(0, {"role": "system", "content": [{"type": "text", "text": "synthetic source instruction"}]})
        document["messages"][2]["content"].extend(blocks)
        result = copilot_import.import_document(document)
        body = copilot_local.document(result["id"])
        text = json.dumps(body, ensure_ascii=False)
        self.assertIn("不是待执行请求", text)
        self.assertIn("synthetic source instruction", text)
        for block in blocks:
            self.assertTrue(any(json.dumps(block, ensure_ascii=False, sort_keys=True) in message["content"][0]["text"] for message in body["messages"]))
        events = [json.loads(line) for line in Path(result["location"]).read_text(encoding="utf-8").splitlines()]
        self.assertFalse(any(event["type"].startswith(("tool.", "permission.")) for event in events))

    def test_chatgpt_export_flows_to_desktop_and_is_deduplicated(self):
        document = conversation(self.directory)
        fixture = self.base / "chatgpt-export.json"
        fixture.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        original = fixture.read_bytes()

        def exported(args, *unused, **kwargs):
            self.assertEqual(args[:4], ["export", document["id"], "--from", "chatgpt"])
            Path(args[args.index("--out") + 1]).write_bytes(fixture.read_bytes())
            return __import__("subprocess").CompletedProcess(args, 0, "", "")

        details = {}
        with patch.object(mover, "data_dir", return_value=self.base), patch.object(mover, "_run", side_effect=exported) as engine:
            state, message = mover.move_one("chatgpt", {"id": document["id"], "title": document["title"]}, "copilot_desktop", str(self.directory), details)
            self.assertEqual(state, "ok", message)
            self.assertEqual(details["openUrl"], "ghapp://recent")
            self.assertEqual(engine.call_count, 1)  # Source export only; no resume/model/tool request.
            previous = Path(details["location"]).read_bytes()
            skipped = {}
            self.assertEqual(mover.move_one("chatgpt", {"id": document["id"]}, "copilot_desktop", str(self.directory), skipped)[0], "skipped")
            self.assertEqual(skipped["openUrl"], "ghapp://recent")
            self.assertEqual(engine.call_count, 1)
            self.assertEqual(Path(details["location"]).read_bytes(), previous)
            with closing(sqlite3.connect(self.root / "data.db")) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM sessions").fetchone()[0], 1)
        self.assertEqual(fixture.read_bytes(), original)
        body = copilot_local.document(details["importedId"])
        self.assertEqual(body["title"], document["title"])
        for source in document["messages"]:
            for block in source["content"]:
                self.assertIn(block["text"], [entry["content"][0]["text"] for entry in body["messages"]])

    def test_native_list_handoff_for_new_and_previous_copies_and_open_failure_retry(self):
        for state in ("ok", "skipped"):
            api = Api()
            api._job = SimpleNamespace(target="copilot_desktop", snapshot=lambda: {"items": [
                {"state": state, "openUrl": copilot_import.LIST_URL}]})
            with patch("main.open_external") as opened, patch("main.time.sleep"):
                self.assertEqual(api.open_in_app(0), {"ok": True})
                # Leave Recent before re-entering: opening the same current
                # route alone need not run the native query a second time.
                self.assertEqual(opened.call_args_list, [call("ghapp://chats"), call("ghapp://recent")])
                opened.side_effect = OSError("synthetic missing handler")
                self.assertIn("Manage sessions", api.open_in_app(0)["error"])
                opened.side_effect = None
                self.assertEqual(api.open_in_app(0), {"ok": True})

    def test_handoff_rejects_other_protocols_wrong_batch_and_unsaved_results(self):
        for target, state, url in (("copilot_desktop", "failed", copilot_import.LIST_URL),
                                   ("copilot_desktop", "running", copilot_import.LIST_URL),
                                   ("chatgpt_work", "ok", copilot_import.LIST_URL),
                                   ("copilot_desktop", "ok", "ghapp://sessions/synthetic"),
                                   ("copilot_desktop", "ok", "https://example.invalid/"),
                                   ("copilot_desktop", "skipped", "file:///synthetic")):
            api = Api()
            api._job = SimpleNamespace(target=target, snapshot=lambda: {"items": [{"state": state, "openUrl": url}]})
            with patch("main.open_external") as opened:
                self.assertIn("error", api.open_in_app(0))
                opened.assert_not_called()

    def test_existing_chatgpt_thread_handoff_still_opens_only_own_result(self):
        api = Api()
        api._job = SimpleNamespace(target="chatgpt_work", snapshot=lambda: {"items": [
            {"state": "ok", "importedId": "synthetic-thread", "openUrl": "codex://threads/synthetic-thread"}]})
        with patch("main.open_external") as opened:
            self.assertEqual(api.open_in_app(0), {"ok": True})
            opened.assert_called_once_with("codex://threads/synthetic-thread")

    def test_trigger_cannot_create_additional_sessions(self):
        with closing(sqlite3.connect(self.root / "data.db")) as connection, connection:
            connection.executescript("CREATE TRIGGER unexpected_session AFTER INSERT ON sessions BEGIN INSERT INTO sessions(id,title,session_type,created_at,updated_at) VALUES('unexpected','extra','general_chat','now','now'); END;")
        with self.assertRaises(ValueError):
            copilot_import.import_document(conversation(self.directory))
        with closing(sqlite3.connect(self.root / "data.db")) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)

    def test_bad_schema_and_unknown_required_fields_fail_before_creating_any_history(self):
        with closing(sqlite3.connect(self.root / "data.db")) as connection, connection:
            connection.execute("ALTER TABLE sessions ADD COLUMN future_field TEXT NOT NULL")
        with self.assertRaisesRegex(ValueError, "必填"):
            copilot_import.import_document(conversation(self.directory))
        self.assertFalse((self.root / "session-state").exists())

    def test_unknown_message_shape_is_not_silently_dropped(self):
        for mutate in (lambda doc: doc["messages"][0].update(content=None),
                       lambda doc: doc["messages"][0]["content"][0].update(type="future-block"),
                       lambda doc: doc["messages"][0].update(role="future-role")):
            document = conversation(self.directory)
            mutate(document)
            with self.assertRaises(ValueError):
                copilot_import.import_document(document)
        with closing(sqlite3.connect(self.root / "data.db")) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)

    def test_readback_failure_rolls_back_only_new_row_and_new_files(self):
        with closing(sqlite3.connect(self.root / "data.db")) as connection, connection:
            connection.execute("INSERT INTO sessions(id,title,session_type,created_at,updated_at) VALUES('existing-record','已有记录','general_chat','now','now')")
        with patch.object(copilot_local, "_read", side_effect=ValueError("synthetic readback failure")):
            with self.assertRaisesRegex(ValueError, "synthetic"):
                copilot_import.import_document(conversation(self.directory))
        with closing(sqlite3.connect(self.root / "data.db")) as connection:
            self.assertEqual(connection.execute("SELECT id,title FROM sessions").fetchall(), [("existing-record", "已有记录")])
        self.assertEqual(list((self.root / "session-state").iterdir()), [])

    def test_native_trigger_cannot_write_credentials_or_existing_records(self):
        with closing(sqlite3.connect(self.root / "data.db")) as connection, connection:
            connection.executescript("CREATE TRIGGER unexpected_writer AFTER INSERT ON sessions BEGIN UPDATE app_state SET value='changed'; END;")
        with self.assertRaises(ValueError):
            copilot_import.import_document(conversation(self.directory))
        with closing(sqlite3.connect(self.root / "data.db")) as connection:
            self.assertEqual(connection.execute("SELECT value FROM app_state").fetchone()[0], "never-copy-this-test-value")
            self.assertEqual(connection.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)

    def test_registration_failure_does_not_touch_a_preexisting_uuid_directory(self):
        reserved = self.root / "session-state" / "12345678-1234-1234-1234-123456789abc"
        reserved.mkdir(parents=True)
        sentinel = reserved / "user-note.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        with patch.object(copilot_import.uuid, "uuid4", return_value=__import__("uuid").UUID(reserved.name)):
            with self.assertRaises(ValueError):
                copilot_import.import_document(conversation(self.directory))
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
