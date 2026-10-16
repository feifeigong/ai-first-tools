from __future__ import annotations

import os
import time
from dataclasses import asdict

from .app_server import AppServerClient, fetch_live_rate_limits
from .config import AppConfig
from .paths import resolve_codex_command, sessions_dir
from .quota import QuotaSnapshot, hint_reset_at, parse_quota_payload, quota_available, quota_recovered
from .redeem import try_redeem_weekly_reset
from .procutil import claim_watch_pid, process_running, release_watch_pid
from .resume import spawn_resume
from .sessions import WaitingSession, scan_waiting_sessions
from .state import AppState, load_state, save_state, upsert_thread


def _log(cfg: AppConfig, message: str) -> None:
    path = cfg.resolved_state_dir() / "daemon.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def tick(
    cfg: AppConfig,
    state: AppState | None = None,
    quota_reader: "LiveQuota | None" = None,
) -> AppState:
    now = time.time()
    state_dir = cfg.resolved_state_dir()
    state = state or load_state(state_dir)
    if not cfg.enabled:
        state.last_status = "disabled"
        save_state(state_dir, state)
        return state

    previous = parse_quota_payload(state.last_quota, source="state", fetched_at=state.last_checked_at)
    owned_reader = quota_reader is None
    reader = quota_reader or LiveQuota(cfg)
    try:
        snapshot = reader.read(now)
        if cfg.auto_redeem_weekly_reset and snapshot:
            previous_note = state.last_reset_credit_note
            snapshot, redeem_note = reader.try_redeem(snapshot, state, now)
            if redeem_note and redeem_note != previous_note:
                _log(cfg, redeem_note)
        recovered, reason = (
            quota_recovered(
                previous,
                snapshot,
                ready_used_percent=cfg.ready_used_percent,
                recovery_drop_percent=cfg.recovery_drop_percent,
                now=now,
            )
            if snapshot
            else (False, "quota-unknown")
        )
        if snapshot and snapshot.source != "app-server":
            recovered = False
            reason = "quota-unconfirmed"
        elif snapshot and snapshot.source == "app-server":
            live_ok, _live_reason = quota_available(snapshot, cfg.ready_used_percent, now)
            if not live_ok:
                state.last_live_blocked_at = now
        if snapshot and snapshot.source == "app-server":
            state.last_quota = asdict(snapshot)
            state.last_quota["primary"] = asdict(snapshot.primary) if snapshot.primary else None
            state.last_quota["secondary"] = asdict(snapshot.secondary) if snapshot.secondary else None
            state.last_quota["reset_credit_id"] = None
        state.last_quota_source = snapshot.source if snapshot else "none"
        state.last_checked_at = now
        state.last_status = reason

        since = now - cfg.lookback_hours * 3600
        waiting = (
            scan_waiting_sessions(
                sessions_dir(cfg.resolved_codex_home()),
                since=since,
                ready_used_percent=cfg.ready_used_percent,
            )
            if cfg.auto_discover
            else []
        )
        _log(cfg, f"quota={reason} source={state.last_quota_source} waiting={len(waiting)}")
        for item in waiting:
            current = state.threads.get(item.thread_id)
            if current and not current.enabled:
                continue
            upsert_thread(
                state,
                item.thread_id,
                cwd=item.cwd or (current.cwd if current else None),
                status="waiting",
                mark=item.mark,
                resets_at=item.resets_at,
                observed_at=item.observed_at,
                enabled=True if current is None else current.enabled,
            )

        for thread_id, task in list(state.threads.items()):
            if not task.enabled:
                continue
            if process_running(task.pid, started_at=task.last_resume_at or None):
                task.status = "running"
                continue
            if task.phase == "submitting":
                task.phase = "needs-review"
                task.status = "needs-review"
                task.last_error = "上次续跑提交未确认完成，已停止自动重试，避免重复执行"
                continue
            match = next((item for item in waiting if item.thread_id == thread_id), None)
            if match is None:
                continue
            if task.phase == "failed" and task.failed_mark == match.mark:
                task.status = "resume-failed"
                continue
            if task.handled_mark == match.mark:
                task.status = "already-handled"
                continue
            if recovered and not _cycle_open(task, state):
                task.status = "already-handled"
                continue
            if not recovered:
                task.status = reason
                if snapshot:
                    task.resets_at = hint_reset_at(snapshot, cfg.ready_used_percent) or task.resets_at
                continue
            _resume_one(cfg, state, task, match, now)

        save_state(state_dir, state)
        return state
    finally:
        if owned_reader:
            reader.close()


def watch_forever(cfg: AppConfig) -> None:
    state_dir = cfg.resolved_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "watch.pid"
    if not claim_watch_pid(lock_path):
        raise RuntimeError("已经有一个 watch 在运行，不要同时开两个")
    stop_file = state_dir / "stop.request"
    stop_file.unlink(missing_ok=True)
    reader = LiveQuota(cfg)
    try:
        while not stop_file.exists():
            try:
                state = tick(cfg, quota_reader=reader)
            except Exception as exc:
                _log(cfg, f"tick failed: {exc}")
                _wait_or_stop(stop_file, max(5.0, float(cfg.poll_seconds)))
                continue
            delay = max(5.0, float(cfg.poll_seconds))
            resets = [
                task.resets_at
                for task in state.threads.values()
                if task.enabled
                and task.resets_at
                and task.status not in {"resumed", "already-handled", "resume-cap-reached"}
            ]
            if resets:
                soonest = min(resets) + cfg.reset_buffer_seconds - time.time()
                if 0 < soonest < delay:
                    delay = max(5.0, soonest)
            _wait_or_stop(stop_file, delay)
    finally:
        reader.close()
        release_watch_pid(lock_path)


def _wait_or_stop(stop_file, delay: float) -> None:
    deadline = time.monotonic() + delay
    while not stop_file.exists():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.25, remaining))


class LiveQuota:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg
        self.client: AppServerClient | None = None

    def read(self, now: float) -> QuotaSnapshot | None:
        try:
            payload = self._live_payload()
            parsed = parse_quota_payload(payload, source="app-server", fetched_at=now)
            if parsed:
                return parsed
        except Exception as exc:
            self.close()
            _log(self.cfg, f"app-server quota failed: {exc}")
        return None

    def try_redeem(
        self,
        snapshot: QuotaSnapshot,
        state: AppState,
        now: float,
    ) -> tuple[QuotaSnapshot, str]:
        if self.client is None:
            return snapshot, ""
        return try_redeem_weekly_reset(
            cfg=self.cfg,
            snapshot=snapshot,
            state=state,
            now=now,
            client=self.client,
        )

    def _live_payload(self) -> dict:
        if self.client is None:
            env = os.environ.copy()
            env["CODEX_HOME"] = str(self.cfg.resolved_codex_home())
            self.client = AppServerClient(
                resolve_codex_command(self.cfg.codex_bin or None),
                env=env,
                timeout=18,
            )
            self.client.start()
        return self.client.read_rate_limits(include_credits=False)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None


def read_quota(cfg: AppConfig, now: float) -> QuotaSnapshot | None:
    env = {"CODEX_HOME": str(cfg.resolved_codex_home())}
    try:
        payload = fetch_live_rate_limits(
            codex_bin=cfg.codex_bin or None,
            extra_env=env,
            timeout=18,
            include_credits=True,
        )
        parsed = parse_quota_payload(payload, source="app-server", fetched_at=now)
        if parsed:
            return parsed
    except Exception as exc:
        _log(cfg, f"app-server quota failed: {exc}")
    return None


def _cycle_open(task, state: AppState) -> bool:
    """同一轮实时限额只续一次。新的一轮要先看到实时额度再次用尽。"""
    if not task.last_resume_at:
        return True
    return state.last_live_blocked_at > task.last_resume_at


def _resume_one(
    cfg: AppConfig,
    state: AppState,
    task,
    waiting: WaitingSession | None,
    now: float,
) -> None:
    if waiting:
        task.mark = waiting.mark
        task.cwd = waiting.cwd or task.cwd
        task.resets_at = waiting.resets_at
    log_file = cfg.resolved_state_dir() / "logs" / f"{task.thread_id}.log"
    task.phase = "submitting"
    task.status = "resuming"
    task.last_resume_at = now
    save_state(cfg.resolved_state_dir(), state)
    try:
        pid, mode = spawn_resume(
            thread_id=task.thread_id,
            prompt=cfg.resume_prompt,
            cwd=task.cwd,
            log_file=log_file,
            extra_args=list(cfg.extra_resume_args),
            skip_git_repo_check=cfg.skip_git_repo_check,
            prefer_queue_if_busy=cfg.prefer_queue_if_busy,
            codex_bin=cfg.codex_bin or None,
            extra_env={"CODEX_HOME": str(cfg.resolved_codex_home())},
        )
        task.pid = pid
        task.phase = "sent"
        task.status = "resumed"
        task.resumes += 1
        task.handled_mark = task.mark
        task.failed_mark = ""
        task.log_file = str(log_file)
        task.last_error = mode
    except Exception as exc:
        task.phase = "failed"
        task.status = "resume-failed"
        task.failed_mark = task.mark
        task.last_error = str(exc)
        task.log_file = str(log_file)
