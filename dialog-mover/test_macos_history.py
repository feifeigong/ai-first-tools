"""Exercise MacApi with synthetic compressed projects, never a real account."""
from __future__ import annotations

import ast
import io
import json
import sqlite3
import sys
import time
import unittest
from contextlib import closing, redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'macos'))
sys.path.insert(0, str(ROOT/'scripts'))

import entry
import test_codex_compressed as fixtures
from core import chatgpt, memory_desktop, memory_store, mover
from core.memory_audit import desktop_fixture
from check_macos_parity import fingerprint


class MacHistoryParityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CompressedProjectTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        # Keep the real engine for this host. Selecting Darwin changes business
        # paths, not the architecture of this Windows synthetic-test process.
        engine = mover.txcript_path()
        self.assertIsNotNone(engine)
        self.enterContext(patch.object(mover, 'txcript_path', return_value=engine))

    def move_metadata(self, sid, path, cwd):
        with closing(sqlite3.connect(self.fixture.root/'state_5.sqlite')) as db, db:
            db.execute('UPDATE threads SET cwd=? WHERE id=?', (cwd,sid))
        records = path.read_text(encoding='utf-8').splitlines()
        meta = json.loads(records[0]); meta['payload']['cwd'] = cwd
        path.write_text('\n'.join([json.dumps(meta), *records[1:]])+'\n',encoding='utf-8')

    def test_mac_api_seven_project_records_and_actual_compressed_smart_export(self):
        f = self.fixture
        project = '/Users/synthetic/Projects/中文 项目'
        state = {'local-projects': {'same': {'name': '合成 Mac 项目','rootPaths':[project]}}}
        (f.root/'.codex-global-state.json').write_text(json.dumps(state),encoding='utf-8')
        ids = []
        for index in range(7):
            sid,path = f.add(f'原名称{index}', 'cli' if index<3 else 'vscode',
                             'codex-tui' if index<3 else 'codex_work_desktop')
            self.move_metadata(sid,path,project)
            ids.append(sid)
            if index<5:
                f.compress(path,write_content_size=False)
        terminal,path=f.add('仅终端记录'); self.move_metadata(terminal,path,project)
        f.catalog(ids)
        desktop = f.base/'mac-copilot';desktop_fixture(desktop)
        before={p.relative_to(f.root):p.read_bytes() for p in f.root.rglob('*') if p.is_file()}
        existing=f.project/'keep.txt';existing.write_bytes(b'synthetic existing project: keep unchanged')
        with patch.object(sys,'platform','darwin'), \
             patch.object(chatgpt,'web_data',return_value={'items':[],'projects':[]}), \
             patch.object(chatgpt,'info',return_value={}), \
             patch.object(memory_desktop,'root',return_value=desktop):
            api=entry.MacApi()
            data=api.sessions('chatgpt')
            self.assertEqual((data['total'],data['movable']),(7,7))
            sessions=[s for g in data['groups'] for s in g['sessions']]
            self.assertEqual([s['id'] for s in sessions],list(reversed(ids)))
            self.assertTrue(all(s['folder']==project and not s['note'] for s in sessions))
            self.assertEqual([s['id'] for s in chatgpt.cli_sessions(f.root)],[terminal])
            self.assertTrue(api.prepare_memory('chatgpt',[ids[0]],'copilot_desktop')['ok'])
            deadline=time.monotonic()+10
            while not api.memory_status()['finished'] and time.monotonic()<deadline:time.sleep(.01)
            saved=api.memory_status()
            self.assertTrue(saved['finished']);self.assertEqual(saved['failed'],0,saved)
            bundle=f.base/'workbench/memory/bundles'/saved['items'][0]['bundle']
            info=memory_store.summary(bundle)
            self.assertEqual(info['messages'],2)
            self.assertIn('原文末尾标记',(bundle/'archive/original.json').read_text(encoding='utf-8'))
            plan=api.memory_plan();self.assertTrue(plan.get('ok'),plan)
        self.assertEqual(existing.read_bytes(),b'synthetic existing project: keep unchanged')
        self.assertEqual(before,{p.relative_to(f.root):p.read_bytes() for p in f.root.rglob('*') if p.is_file()})

    def test_mac_project_case_and_chinese_space_paths_do_not_merge(self):
        f=self.fixture
        paths=('/Users/synthetic/Projects/项目 A','/Users/synthetic/Projects/项目 a')
        state={'local-projects':{str(i):{'name':f'合成项目{i}','rootPaths':[p]} for i,p in enumerate(paths)}}
        (f.root/'.codex-global-state.json').write_text(json.dumps(state),encoding='utf-8')
        ids=[]
        for index,cwd in enumerate(paths):
            sid,path=f.add(f'Case {index}','vscode','Codex Desktop')
            self.move_metadata(sid,path,cwd);f.compress(path);ids.append(sid)
        with patch.object(sys,'platform','darwin'):
            data=chatgpt.local_data(f.root)
        by_id={p['id']:p for p in data['projects']}
        for index,cwd in enumerate(paths):
            self.assertEqual(by_id[str(index)]['path'],cwd)
            self.assertEqual([s['id'] for s in by_id[str(index)]['sessions']],[ids[index]])

    def test_mac_packaged_compatibility_report_executes_shared_seven_checks(self):
        report=self.fixture.base/'mac-codex-report.json'
        with patch.object(entry,'version_info',return_value={'release':'synthetic-unpublished'}):
            self.assertEqual(entry.codex_import_check(report),0)
        result=json.loads(report.read_text(encoding='utf-8'))
        self.assertEqual(len(result['checks']),7)
        self.assertTrue(all(result['checks'].values()))
        self.assertEqual(result['modelRequests'],0)
        self.assertFalse(result['nativeContinuationVerified'])
        self.assertFalse(result['frozen'])

    def test_history_test_routes_before_cocoa_and_requires_a_report(self):
        report=self.fixture.base/'report.json'
        with patch.object(sys,'platform','darwin'), \
             patch.object(sys,'argv',['macos-entry','--codex-import-test','--report',str(report)]), \
             patch.object(entry,'codex_import_check',return_value=0) as check, \
             patch.object(entry.webview,'create_window',side_effect=AssertionError('No GUI for a packaged audit')):
            self.assertEqual(entry.run(),0);check.assert_called_once_with(report)
        with patch.object(sys,'platform','darwin'),patch.object(sys,'argv',['macos-entry','--codex-import-test']),redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:entry.run()
            self.assertEqual(error.exception.code,2)

    def test_decoder_dependency_and_validation_inputs_are_in_mac_build(self):
        imports=[]
        for node in ast.walk(ast.parse((ROOT/'macos/AI-First-Tools.spec').read_text(encoding='utf-8'))):
            if isinstance(node,ast.keyword) and node.arg=='hiddenimports':
                imports=ast.literal_eval(node.value.left)
        self.assertIn('zstandard',imports)
        self.assertIn('zstandard==0.23.0',(ROOT/'dialog-mover/requirements.txt').read_text())
        self.assertIn('../dialog-mover/requirements.txt',(ROOT/'macos/requirements.txt').read_text())
        hashes=fingerprint()
        for name in ('macos/AI-First-Tools.spec','macos/requirements.txt','dialog-mover/requirements.txt',
                     'dialog-mover/core/codex_history.py','scripts/package_macos.py','scripts/stage_macos_release.py'):
            self.assertIn(name,hashes)


if __name__=='__main__':unittest.main()
