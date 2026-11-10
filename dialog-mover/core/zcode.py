"""Read ZCode's local session database. The database is opened read-only."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .common import as_millis, finish_groups, folder_name, home, make_group, make_session, read_db


def database() -> Path | None:
    path = home() / ".zcode" / "cli" / "db" / "db.sqlite"
    return path if path.is_file() else None


def installed() -> bool:
    return database() is not None


def _shown(payload: dict) -> bool:
    """ZCode 会把同一句提问重复存档，并把待办提醒标成用户消息。界面上看不见的不要搬。"""
    if payload.get("synthetic") is True:
        return False
    semantics = payload.get("semantics") if isinstance(payload.get("semantics"), dict) else {}
    if semantics.get("uiVisibility") == "hidden" or semantics.get("transcriptVisibility") == "hidden":
        return False
    return True


def _parts(con: sqlite3.Connection, message_id: str) -> str:
    chunks: list[str] = []
    for (raw,) in con.execute("SELECT data FROM part WHERE message_id=? ORDER BY sequence", (message_id,)):
        try:
            part = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if part.get("type") != "text":
            continue
        text = str(part.get("text") or "").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


def document(session_id: str, path: Path | None = None) -> dict:
    db = path or database()
    if db is None:
        raise ValueError("没有找到 ZCode 的本机会话。")
    con = read_db(db)
    try:
        row = con.execute(
            "SELECT id, title, path, directory FROM session WHERE id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise ValueError("没有找到这条 ZCode 对话。")
        messages = []
        for message_id, raw in con.execute(
            "SELECT id, data FROM message WHERE session_id=? ORDER BY sequence",
            (session_id,),
        ):
            try:
                payload = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if not _shown(payload):
                continue
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            content = _parts(con, message_id)
            if not content:
                continue
            previous = messages[-1] if messages else None
            if previous and previous["role"] == role == "user" and previous["content"] == content:
                continue
            if previous and previous["role"] == role == "assistant":
                previous["content"] = previous["content"] + "\n\n" + content
                continue
            created = (payload.get("time") or {}).get("created")
            message = {"role": role, "content": content}
            if created:
                message["timestamp"] = as_millis(created)
            messages.append(message)
    finally:
        con.close()
    if not messages:
        raise ValueError("这条 ZCode 对话没有可读取的正文。")
    folder = row[2] or row[3] or ""
    return {"id": row[0], "title": row[1] or "未命名对话", "cwd": folder, "messages": messages}


def groups(path: Path | None = None) -> list[dict]:
    db = path or database()
    if db is None:
        return []
    con = read_db(db)
    try:
        rows = con.execute(
            "SELECT id, title, path, directory, time_updated, time_created FROM session"
        ).fetchall()
        bodies = set()
        for session_id, raw in con.execute("SELECT session_id, data FROM part"):
            try:
                part = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if part.get("type") == "text" and str(part.get("text") or "").strip():
                bodies.add(session_id)
    finally:
        con.close()
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for sid, title, folder, directory, updated, created in rows:
        path_text = folder or directory or ""
        if path_text not in grouped:
            grouped[path_text] = []
            order.append(path_text)
        grouped[path_text].append(
            make_session(
                sid,
                title or "",
                as_millis(updated or created),
                folder=path_text,
                movable=sid in bodies,
                note="" if sid in bodies else "这条没有可复制的正文",
                source="zcode",
            )
        )
    built = []
    for folder in order:
        built.append(
            make_group(
                folder_name(folder) if folder else "没有目录",
                "folder" if folder else "none",
                grouped[folder],
                path=folder,
            )
        )
    return finish_groups(built)
