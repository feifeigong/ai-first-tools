import json
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
