from __future__ import annotations
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from stage_macos_release import validated_assets, CODEX_IMPORT_CHECKS, REFRESH_CHECKS

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
            for kind in ('self','smoke','network','update','resume','memory','reset','reset-rules','codex-import','copilot-refresh'):
                required={'synthetic'}
                if kind=='smoke':required={'autoResumeControlBridge','resetCalendarBridge','independentReminderSwitch'}
                if kind=='update':required={'nativeUpdateClick','bridgeDrained','nativeParentExit'}
                if kind=='resume':required=RESUME
                if kind=='memory':required=MEMORY
                if kind=='reset':required=RESET
                if kind=='reset-rules':required={f'synthetic_rule_{n}' for n in range(33)}
                if kind=='codex-import':required=CODEX_IMPORT_CHECKS
                if kind=='copilot-refresh':required=REFRESH_CHECKS
                value={'passed':True,'checks':dict.fromkeys(required,True),'architecture':arch,'version':{'release':self.release}}
                if kind=='reset-rules':value['sharedWindowsSources']=dict.fromkeys(('ResetNewsService.cs','ResetNewsDiscovery.cs','ResetNewsPresentation.cs','ResetCalendarModel.cs'),'a'*64)
                if kind=='codex-import':value.update(modelRequests=0,nativeContinuationVerified=False,host='Darwin',frozen=True)
                if kind=='copilot-refresh':value.update(modelRequests=0,host='Darwin',frozen=True,officialLoggedInSidebarVerified=False)
                (source/f'{kind}-test.json').write_text(json.dumps(value))

    def test_both_native_architectures_require_the_complete_feature_reports(self):
        self.assertEqual(len(validated_assets(self.root,self.release)),23)

    def test_credit_boundary_is_required_in_both_new_packaged_architectures(self):
        previous=self.release
        self.release='0.4.0-macos-preview.24'
        for arch in ('arm64','x86_64'):
            directory=self.root/('macos-'+arch)
            name=f'AI-First-Tools-{self.release}-macos-{arch}.dmg'
            (directory/f'AI-First-Tools-{previous}-macos-{arch}.dmg').rename(directory/name)
            (directory/f'SHA256SUMS-{arch}.txt').write_text(hashlib.sha256(b'synthetic').hexdigest()+'  '+name+'\n')
            for path in directory.glob('*-test.json'):
                value=json.loads(path.read_text());value['version']['release']=self.release
                if path.name=='self-test.json':
                    value['finderScope']='product'
                    value['checks'].update(dict.fromkeys(('localizedProductName','finderDisplayName','nativeProcessName','bundledReleaseHighlights','weeklyCreditRequiresExhaustion'),True))
                if path.name=='smoke-test.json':
                    value['checks'].update(dict.fromkeys(('nativeReleaseHighlightsDialog','releaseHighlightsAcknowledgement'),True))
                path.write_text(json.dumps(value))
        self.assertEqual(len(validated_assets(self.root,self.release)),23)
        for arch in ('arm64','x86_64'):
            path=self.root/('macos-'+arch)/'self-test.json';original=path.read_bytes()
            value=json.loads(original);value['checks'].pop('weeklyCreditRequiresExhaustion');path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'credit'):validated_assets(self.root,self.release)
            path.write_bytes(original)

    def test_new_automation_requires_both_architectures_and_native_controls(self):
        previous=self.release;self.release='0.4.0-macos-preview.27'
        required=('weeklyCreditRequiresExhaustion','independentAutomationPolicy','ephemeralTimerWriteAhead','ephemeralRequestSafety','nativeEphemeralSupport')
        for arch in ('arm64','x86_64'):
            directory=self.root/('macos-'+arch);name=f'AI-First-Tools-{self.release}-macos-{arch}.dmg'
            (directory/f'AI-First-Tools-{previous}-macos-{arch}.dmg').rename(directory/name)
            (directory/f'SHA256SUMS-{arch}.txt').write_text(hashlib.sha256(b'synthetic').hexdigest()+'  '+name+'\n')
            for path in directory.glob('*-test.json'):
                value=json.loads(path.read_text());value['version']['release']=self.release
                if path.name=='self-test.json':
                    value['checks'].update(dict.fromkeys((*required,'localizedProductName','finderDisplayName','nativeProcessName','bundledReleaseHighlights'),True));value['finderScope']='product'
                if path.name=='smoke-test.json': value['checks'].update(dict.fromkeys(('independentAutomationBridge','nativeReleaseHighlightsDialog','releaseHighlightsAcknowledgement'),True))
                if path.name=='resume-test.json': value['checks']['finderLocaleWatcherIdentity']=True
                if path.name=='reset-test.json': value['checks'].update(dict.fromkeys(('finderLocaleNotifierIdentity','bundledHistoryImmediatelyAvailable'),True))
                if path.name=='update-test.json':value['checks'].update(dict.fromkeys(('preflightBeforeParentExit','incomingUpdaterHelper','published25FailureReproduced','published25BackgroundRecovered','normalUpdatedWindowStaysReady'),True))
                path.write_text(json.dumps(value))
        self.assertEqual(len(validated_assets(self.root,self.release)),23)
        for arch in ('arm64','x86_64'):
            for kind, names in (('self',required),('smoke',('independentAutomationBridge',)),('resume',('finderLocaleWatcherIdentity',)),('reset',('finderLocaleNotifierIdentity','bundledHistoryImmediatelyAvailable')),('update',('preflightBeforeParentExit','incomingUpdaterHelper','published25FailureReproduced','published25BackgroundRecovered','normalUpdatedWindowStaysReady'))):
                path=self.root/('macos-'+arch)/(kind+'-test.json');original=path.read_bytes()
                for key in names:
                    value=json.loads(original);value['checks'].pop(key);path.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):validated_assets(self.root,self.release)
                    path.write_bytes(original)

    def test_new_releases_require_bundled_highlights_and_native_acknowledgement(self):
        previous=self.release;self.release='0.4.0-macos-preview.22'
        for arch in ('arm64','x86_64'):
            directory=self.root/('macos-'+arch);name=f'AI-First-Tools-{self.release}-macos-{arch}.dmg'
            (directory/f'AI-First-Tools-{previous}-macos-{arch}.dmg').rename(directory/name)
            (directory/f'SHA256SUMS-{arch}.txt').write_text(hashlib.sha256(b'synthetic').hexdigest()+'  '+name+'\n')
            for path in directory.glob('*-test.json'):
                value=json.loads(path.read_text());value['version']['release']=self.release
                if path.name=='self-test.json':
                    value['checks'].update(dict.fromkeys(('localizedProductName','finderDisplayName','nativeProcessName','bundledReleaseHighlights'),True));value['finderScope']='product'
                if path.name=='smoke-test.json':value['checks'].update(dict.fromkeys(('nativeReleaseHighlightsDialog','releaseHighlightsAcknowledgement'),True))
                path.write_text(json.dumps(value))
        self.assertEqual(len(validated_assets(self.root,self.release)),23)
        for kind,key in (('self','bundledReleaseHighlights'),('smoke','nativeReleaseHighlightsDialog'),('smoke','releaseHighlightsAcknowledgement')):
            path=self.root/'macos-arm64'/f'{kind}-test.json';original=path.read_text();value=json.loads(original);value['checks'].pop(key);path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError,'release highlights'):validated_assets(self.root,self.release)
            path.write_text(original)

    def test_staging_finder_fallback_cannot_replace_real_product_name_verification(self):
        previous=self.release
        self.release='0.4.0-macos-preview.21'
        for architecture in ('arm64','x86_64'):
            directory=self.root/('macos-'+architecture)
            name=f'AI-First-Tools-{self.release}-macos-{architecture}.dmg'
            (directory/f'AI-First-Tools-{previous}-macos-{architecture}.dmg').rename(directory/name)
            (directory/f'SHA256SUMS-{architecture}.txt').write_text(hashlib.sha256(b'synthetic').hexdigest()+'  '+name+'\n')
            for path in directory.glob('*-test.json'):
                value=json.loads(path.read_text());value['version']['release']=self.release
                if path.name=='self-test.json':
                    value['checks'].update(dict.fromkeys(('localizedProductName','finderDisplayName','nativeProcessName'),True))
                    value['finderScope']='product'
                path.write_text(json.dumps(value))
        self.assertEqual(len(validated_assets(self.root,self.release)),23)
        path=self.root/'macos-arm64/self-test.json';value=json.loads(path.read_text())
        value['finderScope']='update-staging';path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'renamed product'):validated_assets(self.root,self.release)

    def test_independent_previews_need_their_own_names_and_isolation_report(self):
        for architecture in ('arm64','x86_64'):
            directory = self.root/('macos-'+architecture)
            ordinary = f'AI-First-Tools-{self.release}-macos-{architecture}.dmg'
            preview = f'AI-First-Tools-{self.release}-local-parity-macos-{architecture}.dmg'
            (directory/ordinary).rename(directory/preview)
            (directory/f'SHA256SUMS-{architecture}.txt').write_text(hashlib.sha256(b'synthetic').hexdigest()+'  '+preview+'\n')
            path = directory/'self-test.json'; result = json.loads(path.read_text())
            result['version']['developmentPreview'] = True
            result['checks']['developmentPreviewIsolation'] = True
            path.write_text(json.dumps(result))
        self.assertEqual(len(validated_assets(self.root,self.release,local_preview=True)),23)
        path = self.root/'macos-arm64/self-test.json'; result = json.loads(path.read_text())
        result['checks'].pop('developmentPreviewIsolation'); path.write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError,'identities'): validated_assets(self.root,self.release,local_preview=True)

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
        for kind,key in (('memory','bundled_stdio_mcp_handshake'),('reset','nativeWindowClosePreservesNotifier'),('smoke','independentReminderSwitch'),('copilot-refresh','nativeDraftPreserved')):
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
