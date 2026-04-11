from __future__ import annotations

import json
from typing import Callable

from pydantic import ValidationError

from reviewbot.models import ReviewResult


class OutputParseError(RuntimeError):
    pass


RepairCallback = Callable[[str], str]


def parse_review_result(raw_text: str, repair: RepairCallback | None = None) -> ReviewResult:
    """Parse model output into ReviewResult, optionally retrying once via repair."""
    cleaned = _extract_json(raw_text)

    try:
        return ReviewResult.model_validate_json(cleaned)
    except ValidationError as error:
        if repair is None:
            raise OutputParseError(f"Invalid review JSON: {error}") from error

        repaired_raw = repair(build_repair_prompt(raw_text, error))
        repaired_cleaned = _extract_json(repaired_raw)

        try:
            return ReviewResult.model_validate_json(repaired_cleaned)
        except ValidationError as retry_error:
            raise OutputParseError(f"Invalid review JSON after repair: {retry_error}") from retry_error


def build_repair_prompt(raw_text: str, error: ValidationError) -> str:
    return (
        "Return valid JSON only. Fix the schema violations described below without adding markdown.\n\n"
        f"Validation error:\n{error}\n\n"
        f"Broken JSON:\n{raw_text}"
    )


def _extract_json(raw_text: str) -> str:
    candidate = raw_text.strip()
    if candidate.startswith("```"):
        candidate = _strip_fences(candidate)

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise OutputParseError(f"Model output is not valid JSON: {error}") from error

    return json.dumps(parsed)


def _strip_fences(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return text

    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]

    return "\n".join(lines).strip()
