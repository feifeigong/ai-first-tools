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
        output=f'10 {self.controller.executable} {WATCH}\n11 {self.controller.executable} --smoke-test\n12 /other/app {WATCH}\n13 {self.controller.executable} {WATCH} --manual\n'
        with patch('auto_resume.subprocess.run',return_value=Mock(stdout=output)):
            self.assertEqual(self.controller.watchers(),[10,13])

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
