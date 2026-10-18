"""Official Copilot runtime reads synthetic imports; no login or model requests."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from core import copilot_import, mover
from test_copilot_import import conversation, desktop_index, visual_conversation


class NativeReader:
    METHODS = {"connect", "sessions.readPersistedEvents", "sessions.list", "session.resume", "session.getMessages", "session.detach"}

    def __init__(self, binary: Path, base: Path):
        env = {key: os.environ[key] for key in ("PATH", "SystemRoot") if key in os.environ}
        for key, folder in {"HOME": "home", "USERPROFILE": "home", "APPDATA": "appdata", "LOCALAPPDATA": "localappdata",
                            "TEMP": "temp", "TMP": "temp", "TMPDIR": "temp", "GH_CONFIG_DIR": "gh"}.items():
            path = base / folder
            path.mkdir(exist_ok=True)
            env[key] = str(path)
        env.update(COPILOT_HOME=str(base / "profile"), COPILOT_DISABLE_KEYTAR="1", COPILOT_TELEMETRY_DISABLED="1",
                   GIT_CONFIG_NOSYSTEM="1", HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9",
                   NO_PROXY="127.0.0.1,localhost")
        self.output = queue.Queue()
        self.counter = 0
        self.stderr = (base / "native.log").open("wb")
        self.process = subprocess.Popen([str(binary), "--headless", "--no-auto-update", "--no-auto-login", "--stdio", "--log-level", "error"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, cwd=base / "project", env=env,
            creationflags=mover.CREATE_NO_WINDOW)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                header = {}
                while line := self.process.stdout.readline():
                    if line == b"\r\n":
                        break
                    key, value = line.decode("ascii").split(":", 1)
                    header[key.lower()] = value.strip()
                if not line:
                    break
                length = int(header["content-length"])
                body = bytearray()
                while len(body) < length:
                    chunk = self.process.stdout.read(length - len(body))
                    if not chunk:
                        raise EOFError("Native reader stopped mid-message")
                    body.extend(chunk)
                self.output.put(json.loads(body))
        except Exception as error:
            self.output.put(error)
        finally:
            self.output.put(EOFError("Native reader stopped"))

    def request(self, method: str, params: dict):
        if method not in self.METHODS:
            raise ValueError("Model requests and authentication are forbidden in this audit")
        self.counter += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params}).encode("utf-8")
        self.process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
        self.process.stdin.flush()
        while True:
            value = self.output.get(timeout=40)
            if isinstance(value, Exception):
                raise value
            if "method" in value and "id" in value:
                raise ValueError("Native reader unexpectedly requested a client operation")
            if value.get("id") == self.counter:
                if "error" in value:
                    raise ValueError(f"{method}: {value['error']}")
                return value["result"]

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()  # Only the isolated test child.
            self.process.wait(timeout=10)
        self.reader.join(timeout=5)
        self.process.stdout.close()
        self.stderr.close()


class NativeCopilotTests(unittest.TestCase):
    def test_long_import_survives_complete_native_read_and_strict_resume(self):
        configured = os.environ.get("DIALOG_MOVER_NATIVE_COPILOT")
        if not configured:
            self.skipTest("Pinned official Copilot test runtime not prepared")
        binary = Path(configured)
        self.assertTrue(binary.is_file())
        with tempfile.TemporaryDirectory(prefix="copilot-native-") as scratch:
            base = Path(scratch)
            (base / "project").mkdir()
            desktop_index(base / "profile")
            source = conversation(base / "project", 125)
            source["messages"][1]["content"].append({"type": "tool_result", "tool_use_id": "foreign-id", "content": "Historical result\n" * 1000})
            source["messages"].extend(visual_conversation(base / "project")["messages"])
            result = copilot_import.import_document(source, base / "profile")
            expected = [json.loads(line) for line in Path(result["location"]).read_text(encoding="utf-8").splitlines()]
            reader = NativeReader(binary, base)
            try:
                reader.request("connect", {"supportedTaskKinds": ["agent", "client", "shell"]})
                params = {"sessionId": result["id"]}
                actual = []
                for _ in range(100):
                    page = reader.request("sessions.readPersistedEvents", params)
                    self.assertEqual(page["cursorStatus"], "ok")
                    actual.extend(page["events"])
                    if not page["hasMore"]:
                        break
                    self.assertTrue(page["cursor"])
                    params["cursor"] = page["cursor"]
                else:
                    self.fail("Native pagination failed to finish")
                self.assertEqual(actual, expected)
                metadata = reader.request("sessions.list", {})["sessions"]
                self.assertTrue(any(item.get("sessionId", item.get("id")) == result["id"] for item in metadata))
                resumed = reader.request("session.resume", {"sessionId": result["id"], "allowTranscriptRecovery": False,
                    "workingDirectory": str(base / "project"), "availableTools": [], "enableConfigDiscovery": False,
                    "enableFileHooks": False, "model": "synthetic-offline-model", "provider": {"type": "openai",
                    "baseUrl": "http://127.0.0.1:9/v1", "apiKey": "synthetic-not-a-credential"}})
                self.assertFalse(resumed.get("transcriptRecovery"))
                events = reader.request("session.getMessages", {"sessionId": result["id"]})["events"]
                original_ids = {event["id"] for event in expected}
                kept = [event for event in events if event["id"] in original_ids]
                self.assertEqual(kept, expected)  # Full text, reasoningText, order and timestamps.
                reader.request("session.detach", {"sessionId": result["id"]})
            finally:
                reader.close()


if __name__ == "__main__":
    unittest.main()
