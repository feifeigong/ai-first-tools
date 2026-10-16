from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from core import imports, mover, sources
from main import Api


class ImportUiTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(sources, "installed", return_value=True))
        self.enterContext(patch.object(sources, "unsupported_found", return_value=[]))
        self.enterContext(patch.object(mover, "txcript_path", return_value=Path("fixture/txcript.exe")))

    def test_copilot_source_search_selection_refresh_and_read_only_destination(self):
        capabilities = Api().agents()
        capabilities["agents"] = [item for item in capabilities["agents"] if item["id"] == "copilot_desktop"]
        source = {"groups": [{"title": "合成项目", "kind": "folder", "path": "/synthetic/project", "sessions": [
            {"id": "desktop-session", "title": "Copilot 桌面长对话", "movable": True, "ts": 2, "when": "刚刚", "note": "Copilot Desktop"},
            {"id": "shared-session", "title": "Copilot 共享示例", "movable": True, "ts": 1, "when": "昨天", "note": "Copilot 共享会话（Desktop / CLI 共用，来源未确认）"},
            {"id": "broken-session", "title": "不完整记录", "movable": False, "ts": 0, "note": "记录不完整，请刷新"}]}], "total": 3, "movable": 2}
        bootstrap = """
        window._refreshes = 0;
        window.pywebview = {api: {
          agents: async () => (CAPABILITIES),
          sessions: async (id, refresh) => {if(refresh) window._refreshes++; return SOURCE;},
          folders: async () => []
        }};
        window.addEventListener('DOMContentLoaded', () => window.dispatchEvent(new Event('pywebviewready')));
        """.replace("CAPABILITIES", json.dumps(capabilities)).replace("SOURCE", json.dumps(source))
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page(viewport={"width": 1180, "height": 780})
                page.add_init_script(bootstrap)
                page.goto((Path(__file__).parent / "ui/index.html").as_uri())
                page.locator('[data-id="desktop-session"]').wait_for()
                logo = page.locator('[data-agent="copilot_desktop"] img')
                self.assertEqual(logo.get_attribute("src"), "assets/agents/copilot.png")
                page.wait_for_function("document.querySelector('[data-agent=\"copilot_desktop\"] img').naturalWidth > 0")
                self.assertIn("来源未确认", page.locator('[data-id="shared-session"]').inner_text())
                page.locator("#search").fill("长对话")
                self.assertEqual(page.locator(".row").count(), 1)
                page.locator("#search").fill("")
                page.locator('[data-id="broken-session"]').click()
                self.assertTrue(page.locator("#bar").is_hidden())
                page.locator("#reload").click()
                page.wait_for_function("window._refreshes === 1")
                page.locator(".group-check").click()
                self.assertEqual(page.locator("#bar-count").inner_text(), "2")
                page.locator("#bar-go").click()
                destination = page.locator('[data-target="copilot_desktop"]')
                self.assertFalse(destination.is_enabled())
                self.assertIn("暂不支持搬入", destination.inner_text())
            finally:
                browser.close()

    def test_real_capabilities_render_and_navigate(self):
        capabilities = Api().agents()
        source = {"groups": [{"title": "测试项目", "kind": "folder", "path": "D:\\vibcoding",
                              "sessions": [{"id": "synthetic-session", "title": "测试对话", "movable": True, "folder": "D:\\vibcoding", "when": "刚刚", "ts": 1}]}], "total": 1, "movable": 1}
        bootstrap = """
        window._moves = [];
        window.pywebview = {api: {
          agents: async () => (CAPABILITIES),
          sessions: async () => (SESSIONS),
          folders: async () => [{name: 'vibcoding', path: 'D:\\\\vibcoding'}],
          start_move: async (...args) => {window._moves.push(args); return {ok:true,total:1};},
          move_status: async () => ({finished:true,total:1,done:1,ok:1,failed:0,skipped:0,
            items:[{id:'synthetic-session',title:'测试对话',state:'ok',message:'已搬好',location:'D:\\\\fixture\\\\trajectory.jsonl',resumeCommand:'codex resume synthetic-import'}]}),
          open_import_folder: async () => ({ok:true})
        }};
        window.addEventListener('DOMContentLoaded', () => window.dispatchEvent(new Event('pywebviewready')));
        """.replace("CAPABILITIES", json.dumps(capabilities)).replace("SESSIONS", json.dumps(source))
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page(viewport={"width": 1180, "height": 780}, device_scale_factor=1)
                page.add_init_script(bootstrap)
                failures = []
                page.on("pageerror", lambda error: failures.append(str(error)))
                page.goto((Path(__file__).parent / "ui" / "index.html").as_uri())
                page.locator(".row").first.click()
                page.locator("#bar-go").click()
                for product in ("chatgpt", "claude"):
                    button = page.locator(f'[data-product="{product}"]')
                    self.assertEqual(button.count(), 1)
                    self.assertTrue(button.is_enabled())
                for target in capabilities["targets"]:
                    if target.get("product"):
                        page.locator(f'[data-product="{target["product"]}"]').click()
                    button = page.locator(f'[data-target="{target["id"]}"]')
                    self.assertEqual(button.is_enabled(), target["canTarget"], target["id"])
                    if not target["canTarget"]:
                        self.assertIn(target["readOnlyReason"], button.inner_text())
                    if target.get("product"):
                        page.locator("#sheet-back").click()
                page.screenshot(path=str(Path(__file__).parent / "_import_targets.png"))
                for target in capabilities["targets"]:
                    if not target["canTarget"]:
                        continue
                    if target.get("product"):
                        page.locator(f'[data-product="{target["product"]}"]').click()
                        page.screenshot(path=str(Path(__file__).parent / f'_import_{target["product"]}_modes.png'))
                    page.locator(f'[data-target="{target["id"]}"]').click()
                    self.assertIn(target["folderHint"], page.locator("#sheet-body").inner_text())
                    if target.get("notice"):
                        self.assertIn(target["notice"], page.locator(".import-notice").inner_text())
                    page.locator("[data-path]").first.click()
                    page.locator("#next").click()
                    self.assertIn(target["name"], page.locator("#sheet-body").inner_text())
                    if target.get("notice"):
                        self.assertIn(target["notice"], page.locator(".import-notice").inner_text())
                    page.locator("#sheet-back").click()
                    self.assertEqual(page.locator(".folder.on").count(), 1)
                    page.locator("#sheet-back").click()
                    if target.get("product"):
                        self.assertEqual(page.locator(f'[data-target="{target["id"]}"].on').count(), 1)
                        page.locator("#sheet-back").click()
                page.locator('[data-target="cursor_desktop"]').click()
                page.locator("#next").click()
                page.locator("#go").click()
                page.locator("#finish").wait_for()
                self.assertIn("Cursor", page.locator("#sheet-body").inner_text())
                self.assertIn("目标软件是否显示、能否继续对话", page.locator("[data-verification-scope]").inner_text())
                self.assertEqual(page.locator('[aria-label="续聊命令"]').input_value(), "codex resume synthetic-import")
                self.assertEqual(page.locator("[data-import-folder]").count(), 1)
                self.assertEqual(page.evaluate("window._moves[0][2]"), "cursor_desktop")
                self.assertFalse(next(item for item in capabilities["targets"] if item["id"] == "doubao_work")["canTarget"])
                self.assertEqual(page.locator('[data-agent="chatgpt"]').count(), 1)
                self.assertEqual(page.locator('[data-agent="codex"]').count(), 0)
                page.locator("#finish").click()
                for destination in ("chatgpt_work", "codex", "cowork"):
                    page.locator(".row").first.click()
                    page.locator("#bar-go").click()
                    product = next(item["product"] for item in capabilities["targets"] if item["id"] == destination)
                    page.locator(f'[data-product="{product}"]').click()
                    page.locator(f'[data-target="{destination}"]').click()
                    page.locator("[data-path]").first.click()
                    page.locator("#next").click()
                    page.locator("#go").click()
                    page.locator("#finish").wait_for()
                    self.assertEqual(page.evaluate("window._moves.at(-1)[2]"), destination)
                    page.locator("#finish").click()
                self.assertEqual(failures, [])
                self.assertTrue(set(imports.TARGETS) <= {item["id"] for item in capabilities["targets"]})
            finally:
                browser.close()

    def test_open_request_does_not_claim_native_display_or_resume_verified(self):
        capabilities = Api().agents()
        bootstrap = """
        window._openFails = false;
        window.pywebview = {api: {
          agents: async () => (CAPABILITIES),
          sessions: async () => ({groups:[{title:'项目',kind:'folder',path:'D:\\\\vibcoding',sessions:[{id:'fixture',title:'测试记录',movable:true,folder:'D:\\\\vibcoding',ts:1}]}],total:1,movable:1}),
          folders: async () => [{name:'vibcoding',path:'D:\\\\vibcoding'}],
          start_move: async () => ({ok:true,total:1}),
          move_status: async () => ({finished:true,total:1,done:1,ok:1,failed:0,skipped:0,items:[{id:'fixture',title:'测试记录',state:'ok',message:'已写入',openUrl:'codex://threads/fixture'}]}),
          open_in_app: async () => window._openFails ? {error:'测试打开失败'} : {ok:true}
        }};
        window.addEventListener('DOMContentLoaded', () => window.dispatchEvent(new Event('pywebviewready')));
        """.replace("CAPABILITIES", json.dumps(capabilities))
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page(viewport={"width": 1180, "height": 900})
                page.add_init_script(bootstrap)
                page.goto((Path(__file__).parent / "ui" / "index.html").as_uri())
                page.locator(".row").first.click()
                page.locator("#bar-go").click()
                page.locator('[data-product="chatgpt"]').click()
                page.locator('[data-target="chatgpt_work"]').click()
                page.locator("[data-path]").first.click()
                page.locator("#next").click()
                page.locator("#go").click()
                page.get_by_text("已请求打开这条记录；请在 ChatGPT 中确认", exact=True).wait_for()
                self.assertNotIn("已自动在 ChatGPT 里打开", page.locator("#sheet-body").inner_text())
                page.evaluate("window._openFails = true")
                page.locator("[data-open-app]").click()
                page.get_by_text("记录已复制，打开软件失败；可以重试", exact=True).wait_for()
                self.assertTrue(page.locator("#finish").is_enabled())
                page.evaluate("window._openFails = false")
                page.locator("[data-open-app]").click()
                page.get_by_text("已请求打开这条记录；请在 ChatGPT 中确认", exact=True).wait_for()
            finally:
                browser.close()

    def test_failed_copy_and_archived_tool_notices_are_explicit_and_readable(self):
        capabilities = Api().agents()
        for ok, text in ((0, "历史工具调用缺少配对结果，已停止导入。" * 20),
                         (1, "已搬好；2 条未能完整配对的工具日志已作为历史说明保留，未补写执行结果。")):
            with self.subTest(ok=ok), sync_playwright() as runtime:
                browser = runtime.chromium.launch(channel="msedge", headless=True)
                try:
                    page = browser.new_page(viewport={"width": 960, "height": 740})
                    page.set_default_timeout(5000)
                    status = {"finished": True, "total": 1, "done": 1, "ok": ok, "failed": 1 - ok, "skipped": 0,
                              "items": [{"id": "fixture", "title": "合成记录", "state": "ok" if ok else "failed", "message": text}]}
                    page.add_init_script("""
window.pywebview={api:{agents:async()=>(CAPABILITIES),
sessions:async()=>({groups:[{title:'项目',kind:'folder',path:'/synthetic',sessions:[{id:'fixture',title:'合成记录',movable:true,folder:'/synthetic',ts:1}]}],total:1,movable:1}),
folders:async()=>[{name:'synthetic',path:'/synthetic'}],start_move:async()=>({ok:true,total:1}),move_status:async()=>(STATUS)}};
window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));
""".replace("CAPABILITIES", json.dumps(capabilities)).replace("STATUS", json.dumps(status)))
                    page.goto((Path(__file__).parent / "ui/index.html").as_uri())
                    page.locator(".row").first.click()
                    page.locator("#bar-go").click()
                    page.locator('[data-product="chatgpt"]').click()
                    page.locator('[data-target="chatgpt_work"]').click()
                    page.locator("[data-path]").first.click()
                    page.locator("#next").click()
                    page.locator("#go").click()
                    page.get_by_role("heading", name="记录已复制" if ok else "这次没有复制成功", exact=True).wait_for()
                    self.assertEqual(page.locator(".result .m").inner_text(), text)
                    self.assertTrue(page.locator(".result").evaluate("el=>el.scrollWidth<=el.clientWidth+1"))
                    self.assertEqual(page.locator("[data-verification-scope]").count(), ok)
                    self.assertTrue(page.locator("#finish").is_visible())
                finally:
                    browser.close()

    def test_slow_native_bridge_never_shows_fake_agents_or_conversations(self):
        capabilities = Api().agents()
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page()
                page.goto((Path(__file__).parent / "ui" / "index.html").as_uri())
                page.get_by_text("正在连接本机搬运组件…").wait_for()
                self.assertEqual(page.locator(".agent").count(), 0)
                self.assertEqual(page.locator(".row").count(), 0)
                page.evaluate("""capabilities => {
                  window.pywebview = {api:{agents:async()=>capabilities,sessions:async()=>({groups:[],total:0,movable:0})}};
                  window.dispatchEvent(new Event('pywebviewready'));
                }""", capabilities)
                page.locator(".agent").first.wait_for()
                self.assertEqual(page.locator("[data-agent]").count(), len(capabilities["agents"]))
                self.assertEqual(page.locator(".row").count(), 0)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
