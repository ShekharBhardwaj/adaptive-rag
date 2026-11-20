"""Provider-scoped pacing without changing persistent model/index identities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .pacing import RequestPacer

if TYPE_CHECKING:
    from adaptive_rag.config import ModelSettings, RequestPacingSettings


def request_pacers(settings: ModelSettings) -> tuple[RequestPacer | None, RequestPacer | None]:
    """Return embedding/chat pacers; all chat roles share the latter object.

    A common endpoint shares one gate even if key-environment names differ.
    With conflicting overrides the shared gate uses the stricter settings.
    Gates are process-local; concurrent CLI processes do not share state.
    """
    embedding = settings.request_pacing
    chat = settings.chat_request_pacing or embedding

    def create(interval: float, rpm: int | None) -> RequestPacer | None:
        if interval == 0 and rpm is None:
            return None
        return RequestPacer(min_interval_seconds=interval, max_requests_per_minute=rpm)

    def from_settings(value: RequestPacingSettings) -> RequestPacer | None:
        return create(value.min_interval_seconds, value.max_requests_per_minute)

    if settings.base_url.rstrip("/") == (settings.chat_base_url or settings.base_url).rstrip("/"):
        caps = [
            value
            for value in (embedding.max_requests_per_minute, chat.max_requests_per_minute)
            if value is not None
        ]
        shared = create(
            max(embedding.min_interval_seconds, chat.min_interval_seconds),
            min(caps) if caps else None,
        )
        return shared, shared
    return from_settings(embedding), from_settings(chat)
