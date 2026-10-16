from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .paths import resolve_codex_command
from .procutil import hidden_popen

BUSY_HINTS = (
    "already owns",
    "already loaded",
    "cannot resume",
    "thread is loaded",
    "held open",
    "active writer",
    "-32600",
)


def spawn_resume(
    *,
    thread_id: str,
    prompt: str,
    cwd: str | None,
    log_file: Path,
    extra_args: list[str],
    skip_git_repo_check: bool,
    prefer_queue_if_busy: bool,
    codex_bin: str | None,
    extra_env: dict[str, str] | None,
) -> tuple[int, str]:
    command = resolve_codex_command(codex_bin)
    args = [*command, "exec", "resume", "--all"]
    if skip_git_repo_check:
        args.append("--skip-git-repo-check")
    args.extend(extra_args)
    args.extend([thread_id, prompt])
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handle = log_file.open("a", encoding="utf-8", errors="replace")
    handle.write(f"$ {' '.join(args)}\n")
    handle.flush()
    output_from = log_file.stat().st_size
    proc = hidden_popen(
        args,
        cwd=cwd if cwd and Path(cwd).exists() else None,
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
    )
    if not prefer_queue_if_busy:
        return proc.pid, "exec-resume"

    deadline = time.time() + 8
    while True:
        output = _log_since(log_file, output_from)
        if _looks_busy(output):
            _stop(proc)
            handle.write("\n# exec resume busy, fallback to queue\n")
            handle.flush()
            return _spawn_queue(
                command=command,
                thread_id=thread_id,
                prompt=prompt,
                cwd=cwd,
                handle=handle,
                env=env,
                extra_args=extra_args,
            ), "queue"
        code = proc.poll()
        if code is not None:
            if code != 0:
                raise RuntimeError(f"codex exec resume 失败，exit={code}，详见 {log_file}")
            return proc.pid, "exec-resume-finished"
        if time.time() >= deadline:
            if "error:" in output:
                _stop(proc)
                raise RuntimeError(f"codex exec resume 超时且已报错，详见 {log_file}")
            return proc.pid, "exec-resume"
        time.sleep(0.2)


def _spawn_queue(
    *,
    command: list[str],
    thread_id: str,
    prompt: str,
    cwd: str | None,
    handle,
    env: dict[str, str],
    extra_args: list[str],
) -> int:
    args = [*command, "queue", "--thread", thread_id, "--message", prompt, *extra_args]
    handle.write(f"$ {' '.join(args)}\n")
    handle.flush()
    proc = hidden_popen(
        args,
        cwd=cwd if cwd and Path(cwd).exists() else None,
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return proc.pid


def _looks_busy(output: str) -> bool:
    return any(hint in output for hint in BUSY_HINTS)


def _log_since(log_file: Path, start: int) -> str:
    try:
        data = log_file.read_bytes()
    except OSError:
        return ""
    if start < 0 or start > len(data):
        start = 0
    return data[start:].decode("utf-8", errors="replace").lower()


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
