from __future__ import annotations

import unittest
from types import SimpleNamespace

from webview.event import Event

from main import Api


class CloseSafetyTests(unittest.TestCase):
    def test_idle_window_can_close(self):
        self.assertTrue(Api().can_close())

    def test_busy_job_vetoes_native_close_without_stopping_it(self):
        api = Api()
        job = SimpleNamespace(snapshot=lambda: {"finished": False})
        api._job = job
        self.assertFalse(api.can_close())
        self.assertIs(api._job, job)
        job.snapshot = lambda: {"finished": True}
        self.assertTrue(api.can_close())

    def test_window_closing_event_obeys_busy_guard(self):
        api = Api()
        window = SimpleNamespace(events=SimpleNamespace(closing=Event(None, should_lock=True)))
        api.bind(window)
        self.assertFalse(window.events.closing.set())
        api._job = SimpleNamespace(snapshot=lambda: {"finished": False})
        self.assertTrue(window.events.closing.set())
        api._job.snapshot = lambda: {"finished": True}
        self.assertFalse(window.events.closing.set())

    def test_preparing_a_move_blocks_close_without_waiting_for_its_lock(self):
        api = Api()
        api._lock.acquire()
        try:
            self.assertFalse(api.can_close())
        finally:
            api._lock.release()
        self.assertTrue(api.can_close())
