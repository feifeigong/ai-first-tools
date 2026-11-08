import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from verify_windows_release import digest, validated_assets


class WindowsVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ai-first-windows-assets-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name in ("release", "windows"):
            (self.root / name).mkdir()
        self.report = {"passed": True, "version": "0.3.10", "checks": dict.fromkeys(
            ("silentInstall", "silentReinstall", "installedSelfChecks", "installedVersion", "extraFilePreserved", "safeUninstall"), True)}
        self.report_path = self.root / "windows/installer-test.json"
        self.report_path.write_text(json.dumps(self.report))
        (self.root / "windows/installed-self-test.json").write_text(json.dumps({"passed": 67, "failed": 0}))
        self.assets = [self.root / "release" / "AI-First-Tools-Setup-0.3.10.exe",
                       self.root / "release" / "AI-First-Tools-Portable-0.3.10-win-x64.zip"]
        for path in self.assets:
            path.write_bytes(b"Synthetic artifact, never executable")
        (self.root / "release/SHA256SUMS.txt").write_text("\n".join(f"{digest(path)}  {path.name}" for path in self.assets) + "\n")

    def test_original_reports_and_assets_pass_but_changed_file_is_rejected(self):
        self.assertEqual(len(validated_assets(self.root, "0.3.10")), 3)
        self.assets[0].write_bytes(b"different actual bytes")
        with self.assertRaisesRegex(ValueError, "checksum"):
            validated_assets(self.root, "0.3.10")

    def test_failed_install_or_mismatched_version_is_rejected_before_staging(self):
        self.report["checks"]["safeUninstall"] = False
        self.report_path.write_text(json.dumps(self.report))
        with self.assertRaisesRegex(ValueError, "did not pass"):
            validated_assets(self.root, "0.3.10")
        with self.assertRaisesRegex(ValueError, "did not pass"):
            validated_assets(self.root, "0.3.12")

    def test_bundled_release_requires_actual_runtime_and_lifecycle_reports(self):
        self.report['version']='0.3.12'
        self.report['checks'].update(dict.fromkeys(('bundledRuntime','bundledControls','backgroundUpgrade','backgroundUninstall'),True))
        self.report_path.write_text(json.dumps(self.report))
        self.assets=[path.rename(path.with_name(path.name.replace('0.3.10','0.3.12'))) for path in self.assets]
        (self.root / 'release/SHA256SUMS.txt').write_text('\n'.join(f'{digest(path)}  {path.name}' for path in self.assets)+'\n')
        with self.assertRaisesRegex(ValueError,'Bundled'):
            validated_assets(self.root,'0.3.12')

        (self.root / 'windows/resume-runtime-test.json').write_text(json.dumps({'passed':4,'failed':0}))
        background={'passed':True,'checks':dict.fromkeys(('start','stop','restart','upgrade','uninstall'),True)}
        path=self.root / 'windows/resume-control-test.json'
        path.write_text(json.dumps(background))
        self.assertEqual(len(validated_assets(self.root,'0.3.12')),3)
        background['checks']['uninstall']=False
        path.write_text(json.dumps(background))
        with self.assertRaisesRegex(ValueError,'Bundled'):
            validated_assets(self.root,'0.3.12')

    def test_new_release_requires_full_payload_reopen_and_frozen_draft_evidence(self):
        self._full_payload_evidence('0.3.16')

    def _full_payload_evidence(self, version):
        self.report['version'] = version
        self.report['checks'].update(dict.fromkeys(('bundledRuntime', 'bundledControls', 'backgroundUpgrade', 'backgroundUninstall'), True))
        self.report_path.write_text(json.dumps(self.report))
        self.assets = [path.rename(path.with_name(path.name.replace('0.3.10', version))) for path in self.assets]
        (self.root / 'release/SHA256SUMS.txt').write_text('\n'.join(f'{digest(path)}  {path.name}' for path in self.assets) + '\n')
        runtime = {'passed': 4, 'failed': 0}
        if tuple(map(int, version.split('.'))) >= (0, 4, 4):
            runtime['results'] = [{'name': 'Frozen main-session identity and final submission safety', 'passed': True}]
        (self.root / 'windows/resume-runtime-test.json').write_text(json.dumps(runtime))
        (self.root / 'windows/resume-control-test.json').write_text(json.dumps({'passed': True, 'checks': dict.fromkeys(('a','b','c','d','e'), True)}))
        with self.assertRaisesRegex(ValueError, 'Full update'):
            validated_assets(self.root, version)
        for filename, fields in (
                ('staged-install-test.json', ('stageOnly', 'incrementalApply', 'stableFilesUntouched', 'extraFilePreserved', 'allHashesVerified', 'uninstallerUpdated')),
                ('update-pipeline-test.json', ('realHelper', 'newToolAttached', 'extraFilePreserved'))):
            data = dict.fromkeys(('passed', *fields), True)
            data['fullPayloadBytes'] = 600_000_000
            (self.root / 'windows' / filename).write_text(json.dumps(data))
        guard = self.root / 'windows/copilot-refresh-test.json'
        guard.write_text(json.dumps({'passed': True, 'draftDetected': True, 'emptyAccepted': True}))
        self.assertEqual(len(validated_assets(self.root, version)), 3)
        data['newToolAttached'] = False
        (self.root / 'windows/update-pipeline-test.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Full update'):
            validated_assets(self.root, version)

    def test_current_copilot_frozen_checks_are_required_for_new_release(self):
        self._copilot_evidence('0.3.24')

    def test_selected_project_and_installed_taskbar_checks_are_required(self):
        self.report['checks']['taskbarIdentity'] = True
        self._copilot_evidence('0.3.25', project=True)
        value = json.loads(self.report_path.read_text())
        del value['checks']['taskbarIdentity']
        self.report_path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'installation'):
            validated_assets(self.root, '0.3.25')

    def test_current_release_requires_frozen_session_identity_before_remote_verification(self):
        self.report['checks']['taskbarIdentity'] = True
        self._copilot_evidence('0.4.4', project=True)
        memory = self.root / 'windows/memory-package-test.json'
        value = json.loads(memory.read_text())
        value['model_requests'] = 0
        memory.write_text(json.dumps(value))
        self.assertEqual(len(validated_assets(self.root, '0.4.4')), 3)
        runtime = self.root / 'windows/resume-runtime-test.json'
        original = json.loads(runtime.read_text())
        for results in ([], [{'name': 'Frozen main-session identity and final submission safety', 'passed': False}]):
            with self.subTest(results=results):
                runtime.write_text(json.dumps({**original, 'results': results}))
                with self.assertRaisesRegex(ValueError, 'main-session'):
                    validated_assets(self.root, '0.4.4')

    def test_current_release_cannot_stage_without_frozen_session_identity(self):
        import stage_windows_release as stage
        import sys

        stage_root = self.root / 'stage-source'
        (stage_root / 'workspace').mkdir(parents=True)
        reports = stage_root / 'artifacts/windows'
        reports.mkdir(parents=True)
        (stage_root / 'workspace/AIFirst.Workspace.csproj').write_text(
            '<Project><PropertyGroup><Version>0.4.4</Version></PropertyGroup></Project>')
        (reports / 'installer-test.json').write_text(json.dumps({
            'passed': True, 'version': '0.4.4', 'checks': {'taskbarIdentity': True}}))
        (reports / 'installed-self-test.json').write_text(json.dumps({'failed': 0, 'passed': 67}))
        ui = reports / 'release-highlights-ui'
        ui.mkdir()
        ui_checks = {mode + name: True for mode in ('done', 'close', 'escape')
                     for name in ('Layout', 'Focus', 'Acknowledged')}
        (ui / 'report.json').write_text(json.dumps({'passed': True, 'checks': ui_checks}))
        prior = [{'name': name, 'passed': True} for name in (
            'Frozen credit policy never spends before full weekly exhaustion',
            'Frozen independent automation preserves timer deduplication and spending permissions',
            'Native Codex supports the isolated ephemeral request flags without model requests')]
        for extra in ([], [{'name': 'Frozen main-session identity and final submission safety', 'passed': False}]):
            with self.subTest(extra=extra):
                (reports / 'resume-runtime-test.json').write_text(json.dumps({'failed': 0, 'results': prior + extra}))
                with patch.object(stage, '__file__', str(stage_root / 'scripts/stage_windows_release.py')), \
                        patch.object(sys, 'argv', ['stage', '--commit', 'a' * 40]), \
                        patch.object(stage.subprocess, 'run', side_effect=AssertionError('No GitHub access allowed')) as remote:
                    with self.assertRaisesRegex(ValueError, 'main-session'):
                        stage.main()
                    remote.assert_not_called()

    def _copilot_evidence(self, version, project=False):
        path = self.root / 'windows/memory-package-test.json'
        names = ('current_full_chat_registration_without_worktree','unknown_full_chat_trigger_still_denied')
        if project:
            names += ('full_history_uses_selected_folder_project','full_history_reuses_project_without_worktree')
        value = {'passed': True, 'synthetic_only': True, 'model_requests': 0,
                 'checks': [{'name': name, 'passed': True} for name in names]}
        path.write_text(json.dumps(value))
        self._full_payload_evidence(version)
        for filename, fields in (('update-pipeline-test.json', ('newToolAttached',)),):
            audit_path = self.root / 'windows' / filename
            data = json.loads(audit_path.read_text())
            data.update(dict.fromkeys(fields, True))
            audit_path.write_text(json.dumps(data))
        for name in names:
            changed = {**value, 'checks': [item for item in value['checks'] if item['name'] != name]}
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'Copilot'):
                validated_assets(self.root, version)
        path.write_text(json.dumps({**value, 'model_requests': 1}))
        with self.assertRaisesRegex(ValueError, 'Copilot'):
            validated_assets(self.root, version)



if __name__ == "__main__":
    unittest.main()
