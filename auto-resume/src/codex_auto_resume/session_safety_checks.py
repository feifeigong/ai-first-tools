"""Synthetic checks in both frozen packages; native processes and network are blocked."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from unittest.mock import patch

from . import daemon, sessions
from .app_server import AppServerClient
from .config import AppConfig
from .quota import QuotaSnapshot, QuotaWindow
from .state import AppState, ThreadState


def run() -> dict[str, bool]:
    main_id = "00000001-1111-4111-8111-111111111111"
    stamp = datetime.fromtimestamp(time.time() - 10, timezone.utc).isoformat()
    forbidden_calls = []

    def forbid(*args, **kwargs):
        forbidden_calls.append(True)
        raise AssertionError("Real process, account and network access forbidden in session audit")

    def require(value):
        if not value:
            raise AssertionError("Frozen main-session safety regression")

    class OfflineQuota:
        def read(self, now):
            return QuotaSnapshot(
                primary=QuotaWindow(0, int(now + 3600), 300),
                secondary=QuotaWindow(10, int(now + 86400), 10080),
                source="app-server", fetched_at=now,
            )

        try_redeem = staticmethod(forbid)
        start_window = staticmethod(forbid)

    with tempfile.TemporaryDirectory(prefix="session-frozen-synthetic-") as temporary, ExitStack() as guards:
        root = Path(temporary)
        guards.enter_context(patch.object(subprocess, "Popen", side_effect=forbid))
        guards.enter_context(patch.object(socket.socket, "connect", side_effect=forbid))
        guards.enter_context(patch.object(socket.socket, "connect_ex", side_effect=forbid))
        guards.enter_context(patch.object(AppServerClient, "start", side_effect=forbid))
        guards.enter_context(patch.object(daemon, "LiveQuota", side_effect=forbid))
        guards.enter_context(patch.object(daemon, "process_running", return_value=False))
        spawn = guards.enter_context(patch.object(daemon, "spawn_resume", return_value=(999999, "synthetic-only")))

        def config(name):
            directory = root / name
            (directory / "codex" / "sessions").mkdir(parents=True)
            return AppConfig(codex_home=str(directory / "codex"), state_dir=str(directory / "state"),
                             auto_redeem_weekly_reset=False, auto_start_five_hour=False)

        def write(cfg, ident, source, *, missing_source=False):
            meta = {"id": ident, "source": source, "originator": "codex_cli_rs",
                    "cwd": str(cfg.resolved_codex_home().parent)}
            if missing_source:
                del meta["source"]
            rows = [
                {"timestamp": stamp, "type": "session_meta", "payload": meta},
                {"timestamp": stamp, "type": "event_msg", "payload": {
                    "type": "error", "codex_error_info": "usage_limit_exceeded"}},
            ]
            path = cfg.resolved_codex_home() / "sessions" / f"rollout-{ident}.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            return path

        cfg = config("six-waiters")
        write(cfg, main_id, "cli")
        children = []
        for number in range(2, 7):
            ident = f"{number:08d}-1111-4111-8111-111111111111"
            children.append(ident)
            source = ({"internal": "guardian"} if number == 6 else
                      {"subagent": {"thread_spawn": {"parent_thread_id": main_id, "depth": 1}}})
            write(cfg, ident, source)
        found = sessions.scan_waiting_sessions(cfg.resolved_codex_home() / "sessions", since=0, ready_used_percent=99)
        require([item.thread_id for item in found] == [main_id])
        state = AppState(threads={ident: ThreadState(thread_id=ident, status="waiting") for ident in children})
        state = daemon.tick(cfg, state=state, quota_reader=OfflineQuota())
        require(spawn.call_count == 1 and spawn.call_args.kwargs["thread_id"] == main_id)
        require(state.threads[main_id].resumes == 1 and all(state.threads[ident].resumes == 0 for ident in children))

        spawn.reset_mock()
        cfg = config("unknown-identities")
        unknown = []
        for number, source in enumerate((None, "unknown", "cli"), 7):
            ident = f"{number:08d}-1111-4111-8111-111111111111"
            unknown.append(ident)
            write(cfg, ident, source, missing_source=number == 9)
        require(not sessions.scan_waiting_sessions(cfg.resolved_codex_home() / "sessions", since=0, ready_used_percent=99))
        state = AppState(threads={ident: ThreadState(thread_id=ident, status="waiting") for ident in unknown})
        state = daemon.tick(cfg, state=state, quota_reader=OfflineQuota())
        require(not spawn.called and all(task.resumes == 0 for task in state.threads.values()))

        cfg = config("continued-before-submit")
        path = write(cfg, main_id, "cli")

        def scan_then_continue(*args, **kwargs):
            found = sessions.scan_waiting_sessions(*args, **kwargs)
            require([item.thread_id for item in found] == [main_id])
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"timestamp": stamp, "type": "event_msg", "payload": {
                    "type": "user_message", "message": "Synthetic continuation"}}) + "\n")
            return found

        with patch.object(daemon, "scan_waiting_sessions", side_effect=scan_then_continue):
            state = daemon.tick(cfg, state=AppState(), quota_reader=OfflineQuota())
        task = state.threads[main_id]
        require(not spawn.called and task.resumes == 0 and task.last_resume_at == 0)
        require(task.phase != "submitting" and task.status == "session-unverified")
        require(not forbidden_calls)
    return {"mainSessionIdentityFiltering": True, "unknownSessionIdentityRejected": True,
            "continuedSessionBlockedAtSubmission": True}
