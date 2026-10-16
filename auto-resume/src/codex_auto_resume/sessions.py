from __future__ import annotations

import json
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
    if not sessions_root.exists():
        return []
    files: list[Path] = []
    for path in sessions_root.rglob("*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= since:
            files.append(path)
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return files


def scan_waiting_sessions(
    sessions_root: Path,
    *,
    since: float,
    ready_used_percent: float,
) -> list[WaitingSession]:
    found: dict[str, WaitingSession] = {}
    for path in iter_recent_rollouts(sessions_root, since):
        parsed = inspect_rollout(path, since=since, ready_used_percent=ready_used_percent)
        if parsed is None:
            continue
        previous = found.get(parsed.thread_id)
        if previous is None or parsed.observed_at >= previous.observed_at:
            found[parsed.thread_id] = parsed
    return sorted(found.values(), key=lambda item: item.observed_at, reverse=True)


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
    thread_id = _thread_id_from_name(path.name)
    cwd: str | None = None
    last_snapshot: QuotaSnapshot | None = None
    last_limit_at: float | None = None
    last_limit_reset: int | None = None
    later_activity = False
    last_event_at = 0.0

    try:
        handle = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            rec = _loads(line)
            if rec is None:
                continue
            event_at = _event_time(rec) or 0.0
            last_event_at = max(last_event_at, event_at)
            payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
            rec_type = str(rec.get("type") or "")
            payload_type = str(payload.get("type") or "")

            if rec_type == "session_meta" or payload_type == "session_meta":
                meta = payload if payload else rec
                ident = meta.get("id") or (payload.get("id") if payload else None)
                if isinstance(ident, str) and THREAD_RE.fullmatch(ident):
                    thread_id = ident
                raw_cwd = meta.get("cwd") or payload.get("cwd")
                if isinstance(raw_cwd, str) and raw_cwd:
                    cwd = raw_cwd

            snapshot = _extract_snapshot(rec, fetched_at=event_at or path.stat().st_mtime)
            if snapshot is not None:
                last_snapshot = snapshot
                if _snapshot_exhausted(snapshot, ready_used_percent):
                    last_limit_at = event_at or path.stat().st_mtime
                    last_limit_reset = _limit_reset(snapshot, ready_used_percent)
                    later_activity = False

            if _looks_like_limit_error(rec, payload):
                last_limit_at = event_at or path.stat().st_mtime
                later_activity = False

            if last_limit_at and event_at > last_limit_at and _is_progress_event(rec_type, payload):
                later_activity = True

    if thread_id is None:
        return None
    observed = last_limit_at or (last_snapshot.fetched_at if last_snapshot else 0.0)
    if require_waiting:
        if last_limit_at is None or last_limit_at < since or later_activity:
            return None
    elif last_snapshot is None:
        return None
    mark = f"{path.name}:{int(last_limit_at or last_event_at)}:{last_limit_reset or 0}"
    return WaitingSession(
        thread_id=thread_id,
        cwd=cwd,
        path=path,
        mark=mark,
        resets_at=last_limit_reset or (last_snapshot and _limit_reset(last_snapshot, ready_used_percent)),
        observed_at=observed or path.stat().st_mtime,
        snapshot=last_snapshot,
        reason="usage-limit" if last_limit_at else "quota-snapshot",
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
    if payload_type in {"agent_message", "message"} and role in {"user", "assistant"}:
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
