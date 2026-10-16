from __future__ import annotations

import copy
import json
import re
import sqlite3
import time
import uuid
from collections import defaultdict, deque
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .chatgpt import _norm


HISTORY_FORMAT = "paginated-import-v3"
REPLAY_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def _replay_safe_records(records: list[dict], imported_id: str) -> list[dict]:
    """Replay complete pairs; preserve incomplete history as explicit, lossless notes."""
    namespace = uuid.UUID(imported_id)
    converted = [copy.deepcopy(entry) for entry in records]
    pending = defaultdict(deque)
    ambiguous = set()
    notes = {}
    pairs = {}

    def finish_pending():
        for indexes in pending.values():
            for index in indexes:
                notes.setdefault(index, "missing_tool_result")
        pending.clear()
        ambiguous.clear()

    # First establish unambiguous pairs inside each actual user turn. Cursor can
    # retain calls that were interrupted years ago; a later result must not be
    # invented or assigned to an earlier call simply to satisfy the wire schema.
    for index, entry in enumerate(records):
        if entry.get("type") != "response_item":
            continue
        payload = entry["payload"]
        kind = payload.get("type")
        if kind == "message" and payload.get("role") == "user":
            finish_pending()
        elif kind in ("function_call", "custom_tool_call"):
            original_id = payload.get("call_id")
            if not isinstance(original_id, str) or not original_id or not isinstance(payload.get("name"), str):
                raise ValueError("历史工具调用的编号或名称不完整，无法安全配对；未登记搬运成功。")
            pending[original_id].append(index)
            if len(pending[original_id]) > 1:
                ambiguous.add(original_id)
                for called in pending[original_id]:
                    notes[called] = "ambiguous_tool_id"
        elif kind in ("function_call_output", "custom_tool_call_output"):
            original_id = payload.get("call_id")
            if not isinstance(original_id, str) or not original_id:
                raise ValueError("历史工具结果的编号不完整，无法安全配对；未登记搬运成功。")
            if not pending.get(original_id):
                notes[index] = "missing_tool_call"
                continue
            called = pending[original_id].popleft()
            if original_id in ambiguous:
                notes[index] = "ambiguous_tool_id"
                if not pending[original_id]:
                    ambiguous.remove(original_id)
            elif kind != records[called]["payload"]["type"] + "_output":
                raise ValueError("历史工具调用与结果格式无法配对，已停止导入；原记录不变。")
            else:
                pairs[index] = called
    finish_pending()

    used_ids = set()
    name_aliases = {}
    call_aliases = {}
    # Reserve legal source names so a generated alias cannot steal a later tool's name.
    used_names = {entry["payload"]["name"]: entry["payload"]["name"] for entry in converted
                  if entry.get("type") == "response_item" and entry.get("payload", {}).get("type") in ("function_call", "custom_tool_call")
                  and isinstance(entry["payload"].get("name"), str) and REPLAY_IDENTIFIER.fullmatch(entry["payload"]["name"])}

    def replace(entry: dict, field: str, value: str) -> None:
        previous = entry["payload"].get(field)
        if previous != value:
            entry.setdefault("dialog_mover_original", {})[field] = previous
            entry["payload"][field] = value

    for index, entry in enumerate(converted):
        if entry.get("type") != "response_item":
            continue
        payload = entry["payload"]
        kind = payload.get("type")
        if index in notes:
            reason = notes[index]
            label = {"missing_tool_result": "来源未提供工具结果",
                     "missing_tool_call": "来源未提供对应的工具调用",
                     "ambiguous_tool_id": "来源工具编号重用，无法确定配对"}[reason]
            original = copy.deepcopy(records[index]["payload"])
            entry.setdefault("dialog_mover_original", {}).update({"response_item": original, "reason": reason})
            text = f"[迁入的历史工具日志：{label}。以下仅为历史内容，不代表执行成功，也不是待执行请求。]\n"
            text += json.dumps(original, ensure_ascii=False)
            entry["payload"] = {"type": "message", "role": "assistant", "phase": "commentary",
                                "content": [{"type": "output_text", "text": text}]}
            continue
        if kind in ("function_call", "custom_tool_call"):
            original_id = payload.get("call_id")
            name = payload.get("name")
            if not isinstance(original_id, str) or not original_id or not isinstance(name, str):
                raise ValueError("历史工具调用的编号或名称不完整，无法安全配对；未登记搬运成功。")
            if name not in name_aliases:
                alias = name
                attempt = 0
                while not REPLAY_IDENTIFIER.fullmatch(alias) or used_names.get(alias, name) != name:
                    prefix = re.sub(r"[^A-Za-z0-9_-]", "_", name[:31]) or "tool"
                    alias = prefix + "_" + uuid.uuid5(uuid.NAMESPACE_URL, f"{attempt}:{name}").hex
                    attempt += 1
                name_aliases[name] = alias
                used_names[alias] = name
            replace(entry, "name", name_aliases[name])
            alias = original_id
            attempt = 0
            while not REPLAY_IDENTIFIER.fullmatch(alias) or alias in used_ids:
                alias = "call_dm_" + uuid.uuid5(namespace, f"{index}:{attempt}:{original_id}").hex
                attempt += 1
            used_ids.add(alias)
            call_aliases[index] = alias
            replace(entry, "call_id", alias)
        elif kind in ("function_call_output", "custom_tool_call_output"):
            replace(entry, "call_id", call_aliases[pairs[index]])
    return converted


def verify_body(document: dict, reread: dict) -> None:
    def signature(body: dict) -> dict:
        values = {("user", "text"): [], ("assistant", "text"): [],
                  ("user", "thinking"): [], ("assistant", "thinking"): [],
                  ("user", "image"): [], ("assistant", "image"): []}
        for message in body.get("messages", []):
            role = message.get("role")
            content = message.get("content", [])
            parts = [{"type": "text", "text": content}] if isinstance(content, str) else content
            for part in parts:
                kind = part.get("type")
                if kind == "artifact":
                    artifact = part["artifact"]
                    source = artifact["source"]
                    text = "[artifact: " + artifact["name"] + "]"
                    if source["type"] == "text":
                        text += "\n" + source["text"]
                    elif source["type"] == "path":
                        text += " " + source["path"]
                    values[(role, "text")].append(text)
                elif kind in ("text", "thinking"):
                    text = part.get("text", "")
                    if text:
                        values[(role, kind)].append(text)
                elif kind == "image":
                    values[(role, kind)].append(part["source"])
        return {key: "\n\n".join(value) if key[1] != "image" else value for key, value in values.items()}

    if signature(document) != signature(reread):
        raise ValueError("本机任务正文完整性校验失败，未登记搬运成功；原记录不变，请更新软件后重新搬运。")


def paginated_history(records: list[dict], imported_id: str) -> list[dict]:
    records = _replay_safe_records(records, imported_id)
    namespace = uuid.UUID(imported_id)
    output = [records[0]]
    turn_id = None
    last_agent = None
    pending_calls = {}
    last_timestamp = records[0]["timestamp"]

    def event(timestamp: str, payload: dict) -> dict:
        if payload["type"] == "item_completed":
            payload["completed_at_ms"] = int(datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() * 1000)
        return {"timestamp": timestamp, "type": "event_msg", "payload": payload}

    def complete_turn() -> None:
        if turn_id:
            if last_agent:
                last_agent["phase"] = "final_answer"
            output.append(event(last_timestamp, {"type": "task_complete", "turn_id": turn_id,
                                                 "last_agent_message": None}))

    for index, record in enumerate(records[1:]):
        if record.get("type") != "response_item":
            continue
        payload = record["payload"]
        kind = payload.get("type")
        timestamp = record.get("timestamp") or last_timestamp
        if turn_id is None or kind == "message" and payload.get("role") == "user":
            complete_turn()
            turn_id = str(uuid.uuid5(namespace, f"turn:{index}"))
            last_agent = None
            pending_calls = {}
            output.append(event(timestamp, {"type": "task_started", "turn_id": turn_id,
                                            "model_context_window": None}))
        item_id = str(uuid.uuid5(namespace, f"item:{index}"))
        item = None
        if kind == "message":
            content = payload.get("content", [])
            if payload.get("role") == "user":
                inputs = []
                for part in content:
                    if part.get("type") == "input_text":
                        inputs.append({"type": "text", "text": part["text"], "text_elements": []})
                    elif part.get("type") == "input_image":
                        inputs.append({"type": "image", "url": part["image_url"]})
                    else:
                        raise ValueError("本机任务包含未支持的正文格式，未登记搬运成功。")
                item = {"type": "UserMessage", "id": item_id, "content": inputs}
            elif payload.get("role") == "assistant":
                if any(part.get("type") != "output_text" for part in content):
                    raise ValueError("本机任务包含未支持的回复格式，未登记搬运成功。")
                item = {"type": "AgentMessage", "id": item_id,
                        "content": [{"type": "Text", "text": part["text"]} for part in content],
                        "phase": "commentary"}
                last_agent = item
        elif kind == "reasoning":
            item = {"type": "Reasoning", "id": item_id,
                    "summary_text": [part["text"] for part in payload.get("summary", [])], "raw_content": []}
        elif kind in ("function_call", "custom_tool_call", "web_search_call"):
            arguments = payload.get("arguments", payload.get("input", payload.get("action", {})))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    pass
            item = {"type": "DynamicToolCall", "id": item_id,
                    "tool": payload.get("name", "web_search"), "arguments": arguments,
                    "status": "failed", "content_items": None, "success": None,
                    "error": "来源未提供工具结果，仅保留历史调用"}
            if payload.get("call_id"):
                pending_calls[payload["call_id"]] = item
        elif kind in ("function_call_output", "custom_tool_call_output"):
            result = payload.get("output", "")
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)
            called = pending_calls.pop(payload.get("call_id"), None)
            if called is not None:
                called["content_items"] = [{"type": "inputText", "text": result}]
                called["status"] = "completed"
                called["error"] = None
            else:
                item = {"type": "AgentMessage", "id": item_id,
                        "content": [{"type": "Text", "text": "[迁入的历史工具结果]\n" + result}],
                        "phase": "commentary"}
        else:
            raise ValueError("本机任务包含未支持的记录格式，未登记搬运成功。")
        output.append(record)
        if item is not None:
            output.append(event(timestamp, {"type": "item_completed", "thread_id": imported_id,
                                            "turn_id": turn_id, "item": item}))
        last_timestamp = timestamp
    complete_turn()
    if not any(record.get("payload", {}).get("type") == "item_completed" for record in output):
        raise ValueError("本机任务没有可分页的正文，未登记搬运成功。")
    for ordinal, record in enumerate(output):
        record["ordinal"] = ordinal
    return output


COLUMNS = {
    "threads": {"id", "rollout_path", "created_at", "updated_at", "source", "model_provider", "cwd", "title", "sandbox_policy", "approval_mode", "has_user_event", "first_user_message", "preview", "created_at_ms", "updated_at_ms", "recency_at", "recency_at_ms", "thread_source", "history_mode", "name", "originator", "project_id"},
    "projects": {"id", "name", "metadata", "position", "created_at_ms", "updated_at_ms"},
    "project_roots": {"project_id", "position", "path"},
}


def validate(database: Path) -> None:
    if not database.is_file():
        raise ValueError("请先在 ChatGPT 中使用一次本机 Work 或 Codex，初始化本机任务数据后再搬入。")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        for table, required in COLUMNS.items():
            actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if not required <= actual:
                raise ValueError("ChatGPT 本机任务数据格式发生变化，已停止导入，未修改原有记录。")


def _first_user_text(document: dict) -> str:
    for message in document.get("messages", []):
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text = "\n".join(part.get("text", "") for part in content if part.get("type") == "text")
            if text.strip():
                return text
    return ""


def _project(connection: sqlite3.Connection, directory: str, stamp: int) -> str:
    for project_id, root in connection.execute("SELECT project_id,path FROM project_roots ORDER BY position"):
        if _norm(root) == _norm(directory):
            return project_id
    project_id = str(uuid.uuid4())
    position = connection.execute("SELECT COALESCE(MAX(position),-1)+1 FROM projects").fetchone()[0]
    connection.execute("INSERT INTO projects(id,name,metadata,position,created_at_ms,updated_at_ms) VALUES(?,?,?,?,?,?)",
                       (project_id, Path(directory).name or directory, "{}", position, stamp, stamp))
    connection.execute("INSERT INTO project_roots(project_id,position,path) VALUES(?,?,?)", (project_id, 0, directory))
    return project_id


def register(path: Path, imported_id: str, document: dict, target: str, env: dict) -> int:
    root = Path(env["CODEX_HOME"])
    database = root / "state_5.sqlite"
    validate(database)
    if not path.resolve().is_relative_to((root / "sessions").resolve()):
        raise ValueError("导入记录的位置不属于目标 ChatGPT 本机历史目录，未登记。")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records or records[0].get("type") != "session_meta" or records[0].get("payload", {}).get("id") != imported_id:
        raise ValueError("导入的本机任务编号不一致，未登记。")
    stamp = int(time.time() * 1000)
    timestamp = datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    originator = "codex_work_desktop" if target == "chatgpt_work" else "Codex Desktop"
    directory = str(document["cwd"])
    title = str(document.get("title") or _first_user_text(document)[:120] or "搬入的对话")
    metadata = records[0]["payload"]
    metadata.update({"source": "vscode", "thread_source": "user", "originator": originator, "cwd": directory,
                     "timestamp": timestamp, "history_mode": "paginated", "dialog_mover_import_format": HISTORY_FORMAT})
    records[0]["timestamp"] = timestamp
    records = paginated_history(records, imported_id)
    historical_tool_notes = sum(bool(entry.get("dialog_mover_original", {}).get("reason")) for entry in records)
    records[0]["payload"]["dialog_mover_history_notes"] = historical_tool_notes
    temporary = path.with_suffix(".importing")
    try:
        temporary.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    backups = Path(env["APPDATA"]) / "对话搬家" / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"chatgpt-{stamp}-{uuid.uuid4().hex[:8]}.db"
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        with closing(sqlite3.connect(backup)) as snapshot:
            connection.backup(snapshot)
        connection.execute("PRAGMA foreign_keys=ON")
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            project_id = _project(connection, directory, stamp)
            values = {"id": imported_id, "rollout_path": str(path), "created_at": stamp // 1000, "updated_at": stamp // 1000,
                      "created_at_ms": stamp, "updated_at_ms": stamp, "recency_at": stamp // 1000, "recency_at_ms": stamp,
                      "source": "vscode", "thread_source": "user", "model_provider": "openai", "originator": originator,
                      "cwd": directory, "title": title, "name": title, "first_user_message": _first_user_text(document),
                      "preview": _first_user_text(document)[:600] or title,
                      "has_user_event": 1, "sandbox_policy": '{"type":"read-only"}', "approval_mode": "on-request",
                      "history_mode": "paginated", "project_id": project_id}
            columns = ",".join(values)
            placeholders = ",".join("?" for _column in values)
            connection.execute(f"INSERT INTO threads({columns}) VALUES({placeholders})", tuple(values.values()))
            stored = connection.execute("SELECT name,cwd,originator,project_id FROM threads WHERE id=?", (imported_id,)).fetchone()
            if stored != (title, directory, originator, project_id):
                raise ValueError("ChatGPT 本机登记校验失败，已回滚。")
    return historical_tool_notes
