"""ZCode and Codex conversations can be copied into DSH on Windows and Mac layouts."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import zstandard

from core import dsh, mover, sources, zcode


def build_zcode(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE session(id TEXT, title TEXT, path TEXT, directory TEXT, time_updated INTEGER, time_created INTEGER)")
    con.execute("CREATE TABLE message(id TEXT, session_id TEXT, data TEXT, sequence INTEGER)")
    con.execute("CREATE TABLE part(id TEXT, message_id TEXT, session_id TEXT, data TEXT, sequence INTEGER)")
    con.execute(
        "INSERT INTO session VALUES (?,?,?,?,?,?)",
        ("sess-zcode-1", "ZCode 标题", r"D:\javaProject\kxEes", r"D:\javaProject\kxEes", 1789000000000, 1788000000000),
    )
    con.execute(
        "INSERT INTO message VALUES (?,?,?,?)",
        ("msg-1", "sess-zcode-1", json.dumps({"role": "user", "time": {"created": 1788000001000}}), 1),
    )
    con.execute(
        "INSERT INTO message VALUES (?,?,?,?)",
        ("msg-2", "sess-zcode-1", json.dumps({"role": "assistant", "time": {"created": 1788000002000}}), 2),
    )
    con.execute(
        "INSERT INTO part VALUES (?,?,?,?,?)",
        ("part-1", "msg-1", "sess-zcode-1", json.dumps({"type": "text", "text": "来自 ZCode 的问题"}), 1),
    )
    con.execute(
        "INSERT INTO part VALUES (?,?,?,?,?)",
        ("part-2", "msg-2", "sess-zcode-1", json.dumps({"type": "text", "text": "来自 ZCode 的回答"}), 1),
    )
    con.execute(
        "INSERT INTO part VALUES (?,?,?,?,?)",
        ("part-3", "msg-2", "sess-zcode-1", json.dumps({"type": "tool", "text": "不复制工具过程"}), 2),
    )
    con.commit()
    con.close()
    return "sess-zcode-1"


class ZcodeDshTests(unittest.TestCase):
    def test_zcode_keeps_the_visible_answer_once(self):
        with tempfile.TemporaryDirectory() as scratch:
            db = Path(scratch) / "db.sqlite"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE session(id TEXT, title TEXT, path TEXT, directory TEXT, time_updated INTEGER, time_created INTEGER)")
            con.execute("CREATE TABLE message(id TEXT, session_id TEXT, data TEXT, sequence INTEGER)")
            con.execute("CREATE TABLE part(id TEXT, message_id TEXT, session_id TEXT, data TEXT, sequence INTEGER)")
            con.execute("INSERT INTO session VALUES (?,?,?,?,?,?)", ("sess-visible", "标题", r"D:\work", r"D:\work", 1, 1))
            visible = {"role": "user", "semantics": {"uiVisibility": "visible", "transcriptVisibility": "visible"}}
            hidden = {"role": "user", "synthetic": True, "semantics": {"uiVisibility": "hidden", "transcriptVisibility": "hidden"}}
            rows = [
                ("u1", 1, visible, [{"type": "text", "text": "同一个问题"}]),
                ("u2", 2, visible, [{"type": "text", "text": "同一个问题"}]),
                ("h1", 3, hidden, [{"type": "text", "text": "内部提醒"}]),
                ("a1", 4, {"role": "assistant"}, [{"type": "reasoning", "text": "思考过程"}, {"type": "text", "text": "第一段回答"}]),
                ("a2", 5, {"role": "assistant"}, [{"type": "text", "text": "第二段回答"}]),
                ("u3", 6, visible, [{"type": "text", "text": "继续问"}]),
                ("a3", 7, {"role": "assistant"}, [{"type": "text", "text": "后续回答"}]),
            ]
            for message_id, sequence, payload, parts in rows:
                con.execute("INSERT INTO message VALUES (?,?,?,?)", (message_id, "sess-visible", json.dumps(payload), sequence))
                for index, part in enumerate(parts):
                    con.execute("INSERT INTO part VALUES (?,?,?,?,?)", (f"{message_id}-{index}", message_id, "sess-visible", json.dumps(part), index))
            con.commit()
            con.close()
            exported = zcode.document("sess-visible", db)
            self.assertEqual([item["content"] for item in exported["messages"]], ["同一个问题", "第一段回答\n\n第二段回答", "继续问", "后续回答"])
            events, _seq = dsh.compose_events("session-visible", 1, r"D:\work", "标题", [(item["role"], item["content"]) for item in exported["messages"]])
            deltas = [event["data"]["chunk"]["text"] for event in events if event.get("type") == "assistant/chunk"]
            users = [event["data"]["content"][0]["text"] for event in events if event.get("type") == "user/message"]
            self.assertEqual(users, ["同一个问题", "继续问"])
            self.assertEqual(deltas, ["第一段回答\n\n第二段回答", "后续回答"])

    def test_codex_tool_round_is_written_as_one_visible_reply(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            dsh_root = root / "harness"
            (dsh_root / "sessions").mkdir(parents=True)
            (dsh_root / "storages").mkdir()
            folder = root / "work"
            folder.mkdir()
            document = {
                "title": "安装 GPT Taste 并审查 UI 适配",
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "请改一下界面"}]},
                    {"role": "assistant", "content": [
                        {"type": "text", "text": "我先看一下现有界面。"},
                        {"type": "thinking", "text": "这里是内部推理，不单独显示"},
                        {"type": "tool_use", "id": "call-1", "name": "shell", "input": {}},
                    ]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call-1", "content": "命令输出"}]},
                    {"role": "assistant", "content": [{"type": "output_text", "text": "界面已经改好。"}]},
                ],
            }
            report = dsh.import_document(document, str(folder), dsh_root)
            saved = dsh.document(report["id"], dsh_root)
            self.assertEqual(
                [item["content"] for item in saved["messages"]],
                ["请改一下界面", "我先看一下现有界面。\n\n界面已经改好。"],
            )
            with patch("core.dsh._refresh_app", return_value=True) as refresh, \
                    patch("core.dsh.data_root", return_value=dsh_root):
                again = dsh.import_document(document, str(folder), dsh_root, product="dsh")
                refresh.assert_called_once_with("dsh", dsh_root)
            self.assertTrue(again["refreshed"])

    def test_windows_and_mac_project_folders(self):
        self.assertEqual(dsh.project_key(r"D:\javaProject\kxEes", "win32"), "--D-javaProject-kxEes--")
        self.assertEqual(dsh.project_key(r"D:\\", "win32"), "--D---")
        self.assertEqual(dsh.project_key("/Users/a/proj", "darwin"), "--Users-a-proj--")

    def test_zcode_round_trip_into_dsh_and_codex_shaped_text(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            db = root / "db.sqlite"
            sid = build_zcode(db)
            groups = zcode.groups(db)
            self.assertEqual(groups[0]["sessions"][0]["id"], sid)
            self.assertTrue(groups[0]["sessions"][0]["movable"])
            exported = zcode.document(sid, db)
            self.assertEqual([item["content"] for item in exported["messages"]], ["来自 ZCode 的问题", "来自 ZCode 的回答"])

            dsh_root = root / "harness"
            (dsh_root / "sessions").mkdir(parents=True)
            (dsh_root / "storages").mkdir()
            (dsh_root / "storages" / "session_projcache.json").write_text(
                json.dumps({"tables": {"sessions": {}}}), encoding="utf-8"
            )
            folder = root / "work"
            folder.mkdir()
            report = dsh.import_document(exported, str(folder), dsh_root)
            saved = dsh.document(report["id"], dsh_root)
            self.assertEqual([item["content"] for item in saved["messages"]], [item["content"] for item in exported["messages"]])
            cache = json.loads((dsh_root / "storages" / "session_projcache.json").read_text(encoding="utf-8"))
            self.assertEqual(cache["tables"]["sessions"][report["id"]]["identity"]["cwd"], str(folder))

            codex_doc = {"title": "来自 Codex", "messages": [{"role": "user", "content": "Codex 问题"}, {"role": "assistant", "content": "Codex 回答"}]}
            codex_report = dsh.import_document(codex_doc, str(folder), dsh_root)
            codex_saved = dsh.document(codex_report["id"], dsh_root)
            self.assertEqual([item["content"] for item in codex_saved["messages"]], ["Codex 问题", "Codex 回答"])

    def test_move_zcode_and_codex_documents_through_the_shared_importer(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            db = root / "db.sqlite"
            sid = build_zcode(db)
            dsh_root = root / "harness"
            (dsh_root / "sessions").mkdir(parents=True)
            folder = root / "work"
            folder.mkdir()
            preview = root / "mover-data"
            with patch.dict(os.environ, {"AI_FIRST_MOVER_PREVIEW_DATA": str(preview)}), \
                    patch("core.zcode.database", return_value=db), \
                    patch("core.dsh.data_root", return_value=dsh_root):
                state, message = mover.move_one("zcode", {"id": sid, "title": "ZCode 标题"}, "dsh", str(folder))
                self.assertEqual(state, "ok", message)
                codex_doc = {"id": "codexsess01", "title": "Codex 标题", "cwd": str(folder), "messages": [
                    {"role": "user", "content": "请继续"}, {"role": "assistant", "content": "好的"}]}
                imported = mover._import_document(root / "unused.json", codex_doc, "dsh", {})
                self.assertEqual(imported[0], "ok")
            stored = list((dsh_root / "sessions").rglob("session.jsonl.zstd"))
            self.assertEqual(len(stored), 2)

    def test_official_and_community_stores_stay_separate(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            official = root / ".dsh"
            community = root / "dsh-desktop" / "harness"
            folder = root / "work"
            for path in (official, community, folder):
                path.mkdir(parents=True)
            for path in (official, community):
                (path / "sessions").mkdir()
                (path / "storages").mkdir()
                (path / "storages" / "session_projcache.json").write_text(
                    json.dumps({"tables": {"sessions": {}}}), encoding="utf-8"
                )
            document = {"title": "分开存放", "messages": [{"role": "user", "content": "官方还是社区"}, {"role": "assistant", "content": "两边各一份"}]}
            with patch("core.dsh.home", return_value=root), patch("core.dsh.appdata", return_value=root):
                self.assertEqual(dsh.official_root(), official)
                self.assertEqual(dsh.community_root(), community)
                official_report = dsh.import_document(document, str(folder), product="dsh_official")
                community_report = dsh.import_document(document, str(folder), product="dsh")
                self.assertNotEqual(official_report["id"], community_report["id"])
                self.assertTrue(str(official_report["location"]).startswith(str(official)))
                self.assertTrue(str(community_report["location"]).startswith(str(community)))
                self.assertEqual(len(list(official.rglob("session.jsonl.zstd"))), 1)
                self.assertEqual(len(list(community.rglob("session.jsonl.zstd"))), 1)
                header = zstandard.ZstdDecompressor().decompress(Path(official_report["location"]).read_bytes())
                self.assertTrue(header.endswith(b"\n"))
                self.assertEqual(header.count(b"\n"), 1)
                projection = json.loads((official / "storages" / "session_projcache" / "sessions" / f"{official_report['id']}.json").read_text(encoding="utf-8"))
                self.assertEqual(projection["record"]["rows"]["sessionListMetadata"]["val"]["blank"], False)
                self.assertEqual(projection["record"]["rows"]["title"]["val"], "分开存放")

    def test_repeat_copy_refreshes_the_open_official_window(self):
        with tempfile.TemporaryDirectory() as scratch:
            session = {"id": "sess_repeat_refresh", "source": "zcode"}
            with patch.object(mover, "already_moved", return_value=True), \
                    patch.object(dsh, "official_root", return_value=Path(scratch)), \
                    patch.object(dsh, "_refresh_app", return_value=True) as refresh:
                state, message = mover.move_one("zcode", session, "dsh_official", scratch)
            self.assertEqual(state, "skipped")
            self.assertIn("已刷新", message)
            refresh.assert_called_once_with("dsh_official", Path(scratch))

    def test_unreadable_installed_apps_stay_off_the_sidebar(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / ".codebuddy").mkdir()
            (root / "AppData" / "Roaming" / "Grok Bot").mkdir(parents=True)
            with patch("core.sources.home", return_value=root):
                self.assertEqual(sources.unsupported_found(), [])


if __name__ == "__main__":
    unittest.main()
