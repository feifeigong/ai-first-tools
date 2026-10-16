from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from codex_auto_resume.config import AppConfig, save_config
from codex_auto_resume.daemon import _wait_or_stop
from codex_auto_resume.paths import resolve_codex_command
from codex_auto_resume.workspace_control import allow_background_watch


class WorkbenchBundleTests(unittest.TestCase):
    def test_frozen_runtime_uses_packaged_cli_without_external_python_node_or_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / 'bin/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'synthetic fixture')
            with patch('sys.frozen', True, create=True), patch('sys._MEIPASS', str(root), create=True):
                self.assertEqual(resolve_codex_command('external-cli-that-must-not-run'), [str(executable)])

    def test_frozen_startup_has_separate_preference_from_legacy_service(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = Path(temporary) / 'AI一手工具工作台'
            settings.mkdir()
            (settings / 'auto-resume-startup.json').write_text('{"autostart":false}', encoding='utf-8')
            with patch('sys.frozen', True, create=True):
                self.assertTrue(allow_background_watch(['watch','--quiet'], {'LOCALAPPDATA':temporary}))
                (settings / 'bundled-auto-resume-startup.json').write_text('{"autostart":false}', encoding='utf-8-sig')
                self.assertFalse(allow_background_watch(['watch','--quiet'], {'LOCALAPPDATA':temporary}))
                self.assertTrue(allow_background_watch(['watch','--quiet'], {'LOCALAPPDATA':temporary,'AI_FIRST_MANUAL_WATCH':'1'}))

    def test_runtime_never_writes_user_configuration_into_installation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = root / 'installed'
            application.mkdir()
            with patch('sys.frozen',True,create=True), patch('codex_auto_resume.config.tool_root', return_value=application):
                save_config(AppConfig(state_dir=str(root / 'state')))
            self.assertFalse((application / 'config.example.json').exists())
            self.assertTrue((root / 'state/config.json').is_file())

    def test_stop_request_interrupts_a_long_poll_delay(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'stop.request'
            path.write_text('stop')
            start = time.monotonic()
            _wait_or_stop(path, 3600)
            self.assertLess(time.monotonic() - start, 0.5)
