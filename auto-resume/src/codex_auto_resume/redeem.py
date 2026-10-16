from __future__ import annotations

from typing import Any, Protocol

from .config import AppConfig
from .quota import (
    QuotaSnapshot,
    can_redeem_credit,
    parse_quota_payload,
    weekly_needs_reset,
)
from .state import AppState

_COOLDOWN_NOTES = ("redeemed", "redeem-failed")


class QuotaClient(Protocol):
    def read_rate_limits(self, include_credits: bool = False) -> dict[str, Any]:
        ...

    def consume_reset_credit(self, credit_id: str | None = None) -> dict[str, Any]:
        ...


def try_redeem_weekly_reset(
    *,
    cfg: AppConfig,
    snapshot: QuotaSnapshot,
    state: AppState,
    now: float,
    client: QuotaClient,
) -> tuple[QuotaSnapshot, str]:
    """Use a reset credit only after confirming weekly quota is exhausted.

    The client is injected so tests can pass a fake one. Production passes the
    live app-server client; unit tests never construct that client.
    """
    ready = cfg.ready_used_percent
    need, reason = weekly_needs_reset(snapshot, ready)
    if not need:
        return snapshot, ""

    if _in_redeem_cooldown(state, now, cfg.reset_credit_cooldown_seconds):
        return snapshot, "redeem-cooldown"

    fresh = parse_quota_payload(
        client.read_rate_limits(include_credits=True),
        source="app-server",
        fetched_at=now,
    )
    if fresh is None:
        return snapshot, "redeem-reread-failed"

    need, reason = weekly_needs_reset(fresh, ready)
    if not need:
        if reason == "weekly-ok":
            state.last_reset_credit_note = "skip-tibo-already-reset"
            return fresh, state.last_reset_credit_note
        return fresh, ""

    ok, credit_reason = can_redeem_credit(fresh)
    if not ok:
        state.last_reset_credit_note = f"skip-{credit_reason}"
        return fresh, state.last_reset_credit_note

    state.last_reset_credit_at = now
    try:
        result = client.consume_reset_credit(fresh.reset_credit_id)
    except Exception as exc:
        state.last_reset_credit_note = f"redeem-failed:{exc}"
        return fresh, state.last_reset_credit_note

    outcome = str(result.get("outcome") or "reset") if isinstance(result, dict) else "reset"
    state.last_reset_credit_id = fresh.reset_credit_id or ""
    after = parse_quota_payload(
        client.read_rate_limits(include_credits=True),
        source="app-server",
        fetched_at=now,
    )
    if after is None and isinstance(result, dict):
        after = parse_quota_payload(result, source="app-server", fetched_at=now)
    if after is None:
        state.last_reset_credit_note = f"redeemed:{outcome}:reread-failed"
        return fresh, state.last_reset_credit_note
    state.last_reset_credit_note = f"redeemed:{outcome}"
    return after, state.last_reset_credit_note


def _in_redeem_cooldown(state: AppState, now: float, cooldown_seconds: float) -> bool:
    if not state.last_reset_credit_at:
        return False
    if now - state.last_reset_credit_at >= cooldown_seconds:
        return False
    note = state.last_reset_credit_note or ""
    return note.startswith(_COOLDOWN_NOTES)
