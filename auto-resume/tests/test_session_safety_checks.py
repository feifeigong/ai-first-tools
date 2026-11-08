"""The checks shipped inside frozen apps must also reject broken policies."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from codex_auto_resume import daemon, sessions
from codex_auto_resume.session_safety_checks import run


class FrozenSessionSafetyTests(unittest.TestCase):
    def test_shared_frozen_checks_pass_without_real_process_or_network(self):
        with patch("subprocess.Popen", side_effect=AssertionError("Real process forbidden")), \
                patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")):
            self.assertEqual(run(), dict.fromkeys(("mainSessionIdentityFiltering", "unknownSessionIdentityRejected",
                                                  "continuedSessionBlockedAtSubmission"), True))

    def test_gate_fails_if_subagents_are_accepted_as_main(self):
        with patch.object(sessions, "_is_main_session", return_value=True):
            with self.assertRaisesRegex(AssertionError, "safety regression"):
                run()

    def test_gate_fails_if_unknown_identity_is_allowed(self):
        original = sessions._is_main_session

        def permissive(meta):
            return original(meta) or meta.get("source") in (None, "unknown")

        with patch.object(sessions, "_is_main_session", side_effect=permissive):
            with self.assertRaisesRegex(AssertionError, "safety regression"):
                run()

    def test_gate_fails_if_final_waiting_state_check_is_bypassed(self):
        with patch.object(daemon, "validate_waiting_session", return_value=True):
            with self.assertRaisesRegex(AssertionError, "safety regression"):
                run()


if __name__ == "__main__":
    unittest.main()
