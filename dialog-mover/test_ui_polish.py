import json
import re
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parent
CAPABILITIES = {"ready": True, "agents": [{"id": "cursor_desktop", "name": "Cursor", "sub": "桌面版"}, {"id": "workbuddy", "name": "WorkBuddy", "sub": "国内版"}], "targets": [], "unsupported": []}
SOURCE = {"groups": [{"title": "界面排版测试", "kind": "folder", "path": "D:\\UI-Test", "sessions": [{"id": "ui-fixture", "title": "仅用于界面验证的合成记录", "movable": True, "ts": 1, "when": "刚刚"}]}], "total": 1, "movable": 1}
BOOTSTRAP = "window.pywebview={api:{agents:async()=>(CAPABILITIES),sessions:async()=>(SOURCE)}};window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));".replace("CAPABILITIES", json.dumps(CAPABILITIES)).replace("SOURCE", json.dumps(SOURCE))


class UiPolishTests(unittest.TestCase):
    def test_responsive_header_and_selection_bar_stay_inside_the_window(self):
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page()
                page.add_init_script(BOOTSTRAP)
                page.goto((ROOT / "ui" / "index.html").as_uri())
                page.locator(".row").first.wait_for()
                page.locator(".row").first.click()
                for width in (940, 1044, 1180, 1440):
                    with self.subTest(width=width):
                        page.set_viewport_size({"width": width, "height": 700})
                        for selector in (".titles", ".tools", "#search", "#reload", "#bar", "#bar-go"):
                            bounds = page.locator(selector).bounding_box()
                            self.assertGreaterEqual(bounds["x"], 0)
                            self.assertLessEqual(bounds["x"] + bounds["width"], width)
                            self.assertLessEqual(bounds["y"] + bounds["height"], 700)
                        title = page.locator(".titles").bounding_box()
                        tools = page.locator(".tools").bounding_box()
                        if width <= 1200:
                            self.assertGreaterEqual(tools["y"], title["y"] + title["height"])
                        self.assertEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                self.assertEqual(page.get_by_role("searchbox", name="搜索标题或文件夹").count(), 1)
                self.assertEqual(page.get_by_role("navigation", name="已安装的软件").count(), 1)
            finally:
                browser.close()

    def test_mouse_focus_is_quiet_and_keyboard_focus_remains_visible(self):
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page()
                page.add_init_script(BOOTSTRAP)
                page.goto((ROOT / "ui" / "index.html").as_uri())
                button = page.locator('[data-agent="cursor_desktop"]')
                button.click()
                self.assertEqual(button.evaluate("node=>getComputedStyle(node).outlineStyle"), "none")
                page.keyboard.press("Tab")
                focused = page.locator("button:focus-visible")
                self.assertEqual(focused.count(), 1)
                self.assertEqual(focused.evaluate("node=>getComputedStyle(node).outlineWidth"), "2px")
                page.emulate_media(reduced_motion="reduce")
                self.assertEqual(focused.evaluate("node=>getComputedStyle(node).transitionDuration"), "0s")
            finally:
                browser.close()

    def test_readable_neutral_text_and_primary_action_contrast(self):
        def luminance(color):
            channels = [int(color[index:index + 2], 16) / 255 for index in (0, 2, 4)]
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
            return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
        colors = dict(re.findall(r"--([\w-]+): #([0-9a-f]{6})", (ROOT / "ui" / "style.css").read_text(encoding="utf-8")))
        for foreground, background in ((colors["muted"], colors["bg"]), (colors["muted"], "fafbfd"), (colors["accent-ink"], colors["accent"]), ("145c9c", colors["accent-soft"])):
            with self.subTest(foreground=foreground, background=background):
                values = sorted((luminance(foreground), luminance(background)))
                self.assertGreaterEqual((values[1] + 0.05) / (values[0] + 0.05), 4.5)


if __name__ == "__main__":
    unittest.main()
