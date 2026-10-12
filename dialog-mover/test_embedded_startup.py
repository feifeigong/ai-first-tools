import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from webview.event import Event
from embedded_startup import EmbeddedStartup
from main import main


class EmbeddedStartupTests(unittest.TestCase):
    def test_standalone_launch_keeps_its_normal_visible_window(self):
        with patch.dict(os.environ, {}, clear=True), patch("main.webview.create_window") as create, patch("main.webview.start"):
            main()
            self.assertFalse(create.call_args.kwargs["hidden"])
            self.assertTrue(create.call_args.kwargs["focus"])

    def test_suite_launch_uses_a_hidden_non_focusing_window(self):
        directory = Path(tempfile.gettempdir()) / ("ai-first-startup-" + uuid.uuid4().hex)
        directory.mkdir(exist_ok=False)
        try:
            environment = {"AI_FIRST_WORKSPACE_READY_FILE": str(directory / "window.json"), "AI_FIRST_WORKSPACE_HOST_PID": str(os.getpid())}
            with patch.dict(os.environ, environment, clear=True), patch("main.webview.create_window") as create, patch("main.webview.start"):
                main()
                self.assertTrue(create.call_args.kwargs["hidden"])
                self.assertFalse(create.call_args.kwargs["focus"])
        finally:
            directory.rmdir()

    def test_invalid_or_unowned_startup_paths_do_not_hide_the_app(self):
        for filename, host in (("window.json", "12"), (str(Path(tempfile.gettempdir()) / "window.json"), "12"), ("window.json", "0"), ("window.json", "broken")):
            with self.subTest(filename=filename, host=host), patch.dict(os.environ, {"AI_FIRST_WORKSPACE_READY_FILE": filename, "AI_FIRST_WORKSPACE_HOST_PID": host}, clear=True):
                self.assertIsNone(EmbeddedStartup.from_environment())

    def test_taskbar_is_hidden_before_first_show_and_readiness_waits_for_page_load(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "window.json"
            startup = EmbeddedStartup(filename, os.getpid())
            events = SimpleNamespace(before_show=Event(None, True), loaded=Event(None, True), closed=Event(None, True))
            native = SimpleNamespace(ShowInTaskbar=True, Handle=SimpleNamespace(ToInt64=lambda: 12345))
            window = SimpleNamespace(native=native, events=events, focus=False)
            startup.bind(window)
            self.assertFalse(filename.exists())
            with patch.object(startup, "user_api") as user_api, patch("embedded_startup.threading.Thread") as watcher:
                user_api.return_value.GetWindowLongPtrW.return_value = 0x00040000
                window.events.before_show.set()
                user_api.return_value.SetWindowLongPtrW.assert_called_once_with(12345, -20, 0x00000080)
                watcher.assert_called_once()
            self.assertFalse(filename.exists())
            with patch("embedded_startup.threading.Thread") as thread:
                window.events.loaded.set()
                self.assertTrue(window.focus)
                self.assertEqual(json.loads(filename.read_text()), {"processId": os.getpid(), "window": 12345})
                self.assertFalse(filename.with_suffix(".tmp").exists())
                thread.assert_not_called()
            window.events.closed.set()
            self.assertTrue(startup.closed.is_set())

    def test_interrupted_handshake_restores_the_window(self):
        with tempfile.TemporaryDirectory() as directory:
            startup = EmbeddedStartup(Path(directory) / "absent" / "window.json", os.getpid())
            startup.window = SimpleNamespace(focus=False)
            startup.restore = Mock()
            startup.loaded()
            startup.restore.assert_called_once()
        with tempfile.TemporaryDirectory() as directory:
            startup = EmbeddedStartup(Path(directory) / "window.json", os.getpid())
            startup.window = SimpleNamespace(focus=False, native=SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda: 12345)))
            startup.restore = Mock()
            with patch.object(Path, "write_text", side_effect=OSError("test write failure")):
                startup.loaded()
            startup.restore.assert_called_once()


if __name__ == "__main__":
    unittest.main()
