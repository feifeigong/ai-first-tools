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
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
