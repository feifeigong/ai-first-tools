from __future__ import annotations

import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "macos"))
import updater
import updates


class MacUpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ai-first-updater-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        patcher = patch.object(updater, "state_root", return_value=self.state)
        patcher.start()
        self.addCleanup(patcher.stop)
        swapper = patch.object(updater, "atomic_swap", side_effect=self.swap)
        swapper.start()
        self.addCleanup(swapper.stop)

    def swap(self, first, second):
        self.assertTrue(first.resolve().is_relative_to(self.root.resolve()))
        self.assertTrue(second.resolve().is_relative_to(self.root.resolve()))
        temporary = self.root / "synthetic-swap.app"
        os.rename(first, temporary)
        os.rename(second, first)
        os.rename(temporary, second)

    def bundle(self, path, version):
        (path / "Contents/Resources").mkdir(parents=True)
        (path / "Contents/MacOS").mkdir()
        (path / "Contents/Resources/version.json").write_text(json.dumps({"release": version}))
        (path / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "cn.aifirst.tools", "CFBundleExecutable": updater.EXECUTABLE}))
        (path / "Contents/MacOS" / updater.EXECUTABLE).write_bytes(version.encode())
        return path

    def job(self):
        original = "0.4.0-macos-preview.2"
        version = "0.4.0-macos-preview.3"
        target = self.bundle(self.root / updater.APP_NAME, original)
        directory = Path(tempfile.mkdtemp(prefix=".ai-first-update-", dir=self.root))
        directory.chmod(0o700)
        candidate = self.bundle(directory / "candidate.app", version)
        job = directory / "job.json"
        snapshot = target.stat()
        updater.write_json(job, {"target": str(target), "current": original, "version": version, "architecture": "arm64",
                                "device": snapshot.st_dev, "inode": snapshot.st_ino, "originalDigest": updater.fingerprint(target),
                                "candidateDigest": updater.fingerprint(candidate), "nonce": "a" * 32, "parentPid": 999999})
        return target, candidate, job

    def probe(self, arguments, **options):
        Path(arguments[-1]).write_text(json.dumps({"passed": True}))
        return Mock(returncode=0)

    def test_matching_release_requires_both_integrity_checked_assets(self):
        version = "0.4.0-macos-preview.3"
        name = f"AI-First-Tools-{version}-macos-arm64.dmg"
        assets = [{"name": filename, "state": "uploaded", "size": 100, "digest": "sha256:" + "a" * 64,
                   "browser_download_url": f"{updates.REPOSITORY}/releases/download/v{version}/{filename}"}
                  for filename in (name, "SHA256SUMS.txt")]
        with patch.object(updater.platform, "machine", return_value="arm64"):
            self.assertIsNotNone(updater.package_from_release({"version": version, "assets": assets}))
            self.assertIsNone(updater.package_from_release({"version": version, "assets": assets[:1]}))
            for field, value in (("digest", "sha256:invalid"), ("size", updater.MAX_PACKAGE + 1), ("browser_download_url", "https://example.com/file.dmg")):
                malformed = [dict(asset) for asset in assets]
                malformed[0][field] = value
                self.assertIsNone(updater.package_from_release({"version": version, "assets": malformed}))

    def test_redirects_only_use_https_and_owned_release_or_github_asset_hosts(self):
        for url in ("http://github.com/feifeigong/ai-first-tools/releases/download/a", "https://github.com/other/repo/a",
                    "https://github.com.evil.test/a", "https://user:secret@github.com/feifeigong/ai-first-tools/releases/download/a", "https://127.0.0.1/a",
                    "https://github.com:invalid/feifeigong/ai-first-tools/releases/download/a", "https://[invalid/a"):
            self.assertFalse(updater.safe_download_url(url))
        self.assertTrue(updater.safe_download_url("https://release-assets.githubusercontent.com/a?token=synthetic"))

    def test_incomplete_download_is_removed_without_touching_existing_program(self):
        payload = b"complete"
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        url = f"{updates.REPOSITORY}/releases/download/v0.4.1/test.dmg"
        response.geturl.return_value = url
        response.read.side_effect = [b"short", b""]
        opener = Mock()
        opener.open.return_value = response
        path = self.root / "partial.dmg"
        with patch.object(updater, "build_opener", return_value=opener), patch.object(updates, "tls_context", return_value=Mock()):
            with self.assertRaises(updater.UpdateError):
                updater.download({"url": url, "size": len(payload), "digest": hashlib.sha256(payload).hexdigest()}, path, lambda value: None, threading.Event())
        self.assertFalse(path.exists())

    def test_bundle_identity_and_architecture_are_checked_before_execution(self):
        path = self.bundle(self.root / updater.APP_NAME, "0.4.1")
        with patch.object(updater, "command", return_value=Mock(stdout=b"arm64")):
            updater.validate_app(path, "0.4.1", "arm64")
            with self.assertRaises(updater.UpdateError):
                updater.validate_app(path, "0.4.2", "arm64")
            with self.assertRaises(updater.UpdateError):
                updater.validate_app(path, "0.4.1", "x86_64")

    def test_cancelling_during_validation_stops_before_copy_or_job_creation(self):
        target = self.bundle(self.root / updater.APP_NAME, "0.4.0-macos-preview.8")
        before = updater.fingerprint(target)
        cancelled = threading.Event()
        copied = []
        cleanup = threading.Event()
        package = {"version": "0.4.0-macos-preview.9", "architecture": "arm64",
                   "dmg": {"name": "synthetic.dmg", "digest": "a" * 64}, "sums": {}}

        def download(asset, destination, progress, event):
            destination.write_text("a" * 64 + "  synthetic.dmg\n" if destination.name == "SHA256SUMS.txt" else "synthetic dmg")

        def command(arguments, **options):
            if arguments[0].endswith("hdiutil") and "attach" in arguments:
                mount = Path(arguments[arguments.index("-mountpoint") + 1])
                self.bundle(mount / updater.APP_NAME, package["version"])
            elif arguments[0].endswith("codesign"):
                cancelled.set()
            elif arguments[0].endswith("ditto"):
                copied.append(arguments)
                shutil.copytree(arguments[1], arguments[2])
            return Mock(stdout=b"arm64")

        def cleanup_directory(directory, **options):
            self.assertTrue(Path(directory).resolve().is_relative_to(self.root.resolve()))
            self.assertTrue(Path(directory).name.startswith(".ai-first-update-"))
            cleanup.set()

        with patch.object(updater, "download", side_effect=download), patch.object(updater, "command", side_effect=command), \
                patch.object(updater.shutil, "rmtree", side_effect=cleanup_directory):
            with self.assertRaises(updater.Cancelled):
                updater.prepare(target, package, "0.4.0-macos-preview.8", Mock(), cancelled)
            self.assertTrue(cleanup.wait(2))
        self.assertEqual(copied, [])
        self.assertEqual(updater.fingerprint(target), before)
        self.assertFalse(list(self.root.rglob("job.json")))

    def test_cancel_interrupts_a_running_preparation_command_and_reaps_it(self):
        cancelled = threading.Event()
        control = updater.Preparation(cancelled, Mock(), timeout=5)
        processes = []
        popen = subprocess.Popen

        def start(*args, **kwargs):
            process = popen(*args, **kwargs)
            processes.append(process)
            return process

        timer = threading.Timer(0.4, cancelled.set)
        started = time.monotonic()
        timer.start()
        try:
            with patch.object(updater.subprocess, "Popen", side_effect=start), self.assertRaises(updater.Cancelled):
                updater.command([sys.executable, "-c", "import time; time.sleep(20)"], control=control)
        finally:
            timer.cancel()
            timer.join()
        self.assertLess(time.monotonic() - started, 4)
        self.assertTrue(processes)
        self.assertTrue(all(process.poll() is not None for process in processes))

    def test_preparation_budget_is_shared_across_commands(self):
        control = updater.Preparation(threading.Event(), Mock(), timeout=1.2)
        started = time.monotonic()
        updater.command([sys.executable, "-c", "import time; time.sleep(0.1)"], control=control)
        with self.assertRaisesRegex(updater.UpdateError, "等待太久"):
            updater.command([sys.executable, "-c", "import time; time.sleep(20)"], control=control)
        self.assertLess(time.monotonic() - started, 4)

    def test_controlled_fingerprint_matches_existing_integrity_checks(self):
        bundle = self.bundle(self.root / updater.APP_NAME, "0.4.1")
        (bundle / "Contents/Resources/data.bin").write_bytes(b"synthetic integrity data" * 100000)
        control = updater.Preparation(threading.Event(), Mock())
        self.assertEqual(updater.fingerprint(bundle, control), updater.fingerprint(bundle))
        control.cancelled.set()
        with self.assertRaises(updater.Cancelled):
            updater.fingerprint(bundle, control)

    def test_failed_attach_never_recursively_cleans_a_still_mounted_image(self):
        target = self.bundle(self.root / updater.APP_NAME, "0.4.0-macos-preview.8")
        before = updater.fingerprint(target)
        package = {"version": "0.4.0-macos-preview.9", "architecture": "arm64",
                   "dmg": {"name": "synthetic.dmg", "digest": "a" * 64}, "sums": {}}

        def download(asset, destination, progress, event):
            destination.write_text("a" * 64 + "  synthetic.dmg\n" if destination.name == "SHA256SUMS.txt" else "synthetic dmg")

        def failed_command(arguments, **options):
            raise subprocess.TimeoutExpired(arguments, 0.01)

        with patch.object(updater, "download", side_effect=download), patch.object(updater, "command", side_effect=failed_command), \
                patch.object(updater.os.path, "ismount", return_value=True), patch.object(updater.shutil, "rmtree") as cleanup:
            with self.assertRaises(subprocess.TimeoutExpired):
                updater.prepare(target, package, "0.4.0-macos-preview.8", Mock(), threading.Event())
            cleanup.assert_not_called()
        self.assertEqual(updater.fingerprint(target), before)

    def test_preparation_cancel_request_is_visible_until_worker_finishes(self):
        from entry import MacApi

        api = MacApi()
        api._update_state = {"phase": "preparing", "step": "copying", "progress": 40}
        self.assertEqual(api.cancel_update(), {"ok": True})
        self.assertTrue(api.update_status()["cancelRequested"])
        self.assertEqual(api.update_status()["phase"], "preparing")

    def test_cancelled_ready_update_does_not_wait_for_slow_staging_cleanup(self):
        from entry import MacApi

        target, candidate, job = self.job()
        api = MacApi()
        api._prepared = job
        api._update_state = {"phase": "ready"}
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()

        def cleanup(directory):
            self.assertEqual(Path(directory), job.parent)
            entered.set()
            release.wait(2)
            finished.set()

        with patch.object(updater.shutil, "rmtree", side_effect=cleanup):
            try:
                started = time.monotonic()
                self.assertEqual(api.cancel_update(), {"ok": True})
                self.assertLess(time.monotonic() - started, 0.5)
                self.assertTrue(entered.wait(1))
                self.assertEqual(api.update_status()["phase"], "error")
                self.assertTrue(target.is_dir())
            finally:
                release.set()
                self.assertTrue(finished.wait(2))

    def test_replacement_preserves_backup_and_non_program_data(self):
        target, candidate, job = self.job()
        settings = self.root / "my-dialogue-and-settings.txt"
        settings.write_text("synthetic user data")
        with patch.object(updater, "validate_app"), patch.object(updater.subprocess, "run", side_effect=self.probe):
            self.assertTrue(updater.replace_bundle(job, lambda app: None))
        self.assertTrue((job.parent / "backup.app").is_dir())
        self.assertEqual(json.loads((target / "Contents/Resources/version.json").read_text())["release"], "0.4.0-macos-preview.3")
        self.assertEqual(settings.read_text(), "synthetic user data")

    def test_changed_candidate_never_replaces_original(self):
        target, candidate, job = self.job()
        before = updater.fingerprint(target)
        (candidate / "Contents/MacOS" / updater.EXECUTABLE).write_bytes(b"changed after verification")
        with patch.object(updater, "validate_app"), patch.object(updater.subprocess, "run") as process:
            self.assertFalse(updater.replace_bundle(job, lambda app: None))
        process.assert_not_called()
        self.assertEqual(updater.fingerprint(target), before)
        self.assertFalse((job.parent / "backup.app").exists())

    def test_failed_atomic_install_restores_original(self):
        target, candidate, job = self.job()
        before = updater.fingerprint(target)
        rename = Path.rename
        def fail_candidate(path, destination):
            if path == candidate:
                raise PermissionError("synthetic permission failure")
            return rename(path, destination)
        with patch.object(updater, "validate_app"), patch.object(updater.subprocess, "run", side_effect=self.probe), patch.object(Path, "rename", fail_candidate):
            self.assertFalse(updater.replace_bundle(job, lambda app: None))
        self.assertEqual(updater.fingerprint(target), before)
        self.assertFalse(json.loads((self.state / "result.json").read_text())["success"])

    def test_failed_relaunch_restores_original(self):
        target, candidate, job = self.job()
        before = updater.fingerprint(target)
        def relaunch(app):
            if json.loads((app / "Contents/Resources/version.json").read_text())["release"].endswith(".3"):
                raise OSError("synthetic launch failure")
        with patch.object(updater, "validate_app"), patch.object(updater.subprocess, "run", side_effect=self.probe):
            self.assertFalse(updater.replace_bundle(job, relaunch))
        self.assertEqual(updater.fingerprint(target), before)
        self.assertTrue((job.parent / "failed.app").is_dir())

    def test_job_cannot_point_outside_its_private_app_parent(self):
        target, candidate, job = self.job()
        data = json.loads(job.read_text())
        data["target"] = str(self.root.parent / "outside.app")
        updater.write_json(job, data)
        with self.assertRaises(updater.UpdateError):
            updater.read_job(job)

    def test_helper_must_be_ready_before_original_window_closes(self):
        target, candidate, job = self.job()
        with patch.object(updater.subprocess, "Popen", return_value=Mock(poll=Mock(return_value=1))):
            with self.assertRaises(updater.UpdateError):
                updater.start_helper(job)
        self.assertTrue(target.is_dir())

    def test_relaunch_is_independent_and_does_not_reuse_old_frozen_libraries(self):
        with patch.dict(os.environ, {"DYLD_LIBRARY_PATH": "synthetic-old-libraries"}), patch.object(updater.subprocess, "Popen") as process:
            updater.start_app(self.root / updater.APP_NAME)
        arguments, options = process.call_args
        self.assertEqual(arguments[0], [str(self.root / updater.APP_NAME / "Contents/MacOS" / updater.EXECUTABLE)])
        self.assertEqual(options["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")
        self.assertNotIn("DYLD_LIBRARY_PATH", options["env"])
        self.assertTrue(options["start_new_session"])

    def test_relaunch_rejects_immediate_exit(self):
        with patch.object(updater, "start_app", return_value=Mock(poll=Mock(return_value=0))), patch.object(updater.time, "sleep"):
            with self.assertRaises(updater.UpdateError):
                updater.relaunch_app(self.root / updater.APP_NAME)

    def test_busy_migration_waits_and_restarting_blocks_new_migration(self):
        from entry import MacApi

        api = MacApi()
        api._prepared = self.root / "synthetic-job.json"
        api._window = Mock()
        api._job = Mock(snapshot=Mock(return_value={"finished": False}))
        with patch.object(updater, "start_helper") as process:
            self.assertEqual(api.apply_update(), {"waiting": True})
            process.assert_not_called()
            api._job.snapshot.return_value = {"finished": True}
            self.assertTrue(api.apply_update()["ok"])
            api._window.destroy.assert_called_once()
            self.assertIn("error", api.start_move("example", [], "example", "example"))


if __name__ == "__main__":
    unittest.main()
