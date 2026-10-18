"""Copy sessions from one app to another. The source is never modified."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from .common import appdata, codex_home, localappdata, norm, proxy_env, user_env
from . import codex_import, copilot_import, copilot_local, doubao, imports

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
SAFE_ID = re.compile(r"^[0-9A-Za-z_-]{6,80}$")

TARGETS = imports.TARGETS
SOURCES = {
    "copilot_desktop": "copilot_local",
    "cursor_desktop": "cursor_desktop",
    "workbuddy": "workbuddy",
    "workbuddy_ai": "workbuddy_ai",
    "qwen_work": "qwen_work",
    "doubao_work": "doubao_work",
    "antigravity": "antigravity",
    "antigravity_cli": "antigravity",
    "codex": "codex",
    "chatgpt_work": "codex",
    "claude_code": "claude_code",
    "cowork": "cowork",
    "cursor_cli": "cursor",
    "grok": "grok",
    "hermes": "hermes",
    "opencode": "opencode",
    "chatgpt": "chatgpt",
    "claude_desktop": "claude_desktop",
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    path = appdata() / "对话搬家"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log(text: str) -> None:
    try:
        with (data_dir() / "log.txt").open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
    except OSError:
        pass


def txcript_path() -> Path | None:
    filename = "txcript.exe" if sys.platform == "win32" else "txcript"
    bundled = app_dir() / "bin" / filename
    if bundled.is_file():
        return bundled
    found = shutil.which("txcript")
    if found:
        return Path(found)
    local = localappdata() / "txcript" / filename
    return local if local.is_file() else None


TEST_ENV: dict = {}  # only the self-checks set this, to aim writes at scratch copies


def _env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    if sys.platform == "darwin":
        env.setdefault("APPDATA", str(appdata()))
        env.setdefault("LOCALAPPDATA", str(localappdata()))
    for key in (
        "WORKBUDDY_DIR",
        "WORKBUDDY_AI_DIR",
        "ANTIGRAVITY_DIR",
        "DOUBAO_WORK_DIR",
        "QWENWORK_DIR",
        "CURSOR_DESKTOP_USER_DIR",
    ):
        env.pop(key, None)
    found = codex_home()
    if found:
        env.setdefault("CODEX_HOME", str(found))
    for key, value in proxy_env().items():
        env.setdefault(key, value)
    for name in ("HERMES_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
        value = user_env(name)
        if value:
            env.setdefault(name, value)
    env.update(extra or {})
    return env


def _run(args: list[str], extra_env: dict | None = None, timeout: int = 240):
    exe = txcript_path()
    if exe is None:
        raise RuntimeError("软件缺少搬运组件，请重新安装。")
    return subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=_env(extra_env),
        creationflags=CREATE_NO_WINDOW,
    )


def _history_file() -> Path:
    return data_dir() / "history.json"


def _load_history() -> dict:
    try:
        return json.loads(_history_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_history(history: dict) -> None:
    _history_file().write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")


def history_key(source: str, session_id: str, target: str, directory: str) -> str:
    # views of the same store (e.g. ChatGPT 工作 and Codex) share one history
    return f"{SOURCES.get(source, source)}:{session_id}->{target}:{norm(directory)}"


def already_moved(source: str, session_id: str, target: str, directory: str) -> bool:
    saved = _load_history().get(history_key(source, session_id, target, directory))
    if target in ("codex", "chatgpt_work"):
        return isinstance(saved, dict) and saved.get("format") == codex_import.HISTORY_FORMAT
    if target == "copilot_desktop":
        return isinstance(saved, dict) and saved.get("format") == copilot_import.HISTORY_FORMAT
    return saved is not None


def _record_move(source: str, session_id: str, target: str, directory: str) -> None:
    history = _load_history()
    stamp = int(time.time())
    history_format = (codex_import.HISTORY_FORMAT if target in ("codex", "chatgpt_work") else
                      copilot_import.HISTORY_FORMAT if target == "copilot_desktop" else None)
    history[history_key(source, session_id, target, directory)] = {"time": stamp, "format": history_format} if history_format else stamp
    _save_history(history)


def _friendly(detail: str) -> str:
    text = detail.lower()
    if "no session" in text or "not found" in text or "ambiguous" in text:
        return "没有找到这条对话，可能已被删除。"
    if "locked" in text or "database is locked" in text:
        return "目标软件正在占用数据，请先关闭它再试。"
    if "permission" in text or "access is denied" in text:
        return "没有权限写入，请关闭目标软件后重试。"
    if "timed out" in text or "timeout" in text:
        return "等待太久了，请稍后重试。"
    return "这条对话暂时不能搬。"


def destination_env(target: str) -> dict:
    from . import sources

    extra = {"TXCRIPT_IMPORT_REPORT": "1", "NO_COLOR": "1"}
    if target == "copilot_desktop":
        extra["COPILOT_HOME"] = str(copilot_local.root())
    if target in ("antigravity", "antigravity_cli"):
        extra["ANTIGRAVITY_DIR"] = str(sources._gemini_root(target))
    if target == "cowork":
        root = sources._cowork_root()
        if root is not None:
            extra["COWORK_SESSIONS_DIR"] = str(root)
    extra.update(TEST_ENV)
    return _env(extra)


def _import_document(path: Path, document: dict, target: str, details: dict | None) -> tuple[str, str]:
    if not imports.has_conversation_body(document):
        return "failed", "这条会话没有可搬运的对话正文（为空或仅有工具日志），未写入目标软件。"
    environment = destination_env(target)
    imports.preflight(target, environment)
    if target == "copilot_desktop":
        report = copilot_import.import_document(document, Path(environment["COPILOT_HOME"]))
        if details is not None:
            details.update({"importedId": report["id"], "location": report["location"], "resumeCommand": "",
                            "notice": TARGETS[target]["notice"], "mode": "local",
                            "historicalToolNotes": report["historicalToolNotes"], "openUrl": copilot_import.LIST_URL})
        return "ok", "已复制到 Copilot，正在打开会话列表"
    moved = _run(["continue", str(path), "--with", TARGETS[target]["harness"], "--no-resume"], environment)
    if moved.returncode != 0:
        detail = (moved.stderr or moved.stdout or "").strip()
        log(f"continue failed -> {target}: {detail[-600:]}")
        return "failed", _friendly(detail)
    reports = [line.removeprefix("TXCRIPT_IMPORT_REPORT ") for line in moved.stdout.splitlines() if line.startswith("TXCRIPT_IMPORT_REPORT ")]
    if len(reports) != 1:
        raise ValueError("搬运组件版本不匹配，无法验证导入结果，请使用更新后的完整软件。")
    report = json.loads(reports[0])
    imported_id = str(report.get("id", ""))
    if not SAFE_ID.fullmatch(imported_id):
        raise ValueError("搬运组件未返回有效的导入编号，未登记搬运成功。")
    location = str(report.get("location", ""))
    if location.startswith('"'):
        location = json.loads(location)
    if target != "opencode" and not (Path(location).is_file() or target == "grok" and Path(location).is_dir()):
        raise ValueError("搬运组件没有生成预期的记录文件，未登记搬运成功。")
    verification = tempfile.NamedTemporaryFile(prefix="dm-verify-", suffix=".json", delete=False)
    verification_path = Path(verification.name)
    verification.close()
    try:
        reread = _run(["export", imported_id, "--from", TARGETS[target]["harness"], "--out", str(verification_path)], environment)
        verified = json.loads(verification_path.read_text(encoding="utf-8")) if reread.returncode == 0 else {}
        if not verified.get("messages"):
            raise ValueError("记录已写入，但重新读取验证失败。请查看日志，未登记为搬运成功。")
        if target in ("codex", "chatgpt_work"):
            try:
                codex_import.verify_body(document, verified)
            except ValueError:
                location_path = Path(location).resolve()
                sessions_root = (Path(environment["CODEX_HOME"]) / "sessions").resolve()
                if location_path.is_relative_to(sessions_root) and location_path.name.endswith(f"-{imported_id}.jsonl"):
                    location_path.unlink(missing_ok=True)
                raise
    finally:
        verification_path.unlink(missing_ok=True)
    if target == "qwen_work":
        try:
            imports.register_qwen(Path(location), imported_id, document, environment)
        except Exception:
            Path(location).unlink(missing_ok=True)
            Path(location).with_suffix(".txcript.json").unlink(missing_ok=True)
            raise
    historical_tool_notes = 0
    if target in ("codex", "chatgpt_work"):
        try:
            historical_tool_notes = codex_import.register(Path(location), imported_id, document, target, environment)
        except Exception:
            Path(location).unlink(missing_ok=True)
            raise
    if target == "doubao_work":
        context = Path(location).with_name("txcript-context.json")
        saved = {**document, "id": imported_id}
        context.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    resume = report.get("resume") or {}
    command = ""
    if TARGETS[target]["mode"] == "cli":
        arguments = [str(resume.get("binary", "")), *map(str, resume.get("args", []))]
        command = subprocess.list2cmdline(arguments) if sys.platform == "win32" else shlex.join(arguments)
    if details is not None:
        details.update({"importedId": imported_id, "location": location, "resumeCommand": command,
                        "notice": TARGETS[target].get("notice", ""), "mode": TARGETS[target]["mode"]})
        if target in ("codex", "chatgpt_work"):
            # ChatGPT reads its local list only at start-up; this link makes it open the thread by id
            details["openUrl"] = f"codex://threads/{imported_id}"
    message = "已写入本地记录文件" if TARGETS[target]["mode"] == "trajectory" else "已搬好"
    if isinstance(historical_tool_notes, int) and historical_tool_notes > 0:
        message += f"；{historical_tool_notes} 条未能完整配对的工具日志已作为历史说明保留，未补写执行结果。"
        if details is not None:
            details["historicalToolNotes"] = historical_tool_notes
    return "ok", message


def _move_cached_claude(session: dict, target: str, directory: str, details: dict | None = None) -> tuple[str, str]:
    """Copy a Claude desktop chat from the local cache. The source app is not modified."""
    from . import sources

    sid = str(session.get("id", ""))
    turns = sources.claude_body(sid)
    if not turns:
        return "failed", "这条对话的正文不在这台电脑上，暂时不能搬。"
    messages = []
    for turn in turns:
        message = {"role": turn["role"], "content": turn["content"]}
        if turn.get("timestamp"):
            message["timestamp"] = turn["timestamp"]
        messages.append(message)
    document = {"id": sid, "messages": messages}
    title = str(session.get("title") or "").strip()
    if title and title != "未命名对话":
        document["title"] = title
    document["cwd"] = directory
    handle = tempfile.NamedTemporaryFile(prefix="dm-", suffix=".json", delete=False)
    path = Path(handle.name)
    handle.close()
    try:
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        result = _import_document(path, document, target, details)
        if result[0] != "ok":
            return result
        _record_move("claude_desktop", sid, target, directory)
        log(f"moved claude_desktop/{sid} -> {target} in {directory}")
        return result
    except subprocess.TimeoutExpired:
        return "failed", "等待太久了，请稍后重试。"
    except ValueError as error:
        log(f"import validation claude_desktop/{sid}: {error}")
        return "failed", str(error)
    except Exception as error:  # noqa: BLE001
        log(f"unexpected claude_desktop/{sid}: {error!r}")
        return "failed", "这条对话暂时不能搬。"
    finally:
        path.unlink(missing_ok=True)


def move_one(source: str, session: dict, target: str, directory: str, details: dict | None = None) -> tuple[str, str]:
    """Copy one session. Returns (state, message) with state ok / skipped / failed."""
    sid = str(session.get("id", ""))
    source = str(session.get("source") or source)  # a unified list can mix stores
    if source not in SOURCES or target not in TARGETS:
        return "failed", "这个方向暂时不支持。"
    if not SAFE_ID.fullmatch(sid):
        return "failed", "这条对话的编号不正确。"
    if not directory or not Path(directory).is_dir():
        return "failed", "请先选好要放进去的文件夹。"
    if already_moved(source, sid, target, directory):
        if target == "copilot_desktop" and details is not None:
            # Older receipts intentionally contain no imported id. The fixed
            # list link can refresh these copies too, without another write.
            details.update({"openUrl": copilot_import.LIST_URL, "mode": "local"})
            return "skipped", "之前已复制到 Copilot，打开会话列表查看；不重复搬运。"
        return "skipped", "之前已经搬到这个文件夹了，不重复搬。"
    if source == "claude_desktop":
        return _move_cached_claude(session, target, directory, details)
    handle = tempfile.NamedTemporaryFile(prefix="dm-", suffix=".json", delete=False)
    path = Path(handle.name)
    handle.close()
    try:
        src_env = {}
        if source == "doubao_work":
            src_env["DOUBAO_WORK_DIR"] = str(doubao.workspace())
        if SOURCES[source] == "antigravity" and session.get("root"):
            src_env["ANTIGRAVITY_DIR"] = str(session["root"])
        if source == "cowork":
            from . import sources

            root = sources._cowork_root()
            if root is not None:
                src_env["COWORK_SESSIONS_DIR"] = str(root)
        if source == "chatgpt":
            src_env["TXCRIPT_CHATGPT_ACTIVE_ONLY"] = "1"
        if source == "copilot_desktop":
            document = copilot_local.document(sid)
        else:
            exported = _run(["export", sid, "--from", SOURCES[source], "--out", str(path)], src_env, timeout=300)
            if exported.returncode != 0:
                detail = (exported.stderr or exported.stdout or "").strip()
                log(f"export failed {source}/{sid}: {detail[-400:]}")
                return "failed", _friendly(detail)
            document = json.loads(path.read_text(encoding="utf-8"))
        document["cwd"] = directory
        title = str(session.get("title") or "").strip()
        if title and title != "未命名对话":
            document["title"] = title  # keep the title the user sees in the source app
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        result = _import_document(path, document, target, details)
        if result[0] != "ok":
            return result
        _record_move(source, sid, target, directory)
        log(f"moved {source}/{sid} -> {target} in {directory}")
        return result
    except subprocess.TimeoutExpired:
        return "failed", "等待太久了，请稍后重试。"
    except ValueError as error:
        log(f"import validation {source}/{sid}: {error}")
        return "failed", str(error)
    except Exception as error:  # noqa: BLE001 - keep the app alive, record the cause
        log(f"unexpected {source}/{sid}: {error!r}")
        return "failed", "这条对话暂时不能搬。"
    finally:
        path.unlink(missing_ok=True)


class Job:
    """One batch of sessions being copied in a background thread."""

    def __init__(self, source: str, sessions: list[dict], target: str, directory: str) -> None:
        self.source = source
        self.target = target
        self.directory = directory
        self.items = [
            {"id": s["id"], "title": s.get("title", ""), "state": "waiting", "message": ""} for s in sessions
        ]
        self._sessions = sessions
        self.finished = False
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        for index, session in enumerate(self._sessions):
            with self._lock:
                self.items[index]["state"] = "running"
            details = {}
            state, message = move_one(self.source, session, self.target, self.directory, details)
            with self._lock:
                self.items[index]["state"] = state
                self.items[index]["message"] = message
                self.items[index].update(details)
        with self._lock:
            self.finished = True

    def snapshot(self) -> dict:
        with self._lock:
            items = [dict(item) for item in self.items]
            done = sum(1 for item in items if item["state"] in ("ok", "skipped", "failed"))
            return {
                "finished": self.finished,
                "total": len(items),
                "done": done,
                "ok": sum(1 for item in items if item["state"] == "ok"),
                "skipped": sum(1 for item in items if item["state"] == "skipped"),
                "failed": sum(1 for item in items if item["state"] == "failed"),
                "items": items,
            }
