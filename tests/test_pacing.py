"""Deterministic pacing checks use fake clocks and make no provider requests."""

from datetime import UTC, datetime
from email.utils import format_datetime
from threading import Event, Thread, current_thread

import pytest

from adaptive_rag.generation import pacing
from adaptive_rag.generation.client import ModelCallNotStarted
from adaptive_rag.generation.pacing import MAX_RETRY_AFTER_SECONDS, RequestPacer


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


def pacer(clock, **kwargs):
    return RequestPacer(clock=clock, sleep=clock.sleep, **kwargs)


def test_first_call_immediate_then_start_interval_consumes_remaining_timeout():
    clock = Clock()
    limited = pacer(clock, min_interval_seconds=2)
    with limited.slot(10) as remaining:
        assert remaining == 10
        clock.now += 0.5
    with limited.slot(10) as remaining:
        assert clock.now == 2 and remaining == 8.5
    assert clock.waits == [1.5]


def test_rolling_request_cap_expires_at_exact_sixty_second_boundary():
    clock = Clock()
    limited = pacer(clock, max_requests_per_minute=2)
    with limited.slot(70):
        pass
    clock.now = 1
    with limited.slot(70):
        pass
    with limited.slot(70) as remaining:
        assert clock.now == 60 and remaining == 11
    with limited.slot(70):
        assert clock.now == 61
    assert clock.waits == [59, 1]


def test_rejected_wait_neither_sleeps_nor_consumes_a_request_slot():
    clock = Clock()
    limited = pacer(clock, max_requests_per_minute=1)
    with limited.slot(1):
        pass
    with pytest.raises(ModelCallNotStarted):
        with limited.slot(60):
            pytest.fail("deadline rejection must precede provider delegation")
    assert clock.waits == []
    clock.now = 60
    with limited.slot(1) as remaining:
        assert remaining == 1


def test_interval_and_cap_take_longest_required_wait():
    clock = Clock()
    limited = pacer(clock, min_interval_seconds=70, max_requests_per_minute=1)
    with limited.slot(1):
        pass
    with limited.slot(80) as remaining:
        assert clock.now == 70 and remaining == 10
    assert clock.waits == [70]


def test_body_exception_releases_lock_but_preserves_consumed_slot():
    clock = Clock()
    limited = pacer(clock, min_interval_seconds=2)
    with pytest.raises(RuntimeError):
        with limited.slot(1):
            raise RuntimeError("synthetic provider failure")
    with limited.slot(3) as remaining:
        assert clock.now == 2 and remaining == 1


def test_interrupted_wait_releases_lock_and_does_not_admit_request():
    clock = Clock()
    limited = pacer(clock, min_interval_seconds=2)
    with limited.slot(1):
        pass

    def interrupted(seconds):
        raise KeyboardInterrupt("synthetic interrupted wait")

    limited._sleep = interrupted
    with pytest.raises(KeyboardInterrupt):
        with limited.slot(3):
            pytest.fail("an interrupted wait cannot admit a request")
    limited._sleep = clock.sleep
    clock.now = 2
    with limited.slot(1):
        pass
    assert clock.waits == []


def test_sleep_overshoot_rejects_without_admitting_a_request():
    clock = Clock()
    limited = pacer(clock, min_interval_seconds=2)
    with limited.slot(1):
        pass
    limited._sleep = lambda seconds: setattr(clock, "now", clock.now + seconds + 10)
    with pytest.raises(ModelCallNotStarted):
        with limited.slot(3):
            pytest.fail("overslept deadline cannot admit a request")
    limited._sleep = clock.sleep
    with limited.slot(1):
        pass


@pytest.mark.parametrize("status", [402, 429, 503])
def test_numeric_retry_after_cools_later_calls_without_retry(status):
    clock = Clock()
    limited = pacer(clock)
    with limited.slot(1):
        limited.observe_response(status, {"Retry-After": "3.5"})
    assert clock.now == 0 and clock.waits == []
    with limited.slot(5) as remaining:
        assert clock.now == 3.5 and remaining == 1.5


def test_retry_after_http_date_uses_wall_clock_and_cannot_shorten_cooldown(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(pacing.time, "time", lambda: 1_000_000.0)
    limited = pacer(clock)
    date = format_datetime(datetime.fromtimestamp(1_000_010, UTC), usegmt=True)
    limited.observe_response(503, {"retry-after": date})
    limited.observe_response(429, {"retry-after": "2"})
    with limited.slot(11) as remaining:
        assert clock.now == 10 and remaining == 1


@pytest.mark.parametrize("value", ["bad", "NaN", "inf", "-1", "0", "", "x" * 129])
def test_invalid_retry_after_is_ignored(value):
    clock = Clock()
    limited = pacer(clock)
    limited.observe_response(429, {"Retry-After": value})
    limited.observe_response(200, {"Retry-After": "30"})
    with limited.slot(1):
        pass
    assert clock.waits == []


def test_retry_after_is_bounded_and_cannot_fit_rejected_deadline():
    clock = Clock()
    limited = pacer(clock)
    limited.observe_response(429, {"Retry-After": "1000000"})
    with pytest.raises(ModelCallNotStarted):
        with limited.slot(MAX_RETRY_AFTER_SECONDS):
            pytest.fail("cooldown uses the caller deadline")
    assert clock.waits == []
    with limited.slot(MAX_RETRY_AFTER_SECONDS + 1) as remaining:
        assert remaining == 1 and clock.now == MAX_RETRY_AFTER_SECONDS


@pytest.mark.parametrize("kind", ["requests", "tokens", "input-tokens", "output-tokens"])
def test_exhausted_anthropic_limit_proactively_cools_down_success_response(monkeypatch, kind):
    clock = Clock()
    monkeypatch.setattr(pacing.time, "time", lambda: 1_000_000.0)
    limited = pacer(clock)
    reset = datetime.fromtimestamp(1_000_008, UTC).isoformat().replace("+00:00", "Z")
    limited.observe_response(
        200,
        {
            f"Anthropic-RateLimit-{kind}-Remaining": "0",
            f"Anthropic-RateLimit-{kind}-Reset": reset,
        },
    )
    with limited.slot(10) as remaining:
        assert clock.now == 8 and remaining == 2


@pytest.mark.parametrize(
    "remaining,reset",
    [
        ("1", "1970-01-12T13:46:48Z"),
        ("NaN", "1970-01-12T13:46:48Z"),
        ("invalid", "1970-01-12T13:46:48Z"),
        ("0", "invalid"),
        ("0", "1970-01-12T13:46:48"),
        ("0", "1970-01-01T00:00:00Z"),
    ],
)
def test_nonexhausted_or_malformed_anthropic_headers_do_not_guess_limit(
    monkeypatch, remaining, reset
):
    clock = Clock()
    monkeypatch.setattr(pacing.time, "time", lambda: 1_000_000.0)
    limited = pacer(clock)
    limited.observe_response(
        200,
        {
            "anthropic-ratelimit-requests-remaining": remaining,
            "anthropic-ratelimit-requests-reset": reset,
        },
    )
    with limited.slot(1) as timeout:
        assert timeout == 1 and clock.now == 0
    assert clock.waits == []


def test_header_limits_take_longest_bounded_cooldown(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(pacing.time, "time", lambda: 1_000_000.0)
    limited = pacer(clock)
    reset = datetime.fromtimestamp(1_000_000 + 2 * MAX_RETRY_AFTER_SECONDS, UTC).isoformat()
    limited.observe_response(
        429,
        {
            "retry-after": "5",
            "anthropic-ratelimit-tokens-remaining": "0",
            "anthropic-ratelimit-tokens-reset": reset,
        },
    )
    with limited.slot(MAX_RETRY_AFTER_SECONDS + 1) as timeout:
        assert timeout == 1 and clock.now == MAX_RETRY_AFTER_SECONDS


def test_shared_pacer_serializes_threads_and_accounts_for_in_flight_time():
    clock = Clock()
    waiting = Event()
    entered = Event()
    outcomes = []

    def observed_clock():
        now = clock.now
        if current_thread().name == "pacer-worker":
            waiting.set()
        return now

    limited = RequestPacer(clock=observed_clock, sleep=clock.sleep)

    def worker():
        with limited.slot(10) as remaining:
            outcomes.append(remaining)
            entered.set()

    with limited.slot(10):
        thread = Thread(target=worker, name="pacer-worker")
        thread.start()
        assert waiting.wait(1)
        assert not entered.is_set()
        clock.now = 3
    thread.join(1)
    assert not thread.is_alive() and outcomes == [7]


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_invalid_timeout_rejects_before_admission(timeout):
    clock = Clock()
    with pytest.raises(ModelCallNotStarted):
        with pacer(clock).slot(timeout):
            pytest.fail("invalid timeout cannot admit a request")


@pytest.mark.parametrize("interval", [-1, float("nan"), float("inf"), True])
def test_invalid_intervals_reject_configuration(interval):
    with pytest.raises(ValueError):
        RequestPacer(min_interval_seconds=interval)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_request_caps_reject_configuration(limit):
    with pytest.raises(ValueError):
        RequestPacer(max_requests_per_minute=limit)
