from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    root = Path(__file__).resolve().parent.parent
    names = [("cursor_desktop", "Cursor", "桌面版", 8), ("workbuddy", "WorkBuddy", "国内版", 4), ("workbuddy_ai", "WorkBuddy AI", "海外版", 3), ("qwen_work", "千问办公", "通义千问", 6), ("doubao_work", "豆包工作", "字节跳动", 5), ("chatgpt", "ChatGPT", "聊天、工作、Codex", 12), ("claude_code", "Claude Code", "Anthropic", 4), ("claude_desktop", "Claude", "桌面版 · 聊天", 3)]
    agents = [{"id": identity, "name": name, "full": name, "sub": subtitle, "count": count, "canTarget": identity not in {"doubao_work", "claude_desktop", "chatgpt"}} for identity, name, subtitle, count in names]
    groups = []
    for project, titles, folder in [("个人网站", ["设计首页，让作品更好看", "给网站增加联系入口", "整理页面布局和配色"], "D:\\Projects\\personal-site"), ("工作笔记", ["把想法整理成一份清单", "制作每周工作总结", "优化日常工作的流程"], "D:\\Projects\\notes"), ("Home", ["聊聊下一步的计划", "推荐一个简单的学习方法"], "")]:
        groups.append({"title": project, "kind": "folder", "path": folder, "sessions": [{"id": f"example-{len(groups)}-{index}", "title": title, "movable": True, "folder": folder, "ts": 1, "when": "今天" if index == 0 else "昨天"} for index, title in enumerate(titles)]})
    fixture = {"groups": groups, "total": 8, "movable": 8}
    capabilities = {"ready": True, "agents": agents, "targets": [], "unsupported": []}
    bootstrap = "window.pywebview={api:{agents:async()=>(CAPABILITIES),sessions:async()=>(SOURCE)}};window.addEventListener('DOMContentLoaded',()=>window.dispatchEvent(new Event('pywebviewready')));".replace("CAPABILITIES", json.dumps(capabilities, ensure_ascii=False)).replace("SOURCE", json.dumps(fixture, ensure_ascii=False))
    destination = root / "docs" / "assets"
    destination.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1)
        page.add_init_script(bootstrap)
        page.goto((root / "dialog-mover" / "ui" / "index.html").as_uri())
        page.locator(".row").first.wait_for()
        page.wait_for_function("[...document.querySelectorAll('.agent-logo img')].every(image=>image.complete&&image.naturalWidth>0)")
        page.screenshot(path=str(destination / "dialog-mover.png"))
        browser.close()


if __name__ == "__main__":
    main()
