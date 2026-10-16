from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def home_dir() -> Path:
    return Path.home()


def default_codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    return home_dir() / ".codex"


def default_state_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or (home_dir() / "AppData" / "Local"))
        return base / "vibcoding" / "codex-auto-resume"
    if sys.platform == "darwin":
        return home_dir() / "Library" / "Application Support" / "vibcoding" / "codex-auto-resume"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(xdg).expanduser() if xdg else home_dir() / ".local" / "share"
    return root / "vibcoding" / "codex-auto-resume"


def sessions_dir(codex_home: Path) -> Path:
    return Path(codex_home) / "sessions"


def tool_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundled_codex() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    candidate = Path(sys._MEIPASS) / "bin" / "vendor" / "x86_64-pc-windows-msvc" / "bin" / "codex.exe"
    if not candidate.is_file():
        raise FileNotFoundError("工作台的续跑组件不完整，请重新安装完整工作台。")
    return candidate


def resolve_codex_command(explicit: str | None = None) -> list[str]:
    packaged = bundled_codex()
    if packaged is not None:
        return [str(packaged)]
    if explicit:
        return _without_console_wrapper(_split_or_single(explicit))

    env_bin = os.environ.get("CODEX_BIN", "").strip()
    if env_bin:
        return _without_console_wrapper(_split_or_single(env_bin))

    native = _find_native_codex()
    if native:
        return [native]

    node_js = _find_node_js_codex()
    if node_js:
        return node_js

    which = shutil.which("codex")
    if which:
        return _without_console_wrapper([which])

    mac_bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if mac_bundled.exists():
        return [str(mac_bundled)]
    mac_codex_app = Path("/Applications/Codex.app/Contents/Resources/codex")
    if mac_codex_app.exists():
        return [str(mac_codex_app)]

    raise FileNotFoundError("找不到 codex 可执行文件，请把 Codex CLI 加入 PATH，或设置 CODEX_BIN")


def _npm_root() -> Path:
    return Path(os.environ.get("APPDATA") or (home_dir() / "AppData" / "Roaming")) / "npm"


def _find_native_codex() -> str | None:
    if sys.platform != "win32":
        return None
    roots = [
        _npm_root() / "node_modules" / "@openai" / "codex",
        _npm_root() / "node_modules" / "@openai" / "codex-win32-x64",
        _npm_root() / "node_modules" / "@openai" / "codex-win32-arm64",
    ]
    triples = ("x86_64-pc-windows-msvc", "aarch64-pc-windows-msvc")
    for root in roots:
        for triple in triples:
            candidate = root / "vendor" / triple / "bin" / "codex.exe"
            if candidate.exists():
                return str(candidate)
    return None


def _find_node_js_codex() -> list[str] | None:
    js = _npm_root() / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    node = shutil.which("node")
    if js.exists() and node:
        return [node, str(js)]
    return None


def _without_console_wrapper(command: list[str]) -> list[str]:
    if not command:
        return command
    first = command[0].lower()
    if first.endswith((".cmd", ".bat", ".ps1")):
        unwrapped = _find_native_codex()
        if unwrapped:
            return [unwrapped]
        node_js = _find_node_js_codex()
        if node_js:
            return node_js
    return command


def _split_or_single(value: str) -> list[str]:
    path = Path(value)
    if path.exists():
        return [str(path)]
    return [value]
