from __future__ import annotations

import copy
import base64
import json
import os
import sqlite3
import struct
import tempfile
import unittest
import zlib
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from core import copilot_import, copilot_local, common, mover
from core.memory_audit import desktop_fixture, persistent_projects_fixture, isolated_connections
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
CREATE TABLE projects(id TEXT PRIMARY KEY NOT NULL,name TEXT NOT NULL,main_repo_path TEXT NOT NULL UNIQUE,
container_kind TEXT NOT NULL DEFAULT 'folder',created_at TEXT NOT NULL DEFAULT '',last_opened_at TEXT NOT NULL DEFAULT '',auto_approve INTEGER DEFAULT 1,
show_in_sidebar INTEGER NOT NULL DEFAULT 1);
CREATE TABLE workspaces(id TEXT PRIMARY KEY NOT NULL,project_id TEXT NOT NULL REFERENCES projects(id),workspace_type TEXT NOT NULL,
branch TEXT NOT NULL,name TEXT NOT NULL,session_id TEXT,source_path TEXT,created_at TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL DEFAULT '',
tab_order INTEGER DEFAULT 0,port INTEGER DEFAULT 0,name_source TEXT DEFAULT 'auto',explicitly_opened INTEGER DEFAULT 0,
provisional INTEGER DEFAULT 0,host_id TEXT DEFAULT 'local',is_initialized INTEGER DEFAULT 1);
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


def image_source() -> dict:
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    pixels = b"".join(b"\0" + b"\xe6\x52\x52" * 80 + b"\x49\x90\xe2" * 80 for _ in range(80))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 160, 80, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
    return {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode("ascii")}


def visual_conversation(directory: Path) -> dict:
    return {"id": "synthetic-visual-history", "title": "AI一手导入显示测试", "cwd": str(directory), "messages": [
        {"role": "user", "content": [{"type": "image", "source": image_source()}, {"type": "text", "text": "这张合成图片里有哪两种颜色？"}]},
        {"role": "assistant", "content": [{"type": "thinking", "text": "合成思考：核对图片颜色。"}, {"type": "tool_use", "id": "original-call", "name": "source_shell", "input": {"command": "DO_NOT_EXECUTE_SYNTHETIC"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "original-call", "content": "合成日志：红色和蓝色。"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "图片左侧是红色，右侧是蓝色。"}]},
        {"role": "user", "content": [{"type": "text", "text": "请保持问答顺序。"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "这是第二轮的合成回答。"}]}]}


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
        self.enterContext(isolated_connections(self.base))

    def test_current_native_trigger_allows_chat_without_creating_worktree_or_changing_old_project(self):
        current = self.base / "current-desktop"
        desktop_fixture(current)
        persistent_projects_fixture(current)
        with closing(sqlite3.connect(current / "data.db")) as db, db:
            db.execute("INSERT INTO projects(id,name,main_repo_path,container_kind) VALUES('existing-project','Existing project','synthetic-missing-worktree','folder')")
            db.execute("INSERT INTO sessions(id,title,session_type,created_at,updated_at) VALUES('existing-session','Existing session','project','now','now')")
            db.execute("INSERT INTO workspaces(id,project_id,workspace_type,branch,name,session_id,source_path) VALUES('existing-workspace','existing-project','folder','','Existing session','existing-session','synthetic-missing-worktree')")
            before = {table: db.execute('SELECT * FROM "' + table + '"').fetchall()
                      for table in ('projects', 'workspaces', 'persistent_projects', 'app_state')}
            schema = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            old = db.execute("SELECT * FROM sessions WHERE id='existing-session'").fetchone()
        source = visual_conversation(self.directory)
        result = copilot_import.import_document(source, current)
        with closing(sqlite3.connect(current / "data.db")) as db:
            self.assertEqual(db.execute("SELECT session_type FROM sessions WHERE id=?", (result['id'],)).fetchone(), ('general_chat',))
            self.assertEqual(db.execute("SELECT * FROM sessions WHERE id='existing-session'").fetchone(), old)
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall(), schema)
            for table, rows in before.items():
                self.assertEqual(db.execute('SELECT * FROM "' + table + '"').fetchall(), rows)
        self.assertEqual(copilot_local._read(Path(result['location']), result['id'])['title'], source['title'])
        self.assertEqual(json.loads(Path(result['location']).with_name('.ai-first-source.json').read_text(encoding='utf8')), source)

    def test_changed_current_trigger_is_denied_without_partial_rows_or_files(self):
        for mutation in ("WHEN NEW.session_type = 'general_chat'", "WHEN NEW.session_type = 'agent' OR 1=1"):
            with self.subTest(condition=mutation):
                current = self.base / ('changed-' + str(len(list(self.base.glob('changed-*')))))
                desktop_fixture(current)
                persistent_projects_fixture(current)
                with closing(sqlite3.connect(current / "data.db")) as db, db:
                    db.execute('DROP TRIGGER sessions_insert_agent')
                    db.execute('CREATE TRIGGER sessions_insert_agent AFTER INSERT ON sessions ' + mutation +
                               ' BEGIN INSERT INTO "persistent_projects" (session_id) VALUES (NEW.id); END;')
                with self.assertRaisesRegex(ValueError, '索引.*规则'):
                    copilot_import.import_document(conversation(self.directory), current)
                with closing(sqlite3.connect(current / "data.db")) as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
                    self.assertEqual(db.execute('SELECT count(*) FROM persistent_projects').fetchone()[0], 0)
                    self.assertEqual(db.execute('SELECT value FROM app_state').fetchone()[0], 'never-copy-this-synthetic-value')
                self.assertEqual(list((current / 'session-state').iterdir()), [])

    def test_database_busy_is_not_reported_as_format_change(self):
        with closing(sqlite3.connect(self.root / 'data.db', timeout=0)) as lock:
            lock.execute('BEGIN IMMEDIATE')
            original = sqlite3.connect
            def fast_connect(*args, **kwargs):
                kwargs['timeout'] = 0
                return original(*args, **kwargs)
            with patch.object(sqlite3, 'connect', side_effect=fast_connect):
                with self.assertRaisesRegex(ValueError, '正在保存记录'):
                    copilot_import.import_document(conversation(self.directory))
            lock.rollback()
        self.assertEqual(list((self.root / 'session-state').iterdir()), [])

    def test_complete_long_body_and_desktop_chat_registration_without_permissions_or_credentials(self):
        document = conversation(self.directory, 125)
        original = copy.deepcopy(document)
        result = copilot_import.import_document(document)
        self.assertEqual(document, original)
        body = copilot_local.document(result["id"])
        self.assertEqual(len(body["messages"]), 250)
        for source in document["messages"]:
            for block in source["content"]:
                self.assertIn(block["text"], [part["text"] for entry in body["messages"] for part in entry["content"]])
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

    def test_foreign_tools_and_system_instructions_are_collapsed_complete_history(self):
        document = conversation(self.directory)
        blocks = [{"type": "tool_use", "id": "foreign-call", "name": "dangerous_tool", "input": {"command": "synthetic command, never execute"}},
                  {"type": "tool_result", "tool_use_id": "foreign-call", "content": "完整工具返回\n" + "x" * 10000}]
        document["messages"].insert(0, {"role": "system", "content": [{"type": "text", "text": "synthetic source instruction"}]})
        document["messages"][2]["content"].extend(blocks)
        result = copilot_import.import_document(document)
        body = copilot_local.document(result["id"])
        text = json.dumps(body, ensure_ascii=False)
        self.assertIn("未重新执行", text)
        self.assertIn("synthetic source instruction", text)
        for block in blocks:
            self.assertIn(block, [note["block"] for event in [json.loads(line) for line in Path(result["location"]).read_text(encoding="utf-8").splitlines()]
                                  for note in event["data"].get("result", {}).get("structuredContent", {}).get("importedHistory", [])])
        events = [json.loads(line) for line in Path(result["location"]).read_text(encoding="utf-8").splitlines()]
        self.assertFalse(any(event["type"].startswith("permission.") for event in events))
        self.assertEqual({event["data"]["toolName"] for event in events if event["type"] == "tool.execution_start"}, {copilot_import.HISTORY_TOOL})
        requests = {request["toolCallId"] for event in events for request in event["data"].get("toolRequests", [])}
        completed = {event["data"]["toolCallId"] for event in events if event["type"] == "tool.execution_complete"}
        self.assertEqual(requests, completed)
        self.assertFalse(any("dangerous_tool" in event["data"].get("content", "") for event in events if event["type"] in ("user.message", "assistant.message")))
        self.assertEqual(json.loads(Path(result["location"]).with_name(".ai-first-source.json").read_text(encoding="utf-8")), document)

    def test_images_are_native_attachments_and_normal_chat_has_no_protocol_dumps(self):
        document = visual_conversation(self.directory)
        result = copilot_import.import_document(document)
        events = [json.loads(line) for line in Path(result["location"]).read_text(encoding="utf-8").splitlines()]
        displayed = [event for event in events if event["type"] in ("user.message", "assistant.message") and event["data"]["content"]]
        self.assertEqual([(event["type"], event["data"]["content"]) for event in displayed], [
            ("user.message", "这张合成图片里有哪两种颜色？"), ("assistant.message", "图片左侧是红色，右侧是蓝色。"),
            ("user.message", "请保持问答顺序。"), ("assistant.message", "这是第二轮的合成回答。")])
        image = displayed[0]["data"]["attachments"][0]
        self.assertEqual(image["type"], "blob")
        self.assertEqual(image["data"], image_source()["data"])
        self.assertFalse(any(image["data"] in event["data"]["content"] or "DO_NOT_EXECUTE" in event["data"]["content"] for event in displayed))
        self.assertEqual(copilot_local.document(result["id"])["messages"][0]["content"][1]["source"], image_source())

    def test_bad_images_fail_before_writing_and_old_format_allows_one_corrected_copy(self):
        for source in ({"type": "url", "data": "https://example.invalid/image.png"},
                       {"type": "base64", "media_type": "image/png", "data": "broken encoding!"},
                       {"type": "base64", "media_type": "image/png", "data": base64.b64encode(b"not a PNG").decode()}):
            document = visual_conversation(self.directory)
            document["messages"][0]["content"][0]["source"] = source
            with self.assertRaises(ValueError):
                copilot_import.import_document(document)
        self.assertFalse((self.root / "session-state").exists())
        key = mover.history_key("chatgpt_work", "synthetic-source", "copilot_desktop", str(self.directory))
        (self.base / "history.json").write_text(json.dumps({key: {"time": 1, "format": "copilot-desktop-chat-v1"}}), encoding="utf-8")
        with patch.object(mover, "data_dir", return_value=self.base):
            self.assertFalse(mover.already_moved("chatgpt_work", "synthetic-source", "copilot_desktop", str(self.directory)))
            mover._record_move("chatgpt_work", "synthetic-source", "copilot_desktop", str(self.directory))
            self.assertTrue(mover.already_moved("chatgpt_work", "synthetic-source", "copilot_desktop", str(self.directory)))

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
            self.assertEqual(details["openUrl"], "ghapp://sessions/" + details['importedId'])
            self.assertEqual(engine.call_count, 1)  # Source export only; no resume/model/tool request.
            previous = Path(details["location"]).read_bytes()
            skipped = {}
            self.assertEqual(mover.move_one("chatgpt", {"id": document["id"]}, "copilot_desktop", str(self.directory), skipped)[0], "skipped")
            self.assertEqual(skipped["openUrl"], details['openUrl'])
            self.assertEqual(engine.call_count, 1)
            self.assertEqual(Path(details["location"]).read_bytes(), previous)
            with closing(sqlite3.connect(self.root / "data.db")) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM sessions").fetchone()[0], 1)
        self.assertEqual(fixture.read_bytes(), original)
        body = copilot_local.document(details["importedId"])
        self.assertEqual(body["title"], document["title"])
        for source in document["messages"]:
            for block in source["content"]:
                self.assertIn(block["text"], [part["text"] for entry in body["messages"] for part in entry["content"]])

    def test_native_list_handoff_for_new_and_previous_copies_and_open_failure_retry(self):
        for state in ("ok", "skipped"):
            api = Api()
            api._job = SimpleNamespace(target="copilot_desktop", snapshot=lambda: {"items": [
                {"state": state, "openUrl": copilot_import.LIST_URL}]})
            with patch("main.open_external") as opened, patch("main.time.sleep"), patch("main.copilot_refresh.refresh", return_value="requested") as refresh:
                self.assertEqual(api.open_in_app(0), {"ok": True, "refreshed": True})
                self.assertEqual(opened.call_args_list, [call("ghapp://recent")])
                refresh.assert_called_once_with()
                opened.side_effect = OSError("synthetic missing handler")
                self.assertIn("Manage sessions", api.open_in_app(0)["error"])
                opened.side_effect = None
                self.assertEqual(api.open_in_app(0), {"ok": True, "refreshed": True})

    def test_project_handoff_opens_only_the_saved_uuid_and_preserves_busy_or_draft_guards(self):
        sid = '12345678-1234-4321-9876-123456789abc'
        api = Api()
        item = {'state':'ok','importedId':sid,'openUrl':'ghapp://sessions/'+sid}
        api._job = SimpleNamespace(target='copilot_desktop',snapshot=lambda:{'items':[item]})
        with patch('main.open_external') as opened, patch('main.time.sleep'), patch('main.copilot_refresh.refresh',return_value='requested'):
            self.assertEqual(api.open_in_app(0),{'ok':True,'refreshed':True})
            opened.assert_called_once_with(item['openUrl'])
        for state in ('busy','draft'):
            with patch('main.open_external') as opened, patch('main.copilot_refresh.refresh',return_value=state):
                self.assertIn('error',api.open_in_app(0))
                opened.assert_not_called()
        item['importedId'] = 'different-result'
        with patch('main.open_external') as opened:
            self.assertIn('error',api.open_in_app(0))
            opened.assert_not_called()

    def test_busy_or_unidentified_copilot_does_not_send_navigation_or_report_refresh_success(self):
        api = Api()
        api._job = SimpleNamespace(target="copilot_desktop", snapshot=lambda: {"items": [{"state": "ok", "openUrl": copilot_import.LIST_URL}]})
        for status in ("busy", "draft", "unavailable"):
            with patch("main.copilot_refresh.refresh", return_value=status), patch("main.open_external") as opened:
                self.assertIn("error", api.open_in_app(0))
                opened.assert_not_called()
        for status in ("not-running", "unsupported"):
            with patch("main.copilot_refresh.refresh", return_value=status), patch("main.open_external") as opened:
                self.assertEqual(api.open_in_app(0), {"ok": True, "refreshed": False})
                opened.assert_called_once_with("ghapp://recent")

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


class CopilotProjectDestinationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='copilot-project-import-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'desktop'
        self.directory = self.base / 'selected project'
        self.directory.mkdir()
        (self.directory/'keep.txt').write_text('synthetic original project',encoding='utf8')
        self.enterContext(isolated_connections(self.base))
        desktop_fixture(self.root)
        persistent_projects_fixture(self.root)

    def test_existing_repository_receives_new_folder_session_without_rewriting_old_project_or_files(self):
        with closing(sqlite3.connect(self.root/'data.db')) as db, db:
            db.execute("INSERT INTO projects(id,name,main_repo_path,container_kind,instructions) VALUES('project-one','Existing display name',?,'repository','KEEP CONFIG')", (str(self.directory),))
            db.execute("INSERT INTO sessions(id,title,session_type,created_at,updated_at) VALUES('existing-session','Original','project','now','now')")
            db.execute("INSERT INTO workspaces(id,project_id,workspace_type,branch,name,session_id,source_path) VALUES('existing-workspace','project-one','worktree','main','Original','existing-session',?)", (str(self.directory),))
            original = {table:db.execute('SELECT * FROM '+table).fetchall() for table in ('projects','workspaces','sessions','app_state')}
            schema = db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall()
        document = visual_conversation(self.directory)
        result = copilot_import.import_document(document, self.root, project=True)
        with closing(sqlite3.connect(self.root/'data.db')) as db:
            self.assertEqual(db.execute('SELECT * FROM projects').fetchall(),original['projects'])
            self.assertEqual(db.execute("SELECT * FROM workspaces WHERE id='existing-workspace'").fetchall(),original['workspaces'])
            self.assertEqual(db.execute("SELECT * FROM sessions WHERE id='existing-session'").fetchall(),original['sessions'])
            self.assertEqual(db.execute('SELECT * FROM app_state').fetchall(),original['app_state'])
            self.assertEqual(db.execute('SELECT session_type,auto_approve FROM sessions WHERE id=?',(result['id'],)).fetchone(),('project',0))
            self.assertEqual(db.execute('SELECT project_id,workspace_type,branch,source_path FROM workspaces WHERE session_id=?',(result['id'],)).fetchone(),('project-one','folder','',str(self.directory)))
            self.assertEqual(db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall(),schema)
            self.assertEqual(db.execute('SELECT count(*) FROM persistent_projects').fetchone()[0],0)
        self.assertEqual(result['projectName'],'Existing display name')
        self.assertEqual(result['openUrl'],'ghapp://sessions/'+result['id'])
        self.assertEqual([p.name for p in self.directory.iterdir()],['keep.txt'])
        self.assertEqual(json.loads(Path(result['location']).with_name('.ai-first-source.json').read_text(encoding='utf8')),document)

    def test_unregistered_folder_creates_one_project_and_separate_completed_history_sessions(self):
        results = [copilot_import.import_document(conversation(self.directory), self.root, project=True) for _ in range(2)]
        with closing(sqlite3.connect(self.root/'data.db')) as db:
            self.assertEqual(db.execute('SELECT name,main_repo_path,container_kind,auto_approve FROM projects').fetchall(),[(self.directory.name,str(self.directory),'folder',0)])
            self.assertEqual(db.execute('SELECT count(*) FROM workspaces').fetchone()[0],2)
            self.assertEqual(db.execute("SELECT count(*) FROM sessions WHERE session_type='general_chat'").fetchone()[0],0)
        self.assertNotEqual(results[0]['id'],results[1]['id'])
        self.assertEqual(results[0]['projectId'],results[1]['projectId'])

    def test_hidden_project_and_unknown_project_trigger_never_fall_back_to_chats(self):
        with closing(sqlite3.connect(self.root/'data.db')) as db, db:
            db.execute("INSERT INTO projects(id,name,main_repo_path,container_kind,show_in_sidebar) VALUES('hidden','Hidden',?,'folder',0)",(str(self.directory),))
        with self.assertRaisesRegex(ValueError,'隐藏'):
            copilot_import.import_document(conversation(self.directory),self.root,project=True)
        self.assertFalse((self.root/'session-state').exists())
        with closing(sqlite3.connect(self.root/'data.db')) as db, db:
            db.execute('DELETE FROM projects')
            db.execute("CREATE TRIGGER unknown_workspace AFTER INSERT ON workspaces BEGIN UPDATE app_state SET value='CORRUPTED'; END;")
        with self.assertRaises(ValueError):
            copilot_import.import_document(conversation(self.directory),self.root,project=True)
        with closing(sqlite3.connect(self.root/'data.db')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM projects').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM workspaces').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT value FROM app_state').fetchone()[0],'never-copy-this-synthetic-value')
        self.assertEqual(list((self.root/'session-state').iterdir()),[])

    def test_failed_project_readback_rolls_back_new_associations_and_preserves_existing_project(self):
        with closing(sqlite3.connect(self.root/'data.db')) as db, db:
            db.execute("INSERT INTO projects(id,name,main_repo_path,container_kind,instructions) VALUES('keep','Keep',?,'repository','KEEP')", (str(self.directory),))
            before = {table:db.execute('SELECT * FROM '+table).fetchall() for table in ('projects','workspaces','sessions','app_state')}
        with patch.object(copilot_local, '_read', side_effect=ValueError('synthetic readback failure')):
            with self.assertRaisesRegex(ValueError, 'synthetic'):
                copilot_import.import_document(conversation(self.directory), self.root, project=True)
        with closing(sqlite3.connect(self.root/'data.db')) as db:
            self.assertEqual({table:db.execute('SELECT * FROM '+table).fetchall() for table in before}, before)
        self.assertEqual(list((self.root/'session-state').iterdir()), [])
        self.assertEqual((self.directory/'keep.txt').read_text(encoding='utf8'), 'synthetic original project')


if __name__ == "__main__":
    unittest.main()
