"""Reject LLM output that introduces numbers not present in module facts."""
from __future__ import annotations

import re
from typing import Any

NUMBER_RE = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?")
GENE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")


def _parse_number(token: str) -> float | None:
    cleaned = token.replace(",", "").replace("\u2212", "-")
    try:
        return abs(float(cleaned))
    except (TypeError, ValueError, OverflowError):
        return None


def _normalise(value: float) -> str:
    return f"{float(value):.10g}"


def _collect(value: Any, out: set[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        number = _parse_number(str(value))
        if number is not None:
            out.add(_normalise(number))
        return
    if isinstance(value, str):
        cleaned = GENE_TOKEN_RE.sub(" ", value)
        for match in NUMBER_RE.findall(cleaned):
            number = _parse_number(match)
            if number is not None:
                out.add(_normalise(number))
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect(item, out)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect(item, out)


def allowed_numbers(facts: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    _collect(facts, out)
    return out


def validate_numbers(text: str, facts: dict[str, Any], gene_symbol: str) -> list[str]:
    """Return offending numeric literals (empty list means the text is safe)."""
    cleaned = text.replace(gene_symbol, " ").replace("\u2212", "-")
    cleaned = GENE_TOKEN_RE.sub(" ", cleaned)
    allowed = allowed_numbers(facts)
    offenders: list[str] = []
    for match in NUMBER_RE.findall(cleaned):
        number = _parse_number(match)
        if number is None or _normalise(number) not in allowed:
            offenders.append(match)
    return offenders
