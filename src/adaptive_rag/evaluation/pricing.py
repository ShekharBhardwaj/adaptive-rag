"""Dated, user-supplied price schedules and explicit unknown-cost accounting.

No prices are fetched or guessed. Failed requests may incur cost when their
provider records contain usage; absent rates or usage remain unknown, not free.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, localcontext
from typing import Annotated, Literal, Self

from pydantic import Field, FiniteFloat, field_validator, model_validator

from adaptive_rag.models import ContentSHA256, NonBlank, ResearchModel
from adaptive_rag.retrieval.models import ModelCallRecord

Rate = Annotated[FiniteFloat, Field(strict=True, ge=0)]
Count = Annotated[int, Field(strict=True, ge=0)]


class PricingEntry(ResearchModel):
    base_url: NonBlank
    model: NonBlank
    operation: Literal["chat", "embedding"]
    input_usd_per_million: Rate
    output_usd_per_million: Rate

    @field_validator("base_url")
    @classmethod
    def normalized_endpoint(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized:
            raise ValueError("base_url must identify a nonempty endpoint")
        return normalized


class PriceSchedule(ResearchModel):
    currency: Literal["USD"] = "USD"
    as_of: date
    source: NonBlank
    entries: tuple[PricingEntry, ...]

    @model_validator(mode="after")
    def unique_entries(self) -> Self:
        identities = [(entry.base_url, entry.model, entry.operation) for entry in self.entries]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate price for the same endpoint, model, and operation")
        return self


class CostEstimate(ResearchModel):
    estimated_usd: Annotated[FiniteFloat, Field(ge=0)] | None
    known_subtotal_usd: Annotated[FiniteFloat, Field(ge=0)]
    unknown_calls: Count
    priced_calls: Count
    schedule_sha256: ContentSHA256 | None

    @model_validator(mode="after")
    def unknown_is_not_zero(self) -> Self:
        if self.unknown_calls and self.estimated_usd is not None:
            raise ValueError("a cost with unknown calls cannot have a complete estimate")
        if not self.unknown_calls and self.estimated_usd != self.known_subtotal_usd:
            raise ValueError("complete estimates must equal the known subtotal")
        return self


def schedule_sha256(schedule: PriceSchedule) -> str:
    """Canonical content identity includes the explicit date and source."""
    encoded = json.dumps(
        schedule.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def estimate_cost(calls: Sequence[ModelCallRecord], schedule: PriceSchedule | None) -> CostEstimate:
    prices = (
        {(entry.base_url, entry.model, entry.operation): entry for entry in schedule.entries}
        if schedule is not None
        else {}
    )
    unknown = priced = 0
    subtotal = Decimal(0)
    with localcontext() as context:
        context.prec = 50
        for call in calls:
            rate = prices.get((call.base_url.rstrip("/"), call.model, call.operation))
            if rate is None or call.usage.input_tokens is None or call.usage.output_tokens is None:
                unknown += 1
                continue
            amount = (
                Decimal(call.usage.input_tokens) * Decimal(str(rate.input_usd_per_million))
                + Decimal(call.usage.output_tokens) * Decimal(str(rate.output_usd_per_million))
            ) / Decimal(1_000_000)
            # An amount outside finite float representation cannot be a usable USD estimate.
            # Retain representable known costs and mark this call unknown explicitly.
            candidate = subtotal + amount
            if not math.isfinite(float(candidate)):
                unknown += 1
                continue
            subtotal = candidate
            priced += 1
    known = float(subtotal)
    return CostEstimate(
        estimated_usd=None if unknown else known,
        known_subtotal_usd=known,
        unknown_calls=unknown,
        priced_calls=priced,
        schedule_sha256=schedule_sha256(schedule) if schedule is not None else None,
    )
