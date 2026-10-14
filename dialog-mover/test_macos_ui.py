from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from prepare_macos import prepare

INFO = {"ready": True, "agents": [{"id": "cursor_desktop", "name": "Cursor", "sub": "桌面版"}], "targets": [], "unsupported": []}
SESSIONS = {"groups": [{"title": "Mac 界面验证", "kind": "folder", "path": "/Users/example/项目", "sessions": [
    {"id": "mac-ui-synthetic", "title": "仅用于排版检查的合成记录", "movable": True, "ts": 1, "when": "刚刚"}]}], "total": 1, "movable": 1}
BOOT = "window.pywebview={api:{agents:async()=>(INFO),sessions:async()=>(SESSIONS),workspace_info:async()=>({version:'0.4.0',automaticChecks:true}),check_update:async()=>({available:false})}};window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));".replace("INFO", json.dumps(INFO)).replace("SESSIONS", json.dumps(SESSIONS))


class MacUiTests(unittest.TestCase):
    def test_cocoa_start_waits_for_the_native_bridge_ready_signal(self):
        bootstrap = BOOT + """
window.pywebview.platform='cocoa';window.__AI_FIRST_BRIDGE_READY__=false;
window.agentCalls=0;window.infoCalls=0;window.checkCalls=0;
window.pywebview.api.agents=async()=>{window.agentCalls++;return AGENTS};
window.pywebview.api.workspace_info=async()=>{window.infoCalls++;return {version:'0.4.0',automaticChecks:true}};
window.pywebview.api.check_update=async()=>{window.checkCalls++;return {available:false}};
""".replace("AGENTS", json.dumps(INFO))
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.clock.install()
                page.add_init_script(bootstrap)
                page.goto((resources / "ui/index.html").as_uri())
                page.clock.fast_forward(6000)
                self.assertEqual(page.evaluate("[window.agentCalls,window.infoCalls,window.checkCalls]"), [0, 0, 0])
                page.evaluate("window.__AI_FIRST_BRIDGE_READY__=true;window.dispatchEvent(new CustomEvent('ai-first-ready'))")
                page.get_by_text("Mac · v0.4.0", exact=True).wait_for()
                page.get_by_text("仅用于排版检查的合成记录", exact=True).wait_for()
                page.clock.fast_forward(2100)
                page.wait_for_function("window.checkCalls===1")
                self.assertEqual(page.evaluate("[window.agentCalls,window.infoCalls]"), [1, 1])
            finally:
                browser.close()

    def test_failed_automatic_check_is_visible_and_retries_without_a_click(self):
        for failure_kind in ("response", "exception"):
            with self.subTest(failure_kind=failure_kind), tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
                resources = prepare(Path(temporary))
                browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
                try:
                    page = browser.new_page()
                    page.clock.install()
                    bootstrap = BOOT + """
window.checkCalls=0;
window.pywebview.api.check_update=async()=>{
  window.checkCalls++;
  if(window.checkCalls===1)FAILURE;
  return {available:true,version:'0.4.1',canInstall:true};
};
""".replace("FAILURE", "throw new Error('synthetic bridge failure')" if failure_kind == "exception" else "return {error:'连接超时',errorCode:'timeout',canOpenDownloads:true}")
                    page.add_init_script(bootstrap)
                    page.goto((resources / "ui/index.html").as_uri())
                    page.get_by_text("Mac · v0.4.0", exact=True).wait_for()
                    page.clock.fast_forward(2100)
                    page.wait_for_function("window.checkCalls===1")
                    self.assertTrue(page.locator("#workspace-notice").is_visible())
                    self.assertIn("将自动重试", page.locator("#workspace-message").text_content())
                    self.assertTrue(page.get_by_role("button", name="检查更新", exact=True).is_enabled())
                    page.clock.fast_forward(61000)
                    page.wait_for_function("window.checkCalls===2", timeout=2000)
                    self.assertTrue(page.get_by_role("button", name="下载并更新", exact=True).is_visible())
                finally:
                    browser.close()

    def test_rate_limit_uses_a_long_retry_delay(self):
        bootstrap = BOOT + """
window.checkCalls=0;
window.pywebview.api.check_update=async()=>{window.checkCalls++;return {error:'检查次数达到上限',errorCode:'rate_limit',canOpenDownloads:true}};
"""
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.clock.install()
                page.add_init_script(bootstrap)
                page.goto((resources / "ui/index.html").as_uri())
                page.get_by_text("Mac · v0.4.0", exact=True).wait_for()
                page.clock.fast_forward(2100)
                page.wait_for_function("window.checkCalls===1")
                page.clock.fast_forward(61000)
                self.assertEqual(page.evaluate("window.checkCalls"), 1)
                page.clock.fast_forward(3600000)
                page.wait_for_function("window.checkCalls===2", timeout=2000)
            finally:
                browser.close()

    def test_successful_manual_check_replaces_the_pending_retry(self):
        bootstrap = BOOT + """
window.checkCalls=0;
window.pywebview.api.check_update=async()=>{window.checkCalls++;return window.checkCalls===1?{error:'连接超时',errorCode:'timeout'}:{available:true,version:'0.4.1',canInstall:true}};
"""
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.clock.install()
                page.add_init_script(bootstrap)
                page.goto((resources / "ui/index.html").as_uri())
                page.get_by_text("Mac · v0.4.0", exact=True).wait_for()
                page.clock.fast_forward(2100)
                page.wait_for_function("window.checkCalls===1")
                page.get_by_role("button", name="检查更新", exact=True).click()
                page.get_by_role("button", name="下载并更新", exact=True).wait_for()
                page.clock.fast_forward(61000)
                self.assertEqual(page.evaluate("window.checkCalls"), 2)
                page.clock.fast_forward(6 * 60 * 60 * 1000)
                page.wait_for_function("window.checkCalls===3", timeout=2000)
            finally:
                browser.close()

    def test_retry_backoff_does_not_repeat_a_dismissed_failure_notice(self):
        bootstrap = BOOT + """
window.checkCalls=0;
window.pywebview.api.check_update=async()=>{window.checkCalls++;return {error:'连接超时',errorCode:'timeout'}};
"""
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.clock.install()
                page.add_init_script(bootstrap)
                page.goto((resources / "ui/index.html").as_uri())
                page.get_by_text("Mac · v0.4.0", exact=True).wait_for()
                page.clock.fast_forward(2100)
                page.wait_for_function("window.checkCalls===1")
                page.get_by_role("button", name="关闭提示", exact=True).click()
                page.clock.fast_forward(61000)
                page.wait_for_function("window.checkCalls===2")
                self.assertFalse(page.locator("#workspace-notice").is_visible())
                page.clock.fast_forward(61000)
                self.assertEqual(page.evaluate("window.checkCalls"), 2)
                page.clock.fast_forward(240000)
                page.wait_for_function("window.checkCalls===3")
                page.clock.fast_forward(901000)
                page.wait_for_function("window.checkCalls===4")
            finally:
                browser.close()

    def test_automatic_check_is_deferred_while_downloading_an_update(self):
        bootstrap = BOOT.replace("({available:false})", "({available:true,version:'0.4.1',canInstall:true})") + """
window.checkCalls=0;
window.pywebview.api.check_update=async()=>{window.checkCalls++;return {available:true,version:'0.4.1',canInstall:true}};
window.pywebview.api.start_update=async()=>({ok:true});
window.pywebview.api.update_status=async()=>({phase:'downloading',progress:20});
"""
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.clock.install()
                page.add_init_script(bootstrap)
                page.goto((resources / "ui/index.html").as_uri())
                page.get_by_text("Mac · v0.4.0", exact=True).wait_for()
                page.clock.fast_forward(2100)
                page.get_by_role("button", name="下载并更新", exact=True).click()
                page.get_by_text("正在下载 20% · 下载时可以继续使用", exact=True).wait_for()
                page.clock.fast_forward(6 * 60 * 60 * 1000)
                page.clock.fast_forward(61000)
                self.assertEqual(page.evaluate("window.checkCalls"), 1)
            finally:
                browser.close()

    def test_update_button_appears_automatically_and_one_click_waits_for_migration(self):
        bootstrap = BOOT.replace("({available:false})", "({available:true,version:'0.4.1',canInstall:true})") + """
window.updatePhase='downloading';window.migrationBusy=true;
window.pywebview.api.start_update=async()=>{window.downloadCount=(window.downloadCount||0)+1;return {ok:true}};
window.pywebview.api.update_status=async()=>({phase:window.updatePhase,progress:45});
window.pywebview.api.apply_update=async()=>{if(window.migrationBusy)return {waiting:true};window.updateApplied=true;return {ok:true}};
window.pywebview.api.open_update=async()=>{window.browserOpened=true;return {ok:true}};
"""
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.add_init_script(bootstrap)
                page.goto((resources / "ui/index.html").as_uri())
                page.get_by_role("button", name="下载并更新").click()
                page.get_by_text("正在下载 45% · 下载时可以继续使用", exact=True).wait_for()
                self.assertEqual(page.evaluate("window.downloadCount"), 1)
                self.assertIsNone(page.evaluate("window.browserOpened"))
                page.evaluate("window.updatePhase='ready'")
                page.get_by_text("下载完成，等当前搬运结束后自动更新。", exact=True).wait_for()
                self.assertIsNone(page.evaluate("window.updateApplied"))
                page.evaluate("window.migrationBusy=false")
                page.wait_for_function("window.updateApplied===true")
                page.get_by_text("正在更新并重新打开，请稍等…", exact=True).wait_for()
            finally:
                browser.close()

    def test_download_can_be_cancelled_without_hiding_retry_button(self):
        bootstrap = BOOT.replace("({available:false})", "({available:true,version:'0.4.1',canInstall:true})") + """
window.updatePhase='downloading';
window.pywebview.api.start_update=async()=>({ok:true});
window.pywebview.api.update_status=async()=>({phase:window.updatePhase,progress:20,error:'已取消下载，当前版本可以继续使用。'});
window.pywebview.api.cancel_update=async()=>{window.updatePhase='error';return {ok:true}};
"""
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.add_init_script(bootstrap)
                page.goto((resources / "ui/index.html").as_uri())
                page.get_by_role("button", name="下载并更新").click()
                page.get_by_role("button", name="取消更新").click()
                page.get_by_text("已取消下载，当前版本可以继续使用。", exact=True).wait_for()
                self.assertTrue(page.get_by_role("button", name="下载并更新").is_enabled())
            finally:
                browser.close()

    def test_refresh_discovers_doubao_created_after_workspace_opened(self):
        bootstrap = BOOT.replace(json.dumps(INFO), json.dumps({**INFO, "agents": []}))
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.add_init_script(bootstrap)
                page.goto((resources / "ui/index.html").as_uri())
                page.get_by_text("还没发现支持的本机记录", exact=True).wait_for()
                page.evaluate("window.pywebview.api.agents=async()=>({ready:true,agents:[{id:'doubao_work',name:'豆包工作',sub:'字节跳动'}],targets:[],unsupported:[]})")
                page.get_by_role("button", name="重新读取").click()
                page.locator('#agents [data-agent="doubao_work"]').wait_for()
                page.get_by_text("仅用于排版检查的合成记录", exact=True).wait_for()
                self.assertTrue(page.get_by_role("button", name="重新读取").is_enabled())
            finally:
                browser.close()

    def test_single_workspace_layout_and_fully_hidden_sidebar(self):
        with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
            resources = prepare(Path(temporary))
            browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
            try:
                page = browser.new_page()
                page.add_init_script(BOOT)
                page.goto((resources / "ui/index.html").as_uri())
                page.get_by_text("仅用于排版检查的合成记录", exact=True).wait_for()
                for width in (960, 1100, 1280, 1440):
                    page.set_viewport_size({"width": width, "height": 820})
                    self.assertEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                    for selector in ("#workspace-toggle", "#workspace-update", "#search", "#reload"):
                        box = page.locator(selector).bounding_box()
                        self.assertGreaterEqual(box["x"], 0)
                        self.assertLessEqual(box["x"] + box["width"], width)
                toggle = page.get_by_role("button", name="隐藏工具栏")
                before = page.locator(".app").bounding_box()["x"]
                toggle.click()
                self.assertEqual(page.locator("#workspace-nav").evaluate("node=>getComputedStyle(node).display"), "none")
                self.assertLess(page.locator(".app").bounding_box()["x"], before)
                self.assertEqual(page.get_by_role("button", name="显示工具栏").get_attribute("aria-expanded"), "false")
                self.assertEqual(page.locator("#workspace-toggle").evaluate("node=>getComputedStyle(node).outlineStyle"), "none")
                page.get_by_role("button", name="显示工具栏").click()
                self.assertEqual(page.locator("iframe").count(), 0)
                page.get_by_role("button", name="检查更新").click()
                page.get_by_text("已经是当前最新的 Mac 版本。", exact=True).wait_for()
                page.evaluate("window.pywebview.api.check_update=async()=>({error:'无法验证安全连接',errorCode:'certificate',canOpenDownloads:true});window.pywebview.api.open_update=async()=>{window.downloadOpened=true;return {ok:true}}")
                page.get_by_role("button", name="检查更新").click()
                page.get_by_text("无法验证安全连接", exact=True).wait_for()
                page.get_by_role("button", name="打开下载页").click()
                page.wait_for_function("window.downloadOpened===true")
                page.evaluate("window.pywebview.api.check_update=async()=>({available:true,version:'0.4.1',canInstall:true})")
                page.get_by_role("button", name="检查更新").click()
                page.get_by_role("button", name="下载并更新").wait_for()
                page.evaluate("window.pywebview.api.check_update=async()=>({available:false})")
                page.get_by_role("button", name="检查更新").click()
                page.get_by_text("已经是当前最新的 Mac 版本。", exact=True).wait_for()
                self.assertFalse(page.locator("#workspace-download").is_visible())
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
