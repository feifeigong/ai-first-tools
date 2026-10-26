"""A visible, local Copilot project handoff. Never starts a model or changes old sessions."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from . import copilot_import, copilot_local, memory_workspace

FORMAT = "ai-first-memory-desktop-v1"
REQUIRED = {
    "projects": {"id", "name", "main_repo_path", "container_kind"},
    "sessions": {"id", "title", "session_type", "created_at", "updated_at", "is_running", "auto_approve", "permission_mode"},
    "workspaces": {"id", "project_id", "workspace_type", "branch", "name", "session_id", "source_path"},
}
WRITABLE = {
    "projects": REQUIRED["projects"] | {"created_at", "last_opened_at", "auto_approve", "show_in_sidebar"},
    "sessions": REQUIRED["sessions"] | {"mode", "was_interrupted", "remote_control_enabled", "remote_session_mode", "execution_location", "title_source", "provisional"},
    "workspaces": REQUIRED["workspaces"] | {"created_at", "updated_at", "tab_order", "port", "name_source", "explicitly_opened", "provisional", "host_id", "is_initialized"},
}


def root():
    return copilot_local.root()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def known_trigger(connection, name, expected):
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
    return bool(row and " ".join(row[0].split()).rstrip(";") == expected)


def known_agent_trigger_table(connection, name):
    # Exact shipped 1.1.30/1.1.31 rules. These branches cannot create an Agent
    # for our fixed project session; SQLite still authorizes their bytecode.
    for table, identifier in (("agents", "agents"), ("persistent_projects", '"persistent_projects"')):
        if name == "sessions_insert_agent":
            expected = f"CREATE TRIGGER sessions_insert_agent AFTER INSERT ON sessions WHEN NEW.session_type = 'agent' BEGIN INSERT INTO {identifier} (session_id) VALUES (NEW.id); END"
        elif name == "sessions_update_agent":
            expected = f"CREATE TRIGGER sessions_update_agent AFTER UPDATE OF session_type ON sessions WHEN OLD.session_type != NEW.session_type BEGIN DELETE FROM {identifier} WHERE session_id = NEW.id AND NEW.session_type != 'agent'; INSERT INTO {identifier} (session_id) SELECT NEW.id WHERE NEW.session_type = 'agent'; END"
        else:
            return None
        if known_trigger(connection, name, expected): return table
    return None


def safe_path(base: Path, relative: str):
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts:
        raise ValueError("Copilot 对话的保存位置不正确，已停止搬家。")
    path = base / part
    for parent in (path, *path.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise ValueError("Copilot 的数据位置链接到了其他文件夹，暂时无法安全添加对话。")
        if parent == base: break
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError("Copilot 对话的保存位置超出了预期范围，已停止写入。")
    return path


def schema(connection):
    result = {}
    for table, required in REQUIRED.items():
        kind = connection.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
        columns = {r[1]: r for r in connection.execute(f'PRAGMA table_info("{table}")')}
        if kind != ("table",) or not required <= columns.keys() or columns["id"][5] != 1:
            raise ValueError("当前 Copilot 版本的项目格式暂不支持，未添加对话。可以返回改用完整对话迁移。")
        if any(columns[name][2].upper() != "TEXT" for name in required - {"is_running", "auto_approve"}):
            raise ValueError("Copilot 的项目保存方式发生了变化，已停止写入。可以返回改用完整对话迁移。")
        if any(r[3] and r[4] is None and name not in WRITABLE[table] for name, r in columns.items()):
            raise ValueError("当前 Copilot 项目有无法识别的必填信息，已停止写入。可以返回改用完整对话迁移。")
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


def prepare(workspace: Path, prompt: str, base: Path | None = None, *, title: str, project_name: str | None = None):
    memory_workspace.library_for(workspace / ".agent-memory")
    base = (base or root()).absolute()
    safe_path(base, "data.db")
    safe_path(base, "session-state")
    copilot_import.validate(base)
    with closing(sqlite3.connect((base / "data.db").as_uri() + "?mode=ro", uri=True)) as connection:
        columns = schema(connection)
        existing = project_at(connection, workspace)
    stamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    sid, wid = str(uuid.uuid4()), str(uuid.uuid4())
    project_name = existing["name"] if existing else (project_name or workspace.name)
    project = {"id": existing["id"] if existing else str(uuid.uuid4()), "name": project_name,
               "main_repo_path": str(workspace), "container_kind": "folder", "created_at": stamp,
               "last_opened_at": stamp, "auto_approve": 0, "show_in_sidebar": 1}
    session = {"id": sid, "title": title, "session_type": "project", "created_at": stamp, "updated_at": stamp,
               "is_running": 0, "was_interrupted": 0, "mode": "interactive", "auto_approve": 0, "permission_mode": "on",
               "remote_control_enabled": 0, "remote_session_mode": "off", "execution_location": "local", "title_source": "user", "provisional": 0}
    workspace_row = {"id": wid, "project_id": project["id"], "workspace_type": "folder", "branch": "", "name": title,
                     "session_id": sid, "source_path": str(workspace), "created_at": stamp, "updated_at": stamp,
                     "tab_order": 0, "port": 0, "name_source": "user", "explicitly_opened": 1, "provisional": 0,
                     "host_id": "local", "is_initialized": 1}
    rows = {table: {k: v for k, v in values.items() if k in columns[table]}
            for table, values in (("projects", project), ("sessions", session), ("workspaces", workspace_row))}
    note = ("【AI一手搬家说明 · 旧对话已保存】\n"
            "在下方输入并发送下一步想做的事，Copilot 才会开始回复。\n"
            "例如：“先看看我们上次做到哪了，再继续。”\n"
            "完整旧记录留在本机，聊天时按需要查找。\n\n" + prompt)
    document = {"id": FORMAT, "title": title, "cwd": str(workspace), "messages": [{"role": "user", "content": note}]}
    events, journal, _ = copilot_import.prepare(document, sid)
    files = {"events.jsonl": ("\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n").encode("utf-8"),
             "workspace.yaml": (json.dumps(journal, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
             ".ai-first-memory.json": (json.dumps({"format": FORMAT, "session_id": sid, "project_id": project["id"], "workspace_id": wid}, indent=2) + "\n").encode("utf-8")}
    return {"base": str(base), "workspace": str(workspace), "existing_project": existing, "rows": rows, "files": files,
            "title": title, "project_name": project_name, "session_id": sid, "workspace_id": wid}


def receipt(plan):
    return {key: value for key, value in plan.items() if key != "files"} | {"files": {name: sha(raw) for name, raw in plan["files"].items()}}


def create(plan):
    workspace = Path(plan["workspace"])
    memory_workspace.library_for(workspace / ".agent-memory")
    if (plan["rows"]["sessions"].get("session_type") != "project"
            or plan["rows"]["projects"]["main_repo_path"] != str(workspace)
            or plan["rows"]["workspaces"]["source_path"] != str(workspace)):
        raise ValueError("新资料项目的位置不一致，已停止写入。")
    base = Path(plan["base"])
    destination = safe_path(base, "session-state/" + plan["session_id"])
    reserved = False
    try:
        with closing(sqlite3.connect(safe_path(base, "data.db").as_uri() + "?mode=rw", uri=True, timeout=5)) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            schema(connection)
            if project_at(connection, Path(plan["workspace"])) != plan["existing_project"]:
                raise ValueError("Copilot 项目在预览后发生变化，请重新核对。")
            inactive_agent_table = known_agent_trigger_table(connection, "sessions_insert_agent")
            current_table = ""
            def authorize(action, table, column, database, trigger):
                # SQLite authorizes inactive trigger bytecode too. Our fixed
                # 'project' session cannot execute this exact agent-only branch.
                if action == sqlite3.SQLITE_INSERT and table == inactive_agent_table and trigger == "sessions_insert_agent":
                    return sqlite3.SQLITE_OK
                if action == sqlite3.SQLITE_INSERT and (table != current_table or trigger is not None): return sqlite3.SQLITE_DENY
                if action in (sqlite3.SQLITE_DELETE, sqlite3.SQLITE_UPDATE): return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            connection.set_authorizer(authorize)
            try:
                for table in ("projects", "sessions", "workspaces"):
                    if table == "projects" and plan["existing_project"]: continue
                    current_table = table
                    row = plan["rows"][table]
                    connection.execute(f'INSERT INTO "{table}" (' + ",".join('"' + k + '"' for k in row) + ") VALUES (" + ",".join("?" for _ in row) + ")", list(row.values()))
                destination.parent.mkdir(exist_ok=True)
                destination.mkdir()
                reserved = True
                for name, raw in plan["files"].items():
                    with (destination / name).open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                for table in ("sessions", "workspaces"):
                    expected = plan["rows"][table]
                    actual = connection.execute("SELECT " + ",".join(expected) + f' FROM "{table}" WHERE id=?', (expected["id"],)).fetchone()
                    if actual != tuple(expected.values()): raise ValueError("Copilot 中的新对话没能保存完整，已停止搬家并尝试恢复。")
                if any(sha((destination / name).read_bytes()) != sha(raw) for name, raw in plan["files"].items()):
                    raise ValueError("搬家说明没能保存完整，已停止搬家并尝试恢复。")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    except BaseException:
        if reserved:
            for name, raw in plan["files"].items():
                path = safe_path(base, "session-state/" + plan["session_id"] + "/" + name)
                if path.is_file() and sha(path.read_bytes()) == sha(raw): path.unlink()
            try: destination.rmdir()
            except OSError: pass
        raise
    return receipt(plan)


def _check(connection, saved):
    schema(connection)
    for table in ("agents", "persistent_projects", "session_account_projects"):
        if connection.execute("SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)", (table,)).fetchone()[0]:
            if connection.execute(f'SELECT EXISTS(SELECT 1 FROM "{table}" WHERE session_id=?)', (saved["session_id"],)).fetchone()[0]:
                raise ValueError("这次新增的对话已有后续使用记录，已停止撤销，保留你的后续工作。")
    for table in ("sessions", "workspaces"):
        row = saved["rows"][table]
        actual = connection.execute("SELECT " + ",".join(row) + f' FROM "{table}" WHERE id=?', (row["id"],)).fetchone()
        if actual != tuple(row.values()):
            raise ValueError("这次新增的对话已有新消息或改动，已停止撤销，保留你的后续工作。")
    if saved["existing_project"] is None:
        project = saved["rows"]["projects"]
        actual = connection.execute("SELECT " + ",".join(project) + " FROM projects WHERE id=?", (project["id"],)).fetchone()
        extra = connection.execute("SELECT EXISTS(SELECT 1 FROM workspaces WHERE project_id=? AND id<>?)", (project["id"], saved["workspace_id"])).fetchone()[0]
        if actual != tuple(project.values()) or extra:
            raise ValueError("新建的 Copilot 项目已有后续改动，未撤销。")
        columns = {r[1] for r in connection.execute('PRAGMA table_info("projects")')}
        empty = [name for name in ("instructions", "setup_script", "run_script", "archive_script", "scripts_json", "pull_request_prompt", "issue_prompt") if name in columns]
        unset = [name for name in ("copilot_account_id", "github_account_id", "agent_owner_session_id") if name in columns]
        predicates = [f'COALESCE("{name}",\'\')=\'\'' for name in empty] + [f'"{name}" IS NULL' for name in unset]
        if predicates and not connection.execute("SELECT EXISTS(SELECT 1 FROM projects WHERE id=? AND " + " AND ".join(predicates) + ")", (project["id"],)).fetchone()[0]:
            raise ValueError("新建的 Copilot 项目已有后续设置，未撤销。")
    base = Path(saved["base"])
    folder = safe_path(base, "session-state/" + saved["session_id"])
    if not folder.is_dir() or {p.name for p in folder.iterdir()} != set(saved["files"]):
        raise ValueError("这次新增的对话中已有新文件，已停止撤销，保留你的后续工作。")
    for name, digest in saved["files"].items():
        path = safe_path(base, "session-state/" + saved["session_id"] + "/" + name)
        if not path.is_file() or sha(path.read_bytes()) != digest:
            raise ValueError("这次新增的对话已有新消息或改动，已停止撤销，保留你的后续工作。")


def check_rollback(saved):
    with closing(sqlite3.connect(safe_path(Path(saved["base"]), "data.db").as_uri() + "?mode=ro", uri=True)) as connection:
        _check(connection, saved)


def rollback(saved):
    base = Path(saved["base"])
    with closing(sqlite3.connect(safe_path(base, "data.db").as_uri() + "?mode=rw", uri=True, timeout=5)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")
        _check(connection, saved)
        inactive_account_cleanup = known_trigger(connection, "sessions_remove_account_project",
            "CREATE TRIGGER sessions_remove_account_project AFTER DELETE ON sessions BEGIN DELETE FROM session_account_projects WHERE session_id = OLD.id; END")
        current_table = ""
        def authorize(action, table, column, database, trigger):
            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE): return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_DELETE and current_table == "sessions":
                if table == "session_account_projects" and (trigger is None or (trigger == "sessions_remove_account_project" and inactive_account_cleanup)):
                    return sqlite3.SQLITE_OK  # Empty FK/known cleanup; this session has no such rows.
                if table in {"agents", "persistent_projects"} and trigger is None:
                    return sqlite3.SQLITE_OK  # Empty FK cascade for our non-agent session.
            if action == sqlite3.SQLITE_DELETE and (trigger is not None or (table != current_table and not (current_table == "projects" and table == "workspaces"))): return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        connection.set_authorizer(authorize)
        try:
            for table in ("workspaces", "sessions", "projects"):
                if table == "projects" and saved["existing_project"]: continue
                current_table = table
                connection.execute(f'DELETE FROM "{table}" WHERE id=?', (saved["rows"][table]["id"],))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    folder = safe_path(base, "session-state/" + saved["session_id"])
    for name, digest in saved["files"].items():
        path = safe_path(base, "session-state/" + saved["session_id"] + "/" + name)
        if path.is_file() and sha(path.read_bytes()) == digest: path.unlink()
    try: folder.rmdir()
    except OSError: pass


def repair_legacy_session(saved):
    """Correct only our former type label; preserve every message and other row field."""
    if saved["rows"]["sessions"]["session_type"] != "workspace":
        return False
    workspace = Path(saved["workspace"])
    memory_workspace.library_for(workspace / ".agent-memory")
    if (saved["rows"]["projects"]["main_repo_path"] != str(workspace)
            or saved["rows"]["workspaces"]["source_path"] != str(workspace)):
        raise ValueError("无法核对这次搬家记录的归属，已保留原内容。")
    with closing(sqlite3.connect(safe_path(Path(saved["base"]), "data.db").as_uri() + "?mode=rw", uri=True, timeout=5)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("""SELECT s.session_type,s.is_running FROM sessions s
            JOIN workspaces w ON w.session_id=s.id JOIN projects p ON p.id=w.project_id
            WHERE s.id=? AND w.id=? AND p.id=? AND w.source_path=? AND p.main_repo_path=?""",
            (saved["session_id"], saved["workspace_id"], saved["rows"]["projects"]["id"], str(workspace), str(workspace))).fetchone()
        if not row or row[0] not in {"workspace", "project"}:
            raise ValueError("这条搬家记录已有其他改动，已停止修复，保留现有内容。")
        if row[1]:
            return False  # The caller's global activity guard will defer opening.
        if row[0] == "workspace":
            inactive_agent_table = known_agent_trigger_table(connection, "sessions_update_agent")
            if inactive_agent_table and connection.execute(f'SELECT 1 FROM "{inactive_agent_table}" WHERE session_id=?', (saved["session_id"],)).fetchone():
                raise ValueError("这条记录已有其他工作关联，已保留原内容，未修改。")
            def authorize(action, table, column, database, trigger):
                if action == sqlite3.SQLITE_UPDATE:
                    return sqlite3.SQLITE_OK if table == "sessions" and column == "session_type" and trigger is None else sqlite3.SQLITE_DENY
                if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_DELETE) and table == inactive_agent_table and trigger == "sessions_update_agent":
                    return sqlite3.SQLITE_OK  # Exact inactive insert and an empty per-session cleanup only.
                if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_DELETE): return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            connection.set_authorizer(authorize)
            connection.execute("UPDATE sessions SET session_type='project' WHERE id=? AND session_type='workspace' AND is_running=0", (saved["session_id"],))
        connection.commit()
    saved["rows"]["sessions"]["session_type"] = "project"
    return True


def session_url(saved):
    sid = str(uuid.UUID(saved["session_id"]))
    with closing(sqlite3.connect(safe_path(Path(saved["base"]), "data.db").as_uri() + "?mode=ro", uri=True)) as connection:
        exists = connection.execute("SELECT EXISTS(SELECT 1 FROM sessions s JOIN workspaces w ON s.id=w.session_id WHERE s.id=? AND s.session_type IN ('project','workspace') AND w.id=? AND w.project_id=?)",
                                    (sid, saved["workspace_id"], saved["rows"]["projects"]["id"])).fetchone()[0]
        if not exists: raise ValueError("这次添加的智能搬家对话已不存在，请先在 Copilot 左侧查看对应项目。")
    return "ghapp://sessions/" + sid


def discarded_legacy_registration(connection, saved, columns):
    """A legacy workspace session with no project, links or files is not a live handoff.

    Do not repair/delete its remaining session row. A subsequent move may create a
    fresh independent project, and a healthy newer receipt still takes priority.
    """
    rows = saved["rows"]
    sid = saved["session_id"]
    if (rows["sessions"].get("id") != sid or rows["sessions"].get("session_type") != "workspace"
            or rows["workspaces"].get("id") != saved["workspace_id"]
            or rows["workspaces"].get("session_id") != sid
            or rows["workspaces"].get("project_id") != rows["projects"].get("id")
            or rows["projects"].get("main_repo_path") != saved["workspace"]
            or rows["workspaces"].get("source_path") != saved["workspace"]):
        return False
    folder = safe_path(Path(saved["base"]), "session-state/" + sid)
    if folder.exists(): return False
    for table in ("projects", "workspaces"):
        if connection.execute(f'SELECT 1 FROM "{table}" WHERE id=?', (rows[table]["id"],)).fetchone():
            return False
    selected = ["session_type", "is_running", *sorted(columns["sessions"] & {"archived_at", "deleted_at", "provisional"})]
    session = connection.execute("SELECT " + ",".join('"' + c + '"' for c in selected) + " FROM sessions WHERE id=?", (sid,)).fetchone()
    if not session or session[:2] != ("workspace", 0) or any(value not in (None, "", 0) for value in session[2:]):
        return False
    if connection.execute("SELECT 1 FROM workspaces WHERE session_id=?", (sid,)).fetchone(): return False
    match = "replace(main_repo_path,char(92),'/') COLLATE NOCASE=replace(?,char(92),'/')" if os.name == "nt" else "main_repo_path=?"
    if connection.execute("SELECT 1 FROM projects WHERE " + match, (saved["workspace"],)).fetchone(): return False
    for table in ("agents", "persistent_projects", "session_account_projects"):
        kind = connection.execute("SELECT type FROM sqlite_master WHERE name=?", (table,)).fetchone()
        if kind is not None:
            if kind != ("table",) or connection.execute(f'SELECT 1 FROM "{table}" WHERE session_id=?', (sid,)).fetchone():
                return False
    return True


def present(saved):
    """Check only owned identities/sidebar flags; never load conversation bodies."""
    workspace = Path(saved["workspace"])
    memory_workspace.library_for(workspace / ".agent-memory")
    sid = str(uuid.UUID(saved["session_id"]))
    base = Path(saved["base"])
    with closing(sqlite3.connect(safe_path(base, "data.db").as_uri() + "?mode=ro", uri=True)) as connection:
        columns = schema(connection)
        row = connection.execute("""SELECT s.session_type,w.source_path,p.main_repo_path
            FROM sessions s JOIN workspaces w ON w.session_id=s.id JOIN projects p ON p.id=w.project_id
            WHERE s.id=? AND w.id=? AND p.id=?""",
            (sid, saved["workspace_id"], saved["rows"]["projects"]["id"])).fetchone()
        if row is None:
            if discarded_legacy_registration(connection, saved, columns):
                return False
            remaining = any(connection.execute(f'SELECT 1 FROM "{table}" WHERE id=?', (saved["rows"][table]["id"],)).fetchone()
                            for table in ("sessions", "workspaces", "projects"))
            if remaining:
                raise ValueError("原搬家记录的项目或对话发生变化，已保留现有内容，未创建副本。")
            return False
        if row[0] not in {"project", "workspace"} or row[1:] != (str(workspace), str(workspace)):
            raise ValueError("原搬家记录的归属发生变化，已保留现有内容，未创建副本。")
        for table in ("projects", "sessions", "workspaces"):
            for name in ("archived_at", "deleted_at", "provisional"):
                if name in columns[table]:
                    value = connection.execute(f'SELECT "{name}" FROM "{table}" WHERE id=?', (saved["rows"][table]["id"],)).fetchone()[0]
                    if value not in (None, "", 0):
                        raise ValueError("这条记录已在 Copilot 隐藏或归档，请先在 Copilot 恢复它；不会再创建同名副本。")
        if "show_in_sidebar" in columns["projects"]:
            if connection.execute("SELECT show_in_sidebar FROM projects WHERE id=?", (saved["rows"]["projects"]["id"],)).fetchone()[0] != 1:
                raise ValueError("这条记录的项目已隐藏，请先在 Copilot 恢复它。")
    marker = safe_path(base, f"session-state/{sid}/.ai-first-memory.json")
    if not marker.is_file():
        raise ValueError("无法核对原搬家记录的归属，已保留现有内容。")
    expected = {"format": FORMAT, "session_id": sid, "project_id": saved["rows"]["projects"]["id"], "workspace_id": saved["workspace_id"]}
    if json.loads(marker.read_text(encoding="utf-8")) != expected:
        raise ValueError("原搬家记录的归属标记发生变化，已停止操作。")
    return True
