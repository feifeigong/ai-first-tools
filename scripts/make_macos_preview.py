from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from prepare_macos import ROOT, prepare

sys.path.insert(0, str(ROOT / "dialog-mover"))
from main import AGENTS
from test_macos_ui import BOOT, INFO, SESSIONS
from playwright.sync_api import sync_playwright


def main() -> None:
    examples = {**INFO, "agents": [item for item in AGENTS if item["id"] in
                                   ("cursor_desktop", "workbuddy", "workbuddy_ai", "qwen_work", "doubao_work", "chatgpt", "claude_code", "cowork")]}
    rows = [{"id": f"synthetic-{index}", "title": title, "movable": True, "ts": index, "when": "刚刚"}
            for index, title in enumerate(("给网站首页添加产品介绍", "整理产品上线检查清单", "为新工具设计简单的操作流程", "检查移动端页面布局"), 1)]
    sessions = {"groups": [{"title": "工具工作台", "kind": "folder", "path": "/Users/example/Projects/ai-first-tools", "sessions": rows}],
                "total": len(rows), "movable": len(rows)}
    bootstrap = BOOT.replace(json.dumps(INFO), json.dumps(examples)).replace(json.dumps(SESSIONS), json.dumps(sessions))
    output = ROOT / "docs" / "assets" / "macos-preview.png"
    with tempfile.TemporaryDirectory() as temporary, sync_playwright() as runtime:
        resources = prepare(Path(temporary))
        browser = runtime.chromium.launch(channel="msedge" if sys.platform == "win32" else None, headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
            page.add_init_script(bootstrap)
            page.goto((resources / "ui/index.html").as_uri())
            page.get_by_text(rows[0]["title"], exact=True).wait_for()
            page.screenshot(path=str(output))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
