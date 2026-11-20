"""Declared final-output transport formats; no JSON repair or substring extraction."""

import pytest

from adaptive_rag.generation.json_output import parse_json_response


@pytest.mark.parametrize(
    "payload,expected",
    [
        ('{"value": [1, true, null]}', {"value": [1, True, None]}),
        (' \n {"value": 1} \t', {"value": 1}),
        ('["synthetic", 1.5]', ["synthetic", 1.5]),
        ("null", None),
        (
            '{"answer":"The literal ``` marker is source data."}',
            {"answer": "The literal ``` marker is source data."},
        ),
    ],
)
@pytest.mark.parametrize("fenced", [False, True])
def test_declared_encodings_preserve_the_same_strict_json_value(payload, expected, fenced):
    raw = f"```json\n{payload}\n```" if fenced else payload
    assert parse_json_response(raw) == (expected, "json_fence" if fenced else "json")


@pytest.mark.parametrize(
    "raw",
    [
        "Here is the result:\n```json\n{}\n```",
        "```json\n{}\n```\nExplanation follows.",
        "```json\n{}\n```\n```json\n{}\n```",
        "```json\n{}",
        "```\n{}\n```",
        "```JSON\n{}\n```",
        "```json {} ```",
        "```json \n{}\n```",
        "```json\n{}```",
        "```json\r\n{}\r\n```",
        " ```json\n{}\n```",
        "```json\n{}\n```\n",
        "```json\n```json\n{}\n```\n```",
        "```json\n\n```",
    ],
)
def test_other_wrappers_are_rejected_without_extraction(raw):
    with pytest.raises(ValueError):
        parse_json_response(raw)


@pytest.mark.parametrize(
    "payload",
    [
        '{"value": 1, "value": 2}',
        '{"outer": {"value": 1, "value": 2}}',
        '{"value": 1, "\\u0076alue": 2}',
        '{"value": NaN}',
        '{"value": Infinity}',
        '{"value": -Infinity}',
        '{"value": 1e9999}',
        "{'value': 1}",
        '{"value": 1,}',
        "{} {}",
        "{",
    ],
)
@pytest.mark.parametrize("fenced", [False, True])
def test_invalid_json_is_rejected_in_both_encodings(payload, fenced):
    raw = f"```json\n{payload}\n```" if fenced else payload
    with pytest.raises(ValueError):
        parse_json_response(raw)


@pytest.mark.parametrize("raw", [None, {}, [], b"{}", 1])
def test_nontext_responses_are_rejected(raw):
    with pytest.raises(ValueError, match="must be text"):
        parse_json_response(raw)
