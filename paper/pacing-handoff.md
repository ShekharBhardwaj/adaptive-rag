# Provider request pacing

Pacing is implemented and verified offline. The previous raw runs, index, review
packets, and frozen experiment configurations remain preserved. The final fresh
development plan uses `configs/adaptive.anthropic.final.local.yaml` and writes to
`experiments/raw/adaptive-anthropic-paced-development-20261117-001`; this document
describes its controls. The [final execution report](phase5-paced-development-run.md)
records all 270 jobs, including retained failures and pending human reviews.

The final profile keeps direct Anthropic Haiku 4.5 for routing, navigation, and
answers, and reuses the existing Qwen index and embedding connection. Its
configured bounds are:

| Control | Configured value |
| --- | --- |
| Concurrent requests per endpoint in one process | 1 |
| Minimum time between request starts | 6 seconds |
| Maximum starts per rolling minute | 10 |
| Planned development jobs | 270 |
| Run monotonic elapsed-time limit, including pacing waits | 2 hours (7,200 seconds) |
| Run token / model-attempt limits | 12 million budgeted tokens / 2,000 attempts |
| Estimated admission allocation | $9.90 for the run; at most $0.10 separately for synthetic preflight |
| Unknown-usage policy | `reserve` (opt-in; default remains `stop`) |

All chat roles share one gate. A shared embedding/chat endpoint uses the stricter
of their settings. Separate processes have independent gates; use one experiment
process for the provider account. These controls do not establish the account's
token quotas. Anthropic also limits input and output tokens per minute; request
spacing can reduce bursts but cannot guarantee successful calls. See the
[official rate-limit guidance](https://platform.claude.com/docs/en/api/rate-limits).

The gate applies numeric or HTTP-date `Retry-After` cooldowns on HTTP 402, 429,
and 503. Exhausted Anthropic remaining/reset headers also impose a cooldown.
Server delays are bounded at one hour; a delay that cannot fit a caller's
remaining deadline is rejected before network delegation. Failed calls are
never automatically retried. The former 30-second timeout was not proof of a
provider rate-limit response.

`experiment.budget.unknown_usage_policy` defaults to `stop`: missing provider
usage retains unknown accounting and prevents later jobs. The final profile
explicitly selects `reserve`. Before delegation, the journal reserves a
conservative admission charge using serialized input bytes, the full requested
output token limit, and the dated price schedule. If a call returns usage, the
ledger uses that observed charge; if usage is missing, it retains the reservation
so later jobs can be admitted within the remaining run bounds. A finite token and
cost reservation must be available, or execution still stops.

Reservation does not change the failed job or its evidence. A timed-out request
stays failed, actual missing tokens and complete cost stay unknown, and there is
no retry or replacement answer. Recorded `usage` and actual cost fields retain
their original meanings. Per-job `metadata.budget_accounting` and final status
`budget_accounting` separately expose used-or-reserved token and cost estimates,
including counts of reserved and unreserved unknown calls. Known cost subtotals
are not complete costs. These estimates are admission bounds under the configured
token/price assumptions, not a provider-enforced spending quota or a billing
reconciliation.

Queue waits consume stage/run elapsed budgets and appear in job elapsed time. Raw
provider-call elapsed time starts after pacing admission. Pre-network rejection
or cancellation adds no provider attempt or unknown usage. The journal also
subtracts admission and durable-intent time from the caller's remaining deadline.
Persistent model/index identities and old answer-review hashes are unchanged.

Earlier pacing verification: 194 focused tests passed, including deterministic
clock tests, HTTP mock transports, shared-role pacing, cooldowns, deadline rejection,
cancellation, journal accounting, index recovery, CLI and runner integration.
Ruff lint/format and configuration validation passed. These checks exercise
contracts; they do not establish the final run's outcomes.

Final reservation/pacing integration verification separately passed 147 tests
in 81.11 seconds, with Ruff lint/format passing. The five-call live synthetic
preflight cost estimate was $0.00677328. The final run recorded
6,293.04456858302 seconds of monotonic elapsed time; the operational audit reports
the wall-clock/suspend discrepancy separately. See the
[verification record](../experiments/preflight/final-development-2026-11-17-001/verification.json)
and [final execution report](phase5-paced-development-run.md).

The [final operational audit](../experiments/preflight/final-development-2026-11-17-001/operational-audit-final.json)
is `PASS_WITH_WALL_TIMESTAMP_PACING_EXCEPTION`. Recorded chat wall timestamps
include one 5.945952-second gap and a rolling-60-second peak of 11 in three
overlapping windows. Monotonic admission times were not persisted; delayed
recording or wall-clock variation is possible but unproven. The configured
6-second/10-start limits therefore cannot be claimed for every recorded wall
timestamp. No HTTP errors were observed. Coverage, accounting, and identity
checks passed; see the report for the timing distinction.

Pacing makes execution slower. At ten starts per minute a two-hour run permits
roughly 1,200 starts per endpoint before other overhead; the 270-job plan can
require more calls. The time, admission, and provider limits may still leave a
partial run. There are no automatic retries or reruns. Any later execution needs
a fresh preserved plan and output directory; it must not append to a prior
partial run or blend its results into that run.
