"""Synthetic Copilot events only; never read an installed account or call a model."""

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
from core import codex_import, common, copilot_local, imports, mover, sources
from main import AGENTS, Api
from test_imports import CODEX_SCHEMA


def event(kind: str, data: dict, **extra) -> dict:
    return {"id": str(uuid.uuid4()), "type": kind, "timestamp": "2026-10-15T10:00:00Z", "data": data, **extra}


def conversation(sid: str, cwd: str = "", rounds: int = 1) -> list[dict]:
    result = [event("session.start", {"sessionId": sid, "version": 1, "producer": "copilot-agent",
                                       "context": {"cwd": cwd}, "selectedModel": "synthetic-model"})]
    for index in range(rounds):
        result += [event("user.message", {"content": f"用户问题 {index}\n" + ("完整正文 " * 50).rstrip()}),
                   event("assistant.message", {"messageId": str(uuid.uuid4()), "content": f"助手回答 {index}\n" + ("多行回答 " * 50).rstrip()})]
    return result


class CopilotFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ai-first-copilot-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.env = isolated_env(self.base)
        self.enterContext(patch.dict(os.environ, self.env, clear=True))
        self.enterContext(patch.object(common, "_isolated_home", Path(self.env["HOME"])))
        self.enterContext(patch.object(mover, "TEST_ENV", self.env))
        self.root = copilot_local.root()
        self.sid = str(uuid.uuid4())
        self.directory = self.base / "合成项目 with spaces"
        self.directory.mkdir()

    def write(self, records=None, sid=None):
        sid = sid or self.sid
        path = self.root / "session-state" / sid / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in
                                 (records if records is not None else conversation(sid, str(self.directory)))) + "\n", encoding="utf-8")
        if sid == self.sid and not (self.root / "data.db").is_file():
            self.index([(sid, None, str(self.directory), "2026-10-16T09:00:00Z", None, None)])
        return path

    def index(self, rows):
        self.root.mkdir(parents=True, exist_ok=True)
        database = self.root / "data.db"
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT,cwd TEXT,updated_at TEXT,archived_at TEXT,deleted_at TEXT)")
            connection.execute("DELETE FROM sessions")
            connection.executemany("INSERT INTO sessions VALUES(?,?,?,?,?,?)", rows)
        return database

    def sessions(self):
        return [session for group in sources.list_groups("copilot_desktop") for session in group["sessions"]]


class CopilotTests(CopilotFixture):
    def test_desktop_membership_shared_label_metadata_and_source_bytes(self):
        source = self.write()
        other = str(uuid.uuid4())
        shared = self.write(conversation(other, str(self.directory)), other)
        database = self.index([(self.sid, "桌面端标题", str(self.directory), "2026-10-16T09:00:00Z", None, None)])
        before = {path: path.read_bytes() for path in (source, shared, database)}
        rows = self.sessions()
        self.assertEqual(len(rows), 1)
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id[self.sid]["title"], "桌面端标题")
        self.assertEqual(by_id[self.sid]["sourceLabel"], "Copilot Desktop")
        self.assertNotIn(other, by_id)
        self.assertTrue(all(row["movable"] for row in rows))
        self.assertEqual(rows[0]["id"], self.sid)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_windows_and_mac_detect_same_store_without_authentication(self):
        for platform_name in ("win32", "darwin"):
            with self.subTest(platform=platform_name), patch.object(sys, "platform", platform_name):
                self.assertFalse(sources.installed("copilot_desktop"))
                self.write()
                self.assertTrue(sources.installed("copilot_desktop"))
                self.assertEqual(len(self.sessions()), 1)
                self.assertFalse(any(self.root.rglob("*auth*")))
                (self.root / "session-state" / self.sid / "events.jsonl").unlink()
                (self.root / "session-state" / self.sid).rmdir()
                (self.root / "session-state").rmdir()
                (self.root / "data.db").unlink()

    def test_long_history_and_completed_events_keep_full_body_without_stream_duplicates(self):
        records = conversation(self.sid, str(self.directory), 125)
        records.insert(1, event("assistant.message_delta", {"deltaContent": "不要重复这个流式片段"}, ephemeral=True))
        records += [records[-1], event("session.compaction_complete", {"summary": "不能替换完整历史"}),
                    event("session.title_changed", {"title": "完整长对话"})]
        self.write(records)
        document = copilot_local.document(self.sid)
        self.assertEqual(len(document["messages"]), 250)
        self.assertEqual(document["title"], "完整长对话")
        self.assertEqual(document["messages"][-1]["content"][0]["text"], records[-4]["data"]["content"])
        self.assertNotIn("不要重复这个流式片段", json.dumps(document, ensure_ascii=False))

    def test_tools_pair_once_and_preserve_detailed_results_reasoning_and_errors(self):
        records = conversation(self.sid)
        request = {"toolCallId": "tool-1", "name": "read_file", "arguments": {"path": "synthetic.txt"}}
        records += [event("assistant.reasoning", {"reasoningId": "reason-1", "content": "完整思考"}),
                    event("assistant.message", {"content": "正在读取", "toolRequests": [request]}),
                    event("tool.execution_start", {"toolCallId": "tool-1", "toolName": "read_file", "arguments": request["arguments"]}),
                    event("tool.execution_complete", {"toolCallId": "tool-1", "success": False,
                        "result": {"content": "全部输出", "detailedContent": "完整详细输出", "structuredContent": {"a": [1, 2]}},
                        "error": {"message": "合成失败"}})]
        self.write(records)
        document = copilot_local.document(self.sid)
        blocks = [block for message in document["messages"] for block in message["content"]]
        calls = [block for block in blocks if block["type"] == "tool_use"]
        results = [block for block in blocks if block["type"] == "tool_result"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["is_error"])
        self.assertIn("完整详细输出", results[0]["content"])
        self.assertIn('"a": [1, 2]', results[0]["content"])
        self.assertIn("合成失败", results[0]["content"])
        self.assertIn({"type": "thinking", "text": "完整思考"}, blocks)

    def test_reader_keeps_leading_trailing_whitespace_and_indented_code_verbatim(self):
        records = conversation(self.sid)
        text = "\n  ```python\n    print('synthetic')  \n  ```\n\n"
        records[1]["data"]["content"] = text
        self.write(records)
        self.assertEqual(copilot_local.document(self.sid)["messages"][0]["content"][0]["text"], text)

    def test_missing_and_orphan_tool_results_are_reference_notes_never_fabricated(self):
        records = conversation(self.sid) + [event("tool.execution_start", {"toolCallId": "missing", "toolName": "shell", "arguments": {"command": "echo synthetic"}}),
            event("tool.execution_complete", {"toolCallId": "orphan", "success": True, "result": {"content": "孤立输出"}})]
        self.write(records)
        document = copilot_local.document(self.sid)
        blocks = [block for message in document["messages"] for block in message["content"]]
        self.assertFalse(any(block["type"] in ("tool_use", "tool_result") for block in blocks))
        self.assertIn("没有保存返回结果", json.dumps(document, ensure_ascii=False))
        self.assertIn("孤立输出", json.dumps(document, ensure_ascii=False))

    def test_subagent_interleaving_cannot_capture_parent_tool_pair(self):
        records = conversation(self.sid) + [event("tool.execution_start", {"toolCallId": "same", "toolName": "shell", "arguments": {"x": 1}}),
            event("tool.execution_complete", {"toolCallId": "same", "success": True, "result": {"content": "子任务输出"}}, agentId="child"),
            event("tool.execution_complete", {"toolCallId": "same", "success": True, "result": {"content": "主任务输出"}})]
        self.write(records)
        blocks = [block for message in copilot_local.document(self.sid)["messages"] for block in message["content"]]
        results = [block for block in blocks if block["type"] == "tool_result"]
        self.assertEqual(len(results), 1)
        self.assertIn("主任务输出", results[0]["content"])
        self.assertTrue(any("子任务输出" in block.get("text", "") for block in blocks))

    def test_completion_without_saved_output_is_not_a_fabricated_empty_result(self):
        self.write(conversation(self.sid) + [event("tool.execution_start", {"toolCallId": "missing-output", "toolName": "shell"}),
            event("tool.execution_complete", {"toolCallId": "missing-output", "success": True})])
        blocks = [block for message in copilot_local.document(self.sid)["messages"] for block in message["content"]]
        self.assertFalse(any(block["type"] in ("tool_use", "tool_result") for block in blocks))
        self.assertTrue(any("未保存返回内容" in block.get("text", "") for block in blocks))

    def test_archived_deleted_and_cloud_only_records(self):
        archived, deleted, cloud = (str(uuid.uuid4()) for _ in range(3))
        for sid in (archived, deleted):
            self.write(conversation(sid), sid)
        self.index([(archived, "归档", "", "", "2026-10-15", None), (deleted, "删除", "", "", None, "2026-10-15"),
                    (cloud, "仅有桌面索引", "", "", None, None)])
        rows = self.sessions()
        self.assertEqual([row["id"] for row in rows], [cloud])
        self.assertFalse(rows[0]["movable"])
        self.assertIn("无法读取", rows[0]["note"])
        with self.assertRaisesRegex(ValueError, "归档或删除"):
            copilot_local.document(archived)

    def test_malformed_or_changing_file_cannot_silently_import_partial_history(self):
        path = self.write()
        path.write_text(path.read_text(encoding="utf-8") + '{"type":', encoding="utf-8")
        self.assertFalse(self.sessions()[0]["movable"])
        with patch.object(mover, "_import_document") as importer:
            result = mover.move_one("copilot_desktop", {"id": self.sid}, "claude_code", str(self.directory))
            self.assertEqual(result[0], "failed")
            importer.assert_not_called()
        self.write()
        before = path.stat()
        with patch.object(copilot_local.os, "fstat", return_value=type("Stat", (), {
                "st_size": before.st_size - 1, "st_mtime_ns": before.st_mtime_ns, "st_ino": before.st_ino})()):
            with self.assertRaisesRegex(ValueError, "仍在变化"):
                copilot_local.document(self.sid)

    def test_unknown_versions_shapes_duplicate_ids_and_message_formats_fail_closed(self):
        for mutate in (
            lambda rows: rows[0]["data"].update(version=2),
            lambda rows: rows[0]["data"].update(sessionId="different"),
            lambda rows: rows[1]["data"].update(content=[{"unknown": "shape"}]),
            lambda rows: rows.append(dict(rows[-1], data={"content": "conflicting same event"})),
            lambda rows: rows.append(event("assistant.message_new_format", {"content": "unknown"})),
            lambda rows: rows.append(event("session.snapshot_rewind", {"snapshotId": "synthetic"})),
            lambda rows: rows.append(event("session.truncation", {})),
        ):
            with self.subTest(mutate=mutate):
                records = conversation(self.sid)
                mutate(records)
                self.write(records)
                self.assertFalse(self.sessions()[0]["movable"])

    def test_metadata_schema_change_does_not_resurrect_all_records_as_shared(self):
        self.write()
        with closing(sqlite3.connect(self.root / "data.db")) as connection, connection:
            connection.execute("DROP TABLE sessions")
            connection.execute("CREATE TABLE new_unknown_schema(secret TEXT)")
        with self.assertRaisesRegex(ValueError, "索引"):
            copilot_local.groups()
        self.assertIn("格式已变化", Api().sessions("copilot_desktop")["error"])

    def test_only_tool_logs_are_not_movable(self):
        records = conversation(self.sid)[:1] + [event("tool.execution_start", {"toolCallId": "missing", "toolName": "shell"})]
        self.write(records)
        self.assertFalse(self.sessions()[0]["movable"])
        with self.assertRaisesRegex(ValueError, "没有可搬运"):
            copilot_local.document(self.sid)

    def test_unsafe_session_id_is_rejected_before_read(self):
        for sid in ("../secrets", "..\\secrets", "a/b", "", "/absolute/session"):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                copilot_local.document(sid)

    def test_api_refresh_registration_and_writable_target(self):
        self.write()
        api = Api()
        self.assertIn("copilot_desktop", {agent["id"] for agent in AGENTS})
        with patch.object(sources, "installed", side_effect=lambda aid: aid == "copilot_desktop"):
            data = api.agents()
        self.assertEqual([agent["id"] for agent in data["agents"]], ["copilot_desktop"])
        self.assertTrue(data["targets"][0]["canTarget"])
        self.assertIn("copilot_desktop", mover.TARGETS)
        self.assertEqual(api.sessions("copilot_desktop")["total"], 1)
        other = str(uuid.uuid4())
        self.write(conversation(other), other)
        self.assertEqual(api.sessions("copilot_desktop")["total"], 1)
        self.assertEqual(api.sessions("copilot_desktop", refresh=True)["total"], 1)
        self.index([(self.sid, "桌面聊天", str(self.directory), "2026-10-16T09:00:00Z", None, None),
                    (other, "另一个桌面聊天", str(self.directory), "2026-10-16T09:00:00Z", None, None)])
        self.assertEqual(api.sessions("copilot_desktop", refresh=True)["total"], 2)

    def test_desktop_list_excludes_cli_orphans_and_empty_provisional_sessions(self):
        internal = self.root / "chats" / "2026-10-15" / ("file-c-users-encoded-" + self.sid[:8])
        self.write(conversation(self.sid, str(internal)))
        for _ in range(16):
            (self.root / "session-state" / str(uuid.uuid4())).mkdir()
        shared = str(uuid.uuid4())
        self.write(conversation(shared), shared)
        empty = str(uuid.uuid4())
        with closing(sqlite3.connect(self.root / "data.db")) as connection, connection:
            connection.execute("ALTER TABLE sessions ADD COLUMN session_type TEXT DEFAULT 'general_chat'")
            connection.execute("ALTER TABLE sessions ADD COLUMN provisional INTEGER DEFAULT 0")
            connection.execute("INSERT INTO sessions(id,provisional) VALUES(?,1)", (empty,))
        groups = copilot_local.groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["title"], "聊天")
        self.assertEqual(groups[0]["path"], "")
        self.assertEqual([row["id"] for row in groups[0]["sessions"]], [self.sid])
        self.assertEqual(groups[0]["sessions"][0]["folder"], "")
        with self.assertRaisesRegex(ValueError, "未登记"):
            copilot_local.document(shared)

    def test_workspace_project_metadata_and_archive_match_desktop(self):
        self.write()
        with closing(sqlite3.connect(self.root / "data.db")) as connection, connection:
            connection.executescript("CREATE TABLE projects(id TEXT,name TEXT,main_repo_path TEXT);"
                                     "CREATE TABLE workspaces(session_id TEXT,project_id TEXT,name TEXT,source_path TEXT,archived_at TEXT,provisional INTEGER);")
            connection.execute("INSERT INTO projects VALUES('p','真正的项目',?)", (str(self.directory),))
            connection.execute("INSERT INTO workspaces VALUES(?,'p','项目会话',NULL,NULL,0)", (self.sid,))
        groups = copilot_local.groups()
        self.assertEqual(groups[0]["title"], "真正的项目")
        self.assertEqual(groups[0]["path"], str(self.directory))
        with closing(sqlite3.connect(self.root / "data.db")) as connection, connection:
            connection.execute("UPDATE workspaces SET archived_at='2026-10-16T00:00:00Z'")
        self.assertEqual(copilot_local.groups(), [])
        with self.assertRaisesRegex(ValueError, "归档"):
            copilot_local.document(self.sid)


@unittest.skipUnless(mover.txcript_path(), "Requires the project's built migration engine")
class NativeCopilotImportTests(CopilotFixture):
    def test_copilot_moves_to_existing_targets_and_rereads_full_body_readonly(self):
        database = Path(self.env["CODEX_HOME"]) / "state_5.sqlite"
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(CODEX_SCHEMA)
        records = conversation(self.sid, str(self.directory), 125)
        records += [event("assistant.message", {"content": "调用测试工具", "toolRequests": [
            {"toolCallId": "call-synthetic", "name": "Read", "arguments": {"file_path": "synthetic.txt"}}]}),
            event("tool.execution_complete", {"toolCallId": "call-synthetic", "success": True, "result": {"content": "完整工具返回"}})]
        path = self.write(records)
        before = path.read_bytes()
        for target in ("cursor_desktop", "codex", "chatgpt_work", "claude_code", "workbuddy", "workbuddy_ai"):
            with self.subTest(target=target):
                session = self.sessions()[0]
                details = {}
                state, message = mover.move_one("copilot_desktop", session, target, str(self.directory), details)
                self.assertEqual(state, "ok", message)
                output = self.base / f"reread-{target}.json"
                exported = mover._run(["export", details["importedId"], "--from", mover.TARGETS[target]["harness"], "--out", str(output)], mover.destination_env(target))
                self.assertEqual(exported.returncode, 0, exported.stderr)
                reread = json.loads(output.read_text(encoding="utf-8"))
                codex_import.verify_body(copilot_local.document(self.sid), reread)
                serialized = json.dumps(reread, ensure_ascii=False)
                self.assertIn("用户问题 0", serialized)
                self.assertIn("助手回答 124", serialized)
                self.assertIn("完整工具返回", serialized)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(mover.move_one("copilot_desktop", session, target, str(self.directory))[0], "skipped")


if __name__ == "__main__":
    unittest.main()
