from __future__ import annotations

import unittest

from codex_auto_resume.quota import parse_quota_payload, quota_available, quota_recovered


class QuotaTests(unittest.TestCase):
    def test_parse_rollout_snake_case(self) -> None:
        snap = parse_quota_payload(
            {
                "limit_id": "codex",
                "primary": {"used_percent": 100.0, "window_minutes": 300, "resets_at": 2000},
                "secondary": {"used_percent": 12.0, "window_minutes": 10080, "resets_at": 3000},
                "plan_type": "plus",
            },
            source="rollout",
            fetched_at=10,
        )
        assert snap is not None
        self.assertEqual(snap.primary.used_percent, 100.0)
        self.assertEqual(snap.primary.resets_at, 2000)
        self.assertEqual(snap.plan_type, "plus")

    def test_parse_app_server_camel_case(self) -> None:
        snap = parse_quota_payload(
            {
                "ordinaryUsageAllowed": False,
                "rateLimits": {
                    "primary": {"usedPercent": 100, "windowDurationMins": 300, "resetsAt": 5000},
                    "rateLimitReachedType": None,
                },
            },
            source="app-server",
        )
        assert snap is not None
        self.assertFalse(snap.ordinary_usage_allowed)
        self.assertEqual(snap.primary.resets_at, 5000)

    def test_reset_time_is_hint_not_proof(self) -> None:
        blocked = parse_quota_payload(
            {"primary": {"used_percent": 100.0, "resets_at": 100}},
        )
        assert blocked is not None
        ok, reason = quota_available(blocked, 99.0, now=50)
        self.assertFalse(ok)
        self.assertEqual(reason, "window-exhausted")
        ok, reason = quota_available(blocked, 99.0, now=150)
        self.assertTrue(ok)
        self.assertEqual(reason, "reset-time-passed")

    def test_tibo_early_reset_by_percent_drop(self) -> None:
        before = parse_quota_payload({"primary": {"used_percent": 100.0, "resets_at": 999999}})
        after = parse_quota_payload({"primary": {"used_percent": 8.0, "resets_at": 999999}})
        assert before and after
        ok, reason = quota_recovered(
            before,
            after,
            ready_used_percent=99.0,
            recovery_drop_percent=20.0,
            now=1,
        )
        self.assertTrue(ok)
        self.assertIn(reason, {"available", "early-reset"})


if __name__ == "__main__":
    unittest.main()
