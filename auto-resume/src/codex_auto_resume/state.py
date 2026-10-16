from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ThreadState:
    thread_id: str
    enabled: bool = True
    cwd: str | None = None
    name: str = ""
    status: str = "watching"
    mark: str = ""
    resets_at: int | None = None
    observed_at: float = 0.0
    resumes: int = 0
    handled_mark: str = ""
    failed_mark: str = ""
    phase: str = "idle"
    pid: int | None = None
    log_file: str | None = None
    last_error: str = ""
    last_resume_at: float = 0.0


@dataclass
class AppState:
    version: int = 1
    threads: dict[str, ThreadState] = field(default_factory=dict)
    last_status: str = "idle"
    last_quota_source: str = ""
    last_checked_at: float = 0.0
    last_quota: dict[str, Any] = field(default_factory=dict)
    last_reset_credit_at: float = 0.0
    last_reset_credit_id: str = ""
    last_reset_credit_note: str = ""
    last_live_blocked_at: float = 0.0


def state_path(state_dir: Path) -> Path:
    return state_dir / "state.json"


def _quarantine_state(path: Path) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path.with_name(f"state.json.broken-{stamp}")
    try:
        path.replace(dest)
    except OSError:
        try:
            path.unlink()
        except OSError:
            pass


def _note(state_dir: Path, message: str) -> None:
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "daemon.log"
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {message}\n")
    except OSError:
        pass


def load_state(state_dir: Path) -> AppState:
    path = state_path(state_dir)
    if not path.exists():
        return AppState()
    try:
        text = path.read_text(encoding="utf-8").strip("\x00").strip()
        raw = json.loads(text) if text else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raw = None
    if not isinstance(raw, dict):
        _quarantine_state(path)
        _note(state_dir, "state.json 已损坏，已挪走并从头记录。之前跟踪过的对话会按最近会话重新发现")
        return AppState()
    threads = {}
    for key, value in (raw.get("threads") or {}).items():
        if not isinstance(value, dict):
            continue
        value = {**value, "thread_id": value.get("thread_id") or key}
        allowed = {k: value[k] for k in ThreadState.__dataclass_fields__ if k in value}
        threads[key] = ThreadState(**allowed)
    status = str(raw.get("last_status") or "idle")
    checked_at = float(raw.get("last_checked_at") or 0)
    if "last_live_blocked_at" in raw:
        blocked_at = float(raw.get("last_live_blocked_at") or 0)
    elif status.startswith(("reached", "window", "spend", "ordinary")):
        blocked_at = checked_at
    else:
        blocked_at = 0.0
    return AppState(
        version=int(raw.get("version") or 1),
        threads=threads,
        last_status=status,
        last_quota_source=str(raw.get("last_quota_source") or ""),
        last_checked_at=checked_at,
        last_quota=raw.get("last_quota") if isinstance(raw.get("last_quota"), dict) else {},
        last_reset_credit_at=float(raw.get("last_reset_credit_at") or 0),
        last_reset_credit_id=str(raw.get("last_reset_credit_id") or ""),
        last_reset_credit_note=str(raw.get("last_reset_credit_note") or ""),
        last_live_blocked_at=blocked_at,
    )


def save_state(state_dir: Path, state: AppState) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(state_dir)
    payload: dict[str, Any] = {
        "version": state.version,
        "last_status": state.last_status,
        "last_quota_source": state.last_quota_source,
        "last_checked_at": state.last_checked_at,
        "last_quota": state.last_quota,
        "last_reset_credit_at": state.last_reset_credit_at,
        "last_reset_credit_id": state.last_reset_credit_id,
        "last_reset_credit_note": state.last_reset_credit_note,
        "last_live_blocked_at": state.last_live_blocked_at,
        "threads": {key: asdict(value) for key, value in state.threads.items()},
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def upsert_thread(state: AppState, thread_id: str, **changes: Any) -> ThreadState:
    current = state.threads.get(thread_id) or ThreadState(thread_id=thread_id)
    for key, value in changes.items():
        setattr(current, key, value)
    state.threads[thread_id] = current
    return current
