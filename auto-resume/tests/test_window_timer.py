from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from codex_auto_resume.automation import control, permitted
from codex_auto_resume.config import AppConfig, save_config
from codex_auto_resume.daemon import tick
from codex_auto_resume.quota import QuotaSnapshot, QuotaWindow
from codex_auto_resume.state import AppState
from codex_auto_resume.window_timer import tick_timer, timer_summary

NOW=10000


def snapshot(reset=9000, used=0, weekly=30, **kw):
    return QuotaSnapshot(primary=QuotaWindow(used_percent=used, resets_at=reset, window_minutes=300),
        secondary=QuotaWindow(used_percent=weekly, resets_at=90000, window_minutes=10080),
        limit_id='codex', source='app-server', **kw)


class WindowTimerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='quota-timer-synthetic-')
        self.root=Path(self.temp.name)
        self.cfg=AppConfig(enabled=False, auto_start_five_hour=True, state_dir=str(self.root), codex_home=str(self.root/'empty'))
        self.reader=Mock()
        self.reader.read.side_effect=[snapshot(),snapshot(reset=28000,used=1)]
        self.reader.start_window.return_value=True

    def tearDown(self): self.temp.cleanup()

    def run_timer(self, before=None, **kwargs):
        tick_timer(self.cfg,self.reader,before or snapshot(),NOW,**kwargs)

    def test_one_ephemeral_request_and_only_official_time_confirm_success(self):
        self.run_timer()
        self.reader.start_window.assert_called_once()
        self.assertEqual(timer_summary(self.root),{'timerStatus':'started','nextResetAt':28000})

    def test_off_by_default_and_disabled_does_not_even_read_quota(self):
        self.assertFalse(AppConfig().auto_start_five_hour)
        self.assertFalse(AppConfig().auto_redeem_weekly_reset)
        self.cfg.auto_start_five_hour=False
        self.run_timer()
        self.reader.read.assert_not_called()
        self.reader.start_window.assert_not_called()

    def test_normal_future_window_and_user_use_do_not_send(self):
        for used in (0,1,99):
            with self.subTest(used=used): self.run_timer(snapshot(reset=28000,used=used))
        self.reader.start_window.assert_not_called()
        self.assertEqual(timer_summary(self.root)['nextResetAt'],28000)

    def test_running_or_resumed_work_takes_priority(self):
        self.run_timer(activity=True)
        self.reader.start_window.assert_not_called()
        self.assertEqual(timer_summary(self.root)['timerStatus'],'activity')

    def test_user_started_during_reread_skip_extra_request(self):
        self.reader.read.side_effect=[snapshot(reset=28000,used=1)]
        self.run_timer()
        self.reader.start_window.assert_not_called()

    def test_weekly_exhaustion_never_redeems_for_timer(self):
        self.run_timer(snapshot(weekly=100))
        self.reader.read.assert_not_called()
        self.reader.start_window.assert_not_called()
        self.reader.try_redeem.assert_not_called()

    def test_unsupported_quota_pool_and_unknown_usage_never_send(self):
        bad=[replace(snapshot(),limit_id=None),replace(snapshot(),limit_id='other'),replace(snapshot(),ambiguous_bucket=True),
             replace(snapshot(),source='cache'), replace(snapshot(),primary=QuotaWindow(used_percent=0,window_minutes=60)),
             snapshot(used=float('nan')),snapshot(used=100),snapshot(weekly=float('inf')),
             snapshot(ordinary_usage_allowed=False),snapshot(spend_control_reached=True)]
        for value in bad:
            with self.subTest(value=value): self.run_timer(value)
        self.reader.start_window.assert_not_called()

    def test_response_without_new_official_reset_is_not_success(self):
        self.reader.read.side_effect=[snapshot(),snapshot()]
        self.run_timer()
        self.assertEqual(timer_summary(self.root),{'timerStatus':'unconfirmed','nextResetAt':0})

    def test_different_bucket_and_unreasonable_time_are_not_success(self):
        for after in (replace(snapshot(reset=28000),limit_id='other'),snapshot(reset=9999999)):
            with self.subTest(after=after):
                (self.root/'window-timer.json').unlink(missing_ok=True)
                self.reader.read.side_effect=[snapshot(),after]
                self.run_timer()
                self.assertEqual(timer_summary(self.root)['timerStatus'],'unconfirmed')

    def test_timeout_and_restart_do_not_duplicate_attempt(self):
        self.reader.start_window.side_effect=TimeoutError
        self.run_timer()
        self.assertEqual(timer_summary(self.root)['timerStatus'],'unconfirmed')
        fresh=Mock()
        tick_timer(self.cfg,fresh,snapshot(),NOW+30)
        fresh.start_window.assert_not_called()
        fresh.read.assert_not_called()

    def test_definitely_unsent_preflight_failure_can_retry_after_cooldown(self):
        self.reader.read.side_effect=None;self.reader.read.return_value=snapshot()
        self.reader.start_window.return_value=None
        self.run_timer()
        self.assertEqual(timer_summary(self.root)['timerStatus'],'unavailable')
        tick_timer(self.cfg,self.reader,snapshot(),NOW+30)
        self.assertEqual(self.reader.start_window.call_count,1)
        tick_timer(self.cfg,self.reader,snapshot(),NOW+601)
        self.assertEqual(self.reader.start_window.call_count,2)

    def test_disappearing_or_changing_stale_stamp_does_not_duplicate(self):
        self.reader.start_window.side_effect=TimeoutError
        self.run_timer()
        other=Mock()
        for reset in (0,9001,8999):
            tick_timer(self.cfg,other,snapshot(reset=reset),NOW+60)
        other.start_window.assert_not_called()
        other.read.assert_not_called()

    def test_write_ahead_crash_does_not_duplicate(self):
        self.reader.start_window.side_effect=KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt): self.run_timer()
        self.reader.start_window.reset_mock()
        self.run_timer()
        self.reader.start_window.assert_not_called()
        self.assertEqual(timer_summary(self.root)['timerStatus'],'unconfirmed')

    def test_next_observed_cycle_allows_exactly_one_new_attempt(self):
        self.run_timer()
        self.reader.read.side_effect=[snapshot(reset=28000),snapshot(reset=46600,used=1)]
        tick_timer(self.cfg,self.reader,snapshot(reset=28000),28600)
        self.assertEqual(self.reader.start_window.call_count,2)

    def test_disable_during_reread_prevents_submission(self):
        def read(*args):
            control('timer-off',self.root)
            return snapshot()
        self.reader.read.side_effect=read
        self.run_timer()
        self.reader.start_window.assert_not_called()

    def test_cancel_during_write_ahead_prevents_submission(self):
        checks=iter([False,False,True])
        self.run_timer(should_stop=lambda:next(checks))
        self.reader.start_window.assert_not_called()

    def test_corrupt_timer_is_preserved_and_blocks_requests(self):
        p=self.root/'window-timer.json';p.write_text('{unknown',encoding='utf8')
        self.run_timer()
        self.assertEqual(p.read_text(),'{unknown')
        self.assertEqual(timer_summary(self.root)['timerStatus'],'error')
        self.reader.start_window.assert_not_called()

    def test_timer_only_tick_does_not_scan_resume_or_use_cards(self):
        self.cfg.auto_redeem_weekly_reset=True
        self.reader.read.side_effect=None;self.reader.read.return_value=snapshot(weekly=100)
        with patch('codex_auto_resume.daemon.scan_waiting_sessions') as scan, patch('codex_auto_resume.daemon.spawn_resume') as resume:
            tick(self.cfg,AppState(),self.reader)
        self.reader.try_redeem.assert_not_called();scan.assert_not_called();resume.assert_not_called()


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='quota-policy-synthetic-')
        self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_status_is_read_only_new_options_default_off(self):
        value=control('status',self.root)
        self.assertFalse(value['autoRedeem']);self.assertFalse(value['autoStartWindow'])
        self.assertEqual(list(self.root.iterdir()),[])

    def test_policy_preserves_legacy_choices_and_unknown_settings(self):
        p=self.root/'config.json';p.write_text(json.dumps({'enabled':True,'auto_redeem_weekly_reset':True,'custom':{'keep':1}}))
        control('timer-on',self.root)
        value=json.loads(p.read_text());self.assertTrue(value['enabled']);self.assertTrue(value['auto_redeem_weekly_reset'])
        self.assertEqual(value['custom'],{'keep':1})

    def test_turn_off_resume_keeps_timer_but_clears_credit_and_never_reenables_it(self):
        control('timer-on',self.root);control('credit-on',self.root)
        value=control('resume-off',self.root)
        self.assertFalse(value['resumeEnabled']);self.assertTrue(value['autoStartWindow']);self.assertFalse(value['autoRedeem'])
        before=(self.root/'config.json').read_bytes()
        with self.assertRaises(ValueError): control('credit-on',self.root)
        self.assertEqual((self.root/'config.json').read_bytes(),before)
        self.assertFalse(control('resume-on',self.root)['autoRedeem'])

    def test_invalid_boolean_is_not_treated_as_enabled_or_overwritten(self):
        p=self.root/'config.json';p.write_text('{"auto_start_five_hour":"false"}')
        old=p.read_bytes()
        with self.assertRaises(ValueError): control('timer-on',self.root)
        self.assertEqual(p.read_bytes(),old)
        self.assertFalse(permitted(AppConfig(state_dir=str(self.root)),'auto_start_five_hour'))
