from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from core import memory_deploy, memory_desktop, memory_store, mover, sources
from core.memory_audit import desktop_fixture, legacy_project_fixture
from main import Api
from test_memory import fixture


class MemoryUiTests(unittest.TestCase):
    def test_real_bridge_isolated_move_retrieve_review_undo_and_full_fallback(self):
        with tempfile.TemporaryDirectory(prefix="ai-first-memory-ui-") as scratch:
            base = Path(scratch).resolve()
            project = base / "synthetic-existing-project"
            project.mkdir()
            desktop = base / "desktop"
            desktop_fixture(desktop)
            with closing(sqlite3.connect(desktop / "data.db")) as db, db:
                db.execute("INSERT INTO projects(id,name,main_repo_path,instructions) VALUES('old-project','已有项目',?,'keep old requirements')", (str(project),))
                original_row = db.execute("SELECT * FROM projects").fetchall()
                original_schema = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall()
            (project / ".mcp.json").write_bytes(b'{"mcpServers":{"existing":{"command":"synthetic-existing"}}}')
            (project / ".gitignore").write_bytes(b"synthetic-original/\r\n")
            original_files = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
            api = Api()
            sessions = {"groups": [{"title": "合成项目", "kind": "folder", "path": str(project), "sessions": [
                {"id": "synthetic-history", "title": "合成开发讨论", "movable": True, "folder": str(project), "ts": 1}]}], "total": 1, "movable": 1}
            api._groups = {"chatgpt": sessions["groups"]}
            capabilities = {"ready": True, "unsupported": [],
                "agents": [{"id": "chatgpt", "name": "ChatGPT", "sub": "合成来源"}],
                "targets": [{"id": "cursor_desktop", "name": "Cursor", "sub": "桌面版", "canTarget": True}],
                "smartTargets": [{**target, "canTarget": True} for target in memory_deploy.TARGETS.values()]}
            calls, imported = [], []
            def full_import(path, document, target, details):
                imported.append(document)
                return "ok", "合成完整迁移验证通过"
            def bridge(name, arguments):
                calls.append(name)
                if name == "agents": return capabilities
                if name == "sessions": return sessions
                if name == "folders": return [{"name": "合成项目", "path": str(project)}]
                allowed = {"memory_records", "select_memory_record", "open_memory_desktop", "prepare_memory", "memory_status", "memory_plan", "deploy_memory", "confirm_memory_facts", "search_memory", "read_memory", "start_full_from_memory", "move_status", "rollback_memory"}
                if name not in allowed: raise ValueError("Unexpected test bridge operation")
                return getattr(api, name)(*arguments)
            with patch.object(mover, "data_dir", return_value=base / "app-data"), patch.object(mover, "export_document", return_value=fixture()) as export, \
                 patch.object(sources, "installed", return_value=True), patch.object(mover, "_import_document", side_effect=full_import), \
                 patch.object(memory_desktop, "root", return_value=desktop), patch("main.copilot_refresh.refresh", return_value="not-running") as refresh, patch("main.open_external") as opened:
                with sync_playwright() as runtime:
                    browser = runtime.chromium.launch(channel="msedge", headless=True)
                    try:
                        page = browser.new_page(viewport={"width": 1280, "height": 900})
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.expose_function("memoryBridge", bridge)
                        page.add_init_script("""
                          window.pywebview={api:new Proxy({}, {get:(_,name)=>(...args)=>window.memoryBridge(name,args)})};
                          window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));
                        """)
                        page.goto((Path(__file__).parent / "ui/index.html").as_uri())
                        page.locator(".row").first.click()
                        page.locator("#bar-go").click()
                        self.assertEqual(page.locator("[data-target]").count(), 1)
                        output = Path(__file__).parent.parent / "artifacts/memory-preview-build"
                        output.mkdir(exist_ok=True)
                        page.screenshot(path=str(output / "memory-isolated-target.png"))
                        page.locator('[data-target="copilot_desktop"]').click()
                        page.locator("#memory-deploy").wait_for(timeout=15000)
                        workspace = Path(api._memory_context["directory"])
                        self.assertFalse((workspace / ".agent-memory").exists())
                        self.assertNotIn("folders", calls)
                        self.assertNotIn("memory_folders", calls)
                        self.assertEqual(page.locator('#steps [aria-current="step"]').inner_text().replace("\n", ""), "2确认搬家")
                        self.assertFalse(page.locator("#memory-deploy").is_disabled())
                        self.assertEqual(page.locator('#sheet-body input, #sheet-body select, #sheet-body details').count(), 0)
                        for technical in (".mcp", ".gitignore", "合并", "候选", "get_current_state"):
                            self.assertNotIn(technical, page.locator("#sheet-body").inner_text())
                        self.assertIn("合成开发讨论（智能搬家）", page.locator("#sheet-body").inner_text())
                        page.screenshot(path=str(output / "memory-isolated-review.png"))
                        page.set_viewport_size({"width": 800, "height": 640})
                        page.locator("#memory-deploy").focus()
                        box = page.locator("#memory-deploy").bounding_box()
                        self.assertLessEqual(box["y"] + box["height"], 640)
                        self.assertGreaterEqual(box["x"], 0)
                        self.assertFalse(page.locator("#sheet-body").evaluate("el => el.scrollWidth > el.clientWidth"))
                        page.screenshot(path=str(output / "memory-isolated-review-small.png"))
                        page.set_viewport_size({"width": 1280, "height": 900})
                        refresh.side_effect = ["draft", "busy", "not-running"]
                        page.locator("#memory-deploy").click()
                        page.get_by_text("Copilot 里还有未发送的内容，先为你保留。处理完后会自动显示新对话。", exact=True).wait_for()
                        opened.assert_not_called()
                        page.screenshot(path=str(output / "memory-sidebar-waiting.png"))
                        page.get_by_text("在 Copilot 中输入下一步想做的事，就能接着聊。", exact=True).wait_for(timeout=20000)
                        refresh.side_effect = None
                        self.assertIn("合成开发讨论（智能搬家）", page.locator("#sheet-body").inner_text())
                        self.assertEqual(page.locator("#sheet-body details, #sheet-body input, #sheet-body select").count(), 0)
                        self.assertEqual(page.locator("#sheet-body button").all_text_contents(), ["完成"])
                        self.assertNotIn("使用帮助", page.locator("#sheet-body").inner_text())
                        self.assertNotIn("复制这句话", page.locator("#sheet-body").inner_text())
                        self.assertEqual(opened.call_count, 1)
                        self.assertTrue(opened.call_args.args[0].startswith("ghapp://sessions/"))
                        refresh.assert_called_with(passive=True)
                        page.screenshot(path=str(output / "memory-simple-result.png"))
                        page.set_viewport_size({"width": 800, "height": 640})
                        box = page.locator("#memory-finish").bounding_box()
                        self.assertLessEqual(box["y"] + box["height"], 640)
                        self.assertFalse(page.locator("#sheet-body").evaluate("el => el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth"))
                        page.screenshot(path=str(output / "memory-simple-result-small.png"))
                        self.assertEqual(opened.call_count, 1)  # Rerender/resize must not open again.
                        page.set_viewport_size({"width": 1280, "height": 900})
                        page.locator("#memory-finish").click()
                        # A new API instance has no in-memory preparation/deployment context.
                        api = Api()
                        api._groups = {"chatgpt": sessions["groups"]}
                        self.assertEqual(page.locator("#memory-records").count(), 0)
                        page.locator("[data-memory-tools]").first.wait_for()
                        page.set_viewport_size({"width": 800, "height": 640})
                        self.assertFalse(page.locator("#list").evaluate("el => el.scrollWidth > el.clientWidth"))
                        page.screenshot(path=str(output / "memory-source-entry-small.png"))
                        page.set_viewport_size({"width": 1280, "height": 900})
                        page.locator("[data-memory-tools]").first.click()
                        page.locator("#memory-browser > summary").click()
                        page.locator("#memory-query").fill("数据库")
                        page.locator("#memory-search").click()
                        page.locator(".memory-hit").first.click()
                        page.locator("#memory-read pre").wait_for()
                        self.assertIn("数据库", page.locator("#memory-read pre").inner_text())
                        page.screenshot(path=str(output / "memory-isolated-search.png"))
                        page.locator(".memory-facts > summary").click()
                        page.get_by_label("这条要求现在还适用吗").first.select_option("confirmed")
                        page.locator("#memory-facts-save").click()
                        page.locator("#memory-facts-note").filter(has_text="已保存").wait_for()
                        reader = memory_store.HistoryReader(Path(api._memory_deployment["location"]))
                        self.assertEqual(len(reader.current_state()["facts"]), 1)
                        self.assertEqual({p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}, original_files)
                        with closing(sqlite3.connect(desktop / "data.db")) as db:
                            self.assertEqual(db.execute("SELECT * FROM projects WHERE id='old-project'").fetchall(), original_row)
                            self.assertEqual(db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name").fetchall(), original_schema)
                        page.locator("#memory-rollback").click()
                        page.locator("#memory-rollback-cancel").click()
                        self.assertNotIn("rollback_memory", calls)
                        self.assertTrue((workspace / ".agent-memory").exists())
                        page.locator("#memory-rollback").click()
                        page.locator("#memory-rollback-confirm").click()
                        page.locator("#sheet").wait_for(state="hidden")
                        page.locator("[data-memory-tools]").wait_for(state="detached")
                        self.assertFalse((workspace / ".agent-memory").exists())
                        page.locator(".row").first.click()
                        page.locator("#bar-go").click()
                        page.locator('[data-target="copilot_desktop"]').click()
                        page.locator("#memory-deploy").wait_for(timeout=15000)
                        opened.side_effect = [OSError("synthetic failed launch"), None]
                        page.locator("#memory-deploy").click()
                        page.locator("#memory-open").wait_for(timeout=20000)
                        self.assertIn("暂时无法自动打开", page.locator("#sheet-body").inner_text())
                        self.assertEqual(len(api.memory_records()["items"]), 1)  # Launch failure never rolls back a saved move.
                        refresh.side_effect = ["draft", "not-running"]
                        page.locator("#memory-open").click()
                        page.get_by_text("Copilot 里还有未发送的内容，先为你保留。处理完后会自动显示新对话。", exact=True).wait_for()
                        page.locator("#memory-finish").click()  # Dismissing the result does not abandon the deferred open.
                        page.wait_for_timeout(3500)
                        self.assertEqual(opened.call_count, 3)
                        refresh.side_effect = None
                        self.assertEqual(calls.count("deploy_memory"), 2)  # Retrying opens only, no duplicate imports.
                        self.assertEqual(export.call_count, 2)
                        # Repeating the same move retains the same native entry and project.
                        previous = api.memory_records()["items"][0]["id"]
                        legacy = legacy_project_fixture(mover.data_dir() / "memory", base / "legacy-existing-project")
                        legacy_before = legacy.read_bytes()
                        page.locator(".row").first.click()
                        page.locator("#bar-go").click()
                        page.locator('[data-target="copilot_desktop"]').click()
                        page.locator("#memory-deploy").wait_for(timeout=15000)
                        self.assertIn("不会重复创建", page.locator("#sheet-body").inner_text())
                        opened.side_effect = None
                        page.locator("#memory-deploy").click()
                        page.locator("#memory-finish").wait_for(timeout=20000)
                        page.get_by_text("在 Copilot 中输入下一步想做的事，就能接着聊。", exact=True).wait_for()
                        self.assertEqual([r["id"] for r in api.memory_records()["items"]], [previous])
                        self.assertEqual(legacy.read_bytes(), legacy_before)
                        page.locator("#memory-finish").click()
                        # Desktop discarded the older preview's workspace registration:
                        # only its session row remains, with no links or files.
                        receipt_path = mover.data_dir() / "memory/deployments" / previous / "receipt.json"
                        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                        native = receipt["desktop"]
                        native["rows"]["sessions"]["session_type"] = "workspace"
                        receipt_path.write_text(memory_store.encoded(receipt), encoding="utf-8")
                        receipt_before = receipt_path.read_bytes()
                        with closing(sqlite3.connect(desktop / "data.db")) as db, db:
                            db.execute("UPDATE sessions SET session_type='workspace' WHERE id=?", (native["session_id"],))
                            db.execute("DELETE FROM workspaces WHERE id=?", (native["workspace_id"],))
                            db.execute("DELETE FROM projects WHERE id=?", (native["rows"]["projects"]["id"],))
                        shutil.rmtree(desktop / "session-state" / native["session_id"])
                        page.reload()
                        page.locator(".row").first.wait_for()
                        self.assertEqual(page.locator("[data-memory-open]").count(), 0)
                        page.locator(".row").first.click()
                        page.locator("#bar-go").click()
                        page.locator('[data-target="copilot_desktop"]').click()
                        page.locator("#memory-deploy:not([disabled])").wait_for(timeout=15000)
                        self.assertNotIn("需要核对", page.locator("#sheet-body").inner_text())
                        page.locator("#memory-deploy").click()
                        page.locator("#memory-finish").wait_for(timeout=20000)
                        current = api._memory_deployment["id"]
                        self.assertNotEqual(current, previous)
                        self.assertEqual(receipt_path.read_bytes(), receipt_before)
                        self.assertEqual([r["id"] for r in api.memory_records()["items"]], [current])
                        page.locator("#memory-finish").click()
                        page.locator(f'[data-memory-open="{current}"]').wait_for()
                        self.assertEqual(page.locator("[data-memory-open]").count(), 1)
                        page.locator("[data-memory-tools]").first.click()
                        page.locator("#memory-full").click()
                        page.locator('[data-target="cursor_desktop"]').click()
                        page.locator("[data-path]").first.click()
                        page.locator("#next").click()
                        page.locator("#go").click()
                        page.locator("#finish").wait_for()
                        self.assertEqual(export.call_count, 4)
                        self.assertEqual(imported[0]["messages"], fixture()["messages"])
                        self.assertIn("start_full_from_memory", calls)
                        self.assertEqual(errors, [])
                    finally:
                        browser.close()


if __name__ == "__main__":
    unittest.main()
