"""Parse declared assistant-output encodings without extracting or repairing JSON."""

from __future__ import annotations

import json
import math
from typing import Any, Literal

JSONEncoding = Literal["json", "json_fence"]


def parse_json_response(raw: str) -> tuple[Any, JSONEncoding]:
    """Accept raw strict JSON or one exact JSON code-fence envelope.

    The optional envelope is case-sensitive and must cover the entire string,
    with literal LF separators and no outer whitespace or commentary. JSON's own
    whitespace remains valid inside the payload. Duplicate keys, nonstandard
    constants, and floating-point overflow are rejected in either encoding.
    This parser is for final assistant content, never tool-call arguments.
    """
    if not isinstance(raw, str):
        raise ValueError("assistant JSON response must be text")
    encoding: JSONEncoding = "json"
    payload = raw
    if raw.startswith("```json\n") and raw.endswith("\n```"):
        payload = raw[len("```json\n") : -len("\n```")]
        encoding = "json_fence"

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    def constant(_value: str) -> None:
        raise ValueError("nonstandard JSON numeric constant")

    def finite(raw_number: str) -> float:
        value = float(raw_number)
        if not math.isfinite(value):
            raise ValueError("JSON number exceeds the finite floating-point range")
        return value

    value = json.loads(
        payload, object_pairs_hook=unique, parse_constant=constant, parse_float=finite
    )
    return value, encoding
