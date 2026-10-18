"""Destination capabilities and registration of imported local sessions."""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path

from .common import norm


TARGETS = {
    "copilot_desktop": {"harness": "copilot_local", "mode": "local", "targetSub": "桌面端 · 本机聊天",
        "notice": "复制到 Copilot Desktop 的聊天列表。图片作为附件，操作过程折叠保存，不重新执行原工具。旧格式记录可重新复制一次，旧副本保留。",
        "folderHint": "选择继续使用这条聊天时的工作文件夹；记录加入 Copilot 的 Chats，不新建项目或复制项目文件。",
        "resultHint": ("完成后自动刷新并打开 Copilot，最新复制的记录显示在 Chats（聊天）顶部。有进行中的任务或未发送草稿时暂缓刷新，处理完后可点下方按钮查看。" if sys.platform == "win32" else "记录在 Copilot 的 Chats（聊天）中；若仍是旧列表，在任务结束后完全退出 Copilot 再打开。") + "旧格式副本不会被覆盖。"},
    "cursor_desktop": {"harness": "cursor_desktop", "mode": "history", "resultHint": "打开对应文件夹的 Cursor，等待历史列表刷新。"},
    "workbuddy": {"harness": "workbuddy", "mode": "history", "resultHint": "已复制到 WorkBuddy 的本机历史。请在对应文件夹下确认记录是否显示；刷新方式取决于软件版本。"},
    "workbuddy_ai": {"harness": "workbuddy_ai", "mode": "history", "resultHint": "在 WorkBuddy AI 的对应文件夹下查看；未刷新时重新打开 WorkBuddy AI。"},
    "qwen_work": {"harness": "qwen_work", "mode": "history", "resultHint": "已登记千问办公的项目、任务和正文。千问办公不会自己发现新记录：请把它完全退出（托盘里也要退出）再重新打开，在对应项目下查看。"},
    "claude_code": {"harness": "claude_code", "mode": "cli", "resultHint": "在所选文件夹启动 Claude Code，用下方续聊命令打开导入记录。"},
    "cowork": {"harness": "cowork", "mode": "local", "targetSub": "本机 Cowork 任务", "notice": "仅导入已初始化的本机 Cowork 账户；不写入云端任务。", "resultHint": "已写入本机 Cowork 会话。重新打开 Claude 的 Cowork 查看，工作环境与附件不会一并迁移。"},
    "antigravity": {"harness": "antigravity", "mode": "local", "notice": "写入 Antigravity 桌面端本机历史文件；窗口是否重新索引取决于该版本，不保证自动显示或续聊。", "resultHint": "已写入桌面端专属历史目录，不会写到命令行版本。"},
    "antigravity_cli": {"harness": "antigravity", "mode": "cli", "resultHint": "已写入 Antigravity 命令行专属历史，用下方续聊命令打开。"},
    "cursor_cli": {"harness": "cursor", "mode": "cli", "resultHint": "已写入 Cursor 命令行历史，与 Cursor 桌面版的列表不同。用下方续聊命令打开。"},
    "grok": {"harness": "grok", "mode": "cli", "resultHint": "在所选文件夹启动 Grok，用下方续聊命令打开。"},
    "opencode": {"harness": "opencode", "mode": "cli", "resultHint": "已通过 OpenCode 自带导入功能登记。用下方续聊命令打开。"},
    "codex": {
        "harness": "codex", "mode": "cli", "targetSub": "本机 Codex · 可搬入",
        "notice": "写入 ChatGPT 的本机 Codex 历史和项目登记，不写入云端聊天。不会启动模型或改变现有权限设置。",
        "resultHint": "已写入本机 Codex 历史并登记项目。会请求 ChatGPT 打开最后一条，请在软件中确认是否显示；也可以使用下方打开记录命令。",
    },
    "chatgpt_work": {
        "harness": "codex", "mode": "local", "targetSub": "本机 Work · 可搬入",
        "notice": "写入 ChatGPT 的本机 Work 历史，保留 Work 模式标记并登记所选目录；不是云端 Work。不会启动模型或复制附件、运行环境。",
        "resultHint": "已写入本机 Work 历史并登记项目。会请求 ChatGPT 打开最后一条，请在软件中确认是否显示。工作环境与附件需另行准备。",
    },
}

READ_ONLY = {
    "chatgpt": "仅云端 Chat / Work 不能搬入；上方本机 Work 和 Codex 可以搬入",
    "claude_desktop": "仅普通云端聊天不能搬入；上方本机 Cowork 和 Claude Code 可以搬入",
    "hermes": "当前 txcript 的 Hermes 适配仅支持读取，没有写入实现",
    "doubao_work": "豆包的对话保存在豆包服务器上，本机写入的记录它不会显示；只能从豆包搬出到别的软件",
}

for capability in TARGETS.values():
    capability["folders"] = True
    capability.setdefault("folderHint", "此文件夹作为导入记录的工作目录；不会复制项目文件或附件。")


QWEN_COLUMNS = {
    "projects": {"id", "name", "path", "created_at", "updated_at"},
    "local_projects": {"id", "name", "root_paths", "created_at", "updated_at", "deleted_at"},
    "chats": {"id", "name", "project_id", "local_project_id", "chat_type", "worktree_path", "output_directory", "created_at", "updated_at", "ext"},
    "sub_chats": {"id", "chat_id", "session_id", "messages", "created_at", "updated_at"},
    "messages": {"id", "message_id", "chat_id", "sub_chat_id", "sequence", "role", "parts", "metadata", "searchable_text", "created_at", "updated_at"},
}


def has_conversation_body(document: dict) -> bool:
    for message in document.get("messages", []):
        if message.get("role") not in ("user", "assistant"):
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return True
        if isinstance(content, list):
            for part in content:
                if part.get("type") in ("text", "thinking") and str(part.get("text") or part.get("thinking") or "").strip():
                    return True
                if part.get("type") in ("image", "artifact"):
                    return True
    return False


def qwen_db(env: dict) -> Path:
    return Path(env["APPDATA"]) / "QwenWorkCN" / "data" / "agents.db"


def validate_qwen(database: Path) -> None:
    if not database.is_file():
        raise ValueError("请先打开千问办公并创建一条本机任务，初始化数据后再搬入。")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        for table, required in QWEN_COLUMNS.items():
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if not required <= columns:
                raise ValueError("千问办公的数据格式发生变化，已停止导入，未修改原有记录。")


def preflight(target: str, env: dict) -> None:
    if target == "copilot_desktop":
        from . import copilot_import

        copilot_import.validate(Path(env["COPILOT_HOME"]))
    if target in ("codex", "chatgpt_work"):
        from . import codex_import

        codex_import.validate(Path(env["CODEX_HOME"]) / "state_5.sqlite")
    if target == "qwen_work":
        validate_qwen(qwen_db(env))
    if target == "cowork":
        root = Path(env.get("COWORK_SESSIONS_DIR", ""))
        initialized = False
        if root.is_dir():
            for organization in root.iterdir():
                if not organization.is_dir():
                    continue
                try:
                    uuid.UUID(organization.name)
                except ValueError:
                    continue
                for account in organization.iterdir():
                    try:
                        uuid.UUID(account.name)
                    except ValueError:
                        continue
                    initialized |= account.is_dir()
        if not initialized:
            raise ValueError("请先在 Claude 的 Cowork 中创建一条本机任务，初始化账户后再搬入。")


def _qwen_messages(path: Path, session_id: str) -> list[dict]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tools = {}
    messages = []
    for record in records:
        role = record.get("type")
        if role not in ("user", "assistant"):
            continue
        raw = record.get("message", {}).get("content", [])
        if isinstance(raw, str):
            raw = [{"type": "text", "text": raw}]
        parts = []
        for part in raw:
            kind = part.get("type")
            if kind == "text":
                parts.append({"type": "text", "text": part.get("text", "")})
            elif kind == "thinking":
                parts.append({"type": "text", "text": part.get("thinking", "")})
            elif kind == "tool_use":
                tool = {"type": "tool-" + str(part.get("name", "tool")), "toolName": part.get("name", "tool"),
                        "toolCallId": part["id"], "input": part.get("input"), "state": "input-available"}
                tools[part["id"]] = tool
                parts.append(tool)
            elif kind == "tool_result":
                tool = tools.get(part.get("tool_use_id"))
                if tool is not None:
                    tool["state"] = "output-error" if part.get("is_error") else "output-available"
                    tool["output"] = part.get("content")
                    if part.get("is_error"):
                        tool["errorText"] = str(part.get("content", ""))
                else:
                    parts.append({"type": "text", "text": str(part.get("content", ""))})
        if not parts:
            continue
        message_id = record.get("uuid") or str(uuid.uuid4())
        messages.append({"id": message_id, "role": role, "parts": parts,
                         "metadata": {"source": "txcript-import", "sessionId": session_id,
                                      "sdkMessageUuid": message_id, "sdkMessageUuids": [message_id], "status": "completed"}})
    return messages


def _save_setting(connection, key: str, value: dict, stamp: int) -> None:
    connection.execute("UPDATE app_settings SET value=?,updated_at=? WHERE key=?", (json.dumps(value), stamp, key))


def _place_qwen_task(connection, project_id: str, chat_id: str, stamp: int) -> None:
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'").fetchone():
        return
    row = connection.execute("SELECT value FROM app_settings WHERE key='sidebarTaskLayout'").fetchone()
    if row:
        layout = json.loads(row[0])
        if layout.get("schemaVersion") == 2 and layout.get("preferences", {}).get("projects") == "manual":
            orders = layout.setdefault("orders", {}).setdefault("projects", {})
            orders[project_id] = [chat_id, *orders.get(project_id, [])]
            layout["revision"] = layout.get("revision", 0) + 1
            _save_setting(connection, "sidebarTaskLayout", layout, stamp)
    row = connection.execute("SELECT value FROM app_settings WHERE key='sidebarProjectOrder'").fetchone()
    if row:
        order = json.loads(row[0])
        if order.get("schemaVersion") == 1 and project_id not in order.get("projectIds", []):
            order["projectIds"] = [project_id, *order.get("projectIds", [])]
            order["revision"] = order.get("revision", 0) + 1
            _save_setting(connection, "sidebarProjectOrder", order, stamp)


def register_qwen(path: Path, session_id: str, document: dict, env: dict) -> None:
    database = qwen_db(env)
    validate_qwen(database)
    messages = _qwen_messages(path, session_id)
    if not messages:
        raise ValueError("千问导入记录没有可显示的正文，已停止登记。")
    directory = str(document["cwd"])
    stamp = int(time.time() * 1000)
    title = document.get("title") or "导入的对话"
    backup = Path(env["APPDATA"]) / "对话搬家" / "backups" / f"qwen-{uuid.uuid4()}.db"
    backup.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database, timeout=10)) as connection, connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with closing(sqlite3.connect(backup)) as copied:
            connection.backup(copied)
        connection.execute("BEGIN IMMEDIATE")
        project_id = next((row[0] for row in connection.execute("SELECT id,path FROM projects") if norm(row[1]) == norm(directory)), None)
        if project_id is None:
            project_id = str(uuid.uuid4())
            connection.execute("INSERT INTO projects(id,name,path,created_at,updated_at) VALUES(?,?,?,?,?)", (project_id, Path(directory).name, directory, stamp, stamp))
        local_id = None
        for row in connection.execute("SELECT id,root_paths FROM local_projects WHERE deleted_at IS NULL"):
            if any(norm(root) == norm(directory) for root in json.loads(row[1])):
                local_id = row[0]
                break
        if local_id is None:
            local_id = str(uuid.uuid4())
            connection.execute("INSERT INTO local_projects(id,name,root_paths,created_at,updated_at) VALUES(?,?,?,?,?)", (local_id, Path(directory).name, json.dumps([directory]), stamp, stamp))
        chat_id, sub_id = str(uuid.uuid4()), str(uuid.uuid4())
        connection.execute("INSERT INTO chats(id,name,project_id,local_project_id,chat_type,worktree_path,output_directory,created_at,updated_at,ext) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (chat_id, title, project_id, local_id, "task", directory, directory, stamp, stamp, "{}"))
        connection.execute("INSERT INTO sub_chats(id,chat_id,session_id,messages,created_at,updated_at) VALUES(?,?,?,?,?,?)", (sub_id, chat_id, session_id, "[]", stamp, stamp))
        for sequence, message in enumerate(messages):
            connection.execute("INSERT INTO messages(id,message_id,chat_id,sub_chat_id,sequence,role,parts,metadata,searchable_text,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (str(uuid.uuid4()), message["id"], chat_id, sub_id, sequence, message["role"], json.dumps(message["parts"], ensure_ascii=False), json.dumps(message["metadata"]),
                                "\n".join(part.get("text", "") for part in message["parts"]), stamp, stamp))
        _place_qwen_task(connection, local_id, chat_id, stamp)
