import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import cursor_refresh

PALETTE_ROWS = ["Go Back", "Go Forward", "New Agent", "Select Model"]
SIDEBAR_ROWS = ["Synthetic chat", "Another chat"]


class Keyboard:
    """Records the calls that would reach Cursor's window."""

    instances = []

    def __init__(self):
        self.calls = []
        Keyboard.instances.append(self)

    def palette(self):
        self.calls.append("palette")
        return True

    def type(self, text):
        self.calls.append(("type", text))
        return True

    def enter(self):
        self.calls.append("enter")
        return True

    def escape(self):
        self.calls.append("escape")
        return True


def uia():
    """Stands in for the UI Automation types; roots are just tuples."""
    return (lambda handle: handle), SimpleNamespace(FromHandle=lambda handle: ("root", handle)), object, object, object


class CursorRefreshTests(unittest.TestCase):
    def setUp(self):
        Keyboard.instances = []
        self.patches = [
            patch.object(cursor_refresh, "sys", SimpleNamespace(platform="win32")),
            patch.object(cursor_refresh, "_uia", uia),
            patch.object(cursor_refresh, "_Keyboard", Keyboard),
            patch.object(cursor_refresh, "PALETTE_WAIT", 0.05),
            patch.object(cursor_refresh, "LIST_WAIT", 0.05),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(lambda: [item.stop() for item in self.patches])

    def keys(self):
        return Keyboard.instances[-1].calls if Keyboard.instances else []

    def rows(self, opened, filtered=None):
        """Sidebar rows until the palette opens, then the palette's own rows."""
        def call(_root):
            calls = self.keys()
            if "palette" not in calls:
                return SIDEBAR_ROWS
            if not any(isinstance(call_item, tuple) for call_item in calls):
                return opened
            return opened if filtered is None else filtered
        return call

    def test_absent_cursor_is_not_an_error_and_sends_nothing(self):
        with patch.object(cursor_refresh, "_windows", return_value=[]):
            self.assertEqual(cursor_refresh.refresh(), "not-running")
        self.assertEqual(self.keys(), [])

    def test_two_ordinary_windows_are_never_guessed_between(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(1, "Cursor"), (2, "Cursor")]), \
                patch.object(cursor_refresh, "_lift") as lift:
            self.assertEqual(cursor_refresh.refresh(), "unavailable")
        lift.assert_not_called()

    def test_the_agents_window_is_chosen_when_an_editor_window_is_also_open(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(1, "Cursor"), (2, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="draft"), \
                patch.object(cursor_refresh, "_lift") as lift:
            self.assertEqual(cursor_refresh.refresh(), "draft")
        lift.assert_not_called()

    def test_unsent_text_stops_every_keystroke(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(7, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="draft"), \
                patch.object(cursor_refresh, "_lift") as lift:
            self.assertEqual(cursor_refresh.refresh(), "draft")
        lift.assert_not_called()
        self.assertEqual(self.keys(), [])

    def test_a_running_agent_stops_every_keystroke(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(7, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="busy"), \
                patch.object(cursor_refresh, "_lift") as lift:
            self.assertEqual(cursor_refresh.refresh(), "busy")
        lift.assert_not_called()
        self.assertEqual(self.keys(), [])

    def test_a_window_that_cannot_be_raised_is_not_typed_into(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(7, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="ready"), \
                patch.object(cursor_refresh, "_lift", return_value=False):
            self.assertEqual(cursor_refresh.refresh(), "unavailable")
        self.assertEqual(self.keys(), [])

    def test_an_already_open_palette_is_left_to_the_user(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(7, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="ready"), \
                patch.object(cursor_refresh, "_lift", return_value=True), \
                patch.object(cursor_refresh, "_names", return_value=PALETTE_ROWS):
            self.assertEqual(cursor_refresh.refresh(), "unavailable")
        self.assertEqual(self.keys(), [])

    def test_a_palette_that_never_opens_receives_no_command_name(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(7, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="ready"), \
                patch.object(cursor_refresh, "_lift", return_value=True), \
                patch.object(cursor_refresh, "_names", return_value=SIDEBAR_ROWS):
            self.assertEqual(cursor_refresh.refresh(), "unavailable")
        self.assertEqual(self.keys(), ["palette"])

    def test_a_palette_without_the_command_is_escaped_not_confirmed(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(7, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="ready"), \
                patch.object(cursor_refresh, "_lift", return_value=True), \
                patch.object(cursor_refresh, "_names", self.rows(PALETTE_ROWS + ["Archive", "Search Agents"])):
            self.assertEqual(cursor_refresh.refresh(), "unavailable")
        self.assertEqual(self.keys(), ["palette", ("type", "reload window"), "escape"])

    def test_the_listed_command_is_confirmed_with_one_enter(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(7, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="ready"), \
                patch.object(cursor_refresh, "_lift", return_value=True), \
                patch.object(cursor_refresh, "_names", self.rows(PALETTE_ROWS, PALETTE_ROWS + ["Reload Window"])):
            self.assertEqual(cursor_refresh.refresh(), "requested")
        self.assertEqual(self.keys(), ["palette", ("type", "reload window"), "enter"])

    def test_a_composer_that_cannot_be_read_fails_closed(self):
        with patch.object(cursor_refresh, "_windows", return_value=[(7, "Cursor Agents")]), \
                patch.object(cursor_refresh, "_inspect", return_value="unavailable"), \
                patch.object(cursor_refresh, "_lift", return_value=True):
            self.assertEqual(cursor_refresh.refresh(), "unavailable")
        self.assertEqual(self.keys(), [])

    def test_other_platforms_never_send_input(self):
        with patch.object(cursor_refresh, "sys", SimpleNamespace(platform="darwin")), \
                patch.object(cursor_refresh, "_windows") as windows:
            self.assertEqual(cursor_refresh.refresh(), "unsupported")
        windows.assert_not_called()
        self.assertEqual(self.keys(), [])


class CursorCommandNameTests(unittest.TestCase):
    def test_known_names_are_recognised_with_or_without_the_shortcut(self):
        for name in ("Reload Window", "reload window", "Developer: Reload Window",
                     "重新加载窗口", "Reload WindowCtrl+Shift+P"):
            self.assertTrue(cursor_refresh._reload_entry([name]), name)

    def test_other_commands_that_merely_start_with_reload_are_not_accepted(self):
        for name in ("Reload Agent", "Reload Webviews", "Reload Window Settings"):
            self.assertFalse(cursor_refresh._reload_entry([name]), name)

    def test_the_palette_needs_its_own_rows_before_anything_is_typed(self):
        self.assertTrue(cursor_refresh._palette_open(PALETTE_ROWS))
        self.assertFalse(cursor_refresh._palette_open(["Go Back", "New Agent"]))
        self.assertFalse(cursor_refresh._palette_open(SIDEBAR_ROWS))

    def test_only_letters_and_spaces_can_be_typed(self):
        keys = object.__new__(cursor_refresh._Keyboard)
        sent = []
        keys._types = (lambda *arguments: SimpleNamespace(), lambda **values: values, lambda *arguments: arguments)
        keys._send = lambda events: sent.append(events) or True
        self.assertTrue(keys.type("reload window"))
        self.assertEqual(len(sent[0]), 26)
        self.assertFalse(keys.type("reload\nwindow"))


if __name__ == "__main__":
    unittest.main()
