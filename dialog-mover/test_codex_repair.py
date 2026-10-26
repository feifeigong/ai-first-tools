from __future__ import annotations

import copy
import json
import os
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from audit_import_targets import isolated_env
from core import codex_import, codex_repair

SCHEMA = '''
CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}',position INTEGER NOT NULL,created_at_ms INTEGER NOT NULL,updated_at_ms INTEGER NOT NULL);
CREATE TABLE project_roots(project_id TEXT NOT NULL REFERENCES projects(id),position INTEGER NOT NULL,path TEXT NOT NULL,PRIMARY KEY(project_id,position));
CREATE TABLE threads(id TEXT PRIMARY KEY,rollout_path TEXT NOT NULL,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,source TEXT NOT NULL,model_provider TEXT NOT NULL,cwd TEXT NOT NULL,title TEXT NOT NULL,sandbox_policy TEXT NOT NULL,approval_mode TEXT NOT NULL,has_user_event INTEGER DEFAULT 0,first_user_message TEXT NOT NULL DEFAULT '',preview TEXT NOT NULL DEFAULT '',created_at_ms INTEGER,updated_at_ms INTEGER,recency_at INTEGER DEFAULT 0,recency_at_ms INTEGER DEFAULT 0,thread_source TEXT,history_mode TEXT DEFAULT 'legacy',name TEXT,originator TEXT,project_id TEXT REFERENCES projects(id));
'''


def entry(payload, stamp='2026-10-22T00:00:00Z', kind='response_item'):
    return {'type': kind, 'timestamp': stamp, 'payload': payload}


def message(role, text, stamp='2026-10-22T00:00:00Z'):
    return entry({'type': 'message', 'role': role, 'content': [
        {'type': 'input_text' if role == 'user' else 'output_text', 'text': text}]}, stamp)


def legacy(identity):
    meta = entry({'id': identity, 'dialog_mover_import_format': 'paginated-import-v3'}, kind='session_meta')
    result = [meta, entry({'type': 'task_started', 'turn_id': 'old'}, kind='event_msg'), message('user', '合成原问题')]
    for i in range(154):
        result.append(entry({'type': 'reasoning', 'summary': [{'type': 'summary_text', 'text': f'合成历史思考{i}'}], 'encrypted_content': None}))
    result.extend([message('assistant', '合成完整旧回复'), entry({'type': 'task_complete', 'turn_id': 'old'}, kind='event_msg')])
    return result


def continued(identity):
    at = '2026-10-23T01:00:00Z'
    return [entry({'id': identity}, at, 'session_meta'),
            entry({'type': 'task_started', 'turn_id': 'new'}, at, 'event_msg'),
            entry({'type': 'additional_tools', 'tools': [{'name': 'synthetic-runtime-only'}]}, at),
            message('developer', '合成旧运行指令，不得作为新副本的指令', at),
            message('user', '合成搬入后的新问题', at),
            entry({'type': 'custom_tool_call', 'name': 'fixture', 'call_id': 'paired-fixture', 'input': '完整合成参数'}, at),
            entry({'type': 'custom_tool_call_output', 'call_id': 'paired-fixture', 'output': '完整合成结果'}, at),
            message('assistant', '合成搬入后的新回复', at),
            entry({'response_id': 'private-synthetic-response'}, at, 'token_usage_record'),
            entry({'type': 'task_complete', 'turn_id': 'new'}, at, 'event_msg')]


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='ai-first-compatible-copy-')
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.env = isolated_env(self.base)
        self.root = Path(self.env['CODEX_HOME'])
        self.project = self.base / 'existing-project'; self.project.mkdir()
        (self.project / 'keep.txt').write_text('unchanged-project', encoding='utf-8')
        self.archives = Path(self.env['LOCALAPPDATA']) / 'AI一手工具工作台/memory-preview/codex-repairs'
        self.old_id = str(uuid.uuid4()); self.project_id = str(uuid.uuid4())
        self.sources = []
        for i, rows in enumerate((legacy(self.old_id), continued(self.old_id))):
            path = self.root / 'sessions/2026/10/23' / f'synthetic-{i}-{self.old_id}.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
            self.sources.append(path)
        with closing(sqlite3.connect(self.root / 'state_5.sqlite')) as c:
            c.executescript(SCHEMA)
            c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)', (self.project_id, 'Synthetic', '{}', 0, 1, 1))
            c.execute('INSERT INTO project_roots VALUES(?,?,?)', (self.project_id, 0, str(self.project)))
            values = {'id': self.old_id, 'rollout_path': str(self.sources[-1]), 'created_at': 1, 'updated_at': 1,
                      'source': 'vscode', 'model_provider': 'openai', 'cwd': str(self.project), 'title': 'Synthetic title',
                      'sandbox_policy': '{}', 'approval_mode': 'on-request', 'name': 'Synthetic title',
                      'originator': 'codex_work_desktop', 'project_id': self.project_id, 'history_mode': 'paginated'}
            c.execute('INSERT INTO threads('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')', tuple(values.values()))
            c.commit()

    def create(self, **extra):
        args = dict(root=self.root, archive_root=self.archives, source_paths=self.sources, old_id=self.old_id,
                    title='Synthetic title', directory=str(self.project), env=self.env, approved=True)
        args.update(extra)
        return codex_repair.create_copy(**args)

    def rows(self):
        with closing(sqlite3.connect(self.root / 'state_5.sqlite')) as c:
            return c.execute('SELECT * FROM threads ORDER BY id').fetchall()

    def test_old_reasoning_and_new_followup_become_one_compatible_context_without_provider_links(self):
        chunks = [legacy(self.old_id), continued(self.old_id)]; original = copy.deepcopy(chunks)
        new_id = str(uuid.uuid4()); result, runtime = codex_repair.compatible_records(chunks, self.old_id, new_id)
        self.assertEqual(chunks, original); self.assertEqual(runtime, 2)
        active = [r['payload'] for r in result if r['type'] == 'response_item']
        self.assertFalse(any(p['type'] in {'reasoning', 'web_search_call', 'compaction', 'additional_tools'} for p in active))
        self.assertFalse(any(p.get('role') in {'system', 'developer'} for p in active))
        text = json.dumps(active, ensure_ascii=False)
        for wanted in ('合成原问题', '合成完整旧回复', '合成搬入后的新问题', '合成搬入后的新回复', '完整合成参数', '完整合成结果'):
            self.assertIn(wanted, text)
        self.assertEqual(sum(r.get('dialog_mover_original', {}).get('reason') == 'foreign_reasoning' for r in result), 154)
        self.assertNotIn('private-synthetic-response', json.dumps(result))
        self.assertEqual([r['ordinal'] for r in result], list(range(len(result))))

    def test_copy_archives_full_originals_keeps_existing_index_project_and_files_and_reuses(self):
        before = [p.read_bytes() for p in self.sources]; old = self.rows()[0]
        result = self.create(); self.assertFalse(result['reused']); self.assertEqual(uuid.UUID(result['newId']).version, 7)
        self.assertEqual([p.read_bytes() for p in self.sources], before)
        self.assertIn(old, self.rows()); self.assertEqual(len(self.rows()), 2)
        self.assertEqual((self.project / 'keep.txt').read_text(), 'unchanged-project')
        folder = self.archives / self.old_id
        self.assertEqual([(folder / f'original-{i+1}.jsonl').read_bytes() for i in range(2)], before)
        again = self.create(); self.assertTrue(again['reused']); self.assertEqual(result['newId'], again['newId'])
        self.assertEqual(len(self.rows()), 2)
        with closing(sqlite3.connect(self.root / 'state_5.sqlite')) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM projects').fetchone()[0], 1)

    def test_not_approved_does_not_read_body_or_create_a_directory(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Body read')):
            with self.assertRaisesRegex(ValueError, '尚未授权'):
                self.create(approved=False)
        self.assertFalse(self.archives.exists()); self.assertEqual(len(self.rows()), 1)

    def test_outside_store_and_wrong_archive_are_rejected(self):
        with self.assertRaisesRegex(ValueError, '自己的资料区'):
            self.create(archive_root=self.project)
        outside = self.base / 'outside.jsonl'; outside.write_bytes(self.sources[0].read_bytes())
        with self.assertRaisesRegex(ValueError, '未读取正文'):
            self.create(source_paths=[outside])
        self.assertEqual(len(self.rows()), 1)

    def test_unknown_item_incomplete_turn_duplicate_branch_and_reversed_chunks_are_rejected(self):
        chunks = [legacy(self.old_id), continued(self.old_id)]
        cases = []
        bad = copy.deepcopy(chunks); bad[1].insert(-1, entry({'type': 'unrecognized'}, '2026-10-23T01:00:00Z')); cases.append(bad)
        bad = copy.deepcopy(chunks); bad[1].pop(); cases.append(bad)
        bad = copy.deepcopy(chunks); bad.append(copy.deepcopy(bad[1])); cases.append(bad)
        bad = copy.deepcopy(chunks); bad[1][4]['timestamp'] = '2026-10-01T00:00:00Z'; cases.append(bad)
        for bad in cases:
            with self.subTest(case=cases.index(bad)), self.assertRaises(ValueError):
                codex_repair.compatible_records(bad, self.old_id, str(uuid.uuid4()))

    def test_existing_original_updated_after_repair_is_preserved_without_duplicate(self):
        self.create()
        with self.sources[-1].open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry({'response_id': 'new-synthetic-reference'}, '2026-10-23T02:00:00Z', 'token_usage_record'))+'\n')
        changed = self.sources[-1].read_bytes()
        with self.assertRaisesRegex(ValueError, '又有变化'):
            self.create()
        self.assertEqual(len(self.rows()), 2); self.assertEqual(self.sources[-1].read_bytes(), changed)

    def test_register_failure_never_changes_original_and_never_removes_a_committed_copy(self):
        before = [p.read_bytes() for p in self.sources]
        with patch.object(codex_import, 'register', side_effect=ValueError('synthetic failure')):
            with self.assertRaisesRegex(ValueError, 'synthetic failure'):
                self.create()
        self.assertEqual(self.rows()[0][0], self.old_id); self.assertEqual(len(self.rows()), 1)
        self.assertEqual([p.read_bytes() for p in self.sources], before)
        self.assertEqual(len(list((self.root / 'sessions').rglob('*.jsonl'))), 2)
        self.assertFalse((self.archives / self.old_id / 'repair.lock').exists())

    def test_receipt_failure_after_commit_preserves_the_usable_copy_and_recovers_without_duplicate(self):
        original_writer = codex_repair._atomic_json
        calls = 0
        def fail_second(path, value):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('synthetic receipt failure')
            original_writer(path, value)
        with patch.object(codex_repair, '_atomic_json', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'synthetic receipt failure'):
                self.create()
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(len(list((self.root / 'sessions').rglob('*.jsonl'))), 3)
        self.assertTrue(self.create()['reused']); self.assertEqual(len(self.rows()), 2)

    def test_archives_cannot_be_written_into_an_existing_project_and_unknown_schema_stops_before_body(self):
        with self.assertRaisesRegex(ValueError, '自己的资料区'):
            self.create(archive_root=self.project)
        with closing(sqlite3.connect(self.root / 'state_5.sqlite')) as c:
            c.execute('ALTER TABLE threads RENAME TO unknown_threads'); c.commit()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Body read')):
            with self.assertRaisesRegex(ValueError, '格式发生变化'):
                self.create()
        self.assertFalse(self.archives.exists())


class NativeRepairTests(unittest.TestCase):
    def test_actual_native_history_reader_can_page_the_repaired_old_and_new_turns_without_starting_a_model_turn(self):
        from test_codex_native import NativeServer, native_binary
        binary = native_binary()
        if binary is None:
            self.skipTest('Installed native history reader unavailable')
        with tempfile.TemporaryDirectory(prefix='ai-first-repair-native-') as scratch:
            base = Path(scratch); env = isolated_env(base)
            for name in list(env):
                if name.startswith('CODEX_') and name != 'CODEX_HOME': env.pop(name)
            root = Path(env['CODEX_HOME']); project = base / 'existing-project'; project.mkdir()
            server = NativeServer(binary, env, base)
            requested = []
            def request(method, args):
                requested.append(method)
                if method not in {'initialize', 'thread/list', 'thread/resume', 'thread/items/list'}:
                    raise AssertionError('Unexpected native operation')
                return server.request(method, args)
            try:
                request('initialize', {'clientInfo': {'name': 'synthetic_repair_check', 'version': '1.0'}, 'capabilities': {'experimentalApi': True}})
                request('thread/list', {'limit': 1})
                old_id = str(uuid.uuid4()); paths = []
                for index, rows in enumerate((legacy(old_id), continued(old_id))):
                    path = root / 'sessions/2026/10/23' / f'synthetic-{index}-{old_id}.jsonl'
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows), encoding='utf-8')
                    paths.append(path)
                document = {'cwd': str(project), 'title': 'Synthetic repair title', 'messages': [{'role': 'user', 'content': '合成原问题'}]}
                codex_import.register(paths[0], old_id, document, 'chatgpt_work', env)
                # Reconstruct an old-format fixture; never use a real conversation.
                paths[0].write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in legacy(old_id)), encoding='utf-8')
                with closing(sqlite3.connect(root / 'state_5.sqlite')) as c:
                    c.execute('UPDATE threads SET rollout_path=? WHERE id=?', (str(paths[-1]), old_id)); c.commit()
                before = [p.read_bytes() for p in paths]
                result = codex_repair.create_copy(root=root, archive_root=Path(env['LOCALAPPDATA'])/'AI一手工具工作台/memory-preview/codex-repairs',
                    source_paths=paths, old_id=old_id, title=document['title'], directory=str(project), env=env, approved=True)
                request('thread/resume', {'threadId': result['newId'], 'cwd': str(project), 'excludeTurns': True,
                                         'sandbox': 'read-only', 'approvalPolicy': 'on-request'})
                cursor = None; items = []
                for _ in range(30):
                    args = {'threadId': result['newId'], 'limit': 19, 'sortDirection': 'asc'}
                    if cursor: args['cursor'] = cursor
                    page = request('thread/items/list', args); items.extend(page['data']); cursor = page.get('nextCursor')
                    if not cursor: break
                self.assertIsNone(cursor)
                self.assertFalse(any(row['item']['type'] == 'reasoning' for row in items))
                displayed = json.dumps(items, ensure_ascii=False)
                for text in ('合成原问题', '合成完整旧回复', '合成历史思考153', '合成搬入后的新问题', '合成搬入后的新回复', '完整合成结果'):
                    self.assertIn(text, displayed)
                self.assertEqual([p.read_bytes() for p in paths], before)
                self.assertNotIn('turn/start', requested)
            finally:
                server.close()


if __name__ == '__main__':
    unittest.main()
