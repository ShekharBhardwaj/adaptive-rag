"""Small synchronous Chat Completions/embeddings adapter; no automatic retries."""

import copy
import hashlib
import json
import math
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import FiniteFloat

from adaptive_rag.models import ResearchModel
from adaptive_rag.retrieval.models import ModelCallRecord, TokenUsage

if TYPE_CHECKING:
    from .pacing import RequestPacer


class ModelClientError(ValueError):
    def __init__(self, message: str, record: ModelCallRecord | None = None):
        super().__init__(message)
        self.record = record


class ModelCallNotStarted(ModelClientError):
    """Admission rejected before provider delegation; no usage was incurred."""

    attempted = False


class EmbeddingResponse(ResearchModel):
    vectors: tuple[tuple[FiniteFloat, ...], ...]
    call: ModelCallRecord


class ChatResponse(ResearchModel):
    message: dict[str, Any]
    call: ModelCallRecord


class EmbeddingClient(Protocol):
    @property
    def identity(self) -> dict[str, Any]: ...

    def embed(self, texts: list[str], *, timeout: float) -> EmbeddingResponse: ...


class ChatClient(Protocol):
    @property
    def identity(self) -> dict[str, Any]: ...

    def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        max_output_tokens: int,
        temperature: float | None,
        timeout: float,
    ) -> ChatResponse: ...


def _token_count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonstandard JSON numeric constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("provider response contains duplicate JSON keys")
        result[key] = value
    return result


def _usage(body: dict, operation: str) -> TokenUsage:
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return TokenUsage(input_tokens=None, output_tokens=None)
    incoming = _token_count(usage.get("prompt_tokens", usage.get("input_tokens")))
    if operation == "embedding":
        if incoming is None:
            incoming = _token_count(usage.get("total_tokens"))
        # An embeddings operation has no generated output tokens.
        return TokenUsage(input_tokens=incoming, output_tokens=0)
    return TokenUsage(
        input_tokens=incoming,
        output_tokens=_token_count(usage.get("completion_tokens", usage.get("output_tokens"))),
    )


class _JSONClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        pacer: "RequestPacer | None" = None,
    ):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "base_url must be an HTTP(S) endpoint without credentials, query or fragment"
            )
        if not isinstance(model, str) or not model.strip():
            raise ValueError("a provider model identifier is required")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self._transport = transport
        self.pacer = pacer

    @property
    def identity(self) -> dict[str, Any]:
        return {"base_url": self.base_url, "model": self.model}

    def _post(
        self, operation: Literal["embedding", "chat"], path: str, payload: dict, timeout: float
    ) -> tuple[dict, ModelCallRecord]:
        with self._request_slot(timeout) as remaining:
            return self._post_admitted(operation, path, payload, remaining)

    @contextmanager
    def _request_slot(self, timeout: float):
        if self.pacer is None:
            yield timeout
            return
        acquired = False
        try:
            with self.pacer.slot(timeout) as remaining:
                acquired = True
                yield remaining
        except (KeyboardInterrupt, SystemExit) as exc:
            if not acquired:
                # The journal must preserve cancellation without inventing a call.
                exc._adaptive_rag_not_started = True
            raise

    def _post_admitted(
        self, operation: Literal["embedding", "chat"], path: str, payload: dict, timeout: float
    ) -> tuple[dict, ModelCallRecord]:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ModelClientError("model call requires positive remaining execution time")
        started_at = datetime.now(UTC)
        started = time.monotonic()
        payload = copy.deepcopy(payload)
        body: dict = {}
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        failure: str | None = None
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "POST", self.base_url + path, headers=headers, json=payload
                ) as response:
                    if self.pacer is not None:
                        self.pacer.observe_response(response.status_code, response.headers)
                    parts = []
                    size = 0
                    for part in response.iter_bytes():
                        size += len(part)
                        if size > 16 * 1024 * 1024:
                            raise ValueError("provider response exceeds 16 MiB")
                        if time.monotonic() - started > timeout:
                            raise ValueError("provider exceeded the execution deadline")
                        parts.append(part)
                    raw = b"".join(parts)
                    try:
                        parsed = json.loads(
                            raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object
                        )
                    except (ValueError, UnicodeError, RecursionError) as exc:
                        body = {
                            "body_sha256": hashlib.sha256(raw).hexdigest(),
                            "body_bytes": len(raw),
                            "raw_body": raw.decode("utf-8", errors="replace"),
                        }
                        raise ValueError("provider response is not valid JSON") from exc
                    body = parsed if isinstance(parsed, dict) else {"raw_response": parsed}
                    if response.status_code >= 300:
                        raise ValueError(f"provider returned HTTP {response.status_code}")
                    if not isinstance(parsed, dict):
                        raise ValueError("provider response must be a JSON object")
                    if time.monotonic() - started > timeout:
                        raise ValueError("provider exceeded the execution deadline")
        except (httpx.HTTPError, ValueError) as exc:
            # Exception messages deliberately exclude request headers and URLs.
            failure = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        record = ModelCallRecord(
            operation=operation,
            model=self.model,
            base_url=self.base_url,
            started_at=started_at,
            request=payload,
            response=body,
            usage=_usage(body, operation),
            elapsed_seconds=time.monotonic() - started,
            error=failure,
        )
        if failure is not None:
            raise ModelClientError(failure, record)
        return body, record

    @staticmethod
    def _invalid(message: str, record: ModelCallRecord) -> ModelClientError:
        return ModelClientError(message, record.model_copy(update={"error": message}))


class OpenAIEmbeddingClient(_JSONClient):
    def __init__(self, *, dimensions: int | None = None, **kwargs):
        super().__init__(**kwargs)
        if dimensions is not None and (type(dimensions) is not int or dimensions < 1):
            raise ValueError("embedding dimensions must be positive")
        self.dimensions = dimensions

    @property
    def identity(self) -> dict[str, Any]:
        return {**super().identity, "dimensions": self.dimensions}

    def embed(self, texts: list[str], *, timeout: float) -> EmbeddingResponse:
        if not texts or any(not isinstance(text, str) or not text for text in texts):
            raise ModelClientError("embedding inputs must contain nonempty strings")
        payload = {"model": self.model, "input": texts, "encoding_format": "float"}
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions
        body, record = self._post("embedding", "/embeddings", payload, timeout)
        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise self._invalid("embedding response count differs from input count", record)
        indexed = {}
        for item in data:
            if not isinstance(item, dict):
                raise self._invalid("embedding row must be an object", record)
            index, vector = item.get("index"), item.get("embedding")
            if (
                type(index) is not int
                or not 0 <= index < len(texts)
                or index in indexed
                or not isinstance(vector, list)
                or not vector
                or any(type(v) not in (int, float) for v in vector)
            ):
                raise self._invalid("invalid embedding index or nonfinite vector", record)
            try:
                converted = tuple(float(v) for v in vector)
            except (OverflowError, ValueError) as exc:
                raise self._invalid("embedding value exceeds floating-point range", record) from exc
            if not all(math.isfinite(v) for v in converted):
                raise self._invalid("embedding contains a nonfinite value", record)
            indexed[index] = converted
        vectors = tuple(indexed[i] for i in range(len(texts)))
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors):
            raise self._invalid("embedding dimensions differ between rows", record)
        if self.dimensions is not None and dimension != self.dimensions:
            raise self._invalid("provider returned unexpected embedding dimensions", record)
        return EmbeddingResponse(vectors=vectors, call=record)


class OpenAIChatClient(_JSONClient):
    def __init__(
        self,
        *,
        token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens",
        **kwargs,
    ):
        super().__init__(**kwargs)
        if token_parameter not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("unsupported chat token cap parameter")
        self.token_parameter = token_parameter

    def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        max_output_tokens: int,
        temperature: float | None,
        timeout: float,
    ) -> ChatResponse:
        if type(max_output_tokens) is not int or max_output_tokens < 1:
            raise ModelClientError("max_output_tokens must be positive")
        payload = {
            "model": self.model,
            "messages": messages,
            self.token_parameter: max_output_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload.update(tools=tools, tool_choice="auto")
        body, record = self._post("chat", "/chat/completions", payload, timeout)
        choices = body.get("choices")
        if (
            not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
            or not isinstance(choices[0].get("message"), dict)
        ):
            raise self._invalid("expected exactly one assistant response", record)
        message = choices[0]["message"]
        if message.get("role") != "assistant":
            raise self._invalid("provider returned a non-assistant message", record)
        return ChatResponse(message=copy.deepcopy(message), call=record)
