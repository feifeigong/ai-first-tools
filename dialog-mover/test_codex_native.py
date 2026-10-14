from __future__ import annotations

import json
import hashlib
import os
import queue
import subprocess
import tempfile
import threading
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from audit_import_targets import isolated_env
from core import mover, sources


def native_binary() -> Path | None:
    explicit = os.environ.get("DIALOG_MOVER_NATIVE_CODEX")
    if explicit:
        if not Path(explicit).is_file():
            raise ValueError("The configured native history audit binary is missing")
        return Path(explicit)
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
    paths = list(root.glob("*/codex.exe"))
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


class NativeServer:
    def __init__(self, binary: Path, env: dict, directory: Path):
        env = {name: value for name, value in env.items()
               if not any(marker in name.upper() for marker in ("TOKEN", "SECRET", "PASSWORD", "API_KEY"))}
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
        if method not in ("initialize", "thread/list", "thread/read", "thread/resume", "thread/turns/list", "thread/items/list"):
            raise ValueError("The isolated history audit cannot run model requests")
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
    def test_mixed_historical_items_are_pageable_and_tool_results_do_not_create_turns(self):
        binary = native_binary()
        if binary is None:
            self.skipTest("Installed native Codex engine unavailable")
        with tempfile.TemporaryDirectory(prefix="dm-native-mixed-") as scratch:
            base = Path(scratch)
            env = isolated_env(base)
            directory = base / "project"
            directory.mkdir()
            messages = [{"role": "user", "content": "Synthetic mixed question"}]
            for index in range(3):
                messages.extend([
                    {"role": "assistant", "content": [{"type": "thinking", "text": f"Synthetic reasoning {index}"},
                     {"type": "tool_use", "id": "reused-call", "name": "fixture", "input": {"index": index}}]},
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "reused-call", "content": f"Synthetic result {index}"}]},
                    {"role": "assistant", "content": f"Synthetic intermediate answer {index}"}])
            messages.extend([{"role": "user", "content": "Synthetic last question"}, {"role": "assistant", "content": "Synthetic final answer"}])
            document = {"id": str(uuid.uuid4()), "cwd": str(directory), "messages": messages}
            source = base / "source.json"
            source.write_text(json.dumps(document), encoding="utf-8")
            server = NativeServer(binary, env, base)
            try:
                server.request("initialize", {"clientInfo": {"name": "dialog_mover_test", "version": "1.0"}, "capabilities": {"experimentalApi": True}})
                server.request("thread/list", {"limit": 1})
                with patch.dict(os.environ, env, clear=True), patch.object(mover, "TEST_ENV", env):
                    details = {}
                    self.assertEqual(mover._import_document(source, document, "chatgpt_work", details)[0], "ok")
                server.request("thread/resume", {"threadId": details["importedId"], "cwd": str(directory), "excludeTurns": True,
                                                 "sandbox": "read-only", "approvalPolicy": "on-request"})
                turns = server.request("thread/turns/list", {"threadId": details["importedId"], "itemsView": "full"})["data"]
                self.assertEqual(len(turns), 2)
                items = server.request("thread/items/list", {"threadId": details["importedId"], "limit": 30})["data"]
                self.assertEqual(len(items), 12)
                tools = [entry["item"] for entry in items if entry["item"]["type"] == "dynamicToolCall"]
                self.assertEqual(len({item["id"] for item in tools}), 3, [entry["item"]["type"] for entry in items])
                for index, item in enumerate(tools):
                    self.assertEqual(item["arguments"], {"index": index})
                    self.assertEqual(item["contentItems"][0]["text"], f"Synthetic result {index}")
                self.assertEqual(items[-1]["item"]["text"], "Synthetic final answer")
                self.assertEqual(sum(entry["item"]["type"] == "reasoning" for entry in items), 3)
            finally:
                server.close()

    def test_long_import_can_page_back_to_the_first_turn(self):
        binary = native_binary()
        if binary is None:
            self.skipTest("Installed native Codex engine unavailable")
        with tempfile.TemporaryDirectory(prefix="dm-native-pages-") as scratch:
            base = Path(scratch)
            env = isolated_env(base)
            for name in list(env):
                if name.startswith("CODEX_") and name != "CODEX_HOME":
                    env.pop(name)
            directory = base / "project"
            directory.mkdir()
            messages = []
            for index in range(125):
                messages.extend([{"role": "user", "content": f"Synthetic question {index:04d}"},
                                 {"role": "assistant", "content": f"Synthetic answer {index:04d} " + "完整历史 \n" * 500}])
            document = {"id": str(uuid.uuid4()), "cwd": str(directory), "messages": messages}
            source = base / "source.json"
            source.write_text(json.dumps(document), encoding="utf-8")
            server = NativeServer(binary, env, base)
            try:
                server.request("initialize", {"clientInfo": {"name": "dialog_mover_test", "version": "1.0"}, "capabilities": {"experimentalApi": True}})
                server.request("thread/list", {"limit": 1})
                cursor_root = Path(env["HOME"]) / ("Library/Application Support/Cursor/User" if sys.platform == "darwin" else "AppData/Roaming/Cursor/User")
                env["CURSOR_DESKTOP_USER_DIR"] = str(cursor_root)
                with patch.dict(os.environ, env, clear=True), patch.object(mover, "TEST_ENV", env), patch.object(mover, "_history_file", return_value=base / "history.json"):
                    seeded = {}
                    self.assertEqual(mover._import_document(source, document, "cursor_desktop", seeded)[0], "ok")
                    cursor_database = cursor_root / "globalStorage/state.vscdb"
                    original_cursor = hashlib.sha256(cursor_database.read_bytes()).hexdigest()
                    details = {}
                    result = mover.move_one("cursor_desktop", {"id": seeded["importedId"], "title": "Synthetic Cursor history"}, "chatgpt_work", str(directory), details)
                    self.assertEqual(hashlib.sha256(cursor_database.read_bytes()).hexdigest(), original_cursor)
                self.assertEqual(result[0], "ok", result)
                server.request("thread/resume", {"threadId": details["importedId"], "cwd": str(directory),
                                                 "excludeTurns": True, "sandbox": "read-only", "approvalPolicy": "on-request"})
                cursor = None
                seen_cursors = set()
                turns = []
                for _page in range(20):
                    params = {"threadId": details["importedId"], "limit": 17, "sortDirection": "desc", "itemsView": "full"}
                    if cursor:
                        params["cursor"] = cursor
                    page = server.request("thread/turns/list", params)
                    turns.extend(page["data"])
                    cursor = page.get("nextCursor")
                    if not cursor:
                        break
                    self.assertNotIn(cursor, seen_cursors)
                    seen_cursors.add(cursor)
                self.assertIsNone(cursor)
                self.assertGreater(len(seen_cursors), 1, (base / "native-server.log").read_text(encoding="utf-8")[-6000:])
                self.assertEqual(len(turns), 125)
                self.assertEqual(len({turn["id"] for turn in turns}), 125)
                self.assertTrue(all(turn["status"] == "completed" for turn in turns))
                items = []
                cursor = None
                for _page in range(40):
                    params = {"threadId": details["importedId"], "limit": 19, "sortDirection": "asc"}
                    if cursor:
                        params["cursor"] = cursor
                    page = server.request("thread/items/list", params)
                    items.extend(page["data"])
                    cursor = page.get("nextCursor")
                    if not cursor:
                        break
                self.assertIsNone(cursor)
                self.assertEqual(len(items), 250)
                self.assertEqual(len({entry["item"]["id"] for entry in items}), 250)
                self.assertEqual([entry["item"]["type"] for entry in items], ["userMessage", "agentMessage"] * 125)
                for index, message in enumerate(messages):
                    native_item = items[index]["item"]
                    stored_text = native_item["content"][0]["text"] if message["role"] == "user" else native_item["text"]
                    self.assertEqual(stored_text, message["content"])
                anchor = server.request("thread/items/list", {"threadId": details["importedId"], "turnId": items[0]["turnId"],
                                                               "cursor": {"type": "item", "itemId": items[0]["item"]["id"]}, "limit": 1})
                self.assertEqual(anchor["data"][0]["item"]["id"], items[1]["item"]["id"])
                self.assertEqual(source.read_text(encoding="utf-8"), json.dumps(document))
            finally:
                server.close()

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
                        server.request("thread/resume", {"threadId": details["importedId"], "cwd": str(directory),
                                                         "excludeTurns": True, "sandbox": "read-only", "approvalPolicy": "on-request"})
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
