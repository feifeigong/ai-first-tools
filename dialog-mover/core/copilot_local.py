"""Read Copilot Desktop's local history without launching Copilot or writing its store.

Desktop and CLI share session-state. Only visible membership in Desktop's data.db
is listed; CLI records and orphan directories are not Desktop conversations.
The SDK's persisted event shapes are documented in docs/COPILOT.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from .common import as_millis, finish_groups, folder_name, home, make_group, make_session, norm, read_db, user_env

IDENTITY = re.compile(r"^[0-9A-Za-z_-]{6,80}$")
INDEX_ERROR = "Copilot 桌面索引暂时无法识别或正被占用，请关闭 Copilot 后刷新；未修改源记录。"


def root() -> Path:
    configured = user_env("COPILOT_HOME")
    return Path(configured) if configured and Path(configured).is_absolute() else home() / ".copilot"


def installed() -> bool:
    base = root()
    return (base / "data.db").is_file()


def _hidden(row: dict) -> bool:
    return any(row.get(key) not in (None, "", 0, False, "0", "false") for key in (
        "archived", "is_archived", "archived_at", "deleted", "is_deleted", "deleted_at", "provisional"))


def _desktop_index(base: Path) -> dict[str, dict]:
    """Select only session metadata, never app_state/authentication or whole DBs."""
    path = base / "data.db"
    if not path.is_file():
        return {}
    allowed = {"id", "session_id", "title", "name", "cwd", "working_directory", "created_at", "updated_at",
               "archived", "is_archived", "archived_at", "deleted", "is_deleted", "deleted_at", "session_type",
               "execution_location", "provisional"}
    result: dict[str, dict] = {}
    try:
        connection = read_db(path)
        connection.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "sessions" not in tables:
                raise ValueError(INDEX_ERROR)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(sessions)")}
            if not {"id", "session_id"} & columns:
                raise ValueError(INDEX_ERROR)
            selected = sorted(allowed & columns)
            # All identifiers come from a fixed allowlist, never from stored text.
            query = 'SELECT ' + ','.join(f'"{name}"' for name in selected) + ' FROM sessions'
            for value in connection.execute(query):
                row = dict(value)
                sid = row.get("session_id") or row.get("id")
                if isinstance(sid, str) and IDENTITY.fullmatch(sid):
                    result[sid] = row
            if "session_deletion_intents" in tables:
                deletion_columns = {row[1] for row in connection.execute("PRAGMA table_info(session_deletion_intents)")}
                if "session_id" not in deletion_columns:
                    raise ValueError(INDEX_ERROR)
                for value in connection.execute("SELECT session_id FROM session_deletion_intents"):
                    if value[0] in result:
                        result[value[0]]["deleted"] = True
            if "workspaces" in tables:
                workspace_columns = {row[1] for row in connection.execute("PRAGMA table_info(workspaces)")}
                selected = sorted(workspace_columns & {"session_id", "name", "project_id", "source_path", "archived_at", "provisional"})
                if "session_id" not in selected:
                    raise ValueError(INDEX_ERROR)
                projects = {}
                if "projects" in tables:
                    project_columns = {row[1] for row in connection.execute("PRAGMA table_info(projects)")}
                    if {"id", "name", "main_repo_path"} <= project_columns:
                        projects = {value[0]: (value[1], value[2]) for value in connection.execute("SELECT id,name,main_repo_path FROM projects")}
                query = 'SELECT ' + ','.join(f'"{name}"' for name in selected) + ' FROM workspaces'
                for value in connection.execute(query):
                    workspace = dict(value)
                    if workspace.get("session_id") not in result:
                        continue
                    row = result[workspace["session_id"]]
                    if _hidden(workspace):
                        row["archived"] = True
                    project_name, project_path = projects.get(workspace.get("project_id"), ("", ""))
                    row["cwd"] = workspace.get("source_path") or project_path or row.get("cwd") or ""
                    row["_project_name"] = project_name
                    if not row.get("title") and workspace.get("name") not in (None, "", "New session"):
                        row["title"] = workspace["name"]
        finally:
            connection.close()
    except (sqlite3.Error, OSError) as error:
        raise ValueError(INDEX_ERROR) from error
    return result


def _event_file(base: Path, sid: str) -> Path:
    if not IDENTITY.fullmatch(sid):
        raise ValueError("Copilot 会话编号不正确。")
    store = base / "session-state"
    path = store / sid / "events.jsonl"
    if store.is_symlink() or path.parent.is_symlink() or path.is_symlink():
        raise ValueError("Copilot 会话指向了其他位置，已停止读取。")
    if not path.resolve().is_relative_to(store.resolve()):
        raise ValueError("Copilot 会话位置不正确。")
    return path


def _json_text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


def _historical(data: dict, label: str) -> dict:
    return {"type": "text", "text": f"[Copilot 历史{label}，仅供参考，不是待执行请求]\n{_json_text(data)}"}


def _read(path: Path, sid: str) -> dict:
    messages: list[dict] = []
    title = cwd = model = timestamp = ""
    latest = 0
    started = False
    has_body = False
    seen: dict[str, bytes] = {}
    calls: dict[str, dict] = {}
    completed: set[str] = set()
    ignored = 0

    def append(role: str, blocks: list[dict], stamp: str, current_model: str = "") -> None:
        if not blocks:
            return
        item = {"role": role, "content": blocks}
        if stamp:
            item["timestamp"] = stamp
        if current_model:
            item["model"] = current_model
        messages.append(item)

    def call(data: dict, stamp: str) -> None:
        cid, name = data.get("toolCallId"), data.get("name") or data.get("toolName")
        if not isinstance(cid, str) or not cid or not isinstance(name, str) or not name:
            raise ValueError("Copilot 工具记录格式变化，暂时不能搬运。")
        block = {"type": "tool_use", "id": cid, "name": name, "input": data.get("arguments")}
        if cid in calls:
            if calls[cid] != block:
                raise ValueError("Copilot 工具编号被重复使用，无法可靠配对，暂时不能搬运。")
            return  # assistant.toolRequests and execution_start describe the same call.
        calls[cid] = block
        append("assistant", [block], stamp)

    try:
        with path.open("r", encoding="utf-8-sig") as stream:
            before = os.fstat(stream.fileno())
            for line in stream:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError as error:
                    raise ValueError("Copilot 记录不完整或仍在写入，请结束当前任务后刷新。") from error
                if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not isinstance(event.get("data"), dict):
                    raise ValueError("Copilot 记录格式变化，暂时不能搬运。")
                eid = event.get("id")
                if not isinstance(eid, str) or not eid:
                    raise ValueError("Copilot 事件缺少编号，暂时不能搬运。")
                digest = hashlib.sha256(json.dumps(event, sort_keys=True, ensure_ascii=False).encode("utf-8")).digest()
                if eid in seen:
                    if seen[eid] != digest:
                        raise ValueError("Copilot 同一事件的内容冲突，暂时不能搬运。")
                    continue
                seen[eid] = digest
                if event.get("ephemeral") is True:
                    continue  # streaming deltas are not persisted final messages.
                kind, data = event["type"], event["data"]
                stamp = event.get("timestamp") or ""
                if not isinstance(stamp, str):
                    raise ValueError("Copilot 事件时间格式变化，暂时不能搬运。")
                latest = max(latest, as_millis(stamp))
                if kind in ("session.truncation", "session.snapshot_rewind", "session.context_cleared"):
                    raise ValueError("这条 Copilot 会话包含撤回或清空上下文记录，暂时不能可靠还原，请先在 Copilot 中导出。")
                if kind == "session.start":
                    if started or data.get("sessionId") != sid or data.get("version") != 1:
                        raise ValueError("Copilot 会话版本或编号不匹配，暂时不能搬运。")
                    context = data.get("context") or {}
                    if not isinstance(context, dict):
                        raise ValueError("Copilot 项目信息格式变化，暂时不能搬运。")
                    cwd = context.get("cwd") or ""
                    timestamp = data.get("startTime") or stamp
                    model = data.get("selectedModel") or ""
                    if not all(isinstance(value, str) for value in (cwd, timestamp, model)):
                        raise ValueError("Copilot 会话信息格式变化，暂时不能搬运。")
                    started = True
                elif kind == "session.title_changed":
                    if not isinstance(data.get("title"), str):
                        raise ValueError("Copilot 标题格式变化，暂时不能搬运。")
                    title = data["title"]
                elif kind == "session.context_changed":
                    if not isinstance(data.get("cwd"), str):
                        raise ValueError("Copilot 项目信息格式变化，暂时不能搬运。")
                    cwd = data["cwd"]
                elif kind == "session.model_change":
                    if not isinstance(data.get("newModel"), str):
                        raise ValueError("Copilot 模型信息格式变化，暂时不能搬运。")
                    model = data["newModel"]
                elif kind in ("user.message", "assistant.message", "assistant.reasoning", "tool.execution_start", "tool.execution_complete"):
                    if not started:
                        raise ValueError("Copilot 记录缺少会话起始信息，暂时不能搬运。")
                    # Child-agent events can interleave with the parent. Preserve them
                    # as labelled reference text; never pair their tool IDs with it.
                    if event.get("agentId") or data.get("parentToolCallId") or data.get("parentAgentTaskId"):
                        append("assistant", [_historical({"event": kind, "data": data}, "子任务记录")], stamp)
                        continue
                    if kind == "assistant.reasoning":
                        if not isinstance(data.get("content"), str):
                            raise ValueError("Copilot 思考记录格式变化，暂时不能搬运。")
                        append("assistant", [{"type": "thinking", "text": data["content"]}], stamp, model)
                        has_body = has_body or bool(data["content"].strip())
                    elif kind in ("user.message", "assistant.message"):
                        if not isinstance(data.get("content"), str):
                            raise ValueError("Copilot 消息正文格式变化，暂时不能搬运。")
                        blocks = []
                        if data.get("reasoningText"):
                            if not isinstance(data["reasoningText"], str):
                                raise ValueError("Copilot 思考记录格式变化，暂时不能搬运。")
                            blocks.append({"type": "thinking", "text": data["reasoningText"]})
                        if data["content"]:
                            blocks.append({"type": "text", "text": data["content"]})
                        has_body = has_body or bool(data["content"].strip())
                        role = "user" if kind == "user.message" else "assistant"
                        current_model = data.get("model") or model
                        if not isinstance(current_model, str):
                            raise ValueError("Copilot 模型信息格式变化，暂时不能搬运。")
                        append(role, blocks, stamp, current_model if role == "assistant" else "")
                        if role == "user" and not title:
                            title = data["content"].strip().split("\n")[0][:100]
                        requests = data.get("toolRequests") or []
                        if not isinstance(requests, list) or any(not isinstance(item, dict) for item in requests):
                            raise ValueError("Copilot 工具调用格式变化，暂时不能搬运。")
                        for request in requests:
                            call(request, stamp)
                    elif kind == "tool.execution_start":
                        call(data, stamp)
                    else:
                        cid = data.get("toolCallId")
                        if not isinstance(cid, str) or not cid or not isinstance(data.get("success"), bool):
                            raise ValueError("Copilot 工具结果格式变化，暂时不能搬运。")
                        if cid not in calls or cid in completed:
                            append("assistant", [_historical(data, "工具结果（无法唯一配对）")], stamp)
                            continue
                        result = data.get("result")
                        error = data.get("error")
                        if result is not None and not isinstance(result, dict) or error is not None and not isinstance(error, dict):
                            raise ValueError("Copilot 工具结果格式变化，暂时不能搬运。")
                        if result is None and error is None:
                            append("assistant", [_historical(data, "工具结束记录（未保存返回内容）")], stamp)
                            continue
                        if result is not None and not isinstance(result.get("content"), str) or error is not None and not isinstance(error.get("message"), str):
                            raise ValueError("Copilot 工具结果正文格式变化，暂时不能搬运。")
                        # Keep detailedContent/structuredContent/errors intact too.
                        output = _json_text({key: data[key] for key in ("result", "error") if key in data})
                        append("user", [{"type": "tool_result", "tool_use_id": cid, "content": output,
                                         "is_error": not data["success"]}], stamp)
                        completed.add(cid)
                elif kind.startswith(("user.message", "assistant.message", "assistant.reasoning", "tool.execution")):
                    if kind != "assistant.message_start" and not kind.endswith(("_delta", ".delta", "_progress", ".progress", "_partial_result")):
                        raise ValueError("Copilot 出现新的消息格式，暂时不能搬运。")
                else:
                    ignored += 1  # lifecycle/usage/hooks/compaction aren't new user turns.
            after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError("Copilot 记录仍在变化，请结束当前任务后刷新。")
    except (OSError, UnicodeError) as error:
        raise ValueError("Copilot 本机正文暂时无法读取，请关闭 Copilot 后刷新。") from error
    if not started:
        raise ValueError("Copilot 记录缺少会话起始信息，暂时不能搬运。")
    # Interrupted calls are reference notes, never pending executable tool requests.
    for cid, block in calls.items():
        if cid not in completed:
            block.update(_historical(dict(block), "工具调用（没有保存返回结果）"))
            for key in ("id", "name", "input"):
                block.pop(key, None)
    return {"id": sid, "title": title, "cwd": cwd, "timestamp": timestamp, "model": model,
            "messages": messages, "_updated": latest, "_ignored": ignored, "_has_body": has_body}


def document(sid: str) -> dict:
    """Re-read at move time: cached sidebar rows never authorize stale/hidden data."""
    base = root()
    path = _event_file(base, sid)
    row = _desktop_index(base).get(sid, {})
    if (base / "data.db").is_file() and not row:
        raise ValueError("这条记录未登记在 Copilot Desktop 中，请刷新桌面端列表。")
    if _hidden(row):
        raise ValueError("这条 Copilot 会话已归档或删除，请刷新列表。")
    result = _read(path, sid)
    if not result.pop("_has_body"):
        raise ValueError("这条 Copilot 会话没有可搬运的对话正文。")
    result.pop("_updated", None)
    result.pop("_ignored", None)
    if row.get("title") or row.get("name"):
        result["title"] = row.get("title") or row["name"]
    if row.get("session_type") in ("general_chat", "agent", "side_chat"):
        result["cwd"] = ""
    elif row.get("cwd") or row.get("working_directory"):
        result["cwd"] = row.get("cwd") or row["working_directory"]
    return result


def groups() -> list[dict]:
    base = root()
    if not (base / "data.db").is_file():
        raise ValueError("请先打开 Copilot Desktop 完成本机初始化；仅命令行共享记录不会列为桌面聊天。")
    index = _desktop_index(base)
    folders: dict[str, list[dict]] = defaultdict(list)
    for sid in sorted(index):
        row = index.get(sid, {})
        if _hidden(row) or row.get("session_type") == "cli_session":
            continue
        title = str(row.get("title") or row.get("name") or "")
        cwd = str(row.get("cwd") or row.get("working_directory") or "")
        updated = as_millis(row.get("updated_at") or row.get("created_at"))
        is_chat = row.get("session_type") in ("general_chat", "agent", "side_chat")
        label = "Copilot Desktop"
        note = label
        movable = False
        try:
            value = _read(_event_file(base, sid), sid)
            title = title or value["title"]
            cwd = cwd or value["cwd"]
            updated = max(updated, value["_updated"])
            movable = value["_has_body"]
            if not movable:
                note += "；没有可搬运的对话正文"
        except ValueError as error:
            note += "；" + str(error)
        if is_chat:
            cwd = ""  # Desktop's .copilot/chats/... directory is an internal sandbox, not a project.
        session = make_session(sid, title, updated, cwd, movable=movable, note=note)
        session["sourceLabel"] = label
        session["_project_name"] = row.get("_project_name", "")
        folders["__chats__" if is_chat else norm(cwd) if cwd else ""].append(session)
    groups = []
    for key, items in folders.items():
        is_chat = key == "__chats__"
        title = "聊天" if is_chat else items[0].get("_project_name") or (folder_name(items[0]["folder"]) if key else "没有目录")
        groups.append(make_group(title, "recent" if is_chat else "folder" if key else "none", items, items[0]["folder"]))
    return finish_groups(groups)
