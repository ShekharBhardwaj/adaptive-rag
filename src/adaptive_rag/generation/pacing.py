"""Shared request admission and provider cooldowns; failed requests are never retried."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .client import ModelCallNotStarted

MAX_RETRY_AFTER_SECONDS = 3600.0


def _retry_after_delay(value: str | None) -> float | None:
    if not isinstance(value, str) or len(value) > 128:
        return None
    try:
        return float(value.strip())
    except ValueError:
        try:
            date = parsedate_to_datetime(value.strip())
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            return date.timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            return None


class RequestPacer:
    """Serialize calls, space their starts, and enforce a rolling 60-second cap.

    ``clock`` is monotonic and ``sleep`` advances that clock in deterministic
    tests. Waiting for another in-flight call, pacing and cooldowns all consume
    the supplied timeout. A yielded slot counts once even when its body raises.
    Retry-After is honored for HTTP 402/429/503, capped at one hour. Exhausted
    Anthropic remaining/reset header pairs can impose the same cooldown on any
    response. Header timestamps use the wall clock; no request is retried.
    """

    def __init__(
        self,
        min_interval_seconds: float = 0.0,
        max_requests_per_minute: int | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        if (
            type(min_interval_seconds) not in (int, float)
            or not math.isfinite(min_interval_seconds)
            or min_interval_seconds < 0
        ):
            raise ValueError("minimum request interval must be finite and nonnegative")
        if max_requests_per_minute is not None and (
            type(max_requests_per_minute) is not int or max_requests_per_minute < 1
        ):
            raise ValueError("requests per minute must be a positive integer or None")
        self.min_interval_seconds = float(min_interval_seconds)
        self.max_requests_per_minute = max_requests_per_minute
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._in_flight = threading.Lock()
        self._state = threading.Lock()
        self._starts: deque[float] = deque()
        self._last_start: float | None = None
        self._cooldown_until = 0.0

    @contextmanager
    def slot(self, timeout: float) -> Iterator[float]:
        """Yield positive remaining timeout or reject before consuming a slot."""
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ModelCallNotStarted("request pacing requires a positive finite timeout")
        deadline = self._clock() + timeout
        if not self._in_flight.acquire(timeout=timeout):
            raise ModelCallNotStarted("request deadline exhausted waiting for an in-flight call")
        try:
            while True:
                with self._state:
                    now = self._clock()
                    remaining = deadline - now
                    while self._starts and self._starts[0] <= now - 60.0:
                        self._starts.popleft()
                    ready = self._cooldown_until
                    if self._last_start is not None:
                        ready = max(ready, self._last_start + self.min_interval_seconds)
                    if (
                        self.max_requests_per_minute is not None
                        and len(self._starts) >= self.max_requests_per_minute
                    ):
                        ready = max(ready, self._starts[0] + 60.0)
                    wait = max(0.0, ready - now)
                    if remaining <= 0 or wait >= remaining:
                        raise ModelCallNotStarted(
                            "request deadline cannot admit the required pacing/cooldown wait"
                        )
                    if wait == 0:
                        self._last_start = now
                        if self.max_requests_per_minute is not None:
                            self._starts.append(now)
                        break
                self._sleep(wait)
            yield remaining
        finally:
            self._in_flight.release()

    def observe_response(self, status_code: int, headers: Mapping[str, str]) -> None:
        """Apply explicit bounded server cooldowns to later, independent calls."""
        normalized = {key.casefold(): value for key, value in headers.items()}
        delays = []
        if status_code in (402, 429, 503):
            delay = _retry_after_delay(normalized.get("retry-after"))
            if delay is not None:
                delays.append(delay)
        for name in ("requests", "tokens", "input-tokens", "output-tokens"):
            prefix = f"anthropic-ratelimit-{name}"
            remaining = normalized.get(prefix + "-remaining")
            reset = normalized.get(prefix + "-reset")
            if (
                not isinstance(remaining, str)
                or not isinstance(reset, str)
                or len(remaining) > 128
                or len(reset) > 128
            ):
                continue
            try:
                if float(remaining.strip()) != 0 or "T" not in reset:
                    continue
                date = datetime.fromisoformat(reset.strip())
                if date.tzinfo is not None:
                    delays.append(date.timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                continue
        delays = [delay for delay in delays if math.isfinite(delay) and delay > 0]
        if not delays:
            return
        delay = min(max(delays), MAX_RETRY_AFTER_SECONDS)
        with self._state:
            self._cooldown_until = max(self._cooldown_until, self._clock() + delay)
