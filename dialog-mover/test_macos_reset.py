from __future__ import annotations
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'macos'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'auto-resume/src'))
import reset_notices as notices
import auto_resume
from codex_auto_resume import watch_control

DLL = Path(__file__).resolve().parents[1] / 'macos/ResetBridge/bin/Release/net8.0/AI.First.ResetBridge.dll'


class MacResetTests(unittest.TestCase):
    def setUp(self):
        self.scratch = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.scratch).resolve()
        self.bundle = self.root / notices.APP
        self.directory = self.root / 'state'
        self.client = Mock()
        self.client.request.return_value = {'enabled': True, 'events': []}
        self.monitor = notices.Monitor(self.bundle, self.directory, self.client)
        self.monitor.executable.parent.mkdir(parents=True)
        self.monitor.executable.write_text('synthetic non-executable fixture')
        self.identity = {'started': 'Fri Oct 23 09:00:00 2026', 'command': str(self.monitor.executable) + ' ' + notices.WATCH}
        self.owner = {'format': notices.FORMAT, 'pid': 1234, 'token': 'a' * 32,
            'executable': str(self.monitor.executable), 'started': self.identity['started']}

    def test_disabled_notifications_never_launch_and_do_not_touch_resume(self):
        self.client.request.return_value['enabled'] = False
        with patch('reset_notices.subprocess.Popen') as launch, patch.object(auto_resume.Controller, 'action') as resume:
            self.monitor.ensure()
            launch.assert_not_called(); resume.assert_not_called()
        self.assertFalse(self.directory.exists())

    def test_independent_background_uses_the_same_bundle_without_external_runtime(self):
        with patch('reset_notices.subprocess.Popen') as launch:
            self.monitor.ensure()
        self.assertEqual(launch.call_args.args[0], [str(self.monitor.executable), notices.WATCH])
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        self.assertEqual(launch.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')

    def test_foreign_owned_notifier_is_neither_stopped_nor_replaced(self):
        foreign = self.root / 'other' / notices.APP / 'Contents/MacOS/AI First Tools'
        owner = {**self.owner, 'executable': str(foreign)}
        notices.write_json(self.monitor.owner_path, owner)
        before = self.monitor.owner_path.read_bytes()
        with patch('reset_notices.process_identity', return_value={**self.identity, 'command': str(foreign) + ' ' + notices.WATCH}), \
             patch('reset_notices.subprocess.Popen') as launch:
            self.monitor.ensure(); self.monitor.stop_owned('update')
        launch.assert_not_called()
        self.assertFalse(self.monitor.stop_path.exists())
        self.assertFalse(self.monitor.receipt.exists())
        self.assertEqual(self.monitor.owner_path.read_bytes(), before)

    def test_stop_targets_exact_owner_and_preserves_settings(self):
        notices.write_json(self.monitor.owner_path, self.owner)
        settings = self.directory / 'state.json'
        settings.write_bytes(b'{"enabled":true}')
        with patch('reset_notices.process_identity', side_effect=[self.identity, self.identity, None, None]):
            self.monitor.stop_owned('update')
        self.assertEqual(notices.read_json(self.monitor.stop_path), {'token': self.owner['token'], 'executable': self.owner['executable']})
        self.assertTrue(notices.read_json(self.monitor.receipt)['restart'])
        self.assertEqual(settings.read_bytes(), b'{"enabled":true}')

    def test_pid_reuse_and_owner_changes_cannot_stop_an_unrelated_process(self):
        notices.write_json(self.monitor.owner_path, self.owner)
        with patch('reset_notices.process_identity', return_value={**self.identity, 'started': 'different start'}):
            with self.assertRaises(notices.NoticeError): self.monitor.stop_owned()
        self.assertFalse(self.monitor.stop_path.exists())
        with patch.object(self.monitor, 'live_owner', side_effect=[self.owner, {**self.owner, 'token':'b'*32}]):
            with self.assertRaises(notices.NoticeError): self.monitor.stop_owned()
        self.assertFalse(self.monitor.stop_path.exists())

    def test_stop_waits_for_the_owned_process_after_metadata_is_released(self):
        with patch.object(self.monitor,'live_owner',side_effect=[self.owner,self.owner,None,None]), \
             patch('reset_notices.process_identity',side_effect=[self.identity,None]), patch('reset_notices.time.sleep') as wait:
            self.monitor.stop_owned()
        wait.assert_called_once_with(.2)

    def test_held_lock_prevents_duplicate_start_without_overwriting_owner(self):
        lease = notices.Lease(self.directory / 'monitor.lock')
        self.assertTrue(lease.acquire())
        try:
            with patch('reset_notices.subprocess.Popen') as launch: self.monitor.ensure()
            launch.assert_not_called()
        finally: lease.close()

    def test_monitor_claim_and_delivery_do_not_change_resume_and_clean_only_own_files(self):
        stopped = False
        alert = {'id':'2113162413008884099','summary':'合成预告'}
        self.client.request.side_effect = [{'enabled':True,'events':[]},{'enabled':True,'events':[],'alert':alert}]
        def notify(value):
            nonlocal stopped
            self.assertEqual(value, alert); stopped = True
        with patch('reset_notices.process_identity', return_value=self.identity), patch.object(auto_resume.Controller, 'action') as resume:
            self.assertEqual(self.monitor.run(notify, lambda: stopped), 0)
            resume.assert_not_called()
        self.assertFalse(self.monitor.owner_path.exists())
        self.assertEqual(self.client.request.call_args_list[0].args, ('refresh',))
        self.assertFalse(self.client.request.call_args_list[0].kwargs['manual'])

    def test_stopping_during_fetch_does_not_deliver_and_release_is_cooperative(self):
        stopped = False
        def request(*args, **kwargs):
            nonlocal stopped
            stopped = True
            return {'enabled':True,'events':[]}
        self.client.request.side_effect = request
        with patch('reset_notices.process_identity', return_value=self.identity):
            notified = Mock()
            self.assertEqual(self.monitor.run(notified, lambda: stopped), 0)
        notified.assert_not_called()
        self.assertEqual(self.client.request.call_count, 1)
        self.assertFalse(self.monitor.owner_path.exists())

    def test_malformed_owner_is_preserved_and_does_not_launch(self):
        notices.write_json(self.monitor.owner_path, {**self.owner,'token':12})
        before = self.monitor.owner_path.read_bytes()
        with patch('reset_notices.subprocess.Popen') as launch:
            with self.assertRaises(notices.NoticeError): self.monitor.ensure()
        launch.assert_not_called()
        self.assertEqual(self.monitor.owner_path.read_bytes(), before)

    def test_mac_identity_handles_spaces_without_splitting_executable(self):
        path = str(self.monitor.executable)
        with patch('sys.platform','darwin'), patch('codex_auto_resume.watch_control._darwin_process_start',return_value=1792994400123456), \
            patch('codex_auto_resume.watch_control._darwin_process_path',return_value=Path(path)), \
            patch('codex_auto_resume.watch_control.subprocess.check_output',
            side_effect=[path+'\n',path+' --auto-resume-watch --manual\n']):
            result = watch_control._inspect_process(1234)
        self.assertEqual(result['argv'], [path,'--auto-resume-watch','--manual'])

    def test_notifier_identity_also_uses_kernel_birth_time(self):
        from types import SimpleNamespace
        command = str(self.monitor.executable) + ' ' + notices.WATCH
        with patch('codex_auto_resume.watch_control._darwin_process_start',return_value=1792994400123456), \
                patch('reset_notices.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=command+'\n')) as ps:
            self.assertEqual(notices.process_identity(1234),{'started':1792994400123456,'command':command})
        self.assertNotIn('lstart=',ps.call_args.args[0])

    def test_packaged_mac_watcher_requires_bundle_identity_and_exact_mode(self):
        import plistlib
        info = self.monitor.executable.parent.parent / 'Info.plist'
        info.write_bytes(plistlib.dumps({'CFBundleIdentifier':'cn.aifirst.tools','CFBundleExecutable':'AI First Tools'}))
        identity = {'executable':str(self.monitor.executable),'argv':[str(self.monitor.executable),'--auto-resume-watch']}
        with patch('sys.platform','darwin'):
            self.assertTrue(watch_control._watcher(identity))
            self.assertFalse(watch_control._watcher({**identity,'argv':[str(self.monitor.executable),'--reset-monitor']}))
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier':'cn.aifirst.tools.preview','CFBundleExecutable':'AI First Tools'}))
            self.assertTrue(watch_control._watcher(identity))
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier':'foreign','CFBundleExecutable':'AI First Tools'}))
            self.assertFalse(watch_control._watcher(identity))

    def test_named_preview_watcher_requires_the_independent_bundle_identifier(self):
        import plistlib
        executable = self.root/'AI一手工具工作台预览.app/Contents/MacOS/AI First Tools'
        executable.parent.mkdir(parents=True); executable.touch()
        info = executable.parent.parent/'Info.plist'
        identity = {'executable':str(executable),'argv':[str(executable),'--auto-resume-watch']}
        for identifier,expected in (('cn.aifirst.tools.preview',True),('cn.aifirst.tools',False)):
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier':identifier,'CFBundleExecutable':'AI First Tools'}))
            with patch('sys.platform','darwin'): self.assertEqual(watch_control._watcher(identity),expected)

    def test_resume_stop_never_sends_termination_even_when_still_finishing(self):
        controller = auto_resume.Controller(self.bundle, self.root / 'home')
        controller.watchers = Mock(return_value=[1234])
        with patch('codex_auto_resume.watch_control.request_stop', return_value=0), \
             patch('auto_resume.time.monotonic', side_effect=[0,0,20]), patch('auto_resume.time.sleep'), patch('os.kill') as kill:
            with self.assertRaises(auto_resume.ControlError): controller.stop()
        kill.assert_not_called()

    @unittest.skipUnless(DLL.is_file(), 'Build macos/ResetBridge first; CI requires this build')
    def test_actual_shared_bridge_is_offline_until_refresh_and_switches_are_independent(self):
        client = notices.Client(self.directory, ['dotnet',str(DLL)])
        first = client.request()
        self.assertTrue(first['enabled']); self.assertEqual(first['events'], [])
        self.assertFalse(self.directory.exists())
        self.assertFalse(client.request('enabled', enabled=False)['enabled'])
        self.assertFalse(client.request('refresh', manual=True)['enabled'])
        self.assertTrue(client.request('enabled', enabled=True)['enabled'])

    def test_post_navigation_accepts_only_the_verified_cached_tibo_id(self):
        client = notices.Client(self.directory, ['synthetic'])
        identity = '2113162413008884099'
        value = {'enabled':True,'events':[{'id':identity,'url':'https://evil.invalid/'}]}
        with patch.object(client,'request',return_value=value), patch('core.common.open_external') as opened:
            with self.assertRaises(notices.NoticeError): client.open_post(identity)
            opened.assert_not_called()
            value['events'][0]['url'] = 'https://x.com/thsottiaux/status/'+identity
            self.assertTrue(client.open_post(identity)['ok'])
            opened.assert_called_once_with(value['events'][0]['url'])

    def test_popup_only_pauses_after_the_explicit_user_button(self):
        alert = {'id':'2113162413008884099','url':'https://x.com/thsottiaux/status/2113162413008884099',
                 'summary':'合成重置消息','description':'合成说明','timeText':'北京时间 02:00 前','timeNote':''}
        dialog = Mock()
        fake_alert = Mock();fake_alert.alloc.return_value.init.return_value=dialog
        fake_app = Mock()
        modules = {'AppKit':SimpleNamespace(NSAlert=fake_alert,NSApplication=fake_app),
                   'PyObjCTools':SimpleNamespace(AppHelper=SimpleNamespace(callAfter=lambda fn,*args:fn(*args)))}
        with patch.dict(sys.modules,modules), patch.object(auto_resume.Controller,'action',return_value={'running':False,'autostart':False}) as action, \
             patch('core.common.open_external') as opened, patch('reset_notices.threading.Thread',side_effect=lambda target,daemon:SimpleNamespace(start=target)):
            dialog.runModal.return_value=1000
            notices.show_notice(alert)
            action.assert_not_called();opened.assert_not_called()
            dialog.runModal.return_value=1001
            notices.show_notice(alert)
            opened.assert_called_once_with(alert['url']);action.assert_not_called()
            dialog.runModal.return_value=1002
            notices.show_notice(alert)
            action.assert_called_once_with('stop')


if __name__ == '__main__': unittest.main()
