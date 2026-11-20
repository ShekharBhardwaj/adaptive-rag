"""Admission-only token/cost charges; provider usage and billing stay untouched."""

from __future__ import annotations

import math
from decimal import Decimal, localcontext
from typing import Any

from adaptive_rag.retrieval.models import ModelCallRecord

from .pricing import PriceSchedule


class CallReservation:
    """One delegation intent, settled against whatever usage the provider reports.

    Missing components retain serialized-input-byte/full-output reservations.
    These are budget charges under the existing byte-admission assumption, not
    measured tokens, invoice amounts, or a guarantee about provider tokenizers.
    """

    def __init__(
        self,
        attempt_id: str,
        operation: str,
        identity: dict[str, Any],
        input_bytes: int,
        reserved_output: int,
        prices: PriceSchedule | None,
    ):
        self.attempt_id = attempt_id
        self.operation = operation
        self.identity = {key: identity.get(key) for key in ("base_url", "model")}
        self.reserved = {"input_tokens": input_bytes, "output_tokens": reserved_output}
        self.prices = prices
        self.call: ModelCallRecord | None = None

    def observe(self, call: ModelCallRecord | None) -> None:
        self.call = call

    def receipt(self) -> dict[str, Any]:
        actual = {
            field: getattr(self.call.usage, field) if self.call is not None else None
            for field in self.reserved
        }
        charged = {
            field: actual[field] if actual[field] is not None else self.reserved[field]
            for field in self.reserved
        }
        unknown = any(value is None for value in actual.values())
        valid = (
            self.operation in {"chat", "embedding"}
            and all(isinstance(value, str) and value.strip() for value in self.identity.values())
            and all(type(value) is int and value >= 0 for value in self.reserved.values())
            and all(type(value) is int and value >= 0 for value in charged.values())
        )
        reason = None if valid else "invalid reservation identity or token envelope"
        if self.call is not None and (
            not valid
            or self.call.operation != self.operation
            or self.call.model != self.identity["model"]
            or self.call.base_url.rstrip("/") != self.identity["base_url"].rstrip("/")
            or (
                "model" in self.call.request
                and self.call.request["model"] != self.identity["model"]
            )
        ):
            valid = False
            reason = "provider record contradicts reservation identity or operation"
        rate = (
            next(
                (
                    rate
                    for rate in self.prices.entries
                    if rate.operation == self.operation
                    and rate.model == self.identity["model"]
                    and rate.base_url == self.identity["base_url"].rstrip("/")
                ),
                None,
            )
            if self.prices is not None and valid
            else None
        )
        cost = None
        if rate is None:
            valid = False
            reason = reason or "no dated price for the reservation identity and operation"
        elif valid:
            try:
                with localcontext() as context:
                    context.prec = 50
                    amount = (
                        Decimal(charged["input_tokens"]) * Decimal(str(rate.input_usd_per_million))
                        + Decimal(charged["output_tokens"])
                        * Decimal(str(rate.output_usd_per_million))
                    ) / Decimal(1_000_000)
                cost = float(amount)
                if not math.isfinite(cost) or cost < 0:
                    raise ValueError("nonfinite reservation cost")
            except (ArithmeticError, ValueError, OverflowError):
                valid = False
                cost = None
                reason = "reservation cost is not a usable finite USD estimate"
        return {
            "attempt_id": self.attempt_id,
            "operation": self.operation,
            "identity": dict(self.identity),
            "reserved_usage": dict(self.reserved),
            "actual_usage": actual,
            "usage": charged,
            "estimated_cost_usd": cost,
            "status": "unreserved_unknown"
            if not valid
            else "reserved_unknown"
            if unknown
            else "reported",
            "reason": reason,
        }
