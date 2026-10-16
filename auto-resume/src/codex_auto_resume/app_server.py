from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from .paths import resolve_codex_command
from .procutil import hidden_popen


class AppServerError(RuntimeError):
    pass


class AppServerClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None, timeout: float = 20.0):
        self.command = command
        self.env = env
        self.timeout = timeout
        self.proc: subprocess.Popen[str] | None = None
        self._incoming: Queue[dict[str, Any]] = Queue()
        self._stderr: list[str] = []
        self._next_id = 1
        self._lock = threading.Lock()

    def __enter__(self) -> "AppServerClient":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start(self) -> None:
        self.proc = hidden_popen(
            [*self.command, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=self.env,
        )
        assert self.proc.stdout and self.proc.stderr
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "vibcoding_codex_auto_resume",
                    "title": "Codex Auto Resume",
                    "version": "0.1.0",
                }
            },
        )
        self.notify("initialized")

    def close(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            try:
                message = self._incoming.get(timeout=0.2)
            except Empty:
                if self.proc and self.proc.poll() is not None:
                    raise AppServerError(f"app-server 已退出: {''.join(self._stderr)[-500:]}")
                continue
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                raise AppServerError(str(message["error"]))
            result = message.get("result")
            return result if isinstance(result, dict) else {"result": result}
        raise AppServerError(f"等待 {method} 超时")

    def read_rate_limits(self, include_credits: bool = False) -> dict[str, Any]:
        if include_credits:
            return self.request("account/rateLimits/read", {})
        try:
            return self.request("account/rateLimits/read", {"excludeResetCreditDetails": True})
        except AppServerError:
            return self.request("account/rateLimits/read", {})

    def consume_reset_credit(self, credit_id: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"idempotencyKey": str(uuid.uuid4())}
        if credit_id:
            params["creditId"] = credit_id
        return self.request("account/rateLimitResetCredit/consume", params)

    def _write(self, payload: dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise AppServerError("app-server 未启动")
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read_stdout(self) -> None:
        if not self.proc or not self.proc.stdout:
            return
        for line in self.proc.stdout:
            text = line.strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self._incoming.put(message)

    def _read_stderr(self) -> None:
        if not self.proc or not self.proc.stderr:
            return
        for line in self.proc.stderr:
            self._stderr.append(line)
            if len(self._stderr) > 200:
                self._stderr = self._stderr[-80:]


def fetch_live_rate_limits(
    *,
    codex_bin: str | None,
    extra_env: dict[str, str] | None = None,
    timeout: float = 20.0,
    include_credits: bool = False,
) -> dict[str, Any]:
    command = resolve_codex_command(codex_bin)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    with AppServerClient(command, env=env, timeout=timeout) as client:
        return client.read_rate_limits(include_credits=include_credits)


def doctor_app_server(codex_home: Path, codex_bin: str | None) -> tuple[bool, str, dict[str, Any] | None]:
    try:
        result = fetch_live_rate_limits(
            codex_bin=codex_bin,
            extra_env={"CODEX_HOME": str(codex_home)},
            timeout=18,
            include_credits=True,
        )
        return True, "ok", result
    except Exception as exc:
        return False, str(exc), None
