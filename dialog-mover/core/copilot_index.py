"""Exact public Desktop index rules shared by full and smart migration.

These agent-only branches are compiled by SQLite even for a non-agent INSERT.
Recognizing their exact definition permits compilation, not creating an agent or
modifying existing data. Unknown triggers must still be denied by each writer.
"""
from __future__ import annotations

import sqlite3
import os

PROJECT_REQUIRED = {
    "projects": {"id", "name", "main_repo_path", "container_kind"},
    "sessions": {"id", "title", "session_type", "created_at", "updated_at", "is_running", "auto_approve", "permission_mode"},
    "workspaces": {"id", "project_id", "workspace_type", "branch", "name", "session_id", "source_path"},
}
PROJECT_WRITABLE = {
    "projects": PROJECT_REQUIRED["projects"] | {"created_at", "last_opened_at", "auto_approve", "show_in_sidebar"},
    "sessions": PROJECT_REQUIRED["sessions"] | {"mode", "was_interrupted", "remote_control_enabled", "remote_session_mode", "execution_location", "title_source", "provisional"},
    "workspaces": PROJECT_REQUIRED["workspaces"] | {"created_at", "updated_at", "tab_order", "port", "name_source", "explicitly_opened", "provisional", "host_id", "is_initialized"},
}


def project_schema(connection):
    result = {}
    for table, required in PROJECT_REQUIRED.items():
        kind = connection.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
        columns = {r[1]: r for r in connection.execute(f'PRAGMA table_info("{table}")')}
        if kind != ("table",) or not required <= columns.keys() or columns["id"][5] != 1:
            raise ValueError("当前 Copilot 版本的项目格式暂不支持，未添加对话。")
        if any(columns[name][2].upper() != "TEXT" for name in required - {"is_running", "auto_approve"}):
            raise ValueError("Copilot 的项目保存方式发生了变化，已停止写入。")
        if any(r[3] and r[4] is None and name not in PROJECT_WRITABLE[table] for name, r in columns.items()):
            raise ValueError("当前 Copilot 项目有无法识别的必填信息，已停止写入。")
        result[table] = set(columns)
    return result


def project_at(connection, workspace):
    # Read only this folder's identity, never app settings, accounts or chat bodies.
    columns = {r[1] for r in connection.execute('PRAGMA table_info("projects")')}
    selected = ["id", "name", "main_repo_path", "container_kind"]
    selected += [name for name in ("show_in_sidebar", "archived_at") if name in columns]
    match = "replace(main_repo_path,char(92),'/') COLLATE NOCASE=replace(?,char(92),'/')" if os.name == "nt" else "main_repo_path=?"
    rows = connection.execute("SELECT " + ",".join(selected) + " FROM projects WHERE " + match, (str(workspace),)).fetchall()
    if len(rows) > 1:
        raise ValueError("Copilot 中有多个同路径项目，请先在桌面端核对。")
    if not rows: return None
    row = dict(zip(selected, rows[0]))
    if row["container_kind"] not in {"folder", "repository"}:
        raise ValueError("这个路径属于其他类型的 Copilot 项目，未写入。")
    if row.get("show_in_sidebar", 1) != 1 or row.get("archived_at"):
        raise ValueError("这个 Copilot 项目已隐藏或归档，请先在桌面端恢复后重试。")
    return row


def known_trigger(connection, name, expected):
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
    return bool(row and row[0] and " ".join(row[0].split()).rstrip(";") == expected)


def known_agent_trigger_table(connection, name):
    # Shipped 1.1.30 agents and 1.1.31–1.1.33 persistent_projects migrations.
    # No heuristic parsing, altered condition or extra statement is accepted.
    for table, identifier in (("agents", "agents"), ("persistent_projects", '"persistent_projects"')):
        if name == "sessions_insert_agent":
            expected = f"CREATE TRIGGER sessions_insert_agent AFTER INSERT ON sessions WHEN NEW.session_type = 'agent' BEGIN INSERT INTO {identifier} (session_id) VALUES (NEW.id); END"
        elif name == "sessions_update_agent":
            expected = f"CREATE TRIGGER sessions_update_agent AFTER UPDATE OF session_type ON sessions WHEN OLD.session_type != NEW.session_type BEGIN DELETE FROM {identifier} WHERE session_id = NEW.id AND NEW.session_type != 'agent'; INSERT INTO {identifier} (session_id) SELECT NEW.id WHERE NEW.session_type = 'agent'; END"
        else:
            return None
        if known_trigger(connection, name, expected):
            return table
    return None


def import_error(error):
    """Explain the failure class without revealing SQL, paths or stored text."""
    code = getattr(error, 'sqlite_errorcode', 0) & 0xff
    if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return ValueError("Copilot 正在保存记录，本次未复制。请等当前操作结束后重试。")
    if code in (sqlite3.SQLITE_AUTH, sqlite3.SQLITE_PERM):
        return ValueError("Copilot 的本机索引写入规则暂不支持，本次未复制，原记录未改动。")
    if code in (sqlite3.SQLITE_CONSTRAINT, sqlite3.SQLITE_SCHEMA, sqlite3.SQLITE_ERROR):
        return ValueError("Copilot 的会话索引格式暂不支持，本次未复制，原记录未改动。")
    return ValueError("Copilot 的本机记录未能保存，请检查保存位置是否可写、磁盘空间是否充足后重试。原记录未改动。")
