from __future__ import annotations

import copy
import json
import ntpath
import posixpath
import re
import sqlite3
import threading
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

from .common import appdata, as_millis, codex_home, make_group, make_session, read_db
from . import codex_history


_WEB_CACHE = {"stamp": 0.0, "data": None, "force": False}
_WEB_LOCK = threading.Lock()
_REFRESH = {"running": False, "error": ""}
FRESH_SECONDS = 300
PARALLEL = 3  # more than this and chatgpt.com starts answering 429
MAX_PAGES = 300  # 30,000 conversations; anything more means the server is repeating itself


def invalidate() -> None:
    """The user asked for a refresh: the next read must really go to chatgpt.com."""
    with _WEB_LOCK:
        _WEB_CACHE["stamp"] = 0.0
        _WEB_CACHE["force"] = True


def _cache_file() -> Path:
    return appdata() / "对话搬家" / "chatgpt-web-cache.json"


def _load_disk() -> tuple[float, dict] | None:
    try:
        saved = json.loads(_cache_file().read_text(encoding="utf-8"))
        data = saved["data"]
        if isinstance(data.get("items"), list) and isinstance(data.get("projects"), list):
            return float(saved["stamp"]), data
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return None


def _save_disk(stamp: float, data: dict) -> None:
    try:
        target = _cache_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps({"stamp": stamp, "data": data}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)
    except OSError:
        pass  # a missing cache only costs speed


def info() -> dict:
    """How old the cloud part of the list is, and whether it is being updated right now."""
    with _WEB_LOCK:
        stamp = _WEB_CACHE["stamp"]
        has = _WEB_CACHE["data"] is not None
    if not has:
        saved = _load_disk()
        stamp = saved[0] if saved else 0.0
    return {"age": int(time.time() - stamp) if stamp else None, "refreshing": _REFRESH["running"], "error": _REFRESH["error"]}


def _json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _norm(path: str) -> str:
    if sys.platform != "win32" and not re.match(r"^[A-Za-z]:[\\/]", str(path or "")) and not str(path or "").startswith("\\"):
        return (posixpath.normpath(path).rstrip("/") or "/") if path else ""
    text = str(path or "").replace("/", "\\")
    extended = bool(re.match(r"^\\+\?\\+", text))
    if extended:
        text = re.sub(r"^\\+\?\\+", "", text)
        if text.casefold().startswith("unc\\"):
            text = "\\\\" + text[4:]
    return ntpath.normpath(text).rstrip("\\").casefold() if text else ""


def _rows(path: Path, query: str) -> list[dict]:
    if not path.is_file():
        return []
    connection = read_db(path)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(query)]
    finally:
        connection.close()


def native_state(root: Path | None = None) -> tuple[dict, dict, dict]:
    root = root or codex_home()
    if root is None:
        return {}, {}, {}
    state = _json(root / ".codex-global-state.json")
    atoms = state.get("electron-persisted-atom-state") or {}
    account = (_json(root / "auth.json").get("tokens") or {}).get("account_id")
    accounts = atoms.get("chatgpt-sidebar-state-v2") or atoms.get("chatgpt-sidebar-state-v1") or {}
    sidebar = accounts.get(account) if account else None
    if sidebar is None and len(accounts) == 1:
        sidebar = next(iter(accounts.values()))
    custom = atoms.get("sidebar-custom-sections-v3") or {}
    saved_sections = custom.get(account) if account else None
    if saved_sections is None and len(custom) == 1:
        saved_sections = next(iter(custom.values()))
    return state, atoms, {**(sidebar or {}), "customSections": saved_sections or {}}


def sort_mode(atoms: dict, field: str) -> str:
    preferences = atoms.get("flat-project-sidebar-preferences-v1") or {}
    mode = preferences.get(field, "updated_at")
    if atoms.get("codex-sidebar-sort-mode-v1") is not None:
        return "updated_at"
    if mode in ("priority", "created_at") or (mode == "manual" and preferences.get("manualSortVersion") != 1):
        return "updated_at"
    return mode


def ordered(items: list[dict], keys: list[str], new_first: bool = False) -> list[dict]:
    by_key = {item["key"]: item for item in items}
    saved = list(dict.fromkeys(key for key in keys if key in by_key))
    missing = [item for item in items if item["key"] not in set(saved)]
    known = [by_key[key] for key in saved]
    return missing + known if new_first else known + missing


def _sessions(items: list[dict], mode: str, keys: list[str]) -> list[dict]:
    newest = sorted(items, key=lambda item: item["ts"], reverse=True)
    return ordered(newest, keys, new_first=True) if mode == "manual" else newest


def _catalog(root: Path) -> tuple[list[dict], bool]:
    for path in (root / "sqlite" / "codex.db", root / "sqlite" / "codex-dev.db"):
        if not path.is_file():
            continue
        try:
            complete = _rows(path, "SELECT initial_build_complete FROM local_thread_catalog_sync_state WHERE host_id = 'local'")
            if complete and complete[0]["initial_build_complete"]:
                return _rows(path, "SELECT * FROM local_thread_catalog WHERE host_id = 'local' ORDER BY source_recency_at DESC, source_created_at DESC, thread_id DESC"), True
        except sqlite3.Error:
            continue
    return [], False


def thread_metadata(path: Path | None) -> dict:
    return codex_history.metadata(path)


def project_layout(root: Path) -> dict:
    """Project association metadata only; never load authentication/account atoms."""
    path = root / '.codex-global-state.json'
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding='utf-8')
        result = {}
        with closing(sqlite3.connect(':memory:')) as db:
            for key in ('local-projects', 'thread-project-assignments', 'projectless-thread-ids', 'thread-workspace-root-hints'):
                value = db.execute('SELECT json_extract(?, ?)', (raw, '$."' + key + '"')).fetchone()[0]
                if value:
                    result[key] = json.loads(value)
        return result
    except (OSError, ValueError, sqlite3.Error):
        return {}


def _project_for_thread(state, by_id, by_path, thread_id, row, cached):
    assignment = (state.get('thread-project-assignments') or {}).get(thread_id) or {}
    if assignment.get('projectOrigin') == 'chatgpt' or assignment.get('projectKind', 'local') != 'local':
        return None
    project = by_id.get(assignment.get('projectId'))
    project = project or by_id.get(cached.get('project_id')) or by_id.get(row.get('project_id'))
    if project is None and thread_id not in (state.get('projectless-thread-ids') or []):
        hint = (state.get('thread-workspace-root-hints') or {}).get(thread_id) or cached.get('cwd') or row.get('cwd') or ''
        matches = by_path.get(_norm(hint), [])
        project = matches[0] if matches else None
    return project


def _project_maps(root, state):
    by_id, by_path = {}, {}
    for key, item in (state.get('local-projects') or {}).items():
        project = {'id': key, 'title': item.get('name')}
        by_id[key] = project
        for path in item.get('rootPaths') or []:
            by_path.setdefault(_norm(path), []).append(project)
    database = root / 'state_5.sqlite'
    if database.is_file():
        for item in _rows(database, 'SELECT p.id, p.name, r.path FROM projects p JOIN project_roots r ON r.project_id=p.id'):
            matches = by_path.get(_norm(item['path']), [])
            if matches:
                by_id[item['id']] = next((p for p in matches if p['title'] == item['name']), matches[0])
    return by_id, by_path


def terminal_history_ids(root: Path) -> set[str]:
    """Read only native TUI history prefixes; do not decode or retain prompt text."""
    ids = set()
    path = root / "history.jsonl"
    if not path.is_file() or path.is_symlink():
        return ids
    prefix = re.compile(rb'^\s*\{\s*"session_id"\s*:\s*"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})"\s*,\s*"ts"\s*:\s*\d+\s*,\s*"text"\s*:')
    try:
        with path.open("rb") as stream:
            while start := stream.readline(256):
                match = prefix.match(start)
                tail = start
                while tail and not tail.endswith(b"\n"):
                    tail = stream.readline(65536)
                if match and tail.endswith(b"\n") and tail.rstrip().endswith(b"}"):
                    ids.add(match[1].decode("ascii").lower())
    except OSError:
        pass
    return ids


def is_cli_thread(row: dict, cached: dict, metadata: dict, *, terminal_history: bool = False) -> bool:
    if terminal_history:
        return True
    # The persisted header wins over a stale desktop index. TUI origin names
    # changed across versions; a desktop cache must not mask a native CLI source.
    for item in (metadata, row, cached):
        origin = str(item.get("originator") or "").strip().casefold()
        source = item.get("source") or item.get("source_kind")
        if source == "cli" or origin in {"codex_cli_rs", "codex-tui"}:
            return True
        if origin in {"codex desktop", "codex_work_desktop"} or source == "vscode":
            return False
    return False


def cli_sessions(root: Path | None = None) -> list[dict]:
    """Local CLI history only: no desktop account state or cloud reads."""
    root = root or codex_home()
    if root is None:
        return []
    files = codex_history.files(root)
    archived = set(codex_history.files(root, 'archived_sessions'))
    rows = {str(row["id"]).lower(): row for row in _rows(root / "state_5.sqlite", "SELECT * FROM threads")}
    catalog, complete = _catalog(root)
    cached = {str(row["thread_id"]).lower(): row for row in catalog}
    layout = project_layout(root)
    by_id, by_path = _project_maps(root, layout)
    terminal_ids = terminal_history_ids(root)
    names = {}
    index = root / "session_index.jsonl"
    if index.is_file():
        with index.open("r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                    if isinstance(item, dict) and isinstance(item.get("id"), str):
                        names[item["id"].lower()] = item
                except ValueError:
                    continue
    sessions = []
    for sid in dict.fromkeys([*rows, *cached, *files]):
        row, entry = rows.get(sid, {}), cached.get(sid, {})
        if sid in archived or row.get("archived") or entry.get("missing_candidate"):
            continue
        path = codex_history.resolve(root, sid, row.get('rollout_path') or '', files)
        meta = thread_metadata(path)
        if any(item.get("thread_source") in ("subagent", "guardian_review") or isinstance(item.get("source"), dict)
               or str(item.get("source", "")).startswith("{") for item in (row, entry, meta)):
            continue
        # Current Desktop project membership beats historical launch origin.
        # A shared cwd alone, without a complete Desktop catalog entry, does not.
        if complete and entry and _project_for_thread(layout, by_id, by_path, sid, row, entry):
            continue
        if not is_cli_thread(row, entry, meta, terminal_history=sid in terminal_ids):
            continue
        renamed = names.get(sid, {})
        title = renamed.get("thread_name") or row.get("name") or entry.get("display_title") or row.get("title") or ""
        stamp = max(as_millis(row.get("recency_at_ms") or row.get("recency_at")), as_millis(entry.get("source_recency_at")))
        stamp = stamp or as_millis(renamed.get("updated_at") or row.get("updated_at_ms") or row.get("updated_at"))
        stamp = stamp or (int(path.stat().st_mtime * 1000) if path else 0)
        cwd = str(row.get("cwd") or meta.get("cwd") or entry.get("cwd") or "")
        sessions.append(make_session(sid, str(title), stamp, cwd, movable=path is not None, source="codex_cli",
                                     note="" if path else "本地记录暂时无法读取，请在原软件打开后刷新"))
    return sessions


def local_data(root: Path | None = None) -> dict:
    root = root or codex_home()
    result = {"projects": [], "pinned": [], "recent": [], "mirrors": {}}
    if root is None:
        return result
    state, atoms, _sidebar = native_state(root)
    projects = []
    by_id = {}
    by_path: dict[str, list[dict]] = {}
    for project_id, item in (state.get("local-projects") or {}).items():
        paths = [str(path) for path in item.get("rootPaths") or []]
        project = {"id": project_id, "key": f"codex:project:{project_id}", "title": item.get("name") or "项目", "kind": "project", "path": paths[0] if paths else "", "paths": paths, "sessions": [], "keepEmpty": True}
        mirror = next((Path(path.replace("\\", "/")).name for path in paths if ".chatgpt-projects" in path.replace("\\", "/").split("/")), None)
        if mirror:
            project["mirror"] = mirror
        projects.append(project)
        by_id[project_id] = project
        for path in paths:
            by_path.setdefault(_norm(path), []).append(project)
    database = root / "state_5.sqlite"
    db_projects = _rows(database, "SELECT p.id, p.name, r.path FROM projects p JOIN project_roots r ON r.project_id=p.id ORDER BY p.position,r.position")
    for item in db_projects:
        candidates = by_path.get(_norm(item["path"]), [])
        project = by_id.get(item["id"]) or next((project for project in candidates if project["title"] == item["name"]), None)
        if project is None and candidates:
            project = candidates[0]
        if project is None:
            # Only the state database knows this project (an import wrote it): ChatGPT's own
            # sidebar does not list it, and shows its threads under 最近, so do the same.
            continue
        by_id[item["id"]] = project
    thread_rows = _rows(database, "SELECT * FROM threads ORDER BY recency_at_ms DESC,created_at_ms DESC,id DESC")
    threads = {row["id"]: row for row in thread_rows}
    catalog, complete = _catalog(root)
    catalog_by_id = {row["thread_id"]: row for row in catalog}
    candidates = [row["thread_id"] for row in catalog]
    candidates += [row["id"] for row in thread_rows if row["id"] not in catalog_by_id]
    files = codex_history.files(root)
    archived = set(codex_history.files(root, 'archived_sessions'))
    pinned_ids = list(state.get("pinned-thread-ids") or [])
    terminal_ids = terminal_history_ids(root)
    for thread_id in candidates:
        row = threads.get(thread_id) or {}
        cached = catalog_by_id.get(thread_id) or {}
        if cached.get("missing_candidate") or row.get("archived") or str(thread_id).lower() in archived:
            continue
        source = cached.get("source_kind") or row.get("source")
        provenance = row.get("thread_source") or cached.get("thread_source")
        if source not in ("vscode", "cli") or provenance in ("subagent", "guardian_review") or str(source).startswith("{"):
            continue
        if not row and not complete:
            continue
        rollout = codex_history.resolve(root, str(thread_id), row.get('rollout_path') or '', files)
        metadata = thread_metadata(rollout)
        project = _project_for_thread(state, by_id, by_path, thread_id, row, cached)
        desktop_project = bool(complete and cached and project)
        if not desktop_project and is_cli_thread(row, cached, metadata, terminal_history=str(thread_id).lower() in terminal_ids):
            continue
        cwd = str(row.get("cwd") or cached.get("cwd") or "")
        title = cached.get("display_title") or row.get("name") or row.get("title") or ""
        if row.get("name") and as_millis(row.get("updated_at_ms") or row.get("updated_at")) > as_millis(cached.get("source_updated_at")):
            title = row["name"]
        stamp = max(as_millis(row.get("recency_at_ms") or row.get("recency_at")), as_millis(cached.get("source_recency_at")))
        stamp = stamp or as_millis(row.get("updated_at_ms") or row.get("updated_at") or cached.get("source_updated_at"))
        work = (metadata.get('originator') or row.get('originator')) == "codex_work_desktop" or bool(re.search(r"[\\/]Documents[\\/]Codex[\\/]\d{4}-\d{2}-\d{2}[\\/]", cwd, re.I))
        available = bool(rollout and rollout.is_file())
        session = make_session(thread_id, str(title), stamp, project["path"] if project and not project.get("mirror") else "", movable=available, note="" if available else "本地记录暂时无法读取，请在 ChatGPT 打开后刷新", kind="work" if work else "codex", source="chatgpt_work")
        session["key"] = f"codex:thread:local:{thread_id}"
        if row.get("is_pinned") or thread_id in pinned_ids:
            result["pinned"].append(session)
        elif project and project.get("mirror"):
            result["mirrors"].setdefault(project["mirror"], []).append(session)
        elif project:
            project["sessions"].append(session)
        else:
            result["recent"].append(session)
    order = [f"codex:project:{project_id}" for project_id in state.get("project-order") or []]
    projects = ordered([project for project in projects if not project.get("mirror")], order, new_first=True)
    pinned_projects = list(state.get("pinned-project-ids") or [])
    manual = state.get("sidebar-project-thread-orders") or {}
    for project in projects:
        project["pinned"] = project["id"] in pinned_projects
        keys = [f"codex:thread:local:{thread_id}" for thread_id in (manual.get(project["id"]) or {}).get("threadIds") or []]
        if sort_mode(atoms, "projectSortMode") == "manual":
            project["sessions"] = ordered(sorted(project["sessions"], key=lambda item: item["ts"], reverse=True), keys)
        else:
            project["sessions"].sort(key=lambda item: item["ts"], reverse=True)
    pin_rank = {thread_id: index for index, thread_id in enumerate(pinned_ids)}
    result["pinned"].sort(key=lambda item: pin_rank.get(item["id"], len(pin_rank)))
    result["projects"] = projects
    return result


def fetch_web(get, workers: int = PARALLEL, pages_hint: int | None = None) -> dict:
    """Every cloud conversation and project, read side by side.

    `get(path)` answers one request. When it has a `many(paths)` attribute, several
    requests share one connection (starting a connection costs more than asking), and
    those groups run in parallel. Anything that failed is asked again on its own.
    """
    many = getattr(get, "many", None)

    def solo(paths: list[str]) -> list:
        return [get(path) for path in paths]

    def run(paths: list[str]) -> list:
        if not paths:
            return []
        if many is None:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                return list(pool.map(get, paths))
        groups = [list(range(i, len(paths), workers)) for i in range(workers)]
        groups = [group for group in groups if group]
        answers: list = [None] * len(paths)
        with ThreadPoolExecutor(max_workers=len(groups)) as pool:
            for group, got in zip(groups, pool.map(lambda g: many([paths[i] for i in g]), groups)):
                for i, value in zip(group, got):
                    answers[i] = value
        return [value if value is not None else get(path) for value, path in zip(answers, paths)]

    def conversations_path(offset: int) -> str:
        return f"/backend-api/conversations?offset={offset}&limit=100&order=updated&is_archived=false"

    def sidebar_path(cursor: str | None) -> str:
        return "/backend-api/gizmos/snorlax/sidebar?" + urlencode({"owned_only": "false", "conversations_per_gizmo": 0, "limit": 20, **({"cursor": cursor} if cursor else {})})

    def project_path(project_id: str, cursor: str | None) -> str:
        return f"/backend-api/gizmos/{project_id}/conversations?" + urlencode({"limit": 20, "owned_only": "false", **({"cursor": cursor} if cursor else {})})

    def check(data, message: str) -> dict:
        if data is None or not isinstance(data.get("items"), list):
            raise RuntimeError(message)
        return data

    # 1. the first page of conversations says how many there are; the sidebar lists the projects
    paths = [conversations_path(0), sidebar_path(None)]
    first = many(paths) if many is not None else solo(paths)
    first = [value if value is not None else get(path) for value, path in zip(first, paths)]
    items: list = []
    seen: set = set()

    def absorb(data: dict) -> dict:
        rows = data["items"]
        fresh = [item for item in rows if item.get("id") not in seen]
        if rows and not fresh:
            raise RuntimeError("ChatGPT 分页返回了重复内容，请稍后刷新。")
        items.extend(fresh)
        seen.update(item.get("id") for item in fresh)
        return data

    def page_failed(offset: int) -> str:
        return f"ChatGPT 对话列表在第 {offset // 100 + 1} 页读取失败，请稍后刷新；没有把不完整名单当作完整结果。"

    pages = [absorb(check(first[0], page_failed(0)))]
    project_pages = [check(first[1], "ChatGPT 项目列表读取失败，请稍后刷新。")]
    cursor = project_pages[-1].get("cursor")
    cursors = set()
    while cursor is not None:  # a long project list continues page by page
        if cursor in cursors:
            raise RuntimeError("ChatGPT 项目分页重复，请稍后刷新。")
        cursors.add(cursor)
        project_pages.append(check(get(sidebar_path(cursor)), "ChatGPT 项目列表读取失败，请稍后刷新。"))
        cursor = project_pages[-1].get("cursor")
    projects = [entry for page in project_pages for entry in page["items"]]
    project_ids = []
    for entry in projects:
        project_id = ((entry.get("gizmo") or {}).get("gizmo") or {}).get("id")
        if project_id and project_id.startswith("g-p-"):
            project_ids.append(project_id)

    # 2. the remaining conversation pages and every project's first page, side by side.
    # The page count the server reports is capped, so guess from the last read (default 6 pages).
    total = pages[0].get("total")
    guess = max(pages_hint or 6, -(-total // 100) if isinstance(total, int) else 0)
    offsets = list(range(100, 100 * (guess + 1), 100)) if len(pages[0]["items"]) >= 100 else []
    wanted = [conversations_path(offset) for offset in offsets] + [project_path(project_id, None) for project_id in project_ids]
    answers = run(wanted)
    for offset, data in zip(offsets, answers[: len(offsets)]):
        if len(pages[-1]["items"]) < 100:
            break  # the list ended earlier than guessed; the rest are empty pages
        pages.append(absorb(check(data, page_failed(offset))))
    while len(pages[-1]["items"]) >= 100:  # longer than guessed: read on, a wave at a time
        if len(pages) > MAX_PAGES:
            raise RuntimeError("ChatGPT 对话列表页数异常，已停止读取，请稍后刷新。")
        wave = [100 * (len(pages) + i) for i in range(workers * 2)]
        for offset, data in zip(wave, run([conversations_path(offset) for offset in wave])):
            if len(pages[-1]["items"]) < 100:
                break
            pages.append(absorb(check(data, page_failed(offset))))
    by_id = {item["id"]: item for item in items if item.get("id")}

    # 3. a project with more than one page continues on its own; then merge in the app's project order
    for project_id, data in zip(project_ids, answers[len(offsets):]):
        data = check(data, "ChatGPT 项目里的对话未读完整，请稍后刷新。")
        gathered = [data]
        seen_cursors = set()
        cursor = data.get("cursor")
        while cursor is not None:
            if cursor in seen_cursors:
                raise RuntimeError("ChatGPT 项目对话分页重复，请稍后刷新。")
            seen_cursors.add(cursor)
            data = check(get(project_path(project_id, cursor)), "ChatGPT 项目里的对话未读完整，请稍后刷新。")
            gathered.append(data)
            cursor = data.get("cursor")
        for page in gathered:
            for item in page["items"]:
                if item.get("id") and item["id"] not in seen:
                    items.append({**item, "gizmo_id": project_id})
                    seen.add(item["id"])
                elif item.get("id") in by_id:
                    by_id[item["id"]]["gizmo_id"] = project_id
    return {"items": items, "projects": projects, "pages": len(pages)}


def _page_hint() -> int | None:
    with _WEB_LOCK:
        data = _WEB_CACHE["data"]
    if data is None:
        saved = _load_disk()
        data = saved[1] if saved else None
    pages = (data or {}).get("pages")
    return pages + 1 if isinstance(pages, int) and pages > 0 else None  # one spare page for new chats


def _remember(data: dict) -> None:
    stamp = time.time()
    with _WEB_LOCK:
        _WEB_CACHE.update(stamp=stamp, data=copy.deepcopy(data), force=False)
    _save_disk(stamp, data)


def _refresh_in_background(get) -> None:
    with _WEB_LOCK:
        if _REFRESH["running"]:
            return
        _REFRESH["running"] = True

    def work() -> None:
        try:
            _remember(fetch_web(get, pages_hint=_page_hint()))
            _REFRESH["error"] = ""
        except Exception as error:  # noqa: BLE001 - the old list stays on screen
            _REFRESH["error"] = str(error)
        finally:
            _REFRESH["running"] = False

    threading.Thread(target=work, daemon=True).start()


def web_data(get, refresh: bool = False, allow_stale: bool = False) -> dict:
    """The chatgpt.com part of the list.

    `allow_stale` answers at once from the last saved copy and updates it in the
    background, unless the user just asked for a refresh.
    """
    with _WEB_LOCK:
        fresh = _WEB_CACHE["data"] is not None and time.time() - _WEB_CACHE["stamp"] < FRESH_SECONDS
        forced = refresh or _WEB_CACHE["force"]
        if fresh and not forced:
            return copy.deepcopy(_WEB_CACHE["data"])
        remembered = _WEB_CACHE["data"]
    if allow_stale and not forced:
        if remembered is None:
            saved = _load_disk()
            if saved:
                remembered = saved[1]
                with _WEB_LOCK:
                    _WEB_CACHE.update(stamp=saved[0], data=copy.deepcopy(remembered))
        if remembered is not None:
            _refresh_in_background(get)
            return copy.deepcopy(remembered)
    data = fetch_web(get, pages_hint=_page_hint())
    _remember(data)
    return data


def build_groups(web: dict, local: dict, state: dict, atoms: dict, sidebar: dict) -> list[dict]:
    projects = copy.deepcopy(local["projects"])
    by_project = {project["key"]: project for project in projects}
    for entry in web["projects"]:
        gizmo = (entry.get("gizmo") or {}).get("gizmo") or {}
        project_id = gizmo.get("id")
        if not project_id or not project_id.startswith("g-p-"):
            continue
        project = {"id": project_id, "key": f"chatgpt:project:{project_id}", "title": (gizmo.get("display") or {}).get("name") or "项目", "kind": "project", "path": "", "sessions": [], "keepEmpty": True, "pinned": False}
        if project["key"] not in by_project:
            projects.append(project)
            by_project[project["key"]] = project
    pinned_projects = {item.get("project", {}).get("id") for item in sidebar.get("pinnedProjects") or []}
    for project in projects:
        if project["id"] in pinned_projects:
            project["pinned"] = True
    items_by_id = {item["id"]: item for item in web["items"] if item.get("id") and not item.get("is_archived") and not item.get("is_temporary_chat")}
    pinned_order = [entry.get("conversation", {}).get("id") for entry in sidebar.get("pinnedConversations") or []]
    web_pinned = []
    recent = copy.deepcopy(local["recent"])
    for item in items_by_id.values():
        session = make_session(item["id"], str(item.get("title") or ""), as_millis(item.get("update_time")), kind="work" if item.get("trial_conversation_type") == "work" else "chat", source="chatgpt")
        session["key"] = f"chatgpt:conversation:{item['id']}"
        pin = item.get("is_starred") or item.get("pinned_time")
        if pin:
            session["pinAt"] = as_millis(item.get("pinned_time"))
            web_pinned.append(session)
        else:
            project = by_project.get(f"chatgpt:project:{item.get('gizmo_id')}")
            if project:
                project["sessions"].append(session)
            else:
                recent.append(session)
    web_pinned.sort(key=lambda item: item["pinAt"])
    web_pinned = ordered(web_pinned, [f"chatgpt:conversation:{thread_id}" for thread_id in pinned_order])
    for project_id, sessions in local["mirrors"].items():
        project = by_project.get(f"chatgpt:project:{project_id}")
        if project:
            project["sessions"].extend(copy.deepcopy(sessions))
        else:
            recent.extend(copy.deepcopy(sessions))
    local_pinned = copy.deepcopy(local["pinned"])
    pinned_mode = atoms.get("pinned-sidebar-sort-mode-v1", "manual")
    if pinned_mode != "manual":
        local_pinned.sort(key=lambda item: item["ts"], reverse=True)
    local_project_pins = [project for project in projects if project["pinned"] and project["key"].startswith("codex:")]
    rank = {project_id: index for index, project_id in enumerate(state.get("pinned-project-ids") or [])}
    local_project_pins.sort(key=lambda project: rank.get(project["id"], len(rank)))
    pinned = local_pinned + local_project_pins + web_pinned + [project for project in projects if project["pinned"] and project["key"].startswith("chatgpt:")]
    if pinned_mode == "manual":
        pinned = ordered(pinned, atoms.get("unified-sidebar-pinned-order-v1") or [])
    unpinned = ordered([project for project in projects if not project["pinned"]], atoms.get("unified-sidebar-project-order-v1") or [])
    mode = (atoms.get("flat-project-sidebar-preferences-v1") or {}).get("mode", "project")
    if mode == "list":
        recent.extend(item for project in unpinned for item in project["sessions"])
        unpinned = []
    recent = _sessions(recent, sort_mode(atoms, "chatSortMode"), atoms.get("unified-sidebar-chat-order-v1") or [])
    for project in projects:
        if project["key"].startswith("chatgpt:"):
            project["sessions"].sort(key=lambda item: item["ts"], reverse=True)
    custom = sidebar.get("customSections") or {}
    sections = {section["id"]: section for section in custom.get("sections") or [] if section.get("id")}
    children = [item for project in projects for item in project["sessions"]]
    all_entries = {item["key"]: item for item in pinned + projects + recent + children}
    custom_keys = {key for section in sections.values() for key in section.get("itemKeys") or []}
    pinned = [item for item in pinned if item["key"] not in custom_keys]
    unpinned = [item for item in unpinned if item["key"] not in custom_keys]
    recent = [item for item in recent if item["key"] not in custom_keys]
    for project in projects:
        project["sessions"] = [item for item in project["sessions"] if item["key"] not in custom_keys]
    base = {"pinned": pinned, "threads": unpinned, "chats": recent}
    section_order = list(dict.fromkeys([*(custom.get("sectionOrder") or []), "pinned", *sections, "threads", "chats"]))
    groups = []
    for section_id in section_order:
        entries = base.get(section_id)
        if entries is None and section_id in sections:
            entries = [all_entries[key] for key in sections[section_id].get("itemKeys") or [] if key in all_entries]
        if entries is None:
            continue
        label = {"pinned": "置顶", "threads": "项目", "chats": "最近"}.get(section_id, sections.get(section_id, {}).get("name") or "分组")
        rows = []
        def flush() -> None:
            if rows:
                group = make_group(label, "recent", rows.copy(), ordered=True)
                group.update(key=f"section:{section_id}:{len(groups)}", section=section_id, sectionTitle=label, headless=section_id != "chats")
                groups.append(group)
                rows.clear()
        for entry in entries:
            if entry.get("kind") == "project":
                flush()
                group = copy.deepcopy(entry)
                group.update(section=section_id, sectionTitle=label)
                groups.append(group)
            else:
                rows.append(entry)
        flush()
    return groups


def groups(get) -> list[dict]:
    state, atoms, sidebar = native_state()
    return build_groups(web_data(get, allow_stale=True), local_data(), state, atoms, sidebar)


def desktop_threads() -> dict:
    data = local_data()
    state, atoms, _sidebar = native_state()
    projects = ordered(data["projects"], atoms.get("unified-sidebar-project-order-v1") or [])
    rank = {project_id: index for index, project_id in enumerate(state.get("pinned-project-ids") or [])}
    pinned = sorted([project for project in projects if project["pinned"]], key=lambda project: rank.get(project["id"], len(rank)))
    return {"pinned_projects": [(project["title"], project["path"], project["sessions"]) for project in pinned], "projects": [(project["title"], project["path"], project["sessions"]) for project in projects if not project["pinned"]], "pinned": data["pinned"], "recent": data["recent"] + [item for sessions in data["mirrors"].values() for item in sessions]}
