from __future__ import annotations
import json
import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'macos'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'auto-resume/src'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from auto_resume import Controller,ControlError,LABEL,WATCH

class MacResumeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.controller=Controller(self.root/'AI一手工具工作台.app',self.root/'home')
        self.controller.executable.parent.mkdir(parents=True)
        self.controller.executable.write_text('synthetic non executable')
        self.controller.watchers=Mock(return_value=[])
        self.controller.launchctl=Mock()
        self.controller.start=Mock()
        self.controller.stop=Mock()

    def test_fresh_status_does_not_install_or_start(self):
        self.assertFalse(self.controller.status()['running'])
        self.assertFalse(self.controller.status()['autostart'])
        self.assertFalse(self.controller.root.exists())

    def test_timer_only_and_resume_switches_preserve_independent_preferences(self):
        running=False
        def start():
            nonlocal running
            running=True
        def stop():
            nonlocal running
            running=False
        self.controller.start.side_effect=start;self.controller.stop.side_effect=stop
        self.controller.watchers.side_effect=lambda:[123] if running else []
        value=self.controller.act('timer-on')
        self.assertTrue(value['running']);self.assertTrue(value['autoStartWindow'])
        self.assertFalse(value['resumeEnabled']);self.assertFalse(value['autoRedeem'])
        self.controller.startup(True)
        value=self.controller.act('resume-on')
        self.assertTrue(value['resumeEnabled']);self.assertFalse(value['autoRedeem'])
        value=self.controller.act('resume-off')
        self.assertTrue(value['running']);self.assertTrue(value['autoStartWindow']);self.assertTrue(value['autostart'])
        self.assertFalse(value['resumeEnabled'])
        value=self.controller.act('timer-off')
        self.assertFalse(value['running']);self.assertFalse(value['autostart'])

    def test_disable_credit_keeps_resume_startup_and_timer_choices(self):
        from codex_auto_resume.automation import control
        control('resume-on',self.controller.policy_root)
        control('credit-on',self.controller.policy_root)
        self.controller.watchers.return_value=[123]
        self.controller.startup(True)
        value=self.controller.act('credit-off')
        self.assertTrue(value['resumeEnabled']);self.assertTrue(value['autostart']);self.assertFalse(value['autoRedeem'])
        self.controller.stop.assert_called_once();self.controller.start.assert_called_once()

    def test_startup_is_self_contained_and_does_not_change_running(self):
        self.controller.startup(True)
        value=self.controller.registration()
        self.assertEqual(value['ProgramArguments'],[str(self.controller.executable),WATCH])
        self.assertFalse(value['KeepAlive'])
        self.controller.startup(False)
        self.assertFalse(self.controller.plist.exists())
        self.controller.start.assert_not_called();self.controller.stop.assert_not_called()

    def test_stop_disables_startup_before_stopping(self):
        self.controller.startup(True)
        self.controller.stop.side_effect=lambda:self.assertFalse(self.controller.plist.exists())
        self.controller.act('stop')
        self.controller.stop.assert_called_once()
        self.assertFalse(self.controller.enabled())

    def test_update_receipt_restores_running_and_keeps_startup(self):
        self.controller.startup(True)
        self.controller.watchers.return_value=[123]
        self.controller.act('prepare-update')
        self.assertTrue(self.controller.receipt.exists())
        self.controller.act('finish-update')
        self.controller.start.assert_called_once()
        self.assertFalse(self.controller.receipt.exists())
        self.assertTrue(self.controller.enabled())

    def test_foreign_registration_is_preserved(self):
        self.controller.startup(True)
        path=self.controller.plist
        value=self.controller.registration();value['ProgramArguments']=['/other/app',WATCH]
        path.write_bytes(plistlib.dumps(value))
        before=path.read_bytes()
        with self.assertRaises(ControlError): self.controller.startup(False)
        self.assertEqual(path.read_bytes(),before)

    def test_uninstall_clears_registration_and_receipt(self):
        self.controller.startup(True)
        self.controller.write(self.controller.receipt,{'restart':True})
        self.controller.act('uninstall')
        self.assertFalse(self.controller.receipt.exists())
        self.assertFalse(self.controller.plist.exists())
        self.controller.stop.assert_called_once()

    def test_process_identity_requires_exact_packaged_watch_command(self):
        self.controller=Controller(self.controller.bundle,self.controller.home)
        with patch('codex_auto_resume.watch_control.state_path',return_value=self.root/'watch.pid'), \
             patch('codex_auto_resume.watch_control.inspect_watch',return_value={'running':True,'pid':10,'executable':str(self.controller.executable)}) as inspect:
            self.assertEqual(self.controller.watchers(),[10])
            inspect.return_value['executable']=str(self.root/'other'/self.controller.executable.name)
            with self.assertRaises(ControlError): self.controller.watchers()

    def test_verified_other_package_is_reused_and_only_explicit_stop_controls_it(self):
        self.controller=Controller(self.controller.bundle,self.controller.home)
        other=Controller(self.root/'another'/'AI一手工具工作台.app',self.controller.home)
        other.executable.parent.mkdir(parents=True);other.executable.write_text('synthetic')
        other.startup(True)
        value={'running':True,'pid':321,'executable':str(other.executable)}
        def stopped(controller): value.update(running=False,pid=None,executable=None)
        with patch('codex_auto_resume.watch_control.state_path',return_value=self.root/'watch.pid'), \
             patch('codex_auto_resume.watch_control.inspect_watch',side_effect=lambda path:dict(value)), \
             patch.object(Controller,'stop',autospec=True,side_effect=stopped) as stop, \
             patch.object(Controller,'launchctl'):
            self.assertTrue(self.controller.act('status')['running'])
            self.assertTrue(self.controller.act('prepare-update')['running'])
            self.assertTrue(other.plist.exists());stop.assert_not_called()
            result=self.controller.act('stop')
            self.assertFalse(result['running']);self.assertFalse(result['autostart'])
            self.assertEqual(stop.call_args.args[0].executable,other.executable)
        self.assertFalse(other.plist.exists())

    def test_mac_native_resolution_uses_packaged_architecture(self):
        from codex_auto_resume.paths import bundled_codex
        with patch('sys.platform','darwin'),patch('sys.frozen',True,create=True),patch('sys._MEIPASS',str(self.root),create=True):
            for arch,triple in [('arm64','aarch64-apple-darwin'),('x86_64','x86_64-apple-darwin')]:
                path=self.root/'auto-resume-native/vendor'/triple/'bin/codex'
                path.parent.mkdir(parents=True);path.write_text('synthetic')
                with patch('codex_auto_resume.paths.platform.machine',return_value=arch):self.assertEqual(bundled_codex(),path)

    def test_release_requires_real_resume_report_and_native_ui_bridge(self):
        import hashlib
        from stage_macos_release import validated_assets
        release='0.4.0-macos-preview.15'
        required=('nativeRuntimeWithoutExternalInstallation','singlePackagedWatcher','startupSwitchIndependent','stopBlocksStartupRelaunch','updateRestoresRunningAndStartup','realLaunchAgentStopsWithoutRelaunch','finderRemovalCleansBackgroundAndStartup','cleanupPreservesUserSettings')
        for arch in ('arm64','x86_64'):
            source=self.root/('macos-'+arch);source.mkdir()
            name=f'AI-First-Tools-{release}-macos-{arch}.dmg'
            (source/name).write_bytes(b'synthetic')
            (source/('SHA256SUMS-'+arch+'.txt')).write_text(hashlib.sha256(b'synthetic').hexdigest()+'  '+name+'\n')
            for kind in ('self','smoke','network','update','resume'):
                checks={'synthetic':True}
                if kind=='update': checks.update(dict.fromkeys(('nativeUpdateClick','bridgeDrained','nativeParentExit'),True))
                if kind=='smoke': checks['autoResumeControlBridge']=True
                if kind=='resume': checks=dict.fromkeys(required,True)
                (source/(kind+'-test.json')).write_text(json.dumps({'passed':True,'checks':checks,'architecture':arch,'version':{'release':release}}))
        self.assertEqual(len(validated_assets(self.root,release)),13)
        path=self.root/'macos-arm64/resume-test.json'
        value=json.loads(path.read_text());value['checks'].pop(required[0]);path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'lifecycle'): validated_assets(self.root,release)

if __name__=='__main__':unittest.main()
