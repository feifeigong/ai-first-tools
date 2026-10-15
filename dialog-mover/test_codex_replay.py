from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from audit_import_targets import isolated_env
from core import codex_import, mover
from test_codex_native import NativeServer, native_binary


class LoopbackResponses:
    def __init__(self):
        self.requests = []
        self.rejections = []
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_arguments):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                if self.path != "/v1/responses" or not 0 < length <= 4 * 1024 * 1024:
                    self.send_error(400)
                    return
                body = json.loads(self.rfile.read(length))
                fixture.requests.append(body)
                for index, item in enumerate(body.get("input", [])):
                    for field in ("name", "call_id"):
                        value = item.get(field)
                        if isinstance(value, str) and len(value) > 64:
                            message = f"input[{index}].{field}: maximum length 64, but got a string with length {len(value)} instead"
                            fixture.rejections.append(message)
                            data = json.dumps({"error": {"message": message, "type": "invalid_request_error", "code": "string_above_max_length"}}).encode()
                            self.send_response(400)
                            self.send_header("Content-Type", "application/json")
                            self.send_header("Content-Length", str(len(data)))
                            self.end_headers()
                            self.wfile.write(data)
                            return
                answer = {"id": "msg_synthetic", "type": "message", "role": "assistant", "status": "completed",
                          "content": [{"type": "output_text", "text": "Synthetic offline continuation.", "annotations": []}]}
                response = {"id": "resp_synthetic", "object": "response", "created_at": 1, "model": "gpt-5.1-codex-mini",
                            "status": "completed", "output": [answer], "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}}
                events = [{"type": "response.created", "response": {**response, "status": "in_progress", "output": []}},
                          {"type": "response.output_item.added", "output_index": 0, "item": {**answer, "status": "in_progress", "content": []}},
                          {"type": "response.output_item.done", "output_index": 0, "item": answer},
                          {"type": "response.completed", "response": response}]
                data = "".join("data: " + json.dumps(event) + "\n\n" for event in events).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, *_arguments):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=5)

    def resume(self, binary: Path, env: dict, directory: Path, thread_id: str):
        endpoint = f"http://127.0.0.1:{self.server.server_port}/v1"
        config = '\n'.join(['model = "gpt-5.1-codex-mini"', 'model_provider = "loopback_audit"',
                            'cli_auth_credentials_store = "file"', 'approval_policy = "never"', 'sandbox_mode = "read-only"',
                            '[analytics]', 'enabled = false', '[feedback]', 'enabled = false',
                            '[model_providers.loopback_audit]', 'name = "Synthetic local-only audit"',
                            'base_url = ' + json.dumps(endpoint), 'wire_api = "responses"', 'requires_openai_auth = false',
                            'supports_websockets = false', 'request_max_retries = 0', 'stream_max_retries = 0'])
        (Path(env["CODEX_HOME"]) / "config.toml").write_text(config, encoding="utf-8")
        environment = {name: value for name, value in env.items()
                       if not any(marker in name.upper() for marker in ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "OPENAI_", "AZURE_"))
                       and name.lower() not in ("http_proxy", "https_proxy", "all_proxy")}
        environment["NO_PROXY"] = "127.0.0.1,localhost"
        environment["OTEL_SDK_DISABLED"] = "true"
        return subprocess.run([str(binary), "exec", "--skip-git-repo-check", "--json", "resume", thread_id,
                               "Synthetic follow-up; return only the fixture answer."],
                              cwd=directory, env=environment, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=60, creationflags=mover.CREATE_NO_WINDOW)


class NativeReplayTests(unittest.TestCase):
    def check_cursor_continuation(self, tool_name: str, call_id: str, repetitions: int = 1, legacy: bool = False):
        binary = native_binary()
        if binary is None:
            self.skipTest("Native engine unavailable; the Mac CI supplies a checksum-pinned executable")
        with tempfile.TemporaryDirectory(prefix="dm-offline-replay-") as scratch:
            base = Path(scratch)
            env = isolated_env(base)
            for name in list(env):
                if name.startswith("CODEX_") and name != "CODEX_HOME":
                    env.pop(name)
            directory = base / "project"
            directory.mkdir()
            cursor_root = Path(env["HOME"]) / ("Library/Application Support/Cursor/User" if sys.platform == "darwin" else "AppData/Roaming/Cursor/User")
            env["CURSOR_DESKTOP_USER_DIR"] = str(cursor_root)
            arguments = {"sentinel": "Do not truncate arguments. " * 20}
            if tool_name == "ApplyPatch":
                arguments = {"patch": "*** Begin Patch\n*** Add File: must-not-execute.txt\n+synthetic only\n*** End Patch", "files": ["must-not-execute.txt"]}
            messages = [{"role": "user", "content": "Synthetic first question"}]
            for index in range(repetitions):
                messages.extend([
                    {"role": "assistant", "content": [{"type": "tool_use", "id": call_id, "name": tool_name, "input": arguments}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call_id, "content": f"Synthetic complete tool output {index}"}]}])
            messages.append({"role": "assistant", "content": "Synthetic last answer"})
            document = {"id": str(uuid.uuid4()), "cwd": str(directory), "messages": messages}
            source = base / "source.json"
            original = json.dumps(document)
            source.write_text(original, encoding="utf-8")
            native = NativeServer(binary, env, base)
            try:
                native.request("initialize", {"clientInfo": {"name": "offline_replay_audit", "version": "1.0"}, "capabilities": {"experimentalApi": True}})
                native.request("thread/list", {"limit": 1})
                with patch.dict(os.environ, env, clear=True), patch.object(mover, "TEST_ENV", env), patch.object(mover, "_history_file", return_value=base / "history.json"):
                    seeded = {}
                    self.assertEqual(mover._import_document(source, document, "cursor_desktop", seeded)[0], "ok")
                    database = cursor_root / "globalStorage/state.vscdb"
                    before = hashlib.sha256(database.read_bytes()).hexdigest()
                    details = {}
                    if legacy:
                        # Reproduce the old wire payload while keeping the same import and resume path.
                        with patch.object(codex_import, "_replay_safe_records", side_effect=lambda records, _imported_id: records):
                            result = mover.move_one("cursor_desktop", {"id": seeded["importedId"], "title": "Synthetic long identifiers"}, "chatgpt_work", str(directory), details)
                    else:
                        result = mover.move_one("cursor_desktop", {"id": seeded["importedId"], "title": "Synthetic long identifiers"}, "chatgpt_work", str(directory), details)
                    self.assertEqual(result[0], "ok", result)
                    self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)
            finally:
                native.close()
            with LoopbackResponses() as fixture:
                result = fixture.resume(binary, env, directory, details["importedId"])
                self.assertTrue(fixture.requests, result.stderr[-2000:])
                if legacy:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(fixture.rejections)
                    self.assertIn("maximum length 64, but got a string with length 85 instead", fixture.rejections[0])
                    return
                self.assertEqual(fixture.rejections, [])
                self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
                self.assertIn("Synthetic offline continuation.", result.stdout)
                history = fixture.requests[0]["input"]
                kind = "custom_tool_call" if tool_name == "ApplyPatch" else "function_call"
                calls = [item for item in history if item.get("type") == kind]
                outputs = [item for item in history if item.get("type") == kind + "_output"]
                self.assertEqual(len(calls), repetitions)
                self.assertEqual(len(outputs), repetitions)
                self.assertEqual(len({item["call_id"] for item in calls}), repetitions)
                for index, (call, output) in enumerate(zip(calls, outputs)):
                    self.assertEqual(call["call_id"], output["call_id"])
                    if kind == "custom_tool_call":
                        self.assertEqual(call["input"], arguments["patch"])
                        self.assertIn(f"Synthetic complete tool output {index}", output["output"])
                    else:
                        self.assertEqual(json.loads(call["arguments"]), arguments)
                        self.assertEqual(output["output"], f"Synthetic complete tool output {index}")
                self.assertFalse((directory / "must-not-execute.txt").exists())
                self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_short_identifiers_can_continue_using_only_a_local_fixture(self):
        self.check_cursor_continuation("fixture", "short-call")

    def test_legacy_85_character_identifiers_reproduce_the_reported_rejection(self):
        for tool_name, call_id in (("fixture", "call_" + "a" * 80), ("mcp__" + "b" * 80, "short-call")):
            with self.subTest(name_length=len(tool_name), call_id_length=len(call_id)):
                self.check_cursor_continuation(tool_name, call_id, legacy=True)

    def test_cursor_85_character_call_ids_and_tool_names_are_safe_when_continuing(self):
        for tool_name, call_id in (("fixture", "call_" + "a" * 80), ("mcp__" + "b" * 80, "short-call")):
            with self.subTest(name_length=len(tool_name), call_id_length=len(call_id)):
                self.check_cursor_continuation(tool_name, call_id)

    def test_custom_tool_history_continues_without_executing_the_historical_patch(self):
        self.check_cursor_continuation("ApplyPatch", "custom_" + "c" * 80)

    def test_reused_historical_ids_are_unique_and_paired_in_the_actual_request(self):
        self.check_cursor_continuation("fixture", "reused-call", repetitions=3)


if __name__ == "__main__":
    unittest.main()
