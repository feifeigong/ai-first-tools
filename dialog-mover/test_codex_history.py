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

    def test_foreign_reasoning_is_preserved_as_history_without_an_unverified_native_state(self):
        thinking = {'type':'reasoning','summary':[{'type':'summary_text','text':'历史思考\n完整内容 ' * 800}],
                    'content':[{'type':'reasoning_text','text':'来源补充思考'}],'encrypted_content':None}
        records = [self.meta,message('user','起点'),record('response_item',thinking),message('assistant','终点')]
        before = copy.deepcopy(records)
        converted = codex_import.paginated_history(records,self.imported_id)
        payloads = [entry['payload'] for entry in converted if entry['type']=='response_item']
        self.assertFalse(any(payload['type']=='reasoning' for payload in payloads))
        note = next(entry for entry in converted if entry.get('dialog_mover_original',{}).get('reason')=='foreign_reasoning')
        self.assertEqual(note['dialog_mover_original']['response_item'],thinking)
        text = note['payload']['content'][0]['text']
        self.assertIn(thinking['summary'][0]['text'],text)
        self.assertIn('来源补充思考',text)
        self.assertIn('历史思考',text)
        displayed = [entry['payload']['item'] for entry in converted if entry.get('payload',{}).get('type')=='item_completed']
        self.assertTrue(all(item['type']!='Reasoning' for item in displayed))
        self.assertEqual(displayed[1]['type'],'AgentMessage')
        self.assertEqual(records,before)
        self.assertEqual(payloads[0]['role'],'user')
        self.assertEqual(payloads[-1]['content'][0]['text'],'终点')

    def test_frozen_compatibility_audit_uses_no_model_and_reports_its_actual_scope(self):
        from core.codex_audit import run
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary)/'check.json'
            self.assertEqual(run(report),0)
            result = json.loads(report.read_text(encoding='utf-8'))
            self.assertTrue(result['passed'])
            self.assertEqual(len(result['checks']),7)
            self.assertEqual(result['savedFollowupRoundTrips'],2)
            self.assertEqual(result['modelRequests'],0)
            self.assertFalse(result['nativeContinuationVerified'])

    def test_normal_import_audit_rejects_the_old_unportable_writer(self):
        from core.codex_audit import normal_import_with_saved_followups
        def require(value):
            if not value: raise AssertionError('Synthetic assertion')
        with patch.object(codex_import,'_archive_nonportable',return_value=False):
            with self.assertRaises(AssertionError): normal_import_with_saved_followups(require)

    def test_import_registration_rejects_context_or_display_state_before_writing_or_indexing(self):
        bad_context = record('response_item',{'type':'reasoning','summary':[],'encrypted_content':None})
        bad_display = record('event_msg',{'type':'item_completed','item':{'type':'Reasoning'}})
        for bad in (bad_context,bad_display):
            with tempfile.TemporaryDirectory(prefix='ai-first-register-guard-') as temporary:
                root = Path(temporary);path = root/'sessions/new.jsonl';path.parent.mkdir()
                rows = [self.meta,message('user','synthetic question'),bad,message('assistant','synthetic answer')]
                path.write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8');before=path.read_bytes()
                with patch.object(codex_import,'validate'), patch.object(codex_import,'paginated_history',side_effect=lambda value,_id:value), \
                        patch.object(codex_import.sqlite3,'connect',side_effect=AssertionError('Index opened before compatibility guard')):
                    with self.assertRaisesRegex(ValueError,'不可移植|兼容转换'):
                        codex_import.register(path,self.imported_id,{'cwd':temporary,'title':'Synthetic title'},'chatgpt_work',{'CODEX_HOME':temporary,'APPDATA':temporary})
                self.assertEqual(path.read_bytes(),before)

    def test_hosted_search_and_compaction_are_archived_without_replaying_opaque_state(self):
        payloads = [{'type':'web_search_call','id':'old-search','status':'completed',
                     'action':{'type':'search','query':'合成历史问题'}},
                    {'type':'compaction','id':'old-compaction','encrypted_content':'opaque-synthetic-only'}]
        records = [self.meta,message('user','起点'),*(record('response_item',p) for p in payloads),message('assistant','终点')]
        converted = codex_import.paginated_history(records,self.imported_id)
        self.assertFalse(any(entry.get('type')=='response_item' and entry['payload']['type'] in {'web_search_call','compaction'} for entry in converted))
        archived = [entry['dialog_mover_original']['response_item'] for entry in converted if entry.get('dialog_mover_original',{}).get('reason') in {'foreign_hosted_tool','foreign_compaction'}]
        self.assertEqual(archived,payloads)
        self.assertIn('合成历史问题',json.dumps(converted,ensure_ascii=False))
        self.assertEqual(sum(entry.get('payload',{}).get('type')=='task_started' for entry in converted),1)

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

    def test_mismatched_tool_types_are_still_rejected_before_reporting_success(self):
        call = record("response_item", {"type": "function_call", "name": "fixture", "call_id": "call-fixture", "arguments": "{}"})
        with self.assertRaisesRegex(ValueError, "配对"):
            codex_import.paginated_history([self.meta, message("user", "question"), call,
                record("response_item", {"type": "custom_tool_call_output", "call_id": "call-fixture", "output": "wrong type"})], self.imported_id)

    def test_unpaired_logs_are_lossless_explicit_notes_and_never_fabricated_pairs(self):
        call = record("response_item", {"type": "function_call", "name": "mcp__" + "x" * 80,
                                       "call_id": "call_" + "c" * 80, "arguments": json.dumps({"full": "参数\n" * 1000})})
        result = record("response_item", {"type": "function_call_output", "call_id": "orphan", "output": "原始结果\n" * 1000})
        records = [self.meta, message("user", "prefix"), call, result, message("assistant", "tail")]
        original = copy.deepcopy(records)
        converted = codex_import.paginated_history(records, self.imported_id)
        self.assertEqual(records, original)
        responses = [entry for entry in converted if entry["type"] == "response_item"]
        self.assertTrue(all(entry["payload"]["type"] == "message" for entry in responses))
        for note, source, reason in ((responses[1], call, "missing_tool_result"), (responses[2], result, "missing_tool_call")):
            self.assertEqual(note["dialog_mover_original"]["response_item"], source["payload"])
            self.assertEqual(note["dialog_mover_original"]["reason"], reason)
            self.assertEqual(json.loads(note["payload"]["content"][0]["text"].split("\n", 1)[1]), source["payload"])
            self.assertIn("不代表执行成功", note["payload"]["content"][0]["text"])
        self.assertEqual(sum(entry.get("payload", {}).get("type") == "task_started" for entry in converted), 1)

    def test_interrupted_call_cannot_steal_a_reused_id_from_a_later_user_turn(self):
        call = record("response_item", {"type": "function_call", "name": "fixture", "call_id": "reused", "arguments": "{}"})
        records = [self.meta, message("user", "first"), call, message("assistant", "interrupted"),
                   message("user", "second"), call,
                   record("response_item", {"type": "function_call_output", "call_id": "reused", "output": "second result"})]
        converted = codex_import.paginated_history(records, self.imported_id)
        notes = [entry for entry in converted if entry.get("dialog_mover_original", {}).get("reason") == "missing_tool_result"]
        self.assertEqual(len(notes), 1)
        tools = [entry["payload"]["item"] for entry in converted if entry.get("payload", {}).get("type") == "item_completed"
                 and entry["payload"]["item"]["type"] == "DynamicToolCall"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["content_items"], [{"type": "inputText", "text": "second result"}])
        self.assertEqual(sum(entry.get("payload", {}).get("type") == "task_started" for entry in converted), 2)

    def test_overlapping_reused_ids_are_preserved_without_guessing_the_pairing(self):
        calls = [record("response_item", {"type": "function_call", "name": "fixture", "call_id": "ambiguous", "arguments": str(index)}) for index in range(2)]
        results = [record("response_item", {"type": "function_call_output", "call_id": "ambiguous", "output": str(index)}) for index in range(2)]
        converted = codex_import.paginated_history([self.meta, message("user", "question"), *calls, *results], self.imported_id)
        notes = [entry for entry in converted if entry.get("dialog_mover_original", {}).get("reason") == "ambiguous_tool_id"]
        self.assertEqual([entry["dialog_mover_original"]["response_item"] for entry in notes], [entry["payload"] for entry in [*calls, *results]])
        self.assertFalse(any(entry.get("payload", {}).get("type") in ("function_call", "function_call_output") for entry in converted))

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
                for previous in ("paginated-import-v1", "paginated-import-v2", "paginated-import-v3"):
                    history.write_text(json.dumps({key: {"time": 123, "format": previous}}))
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
