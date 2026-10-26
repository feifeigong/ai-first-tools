from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'macos'))
from entry import MacApi
from core import memory_deploy, memory_desktop, memory_store, memory_workspace, memory_jobs, mover
from core.memory_audit import desktop_fixture
from test_memory import fixture


class MacMemoryParityTests(unittest.TestCase):
    def setUp(self):
        self.scratch = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.scratch).resolve()
        self.library = self.root / 'memory'
        self.desktop = self.root / 'copilot'
        desktop_fixture(self.desktop)
        self.enterContext(patch.object(memory_jobs, 'library', return_value=self.library))
        self.enterContext(patch.object(memory_desktop, 'root', return_value=self.desktop))
        self.export = self.enterContext(patch.object(mover, 'export_document', return_value=fixture()))
        self.api = MacApi()
        self.api._groups = {'chatgpt':[{'sessions':[{'id':'synthetic-history','title':'合成开发讨论','movable':True}]}]}

    def prepare(self):
        self.assertTrue(self.api.prepare_memory('chatgpt',['synthetic-history'],'copilot_desktop')['ok'])
        deadline = time.monotonic() + 10
        while not self.api.memory_status()['finished'] and time.monotonic() < deadline: time.sleep(.01)
        self.assertEqual(self.api.memory_status()['failed'], 0)
        result = self.api.memory_plan()
        self.assertTrue(result.get('ok'), result)
        return result

    def test_mac_api_uses_full_archive_independent_project_and_same_repeat_protection(self):
        plan = self.prepare()
        self.assertTrue(Path(plan['workspace']).is_relative_to(self.library / 'copilot-workspaces'))
        result = self.api.deploy_memory()
        self.assertTrue(result.get('ok'), result)
        original_files = {p.relative_to(self.desktop):p.read_bytes() for p in self.desktop.rglob('*') if p.is_file()}
        self.prepare()
        repeated = self.api.deploy_memory()
        self.assertTrue(repeated.get('reused'), repeated)
        self.assertEqual(repeated['id'], result['id'])
        self.assertEqual({p.relative_to(self.desktop):p.read_bytes() for p in self.desktop.rglob('*') if p.is_file()}, original_files)
        bundle = self.api.memory_status()['items'][0]['bundle']
        self.assertEqual(json.loads((self.library / 'bundles' / bundle / 'archive/original.json').read_text(encoding='utf-8')), fixture())
        self.assertTrue(self.api.search_memory('数据库')['hits'])

    def test_mac_memory_writes_cannot_race_update_handoff(self):
        self.api._handing_off = True
        for result in (self.api.prepare_memory('chatgpt',['synthetic-history'],'copilot_desktop'),
                       self.api.deploy_memory(), self.api.rollback_memory(), self.api.start_full_from_memory('codex','synthetic')):
            self.assertIn('正在更新', result['error'])
        self.assertFalse(self.library.exists())
        self.export.assert_not_called()

    def test_local_mac_preview_cannot_download_updates_or_consume_formal_update_receipt(self):
        update_root=self.root/'updates';update_root.mkdir()
        receipt=update_root/'result.json';receipt.write_text('{"version":"synthetic","message":"keep formal receipt"}')
        before=receipt.read_bytes()
        with patch('entry.version_info',return_value={'release':'synthetic','developmentPreview':True}), \
             patch('entry.updater.state_root',return_value=update_root), patch('entry.updates.check') as check:
            info=self.api.workspace_info()
            self.assertFalse(info['automaticChecks'])
            self.assertFalse(self.api.check_update()['available'])
            self.assertIn('error',self.api.start_update())
            check.assert_not_called()
        self.assertEqual(receipt.read_bytes(),before)

    def test_headless_mac_entry_serves_real_stdio_without_cocoa_or_writes(self):
        info = memory_store.ingest(self.library, 'fixture', 'synthetic-stdio', fixture())
        workspace = memory_workspace.create(self.library)
        plan = memory_deploy.build_plan(workspace, 'copilot_desktop', self.library, [info['id']])
        memory_deploy.install(plan, self.library)
        before = {p.relative_to(self.library):p.read_bytes() for p in self.library.rglob('*') if p.is_file()}
        requests = [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'isolated-mac-check','version':'1'}}},
            {'jsonrpc':'2.0','id':2,'method':'tools/list'},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'search_history','arguments':{'query':'数据库','max_tokens':200}}},
        ]
        completed = subprocess.run([sys.executable,str(ROOT/'macos/entry.py'),'--memory-service','--root',str(workspace/'.agent-memory')],
            input='\n'.join(json.dumps(value) for value in requests)+'\n',text=True,encoding='utf-8',capture_output=True,timeout=20)
        self.assertEqual(completed.returncode,0,completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([r['id'] for r in responses],[1,2,3])
        self.assertEqual({tool['name'] for tool in responses[1]['result']['tools']},{'search_history','read_history','get_current_state'})
        self.assertFalse(responses[2]['result']['isError'])
        self.assertEqual({p.relative_to(self.library):p.read_bytes() for p in self.library.rglob('*') if p.is_file()},before)

    def test_frozen_mac_reader_uses_the_same_app_headlessly(self):
        executable = self.root / '中文 空格' / 'AI一手工具工作台.app/Contents/MacOS/AI First Tools'
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b'synthetic')
        with patch('sys.platform','darwin'),patch('sys.frozen',True,create=True),patch('sys.executable',str(executable)):
            self.assertEqual(memory_deploy.runtime_command(),[str(executable),'--memory-service'])

    def test_close_is_blocked_while_a_source_is_being_saved(self):
        started, release = threading.Event(), threading.Event()
        def export(*args):
            started.set();release.wait(5);return fixture()
        self.export.side_effect=export
        try:
            self.assertTrue(self.api.prepare_memory('chatgpt',['synthetic-history'],'copilot_desktop')['ok'])
            self.assertTrue(started.wait(2))
            self.assertFalse(self.api.can_close())
        finally:
            release.set()
            deadline=time.monotonic()+10
            while not self.api.memory_status()['finished'] and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(self.api.can_close())

    def test_native_close_returns_immediately_while_a_memory_write_holds_update_gate(self):
        held, release, answered = threading.Event(), threading.Event(), threading.Event()
        replies=[]
        def write():
            with self.api._update_gate, self.api._lock:
                held.set();release.wait(3)
        def close():
            replies.append(self.api.can_close());answered.set()
        writer=threading.Thread(target=write);writer.start()
        self.assertTrue(held.wait(1))
        closer=threading.Thread(target=close);closer.start()
        try:
            self.assertTrue(answered.wait(.5),'Close should decline without waiting for the write to finish')
            self.assertEqual(replies,[False])
        finally:
            release.set();writer.join(3);closer.join(3)


if __name__ == '__main__': unittest.main()
