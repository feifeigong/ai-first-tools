"""Synthetic compressed Desktop projects and real local export engine checks."""
import json
import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import zstandard

from core import chatgpt, codex_history, memory_store, mover
import test_codex_sources as fixtures
from test_copilot_import import desktop_index


class CompressedProjectTests(unittest.TestCase):
    setUp = fixtures.CodexSourceTests.setUp
    add = fixtures.CodexSourceTests.add
    flat_cli = fixtures.CodexSourceTests.flat_cli
    flat_desktop = fixtures.CodexSourceTests.flat_desktop

    def compress(self, path, **options):
        raw = path.read_bytes()
        packed = Path(str(path) + '.zst')
        packed.write_bytes(zstandard.ZstdCompressor(**options).compress(raw))
        path.unlink()
        return packed

    def catalog(self, ids, complete=True):
        (self.root / 'sqlite').mkdir(exist_ok=True)
        with closing(sqlite3.connect(self.root / 'state_5.sqlite')) as source:
            rows = {sid: source.execute('SELECT cwd,source FROM threads WHERE id=?', (sid,)).fetchone() for sid in ids}
        with closing(sqlite3.connect(self.root / 'sqlite/codex-dev.db')) as db, db:
            db.executescript('''
CREATE TABLE local_thread_catalog_sync_state(host_id TEXT,initial_build_complete INTEGER);
CREATE TABLE local_thread_catalog(host_id TEXT,thread_id TEXT,display_title TEXT,cwd TEXT,
source_kind TEXT,source_recency_at INTEGER,source_created_at INTEGER,missing_candidate INTEGER,project_id TEXT);
''')
            db.execute("INSERT INTO local_thread_catalog_sync_state VALUES('local',?)", (int(complete),))
            for index, sid in enumerate(ids):
                db.execute("INSERT INTO local_thread_catalog VALUES('local',?,?,?,?,?,0,0,NULL)",
                           (sid, f'合成桌面名称 {index}', *rows[sid], 1791600000000 + index))

    def test_seven_current_project_records_include_old_terminal_origins_and_compressed_bodies(self):
        ids = []
        for i, origin in enumerate(('codex-tui', 'codex-tui', 'codex-tui', 'Codex Desktop',
                                    'codex_work_desktop', 'codex-tui', 'codex_work_desktop')):
            sid, path = self.add(f'旧名称{i}', 'cli' if i < 3 else 'vscode', origin)
            ids.append(sid)
            if i < 5:
                self.compress(path, write_checksum=i % 2 == 0, write_content_size=i % 2 == 1)
        terminal, _ = self.add('仅终端使用')
        self.catalog(ids)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        data = chatgpt.local_data(self.root)
        items = data['projects'][0]['sessions']
        self.assertEqual([s['id'] for s in items], list(reversed(ids)))
        self.assertTrue(all(s['movable'] and not s['note'] for s in items))
        self.assertEqual([s['title'] for s in items], [f'合成桌面名称 {i}' for i in reversed(range(7))])
        self.assertEqual(sum(s['kind'] == 'work' for s in items), 2)
        self.assertEqual({s['id'] for s in self.flat_cli()}, {terminal})
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_incomplete_catalog_does_not_move_cli_into_desktop(self):
        sid, path = self.add('只来自终端')
        self.compress(path)
        self.catalog([sid], complete=False)
        self.assertFalse(self.flat_desktop())
        self.assertEqual([s['id'] for s in self.flat_cli()], [sid])

    def test_projectless_and_cloud_assignments_do_not_reclassify_cli(self):
        first, _ = self.add('明确无项目')
        second, _ = self.add('云项目')
        self.catalog([first, second])
        state = json.loads((self.root / '.codex-global-state.json').read_text())
        state.update({'projectless-thread-ids': [first], 'thread-project-assignments': {
            second: {'projectId': 'same', 'projectKind': 'chatgpt', 'projectOrigin': 'chatgpt'}}})
        (self.root / '.codex-global-state.json').write_text(json.dumps(state), encoding='utf-8')
        self.assertFalse(self.flat_desktop())
        self.assertEqual({s['id'] for s in self.flat_cli()}, {first, second})

    def test_deleted_archived_and_subagent_project_records_remain_hidden(self):
        kept, path = self.add('可见', 'vscode', 'Codex Desktop')
        archived, other = self.add('归档', 'vscode', 'Codex Desktop')
        self.compress(other)
        archive = self.root / 'archived_sessions'; archive.mkdir()
        Path(str(other) + '.zst').rename(archive / (other.name + '.zst'))
        hidden, _ = self.add('已删除', 'cli', 'codex-tui')
        child, _ = self.add('内部任务', 'vscode', 'Codex Desktop', provenance='subagent')
        self.catalog([kept, archived, hidden, child])
        with closing(sqlite3.connect(self.root / 'sqlite/codex-dev.db')) as db, db:
            db.execute('UPDATE local_thread_catalog SET missing_candidate=1 WHERE thread_id=?', (hidden,))
        self.assertEqual([s['id'] for s in self.flat_desktop()], [kept])
        self.assertFalse(self.flat_cli())

    def test_compressed_export_full_copy_and_smart_archive_use_same_read_only_source(self):
        sid, path = self.add('压缩的完整桌面原文', 'vscode', 'codex_work_desktop')
        packed = self.compress(path)
        self.catalog([sid])
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        session = self.flat_desktop()[0]
        document = mover.export_document('chatgpt', session)
        self.assertEqual([m['role'] for m in document['messages']], ['user', 'assistant'])
        self.assertIn('原文末尾标记', json.dumps(document, ensure_ascii=False))
        desktop_index(Path(self.env['COPILOT_HOME']))
        details = {}
        self.assertEqual(mover.move_one('chatgpt', session, 'copilot_desktop', str(self.project), details)[0], 'ok')
        from core.memory_jobs import PrepareJob
        import time
        job = PrepareJob('chatgpt', [session])
        deadline = time.monotonic() + 10
        while not job.snapshot()['finished'] and time.monotonic() < deadline:
            time.sleep(.01)
        status = job.snapshot()
        self.assertTrue(status['finished'])
        self.assertEqual(status['failed'], 0, status)
        bundle = self.base / 'workbench/memory/bundles' / status['items'][0]['bundle']
        self.assertEqual(memory_store.summary(bundle)['messages'], 2)
        self.assertFalse(path.exists())
        self.assertTrue(packed.exists())
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_metadata_does_not_parse_body_and_frames_without_size_or_checksum_work(self):
        sid, path = self.add('只读头', 'vscode', 'Codex Desktop')
        raw = path.read_bytes().split(b'\n')[0] + b'\nnot-json-body\n'
        path.write_bytes(raw)
        packed = self.compress(path, write_content_size=False, write_checksum=False)
        self.assertEqual(codex_history.metadata(packed)['id'], sid)
        with self.assertRaises(ValueError), codex_history.export_home(self.root, sid):
            self.fail('Malformed body must not reach exporter')

    def test_indexed_extended_windows_paths_find_compressed_history(self):
        sid, path = self.add('扩展路径的压缩记录', 'vscode', 'Codex Desktop')
        packed = self.compress(path)
        logical = ('\\\\?\\' + str(path)) if os.name == 'nt' else str(path)
        with closing(sqlite3.connect(self.root/'state_5.sqlite')) as db, db:
            db.execute('UPDATE threads SET rollout_path=? WHERE id=?', (logical,sid))
        resolved = codex_history.resolve(self.root,sid,logical)
        self.assertIsNotNone(resolved)
        self.assertTrue(resolved.samefile(packed))
        with codex_history.export_home(self.root,sid) as home:
            self.assertIn('原文末尾标记',next((home/'sessions').glob('*')).read_text(encoding='utf-8'))

    def test_truncation_trailing_garbage_and_unknown_envelope_never_reach_import(self):
        sid, path = self.add('损坏资料', 'vscode', 'Codex Desktop')
        raw = path.read_bytes()
        valid = zstandard.ZstdCompressor().compress(raw)
        unknown = json.dumps({'type': 'unknown-future-format', 'payload': {}}).encode() + b'\n'
        variants = [valid[:-1], valid + b'broken-frame',
                    valid + zstandard.ZstdCompressor().compress(unknown)]
        packed = Path(str(path) + '.zst'); path.unlink()
        for data in variants:
            with self.subTest(size=len(data)), patch.object(mover, '_run', side_effect=AssertionError('Must validate before exporter')):
                packed.write_bytes(data)
                with self.assertRaises(ValueError):
                    mover.export_document('chatgpt_work', {'id': sid})
                self.assertEqual(packed.read_bytes(), data)

    def test_concatenated_frames_and_large_window_export_all_messages(self):
        sid, path = self.add('分帧资料', 'vscode', 'Codex Desktop')
        raw = path.read_bytes()
        split = raw.index(b'\n') + 1
        c = zstandard.ZstdCompressor(write_content_size=False)
        packed = Path(str(path) + '.zst')
        packed.write_bytes(c.compress(raw[:split]) + c.compress(raw[split:]))
        path.unlink()
        with codex_history.export_home(self.root, sid) as home:
            self.assertEqual(next((home / 'sessions').glob('*')).read_bytes(), raw)
            temporary = home
        self.assertFalse(temporary.exists())

    def test_two_megabyte_stream_window_is_supported_without_unbounded_decompression(self):
        sid, path = self.add('较长的压缩资料', 'vscode', 'Codex Desktop')
        records = [json.loads(line) for line in path.read_bytes().splitlines()]
        records[-1]['payload']['content'][0]['text'] = '合成较长历史' * 150000 + '完整末尾'
        raw = b'\n'.join(json.dumps(r, ensure_ascii=False).encode() for r in records) + b'\n'
        path.write_bytes(raw)
        packed = self.compress(path, write_content_size=False)
        self.assertGreater(zstandard.get_frame_parameters(packed.read_bytes()).window_size, 65536)
        with codex_history.export_home(self.root, sid) as home:
            self.assertEqual(next((home/'sessions').glob('*')).read_bytes(), raw)

    def test_decompression_window_budget_and_source_update_are_protected(self):
        sid, path = self.add('保护检查', 'vscode', 'Codex Desktop')
        records = [json.loads(line) for line in path.read_bytes().splitlines()]
        records[-1]['payload']['content'][0]['text'] = 'long synthetic answer ' * 1000
        path.write_bytes(b'\n'.join(json.dumps(r).encode() for r in records) + b'\n')
        packed = self.compress(path, write_content_size=False)
        with patch.object(codex_history,'MAX_WINDOW',1024):
            with self.assertRaises(ValueError), codex_history.export_home(self.root,sid):
                self.fail('Oversized window')
        original = codex_history._chunks
        def changing(file):
            yield from original(file)
            file.write_bytes(file.read_bytes() + b'changed')
        with patch.object(codex_history,'_chunks',side_effect=changing):
            with self.assertRaises(ValueError), codex_history.export_home(self.root,sid):
                self.fail('Concurrent change')

    def test_identity_mismatch_external_path_and_incomplete_paginated_history_refused(self):
        sid, path = self.add('需要完整性保护', 'vscode', 'Codex Desktop')
        outside = self.base / 'outside.jsonl.zst'
        packed = self.compress(path)
        outside.write_bytes(packed.read_bytes())
        packed.unlink()
        with closing(sqlite3.connect(self.root / 'state_5.sqlite')) as db, db:
            db.execute('UPDATE threads SET rollout_path=? WHERE id=?', (str(outside), sid))
        self.assertIsNone(codex_history.resolve(self.root, sid, str(outside)))
        raw = zstandard.ZstdDecompressor().decompress(outside.read_bytes())
        records = [json.loads(line) for line in raw.splitlines()]
        records[0]['payload']['id'] = 'wrong-identity'
        packed.write_bytes(zstandard.ZstdCompressor().compress(b'\n'.join(json.dumps(r).encode() for r in records) + b'\n'))
        self.assertIsNone(codex_history.resolve(self.root, sid))
        records[0]['payload']['id'] = sid; records[0]['ordinal'] = 123
        packed.write_bytes(zstandard.ZstdCompressor().compress(b'\n'.join(json.dumps(r).encode() for r in records) + b'\n'))
        with self.assertRaises(ValueError), codex_history.export_home(self.root, sid):
            self.fail('A tail is not a complete archive')

    def test_size_and_window_limits_refuse_decompression(self):
        sid, path = self.add('受限资料', 'vscode', 'Codex Desktop')
        self.compress(path)
        with patch.object(codex_history, 'MAX_BYTES', 20), self.assertRaises(ValueError):
            with codex_history.export_home(self.root, sid):
                self.fail('Too large')

    def test_project_projection_does_not_read_auth_or_return_accounts(self):
        state = json.loads((self.root / '.codex-global-state.json').read_text())
        state['electron-persisted-atom-state'] = {'synthetic-account': 'must-not-return'}
        (self.root / '.codex-global-state.json').write_text(json.dumps(state), encoding='utf-8')
        value = chatgpt.project_layout(self.root)
        self.assertNotIn('electron-persisted-atom-state', value)
        self.assertIn('local-projects', value)


if __name__ == '__main__':
    unittest.main()
