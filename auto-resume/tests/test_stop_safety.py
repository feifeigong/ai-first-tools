from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_auto_resume.config import AppConfig
from codex_auto_resume.daemon import LiveQuota, tick, watch_forever
from codex_auto_resume.quota import parse_quota_payload
from codex_auto_resume.redeem import try_redeem_weekly_reset
from codex_auto_resume.sessions import WaitingSession
from codex_auto_resume.state import AppState, load_state, save_state

try:
    from fakes import FakeQuotaClient
except ImportError:
    from tests.fakes import FakeQuotaClient


THREAD = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class StopSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="resume-stop-synthetic-")
        self.root = Path(self.temporary.name)
        self.state_dir = self.root / "state"
        self.state_dir.mkdir()
        self.stop = self.state_dir / "stop.request"
        self.cfg = AppConfig(state_dir=str(self.state_dir), codex_home=str(self.root / "codex"), auto_redeem_weekly_reset=True)
        self.waiting = WaitingSession(thread_id=THREAD, cwd=str(self.root), path=self.root / "synthetic.jsonl",
                                      mark="synthetic-limit", resets_at=9999999999, observed_at=1,
                                      snapshot=None, reason="usage-limit")

    def tearDown(self):
        self.temporary.cleanup()

    def live(self, client):
        reader = LiveQuota(self.cfg)
        reader.client = client
        return reader

    def stop_now(self):
        self.stop.write_text("stop\n", encoding="utf-8")

    def test_stop_before_tick_does_not_read_quota(self):
        self.stop_now()
        client = FakeQuotaClient()
        state = tick(self.cfg, quota_reader=self.live(client), should_stop=self.stop.exists)
        self.assertEqual(client.read_calls, [])
        self.assertEqual(state.last_status, "stopping")

    def test_stop_during_quota_read_never_redeems_or_resumes(self):
        client = FakeQuotaClient(primary_used=100, weekly_used=100, allow_consume=True)
        read = client.read_rate_limits

        def stopping_read(include_credits=False):
            result = read(include_credits=include_credits)
            self.stop_now()
            return result

        with patch.object(client, "read_rate_limits", side_effect=stopping_read), patch("codex_auto_resume.daemon.spawn_resume") as spawn, patch("codex_auto_resume.daemon.scan_waiting_sessions") as scan:
            state = tick(self.cfg, quota_reader=self.live(client), should_stop=self.stop.exists)
        self.assertEqual(client.consume_calls, [])
        self.assertEqual(client.read_calls, [False])
        spawn.assert_not_called()
        scan.assert_not_called()
        self.assertEqual(state.last_status, "stopping")

    def test_stop_during_credit_reread_never_consumes_credit(self):
        client = FakeQuotaClient(primary_used=100, weekly_used=100, allow_consume=True)
        read = client.read_rate_limits

        def stopping_credit_read(include_credits=False):
            result = read(include_credits=include_credits)
            if include_credits:
                self.stop_now()
            return result

        with patch.object(client, "read_rate_limits", side_effect=stopping_credit_read), patch("codex_auto_resume.daemon.spawn_resume") as spawn:
            state = tick(self.cfg, quota_reader=self.live(client), should_stop=self.stop.exists)
        self.assertEqual(client.read_calls, [False, True])
        self.assertEqual(client.consume_calls, [])
        self.assertEqual(client.credits, 1)
        self.assertEqual(state.last_reset_credit_at, 0)
        self.assertEqual(state.last_reset_credit_note, "")
        self.assertEqual(state.last_status, "stopping")
        spawn.assert_not_called()

    def test_final_consume_boundary_checks_cancellation_again(self):
        client = FakeQuotaClient(primary_used=100, weekly_used=100, allow_consume=True)
        snapshot = parse_quota_payload(client.read_rate_limits(), source="app-server")
        state = AppState()
        with patch("codex_auto_resume.redeem.can_redeem_credit", side_effect=lambda value: (self.stop_now() or True, "has-credit")):
            _, note = try_redeem_weekly_reset(cfg=self.cfg, snapshot=snapshot, state=state, now=100,
                                             client=client, should_stop=self.stop.exists)
        self.assertEqual(note, "stopped-before-redeem")
        self.assertEqual(client.consume_calls, [])
        self.assertEqual(state.last_reset_credit_at, 0)

    def test_already_sent_consume_result_is_recorded_but_no_resume_follows(self):
        client = FakeQuotaClient(primary_used=100, weekly_used=100, allow_consume=True)
        consume = client.consume_reset_credit

        def sent_then_stop(credit_id=None):
            result = consume(credit_id)
            self.stop_now()
            return result

        with patch.object(client, "consume_reset_credit", side_effect=sent_then_stop), patch("codex_auto_resume.daemon.spawn_resume") as spawn:
            state = tick(self.cfg, quota_reader=self.live(client), should_stop=self.stop.exists)
        self.assertEqual(client.consume_calls, ["sim-credit-1"])
        self.assertEqual(client.credits, 0)
        self.assertEqual(state.last_reset_credit_note, "redeemed:reset")
        self.assertEqual(load_state(self.state_dir).last_reset_credit_note, "redeemed:reset")
        self.assertEqual(state.last_status, "stopping")
        spawn.assert_not_called()

    def test_stop_during_scan_prevents_resume_submission(self):
        client = FakeQuotaClient(primary_used=0, weekly_used=0)

        def stopping_scan(*args, **kwargs):
            self.stop_now()
            return [self.waiting]

        with patch("codex_auto_resume.daemon.scan_waiting_sessions", side_effect=stopping_scan), patch("codex_auto_resume.daemon.spawn_resume") as spawn:
            state = tick(self.cfg, quota_reader=self.live(client), should_stop=self.stop.exists)
        spawn.assert_not_called()
        self.assertEqual(state.last_status, "stopping")

    def test_stop_during_write_ahead_restores_unsubmitted_turn(self):
        client = FakeQuotaClient(primary_used=0, weekly_used=0)

        def save_then_stop(directory, state):
            result = save_state(directory, state)
            if any(task.phase == "submitting" for task in state.threads.values()):
                self.stop_now()
            return result

        with patch("codex_auto_resume.daemon.scan_waiting_sessions", return_value=[self.waiting]), patch("codex_auto_resume.daemon.process_running", return_value=False), patch("codex_auto_resume.daemon.save_state", side_effect=save_then_stop), patch("codex_auto_resume.daemon.spawn_resume") as spawn:
            state = tick(self.cfg, quota_reader=self.live(client), should_stop=self.stop.exists)
        spawn.assert_not_called()
        task = state.threads[THREAD]
        self.assertEqual(task.phase, "idle")
        self.assertEqual(task.last_resume_at, 0)
        self.assertEqual(task.resumes, 0)
        self.assertEqual(state.last_status, "stopping")
        persisted = load_state(self.state_dir).threads[THREAD]
        self.assertEqual(persisted.phase, "idle")
        self.assertEqual(persisted.last_resume_at, 0)

    def test_watch_loop_passes_its_stop_file_to_tick(self):
        def fake_tick(cfg, quota_reader=None, should_stop=None):
            self.assertIsNotNone(should_stop)
            self.assertFalse(should_stop())
            self.stop_now()
            self.assertTrue(should_stop())
            return AppState(last_status="stopping")

        with patch("codex_auto_resume.daemon.claim_watch_pid", return_value=True), patch("codex_auto_resume.daemon.release_watch_pid"), patch("codex_auto_resume.daemon.tick", side_effect=fake_tick) as call:
            watch_forever(self.cfg)
        call.assert_called_once()
