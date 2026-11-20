"""Durable per-call observations and cooperative run-wide model admission.

A request event is fsynced before provider delegation. A process killed during a
request leaves that durable intent; soft interruptions additionally retain an
explicit unknown-usage observation. No rejected admission is a model attempt.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal, NoReturn, TypeVar
from uuid import uuid4

from adaptive_rag.generation.client import (
    ChatClient,
    ChatResponse,
    EmbeddingClient,
    EmbeddingResponse,
    ModelCallNotStarted,
    ModelClientError,
)
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage

from .experiment_models import RunBudget
from .pricing import PriceSchedule, estimate_cost
from .reservations import CallReservation
from .storage import RunStore

Response = TypeVar("Response", ChatResponse, EmbeddingResponse)


class CallJournal:
    def __init__(
        self,
        store: RunStore,
        *,
        budget: RunBudget,
        base_usage: Callable[[], TokenUsage],
        base_attempts: Callable[[], int],
        base_known_cost: Callable[[], float],
        base_unknown_costs: Callable[[], int],
        remaining_seconds: Callable[[], float],
        price_schedule: PriceSchedule | None,
    ):
        self.store = store
        self.budget = budget
        self.base_usage = base_usage
        self.base_attempts = base_attempts
        self.base_known_cost = base_known_cost
        self.base_unknown_costs = base_unknown_costs
        self.remaining_seconds = remaining_seconds
        self.price_schedule = price_schedule
        self._job_id: str | None = None
        self._calls: list[ModelCallRecord] = []
        self._attempts = 0
        self._unknown_attempts = 0
        self._blocked_reason: str | None = None
        self._reservations: list[CallReservation] = []

    def begin_job(self, job_id: str) -> None:
        if not isinstance(job_id, str) or not job_id.strip():
            raise ValueError("journal requires a nonempty job ID")
        self._job_id = job_id
        self._calls = []
        self._attempts = self._unknown_attempts = 0
        self._blocked_reason = None
        self._reservations = []

    @property
    def calls(self) -> tuple[ModelCallRecord, ...]:
        return tuple(call.model_copy(deep=True) for call in self._calls)

    @property
    def usage(self) -> TokenUsage:
        total = TokenUsage()
        for call in self._calls:
            total = total.add(call.usage)
        if self._unknown_attempts:
            total = total.add(TokenUsage(input_tokens=None, output_tokens=None))
        return total

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def unknown_attempts(self) -> int:
        return self._unknown_attempts

    @property
    def blocked_reason(self) -> str | None:
        return self._blocked_reason

    @property
    def budget_accounting(self) -> dict[str, Any]:
        """Current-job admission charges, explicitly separate from actual usage/cost."""
        receipts = [reservation.receipt() for reservation in self._reservations]
        costs = [receipt["estimated_cost_usd"] for receipt in receipts]
        try:
            cost = math.fsum(costs) if all(value is not None for value in costs) else None
        except (OverflowError, ValueError):
            cost = None
        return {
            "usage": {
                field: sum(receipt["usage"][field] for receipt in receipts)
                for field in ("input_tokens", "output_tokens")
            },
            "estimated_cost_usd": cost,
            "reserved_unknown_calls": sum(
                receipt["status"] == "reserved_unknown" for receipt in receipts
            ),
            "unreserved_unknown_calls": sum(
                receipt["status"] == "unreserved_unknown" for receipt in receipts
            ),
            "attempts": receipts,
        }

    def wrap_chat(self, client: ChatClient) -> ChatClient:
        return _JournalChat(self, client)

    def wrap_embedding(self, client: EmbeddingClient) -> EmbeddingClient:
        return _JournalEmbedding(self, client)

    def _event(self, event: dict[str, Any]) -> None:
        self.store.event({"at": datetime.now(UTC).isoformat(), **deepcopy(event)})

    def _deny(self, reason: str, operation: str, identity: dict[str, Any]) -> NoReturn:
        self._blocked_reason = reason
        self._event(
            {
                "event": "model_admission_rejected",
                "job_id": self._job_id,
                "operation": operation,
                "identity": deepcopy(identity),
                "reason": reason,
                "attempted": False,
            }
        )
        raise ModelCallNotStarted(reason)

    def _admit(
        self,
        operation: str,
        identity: dict[str, Any],
        *,
        timeout: float,
        input_bytes: int,
        reserved_output: int,
    ) -> float:
        if self._job_id is None:
            raise ValueError("begin_job must be called before model requests")
        if self._blocked_reason is not None:
            self._deny(self._blocked_reason, operation, identity)
        remaining = self.remaining_seconds()
        if not math.isfinite(remaining) or remaining <= 0:
            self._deny("run wall-clock budget exhausted", operation, identity)
        if not math.isfinite(timeout) or timeout <= 0:
            self._deny("model request has no positive remaining timeout", operation, identity)
        if self.base_attempts() + self._attempts >= self.budget.max_model_calls:
            self._deny("run model-call budget exhausted", operation, identity)
        reserve = getattr(self.budget, "unknown_usage_policy", "stop") == "reserve"
        if self.usage.total_tokens is None:
            self._deny(
                "current-job token usage is unknown; further requests disabled", operation, identity
            )
        accounting = self.budget_accounting if reserve else None
        usage = self.base_usage().add(
            TokenUsage.model_validate(accounting["usage"]) if reserve else self.usage
        )
        if usage.total_tokens is None:
            self._deny("run token usage is unknown; further requests disabled", operation, identity)
        if usage.total_tokens + input_bytes + reserved_output > self.budget.max_tokens:
            self._deny("run token budget cannot admit this request", operation, identity)
        cap = self.budget.max_cost_usd
        if reserve:
            projected = CallReservation(
                "admission", operation, identity, input_bytes, reserved_output, self.price_schedule
            ).receipt()
            if (
                accounting["unreserved_unknown_calls"]
                or accounting["estimated_cost_usd"] is None
                or self.base_unknown_costs()
            ):
                self._deny(
                    "run budget has unreserved unknown cost; further requests disabled",
                    operation,
                    identity,
                )
            if projected["estimated_cost_usd"] is None:
                self._deny(
                    "run cost budget has no usable finite rate for this request",
                    operation,
                    identity,
                )
            prior_cost = self.base_known_cost()
            if not math.isfinite(prior_cost) or prior_cost < 0:
                self._deny("run budget cost is nonfinite or invalid", operation, identity)
            try:
                next_cost = math.fsum(
                    (prior_cost, accounting["estimated_cost_usd"], projected["estimated_cost_usd"])
                )
            except OverflowError:
                self._deny("projected run budget cost is nonfinite", operation, identity)
            if cap is not None and next_cost > cap:
                self._deny(
                    "run estimated-cost budget cannot admit the projected request charge",
                    operation,
                    identity,
                )
            return min(timeout, remaining)
        if cap is not None:
            cost = estimate_cost(self._calls, self.price_schedule)
            if self.base_unknown_costs() or cost.unknown_calls or self._unknown_attempts:
                self._deny(
                    "run estimated cost is unknown; further requests disabled", operation, identity
                )
            if self.base_known_cost() + cost.known_subtotal_usd >= cap:
                self._deny("run estimated-cost budget exhausted", operation, identity)
            if self.price_schedule is None or not any(
                entry.base_url == identity.get("base_url", "").rstrip("/")
                and entry.model == identity.get("model")
                and entry.operation == operation
                for entry in self.price_schedule.entries
            ):
                self._deny("run cost budget has no rate for this request", operation, identity)
        return min(timeout, remaining)

    def _invoke(
        self,
        operation: Literal["chat", "embedding"],
        identity: dict[str, Any],
        request: dict[str, Any],
        delegate: Callable[[float], Response],
        *,
        timeout: float,
        reserved_output: int = 0,
    ) -> Response:
        stage_deadline = time.monotonic() + timeout
        request = deepcopy(request)
        input_bytes = len(
            json.dumps(request, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
        )
        timeout = self._admit(
            operation,
            identity,
            timeout=timeout,
            input_bytes=input_bytes,
            reserved_output=reserved_output,
        )
        event = {
            "job_id": self._job_id,
            "attempt_id": uuid4().hex,
            "operation": operation,
            "identity": deepcopy(identity),
        }
        reservation = CallReservation(
            event["attempt_id"],
            operation,
            identity,
            input_bytes,
            reserved_output,
            self.price_schedule,
        )
        # Failure here must prevent delegation: no request may outlive its durable intent.
        self._event(
            {
                "event": "model_request",
                **event,
                "request": request,
                "timeout_seconds": timeout,
                "budget_reservation": reservation.receipt(),
            }
        )
        # Durable intent itself can take time; clamp again immediately before delegation.
        remaining = self.remaining_seconds()
        if not math.isfinite(remaining) or remaining <= 0:
            self._deny("run wall-clock budget exhausted before delegation", operation, identity)
        stage_remaining = stage_deadline - time.monotonic()
        if not math.isfinite(stage_remaining) or stage_remaining <= 0:
            self._deny("stage wall-clock budget exhausted before delegation", operation, identity)
        timeout = min(timeout, remaining, stage_remaining)
        self._attempts += 1
        self._reservations.append(reservation)
        try:
            response = delegate(timeout)
        except ModelCallNotStarted as exc:
            # A wrapped adapter can perform a more specific admission check too.
            self._attempts -= 1
            self._reservations.pop()
            self._deny(str(exc), operation, identity)
        except BaseException as exc:
            interrupted = isinstance(exc, (KeyboardInterrupt, SystemExit))
            if interrupted and getattr(exc, "_adaptive_rag_not_started", False) is True:
                # HTTP pacing was interrupted before acquiring a provider slot.
                # Preserve cancellation without inventing delegated usage/cost.
                self._attempts -= 1
                self._reservations.pop()
                self._event(
                    {
                        "event": "model_admission_cancelled",
                        **event,
                        "exception_type": type(exc).__name__,
                        "error": str(exc),
                        "attempted": False,
                        "unknown_usage": False,
                        "usage": TokenUsage().model_dump(mode="json"),
                        "interrupted": True,
                    }
                )
                raise
            call = exc.record if isinstance(exc, ModelClientError) else None
            if isinstance(call, ModelCallRecord):
                self._calls.append(call.model_copy(deep=True))
            else:
                call = None
                self._unknown_attempts += 1
            reservation.observe(self._calls[-1] if call is not None else None)
            self._event(
                {
                    "event": "model_error",
                    **event,
                    "call": call.model_dump(mode="json") if call is not None else None,
                    "exception_type": type(exc).__name__,
                    "error": str(exc),
                    "unknown_usage": call is None or call.usage.total_tokens is None,
                    "interrupted": interrupted,
                    "budget_receipt": reservation.receipt(),
                }
            )
            if interrupted:
                self._event({"event": "model_interrupted", **event, "unknown_usage": True})
            raise
        call = getattr(response, "call", None)
        if not isinstance(call, ModelCallRecord):
            self._unknown_attempts += 1
            self._event(
                {
                    "event": "model_error",
                    **event,
                    "call": None,
                    "error": "provider returned no valid model call record",
                    "unknown_usage": True,
                    "interrupted": False,
                    "budget_receipt": reservation.receipt(),
                }
            )
            raise ModelClientError("provider returned no valid model call record")
        self._calls.append(call.model_copy(deep=True))
        reservation.observe(self._calls[-1])
        self._event(
            {
                "event": "model_result",
                **event,
                "call": call.model_dump(mode="json"),
                "budget_receipt": reservation.receipt(),
            }
        )
        return response


class _JournalChat:
    def __init__(self, journal: CallJournal, client: ChatClient):
        self.journal, self.client = journal, client

    @property
    def identity(self) -> dict[str, Any]:
        return deepcopy(self.client.identity)

    def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        max_output_tokens: int,
        temperature: float | None,
        timeout: float,
    ) -> ChatResponse:
        messages, tools = deepcopy(messages), deepcopy(tools)
        parameter = getattr(self.client, "token_parameter", "max_tokens")
        request = {
            "model": self.identity["model"],
            "messages": messages,
            parameter: max_output_tokens,
        }
        if temperature is not None:
            request["temperature"] = temperature
        if tools:
            request.update(tools=tools, tool_choice="auto")
        return self.journal._invoke(
            "chat",
            self.identity,
            request,
            lambda admitted_timeout: self.client.complete(
                deepcopy(messages),
                deepcopy(tools),
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                timeout=admitted_timeout,
            ),
            timeout=timeout,
            reserved_output=max_output_tokens,
        )


class _JournalEmbedding:
    def __init__(self, journal: CallJournal, client: EmbeddingClient):
        self.journal, self.client = journal, client

    @property
    def identity(self) -> dict[str, Any]:
        return deepcopy(self.client.identity)

    def embed(self, texts: list[str], *, timeout: float) -> EmbeddingResponse:
        texts = deepcopy(texts)
        request = {"model": self.identity["model"], "input": texts, "encoding_format": "float"}
        if self.identity.get("dimensions") is not None:
            request["dimensions"] = self.identity["dimensions"]
        return self.journal._invoke(
            "embedding",
            self.identity,
            request,
            lambda admitted_timeout: self.client.embed(deepcopy(texts), timeout=admitted_timeout),
            timeout=timeout,
        )
