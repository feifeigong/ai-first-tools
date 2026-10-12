from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from audit_import_targets import isolated_env
from core import mover, sources


def native_binary() -> Path | None:
    explicit = os.environ.get("DIALOG_MOVER_NATIVE_CODEX")
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    paths = list(root.glob("*/codex.exe"))
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


class NativeServer:
    def __init__(self, binary: Path, env: dict, directory: Path):
        self.messages = queue.Queue()
        self.next_id = 0
        self.stderr = (directory / "native-server.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen([str(binary), "app-server", "--stdio"], env=env, cwd=directory,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                        text=True, encoding="utf-8", creationflags=mover.CREATE_NO_WINDOW)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            self.messages.put(json.loads(line))
        self.messages.put({"error": "Native app server stopped"})

    def request(self, method: str, params: dict):
        self.next_id += 1
        request_id = self.next_id
        self.process.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        while True:
            response = self.messages.get(timeout=40)
            if response.get("id") == request_id:
                if "error" in response:
                    raise ValueError(f"{method}: {response['error']}")
                return response["result"]
            if "error" in response and "id" not in response:
                raise ValueError(response["error"])

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.reader.join(timeout=5)
        self.process.stdout.close()
        self.stderr.close()


class NativeCodexImportTests(unittest.TestCase):
    def test_installed_native_server_lists_and_reads_both_local_modes(self):
        binary = native_binary()
        if binary is None:
            self.skipTest("Installed native Codex engine unavailable")
        with tempfile.TemporaryDirectory(prefix="dm-native-codex-") as scratch:
            base = Path(scratch)
            env = isolated_env(base)
            for name in list(env):
                if name.startswith("CODEX_") and name != "CODEX_HOME":
                    env.pop(name)
            directory = base / "工作目录"
            directory.mkdir()
            server = NativeServer(binary, env, base)
            try:
                server.request("initialize", {"clientInfo": {"name": "dialog_mover_test", "version": "1.0"}, "capabilities": {"experimentalApi": True}})
                server.request("thread/list", {"limit": 1})
                session = {"id": str(uuid.uuid4()), "title": "原生读取验证", "movable": True}
                with patch.dict(os.environ, env), patch.object(mover, "TEST_ENV", env), patch.object(mover, "_history_file", return_value=base / "history.json"), patch.object(sources, "claude_body", return_value=[{"role": "user", "content": "原生问题"}, {"role": "assistant", "content": "原生回答"}]):
                    for target, origin in (("chatgpt_work", "codex_work_desktop"), ("codex", "Codex Desktop")):
                        details = {}
                        result = mover.move_one("claude_desktop", session, target, str(directory), details)
                        self.assertEqual(result[0], "ok", result)
                        listed = server.request("thread/list", {"limit": 20, "useStateDbOnly": True})["data"]
                        native = next(item for item in listed if item["id"] == details["importedId"])
                        self.assertEqual(native["originator"], origin)
                        self.assertEqual(native["name"], session["title"])
                        self.assertEqual(native["cwd"], str(directory))
                        read = server.request("thread/read", {"threadId": details["importedId"], "includeTurns": True})["thread"]
                        body = json.dumps(read["turns"], ensure_ascii=False)
                        self.assertIn("原生问题", body)
                        self.assertIn("原生回答", body)
                        self.assertEqual(read["originator"], origin)
                        resumed = server.request("thread/resume", {"threadId": details["importedId"], "cwd": str(directory),
                                                                   "sandbox": "read-only", "approvalPolicy": "on-request"})["thread"]
                        self.assertEqual(resumed["originator"], origin)
                        self.assertIn("原生问题", json.dumps(resumed["turns"], ensure_ascii=False))
                        self.assertIn("原生回答", json.dumps(resumed["turns"], ensure_ascii=False))
            finally:
                server.close()


if __name__ == "__main__":
    unittest.main()
