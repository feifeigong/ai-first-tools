"""Exact public Desktop index rules shared by full and smart migration.

These agent-only branches are compiled by SQLite even for a non-agent INSERT.
Recognizing their exact definition permits compilation, not creating an agent or
modifying existing data. Unknown triggers must still be denied by each writer.
"""
from __future__ import annotations

import sqlite3


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
