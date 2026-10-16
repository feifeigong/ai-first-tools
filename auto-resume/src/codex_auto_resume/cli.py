from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .app_server import doctor_app_server
from .config import AppConfig, load_config, save_config
from .daemon import read_quota, tick, watch_forever
from .paths import resolve_codex_command, sessions_dir, tool_root
from .quota import hint_reset_at, parse_quota_payload, quota_available
from .sessions import scan_waiting_sessions
from .state import load_state, save_state, upsert_thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codex-auto-resume",
        description="Codex Plus 额度恢复后，按原 thread 自动续跑",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="检查 Codex、额度接口和会话目录")
    sub.add_parser("status", help="查看当前等待中的任务和额度")
    once = sub.add_parser("once", help="扫描一次，额度已恢复则续跑")
    once.add_argument("--dry-run", action="store_true")
    watch = sub.add_parser("watch", help="常驻守护，额度恢复后自动续跑")
    watch.add_argument("--quiet", action="store_true")
    enable = sub.add_parser("enable", help="强制跟踪某个 thread id")
    enable.add_argument("thread_id")
    disable = sub.add_parser("disable", help="停止跟踪某个 thread id")
    disable.add_argument("thread_id")
    sub.add_parser("install-autostart", help="安装开机/登录自启")
    sub.add_parser("uninstall-autostart", help="移除开机/登录自启")

    args = parser.parse_args(argv)
    cfg = load_config()
    save_config(cfg)

    if args.cmd == "doctor":
        return cmd_doctor(cfg)
    if args.cmd == "status":
        return cmd_status(cfg)
    if args.cmd == "once":
        return cmd_once(cfg, dry_run=args.dry_run)
    if args.cmd == "watch":
        if not args.quiet:
            print("codex-auto-resume 已启动，按 Ctrl+C 结束", flush=True)
        try:
            watch_forever(cfg)
        except KeyboardInterrupt:
            return 0
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0
    if args.cmd == "enable":
        return cmd_enable(cfg, args.thread_id, True)
    if args.cmd == "disable":
        return cmd_enable(cfg, args.thread_id, False)
    if args.cmd == "install-autostart":
        return cmd_autostart(True)
    if args.cmd == "uninstall-autostart":
        return cmd_autostart(False)
    return 2


def cmd_doctor(cfg: AppConfig) -> int:
    print(f"version          {__version__}")
    print(f"codex_home       {cfg.resolved_codex_home()}")
    print(f"sessions         {sessions_dir(cfg.resolved_codex_home())}")
    print(f"state_dir        {cfg.resolved_state_dir()}")
    try:
        command = resolve_codex_command(cfg.codex_bin or None)
        print(f"codex            {' '.join(command)}")
    except FileNotFoundError as exc:
        print(f"codex            FAIL {exc}")
        return 1
    sessions = sessions_dir(cfg.resolved_codex_home())
    print(f"sessions_exist   {sessions.exists()}")
    ok, message, payload = doctor_app_server(cfg.resolved_codex_home(), cfg.codex_bin or None)
    print(f"app_server       {'OK' if ok else 'FAIL'} {message}")
    snap = parse_quota_payload(payload, source="app-server") if payload else None
    if snap and snap.primary:
        print(f"5h               {snap.primary.used_percent}%")
    if snap and snap.secondary:
        print(f"weekly           {snap.secondary.used_percent}%")
    if snap and snap.reset_credit_count is not None:
        print(f"reset_credits    {snap.reset_credit_count}")
    now = time.time()
    waiting = scan_waiting_sessions(
        sessions,
        since=now - cfg.lookback_hours * 3600,
        ready_used_percent=cfg.ready_used_percent,
    )
    print(f"waiting_threads  {len(waiting)}")
    for item in waiting[:8]:
        print(f"  - {item.thread_id}  reset={item.resets_at}  {item.reason}")
    return 0 if ok or sessions.exists() else 1


def cmd_status(cfg: AppConfig) -> int:
    now = time.time()
    snapshot = read_quota(cfg, now)
    if snapshot:
        available, reason = quota_available(snapshot, cfg.ready_used_percent, now)
        reset_at = hint_reset_at(snapshot, cfg.ready_used_percent)
        print(f"quota            {reason}  available={available}  source={snapshot.source}")
        print(f"plan             {snapshot.plan_type or '-'}")
        print(f"reset_at         {reset_at or '-'}")
        print(f"reset_credits    {snapshot.reset_credit_count if snapshot.reset_credit_count is not None else '-'}")
        print(f"auto_redeem      {cfg.auto_redeem_weekly_reset}")
        if snapshot.primary:
            print(
                f"5h               {snapshot.primary.used_percent}%  resets_at={snapshot.primary.resets_at}"
            )
        if snapshot.secondary:
            print(
                f"weekly           {snapshot.secondary.used_percent}%  resets_at={snapshot.secondary.resets_at}"
            )
    else:
        print("quota            unknown")
    state = load_state(cfg.resolved_state_dir())
    if state.last_reset_credit_note:
        print(f"last_redeem      {state.last_reset_credit_note}")
    if not state.threads:
        print("threads          (empty)")
        return 0
    print("threads")
    for task in state.threads.values():
        print(
            f"  - {task.thread_id}  enabled={task.enabled}  status={task.status}  "
            f"resumes={task.resumes}"
        )
    return 0


def cmd_once(cfg: AppConfig, dry_run: bool = False) -> int:
    if dry_run:
        cfg = AppConfig(**{**cfg.__dict__, "enabled": False})
        waiting = scan_waiting_sessions(
            sessions_dir(cfg.resolved_codex_home()),
            since=time.time() - cfg.lookback_hours * 3600,
            ready_used_percent=cfg.ready_used_percent,
        )
        print(f"dry-run waiting={len(waiting)}")
        for item in waiting:
            print(f"  {item.thread_id}  {item.reason}  reset={item.resets_at}")
        return 0
    state = tick(cfg)
    print(f"status={state.last_status} source={state.last_quota_source} threads={len(state.threads)}")
    for task in state.threads.values():
        print(f"  {task.thread_id}  {task.status}  {task.last_error}")
    return 0


def cmd_enable(cfg: AppConfig, thread_id: str, enabled: bool) -> int:
    state = load_state(cfg.resolved_state_dir())
    upsert_thread(state, thread_id, enabled=enabled, status="watching" if enabled else "disabled")
    save_state(cfg.resolved_state_dir(), state)
    print(f"{thread_id} {'enabled' if enabled else 'disabled'}")
    return 0


def cmd_autostart(install: bool) -> int:
    scripts = tool_root() / "scripts"
    if sys.platform == "win32":
        name = "install-windows.ps1" if install else "uninstall-windows.ps1"
        script = scripts / name
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            check=False,
        )
        return completed.returncode
    if sys.platform == "darwin":
        name = "install-macos.sh" if install else "uninstall-macos.sh"
        script = scripts / name
        completed = subprocess.run(["/bin/bash", str(script)], check=False)
        return completed.returncode
    print("当前只内置了 Windows 任务计划和 macOS launchd 自启", file=sys.stderr)
    return 2
