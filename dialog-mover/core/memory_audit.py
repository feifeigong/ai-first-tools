"""Frozen-package check using synthetic records and an isolated project only."""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import traceback
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname
from unittest.mock import patch

from . import memory_deploy as deploy, memory_store as store, memory_workspace


@contextmanager
def isolated_connections(base: Path):
    """Fail before SQLite opens anything outside this audit's temporary folder."""
    original = sqlite3.connect
    def connect(database, *args, **kwargs):
        value = str(database)
        if value == ':memory:':
            return original(database, *args, **kwargs)
        target = Path(url2pathname(urlsplit(value).path)) if value.startswith("file:") else Path(value)
        if not target.resolve().is_relative_to(base.resolve()):
            raise ValueError("冻结检查拒绝连接隔离目录之外的数据库。")
        return original(database, *args, **kwargs)
    with patch.object(sqlite3, "connect", side_effect=connect):
        yield


def legacy_project_fixture(library: Path, project: Path) -> Path:
    """Synthetic metadata for the older, pre-independent-project preview only."""
    project.mkdir(parents=True, exist_ok=True)
    (project / "keep.txt").write_bytes(b"synthetic existing project: keep unchanged")
    receipt = {"id": "0" * 32, "state": "validated", "target": "copilot_desktop", "workspace": str(project),
               "files": [{"path": ".gitignore"}, {"path": ".agent-memory/bundles/" + "a" * 24 + "/archive/original.json"}],
               "desktop": {"existing_project": True, "workspace": str(project)}}
    path = library / "deployments" / receipt["id"] / "receipt.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(store.encoded(receipt), encoding="utf-8")
    return path


def desktop_fixture(root: Path):
    """An empty synthetic Desktop index for explicit offline audits only."""
    root.mkdir(parents=True)
    with closing(sqlite3.connect(root / "data.db")) as db, db:
        db.executescript("""
CREATE TABLE projects(id TEXT PRIMARY KEY NOT NULL,name TEXT NOT NULL,main_repo_path TEXT NOT NULL UNIQUE,
container_kind TEXT NOT NULL DEFAULT 'repository' CHECK(container_kind IN ('folder','repository','collection')),
created_at TEXT NOT NULL DEFAULT '',last_opened_at TEXT NOT NULL DEFAULT '',auto_approve INTEGER DEFAULT 1,
show_in_sidebar INTEGER NOT NULL DEFAULT 1,instructions TEXT NOT NULL DEFAULT '',setup_script TEXT NOT NULL DEFAULT '');
CREATE TABLE sessions(id TEXT PRIMARY KEY NOT NULL,title TEXT,session_type TEXT NOT NULL,
created_at TEXT NOT NULL,updated_at TEXT NOT NULL,is_running INTEGER DEFAULT 0,was_interrupted INTEGER DEFAULT 0,
mode TEXT,auto_approve INTEGER DEFAULT 1,permission_mode TEXT,remote_control_enabled INTEGER DEFAULT 0,
remote_session_mode TEXT,execution_location TEXT DEFAULT 'local',title_source TEXT DEFAULT 'auto',
provisional INTEGER DEFAULT 0,archived_at TEXT);
CREATE TABLE workspaces(id TEXT PRIMARY KEY NOT NULL,project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
workspace_type TEXT NOT NULL CHECK(workspace_type IN ('folder','branch','worktree','cloud')),
branch TEXT NOT NULL,name TEXT NOT NULL,session_id TEXT,source_path TEXT,tab_order INTEGER DEFAULT 0,port INTEGER DEFAULT 0,
created_at TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL DEFAULT '',name_source TEXT DEFAULT 'auto',
explicitly_opened INTEGER DEFAULT 0,provisional INTEGER DEFAULT 0,host_id TEXT DEFAULT 'local',is_initialized INTEGER DEFAULT 1,
archived_at TEXT);
CREATE TABLE app_state(key TEXT PRIMARY KEY,value TEXT);
INSERT INTO app_state VALUES('synthetic-credential-canary','never-copy-this-synthetic-value');
CREATE TABLE agents(session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE);
CREATE TABLE session_account_projects(session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE);
CREATE TRIGGER sessions_insert_agent AFTER INSERT ON sessions WHEN NEW.session_type = 'agent'
BEGIN INSERT INTO agents (session_id) VALUES (NEW.id); END;
CREATE TRIGGER sessions_remove_account_project AFTER DELETE ON sessions
BEGIN DELETE FROM session_account_projects WHERE session_id = OLD.id; END;
CREATE TRIGGER sessions_validate_agent_insert BEFORE INSERT ON sessions WHEN NEW.session_type = 'agent'
BEGIN
SELECT RAISE(ABORT, 'Agents must execute locally') WHERE COALESCE(NEW.execution_location,'local') != 'local';
SELECT RAISE(ABORT, 'My Copilot cannot become an Agent') WHERE NEW.id = (SELECT value FROM app_state WHERE key='my_copilot_session_id');
END;
CREATE TRIGGER agents_validate_insert BEFORE INSERT ON agents
BEGIN SELECT RAISE(ABORT, 'Agent record requires an Agent session')
WHERE NOT EXISTS(SELECT 1 FROM sessions WHERE id=NEW.session_id AND session_type='agent'); END;
CREATE TRIGGER agents_validate_delete BEFORE DELETE ON agents
WHEN EXISTS(SELECT 1 FROM sessions WHERE id=OLD.session_id AND session_type='agent')
BEGIN SELECT RAISE(ABORT, 'Delete the Agent through its session'); END;
CREATE TRIGGER workspaces_validate_agent_insert BEFORE INSERT ON workspaces
WHEN EXISTS(SELECT 1 FROM agents WHERE session_id=NEW.session_id)
BEGIN SELECT RAISE(ABORT, 'Agents cannot be workspace-bound'); END;
""")


def persistent_projects_fixture(root: Path):
    """Upgrade only an explicitly marked empty synthetic index to shipped 1.1.31 rules."""
    with closing(sqlite3.connect(root / "data.db")) as db, db:
        if db.execute("SELECT value FROM app_state WHERE key='synthetic-credential-canary'").fetchone() != ("never-copy-this-synthetic-value",):
            raise ValueError("This helper accepts only the marked synthetic fixture")
        if db.execute("SELECT count(*) FROM sessions").fetchone()[0]:
            raise ValueError("Upgrade the empty synthetic fixture before installing")
        db.executescript('''
ALTER TABLE agents RENAME TO persistent_projects;
CREATE TRIGGER sessions_update_agent
AFTER UPDATE OF session_type ON sessions WHEN OLD.session_type != NEW.session_type
BEGIN
    DELETE FROM "persistent_projects" WHERE session_id = NEW.id AND NEW.session_type != 'agent';
    INSERT INTO "persistent_projects" (session_id) SELECT NEW.id WHERE NEW.session_type = 'agent';
END;
''')


def run(report: Path) -> int:
    checks = []
    try:
        with tempfile.TemporaryDirectory(prefix="ai-first-memory-package-check-") as scratch, \
             patch.object(deploy.memory_desktop, "root", return_value=Path(scratch).resolve() / "desktop"), \
             isolated_connections(Path(scratch)):
            base = Path(scratch).resolve()
            try:
                sqlite3.connect(base.parent / (base.name + "-outside") / "data.db")
            except ValueError:
                checks.append({"name": "database_scope_guard", "passed": True})
            else:
                raise AssertionError("Audit database scope guard did not reject an outside path")
            library = base / "library"
            project = memory_workspace.create(library)
            original = {"id": "synthetic-frozen-source", "title": "安装包合成检查", "messages": [
                {"id": "synthetic-user", "role": "user", "content": "保留完整迁移，新增中文历史检索。"},
                {"id": "synthetic-assistant", "role": "assistant", "content": "历史记录合成检查，原文末尾标记。"}]}
            info = store.ingest(library, "fixture", original["id"], original)
            bundle = library / "bundles" / info["id"]
            checks.append({"name": "original_archive", "passed": json.loads((bundle / "archive/original.json").read_text(encoding="utf-8")) == original})
            desktop_fixture(base / "desktop")
            plan = deploy.build_plan(project, "copilot_desktop", library, [info["id"]], desktop_base=base / "desktop")
            result = deploy.install(plan, library)
            reader = store.HistoryReader(project / ".agent-memory")
            hits = reader.search("中文历史检索")["hits"]
            checks.append({"name": "chinese_retrieval", "passed": bool(hits)})
            checks.append({"name": "original_message_read", "passed": "中文历史检索" in reader.read(hits[0]["message_id"])["content"]})
            checks.append({"name": "bundled_stdio_mcp_handshake", "passed": result["state"] == "validated"})
            config = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][deploy.SERVER]
            checks.append({"name": "copilot_local_mcp_config", "passed": config["type"] == "local" and set(config["tools"]) == {"search_history", "read_history", "get_current_state"}})
            link = deploy.desktop_link(library, result["id"])
            with closing(sqlite3.connect(base / "desktop/data.db")) as db:
                row = db.execute("SELECT s.title,s.session_type,w.source_path FROM sessions s JOIN workspaces w ON s.id=w.session_id").fetchone()
            checks.append({"name": "desktop_project_handoff", "passed": row == ("安装包合成检查（智能搬家）", "project", str(project)) and link.startswith("ghapp://sessions/")})
            legacy = legacy_project_fixture(library, base / "legacy-existing-project")
            old_project = base / "legacy-existing-project"
            preserved = legacy.read_bytes(), (old_project / "keep.txt").read_bytes()
            repeated = deploy.install(deploy.prepare_entry(library, "copilot_desktop", info["id"]), library)
            checks.append({"name": "repeat_move_reuses_native_entry", "passed": repeated.get("reused") is True and repeated["id"] == result["id"]})
            checks.append({"name": "legacy_project_kept_untouched", "passed": (legacy.read_bytes(), (old_project / "keep.txt").read_bytes()) == preserved})
            deploy.rollback(library, result["id"])
            checks.append({"name": "rollback_project_changes", "passed": [p.name for p in project.iterdir()] == [memory_workspace.MARKER]})
            with closing(sqlite3.connect(base / "desktop/data.db")) as db:
                checks.append({"name": "rollback_desktop_handoff", "passed": db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0 and db.execute("SELECT count(*) FROM projects").fetchone()[0] == 0})
            # Reproduce an older Desktop-discarded workspace session using only
            # this temporary fixture, then verify a second click stays idempotent.
            persistent_projects_fixture(base / "desktop")
            previous = deploy.install(deploy.prepare_entry(library, "copilot_desktop", info["id"]), library)
            receipt_path = library / "deployments" / previous["id"] / "receipt.json"
            saved = json.loads(receipt_path.read_text(encoding="utf-8"))
            native = saved["desktop"]
            native["rows"]["sessions"]["session_type"] = "workspace"
            receipt_path.write_text(store.encoded(saved), encoding="utf-8")
            receipt_before = receipt_path.read_bytes()
            old_root = Path(previous["workspace"])
            old_files = {p.relative_to(old_root): p.read_bytes() for p in old_root.rglob("*") if p.is_file()}
            with closing(sqlite3.connect(base / "desktop/data.db")) as db, db:
                db.execute("UPDATE sessions SET session_type='workspace' WHERE id=?", (native["session_id"],))
                db.execute("DELETE FROM workspaces WHERE id=?", (native["workspace_id"],))
                db.execute("DELETE FROM projects WHERE id=?", (native["rows"]["projects"]["id"],))
                original_row = db.execute("SELECT * FROM sessions WHERE id=?", (native["session_id"],)).fetchone()
            shutil.rmtree(base / "desktop/session-state" / native["session_id"])
            restored = deploy.install(deploy.prepare_entry(library, "copilot_desktop", info["id"]), library)
            again = deploy.install(deploy.prepare_entry(library, "copilot_desktop", info["id"]), library)
            checks.append({"name": "discarded_legacy_entry_no_longer_blocks_move", "passed": restored["id"] != previous["id"] and again["id"] == restored["id"] and again.get("reused") is True})
            checks.append({"name": "source_badge_uses_current_entry", "passed": [r["id"] for r in deploy.saved_records(library)] == [restored["id"]]})
            with closing(sqlite3.connect(base / "desktop/data.db")) as db:
                unchanged = db.execute("SELECT * FROM sessions WHERE id=?", (native["session_id"],)).fetchone() == original_row
                visible = db.execute("SELECT count(*) FROM sessions s JOIN workspaces w ON s.id=w.session_id JOIN projects p ON p.id=w.project_id").fetchone()[0]
            checks.append({"name": "discarded_registration_and_archive_preserved", "passed": unchanged and visible == 1 and receipt_path.read_bytes() == receipt_before and {p.relative_to(old_root): p.read_bytes() for p in old_root.rglob("*") if p.is_file()} == old_files})
            deploy.rollback(library, restored["id"])
            with closing(sqlite3.connect(base / "desktop/data.db")) as db:
                checks.append({"name": "current_schema_rollback_preserves_legacy_orphan", "passed": db.execute("SELECT count(*) FROM persistent_projects").fetchone()[0] == 0 and db.execute("SELECT id FROM sessions").fetchall() == [(native["session_id"],)]})
    except Exception as error:
        checks.append({"name": "package_check", "passed": False, "error_type": type(error).__name__, "message": str(error),
                       "methods": [{"name": frame.name, "line": frame.lineno} for frame in traceback.extract_tb(error.__traceback__)]})
    passed = bool(checks) and all(item["passed"] for item in checks)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"passed": passed, "checks": checks, "synthetic_only": True, "model_requests": 0, "native_agent_resume_verified": False}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if passed else 1
