from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core import memory_store as store, memory_deploy as deploy, memory_server as server, memory_desktop, memory_workspace, mover, sources, copilot_local
from core.memory_audit import desktop_fixture, legacy_project_fixture, isolated_connections, persistent_projects_fixture
from main import Api


def fixture():
    return {"id": "synthetic-history", "title": "合成开发讨论", "messages": [
        {"id": "user-1", "role": "user", "timestamp": "2026-10-01T00:00:00Z", "content": "最初采用 SQLite 数据库。保留完整对话迁移。"},
        {"id": "assistant-1", "role": "assistant", "parent_id": "user-1", "content": [
            {"type": "text", "text": "数据库设计\n```sql\nSELECT '合成代码';\n```\n"},
            {"type": "image", "asset_pointer": "synthetic/image.png", "mime_type": "image/png"}]},
        {"id": "user-2", "role": "user", "content": "不要删除完整迁移。智能模式也需要保留。之前的全量读取方案不满意。"},
        {"id": "tool-1", "role": "tool", "content": {"type": "tool_result", "output": "历史工具结果，仅作资料"}},
        {"id": "assistant-long", "role": "assistant", "content": "完整长消息\n" + "甲乙丙丁中文分页验证。\n" * 1800 + "末尾完整标记"},
    ], "metadata": {"branch": "synthetic-active", "attachments": ["synthetic/image.png"]}}


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.scratch = self.enterContext(tempfile.TemporaryDirectory())
        self.base = Path(self.scratch).resolve()
        self.library = self.base / "library"
        self.workspace = memory_workspace.create(self.library)
        self.desktop = self.base / "desktop"
        desktop_fixture(self.desktop)
        self.enterContext(patch.object(memory_desktop, "root", return_value=self.desktop))
        self.original = fixture()
        self.info = store.ingest(self.library, "chatgpt", "synthetic-history", self.original)
        self.bundle = self.library / "bundles" / self.info["id"]

    def plan(self, target="copilot_desktop"):
        return deploy.build_plan(self.workspace, target, self.library, [self.info["id"]])

    def test_frozen_audit_scope_guard_rejects_outside_before_opening_any_database(self):
        with patch.object(sqlite3, "connect", wraps=sqlite3.connect) as opened:
            with isolated_connections(self.base):
                with self.assertRaisesRegex(ValueError, "隔离"):
                    sqlite3.connect(self.base.parent / "synthetic-outside-audit/data.db")
                opened.assert_not_called()
                with closing(sqlite3.connect((self.desktop / "data.db").as_uri() + "?mode=ro", uri=True)) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)
                self.assertEqual(opened.call_count, 1)

    def test_current_copilot_project_insert_legacy_type_repair_and_rollback_preserve_schema(self):
        persistent_projects_fixture(self.desktop)
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            schema = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        result, _ = self.install()
        path = self.library / "deployments" / result["id"] / "receipt.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        native = saved["desktop"]
        note = self.desktop / "session-state" / native["session_id"] / "events.jsonl"
        before = note.read_bytes()
        native["rows"]["sessions"]["session_type"] = "workspace"
        path.write_text(store.encoded(saved), encoding="utf-8")
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE sessions SET session_type='workspace' WHERE id=?", (native["session_id"],))
        self.assertEqual(deploy.desktop_link(self.library, result["id"]), "ghapp://sessions/" + native["session_id"])
        self.assertEqual(note.read_bytes(), before)
        self.assertTrue(deploy.install(deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"]), self.library)["reused"])
        deploy.rollback(self.library, result["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM persistent_projects").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall(), schema)
            self.assertEqual(db.execute("SELECT value FROM app_state").fetchone()[0], "never-copy-this-synthetic-value")

    def test_current_copilot_modified_trigger_and_nonproject_plan_are_still_denied(self):
        persistent_projects_fixture(self.desktop)
        plan = self.plan()
        plan["desktop"]["rows"]["sessions"]["session_type"] = "agent"
        with self.assertRaises(ValueError): deploy.install(plan, self.library)
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("DROP TRIGGER sessions_insert_agent")
            db.execute('''CREATE TRIGGER sessions_insert_agent AFTER INSERT ON sessions
                WHEN NEW.session_type = 'project' BEGIN INSERT INTO "persistent_projects" (session_id) VALUES (NEW.id); END''')
        with self.assertRaises(sqlite3.DatabaseError): deploy.install(self.plan(), self.library)
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM persistent_projects").fetchone()[0], 0)

    def test_current_persistent_project_association_protects_legacy_orphan_and_rollback(self):
        persistent_projects_fixture(self.desktop)
        result, native = self.legacy_orphan()
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("DROP TRIGGER agents_validate_insert")
            db.execute("INSERT INTO persistent_projects(session_id) VALUES(?)", (native["session_id"],))
        with self.assertRaises(deploy.SavedEntryError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])

        with self.assertRaisesRegex(ValueError, "后续"):
            deploy.rollback(self.library, result["id"])
        self.assertTrue((self.workspace / ".agent-memory/manifest.json").is_file())

    def install(self, target="copilot_desktop"):
        plan = self.plan(target)
        result = deploy.install(plan, self.library)
        return result, store.HistoryReader(self.workspace / ".agent-memory")

    def test_saved_records_reopen_after_restart_without_opening_or_reimporting(self):
        from main import Api
        result, _ = self.install()
        before = {p.relative_to(self.desktop): p.read_bytes() for p in self.desktop.rglob("*") if p.is_file()}
        with patch("main.memory_jobs.library", return_value=self.library), patch("main.open_external") as opened, \
             patch.object(mover, "export_document", side_effect=AssertionError("Saved archive needs no source export")):
            api = Api()
            self.assertEqual([r["id"] for r in api.memory_records()["items"]], [result["id"]])
            selected = api.select_memory_record(result["id"])
            self.assertTrue(selected["ok"])
            self.assertEqual(selected["deployment"]["desktop_title"], result["desktop_title"])
            self.assertEqual(api._saved_memory_items()[0]["bundle"], self.info["id"])
            self.assertTrue(api.search_memory("数据库")["hits"])
            self.assertIn("error", api.open_memory_desktop("0" * 32))
            opened.assert_not_called()  # Registration and reopening the workbench record are independent of navigation.
        self.assertEqual({p.relative_to(self.desktop): p.read_bytes() for p in self.desktop.rglob("*") if p.is_file()}, before)

    def prepare_batch(self, identities):
        api = Api()
        api._groups = {"chatgpt": [{"sessions": [{"id": identity, "title": "合成开发讨论", "movable": True} for identity in set(identities)]}]}
        self.assertTrue(api.prepare_memory("chatgpt", identities, "copilot_desktop").get("ok"))
        deadline = time.monotonic() + 10
        while not api.memory_status()["finished"] and time.monotonic() < deadline: time.sleep(.01)
        self.assertEqual(api.memory_status()["failed"], 0)
        plan = api.memory_plan()
        self.assertTrue(plan.get("ok"), plan)
        return api, plan

    def test_overlapping_batches_keep_one_native_entry_per_source_and_preserve_followup(self):
        with patch("main.memory_jobs.library", return_value=self.library), patch.object(mover, "export_document", return_value=self.original):
            api, plan = self.prepare_batch(["synthetic-history", "same-title-second", "synthetic-history"])
            self.assertEqual(len(plan["entries"]), 2)
            initial = api.deploy_memory()
            self.assertTrue(initial.get("ok"), initial)
            self.assertEqual(len(initial["entries"]), 2)
            self.assertNotEqual(*[i["workspace"] for i in initial["entries"]])
            receipt = json.loads((self.library / "deployments" / initial["entries"][0]["id"] / "receipt.json").read_text(encoding="utf-8"))
            sid = receipt["desktop"]["session_id"]
            journal = self.desktop / "session-state" / sid / "events.jsonl"
            journal.write_bytes(journal.read_bytes() + b'{"type":"user.message","data":{"content":"synthetic follow-up"}}\n')
            with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
                db.execute("UPDATE sessions SET title='user renamed',is_running=1 WHERE id=?", (sid,))
            before = {p.relative_to(self.desktop): p.read_bytes() for p in self.desktop.rglob("*") if p.is_file()}
            workspace_before = {p.relative_to(self.library / "copilot-workspaces"): p.read_bytes() for p in (self.library / "copilot-workspaces").rglob("*") if p.is_file()}
            for chosen in (["same-title-second"], ["same-title-second", "synthetic-history"]):
                fresh, planned = self.prepare_batch(chosen)
                self.assertEqual(planned["reused_count"], len(chosen))
                repeated = fresh.deploy_memory()
                self.assertTrue(repeated.get("ok"), repeated)
                self.assertEqual(repeated["reused_count"], len(chosen))
            self.assertEqual({p.relative_to(self.desktop): p.read_bytes() for p in self.desktop.rglob("*") if p.is_file()}, before)
            self.assertEqual({p.relative_to(self.library / "copilot-workspaces"): p.read_bytes() for p in (self.library / "copilot-workspaces").rglob("*") if p.is_file()}, workspace_before)
            self.assertEqual(len(deploy.saved_records(self.library)), 2)
            # New source messages update only the workbench archive; the continued chat stays untouched.
            extended = copy.deepcopy(self.original)
            extended["messages"].append({"id": "new-source", "role": "user", "content": "新增的合成资料"})
            store.ingest(self.library, "chatgpt", "synthetic-history", extended)
            self.assertTrue(store.HistoryReader(Path(initial["entries"][0]["location"])).search("新增的合成资料")["hits"])

    def test_partial_batch_retry_reuses_finished_entry(self):
        original_create = memory_desktop.create
        count = 0
        def fail_second(plan):
            nonlocal count
            count += 1
            if count == 2: raise ValueError("合成的第二条失败")
            return original_create(plan)
        with patch("main.memory_jobs.library", return_value=self.library), patch.object(mover, "export_document", return_value=self.original):
            api, _ = self.prepare_batch(["synthetic-history", "second"])
            with patch.object(memory_desktop, "create", side_effect=fail_second):
                self.assertIn("error", api.deploy_memory())
            first = deploy.saved_records(self.library)
            self.assertEqual(len(first), 1)
            self.assertTrue(api.memory_plan().get("ok"))
            done = api.deploy_memory()
            self.assertTrue(done.get("ok"), done)
            self.assertEqual(done["reused_count"], 1)
            self.assertIn(first[0]["id"], [item["id"] for item in done["entries"]])
            with closing(sqlite3.connect(self.desktop / "data.db")) as db:
                for table in ("sessions", "projects", "workspaces"):
                    self.assertEqual(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 2)

    def test_two_prepared_plans_cannot_install_duplicate_and_process_lock_blocks_overlap(self):
        first = deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        second = deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        with deploy.deployment_lock(self.library):
            with self.assertRaises(ValueError): deploy.install(first, self.library)
        original = deploy.install(first, self.library)
        repeated = deploy.install(second, self.library)
        self.assertTrue(repeated["reused"])
        self.assertEqual(repeated["id"], original["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 1)

    def test_hidden_missing_or_changed_entries_do_not_silently_duplicate(self):
        result, _ = self.install()
        path = self.library / "deployments" / result["id"] / "receipt.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        sid = saved["desktop"]["session_id"]
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE sessions SET archived_at='synthetic-time' WHERE id=?", (sid,))
        with self.assertRaises(ValueError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE sessions SET archived_at=NULL WHERE id=?", (sid,))
            db.execute("DELETE FROM workspaces WHERE id=?", (saved["desktop"]["workspace_id"],))
        with self.assertRaises(ValueError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])

    def legacy_orphan(self):
        """Earlier previews used workspace sessions that Desktop could discard."""
        import shutil
        result, _ = self.install()
        path = self.library / "deployments" / result["id"] / "receipt.json"
        saved = json.loads(path.read_text(encoding="utf-8"))
        native = saved["desktop"]
        sid = native["session_id"]
        native["rows"]["sessions"]["session_type"] = "workspace"
        path.write_text(store.encoded(saved), encoding="utf-8")
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE sessions SET session_type='workspace' WHERE id=?", (sid,))
            db.execute("DELETE FROM workspaces WHERE id=?", (native["workspace_id"],))
            db.execute("DELETE FROM projects WHERE id=?", (native["rows"]["projects"]["id"],))
        shutil.rmtree(self.desktop / "session-state" / sid)
        return result, native

    def test_legacy_orphan_repeated_move_creates_one_visible_entry_and_preserves_old_metadata(self):
        old, native = self.legacy_orphan()
        old_files = {p.relative_to(self.workspace): p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}
        old_receipt = (self.library / "deployments" / old["id"] / "receipt.json").read_bytes()
        self.assertEqual(deploy.saved_records(self.library), [])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            old_row = db.execute("SELECT * FROM sessions WHERE id=?", (native["session_id"],)).fetchone()
            old_schema = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        plan = deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        self.assertNotIn("reuse", plan)
        self.assertNotEqual(Path(plan["workspace"]), self.workspace)
        result = deploy.install(plan, self.library)
        self.assertTrue(deploy.install(deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"]), self.library)["reused"])
        self.assertEqual({p.relative_to(self.workspace): p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}, old_files)
        self.assertEqual((self.library / "deployments" / old["id"] / "receipt.json").read_bytes(), old_receipt)
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT * FROM sessions WHERE id=?", (native["session_id"],)).fetchone(), old_row)
            self.assertEqual(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall(), old_schema)
            self.assertEqual(db.execute("SELECT count(*) FROM sessions s JOIN workspaces w ON s.id=w.session_id JOIN projects p ON p.id=w.project_id").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM workspaces").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM projects").fetchone()[0], 1)
        with patch.object(copilot_local, "root", return_value=self.desktop):
            visible = [s for group in copilot_local.groups() for s in group["sessions"] if s["movable"]]
        self.assertEqual(len(visible), 1)
        self.assertNotEqual(visible[0]["id"], native["session_id"])
        self.assertEqual(deploy.find_saved(self.library, "copilot_desktop", self.info["id"])["id"], result["id"])
        self.assertEqual([r["id"] for r in deploy.saved_records(self.library)], [result["id"]])

    def test_legacy_orphan_with_active_hidden_associated_or_remaining_files_is_not_ignored(self):
        _, native = self.legacy_orphan()
        sid = native["session_id"]
        for field, value in (("is_running", 1), ("archived_at", "synthetic-time"), ("provisional", 1), ("session_type", "project")):
            with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
                db.execute(f'UPDATE sessions SET "{field}"=? WHERE id=?', (value, sid))
            with self.assertRaises(deploy.SavedEntryError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
            with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
                db.execute(f'UPDATE sessions SET "{field}"=? WHERE id=?', (native["rows"]["sessions"].get(field), sid))
        for table in ("agents", "session_account_projects"):
            with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
                if table == "agents": db.execute("DROP TRIGGER agents_validate_insert")
                db.execute(f'INSERT INTO "{table}"(session_id) VALUES(?)', (sid,))
            with self.assertRaises(deploy.SavedEntryError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
            with closing(sqlite3.connect(self.desktop / "data.db")) as db, db: db.execute(f'DELETE FROM "{table}" WHERE session_id=?', (sid,))
        folder = self.desktop / "session-state" / sid
        folder.mkdir()
        for name in (None, "events.jsonl", "unrecognized.txt"):
            if name: (folder / name).write_bytes(b"synthetic later data: preserve")
            with self.assertRaises(deploy.SavedEntryError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])

    def test_legacy_orphan_is_not_ignored_when_relinked_or_receipt_identity_changed(self):
        _, native = self.legacy_orphan()
        sid = native["session_id"]
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("INSERT INTO projects(id,name,main_repo_path) VALUES('another-project','synthetic project','synthetic path')")
            db.execute("INSERT INTO workspaces(id,project_id,workspace_type,branch,name,session_id) VALUES('another-workspace','another-project','folder','','synthetic',?)", (sid,))
        with self.assertRaises(deploy.SavedEntryError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("DELETE FROM workspaces WHERE id='another-workspace'")
            db.execute("UPDATE projects SET main_repo_path=? WHERE id='another-project'", (str(self.workspace),))
        with self.assertRaises(deploy.SavedEntryError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE projects SET main_repo_path='synthetic path' WHERE id='another-project'")
        native["rows"]["workspaces"]["session_id"] = "mismatched-receipt"
        with self.assertRaises(ValueError): memory_desktop.present(native)

    def test_legacy_existing_project_receipt_does_not_block_repeat_or_touch_old_project(self):
        result, _ = self.install()
        old_project = self.base / "legacy-existing-work-project"
        legacy = legacy_project_fixture(self.library, old_project)
        before = {p.relative_to(self.base): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}
        with patch.object(deploy, "_install", side_effect=AssertionError("Repeat must reuse instead of importing")):
            repeated = deploy.install(deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"]), self.library)
        self.assertTrue(repeated["reused"])
        self.assertEqual(repeated["id"], result["id"])
        self.assertEqual({p.relative_to(self.base): p.read_bytes() for p in self.base.rglob("*") if p.is_file()}, before)
        self.assertTrue(legacy.is_file())

    def test_known_legacy_project_does_not_block_a_new_independent_move(self):
        old_project = self.base / "legacy-existing-work-project"
        legacy = legacy_project_fixture(self.library, old_project)
        before = legacy.read_bytes(), (old_project / "keep.txt").read_bytes()
        plan = deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        self.assertNotIn("reuse", plan)
        self.assertTrue(Path(plan["workspace"]).is_relative_to(self.library / "copilot-workspaces"))
        result = deploy.install(plan, self.library)
        self.assertEqual((legacy.read_bytes(), (old_project / "keep.txt").read_bytes()), before)
        self.assertEqual(len(deploy.saved_records(self.library)), 1)
        self.assertEqual(result["state"], "validated")

    def test_unreadable_other_receipt_cannot_prevent_safe_reuse_but_blocks_creating_unknown_duplicates(self):
        result, _ = self.install()
        broken = self.library / "deployments" / ("1" * 32) / "receipt.json"
        broken.parent.mkdir()
        broken.write_text("{synthetic interrupted metadata", encoding="utf-8")
        before = {p.relative_to(self.desktop): p.read_bytes() for p in self.desktop.rglob("*") if p.is_file()}
        repeated = deploy.install(deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"]), self.library)
        self.assertEqual(repeated["id"], result["id"])
        self.assertEqual({p.relative_to(self.desktop): p.read_bytes() for p in self.desktop.rglob("*") if p.is_file()}, before)
        other = store.ingest(self.library, "chatgpt", "unrelated-new-source", self.original)
        with self.assertRaises(ValueError): deploy.prepare_entry(self.library, "copilot_desktop", other["id"])
        self.assertEqual(broken.read_text(encoding="utf-8"), "{synthetic interrupted metadata")

    def test_current_receipt_with_removed_scope_cannot_masquerade_as_legacy_project(self):
        result, _ = self.install()
        path = self.library / "deployments" / result["id"] / "receipt.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("scope")
        path.write_text(store.encoded(data), encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(ValueError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_target_field_cannot_disable_duplicate_protection(self):
        result, _ = self.install()
        path = self.library / "deployments" / result["id"] / "receipt.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["target"] = "unrecognized-target"
        path.write_text(store.encoded(data), encoding="utf-8")
        with self.assertRaises(ValueError): deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"])

    def test_reuse_error_is_not_reported_as_incomplete_source_export(self):
        broken = self.library / "deployments" / ("1" * 32) / "receipt.json"
        broken.parent.mkdir(parents=True)
        broken.write_text("{synthetic incomplete registration", encoding="utf-8")
        with patch("main.memory_jobs.library", return_value=self.library), patch.object(mover, "export_document", return_value=self.original):
            api = Api()
            api._groups = {"chatgpt": [{"sessions": [{"id": "synthetic-history", "movable": True}]}]}
            self.assertTrue(api.prepare_memory("chatgpt", ["synthetic-history"], "copilot_desktop")["ok"])
            deadline = time.monotonic() + 10
            while not api.memory_status()["finished"] and time.monotonic() < deadline: time.sleep(.01)
            self.assertEqual(api.memory_status()["failed"], 0)
            plan = api.memory_plan()
            self.assertEqual(plan["error_stage"], "existing-entry")
            self.assertTrue(self.bundle.joinpath("archive/original.json").is_file())
            with closing(sqlite3.connect(self.desktop / "data.db")) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)

    def test_old_preview_mcp_type_upgrade_is_owned_minimal_and_still_undoable(self):
        result, _ = self.install()
        config_path = self.workspace / ".mcp.json"
        manifest_path = self.workspace / ".agent-memory/manifest.json"
        receipt_path = self.library / "deployments" / result["id"] / "receipt.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["mcpServers"][deploy.SERVER]["type"], "local")
        config["mcpServers"][deploy.SERVER]["type"] = "stdio"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["managed_files"][".mcp.json"] = store.digest(config_path.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        for item in receipt["files"]:
            if item["path"] in (".mcp.json", ".agent-memory/manifest.json"):
                item["sha256"] = store.digest((self.workspace / item["path"]).read_bytes())
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        before = {p.relative_to(self.desktop): p.read_bytes() for p in self.desktop.rglob("*") if p.is_file()}
        old_config = config_path.read_bytes()
        config_path.write_bytes(old_config + b" ")  # A later user edit, even valid JSON, must stay untouched.
        with self.assertRaises(ValueError): deploy.desktop_link(self.library, result["id"])
        self.assertEqual(config_path.read_bytes(), old_config + b" ")
        config_path.write_bytes(old_config)
        old_receipt, old_manifest = receipt_path.read_bytes(), manifest_path.read_bytes()
        original_write = deploy.write_atomic
        def fail_manifest(path, content):
            if path == manifest_path: raise OSError("synthetic write failure")
            original_write(path, content)
        with patch.object(deploy, "write_atomic", side_effect=fail_manifest):
            with self.assertRaises(OSError): deploy.desktop_link(self.library, result["id"])
        self.assertEqual((config_path.read_bytes(), manifest_path.read_bytes(), receipt_path.read_bytes()), (old_config, old_manifest, old_receipt))
        deploy.desktop_link(self.library, result["id"])
        reused = deploy.install(deploy.prepare_entry(self.library, "copilot_desktop", self.info["id"]), self.library)
        self.assertTrue(reused["reused"])
        self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"][deploy.SERVER]["type"], "local")
        self.assertEqual({p.relative_to(self.desktop): p.read_bytes() for p in self.desktop.rglob("*") if p.is_file()}, before)
        deploy.rollback(self.library, result["id"])
        self.assertFalse(config_path.exists())

    def test_saved_record_rejects_invalid_identity_foreign_workspace_and_rolled_back_receipt(self):
        result, _ = self.install()
        with self.assertRaises(ValueError): deploy.saved_record(self.library, "../outside")
        receipt_path = self.library / "deployments" / result["id"] / "receipt.json"
        saved = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_path.write_text(json.dumps({**saved, "workspace": str(self.base / "existing-project")}), encoding="utf-8")
        self.assertEqual(deploy.saved_records(self.library), [])
        receipt_path.write_text(json.dumps(saved), encoding="utf-8")
        deploy.rollback(self.library, result["id"])
        self.assertEqual(deploy.saved_records(self.library), [])
        self.assertTrue((self.bundle / "archive/original.json").is_file())

    def test_original_and_parts_roundtrip_without_source_mutation(self):
        self.assertEqual(json.loads((self.bundle / "archive/original.json").read_text(encoding="utf-8")), self.original)
        self.assertEqual(self.original, fixture())
        self.assertEqual(store.digest((self.bundle / "archive/original.json").read_bytes()), self.info["sha256"])
        with store.connect(self.bundle, True) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM messages").fetchone()[0], 5)
            self.assertEqual(db.execute("SELECT count(*) FROM message_parts").fetchone()[0], 6)
            parent = db.execute("SELECT id FROM messages WHERE ordinal=0").fetchone()[0]
            self.assertEqual(db.execute("SELECT parent_id FROM messages WHERE ordinal=1").fetchone()[0], parent)

    def test_legacy_handoff_type_repair_is_narrow_repeatable_and_preserves_history(self):
        result, _ = self.install()
        receipt_path = self.library / "deployments" / result["id"] / "receipt.json"
        saved = json.loads(receipt_path.read_text(encoding="utf-8"))
        sid = saved["desktop"]["session_id"]
        journal = self.desktop / "session-state" / sid / "events.jsonl"
        original = journal.read_bytes()
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE sessions SET session_type='workspace' WHERE id=?", (sid,))
            db.execute("INSERT INTO sessions(id,title,session_type,created_at,updated_at) VALUES('unrelated','不可改动','general_chat','before','before')")
        saved["desktop"]["rows"]["sessions"]["session_type"] = "workspace"
        receipt_path.write_text(json.dumps(saved), encoding="utf-8")
        for _ in range(2):
            self.assertEqual(deploy.desktop_link(self.library, result["id"]), "ghapp://sessions/" + sid)
        self.assertEqual(journal.read_bytes(), original)
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT session_type FROM sessions WHERE id=?", (sid,)).fetchone()[0], "project")
            self.assertEqual(db.execute("SELECT title,session_type FROM sessions WHERE id='unrelated'").fetchone(), ("不可改动", "general_chat"))
            self.assertEqual(db.execute("SELECT count(*) FROM workspaces").fetchone()[0], 1)
        self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8"))["desktop"]["rows"]["sessions"]["session_type"], "project")
        with patch.object(copilot_local, "root", return_value=self.desktop):
            for _ in range(2):  # Fresh connections, independent of an open URL or UI selection.
                groups = copilot_local.groups()
                self.assertTrue(any(g["title"] == result["project_name"] and any(s["id"] == sid for s in g["sessions"]) for g in groups))
        deploy.rollback(self.library, result["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT id FROM sessions").fetchall(), [("unrelated",)])

    def test_legacy_type_repair_refuses_unknown_trigger_and_never_repairs_a_running_session(self):
        result, _ = self.install()
        receipt_path = self.library / "deployments" / result["id"] / "receipt.json"
        saved = json.loads(receipt_path.read_text(encoding="utf-8"))
        sid = saved["desktop"]["session_id"]
        saved["desktop"]["rows"]["sessions"]["session_type"] = "workspace"
        receipt_path.write_text(json.dumps(saved), encoding="utf-8")
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE sessions SET session_type='workspace',is_running=1 WHERE id=?", (sid,))
        deploy.desktop_link(self.library, result["id"])
        self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8"))["desktop"]["rows"]["sessions"]["session_type"], "workspace")
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE sessions SET is_running=0 WHERE id=?", (sid,))
            db.execute("CREATE TRIGGER bad_legacy_repair AFTER UPDATE OF session_type ON sessions BEGIN UPDATE app_state SET value='wrong'; END")
        with self.assertRaises(sqlite3.DatabaseError): deploy.desktop_link(self.library, result["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT session_type FROM sessions WHERE id=?", (sid,)).fetchone()[0], "workspace")
            self.assertEqual(db.execute("SELECT value FROM app_state").fetchone()[0], "never-copy-this-synthetic-value")

    def test_sidebar_sync_waits_for_tasks_and_drafts_and_never_opens_a_transient_entry(self):
        result, _ = self.install()
        api = Api()
        api._memory_deployment = result
        with patch("main.memory_jobs.library", return_value=self.library), patch("main.time.sleep") as pause, \
             patch("main.copilot_refresh.refresh") as refresh, patch("main.open_external") as opened:
            for status in ("busy", "draft"):
                refresh.return_value = status
                self.assertTrue(api.open_memory_desktop()["pending"])
                opened.assert_not_called()
            for status in ("unavailable", "unsupported"):
                refresh.return_value = status
                self.assertIn("error", api.open_memory_desktop())
                opened.assert_not_called()
            refresh.return_value = "requested"
            self.assertTrue(api.open_memory_desktop()["refreshed"])
            refresh.assert_called_with(passive=True)
            pause.assert_called_once_with(1)
            self.assertEqual(opened.call_count, 1)

    def test_failed_reindex_or_partial_export_cannot_replace_saved_original(self):
        before = (self.bundle / "archive/original.json").read_bytes()
        shorter = {**self.original, "messages": self.original["messages"][:2]}
        with self.assertRaises(ValueError): store.ingest(self.library, "chatgpt", "synthetic-history", shorter)
        with patch.object(store, "create_schema", side_effect=ValueError("synthetic database error")):
            with self.assertRaises(ValueError): store.ingest(self.library, "chatgpt", "synthetic-history", self.original)
        self.assertEqual((self.bundle / "archive/original.json").read_bytes(), before)
        self.assertEqual(store.summary(self.bundle)["messages"], 5)

    def test_unexpanded_content_reference_is_not_reported_as_complete_history(self):
        document = {"messages": [{"role": "assistant", "content": '::chatgpt-content-reference{index="1"}'}]}
        with self.assertRaisesRegex(ValueError, "内容引用"):
            store.ingest(self.library, "chatgpt", "synthetic-placeholder", document)

    def test_project_paths_cannot_escape_workspace(self):
        with self.assertRaises(ValueError): deploy.path_in(self.workspace, "../outside")
        with self.assertRaises(ValueError): deploy.path_in(self.workspace, str(self.base / "outside"))

    def test_incremental_ids_and_confirmed_decisions_survive(self):
        fact = self.info["facts"][0]
        store.update_facts(self.bundle, [{"id": fact["id"], "status": "confirmed"}])
        with store.connect(self.bundle, True) as db:
            before = [r[0] for r in db.execute("SELECT id FROM messages ORDER BY ordinal")]
        new = copy.deepcopy(self.original)
        new["messages"].insert(0, {"id": "new-head", "role": "user", "content": "新加入的前置消息"})
        again = store.ingest(self.library, "chatgpt", "synthetic-history", new)
        with store.connect(self.bundle, True) as db:
            after = [r[0] for r in db.execute("SELECT id FROM messages ORDER BY ordinal")]
        self.assertEqual(after[1:], before)
        self.assertEqual(next(f for f in again["facts"] if f["id"] == fact["id"])["status"], "confirmed")

    def test_chinese_short_and_long_queries_with_source_locations(self):
        _, reader = self.install()
        for query in ("数据库", "智能", "完整对话迁移", "SQLite"):
            result = reader.search(query)
            self.assertTrue(result["hits"], query)
            for hit in result["hits"]:
                self.assertTrue((self.workspace / ".agent-memory" / hit["file"]).is_file())
                original = reader.read(hit["message_id"])
                self.assertIn(original["role"], {"user", "assistant"})
                self.assertGreaterEqual(hit["end_line"], hit["start_line"])

    def test_long_message_is_bounded_and_can_be_fully_reassembled(self):
        _, reader = self.install()
        hit = reader.search("末尾完整标记")["hits"][0]
        offset, parts = 0, []
        while True:
            result = reader.read(hit["message_id"], offset, 300)
            self.assertLessEqual(len(result["content"].encode("utf-8")), 300)
            parts.append(result["content"])
            if result["next_offset"] is None: break
            self.assertGreater(result["next_offset"], offset)
            offset = result["next_offset"]
        self.assertEqual("".join(parts), self.original["messages"][-1]["content"])

    def test_only_confirmed_facts_are_current_and_superseded_remains_history(self):
        self.assertTrue(self.info["facts"])
        store.update_facts(self.bundle, [{"id": self.info["facts"][0]["id"], "status": "confirmed"},
                                         {"id": self.info["facts"][-1]["id"], "status": "superseded"}])
        _, reader = self.install()
        facts = reader.current_state()["facts"]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["verified_by"], "user")
        self.assertTrue(reader.search("不满意")["hits"])

    def test_confirming_requirements_changes_only_workbench_index_and_not_deployment(self):
        api = Api()
        api._groups = {"chatgpt": [{"sessions": [{"id": "synthetic-history", "title": "合成开发讨论", "movable": True}]}]}
        with patch("main.memory_jobs.library", return_value=self.library), patch.object(mover, "export_document", return_value=self.original):
            self.assertTrue(api.prepare_memory("chatgpt", ["synthetic-history"], "copilot_desktop")["ok"])
            deadline = time.monotonic() + 5
            while not api.memory_status()["finished"] and time.monotonic() < deadline: time.sleep(.01)
            self.assertTrue(api.memory_plan()["ok"])
            result = api.deploy_memory()
            self.assertTrue(result.get("ok"), result)
            root = Path(result["workspace"])
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            desktop_before = (self.desktop / "data.db").read_bytes()
            reader = store.HistoryReader(Path(result["location"]))
            self.assertFalse(reader.current_state()["facts"])
            item = api.memory_status()["items"][0]
            fact = item["facts"][0]
            self.assertTrue(api.confirm_memory_facts({item["bundle"]: [{"id": fact["id"], "status": "confirmed"}]})["ok"])
            self.assertEqual(reader.current_state()["facts"][0]["id"], fact["id"])
            self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}, before)
            self.assertEqual((self.desktop / "data.db").read_bytes(), desktop_before)
            self.assertIn("error", api.confirm_memory_facts({"unknown": []}))
            self.assertTrue(api.rollback_memory()["ok"])
            self.assertEqual(store.summary(self.bundle)["facts"][0]["status"], "confirmed")

    def test_existing_project_tree_native_rows_and_schema_are_unchanged(self):
        project = self.base / "existing-work"
        (project / ".github").mkdir(parents=True)
        for name, content in {".mcp.json": b'{"mcpServers":{}}', ".gitignore": b"keep/\r\n", ".github/copilot-instructions.md": b"existing requirements", "work.txt": b"unfinished work"}.items():
            (project / name).write_bytes(content)
        journal = self.desktop / "session-state/old-session"
        journal.mkdir(parents=True)
        (journal / "events.jsonl").write_bytes(b"synthetic old chat\n")
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("INSERT INTO projects(id,name,main_repo_path,instructions,setup_script) VALUES('old-project','原项目',?,'keep instructions','keep setup')", (str(project),))
            db.execute("INSERT INTO sessions(id,title,session_type,created_at,updated_at,is_running) VALUES('old-session','正在做的事','workspace','before','before',1)")
            db.execute("INSERT INTO workspaces(id,project_id,workspace_type,branch,name,session_id,source_path) VALUES('old-workspace','old-project','folder','','原工作区','old-session',?)", (str(project),))
        def snapshot():
            with closing(sqlite3.connect(self.desktop / "data.db")) as db:
                schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
                rows = {t: db.execute(f"SELECT * FROM {t} WHERE id=?", (i,)).fetchall() for t, i in [("projects", "old-project"), ("sessions", "old-session"), ("workspaces", "old-workspace")]}
                state = db.execute("SELECT * FROM app_state").fetchall()
            return schema, rows, state, {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}, (journal / "events.jsonl").read_bytes()
        before = snapshot()
        saved, reader = self.install()
        self.assertEqual(snapshot(), before)
        self.assertFalse((project / ".agent-memory").exists())
        self.assertFalse((self.workspace / ".gitignore").exists())
        self.assertFalse((self.workspace / ".agent-memory/bundles").exists())
        self.assertEqual(reader.bundles[self.info["id"]], self.bundle)
        self.assertEqual(len(self.plan()["files"]), 5)
        deploy.rollback(self.library, saved["id"])
        self.assertEqual(snapshot(), before)

    def test_live_reader_rechecks_ownership_and_legacy_archive_remains_readable(self):
        _, reader = self.install()
        (self.workspace / memory_workspace.MARKER).write_text('{}', encoding="utf-8")
        with self.assertRaises(ValueError): reader.search("数据库")
        # Previous preview files can still be read; no existing project is upgraded in place.
        import shutil
        legacy = self.base / "legacy-memory"
        shutil.copytree(self.bundle, legacy / "bundles" / self.info["id"])
        (legacy / "manifest.json").write_text(store.encoded({"owner": deploy.OWNER, "format": store.FORMAT, "bundles": [self.info["id"]]}), encoding="utf-8")
        self.assertTrue(store.HistoryReader(legacy).search("数据库")["hits"])

    def test_read_only_protocol_and_input_scope(self):
        _, reader = self.install()
        request = lambda method, **params: server.respond(reader, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        self.assertEqual(len(request("tools/list")["result"]["tools"]), 3)
        self.assertEqual(request("execute", command="x")["error"]["code"], -32601)
        self.assertTrue(request("tools/call", name="search_history", arguments={"query": "数据库", "path": "../private"})["result"]["isError"])
        self.assertTrue(request("tools/call", name="read_history", arguments={"message_id": "../private"})["result"]["isError"])
        with self.assertRaises(ValueError): reader.read("0" * 24 + ":unknown")
        with store.connect(self.bundle, True) as db:
            with self.assertRaises(Exception): db.execute("DELETE FROM messages")

    def test_existing_user_projects_rejected_by_plan_install_and_bridge(self):
        project = self.base / "existing-project"
        project.mkdir()
        original = b'{"mcpServers":{"other":{"command":"synthetic-existing"}}}'
        (project / ".mcp.json").write_bytes(original)
        # Even a copied ownership marker outside our own library is insufficient.
        (project / memory_workspace.MARKER).write_bytes((self.workspace / memory_workspace.MARKER).read_bytes())
        with self.assertRaisesRegex(ValueError, "已有项目"):
            deploy.build_plan(project, "copilot_desktop", self.library, [self.info["id"]])
        plan = self.plan()
        plan["workspace"] = str(project)
        with self.assertRaises(ValueError): deploy.install(plan, self.library)
        self.assertIn("error", Api().prepare_memory("chatgpt", [], "copilot_desktop", str(project)))
        self.assertEqual((project / ".mcp.json").read_bytes(), original)
        self.assertFalse((project / ".agent-memory").exists())

    def test_workbench_marker_is_required_and_tampering_stops_install(self):
        plan = self.plan()
        (self.workspace / memory_workspace.MARKER).write_text('{}', encoding="utf-8")
        with self.assertRaises(ValueError): deploy.install(plan, self.library)
        self.assertFalse((self.workspace / ".agent-memory").exists())

    def test_preview_staleness_and_foreign_server_collisions_are_rejected(self):
        plan = self.plan()
        (self.workspace / ".mcp.json").write_text("new user change", encoding="utf-8")
        with self.assertRaises(ValueError): deploy.install(plan, self.library)
        self.assertFalse((self.workspace / ".agent-memory").exists())
        (self.workspace / ".mcp.json").write_text('{"mcpServers":{"ai-first-memory":{"command":"not-ours"}}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "同名"): self.plan()

    def test_failed_health_check_restores_all_original_files(self):
        before = b"# preserve bytes\r\n"
        (self.workspace / ".gitignore").write_bytes(before)
        plan = self.plan()
        with patch.object(deploy, "validate", side_effect=ValueError("synthetic health failure")):
            with self.assertRaises(ValueError): deploy.install(plan, self.library)
        self.assertEqual((self.workspace / ".gitignore").read_bytes(), before)
        self.assertFalse((self.workspace / ".mcp.json").exists())
        self.assertFalse((self.workspace / ".agent-memory/manifest.json").exists())
        self.assertFalse((self.workspace / ".agent-memory").exists())
        # An interrupted deployment must remain retryable, without an orphan directory collision.
        self.assertTrue(deploy.install(self.plan(), self.library)["id"])

    def test_user_changes_prevent_rollback_without_partial_writes(self):
        result, _ = self.install()
        path = self.workspace / ".github/copilot-instructions.md"
        path.write_text(path.read_text(encoding="utf-8") + "user later edit", encoding="utf-8")
        config = (self.workspace / ".mcp.json").read_bytes()
        with self.assertRaises(ValueError): deploy.rollback(self.library, result["id"])
        self.assertEqual((self.workspace / ".mcp.json").read_bytes(), config)
        self.assertIn("user later edit", path.read_text(encoding="utf-8"))

    def test_incremental_deploy_reuses_bundle_and_does_not_duplicate_rule(self):
        self.install()
        new = copy.deepcopy(self.original)
        new["messages"].append({"id": "extra", "role": "user", "content": "需要新增进度页面。"})
        store.ingest(self.library, "chatgpt", "synthetic-history", new)
        result, reader = self.install()
        self.assertEqual(len(reader.bundles), 1)
        self.assertTrue(reader.search("进度页面")["hits"])
        self.assertIn("mcpServers", json.loads((self.workspace / ".mcp.json").read_text(encoding="utf-8")))
        self.assertEqual((self.workspace / ".github/copilot-instructions.md").read_text(encoding="utf-8").count(deploy.BEGIN), 1)

    def test_running_reader_discovers_newly_deployed_history_without_restart(self):
        _, running_reader = self.install()
        other = {"title": "另一份合成对话", "messages": [{"id": "second-source-user", "role": "user", "content": "需要保留增量部署后的新资料。"}]}
        second = store.ingest(self.library, "fixture", "second-synthetic-source", other)
        plan = deploy.build_plan(self.workspace, "copilot_desktop", self.library, [second["id"]])
        deploy.install(plan, self.library)
        hits = running_reader.search("增量部署")["hits"]
        self.assertTrue(hits)
        self.assertIn("新资料", running_reader.read(hits[0]["message_id"])["content"])

    def test_bridge_prepares_deploys_searches_and_reuses_saved_original(self):
        api = Api()
        api._groups = {"chatgpt": [{"sessions": [{"id": "synthetic-history", "title": "合成开发讨论", "movable": True}]}]}
        with patch.object(mover, "data_dir", return_value=self.base / "app-data"), patch.object(mover, "export_document", return_value=self.original) as export:
            self.assertTrue(api.prepare_memory("chatgpt", ["synthetic-history"], "copilot_desktop")["ok"])
            deadline = time.monotonic() + 5
            while not api.memory_status()["finished"] and time.monotonic() < deadline: time.sleep(.01)
            self.assertEqual(api.memory_status()["failed"], 0)
            self.assertTrue(api.memory_plan()["ok"])
            result = api.deploy_memory()
            self.assertTrue(result.get("ok"), result)
            self.assertTrue(api.search_memory("数据库")["hits"])
            with patch.object(sources, "installed", return_value=True), patch.object(mover.imports, "preflight"), patch.object(mover, "DocumentJob") as job:
                self.assertTrue(api.start_full_from_memory("cursor_desktop", str(self.workspace))["ok"])
                self.assertEqual(json.loads(job.call_args.args[0][0]["original"].read_text(encoding="utf-8")), self.original)
            self.assertEqual(export.call_count, 1)

    def test_desktop_handoff_is_a_visible_project_session_without_fake_ai_or_old_history(self):
        result, _ = self.install()
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            session = db.execute("SELECT id,title,session_type,is_running,auto_approve,permission_mode FROM sessions").fetchone()
            project = db.execute("SELECT id,name,main_repo_path,auto_approve FROM projects").fetchone()
            workspace = db.execute("SELECT project_id,source_path,session_id,workspace_type,explicitly_opened FROM workspaces").fetchone()
            self.assertEqual(db.execute("SELECT value FROM app_state").fetchone()[0], "never-copy-this-synthetic-value")
        self.assertEqual(session[1:], ("合成开发讨论（智能搬家）", "project", 0, 0, "on"))
        self.assertEqual(project[1:], ("智能搬家资料 · 合成开发讨论", str(self.workspace), 0))
        self.assertEqual(workspace, (project[0], str(self.workspace), session[0], "folder", 1))
        self.assertEqual(deploy.desktop_link(self.library, result["id"]), "ghapp://sessions/" + session[0])
        with patch.object(copilot_local, "root", return_value=self.desktop):
            groups = copilot_local.groups()
            self.assertEqual(groups[0]["title"], "智能搬家资料 · 合成开发讨论")
            self.assertEqual(groups[0]["sessions"][0]["title"], session[1])
        events = [json.loads(line) for line in (self.desktop / "session-state" / session[0] / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["type"] for e in events].count("user.message"), 1)
        self.assertFalse(any(e["type"].startswith(("assistant.", "tool.")) for e in events))
        self.assertNotIn("完整长消息", json.dumps(events, ensure_ascii=False))
        deploy.rollback(self.library, result["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            for table in ("projects", "workspaces", "sessions"):
                self.assertEqual(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)

    def test_selected_history_names_are_used_without_renaming_existing_handoffs(self):
        previous, _ = self.install()
        other = {"title": "另一份合成对话", "messages": [{"role": "user", "content": "保留这次选择的原名称。"}]}
        second = store.ingest(self.library, "fixture", "second-name-source", other)
        plan = deploy.build_plan(self.workspace, "copilot_desktop", self.library, [second["id"], self.info["id"], second["id"]])
        expected = "另一份合成对话 等 2 条对话（智能搬家）"
        self.assertEqual(deploy.public_plan(plan)["desktop_title"], expected)
        saved = deploy.install(plan, self.library)
        self.assertEqual(saved["desktop_title"], expected)
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            rows = db.execute("SELECT s.title,w.name FROM sessions s JOIN workspaces w ON s.id=w.session_id ORDER BY s.created_at").fetchall()
        self.assertCountEqual(rows, [(previous["desktop_title"], previous["desktop_title"]), (expected, expected)])
        self.assertEqual(json.loads((self.bundle / "archive/original.json").read_text(encoding="utf-8")), self.original)

    def test_existing_desktop_project_is_reused_without_changing_its_settings(self):
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("INSERT INTO projects(id,name,main_repo_path,instructions,setup_script) VALUES('existing','已有项目',?,'synthetic rule','synthetic script')", (str(self.workspace),))
        result, _ = self.install()
        self.assertEqual(result["project_name"], "已有项目")
        deploy.rollback(self.library, result["id"])
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT id,name,instructions,setup_script FROM projects").fetchone(), ("existing", "已有项目", "synthetic rule", "synthetic script"))

    def test_desktop_failure_restores_project_and_unknown_triggers_cannot_write_settings(self):
        (self.workspace / ".gitignore").write_bytes(b"synthetic original\r\n")
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("CREATE TRIGGER synthetic_unexpected AFTER INSERT ON workspaces BEGIN UPDATE app_state SET value='wrong'; END")
        with self.assertRaises(sqlite3.DatabaseError): deploy.install(self.plan(), self.library)
        self.assertEqual((self.workspace / ".gitignore").read_bytes(), b"synthetic original\r\n")
        self.assertFalse((self.workspace / ".agent-memory").exists())
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM projects").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT value FROM app_state").fetchone()[0], "never-copy-this-synthetic-value")

    def test_new_desktop_messages_prevent_any_rollback_and_open_refreshes_with_guards(self):
        result, _ = self.install()
        api = Api()
        api._memory_deployment = result
        with patch.object(mover, "data_dir", return_value=self.library.parent), patch("main.copilot_refresh.refresh", return_value="not-running") as refresh, patch("main.open_external") as opened:
            # The API's real library lives in data_dir()/memory.
            with patch("main.memory_jobs.library", return_value=self.library):
                self.assertTrue(api.open_memory_desktop()["ok"])
                self.assertEqual(opened.call_args.args[0], deploy.desktop_link(self.library, result["id"]))
                refresh.assert_called_with(passive=True)
        saved = json.loads((self.library / "deployments" / result["id"] / "receipt.json").read_text(encoding="utf-8"))
        journal = self.desktop / "session-state" / saved["desktop"]["session_id"] / "events.jsonl"
        with journal.open("ab") as stream: stream.write(b'{"synthetic":"later user message"}\n')
        with self.assertRaisesRegex(ValueError, "消息|改动"): deploy.rollback(self.library, result["id"])
        self.assertTrue((self.workspace / ".agent-memory/manifest.json").is_file())

    def test_cli_and_vscode_are_not_smart_targets_and_unknown_desktop_schema_stops_preview(self):
        self.assertEqual(set(deploy.TARGETS), {"copilot_desktop"})
        for target in ("copilot_cli", "copilot_vscode", "copilot_vscode_local"):
            with self.assertRaises(ValueError): self.plan(target)
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("ALTER TABLE workspaces ADD COLUMN unknown_field TEXT NOT NULL")
        with self.assertRaisesRegex(ValueError, "必填"): self.plan()

    def test_later_project_settings_prevent_deleting_the_new_desktop_project(self):
        result, _ = self.install()
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("UPDATE projects SET instructions='synthetic later requirement'")
        with self.assertRaisesRegex(ValueError, "设置"): deploy.rollback(self.library, result["id"])
        self.assertTrue((self.workspace / ".agent-memory/manifest.json").exists())
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 1)

    def test_desktop_changes_between_preview_and_install_restore_project_files(self):
        plan = self.plan()
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("INSERT INTO projects(id,name,main_repo_path) VALUES('later','synthetic later project',?)", (str(self.workspace),))
        with self.assertRaisesRegex(ValueError, "预览后"): deploy.install(plan, self.library)
        self.assertFalse((self.workspace / ".agent-memory").exists())
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT id FROM projects").fetchone()[0], "later")
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)

    def test_changed_agent_trigger_is_not_trusted_and_cannot_insert_any_extra_row(self):
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("DROP TRIGGER sessions_insert_agent")
            db.execute("CREATE TRIGGER sessions_insert_agent AFTER INSERT ON sessions BEGIN INSERT INTO agents(session_id) VALUES(NEW.id); END")
        with self.assertRaises(sqlite3.DatabaseError): deploy.install(self.plan(), self.library)
        self.assertFalse((self.workspace / ".agent-memory").exists())
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM agents").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 0)

    def test_unknown_cleanup_cannot_modify_settings_or_partially_undo_files(self):
        result, _ = self.install()
        with closing(sqlite3.connect(self.desktop / "data.db")) as db, db:
            db.execute("CREATE TRIGGER synthetic_bad_cleanup AFTER DELETE ON sessions BEGIN UPDATE app_state SET value='wrong'; END")
        with self.assertRaises(sqlite3.DatabaseError): deploy.rollback(self.library, result["id"])
        self.assertTrue((self.workspace / ".agent-memory/manifest.json").exists())
        with closing(sqlite3.connect(self.desktop / "data.db")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sessions").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM workspaces").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT value FROM app_state").fetchone()[0], "never-copy-this-synthetic-value")


if __name__ == "__main__":
    unittest.main()
