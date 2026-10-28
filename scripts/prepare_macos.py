from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def prepare(destination: Path) -> Path:
    ui = destination / "ui"
    ui.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "dialog-mover" / "ui", ui, dirs_exist_ok=True)
    shutil.copytree(ROOT / "macos" / "ui", ui, dirs_exist_ok=True)
    shutil.copy2(ROOT / "workspace" / "assets" / "ai-first-app-icon.png", ui / "assets" / "ai-first.png")
    shutil.copy2(ROOT / "workspace" / "assets" / "codex.png", ui / "assets" / "codex.png")
    shutil.copy2(ROOT / "macos" / "version.json", destination / "version.json")
    shutil.copy2(ROOT / "workspace/assets/whats-new.json", ui / "whats-new.json")
    html = (ui / "index.html").read_text(encoding="utf-8")
    header = '''<header class="workspace-header">
      <img class="workspace-logo" src="assets/ai-first.png" alt="AI一手" width="80" height="44">
      <span class="workspace-name">工具箱</span>
      <button id="workspace-toggle" class="workspace-button workspace-toggle" aria-controls="workspace-nav" aria-expanded="true" aria-label="隐藏工具栏"></button>
      <span class="workspace-spacer"></span><button id="workspace-version" class="workspace-button workspace-version" title="查看本次更新" aria-label="查看本次更新">Mac 预览版</button>
      <button id="workspace-download" class="workspace-button workspace-primary" hidden>下载并更新</button>
      <button id="workspace-update" class="workspace-button" disabled>检查更新</button>
    </header>
    <div class="workspace-body">
      <nav id="workspace-nav" class="workspace-nav" aria-label="AI一手工具"><p>工具</p>
        <button id="workspace-mover" class="workspace-tool" aria-current="page"><img src="assets/dialog-mover.png" alt="" width="32" height="32">对话搬家</button>
        <button id="workspace-resume" class="workspace-tool"><img src="assets/codex.png" alt="" width="32" height="32">续跑与重置</button>
      </nav>'''
    ending = (ROOT / 'macos/ui/auto-resume.html').read_text(encoding='utf-8') + (ROOT / 'macos/ui/whats-new.html').read_text(encoding='utf-8') + '''</div><div id="workspace-notice" class="workspace-notice" role="status" aria-live="polite" hidden>
      <div class="workspace-update-detail"><span id="workspace-message"></span><progress id="workspace-progress" max="100" aria-label="更新下载进度" hidden></progress></div>
      <button id="workspace-dismiss" class="workspace-button" aria-label="关闭提示">×</button></div>'''
    html = html.replace("<title>对话搬家</title>", "<title>AI一手工具箱</title>")
    html = html.replace("</head>", '<link rel="stylesheet" href="workspace.css">\n<link rel="stylesheet" href="reset-notices.css">\n</head>')
    html = html.replace("<body>", "<body>\n" + header, 1)
    html = html.replace('  <div id="bar"', ending + '\n  <div id="bar"', 1)
    html = html.replace("</body>", '<script src="whats-new.js"></script>\n<script src="workspace.js"></script>\n<script src="auto-resume.js"></script>\n<script src="reset-notices.js"></script>\n</body>')
    (ui / "index.html").write_text(html, encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=ROOT / "artifacts" / "macos" / "resources")
    args = parser.parse_args()
    prepare(args.destination.resolve())
