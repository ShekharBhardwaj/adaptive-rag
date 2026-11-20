from datetime import date

import pytest
from pydantic import ValidationError

from adaptive_rag.evaluation.pricing import (
    PriceSchedule,
    PricingEntry,
    estimate_cost,
    schedule_sha256,
)
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage


def entry(**changes):
    return PricingEntry.model_validate(
        {
            "base_url": "https://fixture.invalid/v1",
            "model": "fixture-model",
            "operation": "chat",
            "input_usd_per_million": 2.0,
            "output_usd_per_million": 8.0,
            **changes,
        }
    )


def schedule(**changes):
    return PriceSchedule.model_validate(
        {
            "as_of": "2026-11-15",
            "source": "Synthetic unit-test rates; not current commercial prices",
            "entries": [entry()],
            **changes,
        }
    )


def call(**changes):
    return ModelCallRecord.model_validate(
        {
            "operation": "chat",
            "model": "fixture-model",
            "base_url": "https://fixture.invalid/v1",
            "request": {},
            "usage": {"input_tokens": 1_000_000, "output_tokens": 250_000},
            **changes,
        }
    )


def test_prices_are_dated_and_fully_identified():
    prices = schedule()
    result = estimate_cost([call()], prices)
    assert result.estimated_usd == 4.0
    assert result.known_subtotal_usd == 4.0
    assert result.priced_calls == 1 and result.unknown_calls == 0
    assert result.schedule_sha256 == schedule_sha256(prices)
    assert prices.as_of == date(2026, 11, 15)
    assert schedule_sha256(prices) != schedule_sha256(schedule(as_of="2026-11-14"))
    assert schedule_sha256(prices) != schedule_sha256(schedule(source="Another explicit source"))


def test_no_calls_are_zero_even_without_a_schedule():
    result = estimate_cost([], None)
    assert result.estimated_usd == result.known_subtotal_usd == 0
    assert result.unknown_calls == result.priced_calls == 0
    assert result.schedule_sha256 is None


def test_missing_rates_and_usage_remain_unknown_with_known_subtotal():
    unknown_usage = call(usage=TokenUsage(input_tokens=None, output_tokens=5))
    unknown_model = call(model="unpriced")
    result = estimate_cost([call(), unknown_usage, unknown_model], schedule())
    assert result.estimated_usd is None
    assert result.known_subtotal_usd == 4.0
    assert result.unknown_calls == 2 and result.priced_calls == 1
    missing_schedule = estimate_cost([call()], None)
    assert missing_schedule.estimated_usd is None
    assert missing_schedule.known_subtotal_usd == 0
    assert missing_schedule.unknown_calls == 1


def test_failed_requests_with_usage_can_still_cost_money():
    result = estimate_cost([call(error="HTTP error after reported billing")], schedule())
    assert result.estimated_usd == 4.0 and result.priced_calls == 1
    result = estimate_cost(
        [call(error="timeout", usage={"input_tokens": None, "output_tokens": None})], schedule()
    )
    assert result.estimated_usd is None and result.unknown_calls == 1


def test_endpoint_model_and_operation_prices_are_independent():
    prices = schedule(entries=[entry(), entry(operation="embedding", output_usd_per_million=0)])
    embedding = call(operation="embedding", usage={"input_tokens": 1_000_000, "output_tokens": 0})
    assert estimate_cost([embedding], prices).estimated_usd == 2.0
    assert (
        estimate_cost([call(base_url="https://another.invalid/v1")], prices).estimated_usd is None
    )
    assert estimate_cost([call(base_url="https://fixture.invalid/v1/")], prices).estimated_usd == 4


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf"), float("-inf"), True, "1.2"])
def test_rates_must_be_finite_nonnegative_numbers(rate):
    with pytest.raises(ValidationError):
        entry(input_usd_per_million=rate)
    with pytest.raises(ValidationError):
        entry(output_usd_per_million=rate)


def test_duplicate_ambiguous_entries_and_missing_provenance_are_rejected():
    with pytest.raises(ValidationError, match="duplicate price"):
        schedule(entries=[entry(), entry(base_url="https://fixture.invalid/v1/")])
    with pytest.raises(ValidationError):
        schedule(source=" ")
    with pytest.raises(ValidationError):
        PriceSchedule(entries=(), source="fixture")
    with pytest.raises(ValidationError):
        schedule(currency="EUR")


def test_zero_rates_are_explicit_and_still_require_known_usage():
    prices = schedule(entries=[entry(input_usd_per_million=0, output_usd_per_million=0)])
    assert estimate_cost([call()], prices).estimated_usd == 0
    assert (
        estimate_cost(
            [call(usage={"input_tokens": None, "output_tokens": 0})], prices
        ).estimated_usd
        is None
    )


def test_unrepresentable_cost_is_unknown_not_infinite_or_free():
    prices = schedule(entries=[entry(input_usd_per_million=1e308)])
    result = estimate_cost([call(usage={"input_tokens": 10**100, "output_tokens": 0})], prices)
    assert result.estimated_usd is None
    assert result.unknown_calls == 1 and result.priced_calls == 0
