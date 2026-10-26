from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parent
ASSETS = ROOT / "ui" / "assets" / "agents"
AGENTS = [
    ("cursor_desktop", "Cursor"), ("workbuddy", "WorkBuddy"), ("workbuddy_ai", "WorkBuddy AI"),
    ("qwen_work", "千问办公"), ("doubao_work", "豆包工作"), ("chatgpt", "ChatGPT"), ("codex_cli", "Codex CLI"),
    ("claude_code", "Claude Code"), ("claude_desktop", "Claude"), ("cowork", "Cowork"),
    ("antigravity", "Antigravity"), ("grok", "Grok"), ("opencode", "OpenCode"), ("hermes", "Hermes"),
    ("copilot_desktop", "GitHub Copilot"),
]


class AgentIconTests(unittest.TestCase):
    def test_tool_brand_matches_workspace_catalog_icon(self):
        workspace_assets = ROOT.parent / "workspace" / "assets"
        catalog = json.loads((workspace_assets / "tool-catalog.json").read_text(encoding="utf-8"))
        tool = next(entry for entry in catalog if entry["id"] == "dialog-mover")
        workspace_icon = workspace_assets.parent / tool["icon"]
        self.assertEqual((ROOT / "ui" / "assets" / "dialog-mover.png").read_bytes(), workspace_icon.read_bytes())

    def test_chatgpt_uses_black_transparent_light_theme_logo(self):
        manifest = json.loads((ASSETS / "sources.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["chatgpt"]["source"].endswith("altform-lightunplated.png"))
        with Image.open(ASSETS / "chatgpt.png") as picture:
            rgba = picture.convert("RGBA")
            self.assertEqual(rgba.getchannel("A").getextrema(), (0, 255))
            for corner in ((0, 0), (rgba.width - 1, 0), (0, rgba.height - 1), (rgba.width - 1, rgba.height - 1)):
                self.assertEqual(rgba.getpixel(corner)[3], 0)
            pixels = (rgba.getpixel((column, row)) for row in range(rgba.height) for column in range(rgba.width))
            visible = [pixel for pixel in pixels if pixel[3] >= 200]
            self.assertGreater(len(visible), rgba.width * rgba.height // 10)
            self.assertTrue(all(max(pixel[:3]) < 40 for pixel in visible))

    def test_agent_editions_always_use_the_second_line(self):
        agents = [
            {"id": "cursor_desktop", "name": "Cursor", "sub": "桌面版"},
            {"id": "cursor_cli", "name": "Cursor", "sub": "命令行"},
            {"id": "antigravity", "name": "Antigravity", "sub": "桌面端"},
            {"id": "antigravity_cli", "name": "Antigravity", "sub": "命令行"},
            {"id": "workbuddy", "name": "WorkBuddy", "sub": "国内版"},
            {"id": "workbuddy_ai", "name": "WorkBuddy AI", "sub": "海外版"},
            {"id": "qwen_work", "name": "千问办公", "sub": "通义千问"},
            {"id": "doubao_work", "name": "豆包工作", "sub": "字节跳动"},
            {"id": "chatgpt", "name": "ChatGPT", "sub": "聊天、工作、Codex"},
            {"id": "claude_code", "name": "Claude Code", "sub": "Anthropic"},
            {"id": "claude_desktop", "name": "Claude", "sub": "桌面版·聊天"},
        ]
        targets = [dict(agent, canTarget=True) for agent in agents[:4]]
        capabilities = {"ready": True, "agents": agents, "targets": targets, "unsupported": []}
        source = {"groups": [{"title": "界面测试", "kind": "none", "path": "", "sessions": [{"id": "synthetic", "title": "非真实记录", "movable": True, "when": "刚刚", "ts": 1}]}], "total": 1, "movable": 1}
        bootstrap = "window.pywebview={api:{agents:async()=>(CAPABILITIES),sessions:async()=>(SOURCE)}};window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));".replace("CAPABILITIES", json.dumps(capabilities)).replace("SOURCE", json.dumps(source))
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page()
                page.add_init_script(bootstrap)
                page.goto((ROOT / "ui" / "index.html").as_uri())
                page.locator('[data-agent="claude_desktop"]').wait_for()
                page.wait_for_function("[...document.querySelectorAll('.brand-mark img')].every(image=>image.complete&&image.naturalWidth>0)")
                for width in (1180, 940):
                    page.set_viewport_size({"width": width, "height": 780})
                    brand = page.locator(".brand-mark")
                    brand_image = brand.locator("img")
                    self.assertEqual(brand_image.get_attribute("src"), "assets/dialog-mover.png")
                    self.assertEqual(brand.locator("svg").count(), 0)
                    self.assertTrue(brand_image.evaluate("element=>element.complete&&element.naturalWidth>0"))
                    self.assertEqual(brand.evaluate("element=>getComputedStyle(element).backgroundColor"), "rgba(0, 0, 0, 0)")
                    self.assertEqual(brand_image.evaluate("element=>getComputedStyle(element).objectFit"), "contain")
                    self.assertEqual(brand_image.evaluate("element=>getComputedStyle(element).filter"), "none")
                    brand_box = brand_image.bounding_box()
                    self.assertEqual(brand_box["width"], 38)
                    self.assertEqual(brand_box["height"], 38)
                    for agent in agents:
                        with self.subTest(width=width, agent=agent["id"]):
                            row = page.locator(f'[data-agent="{agent["id"]}"]')
                            title = row.locator(".agent-name")
                            subtitle = row.locator(".agent-sub")
                            self.assertEqual(title.inner_text(), agent["name"])
                            self.assertEqual(subtitle.inner_text(), agent["sub"])
                            title_box = title.bounding_box()
                            subtitle_box = subtitle.bounding_box()
                            self.assertAlmostEqual(title_box["x"], subtitle_box["x"], places=1)
                            self.assertGreaterEqual(subtitle_box["y"], title_box["y"] + title_box["height"] - 0.1)
                    self.assertEqual(page.locator(".twin").count(), 0)
                self.assertEqual(page.locator("#agents [data-agent]").evaluate_all("rows=>rows.map(row=>row.dataset.agent)"), [agent["id"] for agent in agents])
                page.locator(".row").first.click()
                page.locator("#bar-go").click()
                for agent in targets:
                    choice = page.locator(f'[data-target="{agent["id"]}"]')
                    self.assertEqual(choice.locator("b").inner_text(), agent["name"])
                    self.assertEqual(choice.locator("small").inner_text(), agent["sub"])
            finally:
                browser.close()

    def test_bundled_icons_match_original_resource_manifest(self):
        manifest = json.loads((ASSETS / "sources.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(manifest), 15)
        for name, data in manifest.items():
            if data.get("status") == "unavailable":
                self.assertFalse((ASSETS / f"{name}.png").exists())
                continue
            asset = ASSETS / f"{name}.png"
            self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(), data["sha256"], name)
            with Image.open(asset) as picture:
                self.assertEqual(list(picture.size), data["size"], name)
                self.assertGreaterEqual(min(picture.size), 32, name)

    def test_sidebar_and_destination_modes_use_images(self):
        agents = [{"id": identity, "name": name, "full": name, "sub": "测试", "canTarget": identity != "hermes"} for identity, name in AGENTS]
        targets = [dict(agent) for agent in agents]
        targets = [target for target in targets if target["id"] not in ("chatgpt", "claude_desktop")]
        for identity, product, name in (("chatgpt_work", "chatgpt", "本机 Work"), ("codex", "chatgpt", "本机 Codex"), ("claude_code", "claude", "Claude Code"), ("cowork", "claude", "Cowork")):
            targets = [target for target in targets if target["id"] != identity]
            targets.append({"id": identity, "product": product, "name": name, "full": name, "canTarget": True})
        capabilities = {"ready": True, "agents": agents, "targets": targets, "unsupported": [{"id": "unknown", "name": "未适配软件"}]}
        source = {"groups": [{"title": "示例项目", "kind": "folder", "path": "D:\\示例项目", "sessions": [{"id": "synthetic", "title": "界面测试示例，不是真实记录", "movable": True, "when": "刚刚", "ts": 1}]}], "total": 1, "movable": 1}
        bootstrap = """window.pywebview={api:{agents:async()=>(CAPABILITIES),sessions:async()=>(SOURCE)}};window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));""".replace("CAPABILITIES", json.dumps(capabilities)).replace("SOURCE", json.dumps(source))
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(channel="msedge", headless=True)
            try:
                page = browser.new_page(viewport={"width": 1180, "height": 780})
                page.add_init_script(bootstrap)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto((ROOT / "ui" / "index.html").as_uri())
                try:
                    page.locator(".row").first.wait_for(timeout=5000)
                except Exception:
                    self.fail(f"Initial view failed: {page.locator('body').inner_text()}\nErrors: {errors}")
                page.wait_for_function("[...document.querySelectorAll('.agent-logo img')].every(image=>image.complete&&image.naturalWidth>0)")
                self.assertEqual(page.locator(".mono").count(), 0)
                chatgpt_logo = page.locator('#agents [data-agent-logo="chatgpt"]')
                self.assertEqual(chatgpt_logo.evaluate("element=>getComputedStyle(element).backgroundColor"), "rgba(0, 0, 0, 0)")
                self.assertEqual(chatgpt_logo.locator("img").evaluate("element=>getComputedStyle(element).filter"), "none")
                self.assertEqual(page.locator(".agent-logo-dark").count(), 0)
                self.assertEqual(page.locator('[data-agent-logo="hermes"] svg').count(), 1)
                self.assertIn("暂未找到原版图标", page.locator('[data-agent-logo="hermes"]').get_attribute("title"))
                self.assertEqual(page.locator('[data-agent-logo="unknown"] svg').count(), 1)
                page.screenshot(path=str(ROOT / "_agent_icons_preview.png"))
                page.locator(".row").first.click()
                page.locator("#bar-go").click()
                for product, expected in (("chatgpt", "chatgpt"), ("claude", "claude")):
                    button = page.locator(f'[data-product="{product}"]')
                    self.assertTrue(button.is_enabled())
                    self.assertTrue(button.locator("img").get_attribute("src").endswith(f"/{expected}.png"))
                    button.click()
                    page.wait_for_function("[...document.querySelectorAll('#sheet-body .agent-logo img')].every(image=>image.complete&&image.naturalWidth>0)")
                    self.assertEqual(page.locator("#sheet-body .mono").count(), 0)
                    self.assertGreaterEqual(page.locator("#sheet-body .agent-logo img").count(), 2)
                    if product == "chatgpt":
                        self.assertTrue(all(color == "rgba(0, 0, 0, 0)" for color in page.locator("#sheet-body .agent-logo").evaluate_all("elements=>elements.map(element=>getComputedStyle(element).backgroundColor)")))
                        self.assertEqual(page.locator(".agent-logo-dark").count(), 0)
                    page.locator("#sheet-back").click()
                page.locator('[data-target="workbuddy_ai"] img').evaluate("image=>{image.src='assets/missing-test-icon.png';}")
                page.locator('[data-target="workbuddy_ai"] .agent-logo-missing').wait_for()
                self.assertEqual(page.locator('[data-target="workbuddy_ai"] svg').count(), 1)
                self.assertEqual(errors, [])
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
