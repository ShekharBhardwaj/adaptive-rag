"""Vector-first escalation policy, versioned and fixed before it is evaluated.

The decision uses only what the first stage observed at run time: whether vector
retrieval and its answer completed, and the answer model's own boolean report of
evidence sufficiency. No benchmark annotation, category, split label, reference
answer, human score or earlier outcome is an input, and no question is special-cased.

Every request made by either stage is charged to the same job. Escalation never
replaces a failure silently: both stages, the reason and the stage that supplied
the final answer are recorded.
"""

from __future__ import annotations

from typing import Literal

POLICY_VERSION = "vector-first-cascade-v1"
FIRST_STAGE = "vector"
SECOND_STAGE = "agentic_wrapup"

EscalationReason = Literal[
    "first_stage_retrieval_failed",
    "first_stage_answer_failed",
    "evidence_reported_insufficient",
]

DESCRIPTION = {
    "policy_version": POLICY_VERSION,
    "first_stage": FIRST_STAGE,
    "second_stage": SECOND_STAGE,
    "escalate_when": (
        "first-stage retrieval or answer did not complete, or the first-stage answer did "
        "not report evidence_sufficient=true"
    ),
    "final_answer": (
        "the second-stage answer when it completes; otherwise the completed first-stage "
        "answer; otherwise the job fails"
    ),
    "inputs": "first-stage statuses and the answer model's evidence_sufficient report only",
    "accounting": "all requests, tokens, tool calls and elapsed time of both stages are charged",
}


def escalation_reason(
    *,
    retrieval_status: str,
    answer_status: str | None,
    evidence_sufficient: bool | None,
) -> EscalationReason | None:
    """Return why the second stage should run, or None when the first stage suffices."""
    if retrieval_status != "completed":
        return "first_stage_retrieval_failed"
    if answer_status != "completed":
        return "first_stage_answer_failed"
    if evidence_sufficient is not True:
        return "evidence_reported_insufficient"
    return None


def final_stage(
    *,
    first_answer_completed: bool,
    second_attempted: bool,
    second_answer_completed: bool,
) -> Literal[1, 2]:
    """Choose which stage supplies the recorded outcome."""
    if second_answer_completed:
        return 2
    if first_answer_completed:
        return 1
    return 2 if second_attempted else 1
