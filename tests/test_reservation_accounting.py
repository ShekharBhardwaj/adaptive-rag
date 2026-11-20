"""Unknown provider usage remains unknown while opt-in admission uses receipts."""

import json
from types import SimpleNamespace

import pytest

from adaptive_rag.evaluation.experiment_models import RunBudget
from adaptive_rag.evaluation.journal import CallJournal
from adaptive_rag.evaluation.pricing import PriceSchedule, PricingEntry, estimate_cost
from adaptive_rag.generation.client import ModelCallNotStarted, ModelClientError
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage


class Store:
    def __init__(self):
        self.events = []

    def event(self, event):
        self.events.append(json.loads(json.dumps(event, allow_nan=False)))


def prices(rate=2.0):
    return PriceSchedule(
        as_of="2026-11-17",
        source="Synthetic test prices; not provider rates",
        entries=(
            PricingEntry(
                base_url="https://fixture.invalid/v1",
                model="fixture",
                operation="chat",
                input_usd_per_million=rate,
                output_usd_per_million=5.0,
            ),
        ),
    )


class Client:
    identity = {"base_url": "https://fixture.invalid/v1", "model": "fixture"}

    def __init__(self, usage=None, *, error=None, model="fixture"):
        self.usage = usage if usage is not None else TokenUsage(input_tokens=10, output_tokens=2)
        self.error, self.model, self.requests = error, model, 0

    def complete(self, messages, tools, **kwargs):
        self.requests += 1
        call = ModelCallRecord(
            operation="chat",
            model=self.model,
            base_url=self.identity["base_url"],
            request={"model": self.model},
            usage=self.usage,
        )
        if self.error == "recorded":
            raise ModelClientError("Synthetic timeout", call)
        if isinstance(self.error, BaseException):
            raise self.error
        return SimpleNamespace(call=call, message={"role": "assistant", "content": "synthetic"})


def journal(*, policy="reserve", schedule=True, **state_changes):
    state = {
        "usage": TokenUsage(),
        "attempts": 0,
        "cost": 0.0,
        "unknown": 0,
        "seconds": 100.0,
        **state_changes,
    }
    result = CallJournal(
        Store(),
        budget=RunBudget(max_cost_usd=10, unknown_usage_policy=policy),
        base_usage=lambda: state["usage"],
        base_attempts=lambda: state["attempts"],
        base_known_cost=lambda: state["cost"],
        base_unknown_costs=lambda: state["unknown"],
        remaining_seconds=lambda: state["seconds"],
        price_schedule=prices() if schedule else None,
    )
    result.begin_job("synthetic-job")
    return result, state


def complete(journal, client):
    return journal.wrap_chat(client).complete(
        [{"role": "user", "content": "synthetic prompt"}],
        [],
        max_output_tokens=16,
        temperature=0.0,
        timeout=30,
    )


@pytest.mark.parametrize("policy", ["stop", "reserve"])
def test_receipts_exist_in_both_modes_and_known_usage_is_authoritative(policy):
    ledger, _ = journal(policy=policy)
    response = complete(ledger, Client(usage=TokenUsage(input_tokens=1000, output_tokens=20)))
    accounting = ledger.budget_accounting
    assert accounting["usage"] == {"input_tokens": 1000, "output_tokens": 20}
    assert accounting["estimated_cost_usd"] == pytest.approx(0.0021)
    assert accounting["reserved_unknown_calls"] == accounting["unreserved_unknown_calls"] == 0
    assert ledger.usage == response.call.usage and ledger.calls == (response.call,)
    assert accounting["attempts"][0]["status"] == "reported"
    assert ledger.store.events[0]["budget_reservation"]["actual_usage"] == {
        "input_tokens": None,
        "output_tokens": None,
    }


@pytest.mark.parametrize(
    "usage",
    [
        TokenUsage(input_tokens=None, output_tokens=None),
        TokenUsage(input_tokens=7, output_tokens=None),
        TokenUsage(input_tokens=None, output_tokens=0),
    ],
)
def test_missing_components_reserve_without_fabricating_actual_usage_or_cost(usage):
    ledger, _ = journal()
    original = Client(usage, error="recorded")
    with pytest.raises(ModelClientError):
        complete(ledger, original)
    receipt = ledger.budget_accounting["attempts"][0]
    request = ledger.store.events[0]["request"]
    input_bytes = len(
        json.dumps(request, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    )
    assert receipt["reserved_usage"] == {"input_tokens": input_bytes, "output_tokens": 16}
    assert receipt["actual_usage"] == usage.model_dump(mode="json")
    assert receipt["usage"] == {
        "input_tokens": usage.input_tokens if usage.input_tokens is not None else input_bytes,
        "output_tokens": usage.output_tokens if usage.output_tokens is not None else 16,
    }
    assert ledger.usage == usage
    assert estimate_cost(ledger.calls, prices()).estimated_usd is None
    assert ledger.budget_accounting["reserved_unknown_calls"] == 1
    assert ledger.budget_accounting["unreserved_unknown_calls"] == 0
    assert receipt["estimated_cost_usd"] is not None
    with pytest.raises(ModelCallNotStarted, match="current-job.*unknown"):
        complete(ledger, original)
    assert original.requests == ledger.attempts == 1


def test_recordless_failure_keeps_envelope_and_next_job_uses_finite_callbacks():
    ledger, state = journal()
    with pytest.raises(RuntimeError):
        complete(ledger, Client(error=RuntimeError("Synthetic failure without provider record")))
    accounting = ledger.budget_accounting
    assert accounting["reserved_unknown_calls"] == 1
    assert ledger.calls == () and ledger.unknown_attempts == ledger.attempts == 1
    assert ledger.usage.total_tokens is None
    state.update(
        usage=TokenUsage.model_validate(accounting["usage"]),
        attempts=ledger.attempts,
        cost=accounting["estimated_cost_usd"],
        unknown=accounting["unreserved_unknown_calls"],
    )
    ledger.begin_job("following-synthetic-job")
    complete(ledger, Client())
    assert ledger.attempts == 1 and ledger.budget_accounting["reserved_unknown_calls"] == 0


def test_projected_request_crossing_ten_dollar_cap_is_denied_before_any_attempt():
    ledger, _ = journal(cost=9.99999)
    client = Client()
    with pytest.raises(ModelCallNotStarted, match="projected"):
        complete(ledger, client)
    assert client.requests == ledger.attempts == 0
    assert ledger.calls == () and ledger.budget_accounting["attempts"] == []
    assert ledger.budget_accounting["usage"] == {"input_tokens": 0, "output_tokens": 0}


@pytest.mark.parametrize("cancel", [False, True])
def test_pre_network_rejection_or_marked_cancellation_removes_reservation(cancel):
    ledger, _ = journal()
    exception = (
        KeyboardInterrupt("Synthetic pacing cancellation")
        if cancel
        else ModelCallNotStarted("Synthetic pacing denial")
    )
    if cancel:
        exception._adaptive_rag_not_started = True
    with pytest.raises(type(exception)):
        complete(ledger, Client(error=exception))
    assert ledger.attempts == ledger.unknown_attempts == 0
    assert ledger.budget_accounting["attempts"] == []
    assert ledger.budget_accounting["estimated_cost_usd"] == 0
    assert ledger.usage.total_tokens == 0


def test_missing_price_is_unreserved_in_default_ledger_and_blocks_opt_in_admission():
    ledger, _ = journal(policy="stop", schedule=False)
    ledger.budget = ledger.budget.model_copy(update={"max_cost_usd": None})
    complete(ledger, Client(TokenUsage(input_tokens=None, output_tokens=0)))
    assert ledger.budget_accounting["estimated_cost_usd"] is None
    assert ledger.budget_accounting["unreserved_unknown_calls"] == 1
    opted_in, _ = journal(schedule=False)
    client = Client()
    with pytest.raises(ModelCallNotStarted, match="rate"):
        complete(opted_in, client)
    assert client.requests == opted_in.attempts == 0


def test_contradictory_record_identity_is_unreserved_and_fails_closed():
    ledger, _ = journal()
    complete(ledger, Client(model="different-provider-model"))
    assert ledger.budget_accounting["estimated_cost_usd"] is None
    assert ledger.budget_accounting["unreserved_unknown_calls"] == 1
    assert ledger.calls[0].model == "different-provider-model"
    with pytest.raises(ModelCallNotStarted, match="unreserved"):
        complete(ledger, Client())
    assert ledger.attempts == 1


@pytest.mark.parametrize("prior_cost", [float("nan"), float("inf"), -1.0])
def test_nonfinite_or_invalid_cumulative_budget_cost_is_rejected(prior_cost):
    ledger, _ = journal(cost=prior_cost)
    with pytest.raises(ModelCallNotStarted, match="invalid|nonfinite"):
        complete(ledger, Client())
    assert ledger.attempts == 0


def test_unrepresentable_rate_charge_is_unreserved_and_rejected_before_network():
    ledger, _ = journal()
    schedule = prices()
    # Deliberately bypass the price model solely to exercise a corrupt injected schedule.
    invalid_rate = schedule.entries[0].model_copy(update={"input_usd_per_million": float("inf")})
    ledger.price_schedule = schedule.model_copy(update={"entries": (invalid_rate,)})
    client = Client()
    with pytest.raises(ModelCallNotStarted, match="finite"):
        complete(ledger, client)
    assert client.requests == ledger.attempts == 0
