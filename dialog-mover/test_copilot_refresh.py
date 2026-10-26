import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

from core import copilot_refresh


class CopilotRefreshTests(unittest.TestCase):
    def test_active_tasks_and_unknown_schema_never_reload_the_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with closing(sqlite3.connect(root / "data.db")) as db, db:
                db.execute("CREATE TABLE sessions(id TEXT, is_running INTEGER)")
                db.execute("INSERT INTO sessions VALUES ('synthetic',1)")
            with patch("core.copilot_local.root", return_value=root), patch("core.copilot_refresh.sys.platform", "win32"), patch("core.copilot_refresh._windows", return_value="requested") as native:
                self.assertEqual(copilot_refresh.refresh(), "busy")
                native.assert_not_called()
                with closing(sqlite3.connect(root / "data.db")) as db, db:
                    db.execute("UPDATE sessions SET is_running=0")
                self.assertEqual(copilot_refresh.refresh(), "requested")
                self.assertEqual(native.call_count, 1)
                with closing(sqlite3.connect(root / "data.db")) as db, db:
                    db.execute("DROP TABLE sessions")
                self.assertEqual(copilot_refresh.refresh(), "unavailable")
                self.assertEqual(native.call_count, 1)

    def test_mac_uses_its_guarded_adapter_instead_of_windows_input(self):
        with patch("core.copilot_refresh.sys.platform", "darwin"), patch("core.copilot_refresh._windows") as native:
            with patch('core.copilot_refresh._busy', return_value='idle'), \
                    patch('core.copilot_refresh_macos.refresh', return_value='requested') as mac:
                self.assertEqual(copilot_refresh.refresh(passive=True), 'requested')
                mac.assert_called_once_with(passive=True, busy=copilot_refresh._busy)
            native.assert_not_called()

    def test_mac_busy_and_unknown_indexes_are_not_opened_or_refreshed(self):
        for state in ('busy', 'unavailable'):
            with patch('core.copilot_refresh.sys.platform','darwin'), \
                    patch('core.copilot_refresh._busy', return_value=state), \
                    patch('core.copilot_refresh_macos.refresh') as native:
                self.assertEqual(copilot_refresh.refresh(), state)
                native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
