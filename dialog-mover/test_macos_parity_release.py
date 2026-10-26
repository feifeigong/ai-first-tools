from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from stage_macos_release import validated_assets, CODEX_IMPORT_CHECKS

MEMORY={'database_scope_guard','original_archive','bundled_stdio_mcp_handshake','discarded_legacy_entry_no_longer_blocks_move','source_badge_uses_current_entry','current_schema_rollback_preserves_legacy_orphan'}
RESET={'frozenSharedRuleBridgeAndSwitch','independentAfterLauncherExit','singleOwnedNotifier','nativeWindowClosePreservesNotifier','nativeChinesePopupHasNoAutomaticResumeAction','anotherPackageCannotStopNotifier','cooperativeUpdateRestoresNotifier','stopPreservesPreferences'}
RESUME={'nativeRuntimeWithoutExternalInstallation','singlePackagedWatcher','startupSwitchIndependent','stopBlocksStartupRelaunch','updateRestoresRunningAndStartup','realLaunchAgentStopsWithoutRelaunch','finderRemovalCleansBackgroundAndStartup','cleanupPreservesUserSettings'}


class MacParityReleaseTests(unittest.TestCase):
    def setUp(self):
        self.scratch=self.enterContext(tempfile.TemporaryDirectory())
        self.root=Path(self.scratch)
        self.release='0.4.0-macos-preview.19'  # Synthetic version; never changes a tag or release.
        for arch in ('arm64','x86_64'):
            source=self.root/('macos-'+arch);source.mkdir()
            name=f'AI-First-Tools-{self.release}-macos-{arch}.dmg'
            (source/name).write_bytes(b'synthetic')
            (source/f'SHA256SUMS-{arch}.txt').write_text(hashlib.sha256(b'synthetic').hexdigest()+'  '+name+'\n')
            for kind in ('self','smoke','network','update','resume','memory','reset','reset-rules','codex-import'):
                required={'synthetic'}
                if kind=='smoke':required={'autoResumeControlBridge','resetCalendarBridge','independentReminderSwitch'}
                if kind=='update':required={'nativeUpdateClick','bridgeDrained','nativeParentExit'}
                if kind=='resume':required=RESUME
                if kind=='memory':required=MEMORY
                if kind=='reset':required=RESET
                if kind=='reset-rules':required={f'synthetic_rule_{n}' for n in range(33)}
                if kind=='codex-import':required=CODEX_IMPORT_CHECKS
                value={'passed':True,'checks':dict.fromkeys(required,True),'architecture':arch,'version':{'release':self.release}}
                if kind=='reset-rules':value['sharedWindowsSources']=dict.fromkeys(('ResetNewsService.cs','ResetNewsDiscovery.cs','ResetNewsPresentation.cs','ResetCalendarModel.cs'),'a'*64)
                if kind=='codex-import':value.update(modelRequests=0,nativeContinuationVerified=False,host='Darwin',frozen=True)
                (source/f'{kind}-test.json').write_text(json.dumps(value))

    def test_both_native_architectures_require_the_complete_feature_reports(self):
        self.assertEqual(len(validated_assets(self.root,self.release)),21)

    def test_missing_compressed_history_check_or_non_mac_report_cannot_be_staged(self):
        for architecture in ('arm64','x86_64'):
            path=self.root/f'macos-{architecture}/codex-import-test.json'
            original=path.read_bytes()
            for field,value in (('host','Windows'),('frozen',False),('modelRequests',1),('nativeContinuationVerified',True)):
                data=json.loads(original);data[field]=value;path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):validated_assets(self.root,self.release)
            for key in CODEX_IMPORT_CHECKS:
                data=json.loads(original);data['checks'].pop(key);path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):validated_assets(self.root,self.release)
            path.write_bytes(original)

    def test_memory_reset_rules_and_popup_failures_cannot_be_staged(self):
        for kind,key in (('memory','bundled_stdio_mcp_handshake'),('reset','nativeWindowClosePreservesNotifier'),('smoke','independentReminderSwitch')):
            path=self.root/'macos-arm64'/f'{kind}-test.json'
            original=path.read_bytes();value=json.loads(original);value['checks'].pop(key)
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):validated_assets(self.root,self.release)
            path.write_bytes(original)
        path=self.root/'macos-arm64/reset-rules-test.json'
        value=json.loads(path.read_text());value['sharedWindowsSources'].pop('ResetNewsPresentation.cs')
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):validated_assets(self.root,self.release)


if __name__=='__main__':unittest.main()
