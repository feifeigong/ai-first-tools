"""Read each app's own session list the way that app shows it.

Rules shared by every source:
- archived and deleted sessions never appear;
- a session is `movable` only if its transcript can really be read;
- sessions are grouped like the app's own sidebar (folder / project / space /
  task / recent) and every session carries the folder it belongs to.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from . import chatgpt, copilot_local, doubao, imports, mover
from .common import (
    appdata,
    as_millis,
    codex_home,
    finish_groups,
    user_env,
    folder_name,
    home,
    localappdata,
    make_group,
    make_session,
    norm,
    read_db,
    same_path,
    under_path,
    uri_to_path,
)

NO_FOLDER = "没有目录"


def _cursor_db() -> Path:
    return appdata() / "Cursor" / "User" / "globalStorage" / "state.vscdb"


def _qwen_db() -> Path:
    return appdata() / "QwenWorkCN" / "data" / "agents.db"


def _doubao_base() -> Path:
    return doubao.profile()


def _gemini_root(agent_id: str) -> Path:
    name = {"antigravity": "antigravity", "antigravity_ide": "antigravity-ide", "antigravity_cli": "antigravity-cli"}[agent_id]
    return home() / ".gemini" / name



def _hermes_db() -> Path | None:
    for base in (user_env("HERMES_HOME"), str(home() / ".hermes"), str(localappdata() / "hermes")):
        if base and (Path(base) / "state.db").is_file():
            return Path(base) / "state.db"
    return None


def _opencode_db() -> Path | None:
    candidates = []
    xdg = user_env("XDG_DATA_HOME")
    if xdg:
        candidates.append(Path(xdg) / "opencode" / "opencode.db")
    candidates.append(home() / ".local" / "share" / "opencode" / "opencode.db")
    return next((p for p in candidates if p.is_file()), None)


def installed(agent_id: str) -> bool:
    if agent_id == "codex_cli":
        root = codex_home()
        if not root:
            return False
        try:
            return bool(chatgpt.cli_sessions(root))
        except (OSError, ValueError, sqlite3.Error):
            return (root / "sessions").is_dir()  # Keep a broken index visible with its read error.
    if agent_id == "copilot_desktop":
        return copilot_local.installed()
    if agent_id in ("antigravity", "antigravity_ide", "antigravity_cli"):
        root = _gemini_root(agent_id)
        conv = root / "conversations"
        return conv.is_dir() and any(conv.glob("*.db"))
    if agent_id in ("codex", "chatgpt_work"):
        found = codex_home()
        return bool(found and (found / "sessions").is_dir())
    if agent_id == "chatgpt":
        found = codex_home()
        return bool(found and ((found / "auth.json").is_file() or (found / "state_5.sqlite").is_file() or any((found / "sessions").rglob("*.jsonl"))))
    if agent_id == "claude_code":
        return (home() / ".claude" / "projects").is_dir()
    if agent_id == "claude_desktop":
        return (_claude_root() / "IndexedDB").is_dir()
    if agent_id == "cowork":
        root = _cowork_root()
        return root is not None and root.is_dir()
    if agent_id == "cursor_cli":
        return (home() / ".cursor" / "chats").is_dir()
    if agent_id == "grok":
        return (home() / ".grok").is_dir()
    if agent_id == "hermes":
        return _hermes_db() is not None
    if agent_id == "opencode":
        return _opencode_db() is not None
    if agent_id == "cursor_desktop":
        return _cursor_db().is_file()
    if agent_id == "workbuddy":
        return (home() / ".workbuddy" / "workbuddy.db").is_file()
    if agent_id == "workbuddy_ai":
        return (home() / ".workbuddy-ai" / "workbuddy.db").is_file()
    if agent_id == "qwen_work":
        return _qwen_db().is_file()
    if agent_id == "doubao_work":
        return doubao.installed()
    return False


# ------------------------------------------------------------------- Cursor

def _cursor_project_created(db: Path, visible: set[str]) -> dict[str, int]:
    """Project creation time per folder, as Cursor stores it ("" = no folder / Home)."""
    found: dict[str, int] = {}
    try:
        con = read_db(db)
        try:
            row = con.execute("SELECT CAST(value AS TEXT) FROM ItemTable WHERE key = 'glass.localAgentProjects.v1'").fetchone()
            members = con.execute("SELECT CAST(value AS TEXT) FROM ItemTable WHERE key = 'glass.localAgentProjectMembership.v1'").fetchone()
        finally:
            con.close()
        projects = json.loads(row[0]) if row and row[0] else []
        membership = json.loads(members[0]) if members and members[0] else {}
        used = {pid for cid, pid in membership.items() if cid in visible}
    except (sqlite3.Error, json.JSONDecodeError, TypeError):
        return found
    for project in projects:
        uri = (project.get("workspace") or {}).get("uri") or {}
        path = uri.get("fsPath") if isinstance(uri, dict) else ""
        key = norm(path) if path else ""
        if key == "" and project.get("id") not in used:
            continue  # a folderless project nobody belongs to is not shown
        stamp = int(project.get("createdAt") or 0)
        found[key] = max(found.get(key, 0), stamp)
    return found


def cursor_groups() -> list[dict]:
    db = _cursor_db()
    con = read_db(db)
    folders: dict[str, list[dict]] = defaultdict(list)
    try:
        rows = con.execute(
            "SELECT composerId, workspaceId, lastUpdatedAt, createdAt, isArchived, isSubagent, value "
            "FROM composerHeaders"
        ).fetchall()
        for cid, _workspace, updated, created, archived, subagent, value in rows:
            if archived or subagent:
                continue
            try:
                header = json.loads(value or "{}")
            except json.JSONDecodeError:
                header = {}
            if header.get("isArchived") is True or header.get("isDraft") is True:
                continue
            ident = header.get("workspaceIdentifier") or {}
            uri = ident.get("uri") if isinstance(ident, dict) else None
            folder = uri.get("fsPath", "") if isinstance(uri, dict) else ""
            has_content = (
                con.execute(
                    "SELECT 1 FROM cursorDiskKV WHERE key >= ? AND key < ? LIMIT 1",
                    (f"bubbleId:{cid}:", f"bubbleId:{cid};"),
                ).fetchone()
                is not None
            )
            if not has_content and not (header.get("name") or "").strip():
                continue
            session = make_session(
                cid,
                header.get("name") or "",
                as_millis(updated or created),
                folder,
                movable=has_content,
                note="" if has_content else "这条记录是新版格式，暂时不能搬运",
            )
            folders[norm(folder) if folder else ""].append(session)
    finally:
        con.close()
    groups = []
    for key, sessions in folders.items():
        if key:
            path = sessions[0]["folder"]
            groups.append(make_group(folder_name(path), "folder", sessions, path))
        else:
            groups.append(make_group(NO_FOLDER, "none", sessions))
    # Cursor's sidebar: conversations by last update; workspaces by when the
    # project was created, newest first. Projects with no folder show as "Home".
    visible_ids = {item["id"] for items in folders.values() for item in items}
    created = _cursor_project_created(db, visible_ids)
    for group in groups:
        key = norm(group["path"]) if group["kind"] != "none" else ""
        group["_created"] = created.get(key, 0)
    groups.sort(key=lambda g: -g["_created"])
    for group in groups:
        group.pop("_created", None)
        if group["kind"] == "none":
            group["title"] = "Home"
    return finish_groups(groups, keep=True)


# --------------------------------------------------------- WorkBuddy (x2)

def _workbuddy_files(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    projects = root / "projects"
    if projects.is_dir():
        for path in projects.glob("*/*.jsonl"):
            found[path.stem] = path
    return found


def _has_dialog(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if '"type":"message"' in line.replace(" ", ""):
                    return True
    except OSError:
        return False
    return False


def workbuddy_groups(root: Path, product_dir: Path) -> list[dict]:
    db = root / "workbuddy.db"
    files = _workbuddy_files(root)
    con = read_db(db)
    tasks: list[dict] = []
    spaces: dict[str, list[dict]] = defaultdict(list)
    try:
        reserved = product_dir / "Claw"
        opened = {
            row[0]: int(row[1] or 0)
            for row in con.execute("SELECT path, last_opened_at FROM workspaces")
            if row[0] and not same_path(row[0], str(reserved))
        }
        space_paths = list(opened)
        rows = con.execute(
            "SELECT id, coalesce(nullif(custom_title,''), title, ''), status, cwd, "
            "coalesce(last_activity_at, created_at), coalesce(is_playground, 0) "
            "FROM sessions WHERE deleted_at IS NULL"
        ).fetchall()
        for sid, title, status, cwd, updated, playground in rows:
            if status == "archived":
                continue
            file = files.get(sid)
            if file is None or not _has_dialog(file):
                continue
            cwd = cwd or ""
            session = make_session(sid, title, as_millis(updated), cwd.replace("/", "\\") if sys.platform == "win32" else cwd)
            if playground:
                session["folder"] = ""
                tasks.append(session)
                continue
            space = next((path for path in space_paths if same_path(path, cwd)), "")
            if space:
                spaces[space].append(session)
    finally:
        con.close()
    groups = [make_group("任务", "task", tasks)]
    # spaces: the one opened most recently first
    for path, sessions in sorted(spaces.items(), key=lambda kv: -opened.get(kv[0], 0)):
        groups.append(make_group(folder_name(path), "space", sessions, path))
    return finish_groups(groups, keep=True)


# ---------------------------------------------------------------- Qwen work

def qwen_groups() -> list[dict]:
    con = read_db(_qwen_db())
    transcripts: dict[str, Path] = {}
    base = home() / ".qwenworkcn" / "projects"
    if base.is_dir():
        for path in base.glob("*/*.jsonl"):
            transcripts[path.stem] = path
    try:
        projects = {}
        for pid, name, roots in con.execute(
            "SELECT id, name, root_paths FROM local_projects WHERE deleted_at IS NULL ORDER BY updated_at DESC"
        ):
            try:
                paths = json.loads(roots or "[]")
            except json.JSONDecodeError:
                paths = []
            projects[pid] = (name or "", paths[0] if paths else "")
        sessions_by_chat: dict[str, str] = {}
        for chat_id, session_id in con.execute("SELECT chat_id, session_id FROM sub_chats ORDER BY created_at"):
            if session_id:
                sessions_by_chat[chat_id] = session_id
        recent: list[dict] = []
        by_project: dict[str, list[dict]] = defaultdict(list)
        for chat_id, name, project_id, updated in con.execute(
            "SELECT id, name, local_project_id, coalesce(updated_at, created_at) FROM chats "
            "WHERE deleted_at IS NULL AND archived_at IS NULL"
        ):
            session_id = sessions_by_chat.get(chat_id, "")
            movable = session_id in transcripts
            project = projects.get(project_id or "")
            folder = project[1] if project else ""
            session = make_session(
                session_id or chat_id,
                name or "",
                as_millis(updated),
                folder,
                movable=movable,
                note="" if movable else "这条对话没有保存在本机，不能搬运",
            )
            if project:
                by_project[project_id].append(session)
            else:
                recent.append(session)
    finally:
        con.close()
    # the app lists 项目 (newest first) above 最近
    groups = []
    for pid in projects:
        if pid in by_project:
            name, path = projects[pid]
            groups.append(make_group(name or folder_name(path), "project", by_project[pid], path))
    groups.append(make_group("最近", "recent", recent))
    return finish_groups(groups, keep=True)


# ------------------------------------------------------------- Doubao work

def _doubao_snapshots() -> dict[str, dict]:
    """Newest conversation-list snapshot per schema, read from a private copy."""
    index = _doubao_base() / "IndexedDB"
    source = index / doubao.INDEX_NAME
    if not source.is_dir():
        return {}
    vendor = Path(__file__).resolve().parent.parent / "vendor"
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    from ccl_chromium_reader import ccl_chromium_indexeddb as idb

    scratch = Path(tempfile.mkdtemp(prefix="dialog-mover-"))
    try:
        level = scratch / source.name
        shutil.copytree(source, level, ignore=shutil.ignore_patterns("LOCK"))
        blob_source = index / "chrome_doubaowork-chat_0.indexeddb.blob"
        blob = scratch / blob_source.name
        if blob_source.is_dir():
            shutil.copytree(blob_source, blob)
        wrapped = idb.WrappedIndexDB(level, blob if blob.is_dir() else None)
        newest: dict[str, tuple[int, dict]] = {}
        for dbid in wrapped.database_ids:
            if not dbid.name.startswith("DoubaoPC_"):
                continue
            db = wrapped[dbid.dbid_no]
            if "conversationListDataSnapshots" not in db.object_store_names:
                continue
            for rec in db["conversationListDataSnapshots"].iterate_records(live_only=True):
                value = rec.value
                if not isinstance(value, dict) or "schema" not in value:
                    continue
                schema = str(value["schema"])
                seq = int(getattr(rec, "ldb_seq_no", 0) or 0)
                if schema not in newest or seq >= newest[schema][0]:
                    newest[schema] = (seq, value.get("data") or {})
        return {schema: data for schema, (_seq, data) in newest.items()}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def doubao_groups() -> list[dict]:
    snapshots = _doubao_snapshots()
    local_dir = doubao.workspace() / ".sessions"
    local = {path.name for path in local_dir.iterdir() if path.is_dir()} if local_dir.is_dir() else set()

    def build(item: dict, folder: str = "") -> dict:
        cid = str(item.get("conversation_id", ""))
        movable = cid in local
        return make_session(
            cid,
            str(item.get("name", "")),
            as_millis(item.get("update_time") or item.get("create_time")),
            folder,
            movable=movable,
            note="" if movable else "这条对话只保存在云端，不能搬运",
        )

    groups: list[dict] = []
    projects = None
    for schema in ("conversation-list-data-project-v4", "conversation-list-data-project-v3"):
        if schema in snapshots:
            projects = snapshots[schema].get("projects") or []
            break
    seen: set[str] = set()

    def display_order(project: dict) -> int:
        try:
            return int(project.get("displayOrder") or 0)
        except (TypeError, ValueError):
            return 0

    # the app lists projects by displayOrder, largest first, conversations as stored
    for project in sorted(projects or [], key=display_order, reverse=True):
        sessions = []
        for item in project.get("conversations") or []:
            seen.add(str(item.get("conversation_id", "")))
            sessions.append(build(item, str(project.get("name", ""))))
        groups.append(make_group(str(project.get("name", "")) or "项目", "project", sessions, ordered=True))
    recent = []
    for item in (snapshots.get("conversation-list-data-non-project-v2") or {}).get("conversations") or []:
        cid = str(item.get("conversation_id", ""))
        if cid in seen or str(item.get("bot_type", "")) == "1" and not item.get("name"):
            continue
        recent.append(build(item))
    groups.append(make_group("最近", "recent", recent, ordered=True))
    return finish_groups(groups, keep=True)


# ------------------------------------------------------------- Antigravity

_ANTIGRAVITY_PINNED: set[str] = set()


def _pb_string(text: str) -> str:
    """Decode a protobuf text-format string literal (octal escapes carry UTF-8)."""
    raw = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if len(text[i + 1 : i + 4]) == 3 and text[i + 1 : i + 4].isdigit():
                raw.append(int(text[i + 1 : i + 4], 8) & 0xFF)
                i += 4
                continue
            mapping = {"n": b"\n", "t": b"\t", "r": b"\r", '"': b'"', "\\": b"\\", "'": b"'"}
            raw.extend(mapping.get(nxt, nxt.encode()))
            i += 2
            continue
        raw.extend(ch.encode("utf-8"))
        i += 1
    return raw.decode("utf-8", errors="replace")


def _antigravity_annotations(root: Path) -> dict[str, tuple[bool, str]]:
    found: dict[str, tuple[bool, str]] = {}
    folder = root / "annotations"
    if not folder.is_dir():
        return found
    for path in folder.glob("*.pbtxt"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        archived = bool(re.search(r"\barchived\s*:\s*true\b", text))
        pinned = bool(re.search(r"\bpinned\s*:\s*true\b", text))
        match = re.search(r'\btitle\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        found[path.stem] = (archived, _pb_string(match.group(1)) if match else "")
        if pinned:
            _ANTIGRAVITY_PINNED.add(path.stem)
    return found


def antigravity_groups(agent_id: str = "antigravity") -> list[dict]:
    by_folder: dict[str, list[dict]] = defaultdict(list)
    seen: set[str] = set()
    _ANTIGRAVITY_PINNED.clear()
    for root in [_gemini_root(agent_id)]:
        db = root / "conversation_summaries.db"
        conversations = root / "conversations"
        if not conversations.is_dir():
            continue
        present = {path.stem for path in conversations.glob("*.db")}
        if not db.is_file():
            # The IDE keeps conversations without a summary index: list the files.
            for cid in sorted(present):
                stamp = (conversations / f"{cid}.db").stat().st_mtime * 1000
                session = make_session(cid, "", int(stamp), "", root=str(root))
                by_folder[""].append(session)
            groups = [make_group(NO_FOLDER, "none", by_folder[""])]
            return finish_groups(groups)
        notes = _antigravity_annotations(root)
        con = read_db(db)
        try:
            query = (
                "SELECT conversation_id, title, preview, workspace_uris, project_id, "
                "last_modified_time, parent_conversation_id, killed FROM conversation_summaries"
            )
            for cid, title, preview, uris, project_id, modified, parent, killed in con.execute(query):
                if cid in seen or cid not in present or killed or parent:
                    continue
                archived_flag, note_title = notes.get(cid, (False, ""))
                if archived_flag:
                    continue
                seen.add(cid)
                folder = ""
                if project_id != "outside-of-project" and uris:
                    try:
                        parsed = json.loads(uris)
                    except json.JSONDecodeError:
                        parsed = []
                    if parsed:
                        folder = uri_to_path(parsed[0])
                text = note_title.strip() or (title or "").strip() or (preview or "").strip()[:40]
                session = make_session(cid, text, as_millis(modified), folder, root=str(root))
                by_folder[norm(folder) if folder else ""].append(session)
        finally:
            con.close()
    # pinned conversations get their own section above the rest, as in the app
    pinned: list[dict] = []
    for key in list(by_folder):
        keep = [s for s in by_folder[key] if s["id"] not in _ANTIGRAVITY_PINNED]
        pinned.extend(s for s in by_folder[key] if s["id"] in _ANTIGRAVITY_PINNED)
        by_folder[key] = keep
    groups = []
    for key, sessions in by_folder.items():
        if not sessions:
            continue
        if key:
            path = sessions[0]["folder"]
            groups.append(make_group(folder_name(path), "folder", sessions, path))
        else:
            groups.append(make_group(NO_FOLDER, "none", sessions))
    ordered = finish_groups(groups)
    if pinned:
        ordered.insert(0, make_group("置顶", "recent", pinned))
    return ordered


# ------------------------------------- apps read through the txcript reader

_LIST_LINE = re.compile(r"^(?P<harness>\S+)\s{2,}(?P<when>.+?)\s{2,}(?P<id>[0-9A-Za-z_-]{6,80})(?:\s{2,}(?P<title>.*))?$")


def _clean_title(title: str, cwd: str = "") -> str:
    """A title that is only a folder path is not a title."""
    text = (title or "").strip()
    if not text:
        return ""
    looks_like_path = bool(re.match(r"^[A-Za-z]:[\\/]", text)) and len(text) < 200
    if looks_like_path and (not cwd or norm(text) == norm(cwd) or norm(cwd) in norm(text)):
        return ""
    return text


def _when_millis(text: str) -> int:
    text = (text or "").strip()
    now = time.time()
    if text == "just now":
        return int(now * 1000)
    match = re.fullmatch(r"(\d+)\s*([mhd])\s+ago", text)
    if match:
        unit = {"m": 60, "h": 3600, "d": 86400}[match.group(2)]
        return int((now - int(match.group(1)) * unit) * 1000)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return int(time.mktime(time.strptime(text, "%Y-%m-%d")) * 1000)
        except ValueError:
            return 0
    return 0


def _txcript_rows(harness: str, env: dict | None = None, timeout: int = 240) -> list[dict]:
    result = mover._run(["list", "--from", harness], {**(env or {}), "TXCRIPT_LIST_REPORT": "1"}, timeout=timeout)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise RuntimeError(detail[-1] if detail else "list failed")
    reports = [line.removeprefix("TXCRIPT_LIST_REPORT ") for line in result.stdout.splitlines() if line.startswith("TXCRIPT_LIST_REPORT ")]
    if reports:
        if len(reports) != 1:
            raise ValueError("搬运组件返回了重复的会话名单。")
        return [{"id": row["id"], "title": row.get("title") or "", "ts": as_millis(row.get("timestamp"))}
                for row in json.loads(reports[0]) if row.get("harness") == harness]
    rows = []
    for line in result.stdout.splitlines():
        match = _LIST_LINE.match(line.rstrip())
        if match and match.group("harness") == harness:
            rows.append(
                {
                    "id": match.group("id"),
                    "title": (match.group("title") or "").strip(),
                    "ts": _when_millis(match.group("when")),
                }
            )
    return rows


def _group_by_folder(sessions: list[dict], none_title: str = NO_FOLDER) -> list[dict]:
    by_folder: dict[str, list[dict]] = defaultdict(list)
    for session in sessions:
        by_folder[norm(session["folder"]) if session["folder"] else ""].append(session)
    groups = []
    for key, items in by_folder.items():
        if key:
            path = items[0]["folder"]
            groups.append(make_group(folder_name(path), "folder", items, path))
        else:
            groups.append(make_group(none_title, "none", items))
    return finish_groups(groups)


def _first_cwd(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(40):
                line = handle.readline()
                if not line:
                    break
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
                cwd = record.get("cwd") or payload.get("cwd")
                if cwd:
                    return str(cwd)
    except OSError:
        pass
    return ""


_CODEX_CHAT_DIR = re.compile(r"[\\/]Documents[\\/]Codex[\\/]\d{4}-\d{2}-\d{2}[\\/]", re.I)


def _codex_state(root: Path) -> dict:
    try:
        return json.loads((root / ".codex-global-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _desktop_threads() -> dict:
    return chatgpt.desktop_threads()


def codex_groups(kind: str = "code") -> list[dict]:
    """Threads of the ChatGPT desktop app's Codex engine.

    The ChatGPT app shows these local threads under 工作 as one flat list of
    recent threads, and in its Codex view. `kind` "work" returns the flat
    list; "code" groups the same threads by the real folder they ran in.
    Both are ordered by each thread's last activity.
    """
    root = codex_home()
    if root is None:
        return []
    files: dict[str, Path] = {}
    for path in (root / "sessions").rglob("rollout-*.jsonl"):
        files[path.stem[-36:].lower()] = path
    archived: set[str] = set()
    if (root / "archived_sessions").is_dir():
        for path in (root / "archived_sessions").rglob("*.jsonl"):
            archived.add(path.stem[-36:].lower())
    index: dict[str, tuple[str, int]] = {}
    index_file = root / "session_index.jsonl"
    if index_file.is_file():
        for line in index_file.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = str(record.get("id", "")).lower()
            if sid:
                index[sid] = (str(record.get("thread_name") or ""), as_millis(record.get("updated_at")))
    projectless = {str(tid).lower() for tid in _codex_state(root).get("projectless-thread-ids") or []}
    recency: dict[str, int] = {}
    state_db = root / "state_5.sqlite"
    if state_db.is_file():
        try:
            con = read_db(state_db)
            try:
                for tid, stamp_ms in con.execute("SELECT id, recency_at_ms FROM threads"):
                    if stamp_ms:
                        recency[str(tid).lower()] = int(stamp_ms)
            finally:
                con.close()
        except sqlite3.Error:
            pass
    sessions: list[dict] = []
    for sid, (name, _updated) in index.items():
        path = files.get(sid)
        if path is None or sid in archived:
            continue
        meta = _first_meta(path)
        if meta.get("thread_source") == "subagent":
            continue
        cwd = str(meta.get("cwd") or "")
        # the app's own sidebar field (recency_at); the file's time if unknown
        stamp = recency.get(sid) or int(path.stat().st_mtime * 1000)
        scratch = bool(cwd) and bool(_CODEX_CHAT_DIR.search(cwd + "\\"))
        sessions.append(make_session(sid, name, stamp, "" if scratch or sid in projectless else cwd))
    if kind == "work":
        return finish_groups([make_group("最近", "recent", sessions)], keep=True)
    return _group_by_folder(sessions)

def _first_meta(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            record = json.loads(handle.readline())
        payload = record.get("payload")
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def claude_code_groups() -> list[dict]:
    projects = home() / ".claude" / "projects"
    files = {path.stem: path for path in projects.glob("*/*.jsonl")}
    rows = _txcript_rows("claude_code")
    details = _details_by_export("claude_code", rows) if len(rows) <= 60 else {}
    sessions = []
    for row in rows:
        path = files.get(row["id"])
        exported_cwd, first, movable = details.get(row["id"], ("", "", True))
        cwd = _first_cwd(path) if path else exported_cwd
        stamp = int(path.stat().st_mtime * 1000) if path else row["ts"]
        title = _clean_title(row["title"], cwd) or first
        sessions.append(make_session(row["id"], title, stamp, cwd, movable=movable,
                                     note="" if movable else "没有可显示的对话正文（为空或仅有工具日志），暂时不能搬运"))
    return _group_by_folder(sessions)


def invalidate_chatgpt() -> None:
    chatgpt.invalidate()


def chatgpt_groups() -> list[dict]:
    return _chatgpt_unified_groups()


def _chatgpt_unified_groups() -> list[dict]:
    return chatgpt.groups(_chatgpt_get)

def _chatgpt_get(path: str) -> dict | None:
    """One read-only GET against chatgpt.com, through the txcript reader."""
    handle = tempfile.NamedTemporaryFile(prefix="dm-api-", suffix=".json", delete=False)
    out = Path(handle.name)
    handle.close()
    try:
        for attempt in range(4):
            result = mover._run(
                ["list", "--from", "chatgpt"],
                {"TXCRIPT_CHATGPT_RAW_PATH": path, "TXCRIPT_CHATGPT_RAW_OUT": str(out)},
                timeout=180,
            )
            if out.is_file() and out.stat().st_size:
                return json.loads(out.read_text(encoding="utf-8"))
            if "429" in (result.stderr or "") or "rate-limit" in (result.stderr or ""):
                time.sleep(6 * (attempt + 1))  # ChatGPT asked us to slow down
                continue
            break
    except Exception:
        return None
    finally:
        out.unlink(missing_ok=True)
    return None


def _chatgpt_get_many(paths: list[str]) -> list:
    """Several read-only GETs over one connection. A failed one comes back as None."""
    if not paths:
        return []
    batch = tempfile.NamedTemporaryFile(prefix="dm-batch-", suffix=".json", delete=False)
    batch_path = Path(batch.name)
    batch.close()
    out = batch_path.with_suffix(".out.json")
    try:
        batch_path.write_text(json.dumps(paths), encoding="utf-8")
        mover._run(
            ["list", "--from", "chatgpt"],
            {"TXCRIPT_CHATGPT_RAW_BATCH": str(batch_path), "TXCRIPT_CHATGPT_RAW_OUT": str(out)},
            timeout=300,
        )
        answers = json.loads(out.read_text(encoding="utf-8")) if out.is_file() and out.stat().st_size else []
        if isinstance(answers, list) and len(answers) == len(paths):
            return answers
    except Exception:
        pass
    finally:
        batch_path.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
    return [None] * len(paths)


_chatgpt_get.many = _chatgpt_get_many  # fetch_web uses it when present


def _chatgpt_web_groups() -> list[dict]:
    state, atoms, sidebar = chatgpt.native_state()
    empty = {"projects": [], "pinned": [], "recent": [], "mirrors": {}}
    return chatgpt.build_groups(chatgpt.web_data(_chatgpt_get), empty, state, atoms, sidebar)


def _first_user_text(document: dict) -> str:
    for message in document.get("messages") or []:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, list):
            content = " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        text = " ".join(str(content or "").split())
        if text and not text.startswith("<"):
            return text[:42]
    return ""


def _details_by_export(harness: str, rows: list[dict], env: dict | None = None) -> dict[str, tuple[str, str, bool]]:
    """Read each session's folder and first question from its own export (small stores)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(row: dict) -> tuple[str, tuple[str, str, bool]]:
        handle = tempfile.NamedTemporaryFile(prefix="dm-", suffix=".json", delete=False)
        path = Path(handle.name)
        handle.close()
        try:
            result = mover._run(["export", row["id"], "--from", harness, "--out", str(path)], env, timeout=120)
            if result.returncode != 0:
                return row["id"], ("", "", False)
            document = json.loads(path.read_text(encoding="utf-8"))
            movable = imports.has_conversation_body(document)
            return row["id"], (str(document.get("cwd") or ""), _first_user_text(document), movable)
        except Exception:
            return row["id"], ("", "", False)
        finally:
            path.unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=4) as pool:
        return dict(pool.map(one, rows))


def _app_times(agent_id: str) -> dict[str, int]:
    """Each app's own ordering time per session, in milliseconds."""
    times: dict[str, int] = {}
    try:
        if agent_id == "hermes" and _hermes_db():
            con = read_db(_hermes_db())
            try:
                query = (
                    "SELECT s.id, COALESCE((SELECT MAX(m.timestamp) FROM messages m WHERE m.session_id = s.id), s.started_at) "
                    "FROM sessions s"
                )
                for sid, stamp in con.execute(query):
                    times[str(sid)] = as_millis(stamp)
            finally:
                con.close()
        elif agent_id == "cursor_cli":
            # `agent ls` lists by last use; the store file is rewritten on every use
            for db in (home() / ".cursor" / "chats").rglob("store.db"):
                times[db.parent.name] = int(db.stat().st_mtime * 1000)
        elif agent_id == "grok":
            # Grok lists sessions by last activity: the newest of its log files
            for folder in (home() / ".grok" / "sessions").glob("*/*"):
                if not folder.is_dir():
                    continue
                stamps = [
                    p.stat().st_mtime
                    for name in ("chat_history.jsonl", "events.jsonl", "summary.json")
                    for p in [folder / name]
                    if p.is_file()
                ]
                if stamps:
                    times[folder.name] = int(max(stamps) * 1000)
        elif agent_id == "opencode" and _opencode_db():
            con = read_db(_opencode_db())
            try:
                for sid, stamp in con.execute("SELECT id, time_updated FROM session"):
                    times[str(sid)] = as_millis(stamp)
            finally:
                con.close()
    except sqlite3.Error:
        pass
    return times


def small_harness_groups(agent_id: str) -> list[dict]:
    harness = mover.SOURCES[agent_id]
    rows = _txcript_rows(harness)
    own = _app_times(agent_id)
    for row in rows:
        row["ts"] = own.get(row["id"]) or row["ts"]
    details = _details_by_export(harness, rows) if len(rows) <= 40 else {}
    sessions = []
    for row in rows:
        cwd, first, movable = details.get(row["id"], ("", "", True))
        title = _clean_title(row["title"], cwd) or first
        sessions.append(make_session(row["id"], title, row["ts"], cwd, movable=movable,
                                     note="" if movable else "正文为空或本机无法读取，暂时不能搬运"))
    return _group_by_folder(sessions)


# ----------------------------------------------------------- Claude desktop

def _claude_root() -> Path:
    if sys.platform != "win32":
        return appdata() / "Claude"
    packages = localappdata() / "Packages"
    if packages.is_dir():
        for entry in sorted(packages.iterdir(), key=lambda path: path.name):
            if not entry.name.startswith("Claude_"):
                continue
            root = entry / "LocalCache" / "Roaming" / "Claude"
            if (root / "IndexedDB").is_dir() or (root / "local-agent-mode-sessions").is_dir():
                return root
    return localappdata() / "Packages" / "Claude_pzs8sxrjxfjjc" / "LocalCache" / "Roaming" / "Claude"


def _cowork_root() -> Path | None:
    """Local Cowork sessions. `$COWORK_SESSIONS_DIR` wins; otherwise the Store package tree."""
    override = user_env("COWORK_SESSIONS_DIR")
    if override:
        return Path(override)
    candidates = [appdata() / "Claude" / "local-agent-mode-sessions"]
    packages = localappdata() / "Packages"
    if packages.is_dir():
        for entry in sorted(packages.iterdir(), key=lambda path: path.name):
            if entry.name.startswith("Claude_"):
                candidates.append(entry / "LocalCache" / "Roaming" / "Claude" / "local-agent-mode-sessions")

    def rank(path: Path) -> tuple[int, float]:
        if not path.is_dir():
            return (0, 0.0)
        records = [*path.glob("*/*/local_*.json"), *path.glob("*/*/agent/local_*.json")]
        if records:
            return (2, max(item.stat().st_mtime for item in records))
        return (1, path.stat().st_mtime)

    best = max(candidates, key=rank)
    return best if rank(best)[0] else None


def cowork_groups() -> list[dict]:
    root = _cowork_root()
    if root is None or not root.is_dir():
        return []
    env = {"COWORK_SESSIONS_DIR": str(root)}
    rows = _txcript_rows("cowork", env)
    details = _details_by_export("cowork", rows, env) if rows and len(rows) <= 40 else {}
    sessions = []
    for row in rows:
        cwd, first, movable = details.get(row["id"], ("", "", True))
        title = _clean_title(row["title"], cwd) or first
        sessions.append(make_session(row["id"], title, row["ts"], cwd, movable=movable,
                                     note="" if movable else "正文为空或本机无法读取，暂时不能搬运"))
    return _group_by_folder(sessions)


# Conversation bodies the desktop app has cached locally, keyed by conversation id.
_CLAUDE_BODIES: dict[str, list[dict]] = {}


def claude_body(sid: str) -> list[dict] | None:
    return _CLAUDE_BODIES.get(sid)


def _claude_message_text(message: dict) -> str:
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type", "text") == "text" and isinstance(part.get("text"), str):
                parts.append(part["text"])
    if not any(part.strip() for part in parts) and isinstance(message.get("text"), str):
        parts.append(message["text"])
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _claude_turns(conversation: dict) -> list[dict]:
    """The active branch of one cached conversation, as plain user/assistant turns."""
    raw = [item for item in (conversation.get("chat_messages") or []) if isinstance(item, dict)]
    by_id = {item.get("uuid"): item for item in raw if item.get("uuid")}
    leaf = by_id.get(conversation.get("current_leaf_message_uuid"))
    chain: list[dict] = []
    seen: set[str] = set()
    while isinstance(leaf, dict) and leaf.get("uuid") not in seen:
        seen.add(str(leaf.get("uuid")))
        chain.append(leaf)
        leaf = by_id.get(leaf.get("parent_message_uuid"))
    ordered = list(reversed(chain)) if chain else raw
    turns = []
    for message in ordered:
        sender = str(message.get("sender") or "")
        role = {"human": "user", "user": "user", "assistant": "assistant"}.get(sender)
        text = _claude_message_text(message)
        if role is None or not text:
            continue
        turn = {"role": role, "content": text, "partial": bool(message.get("truncated"))}
        created = message.get("created_at")
        if isinstance(created, str) and created:
            turn["timestamp"] = created
        turns.append(turn)
    return turns


def _walk_claude(value, lists: list[tuple[float, list]], bodies: dict[str, list[dict]]) -> None:
    if isinstance(value, dict):
        queries = value.get("clientState")
        if isinstance(queries, dict):
            for query in queries.get("queries") or []:
                if not isinstance(query, dict):
                    continue
                key = query.get("queryKey") or []
                if not key or key[0] != "chat_conversation_list":
                    continue
                data = (query.get("state") or {}).get("data") if isinstance(query.get("state"), dict) else None
                rows: list = []
                if isinstance(data, dict) and isinstance(data.get("data"), list):
                    rows = data["data"]
                elif isinstance(data, dict) and isinstance(data.get("pages"), list):
                    rows = [item for page in data["pages"] for item in (page.get("data") or [])]
                if rows:
                    lists.append((float(value.get("timestamp") or 0), rows))
        messages = value.get("chat_messages")
        if isinstance(messages, list) and messages:
            turns = _claude_turns(value)
            uid = str(value.get("uuid") or "")
            if uid and turns and len(turns) >= len(bodies.get(uid, [])):
                bodies[uid] = turns
        for item in value.values():
            _walk_claude(item, lists, bodies)
    elif isinstance(value, list):
        for item in value:
            _walk_claude(item, lists, bodies)


def _read_claude_cache() -> tuple[list[dict], dict[str, list[dict]]]:
    """Sidebar rows, plus any conversation whose messages the app cached locally."""
    vendor = Path(__file__).resolve().parent.parent / "vendor"
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    from ccl_chromium_reader import ccl_chromium_indexeddb as idb
    from ccl_chromium_reader.serialization_formats import ccl_blink_value_deserializer as blink
    from ccl_chromium_reader.serialization_formats import ccl_v8_value_deserializer as v8

    index = _claude_root() / "IndexedDB"
    level_src = index / "https_claude.ai_0.indexeddb.leveldb"
    blob_src = index / "https_claude.ai_0.indexeddb.blob"
    if not level_src.is_dir() or not blob_src.is_dir():
        return [], {}
    scratch = Path(tempfile.mkdtemp(prefix="dialog-mover-"))
    lists: list[tuple[float, list]] = []
    bodies: dict[str, list[dict]] = {}
    try:
        level = scratch / level_src.name
        blob = scratch / blob_src.name
        shutil.copytree(level_src, level, ignore=shutil.ignore_patterns("LOCK"))
        shutil.copytree(blob_src, blob)
        database = idb.WrappedIndexDB(level, blob)
        for info in database.database_ids:
            wrapped = database[info.dbid_no]
            for store in wrapped:
                for record in store.iterate_records(bad_deserializer_data_handler=lambda _key, _buf: None):
                    _walk_claude(record.value, lists, bodies)
        # Some snapshots live in blob files the record index can no longer open.
        raw = database._raw_db
        for path in blob.rglob("*"):
            if not path.is_file() or path.stat().st_size < 2000:
                continue
            try:
                _, stream, _, _ = raw.read_record_precursor(
                    idb.IdbKey(b"\x00\x01"), 1, 1, path.read_bytes(), None, str(path)
                )
                value = v8.Deserializer(stream, host_object_delegate=blink.BlinkV8Deserializer().read).read()
            except Exception:
                continue
            _walk_claude(value, lists, bodies)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    lists.sort(key=lambda item: item[0])
    rows = lists[-1][1] if lists else []
    return rows, bodies


def claude_desktop_groups() -> list[dict]:
    """Sidebar order. A chat can be moved when the desktop app cached its messages."""
    global _CLAUDE_BODIES
    rows, bodies = _read_claude_cache()
    _CLAUDE_BODIES = {}
    sessions = []
    for item in rows:
        sid = str(item.get("uuid") or item.get("id") or "")
        title = str(item.get("name") or "")
        turns = bodies.get(sid)
        if turns:
            _CLAUDE_BODIES[sid] = turns
        partial = bool(turns) and any(turn.get("partial") for turn in turns)
        sessions.append(
            make_session(
                sid,
                title,
                as_millis(item.get("updated_at") or item.get("created_at")),
                movable=bool(turns),
                note="缓存里只保存了打开过的一部分正文" if partial else ("" if turns else "这条还没在本机打开过，缓存里没有正文，暂时不能搬"),
            )
        )
    return finish_groups([make_group("聊天", "recent", sessions, ordered=True)], keep=True)

# ------------------------------------------- found, but not readable yet

UNSUPPORTED = [
    ("codebuddy", "CodeBuddy", "腾讯", [".codebuddy", "AppData/Roaming/CodeBuddy CN", ".codebuddycn"]),
    ("qoder", "Qoder", "阿里", [".qoder", "AppData/Roaming/Qoder", ".qoder-cn"]),
    ("trae", "Trae", "字节跳动", [".trae", ".trae-cn", "AppData/Roaming/Trae", "AppData/Roaming/Trae CN"]),
    ("kimi", "Kimi", "月之暗面", [".kimi", ".kimi-code", ".kimi-work", "AppData/Roaming/kimi-desktop"]),
    ("windsurf", "Windsurf", "Codeium", [".windsurf", "AppData/Roaming/Windsurf"]),
    ("cherry", "Cherry Studio", "", ["AppData/Roaming/CherryStudio"]),
    ("lingma", "通义灵码", "阿里", [".lingma", "AppData/Local/.lingma"]),
    ("marscode", "豆包 MarsCode", "字节跳动", [".marscode"]),
    ("doubao_chat", "豆包（聊天版）", "字节跳动", ["AppData/Local/Doubao"]),
    ("yuanbao", "腾讯元宝", "腾讯", ["AppData/Local/com.tencent.yuanbao"]),
    ("deepseek", "DeepSeek Harness", "", ["deepseek-harness", "AppData/Roaming/@deepseek-ai"]),
    ("perplexity", "Perplexity", "", ["AppData/Roaming/Perplexity"]),
    ("manus", "Manus", "", ["AppData/Roaming/manus", "AppData/Roaming/openmanus"]),
    ("cline", "Cline", "", [".cline"]),
    ("grokbot", "Grok Bot", "", ["AppData/Roaming/Grok Bot"]),
]


EMPTY_ONES = {"grokbot"}


def unsupported_found() -> list[dict]:
    found = []
    for key, name, sub, paths in UNSUPPORTED:
        if any((home() / p).exists() for p in paths):
            found.append(
                {
                    "id": key,
                    "name": name,
                    "sub": sub or "已发现",
                    "reason": "empty" if key in EMPTY_ONES else "format",
                }
            )
    return found


# --------------------------------------------------------------------- API

def list_groups(agent_id: str) -> list[dict]:
    if agent_id == "codex_cli":
        root = codex_home()
        return _group_by_folder(chatgpt.cli_sessions(root)) if root else []
    if agent_id == "copilot_desktop":
        return copilot_local.groups()
    if agent_id == "cursor_desktop":
        return cursor_groups()
    if agent_id == "workbuddy":
        return workbuddy_groups(home() / ".workbuddy", home() / "WorkBuddy")
    if agent_id == "workbuddy_ai":
        return workbuddy_groups(home() / ".workbuddy-ai", home() / "WorkBuddy AI")
    if agent_id == "qwen_work":
        return qwen_groups()
    if agent_id == "doubao_work":
        return doubao_groups()
    if agent_id in ("antigravity", "antigravity_ide", "antigravity_cli"):
        return antigravity_groups(agent_id)
    if agent_id == "codex":
        return codex_groups("code")
    if agent_id == "chatgpt_work":
        return codex_groups("work")
    if agent_id == "claude_code":
        return claude_code_groups()
    if agent_id == "claude_desktop":
        return claude_desktop_groups()
    if agent_id == "cowork":
        return cowork_groups()
    if agent_id == "chatgpt":
        return chatgpt_groups()
    if agent_id in ("cursor_cli", "grok", "hermes", "opencode"):
        return small_harness_groups(agent_id)
    raise ValueError(agent_id)


def known_folders() -> list[dict]:
    """Folders worth offering as a destination: every folder any app already uses."""
    found: dict[str, str] = {}

    def add(path: str) -> None:
        if path and path.strip() and Path(path).is_dir():
            found.setdefault(norm(path), path)

    for agent in (
        "cursor_desktop", "workbuddy", "workbuddy_ai", "antigravity", "antigravity_cli",
        "qwen_work", "codex", "claude_code", "cowork", "copilot_desktop",
    ):
        if not installed(agent):
            continue
        try:
            for group in list_groups(agent):
                add(group["path"])
                for session in group["sessions"]:
                    add(session["folder"])
        except Exception:
            continue
    folders = [{"path": path, "name": folder_name(path)} for path in found.values()]
    folders.sort(key=lambda item: item["name"].lower())
    return folders
