"""对话搬家 — 把对话记录从一个软件复制到另一个软件。"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import webview

from core import chatgpt, copilot_import, copilot_refresh, imports, mover, sources, memory_store, memory_deploy, memory_jobs, memory_workspace
from core.common import open_external
from embedded_startup import EmbeddedStartup

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

if getattr(sys, "frozen", False):
    executable_root = Path(sys.executable).resolve().parent
    if any((parent / "development-preview.json").is_file() for parent in (executable_root, *list(executable_root.parents)[:3])):
        from core.common import localappdata
        os.environ.setdefault("AI_FIRST_MOVER_PREVIEW_DATA", str(localappdata() / "AI一手工具工作台" / "memory-preview" / "mover"))

AGENTS = [
    {"id": "cursor_desktop", "name": "Cursor", "sub": "桌面版", "color": "#1f2933"},
    {"id": "workbuddy", "name": "WorkBuddy", "sub": "国内版", "color": "#e8590c"},
    {"id": "workbuddy_ai", "name": "WorkBuddy AI", "sub": "海外版", "color": "#0c8599"},
    {"id": "qwen_work", "name": "千问办公", "sub": "通义千问", "color": "#6741d9"},
    {"id": "doubao_work", "name": "豆包工作", "sub": "字节跳动", "color": "#1971c2"},
    {"id": "chatgpt", "name": "ChatGPT", "sub": "聊天、工作、桌面 Codex", "color": "#0b8f6f"},
    {"id": "codex_cli", "name": "Codex CLI", "sub": "命令行记录", "color": "#0b8f6f", "sourceOnly": True},
    {"id": "claude_code", "name": "Claude Code", "sub": "Anthropic", "color": "#d97757"},
    {"id": "claude_desktop", "name": "Claude", "sub": "桌面版 · 聊天", "color": "#c15f3c"},
    {"id": "cowork", "name": "Cowork", "sub": "Claude 本机任务", "color": "#d97757"},
    {"id": "antigravity", "name": "Antigravity", "sub": "桌面端", "color": "#2f9e44"},
    {"id": "antigravity_cli", "name": "Antigravity", "sub": "命令行", "color": "#37b24d"},
    {"id": "cursor_cli", "name": "Cursor", "sub": "命令行", "color": "#495057"},
    {"id": "grok", "name": "Grok", "sub": "命令行", "color": "#343a40"},
    {"id": "hermes", "name": "Hermes", "sub": "Agent", "color": "#a61e4d"},
    {"id": "opencode", "name": "OpenCode", "sub": "桌面与命令行", "color": "#364fc7"},
    {"id": "copilot_desktop", "name": "GitHub Copilot", "sub": "桌面端 · 本机历史", "color": "#24292f"},
]


class Api:
    def __init__(self) -> None:
        self._groups: dict[str, list[dict]] = {}
        self._job: mover.Job | None = None
        self._window = None
        self._lock = threading.Lock()
        self._memory_job = None
        self._memory_context = None
        self._memory_plan = None
        self._memory_deployment = None
        self._memory_saved_items = None

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
            if agent.get("sourceOnly"):
                continue
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
            "smartTargets": [{**item, "full": item["name"], "canTarget": sources.installed("copilot_desktop"),
                "readOnlyReason": "请先打开 Copilot 桌面端完成初始化",
                "folderHint": "会单独新建一个智能搬家资料项目。",
                "notice": "对话会沿用原来的名称，并加上“智能搬家”标识。打开后，输入并发送下一步想做的事即可。"}
                for item in memory_deploy.available_targets()],
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
            if agent_id == "copilot_desktop":
                return {"error": "Copilot 桌面索引暂时无法读取或格式已变化，请关闭 Copilot 后刷新；未修改源记录。"}
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

    def prepare_memory(self, source: str, ids: list[str], target: str, directory: str = "") -> dict:
        with self._lock:
            if self._job is not None and not self._job.snapshot()["finished"]:
                return {"error": "正在处理，请等这一批完成。"}
            if target not in memory_deploy.TARGETS or directory:
                return {"error": "智能搬家只使用独立资料项目，不写入已有项目。请返回重新选择软件。"}
            if not isinstance(ids, list): return {"error": "会话列表不正确。"}
            known = {s["id"]: s for g in self._groups.get(source, []) for s in g["sessions"]}
            chosen = [known[i] for i in dict.fromkeys(ids) if i in known and known[i]["movable"]]
            if not chosen: return {"error": "没有可以读取的对话。"}
            self._memory_context = {"target": target, "directories": {}}
            self._memory_plan = None
            self._memory_deployment = None
            self._memory_saved_items = None
            self._memory_job = memory_jobs.PrepareJob(source, chosen)
            self._job = self._memory_job
            return {"ok": True, "total": len(chosen)}

    def memory_status(self) -> dict:
        return self._memory_job.snapshot() if self._memory_job else {"finished": True, "items": [], "total": 0}

    def memory_plan(self) -> dict:
        with self._lock:
            if self._memory_job is None or not self._memory_job.snapshot()["finished"]:
                return {"error": "请先等待历史读取完成。"}
            items = self._memory_job.snapshot()["items"]
            if not items or any(i["state"] != "ok" for i in items):
                return {"error": "有旧对话没能完整保存，请返回后重试；Copilot 项目还没有改动。"}
            try:
                plans = []
                for item in items:
                    directory = self._memory_context["directories"].get(item["bundle"])
                    plan = memory_deploy.prepare_entry(memory_jobs.library(), self._memory_context["target"],
                        item["bundle"], Path(directory) if directory else None)
                    self._memory_context["directories"][item["bundle"]] = plan["workspace"]
                    plans.append(plan)
                self._memory_context["directory"] = plans[-1]["workspace"]
                self._memory_plan = {"entries": plans}
                previews = [memory_deploy.entry_preview(plan) for plan in plans]
                return {"ok": True, **previews[-1], "entries": previews,
                        "reused_count": sum(bool(p.get("reused")) for p in previews)}
            except memory_deploy.SavedEntryError as error:
                return {"error": str(error), "error_stage": "existing-entry"}
            except Exception as error:
                return {"error": str(error) if isinstance(error, ValueError) else "暂时无法准备好搬家，请返回后重试；项目还没有改动。"}

    def deploy_memory(self) -> dict:
        with self._lock:
            if self._memory_plan is None or self._memory_deployment is not None:
                return {"error": "请先返回，保存旧对话并确认这次搬家的内容。"}
            try:
                items = self._memory_job.snapshot()["items"]
                results = []
                for planned in self._memory_plan["entries"]:
                    plan = memory_deploy.prepare_entry(memory_jobs.library(), self._memory_context["target"],
                        planned["bundle"], Path(planned["workspace"]))
                    if "reuse" not in plan and plan["fingerprint"] != planned["fingerprint"]:
                        raise ValueError("刚才有项目文件发生变化，请返回重新确认；已保存的对话仍保留。")
                    result = memory_deploy.install(plan, memory_jobs.library())
                    results.append({**result, "bundle": planned["bundle"]})
                self._memory_deployment = results[-1]
                self._memory_saved_items = [i for i in items if i["bundle"] == results[-1]["bundle"]]
                return {"ok": True, **self._memory_deployment, "entries": results,
                        "reused_count": sum(bool(r.get("reused")) for r in results)}
            except Exception as error:
                return {"error": str(error) if isinstance(error, ValueError) else "这次搬家没有完成，已停止写入。完整旧记录仍保存在工具箱，请返回后重试。"}

    def confirm_memory_facts(self, updates: dict) -> dict:
        """Optional review after moving; changes only the workbench's own index."""
        with self._lock:
            if not self._memory_deployment:
                return {"error": "请先完成这次搬家。"}
            try:
                valid = {i["bundle"] for i in self._saved_memory_items() if i["state"] == "ok"}
                if not isinstance(updates, dict) or set(updates) - valid:
                    raise ValueError("这条要求不在本次选择的旧对话中。")
                for identity, entries in updates.items():
                    memory_store.update_facts(memory_jobs.library() / "bundles" / identity, entries)
                return {"ok": True}
            except (OSError, ValueError, sqlite3.Error):
                return {"error": "没有保存成功，请重新查看要保留的要求。"}

    def _saved_memory_items(self) -> list[dict]:
        if self._memory_saved_items is not None:
            return self._memory_saved_items
        return self._memory_job.snapshot()["items"] if self._memory_job else []

    def memory_records(self) -> dict:
        try:
            return {"items": memory_deploy.saved_records(memory_jobs.library())}
        except (OSError, ValueError):
            return {"error": "暂时无法读取搬家记录，请稍后重试。"}

    def select_memory_record(self, identity: str) -> dict:
        with self._lock:
            if self._job is not None and not self._job.snapshot()["finished"]:
                return {"error": "请等当前搬家完成，再查看以前的记录。"}
            try:
                record = memory_deploy.saved_record(memory_jobs.library(), identity)
                reader = memory_store.HistoryReader(Path(record["location"]))
                items = []
                for bundle, path in reader.bundles.items():
                    info = memory_store.summary(path)
                    items.append({"bundle": bundle, "title": info["title"], "state": "ok",
                                  "facts": info["facts"][:100], "facts_total": len(info["facts"])})
                self._memory_deployment = record
                self._memory_saved_items = items
                self._memory_plan = None
                return {"ok": True, "deployment": record, "items": items}
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                return {"error": "这次搬家的资料暂时无法打开，已保留现有内容。"}

    def search_memory(self, query: str) -> dict:
        if not self._memory_deployment: return {"error": "请先完成这次搬家，再查找旧对话。"}
        try:
            return memory_store.HistoryReader(Path(self._memory_deployment["location"])).search(query)
        except Exception:
            return {"error": "暂时无法查找旧对话，请稍后重试。完整记录仍保留在本机。"}

    def read_memory(self, message_id: str, offset: int = 0) -> dict:
        if not self._memory_deployment: return {"error": "请先完成这次搬家，再查看旧对话。"}
        try:
            return memory_store.HistoryReader(Path(self._memory_deployment["location"])).read(message_id, offset)
        except Exception:
            return {"error": "无法读取这条历史消息。"}

    def open_memory_folder(self) -> dict:
        if not self._memory_deployment: return {"error": "请先完成这次搬家，再打开保存位置。"}
        try:
            open_external(self._memory_deployment.get("archive_location", self._memory_deployment["location"]))
            return {"ok": True}
        except OSError:
            return {"error": "暂时无法打开旧对话的保存位置，请稍后重试。"}

    def open_memory_desktop(self, identity: str = "") -> dict:
        with self._lock:
            if not self._memory_deployment: return {"error": "请先完成历史准备。"}
            if identity and identity != self._memory_deployment["id"]:
                return {"error": "当前查看的对话已切换，请在原记录旁重新打开。"}
            if self._job is not None and not self._job.snapshot()["finished"]:
                return {"error": "请先等待当前任务完成。"}
            try:
                url = memory_deploy.desktop_link(memory_jobs.library(), self._memory_deployment["id"])
                refreshed = copilot_refresh.refresh(passive=True)
                if refreshed in {"busy", "draft"}:
                    return {"ok": True, "pending": True, "refresh_status": refreshed}
                if refreshed == 'permission-required':
                    return {"error": "旧对话已保存。请在 macOS 系统设置中允许工具箱的辅助功能权限，再重试打开 Copilot。"}
                if refreshed not in {"requested", "not-running"}:
                    return {"error": "旧对话已保存，暂时无法安全更新 Copilot 左侧列表。请稍后重试，原记录仍保留。"}
                if refreshed == "requested":
                    time.sleep(1)
                open_external(url)
                return {"ok": True, "refreshed": refreshed == "requested", "refresh_status": refreshed}
            except (OSError, ValueError, sqlite3.Error):
                return {"error": "暂时无法自动打开。请在 Copilot 左侧展开对应项目，找到原名称后带“智能搬家”标识的对话。"}

    def rollback_memory(self) -> dict:
        with self._lock:
            if not self._memory_deployment: return {"error": "当前没有可撤销的搬家记录。"}
            try:
                result = memory_deploy.rollback(memory_jobs.library(), self._memory_deployment["id"])
                self._memory_deployment = None
                self._memory_plan = None
                return result
            except Exception as error:
                return {"error": str(error) if isinstance(error, ValueError) else "无法撤销，请先检查目标项目。"}

    def start_full_from_memory(self, target: str, directory: str) -> dict:
        with self._lock:
            if self._job is not None and not self._job.snapshot()["finished"]:
                return {"error": "请等待当前任务完成。"}
            if target not in mover.TARGETS or not sources.installed(target) or not directory or not Path(directory).is_dir():
                return {"error": "请选择可用的完整迁移目标和文件夹。"}
            try:
                imports.preflight(target, mover.destination_env(target))
                items = self._saved_memory_items()
                if not items: raise ValueError("没有保存的原始档案。")
                if any(i["state"] != "ok" for i in items): raise ValueError("原始记录未能完整保存。")
                documents = []
                for item in items:
                    root = memory_jobs.library() / "bundles" / item["bundle"]
                    data = memory_store.summary(root)
                    original = root / "archive/original.json"
                    if memory_store.digest(original.read_bytes()) != data["sha256"]: raise ValueError("原始档案校验失败。")
                    documents.append({**data, "original": original})
                self._job = mover.DocumentJob(documents, target, directory)
                return {"ok": True, "total": len(documents)}
            except Exception as error:
                return {"error": str(error) if isinstance(error, ValueError) else "完整迁移准备失败，档案已保留。"}

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
        """Open only an allowlisted destination of this batch's saved results."""
        if self._job is None or not isinstance(index, int):
            return {"error": "没有导入结果。"}
        items = self._job.snapshot()["items"]
        if index < 0 or index >= len(items):
            return {"error": "这条记录尚未导入成功。"}
        url = str(items[index].get("openUrl", ""))
        imported = str(items[index].get("importedId", ""))
        copilot = self._job.target == "copilot_desktop" and url == copilot_import.LIST_URL
        state = items[index]["state"]
        if state != "ok" and not (copilot and state == "skipped"):
            return {"error": "这条记录尚未导入成功。"}
        if not copilot and (self._job.target not in ("codex", "chatgpt_work") or not imported or url != f"codex://threads/{imported}" or not mover.SAFE_ID.fullmatch(imported)):
            return {"error": "这个目标不支持直接打开。"}
        try:
            if copilot:
                refreshed = copilot_refresh.refresh()
                if refreshed == "busy":
                    return {"error": "记录已复制。Copilot 正在执行任务，未打断它；任务结束后点「在 Copilot 中查看」即可刷新。"}
                if refreshed == "draft":
                    return {"error": "记录已复制。Copilot 中还有未发送的内容，已保留草稿；处理完草稿后点「在 Copilot 中查看」即可刷新。"}
                if refreshed == "unavailable":
                    return {"error": "记录已复制，但没有完成 Copilot 窗口刷新。请松开快捷键并打开 Copilot，再点「在 Copilot 中查看」重试。"}
                if refreshed == 'permission-required':
                    return {"error": "记录已复制。请在 macOS 系统设置中允许工具箱的辅助功能权限，再点「在 Copilot 中查看」。"}
                if refreshed == "requested":
                    # Let the reload initialize before dispatching navigation.
                    # Reload invalidates both the sidebar and Recent caches.
                    time.sleep(1)
            open_external(url)
        except (OSError, subprocess.SubprocessError) as error:
            mover.log(f"open_in_app {url}: {error!r}")
            return {"error": "无法打开 Copilot 的会话列表，请在 Copilot 用户菜单选择 Manage sessions（管理会话）。" if copilot else "没有找到可以打开它的软件，请先安装并启动 ChatGPT。"}
        return {"ok": True, "refreshed": refreshed == "requested"} if copilot else {"ok": True}

    def move_status(self) -> dict:
        if self._job is None:
            return {"finished": True, "total": 0, "done": 0, "ok": 0, "skipped": 0, "failed": 0, "items": []}
        return self._job.snapshot()


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--codex-import-self-test":
        from core.codex_audit import run
        raise SystemExit(run(Path(sys.argv[2]).resolve()))
    if len(sys.argv) == 3 and sys.argv[1] == "--memory-self-test":
        from core.memory_audit import run
        raise SystemExit(run(Path(sys.argv[2]).resolve()))
    if sys.platform == "win32" and len(sys.argv) == 3 and sys.argv[1] == "--copilot-refresh-self-test":
        from core.copilot_refresh_audit import run
        raise SystemExit(run(Path(sys.argv[2]).resolve()))
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
