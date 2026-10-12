from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .chatgpt import _norm


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


def register(path: Path, imported_id: str, document: dict, target: str, env: dict) -> None:
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
                     "timestamp": timestamp, "history_mode": "legacy"})
    records[0]["timestamp"] = timestamp
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
                      "history_mode": "legacy", "project_id": project_id}
            columns = ",".join(values)
            placeholders = ",".join("?" for _column in values)
            connection.execute(f"INSERT INTO threads({columns}) VALUES({placeholders})", tuple(values.values()))
            stored = connection.execute("SELECT name,cwd,originator,project_id FROM threads WHERE id=?", (imported_id,)).fetchone()
            if stored != (title, directory, originator, project_id):
                raise ValueError("ChatGPT 本机登记校验失败，已回滚。")
