from __future__ import annotations

import json
import os
import socket
import ssl
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from core import chatgpt, common, mover, sources

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "macos"))
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_macos import prepare
from updates import REPOSITORY, choose_release, release_key
import updates


class MacPathsTests(unittest.TestCase):
    def test_smoke_profile_is_empty_without_initializing_destination_stores(self):
        from entry import isolate_profile
        from main import AGENTS
        import updater

        with tempfile.TemporaryDirectory() as temporary, patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {}, clear=True), patch.object(common, "_isolated_home", None), patch.object(updater, "_audit_state", None):
            isolate_profile(Path(temporary))
            self.assertTrue(common.home().is_dir())
            self.assertFalse(Path(os.environ["COWORK_SESSIONS_DIR"]).exists())
            self.assertFalse(any(sources.installed(agent["id"]) for agent in AGENTS))

    def test_smoke_isolates_records_and_receipts_without_changing_native_home(self):
        from entry import isolate_profile
        import updater

        with tempfile.TemporaryDirectory() as temporary, patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {"HOME": "/Users/native-test"}, clear=True), patch.object(common, "_isolated_home", None), patch.object(updater, "_audit_state", None):
            scratch = Path(temporary)
            isolate_profile(scratch)
            self.assertEqual(os.environ["HOME"], "/Users/native-test")
            self.assertEqual(common.home(), scratch / "home")
            self.assertEqual(common.appdata(), scratch / "appdata")
            self.assertEqual(updater.state_root(), scratch / "updates")
            self.assertIsNone(common.codex_home())

    def test_application_support_not_windows_appdata(self):
        with patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {"HOME": "/Users/test", "USERPROFILE": "C:/wrong"}, clear=True):
            self.assertEqual(common.home(), Path("/Users/test"))
            self.assertEqual(common.appdata(), Path("/Users/test/Library/Application Support"))
            self.assertEqual(common.localappdata(), common.appdata())
            self.assertEqual(sources._cursor_db(), common.appdata() / "Cursor/User/globalStorage/state.vscdb")
            self.assertEqual(sources._claude_root(), common.appdata() / "Claude")
            self.assertEqual(sources._qwen_db(), common.appdata() / "QwenWorkCN/data/agents.db")

    def test_posix_file_uri_preserves_slashes_and_chinese_spaces(self):
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(common.uri_to_path("file:///Users/test/%E9%A1%B9%E7%9B%AE%20A"), "/Users/test/项目 A")
            self.assertEqual(chatgpt._norm("/Users/Test/Folder/../Project/"), "/Users/Test/Project")
            self.assertNotEqual(chatgpt._norm("/Users/test/A"), chatgpt._norm("/Users/test/a"))
            self.assertEqual(chatgpt._norm("/"), "/")

    def test_windows_project_paths_remain_compatible(self):
        with patch.object(sys, "platform", "darwin"):
            self.assertEqual(chatgpt._norm("C:/Project/Foo/"), "c:\\project\\foo")

    def test_native_engine_name_and_registration_environment(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(sys, "platform", "darwin"), patch.dict(os.environ, {}, clear=True):
            root = Path(temporary)
            (root / "bin").mkdir()
            engine = root / "bin/txcript"
            engine.touch()
            with patch.object(mover, "app_dir", return_value=root), patch.object(common, "home", return_value=root), patch.object(mover, "codex_home", return_value=None):
                self.assertEqual(mover.txcript_path(), engine)
                self.assertEqual(mover._env()["APPDATA"], str(root / "Library/Application Support"))

    def test_open_folder_uses_argument_list_not_shell(self):
        with patch.object(sys, "platform", "darwin"), patch.object(common.subprocess, "run") as process:
            common.open_external("/Users/test/Folder $x; name")
            process.assert_called_once_with(["/usr/bin/open", "--", "/Users/test/Folder $x; name"], check=True, timeout=15)

    def test_readonly_database_with_uri_characters(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "项目 #问?.db"
            if sys.platform == "win32":
                path = Path(temporary) / "项目 #问.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE example(value)")
            connection.close()
            with closing(common.read_db(path)) as reader:
                with self.assertRaises(sqlite3.OperationalError):
                    reader.execute("INSERT INTO example VALUES (1)")

    def test_local_codex_history_visible_without_cloud_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sessions").mkdir()
            (root / "state_5.sqlite").touch()
            with patch.object(sources, "codex_home", return_value=root):
                self.assertTrue(sources.installed("chatgpt"))


class MacUpdatesTests(unittest.TestCase):
    def release(self, version="0.4.1", architecture="arm64"):
        tag = f"v{version}"
        name = f"AI-First-Tools-{version}-macos-{architecture}.dmg"
        return {"tag_name": tag, "draft": False, "html_url": f"{REPOSITORY}/releases/tag/{tag}", "assets": [
            {"name": name, "size": 100, "state": "uploaded", "browser_download_url": f"{REPOSITORY}/releases/download/{tag}/{name}"}]}

    def test_selects_matching_mac_architecture(self):
        self.assertEqual(choose_release([self.release()], "0.4.0-macos-preview.1", "arm64")["version"], "0.4.1")
        self.assertIsNone(choose_release([self.release()], "0.4.0", "x86_64"))

    def test_preview_and_stable_versions_sort_correctly(self):
        versions = ["0.4.0-macos-preview.1", "0.4.0-macos-preview.2", "0.4.0", "0.4.1"]
        self.assertEqual(sorted(versions, key=release_key), versions)
        self.assertIsNone(release_key("../../invalid"))

    def test_drafts_foreign_urls_missing_assets_and_old_releases_are_rejected(self):
        for attribute, value in (("draft", True), ("html_url", "https://example.com"), ("assets", [])):
            release = self.release()
            release[attribute] = value
            self.assertIsNone(choose_release([release], "0.4.0", "arm64"))
        self.assertIsNone(choose_release([self.release("0.3.6")], "0.4.0", "arm64"))
        release = self.release()
        release["assets"][0]["browser_download_url"] = "https://example.com/file.dmg"
        self.assertIsNone(choose_release([release], "0.4.0", "arm64"))

    def test_native_tls_context_requires_verified_certificate_and_hostname(self):
        context = updates.tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_request_uses_native_context_and_rejects_untrusted_redirects(self):
        response = Mock()
        response.geturl.return_value = updates.API_URL
        response.read.return_value = json.dumps([self.release()]).encode()
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(updates, "build_opener", return_value=opener) as factory, patch.object(updates.platform, "machine", return_value="arm64"):
            self.assertTrue(updates.check("0.4.0")["available"])
            self.assertIsInstance(factory.call_args.args[0], updates.NoRedirect)
            self.assertTrue(factory.call_args.args[1]._context.check_hostname)
            self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)
            response.geturl.return_value = "https://example.com/redirect"
            with self.assertRaises(ValueError):
                updates.check("0.4.0")
        with self.assertRaises(ValueError):
            updates.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")

    def test_oversized_or_invalid_feed_does_not_report_latest(self):
        response = Mock()
        response.geturl.return_value = updates.API_URL
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        for body in (b"x" * (4 * 1024 * 1024 + 1), b"{}", b"not json"):
            with self.subTest(size=len(body)), patch.object(updates, "build_opener", return_value=opener):
                response.read.return_value = body
                with self.assertRaises(ValueError):
                    updates.check("0.4.0")

    def test_normal_update_never_uses_ci_token_or_other_environment_credentials(self):
        response = Mock()
        response.geturl.return_value = updates.API_URL
        response.read.return_value = b"[]"
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(updates, "build_opener", return_value=opener), patch.dict(os.environ, {"AI_FIRST_CI_UPDATE_TOKEN": "synthetic-ci-token", "GH_TOKEN": "synthetic-other-token"}):
            updates.check("0.4.0")
            self.assertIsNone(opener.open.call_args.args[0].get_header("Authorization"))
            updates.check("0.4.0", token="synthetic-explicit-token")
            self.assertEqual(opener.open.call_args.args[0].get_header("Authorization"), "Bearer synthetic-explicit-token")

    def test_failures_are_distinguished_without_leaking_network_secrets(self):
        secret = "https://secret:password@private-proxy.example"
        cases = [(URLError(ssl.SSLCertVerificationError(secret)), "certificate"),
                 (URLError(ssl.SSLEOFError(secret)), "tls"),
                 (URLError(TimeoutError(secret)), "timeout"), (URLError(socket.gaierror(secret)), "dns"),
                 (HTTPError(secret, 403, secret, {"X-RateLimit-Remaining": "0"}, None), "rate_limit"),
                 (HTTPError(secret, 429, secret, {}, None), "rate_limit"),
                 (HTTPError(secret, 503, secret, {}, None), "http"), (ValueError(secret), "response"),
                 (ImportError(secret), "component"), (URLError(secret), "network")]
        for error, code in cases:
            with self.subTest(code=code):
                result = updates.failure(error)
                self.assertEqual(result["errorCode"], code)
                self.assertTrue(result["canOpenDownloads"])
                self.assertNotIn(secret, json.dumps(result))

    def test_failed_check_clears_old_update_and_browser_falls_back_to_own_downloads(self):
        from entry import MacApi

        api = MacApi()
        api._release = f"{REPOSITORY}/releases/tag/v0.4.1"
        with patch("entry.version_info", return_value={"release": "0.4.0"}), patch.object(updates, "check", side_effect=URLError(TimeoutError())):
            self.assertEqual(api.check_update()["errorCode"], "timeout")
        self.assertIsNone(api._release)
        with patch("entry.open_external") as browser:
            self.assertTrue(api.open_update()["ok"])
            browser.assert_called_once_with(updates.DOWNLOADS_URL)

    def test_network_self_check_fails_without_logging_private_exception_details(self):
        from entry import network_check

        with tempfile.TemporaryDirectory() as temporary, patch("entry.version_info", return_value={"release": "0.4.0-macos-preview.2"}), \
                patch("entry.updates.tls_context", side_effect=URLError("secret proxy")):
            report = Path(temporary) / "network-test.json"
            self.assertFalse(network_check(report))
            result = json.loads(report.read_text())
            self.assertEqual(result["errorCode"], "network")
            self.assertNotIn("secret", report.read_text())

    def test_transient_failure_retains_previously_validated_update_but_invalid_feed_clears_it(self):
        from entry import MacApi

        for error, retained in ((URLError(TimeoutError()), True), (ValueError("synthetic invalid feed"), False)):
            with self.subTest(retained=retained):
                api = MacApi()
                release = {"available": True, "version": "0.4.1", "url": f"{REPOSITORY}/releases/tag/v0.4.1"}
                package = {"version": "0.4.1", "sha256": "a" * 64}
                with patch("entry.version_info", return_value={"release": "0.4.0"}), \
                        patch.object(updates, "check", side_effect=[release, error]), \
                        patch("entry.updater.package_from_release", return_value=package) as validator:
                    self.assertTrue(api.check_update()["available"])
                    result = api.check_update()
                    self.assertEqual(result["retainedUpdate"], retained)
                    self.assertEqual(api._package, package if retained else None)
                    self.assertEqual(api._release, release["url"] if retained else None)
                    validator.assert_called_once_with(release)

    def test_smoke_automatic_reminder_is_synthetic_and_never_contacts_github(self):
        from entry import MacApi

        api = MacApi(smoke=True)
        with patch.object(updates, "check") as network:
            self.assertTrue(api.check_update()["available"])
            self.assertEqual(api._smoke_check_calls, 1)
            self.assertIsNone(api._package)
            self.assertEqual(api.update_status()["phase"], "idle")
            network.assert_not_called()


class MacResourceTests(unittest.TestCase):
    def test_cocoa_reads_only_bundled_ui_before_navigation_without_signalling_loaded(self):
        import entry
        from types import SimpleNamespace

        window = Mock(uid="synthetic")
        native = Mock()
        view = Mock()
        view.window.side_effect = [None, native]
        host = SimpleNamespace(window=native, webview=view)
        class Delegate:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

        cocoa = SimpleNamespace(BrowserView=SimpleNamespace(instances={window.uid: host}, BrowserDelegate=Delegate))
        helper = Mock(callAfter=lambda call: call())
        urls = SimpleNamespace(fileURLWithPath_=lambda path: path)
        with patch.dict(sys.modules, {"webview.platforms.cocoa": cocoa, "Foundation": SimpleNamespace(NSURL=urls),
                                     "PyObjCTools": SimpleNamespace(AppHelper=helper),
                                     "WebKit": SimpleNamespace(WKNavigationActionPolicyAllow=1, WKNavigationActionPolicyCancel=0)}):
            entry.load_bundled_content(window)
            host.load_url(window.real_url)
            with self.assertRaises(ValueError):
                host.load_url("https://example.invalid/untrusted")
        self.assertEqual(native.mock_calls, [unittest.mock.call.setContentView_(view), unittest.mock.call.makeFirstResponder_(view)])
        ui = (entry.ROOT / "ui").resolve()
        view.loadFileURL_allowingReadAccessToURL_.assert_called_once_with(str(ui / "index.html"), str(ui))
        self.assertTrue(window._ai_first_content_attached)
        self.assertTrue(window._ai_first_bundled_file_load)
        for local, path, expected in ((True, str(ui / "index.html"), 1), (False, str(ui / "index.html"), 0),
                                      (True, str(ui / "untrusted.html"), 0)):
            action = Mock()
            action.request().URL().isFileURL.return_value = local
            action.request().URL().path.return_value = path
            handler = Mock()
            host._ai_first_file_delegate.webView_decidePolicyForNavigationAction_decisionHandler_(view, action, handler)
            handler.assert_called_once_with(expected)
        window.events.loaded.set.assert_not_called()
        window.run_js.assert_not_called()

    def test_native_bridge_ready_signal_uses_the_injected_script_channel(self):
        import entry

        window = Mock()
        entry.signal_bridge_ready(window)
        window.run_js.assert_called_once_with("window.__AI_FIRST_BRIDGE_READY__=true;window.dispatchEvent(new CustomEvent('ai-first-ready'));")
        window.evaluate_js.assert_not_called()

    def test_cocoa_start_does_not_clear_shared_webkit_data_or_force_a_fixed_port(self):
        import entry

        worker = Mock()
        with patch.object(entry.webview, "settings", dict(entry.webview.settings)), patch.object(entry.webview, "start") as start:
            entry.start_cocoa(worker)
            start.assert_called_once_with(worker, gui="cocoa", private_mode=False)
            self.assertIsNone(entry.webview.settings["DEFAULT_HTTP_PORT"])
            self.assertFalse(entry.webview.settings["IGNORE_SSL_ERRORS"])

    def test_release_staging_leaves_missing_or_published_versions_untouched(self):
        import stage_macos_release

        for releases in ([], [{"tag_name": "v0.4.0-macos-preview.2", "draft": False}]):
            with self.subTest(releases=releases), patch.object(sys, "argv", ["stage", "--artifacts", "synthetic", "--commit", "a" * 40]), \
                    patch.object(stage_macos_release.subprocess, "run", return_value=Mock(stdout=json.dumps(releases))) as process, \
                    patch.object(stage_macos_release, "validated_assets") as assets:
                stage_macos_release.main()
                process.assert_called_once()
                assets.assert_not_called()

    def test_release_staging_rejects_failed_reports_and_wrong_dmg_hash(self):
        from stage_macos_release import validated_assets
        import hashlib

        release = "0.4.0-macos-preview.2"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for architecture in ("arm64", "x86_64"):
                source = directory / f"macos-{architecture}"
                source.mkdir()
                name = f"AI-First-Tools-{release}-macos-{architecture}.dmg"
                payload = b"synthetic package, not a runnable DMG"
                (source / name).write_bytes(payload)
                (source / f"SHA256SUMS-{architecture}.txt").write_text(f"{hashlib.sha256(payload).hexdigest()}  {name}\n")
                for kind in ("self", "smoke", "network", "update"):
                    checks = {"synthetic": True}
                    if kind == "update":
                        checks.update({"nativeUpdateClick": True, "bridgeDrained": True, "nativeParentExit": True})
                    (source / f"{kind}-test.json").write_text(json.dumps({"passed": True, "checks": checks,
                                                                          "architecture": architecture, "version": {"release": release}}))
            self.assertEqual(len(validated_assets(directory, release)), 11)
            update_report = directory / "macos-arm64/update-test.json"
            original_update = update_report.read_text()
            incomplete = json.loads(original_update)
            incomplete["checks"].pop("bridgeDrained")
            update_report.write_text(json.dumps(incomplete))
            with self.assertRaisesRegex(ValueError, "bridge handoff checks are required"):
                validated_assets(directory, release)
            update_report.write_text(original_update)
            report = directory / "macos-arm64/network-test.json"
            report.write_text(json.dumps({"passed": False, "checks": {"synthetic": False}}))
            with self.assertRaisesRegex(ValueError, "checks did not pass"):
                validated_assets(directory, release)
            (directory / f"macos-arm64/AI-First-Tools-{release}-macos-arm64.dmg").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                validated_assets(directory, release)

    def test_cocoa_smoke_waits_for_loaded_event_before_evaluating_bridge(self):
        from entry import MacApi, smoke_check

        window = Mock()
        window.events.loaded.wait.return_value = True
        window._ai_first_content_attached = True
        window._ai_first_bundled_file_load = True
        window.evaluate_js.side_effect = [json.dumps({"passed": True, "checks": {"bridge": True}}), True, None, True]
        api = MacApi(smoke=True)
        api._smoke_check_calls = 1
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "smoke.json"
            smoke_check(window, api, report)
            self.assertTrue(json.loads(report.read_text())["passed"])
        self.assertEqual(window.mock_calls[0], unittest.mock.call.events.loaded.wait(45))
        window.destroy.assert_called_once()

    def test_smoke_rejects_a_ready_bridge_without_native_content_attachment(self):
        from entry import MacApi, smoke_check

        window = Mock()
        window._ai_first_content_attached = False
        window.events.loaded.wait.return_value = True
        window.evaluate_js.side_effect = [json.dumps({"passed": True, "checks": {"bridge": True}}), True, None, True]
        api = MacApi(smoke=True)
        api._smoke_check_calls = 1
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "smoke.json"
            smoke_check(window, api, report)
            result = json.loads(report.read_text())
            self.assertFalse(result["passed"])
            self.assertFalse(result["checks"]["nativeContentAttached"])

    def test_unloaded_cocoa_window_fails_without_evaluating_javascript(self):
        from entry import MacApi, smoke_check

        window = Mock()
        window.events.loaded.wait.return_value = False
        window.events.loaded.is_set.return_value = False
        window.events.shown.is_set.return_value = True
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "smoke.json"
            smoke_check(window, MacApi(smoke=True), report)
            result = json.loads(report.read_text())
            self.assertFalse(result["passed"])
            self.assertFalse(result["checks"]["pageLoaded"])
        window.evaluate_js.assert_not_called()
        window.destroy.assert_called_once()

    def test_native_smoke_rejects_missing_automatic_reminder_even_with_a_ready_bridge(self):
        from entry import MacApi, smoke_check

        window = Mock()
        window.events.loaded.wait.return_value = True
        window.evaluate_js.side_effect = [json.dumps({"passed": True, "checks": {"bridge": True}}), False]
        with tempfile.TemporaryDirectory() as temporary, patch("entry.time.monotonic", side_effect=[0, 1, 46]), patch("entry.time.sleep"):
            report = Path(temporary) / "smoke.json"
            smoke_check(window, MacApi(smoke=True), report)
            result = json.loads(report.read_text())
            self.assertFalse(result["passed"])
            self.assertFalse(result["checks"]["automaticUpdateReminder"])
        window.destroy.assert_called_once()

    def test_workspace_wraps_shared_ui_without_iframes_or_child_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            prepared = prepare(Path(temporary))
            html = (prepared / "ui/index.html").read_text(encoding="utf-8")
            for name in ("workspace-nav", "workspace-toggle", "agents", "bar", "sheet"):
                self.assertEqual(html.count(f'id="{name}"'), 1)
            self.assertNotIn("<iframe", html)
            self.assertIn('aria-controls="workspace-nav"', html)
            self.assertEqual((prepared / "ui/assets/dialog-mover.png").read_bytes(), (ROOT / "workspace/assets/dialog-mover.png").read_bytes())
            self.assertEqual((prepared / "ui/assets/ai-first.png").read_bytes(), (ROOT / "workspace/assets/ai-first-app-icon.png").read_bytes())
            self.assertEqual((prepared / "ui/app.js").read_bytes(), (ROOT / "dialog-mover/ui/app.js").read_bytes())
            self.assertEqual(json.loads((prepared / "version.json").read_text())["version"], "0.4.0")


if __name__ == "__main__":
    unittest.main()
