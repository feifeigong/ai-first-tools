"""Synthetic shared stores: classify clients without editing source history."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from audit_import_targets import isolated_env
from core import chatgpt, common, memory_store, mover, sources
from main import Api
from test_copilot_import import desktop_index

STAMP = 1791600000000


class CodexSourceTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="codex-source-fixture-")))
        self.env = isolated_env(self.base)
        self.root = Path(self.env["CODEX_HOME"])
        (self.root / "sessions").mkdir()
        self.project = self.base / "same-project"
        self.project.mkdir()
        self.enterContext(patch.dict(os.environ, self.env, clear=True))
        self.enterContext(patch.object(common, "_isolated_home", Path(self.env["HOME"])))
        self.enterContext(patch.object(common, "_registry_env", return_value=""))
        self.enterContext(patch.object(mover, "TEST_ENV", self.env))
        self.enterContext(patch.object(mover, "data_dir", return_value=self.base / "workbench"))
        self.enterContext(patch.object(mover, "_history_file", return_value=self.base / "history.json"))
        with closing(sqlite3.connect(self.root / "state_5.sqlite")) as db, db:
            db.executescript("""
CREATE TABLE projects(id TEXT,name TEXT,position INTEGER);
CREATE TABLE project_roots(project_id TEXT,path TEXT,position INTEGER);
CREATE TABLE threads(id TEXT,source TEXT,thread_source TEXT,cwd TEXT,title TEXT,name TEXT,
recency_at_ms INTEGER,archived INTEGER,rollout_path TEXT,created_at_ms INTEGER DEFAULT 0,originator TEXT);
""")
        (self.root / ".codex-global-state.json").write_text(json.dumps({"local-projects": {"same": {"name": "合成项目", "rootPaths": [str(self.project)]}}}), encoding="utf-8")

    def add(self, name, source="cli", origin="codex_cli_rs", *, archived=0, provenance="user", database=True, present=True, cwd=None):
        sid = str(uuid.uuid4())
        path = self.root / "sessions" / f"rollout-fixture-{sid}.jsonl"
        cwd = str(cwd or self.project)
        payload = {"id": sid, "cwd": cwd, "source": source, "originator": origin, "thread_source": provenance,
                   "timestamp": "2026-10-10T00:00:00.000Z", "cli_version": "synthetic"}
        records = [{"timestamp": "2026-10-10T00:00:00.000Z", "type": "session_meta", "payload": payload}]
        for role, content in (("user", "合成问题，完整保留这段文字。"), ("assistant", "合成回答，原文末尾标记。")):
            records.append({"timestamp": "2026-10-10T00:00:01.000Z", "type": "response_item", "payload": {
                "type": "message", "role": role, "content": [{"type": "input_text" if role == "user" else "output_text", "text": content}]}})
        if present:
            path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")
        if database:
            with closing(sqlite3.connect(self.root / "state_5.sqlite")) as db, db:
                db.execute("INSERT INTO threads(id,source,thread_source,cwd,title,name,recency_at_ms,archived,rollout_path,originator) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (sid, source if isinstance(source, str) else json.dumps(source), provenance, cwd, name, name, STAMP, archived, str(path), origin))
        return sid, path

    def flat_cli(self):
        return [item for group in sources.list_groups("codex_cli") for item in group["sessions"]]

    def flat_desktop(self):
        data = chatgpt.local_data(self.root)
        return data["pinned"] + data["recent"] + [s for g in data["projects"] for s in g["sessions"]] + [s for group in data["mirrors"].values() for s in group]

    def test_mixed_clients_same_folder_are_disjoint_and_desktop_modes_stay(self):
        cli, _ = self.add("CLI 记录")
        desktop, _ = self.add("桌面 Codex", "vscode", "Codex Desktop")
        work, _ = self.add("桌面 Work", "vscode", "codex_work_desktop")
        # A CLI run in the Desktop scratch path remains CLI, rather than Work.
        scratch_cli, _ = self.add("同路径 CLI", cwd="D:/Synthetic/Documents/Codex/2026-10-21/scratch")
        local, commandline = self.flat_desktop(), self.flat_cli()
        self.assertEqual({s["id"] for s in local}, {desktop, work})
        self.assertEqual({s["id"] for s in commandline}, {cli, scratch_cli})
        self.assertEqual({s["kind"] for s in local}, {"work", "codex"})
        self.assertTrue(all(s["source"] == "codex_cli" and s["movable"] for s in commandline))
        self.assertEqual(sources.list_groups("codex_cli")[0]["path"], str(self.project))

    def test_first_metadata_and_cli_only_store_without_database_or_name_index(self):
        cli, _ = self.add("无索引 CLI", database=False)
        self.add("桌面记录", "vscode", "Codex Desktop", database=False)
        (self.root / "state_5.sqlite").unlink()
        self.assertEqual([s["id"] for s in self.flat_cli()], [cli])
        self.assertTrue(sources.installed("codex_cli"))

    def test_tui_history_ids_override_polluted_desktop_metadata_without_moving_real_desktop(self):
        terminal, _ = self.add("同名合成记录", "vscode", "Codex Desktop")
        desktop, _ = self.add("同名合成记录", "vscode", "Codex Desktop")
        work, _ = self.add("桌面 Work", "vscode", "codex_work_desktop")
        history = self.root / "history.jsonl"
        history.write_text(json.dumps({"session_id": terminal, "ts": 1791600000, "text": "合成终端输入"}) + "\n", encoding="utf-8")
        before = history.read_bytes()
        self.assertEqual({s["id"] for s in self.flat_cli()}, {terminal})
        self.assertEqual({s["id"] for s in self.flat_desktop()}, {desktop, work})
        self.assertEqual(history.read_bytes(), before)

    def test_current_tui_name_and_header_cli_source_cannot_be_masked_by_old_index(self):
        tui, _ = self.add("新版 TUI", "vscode", "codex-tui")
        stale, path = self.add("缓存仍是桌面", "vscode", "Codex Desktop")
        rows = path.read_text(encoding="utf-8").splitlines()
        meta = json.loads(rows[0])
        meta["payload"].update(source="cli", originator="codex-tui")
        path.write_text("\n".join([json.dumps(meta), *rows[1:]]) + "\n", encoding="utf-8")
        self.assertEqual({s["id"] for s in self.flat_cli()}, {tui, stale})
        self.assertFalse(self.flat_desktop())

    def test_terminal_history_prefixes_do_not_treat_text_as_source_and_skip_partial_writes(self):
        terminal = str(uuid.uuid4())
        fake = str(uuid.uuid4())
        partial = str(uuid.uuid4())
        record = {"session_id": terminal, "ts": 1791600000, "text": '合成输入' * 40000 + '\\n{"session_id":"' + fake + '","ts":1,"text":"fake"}'}
        history = self.root / "history.jsonl"
        history.write_bytes((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8") +
                            json.dumps({"session_id": partial, "ts": 1, "text": "still writing"}).encode("utf-8"))
        self.assertEqual(chatgpt.terminal_history_ids(self.root), {terminal})

    def test_archived_deleted_subagents_and_review_logs_are_not_resurrected(self):
        kept, _ = self.add("正常记录")
        self.add("已归档", archived=1)
        self.add("子任务", provenance="subagent")
        self.add("内部复核", provenance="guardian_review")
        self.add("子任务结构", source={"subagent": {"thread_spawn": {"parent_thread_id": kept}}})
        moved, path = self.add("已移入归档")
        archive = self.root / "archived_sessions"
        archive.mkdir()
        (archive / path.name).write_bytes(path.read_bytes())
        deleted, _ = self.add("已删除")
        (self.root / "sqlite").mkdir()
        with closing(sqlite3.connect(self.root / "sqlite/codex.db")) as db, db:
            db.executescript("CREATE TABLE local_thread_catalog_sync_state(host_id TEXT,initial_build_complete INTEGER); INSERT INTO local_thread_catalog_sync_state VALUES('local',1); CREATE TABLE local_thread_catalog(host_id TEXT,thread_id TEXT,source_kind TEXT,source_recency_at INTEGER,source_created_at INTEGER,missing_candidate INTEGER);")
            db.execute("INSERT INTO local_thread_catalog VALUES('local',?,'cli',0,0,1)", (deleted,))
        self.assertEqual([s["id"] for s in self.flat_cli()], [kept])

    def test_rollout_cli_origin_separates_old_rows_and_missing_body_is_disabled(self):
        sid, path = self.add("旧索引字段", "vscode", "")
        rows = path.read_text(encoding="utf-8").splitlines()
        first = json.loads(rows[0])
        first["payload"].update(source="cli", originator="codex_cli_rs")
        path.write_text("\n".join([json.dumps(first), *rows[1:]]) + "\n", encoding="utf-8")
        missing, _ = self.add("尚无正文", present=False)
        items = {s["id"]: s for s in self.flat_cli()}
        self.assertEqual(set(items), {sid, missing})
        self.assertFalse(items[missing]["movable"])
        self.assertFalse(self.flat_desktop())

    def test_cli_name_index_recency_read_only_and_no_account_or_cloud_reads(self):
        cli, _ = self.add("原名称")
        (self.root / "session_index.jsonl").write_text(json.dumps({"id": cli, "thread_name": "CLI 改过的名称", "updated_at": "2026-10-10T00:00:00Z"}) + "\n", encoding="utf-8")
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with patch.object(chatgpt, "native_state", side_effect=AssertionError("No desktop account reads")), \
             patch.object(chatgpt, "web_data", side_effect=AssertionError("No cloud reads")), patch.object(mover, "_run", side_effect=AssertionError("No exports for listing")):
            item = self.flat_cli()[0]
            self.assertEqual(item["title"], "CLI 改过的名称")
            self.assertEqual(item["ts"], STAMP)
        self.assertEqual({p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}, before)

    def test_api_cli_is_one_source_and_never_a_new_destination(self):
        self.add("命令行记录")
        with patch.object(sources, "installed", side_effect=lambda aid: aid in {"chatgpt", "codex_cli", "codex"}), patch.object(sources, "unsupported_found", return_value=[]):
            info = Api().agents()
        self.assertEqual([s["name"] for s in info["agents"]], ["ChatGPT", "Codex CLI"])
        self.assertNotIn("codex_cli", {t["id"] for t in info["targets"]})
        self.assertIn("codex", {t["id"] for t in info["targets"]})  # Existing Desktop destination retained.
        self.assertEqual(Api().sessions("codex_cli")["total"], 1)

    def test_actual_cli_export_full_copy_and_smart_archive_keep_source_unchanged(self):
        sid, path = self.add("完整的 CLI 原名称")
        desktop_index(Path(self.env["COPILOT_HOME"]))
        selected = self.flat_cli()[0]
        before = path.read_bytes()
        document = mover.export_document("codex_cli", selected)
        self.assertEqual([m["role"] for m in document["messages"]], ["user", "assistant"])
        self.assertIn("原文末尾标记", json.dumps(document, ensure_ascii=False))
        details = {}
        result = mover.move_one("codex_cli", selected, "copilot_desktop", str(self.project), details)
        self.assertEqual(result[0], "ok", result)
        self.assertEqual(mover.history_key("codex_cli", sid, "copilot_desktop", str(self.project)),
                         mover.history_key("chatgpt_work", sid, "copilot_desktop", str(self.project)))
        api = Api()
        self.assertEqual(api.sessions("codex_cli")["total"], 1)
        self.assertTrue(api.prepare_memory("codex_cli", [sid], "copilot_desktop")["ok"])
        deadline = time.monotonic() + 10
        while not api.memory_status()["finished"] and time.monotonic() < deadline:
            time.sleep(.01)
        status = api.memory_status()
        self.assertTrue(status["finished"])
        self.assertEqual(status["failed"], 0, status)
        saved = memory_store.summary(self.base / "workbench/memory/bundles" / status["items"][0]["bundle"])
        self.assertEqual(saved["title"], "完整的 CLI 原名称")
        self.assertEqual(saved["messages"], 2)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
