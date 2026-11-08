from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .quota import QuotaSnapshot, parse_quota_payload

THREAD_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
LIMIT_TEXT = (
    "you've hit your usage limit",
    "you have hit your usage limit",
    "usage limit reached",
    "hit your usage limit",
    "try again at",
)


@dataclass
class WaitingSession:
    thread_id: str
    cwd: str | None
    path: Path
    mark: str
    resets_at: int | None
    observed_at: float
    snapshot: QuotaSnapshot | None
    reason: str


def iter_recent_rollouts(sessions_root: Path, since: float) -> list[Path]:
    files: list[tuple[float, Path]] = []

    def unavailable_directory(error: OSError) -> None:
        # pathlib glob can silently omit an inaccessible subtree. A partial
        # listing cannot prove that an older waiting rollout is still current.
        raise error

    try:
        for directory, _directories, names in os.walk(
            sessions_root, onerror=unavailable_directory, followlinks=False,
        ):
            for name in names:
                if not name.lower().endswith(".jsonl"):
                    continue
                path = Path(directory) / name
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    # Keep the path so inspection can still try to establish
                    # its canonical identity; never silently omit a copy.
                    files.append((float("inf"), path))
                    continue
                if mtime >= since:
                    files.append((mtime, path))
    except OSError:
        # Retry on the next poll; this does not disable the user's settings.
        return []
    files.sort(key=lambda item: item[0], reverse=True)
    return [path for _mtime, path in files]


# Positive evidence is required. A missing source must not inherit Codex's
# deserialization default (VSCode), and originator is shared by child threads.
MAIN_SOURCES = frozenset({"cli", "vscode", "exec", "mcp"})


def _is_main_session(meta: dict[str, Any]) -> bool:
    ident = meta.get("id")
    source = meta.get("source")
    return (
        isinstance(ident, str) and THREAD_RE.fullmatch(ident) is not None
        and isinstance(source, str) and source in MAIN_SOURCES
        and meta.get("thread_source") in (None, "user")
        and meta.get("parent_thread_id") is None
        and meta.get("agent_path") in (None, "/root")
        and meta.get("subagent_history_start_ordinal") is None
    )


@dataclass
class _RolloutInspection:
    session: WaitingSession
    is_main: bool
    waiting: bool
    latest_event_at: float
    canonical_identity_known: bool


def scan_waiting_sessions(
    sessions_root: Path,
    *,
    since: float,
    ready_used_percent: float,
) -> list[WaitingSession]:
    # Inspect non-waiting files too: otherwise a newer continued/completed log
    # is discarded and an older limit for the same thread becomes eligible.
    grouped: dict[str, list[_RolloutInspection]] = {}
    blocked: set[str] = set()
    for path in iter_recent_rollouts(sessions_root, since):
        parsed = _inspect_rollout(path, since=since, ready_used_percent=ready_used_percent)
        if parsed is None or not parsed.canonical_identity_known:
            # A filename can differ from the stable thread ID. Without a valid
            # first header, this file may supersede any older waiting copy.
            # Retry a complete scan next poll rather than authorize a partial one.
            return []
        thread_id = parsed.session.thread_id
        if not parsed.is_main:
            blocked.add(thread_id)
        grouped.setdefault(thread_id, []).append(parsed)
    found: list[WaitingSession] = []
    for thread_id, records in grouped.items():
        if thread_id in blocked:
            continue
        latest = max(item.latest_event_at for item in records)
        newest = [item for item in records if item.latest_event_at == latest]
        if any(not item.waiting for item in newest):
            continue
        # A deterministic tie avoids changing marks just because rglob order
        # changed. Conflicting/inactive records above always win conservatively.
        chosen = min(newest, key=lambda item: str(item.session.path))
        found.append(chosen.session)
    return sorted(found, key=lambda item: item.observed_at, reverse=True)


def validate_waiting_session(
    waiting: WaitingSession, sessions_root: Path, *, since: float, ready_used_percent: float,
) -> bool:
    """Recheck all files: a newly created continuation may supersede waiting.path."""
    return any(
        current.thread_id == waiting.thread_id and current.mark == waiting.mark
        and current.cwd == waiting.cwd
        for current in scan_waiting_sessions(
            sessions_root, since=since, ready_used_percent=ready_used_percent,
        )
    )


def latest_quota_from_rollouts(sessions_root: Path, since: float) -> QuotaSnapshot | None:
    newest: QuotaSnapshot | None = None
    for path in iter_recent_rollouts(sessions_root, since):
        parsed = inspect_rollout(path, since=since, ready_used_percent=99.0, require_waiting=False)
        if parsed is None or parsed.snapshot is None:
            continue
        if newest is None or parsed.snapshot.fetched_at >= newest.fetched_at:
            newest = parsed.snapshot
    return newest


def inspect_rollout(
    path: Path,
    *,
    since: float,
    ready_used_percent: float,
    require_waiting: bool = True,
) -> WaitingSession | None:
    parsed = _inspect_rollout(path, since=since, ready_used_percent=ready_used_percent)
    if parsed is None:
        return None
    if require_waiting:
        return parsed.session if parsed.is_main and parsed.waiting else None
    # Reading account telemetry does not authorize resuming its originating
    # thread. LiveQuota still treats rollout quota as unconfirmed.
    return parsed.session if parsed.session.snapshot is not None else None


def _inspect_rollout(
    path: Path,
    *,
    since: float,
    ready_used_percent: float,
) -> _RolloutInspection | None:
    # A filename UUID is only a grouping hint for an unidentifiable file. A
    # valid canonical SessionMeta.id is authoritative (revert changes rollout IDs).
    thread_id = _thread_id_from_name(path.name)
    cwd: str | None = None
    last_snapshot: QuotaSnapshot | None = None
    last_limit_at: float | None = None
    last_limit_reset: int | None = None
    later_activity = False
    last_event_at = 0.0
    metadata_seen = False
    canonical_identity_known = False
    is_main = False
    first_record = True
    malformed = False
    inherited_history = False

    mtime = 0.0
    try:
        mtime = path.stat().st_mtime
    except OSError:
        # The header may still be readable. If so, veto this canonical thread
        # without blocking other independently verified main tasks.
        malformed = True
    try:
        handle = path.open("r", encoding="utf-8-sig")
    except OSError:
        return None
    try:
        with handle:
            for line in handle:
                if not line.strip():
                    continue
                rec = _loads(line)
                if rec is None:
                    malformed = True
                    first_record = False
                    continue
                event_at = _event_time(rec) or 0.0
                last_event_at = max(last_event_at, event_at)
                payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
                rec_type = str(rec.get("type") or "")
                payload_type = str(payload.get("type") or "")

                if rec_type == "session_meta" or payload_type == "session_meta":
                    # Fork history may contain copied ancestor metadata.
                    # Codex treats the first header as canonical; later headers
                    # must never promote a child/unknown session to a main one.
                    if metadata_seen:
                        inherited_history = True
                        continue
                    meta = payload if payload else rec
                    if not first_record:
                        malformed = True
                    metadata_seen = True
                    is_main = _is_main_session(meta)
                    inherited_history = any(meta.get(key) is not None for key in (
                        "forked_from_id", "forked_from_ordinal_exclusive", "history_base",
                    ))
                    ident = meta.get("id")
                    if isinstance(ident, str) and THREAD_RE.fullmatch(ident):
                        thread_id = ident
                        canonical_identity_known = first_record
                    raw_cwd = meta.get("cwd")
                    if isinstance(raw_cwd, str) and raw_cwd:
                        cwd = raw_cwd
                first_record = False

                limited = False
                snapshot = _extract_snapshot(rec, fetched_at=event_at or mtime)
                if snapshot is not None:
                    last_snapshot = snapshot
                    if _snapshot_exhausted(snapshot, ready_used_percent):
                        last_limit_at = event_at or mtime
                        last_limit_reset = _limit_reset(snapshot, ready_used_percent)
                        later_activity = False
                        limited = True

                if _looks_like_limit_error(rec, payload):
                    last_limit_at = event_at or mtime
                    later_activity = False
                    limited = True

                # File order matters even when adjacent events have equal
                # timestamps. Do not treat terminal usage-limit errors as progress.
                if last_limit_at is not None and not limited and _is_progress_event(rec_type, payload):
                    later_activity = True
    except (OSError, UnicodeError):
        malformed = True

    if thread_id is None:
        return None
    observed = last_limit_at or (last_snapshot.fetched_at if last_snapshot else 0.0)
    # Copied history can contain an ancestor's limit with rewritten timestamps.
    # Until own-history ordinal boundaries are verified, a fork/revert with
    # inherited history is not evidence that this task itself hit its limit.
    waiting = (last_limit_at is not None and last_limit_at >= since
               and not later_activity and not inherited_history)
    mark = f"{path.name}:{int(last_limit_at or last_event_at)}:{last_limit_reset or 0}"
    session = WaitingSession(
        thread_id=thread_id,
        cwd=cwd,
        path=path,
        mark=mark,
        resets_at=last_limit_reset or (last_snapshot and _limit_reset(last_snapshot, ready_used_percent)),
        observed_at=observed or mtime,
        snapshot=last_snapshot,
        reason="usage-limit" if last_limit_at else "quota-snapshot",
    )
    return _RolloutInspection(
        session, metadata_seen and is_main and not malformed, waiting,
        last_event_at or mtime, canonical_identity_known,
    )


def _extract_snapshot(rec: dict[str, Any], fetched_at: float) -> QuotaSnapshot | None:
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else rec
    candidates: Iterable[Any] = (
        payload.get("rate_limits") if isinstance(payload, dict) else None,
        payload.get("rateLimits") if isinstance(payload, dict) else None,
        rec.get("rate_limits"),
        rec.get("rateLimits"),
        payload,
    )
    for item in candidates:
        parsed = parse_quota_payload(item, source="rollout", fetched_at=fetched_at)
        if parsed and (parsed.windows or parsed.rate_limit_reached_type):
            return parsed
    return None


def _snapshot_exhausted(snapshot: QuotaSnapshot, ready_used_percent: float) -> bool:
    if snapshot.rate_limit_reached_type:
        return True
    return any(
        w.used_percent is not None and w.used_percent >= ready_used_percent for w in snapshot.windows
    )


def _limit_reset(snapshot: QuotaSnapshot, ready_used_percent: float) -> int | None:
    stamps = [
        window.resets_at
        for window in snapshot.windows
        if window.resets_at
        and window.used_percent is not None
        and window.used_percent >= ready_used_percent
    ]
    return max(stamps) if stamps else None


def _looks_like_limit_error(rec: dict[str, Any], payload: dict[str, Any]) -> bool:
    # Ordinary user/agent prose may quote an error or say "try again at".
    # Only error events/containers can be evidence of a usage-limit failure.
    if (rec.get("type") != "error"
            and payload.get("type") not in {"error", "task_complete", "turn_complete"}
            and not isinstance(rec.get("error"), dict)):
        return False
    blobs: list[str] = []
    for item in (payload, rec.get("error") if isinstance(rec.get("error"), dict) else None, payload.get("error")):
        if not isinstance(item, dict):
            continue
        code = item.get("codex_error_info") or item.get("codexErrorInfo")
        if isinstance(code, str) and code.replace("_", "").lower() == "usagelimitexceeded":
            return True
        for key in ("message", "error", "reason"):
            value = item.get(key)
            if isinstance(value, str):
                blobs.append(value.lower())
    return any(text in blob for blob in blobs for text in LIMIT_TEXT)


def _is_progress_event(rec_type: str, payload: dict[str, Any]) -> bool:
    payload_type = str(payload.get("type") or "")
    role = str(payload.get("role") or "")
    if rec_type == "response_item" and payload_type == "message" and role in {"user", "assistant"}:
        return True
    if rec_type == "event_msg" and payload_type in {
        "agent_message", "user_message", "task_started", "turn_started",
        "task_complete", "turn_complete", "turn_aborted",
    }:
        return True
    if payload_type == "message" and role in {"user", "assistant"}:
        return True
    return False


def _thread_id_from_name(name: str) -> str | None:
    matches = THREAD_RE.findall(name)
    if not matches:
        return None
    return matches[0]


def _event_time(rec: dict[str, Any]) -> float | None:
    raw = rec.get("timestamp")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        stamp = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(stamp).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


def _loads(line: str) -> dict[str, Any] | None:
    text = line.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None
