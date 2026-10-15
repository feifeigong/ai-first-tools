from __future__ import annotations

import copy
import json
import re
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from core import codex_import, mover


STAMP = "2026-01-01T00:00:00.000Z"


def record(kind: str, payload: dict) -> dict:
    return {"timestamp": STAMP, "type": kind, "payload": payload}


def message(role: str, text: str) -> dict:
    return record("response_item", {"type": "message", "role": role,
                                    "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}]})


class CodexHistoryTests(unittest.TestCase):
    def setUp(self):
        self.imported_id = str(uuid.uuid4())
        self.meta = record("session_meta", {"id": self.imported_id})

    def test_long_history_has_stable_unique_turns_items_and_contiguous_ordinals(self):
        records = [self.meta]
        for index in range(151):
            records.extend([message("user", f"问题 {index}"),
                            record("turn_context", {"turn_id": f"turn-{index}"}),
                            message("assistant", f"回复 {index}"), message("assistant", f"补充 {index}")])
        converted = codex_import.paginated_history(records, self.imported_id)
        self.assertEqual(converted, codex_import.paginated_history(records, self.imported_id))
        self.assertEqual([entry["ordinal"] for entry in converted], list(range(len(converted))))
        payloads = [entry["payload"] for entry in converted if entry["type"] == "event_msg"]
        started = [entry["turn_id"] for entry in payloads if entry["type"] == "task_started"]
        completed = [entry["turn_id"] for entry in payloads if entry["type"] == "task_complete"]
        self.assertEqual(started, completed)
        self.assertEqual(len(set(started)), 151)
        items = [entry for entry in payloads if entry["type"] == "item_completed"]
        self.assertEqual(len({entry["item"]["id"] for entry in items}), 453)
        self.assertTrue(all(entry["thread_id"] == self.imported_id for entry in items))
        self.assertEqual([entry["item"]["phase"] for entry in items if entry["item"]["type"] == "AgentMessage"],
                         ["commentary", "final_answer"] * 151)

    def test_tool_results_do_not_start_fake_user_turns_and_reused_ids_stay_unique(self):
        records = [self.meta, message("user", "开始")]
        for index in range(3):
            records.extend([record("response_item", {"type": "function_call", "name": "fixture", "arguments": "{}", "call_id": "reused"}),
                            record("response_item", {"type": "function_call_output", "call_id": "reused", "output": f"result {index}"})])
        records.append(message("assistant", "结束"))
        payloads = [entry["payload"] for entry in codex_import.paginated_history(records, self.imported_id) if entry["type"] == "event_msg"]
        self.assertEqual(sum(entry["type"] == "task_started" for entry in payloads), 1)
        tools = [entry["item"] for entry in payloads if entry["type"] == "item_completed" and entry["item"]["type"] == "DynamicToolCall"]
        self.assertEqual(len({entry["id"] for entry in tools}), 3)
        self.assertEqual([entry["content_items"][0]["text"] for entry in tools], [f"result {index}" for index in range(3)])
        self.assertTrue(all(entry["status"] == "completed" for entry in tools))

    def test_replayed_tool_identifiers_are_bounded_paired_unique_and_losslessly_annotated(self):
        records = [self.meta, message("user", "Synthetic question " * 100)]
        names = ["mcp__" + "shared_" * 11 + suffix for suffix in ("first", "second")]
        names.extend(["invalid.name", "invalid/name", "n" * 64, "n" * 65, "工具" * 45])
        for index, name in enumerate(names):
            records.extend([record("response_item", {"type": "function_call", "name": name, "arguments": json.dumps({"text": "full arguments " * 500}), "call_id": "call_" + "a" * 80}),
                            record("response_item", {"type": "function_call_output", "call_id": "call_" + "a" * 80, "output": "full output " * 500})])
        original = copy.deepcopy(records)
        converted = codex_import.paginated_history(records, self.imported_id)
        responses = [entry for entry in converted if entry["type"] == "response_item"]
        calls = [entry for entry in responses if entry["payload"]["type"] == "function_call"]
        results = [entry for entry in responses if entry["payload"]["type"] == "function_call_output"]
        self.assertEqual(records, original)
        self.assertEqual(converted, codex_import.paginated_history(records, self.imported_id))
        self.assertEqual(len({entry["payload"]["call_id"] for entry in calls}), len(names))
        self.assertEqual(len({entry["payload"]["name"] for entry in calls}), len(names))
        for index, (call, result) in enumerate(zip(calls, results)):
            for field in ("name", "call_id"):
                self.assertRegex(call["payload"][field], re.compile(r"^[A-Za-z0-9_-]{1,64}$"))
            self.assertEqual(call["payload"]["call_id"], result["payload"]["call_id"])
            self.assertEqual(call["payload"]["arguments"], original[2 + index * 2]["payload"]["arguments"])
            self.assertEqual(result["payload"]["output"], original[3 + index * 2]["payload"]["output"])
            self.assertEqual(call.get("dialog_mover_original", {}).get("name", call["payload"]["name"]), names[index])
            self.assertEqual(call["dialog_mover_original"]["call_id"], "call_" + "a" * 80)

    def test_custom_tool_call_and_result_share_the_same_bounded_identifier(self):
        records = [self.meta, message("user", "Synthetic patch history"),
                   record("response_item", {"type": "custom_tool_call", "name": "apply_patch", "call_id": "c" * 85, "input": "*** Begin Patch\n*** End Patch"}),
                   record("response_item", {"type": "custom_tool_call_output", "call_id": "c" * 85, "output": "synthetic output"})]
        converted = codex_import.paginated_history(records, self.imported_id)
        calls = [entry["payload"] for entry in converted if entry["type"] == "response_item" and "call_id" in entry["payload"]]
        self.assertEqual(calls[0]["call_id"], calls[1]["call_id"])
        self.assertLessEqual(len(calls[0]["call_id"]), 64)
        self.assertEqual(calls[0]["input"], "*** Begin Patch\n*** End Patch")

    def test_identifier_boundary_preserves_legal_values_and_resolves_alias_collisions(self):
        long_name = "mcp__" + "n" * 80
        alias = long_name[:31] + "_" + uuid.uuid5(uuid.NAMESPACE_URL, "0:" + long_name).hex
        records = [self.meta, message("user", "boundary question")]
        for index, name in enumerate((long_name, alias, "s" * 64)):
            call_id = ("id" + str(index)).ljust(64, "x")
            records.extend([record("response_item", {"type": "function_call", "name": name, "call_id": call_id, "arguments": "{}"}),
                            record("response_item", {"type": "function_call_output", "call_id": call_id, "output": "result"})])
        converted = codex_import.paginated_history(records, self.imported_id)
        calls = [entry["payload"] for entry in converted if entry["type"] == "response_item" and entry["payload"]["type"] == "function_call"]
        self.assertNotEqual(calls[0]["name"], alias)
        self.assertEqual(calls[1]["name"], alias)
        self.assertEqual(calls[2]["name"], "s" * 64)
        self.assertEqual([item["call_id"] for item in calls], [("id" + str(index)).ljust(64, "x") for index in range(3)])

    def test_unpaired_or_mismatched_tool_history_is_rejected_before_reporting_success(self):
        call = record("response_item", {"type": "function_call", "name": "fixture", "call_id": "call-fixture", "arguments": "{}"})
        for entries in ([call], [record("response_item", {"type": "function_call_output", "call_id": "missing", "output": "orphan"})],
                        [call, record("response_item", {"type": "custom_tool_call_output", "call_id": "call-fixture", "output": "wrong type"})]):
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, "配对"):
                codex_import.paginated_history([self.meta, message("user", "question"), *entries], self.imported_id)

    def test_unknown_payload_is_rejected_not_silently_omitted(self):
        with self.assertRaisesRegex(ValueError, "未支持"):
            codex_import.paginated_history([self.meta, record("response_item", {"type": "new_unhandled_body"})], self.imported_id)

    def test_integrity_checks_prefix_middle_tail_order_role_and_repeated_text(self):
        document = {"messages": [{"role": "user", "content": "首段\n正文"}, {"role": "assistant", "content": "中段"},
                                 {"role": "user", "content": "重复"}, {"role": "user", "content": "重复"},
                                 {"role": "assistant", "content": "末段"}]}
        codex_import.verify_body(document, document)
        for index in range(len(document["messages"])):
            with self.subTest(missing=index), self.assertRaisesRegex(ValueError, "完整性"):
                codex_import.verify_body(document, {"messages": document["messages"][:index] + document["messages"][index + 1:]})
        with self.assertRaisesRegex(ValueError, "完整性"):
            codex_import.verify_body(document, {"messages": list(reversed(document["messages"]))})

    def test_old_success_allows_one_safe_new_copy_without_removing_previous_records(self):
        with tempfile.TemporaryDirectory() as scratch:
            history = Path(scratch) / "history.json"
            source_id = str(uuid.uuid4())
            key = mover.history_key("cursor_desktop", source_id, "chatgpt_work", scratch)
            history.write_text(json.dumps({key: 123}))
            with patch.object(mover, "_history_file", return_value=history):
                self.assertFalse(mover.already_moved("cursor_desktop", source_id, "chatgpt_work", scratch))
                history.write_text(json.dumps({key: {"time": 123, "format": "paginated-import-v1"}}))
                self.assertFalse(mover.already_moved("cursor_desktop", source_id, "chatgpt_work", scratch))
                mover._record_move("cursor_desktop", source_id, "chatgpt_work", scratch)
                self.assertTrue(mover.already_moved("cursor_desktop", source_id, "chatgpt_work", scratch))
                mover._record_move("cursor_desktop", source_id, "workbuddy_ai", scratch)
                self.assertTrue(mover.already_moved("cursor_desktop", source_id, "workbuddy_ai", scratch))

    def test_truncated_readback_never_registers_success_and_removes_only_new_rollout(self):
        with tempfile.TemporaryDirectory() as scratch:
            base = Path(scratch)
            sessions = base / "codex/sessions"
            sessions.mkdir(parents=True)
            location = sessions / f"rollout-test-{self.imported_id}.jsonl"
            original = sessions / "existing-history.jsonl"
            original.write_text("existing synthetic history")
            document = {"messages": [{"role": "user", "content": "missing prefix"}, {"role": "assistant", "content": "tail"}]}
            source = base / "source.json"
            source.write_text(json.dumps(document))

            def run(arguments, _environment):
                if arguments[0] == "continue":
                    location.write_text("new synthetic rollout")
                    report = {"id": self.imported_id, "location": str(location)}
                    return subprocess.CompletedProcess([], 0, "TXCRIPT_IMPORT_REPORT " + json.dumps(report), "")
                Path(arguments[-1]).write_text(json.dumps({"messages": document["messages"][1:]}))
                return subprocess.CompletedProcess([], 0, "", "")

            with patch.object(mover, "destination_env", return_value={"CODEX_HOME": str(base / "codex")}), patch.object(mover.imports, "preflight"), patch.object(mover, "_run", side_effect=run), patch.object(codex_import, "register") as registration:
                with self.assertRaisesRegex(ValueError, "完整性"):
                    mover._import_document(source, document, "chatgpt_work", {})
                registration.assert_not_called()
            self.assertFalse(location.exists())
            self.assertEqual(original.read_text(), "existing synthetic history")
            self.assertEqual(json.loads(source.read_text()), document)


if __name__ == "__main__":
    unittest.main()
