"""对话搬家 — 把对话记录从一个软件复制到另一个软件。"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import webview

from core import chatgpt, imports, mover, sources
from core.common import open_external
from embedded_startup import EmbeddedStartup

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

AGENTS = [
    {"id": "cursor_desktop", "name": "Cursor", "sub": "桌面版", "color": "#1f2933"},
    {"id": "workbuddy", "name": "WorkBuddy", "sub": "国内版", "color": "#e8590c"},
    {"id": "workbuddy_ai", "name": "WorkBuddy AI", "sub": "海外版", "color": "#0c8599"},
    {"id": "qwen_work", "name": "千问办公", "sub": "通义千问", "color": "#6741d9"},
    {"id": "doubao_work", "name": "豆包工作", "sub": "字节跳动", "color": "#1971c2"},
    {"id": "chatgpt", "name": "ChatGPT", "sub": "聊天、工作、Codex", "color": "#0b8f6f"},
    {"id": "claude_code", "name": "Claude Code", "sub": "Anthropic", "color": "#d97757"},
    {"id": "claude_desktop", "name": "Claude", "sub": "桌面版 · 聊天", "color": "#c15f3c"},
    {"id": "cowork", "name": "Cowork", "sub": "Claude 本机任务", "color": "#d97757"},
    {"id": "antigravity", "name": "Antigravity", "sub": "桌面端", "color": "#2f9e44"},
    {"id": "antigravity_cli", "name": "Antigravity", "sub": "命令行", "color": "#37b24d"},
    {"id": "cursor_cli", "name": "Cursor", "sub": "命令行", "color": "#495057"},
    {"id": "grok", "name": "Grok", "sub": "命令行", "color": "#343a40"},
    {"id": "hermes", "name": "Hermes", "sub": "Agent", "color": "#a61e4d"},
    {"id": "opencode", "name": "OpenCode", "sub": "桌面与命令行", "color": "#364fc7"},
]


class Api:
    def __init__(self) -> None:
        self._groups: dict[str, list[dict]] = {}
        self._job: mover.Job | None = None
        self._window = None
        self._lock = threading.Lock()

    def bind(self, window) -> None:
        self._window = window
        window.events.closing += self.can_close

    def can_close(self) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        try:
            return self._job is None or bool(self._job.snapshot()["finished"])
        finally:
            self._lock.release()

    # ---- reading

    def agents(self) -> dict:
        items = []
        for agent in AGENTS:
            if sources.installed(agent["id"]):
                items.append({**agent, "canTarget": agent["id"] in mover.TARGETS})
        targets = []
        for agent in items:
            capability = mover.TARGETS.get(agent["id"])
            product = "chatgpt" if agent["id"] == "chatgpt" else "claude" if agent["id"] in ("claude_code", "claude_desktop", "cowork") else ""
            name = "ChatGPT · 云端 Chat / Work" if agent["id"] == "chatgpt" else "Claude · 普通聊天" if agent["id"] == "claude_desktop" else "Claude · 本机 Cowork" if agent["id"] == "cowork" else agent["name"]
            targets.append({**agent, "name": name, "product": product, **(capability or {}), "canTarget": capability is not None,
                            "readOnlyReason": "" if capability else imports.READ_ONLY.get(agent["id"], "当前版本没有此软件的写入实现")})
        if sources.installed("codex"):
            for target, name in (("chatgpt_work", "Work"), ("codex", "Codex")):
                targets.append({"id": target, "name": f"ChatGPT · 本机 {name}", "sub": "本机任务历史", "product": "chatgpt",
                                "color": "#0b8f6f", "canTarget": True, **mover.TARGETS[target]})
        return {
            "agents": items,
            "targets": targets,
            "unsupported": sources.unsupported_found(),
            "ready": mover.txcript_path() is not None,
        }

    def sessions(self, agent_id: str, refresh: bool = False) -> dict:
        if agent_id not in {item["id"] for item in AGENTS}:
            return {"error": "不认识这个软件。"}
        try:
            if refresh or agent_id not in self._groups or agent_id == "chatgpt":
                if refresh and agent_id == "chatgpt":
                    sources.invalidate_chatgpt()
                self._groups[agent_id] = sources.list_groups(agent_id)
            groups = self._groups[agent_id]
        except Exception as error:  # noqa: BLE001
            mover.log(f"list {agent_id}: {error!r}")
            text = str(error).lower()
            if "429" in text or "rate" in text:
                return {"error": "ChatGPT 暂时限流了（读取太频繁）。请等几分钟，再点右上角的刷新。"}
            if agent_id == "chatgpt":
                return {"error": str(error) if str(error).startswith("ChatGPT") else "ChatGPT 本机数据没有读完整，请稍后刷新；详细原因已记入日志。"}
            if "locked" in text or "being used" in text:
                return {"error": "这个软件正在占用数据，请先关闭它再试一次。"}
            return {"error": "读取这个软件的对话时出了问题。"}
        total = sum(len(group["sessions"]) for group in groups)
        movable = sum(1 for group in groups for s in group["sessions"] if s["movable"])
        result = {"groups": groups, "total": total, "movable": movable}
        if agent_id == "chatgpt":
            result["web"] = chatgpt.info()  # how old the cloud part is, and whether it is updating
        return result

    def folders(self) -> list[dict]:
        try:
            return sources.known_folders()
        except Exception as error:  # noqa: BLE001
            mover.log(f"folders: {error!r}")
            return []

    def pick_folder(self) -> str:
        if self._window is None:
            return ""
        dialog = getattr(webview, "FileDialog", None)
        kind = dialog.FOLDER if dialog is not None else webview.FOLDER_DIALOG
        chosen = self._window.create_file_dialog(kind)
        return chosen[0] if chosen else ""

    # ---- moving

    def start_move(self, source: str, ids: list[str], target: str, directory: str) -> dict:
        with self._lock:
            if self._job is not None and not self._job.snapshot()["finished"]:
                return {"error": "正在搬运，请等这一批完成。"}
            if target not in mover.TARGETS:
                return {"error": "这个软件暂时不能作为目的地。"}
            if not sources.installed(target):
                return {"error": "没有检测到目标软件，请先安装并使用一次。"}
            if not directory or not Path(directory).is_dir():
                return {"error": "请选择已存在的文件夹。"}
            try:
                imports.preflight(target, mover.destination_env(target))
            except (ValueError, OSError) as error:
                return {"error": str(error)}
            except sqlite3.Error as error:
                mover.log(f"destination preflight {target}: {error!r}")
                return {"error": "目标软件的数据暂时无法读取，请关闭目标软件后重试。"}
            known = {s["id"]: s for g in self._groups.get(source, []) for s in g["sessions"]}
            chosen = [known[i] for i in ids if i in known and known[i]["movable"]]
            if not chosen:
                return {"error": "没有可以搬的对话。"}
            self._job = mover.Job(source, chosen, target, directory)
            return {"ok": True, "total": len(chosen)}

    def open_import_folder(self, index: int) -> dict:
        if self._job is None or not isinstance(index, int):
            return {"error": "没有导入结果。"}
        items = self._job.snapshot()["items"]
        if index < 0 or index >= len(items) or items[index]["state"] != "ok":
            return {"error": "这条记录尚未导入成功。"}
        location = Path(items[index].get("location", ""))
        if not (location.is_file() or location.is_dir() and str(location) != "."):
            return {"error": "此目标保存在数据库中，请使用续聊命令。"}
        try:
            open_external(str(location if location.is_dir() else location.parent))
        except (OSError, subprocess.SubprocessError):
            return {"error": "无法打开记录位置，请在文件管理器中查看下方路径。"}
        return {"ok": True}

    def open_in_app(self, index: int) -> dict:
        """Ask ChatGPT to open a thread we just wrote, by its id. Only codex:// links of our own results."""
        if self._job is None or not isinstance(index, int):
            return {"error": "没有导入结果。"}
        items = self._job.snapshot()["items"]
        if index < 0 or index >= len(items) or items[index]["state"] != "ok":
            return {"error": "这条记录尚未导入成功。"}
        url = str(items[index].get("openUrl", ""))
        imported = str(items[index].get("importedId", ""))
        if not imported or url != f"codex://threads/{imported}" or not mover.SAFE_ID.match(imported):
            return {"error": "这个目标不支持直接打开。"}
        try:
            open_external(url)
        except (OSError, subprocess.SubprocessError) as error:
            mover.log(f"open_in_app {url}: {error!r}")
            return {"error": "没有找到可以打开它的软件，请先安装并启动 ChatGPT。"}
        return {"ok": True}

    def move_status(self) -> dict:
        if self._job is None:
            return {"finished": True, "total": 0, "done": 0, "ok": 0, "skipped": 0, "failed": 0, "items": []}
        return self._job.snapshot()


def main() -> None:
    api = Api()
    startup = EmbeddedStartup.from_environment() if sys.platform == "win32" else None
    window = webview.create_window(
        "对话搬家",
        url=str(ROOT / "ui" / "index.html"),
        js_api=api,
        width=1180,
        height=780,
        min_size=(940, 640),
        background_color="#F6F8FB",
        text_select=False,
        hidden=startup is not None,
        focus=startup is None,
    )
    api.bind(window)
    if startup is not None:
        startup.bind(window)
    icon = ROOT / "ui" / "icon.ico"
    webview.start(icon=str(icon) if icon.is_file() else None)


if __name__ == "__main__":
    main()
