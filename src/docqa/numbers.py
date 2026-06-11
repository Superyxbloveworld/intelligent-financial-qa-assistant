from __future__ import annotations

import math
import re


FINANCIAL_NUMBER_RE = re.compile(
    r"^\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?\)?$"
)


def is_financial_number(value: str) -> bool:
    return bool(FINANCIAL_NUMBER_RE.fullmatch(value.strip()))


def looks_like_numeric_token(value: str) -> bool:
    stripped = value.strip()
    return any(character.isdigit() for character in stripped) and any(
        marker in stripped for marker in [",", ".", "，", "。", "(", ")", "（", "）"]
    )


def parse_financial_number(value: str) -> tuple[float | None, list[str]]:
    raw = value.strip()
    warnings: list[str] = []
    if raw in {"", "-", "—", "–"}:
        return None, warnings
    if not is_financial_number(raw):
        return None, ["invalid_numeric_format"]
    negative = raw.startswith("(") and raw.endswith(")")
    normalized = raw.strip("()").replace(",", "")
    try:
        number = float(normalized)
    except ValueError:
        return None, ["numeric_parse_failed"]
    return (-number if negative else number), warnings


def format_financial_number(value: float | None) -> str:
    if value is None:
        return "-"
    if value < 0:
        return f"({abs(value):,.2f})"
    return f"{value:,.2f}"


def amounts_close(left: float, right: float, tolerance: float = 0.02) -> bool:
    return math.isclose(left, right, abs_tol=tolerance, rel_tol=1e-10)
