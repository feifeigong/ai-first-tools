"""Real page and Python bridge over an isolated shared Codex store."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from core import chatgpt, sources, memory_desktop
from core.memory_audit import desktop_fixture
from main import Api
import test_codex_sources as fixtures


class CodexSourceUiTests(unittest.TestCase):
    def test_compressed_project_seven_records_select_and_prepare_through_real_bridge(self):
        import test_codex_compressed
        fixture = test_codex_compressed.CompressedProjectTests()
        browser_env = {name: os.environ[name] for name in ('SystemRoot','WINDIR','COMSPEC','PATH','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP') if name in os.environ}
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        ids = []
        for index in range(7):
            sid, path = fixture.add(f'合成项目对话{index}', 'cli' if index < 3 else 'vscode',
                                    'codex-tui' if index < 3 else 'codex_work_desktop')
            ids.append(sid)
            if index < 5:
                fixture.compress(path, write_content_size=False)
        fixture.catalog(ids)
        fixture.add('仅终端使用的对话')
        desktop = fixture.base / 'smart-desktop'; desktop_fixture(desktop)
        api = Api(); calls = []
        def bridge(name, args):
            calls.append((name,args))
            if name not in {'agents','sessions','prepare_memory','memory_status','memory_plan'}:
                raise ValueError('Unexpected project UI operation')
            return getattr(api,name)(*args)
        with patch.object(chatgpt,'web_data',return_value={'items':[],'projects':[]}), \
             patch.object(chatgpt,'info',return_value={}), \
             patch.object(sources,'installed',side_effect=lambda aid:aid in {'chatgpt','codex_cli','copilot_desktop'}), \
             patch.object(sources,'unsupported_found',return_value=[]), \
             patch.object(memory_desktop,'root',return_value=desktop), sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel='msedge',headless=True,env=browser_env)
            try:
                page = browser.new_page(viewport={'width':1360,'height':900})
                errors = []; page.on('pageerror',lambda error:errors.append(str(error)))
                page.expose_function('projectBridge',bridge)
                page.add_init_script("""
window.pywebview={api:new Proxy({}, {get:(_,name)=>(...args)=>window.projectBridge(name,args)})};
window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));
""")
                page.goto((Path(__file__).parent/'ui/index.html').as_uri())
                page.locator('[data-agent="chatgpt"]').click()
                page.locator('.row').nth(6).wait_for()
                self.assertEqual(page.locator('.row').count(),7)
                self.assertEqual(page.locator('.row.disabled').count(),0)
                self.assertIn('7 条对话，其中 7 条可以搬运',page.locator('#subtitle').inner_text())
                self.assertEqual(page.locator('.row-title').all_inner_texts(),[f'合成桌面名称 {i}' for i in reversed(range(7))])
                output = Path(__file__).parent.parent/'artifacts/project-history-ui'
                output.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(output/'seven-project-records.png'))
                page.locator('.row').filter(has_text='合成桌面名称 0').click()
                page.locator('#bar-go').click()
                page.locator('[data-target="copilot_desktop"]').click()
                page.locator('#memory-deploy').wait_for(timeout=15000)
                self.assertIn('合成桌面名称 0（智能搬家）',page.locator('#sheet-body').inner_text())
                self.assertEqual([args for name,args in calls if name=='prepare_memory'],[['chatgpt',[ids[0]],'copilot_desktop']])
                self.assertEqual(errors,[])
            finally:
                browser.close()

    def test_separate_source_counts_switch_search_refresh_and_destination(self):
        browser_env = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "COMSPEC", "PATH", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP") if name in os.environ}
        fixture = fixtures.CodexSourceTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        cli, _ = fixture.add("CLI 合成记录", "vscode", "Codex Desktop")
        # Reproduce a terminal thread wrongly labelled Desktop by its producer.
        (fixture.root / "history.jsonl").write_text(json.dumps({"session_id": cli, "ts": 1791600000, "text": "合成终端输入"}) + "\n", encoding="utf-8")
        fixture.add("桌面 Codex 合成记录", "vscode", "Codex Desktop")
        fixture.add("桌面 Work 合成记录", "vscode", "codex_work_desktop")
        desktop = fixture.base / "smart-desktop"
        desktop_fixture(desktop)
        api = Api()
        cloud = {"items": [{"id": "synthetic-cloud", "title": "云端合成聊天"}], "projects": []}
        calls = []
        def bridge(name, args):
            calls.append((name, args))
            if name not in {"agents", "sessions", "prepare_memory", "memory_status", "memory_plan"}:
                raise ValueError("Unexpected source UI test operation")
            return getattr(api, name)(*args)
        with patch.object(chatgpt, "web_data", return_value=cloud), patch.object(chatgpt, "info", return_value={}), \
             patch.object(sources, "installed", side_effect=lambda aid: aid in {"chatgpt", "codex_cli", "codex", "copilot_desktop"}), \
             patch.object(memory_desktop, "root", return_value=desktop), \
             patch.object(sources, "unsupported_found", return_value=[]), sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True, env=browser_env)
            try:
                page = browser.new_page(viewport={"width": 1180, "height": 780})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.expose_function("sourceBridge", bridge)
                page.add_init_script("""
                  window.pywebview={api:new Proxy({}, {get:(_,name)=>(...args)=>window.sourceBridge(name,args)})};
                  window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));
                """)
                page.goto((Path(__file__).parent / "ui/index.html").as_uri())
                page.locator('[data-agent="chatgpt"]').click()
                page.locator('[data-agent="chatgpt"] .agent-count').filter(has_text="3").wait_for()
                self.assertNotIn("CLI 合成记录", page.locator("#list").inner_text())
                self.assertIn("桌面 Codex 合成记录", page.locator("#list").inner_text())
                self.assertIn("桌面 Work 合成记录", page.locator("#list").inner_text())
                page.screenshot(path=str(Path(__file__).parent.parent / "artifacts/memory-preview-build/chatgpt-desktop-only.png"))
                page.locator(".row").first.click()
                page.locator('[data-agent="codex_cli"]').click()
                page.locator('[data-agent="codex_cli"] .agent-count').filter(has_text="1").wait_for()
                self.assertEqual(page.locator("#title").inner_text(), "Codex CLI")
                self.assertEqual(page.locator(".row.selected").count(), 0)
                self.assertEqual(page.locator(".row-title").all_inner_texts(), ["CLI 合成记录"])
                self.assertEqual(page.locator('[data-agent="codex_cli"] img').get_attribute("src"), "assets/agents/chatgpt.png")
                page.locator("#search").fill("不匹配的词")
                page.get_by_text("没有找到匹配的对话", exact=True).wait_for()
                page.locator("#search").fill("CLI")
                self.assertEqual(page.locator(".row").count(), 1)
                (fixture.root / "session_index.jsonl").write_text(json.dumps({"id": cli, "thread_name": "CLI 刷新后的名称"}) + "\n", encoding="utf-8")
                page.locator("#reload").click()
                page.get_by_text("CLI 刷新后的名称", exact=True).wait_for()
                output = Path(__file__).parent.parent / "artifacts/memory-preview-build"
                output.mkdir(exist_ok=True)
                page.screenshot(path=str(output / "codex-separated-sources.png"))
                page.locator(".row").filter(has_text="CLI 刷新后的名称").click()
                page.locator("#bar-go").click()
                self.assertEqual(page.locator('[data-target="codex_cli"]').count(), 0)
                page.locator('[data-migrate-mode="full"]').click()
                self.assertEqual(page.locator('[data-target="codex_cli"]').count(), 0)
                page.locator('[data-product="chatgpt"]').click()
                self.assertEqual(page.locator('[data-target="codex"]').count(), 1)
                page.locator("#sheet-back").click()
                page.locator('[data-migrate-mode="smart"]').click()
                page.locator('[data-target="copilot_desktop"]').click()
                page.locator("#memory-deploy").wait_for(timeout=15000)
                self.assertIn("CLI 刷新后的名称（智能搬家）", page.locator("#sheet-body").inner_text())
                prepared = [args for name, args in calls if name == "prepare_memory"]
                self.assertEqual(prepared, [["codex_cli", [cli], "copilot_desktop"]])
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
