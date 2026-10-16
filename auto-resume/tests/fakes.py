from __future__ import annotations

from typing import Any


class FakeQuotaClient:
    """In-memory Codex quota API. consume() never talks to the network."""

    def __init__(
        self,
        *,
        primary_used: float = 100.0,
        weekly_used: float = 31.0,
        credits: int = 1,
        credit_id: str = "sim-credit-1",
        allow_consume: bool = False,
        tibo_on_credit_read: bool = False,
        consume_error: str | None = None,
    ) -> None:
        self.primary_used = primary_used
        self.weekly_used = weekly_used
        self.credits = credits
        self.credit_id = credit_id
        self.allow_consume = allow_consume
        self.tibo_on_credit_read = tibo_on_credit_read
        self.consume_error = consume_error
        self.read_calls: list[bool] = []
        self.consume_calls: list[str | None] = []

    def read_rate_limits(self, include_credits: bool = False) -> dict[str, Any]:
        self.read_calls.append(include_credits)
        if include_credits and self.tibo_on_credit_read:
            self.primary_used = 4.0
            self.weekly_used = 4.0
        payload: dict[str, Any] = {
            "ordinaryUsageAllowed": self.primary_used < 99 and self.weekly_used < 99,
            "rateLimits": {
                "primary": {
                    "usedPercent": self.primary_used,
                    "windowDurationMins": 300,
                    "resetsAt": 9_999_999_999,
                },
                "secondary": {
                    "usedPercent": self.weekly_used,
                    "windowDurationMins": 10080,
                    "resetsAt": 9_999_999_999,
                },
                "planType": "plus",
            },
        }
        if include_credits:
            rows = []
            if self.credits > 0:
                rows.append({"id": self.credit_id, "status": "available"})
            payload["rateLimitResetCredits"] = {
                "availableCount": self.credits,
                "credits": rows,
            }
        return payload

    def consume_reset_credit(self, credit_id: str | None = None) -> dict[str, Any]:
        self.consume_calls.append(credit_id)
        if not self.allow_consume:
            raise AssertionError("模拟测试禁止扣卡，但代码仍调用了 consume")
        if self.consume_error:
            raise RuntimeError(self.consume_error)
        if self.credits <= 0:
            raise RuntimeError("no reset credits")
        self.credits -= 1
        self.primary_used = 0.0
        self.weekly_used = 0.0
        return {"outcome": "reset"}
