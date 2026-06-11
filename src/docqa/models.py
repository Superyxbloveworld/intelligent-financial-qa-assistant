from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float = 1.0
    source: str = "native"

    @property
    def x_center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class PageDiagnostic:
    pdf_page: int
    printed_page: str | None
    page_type: str
    parser: str
    orientation: str
    width: float
    height: float
    native_text_chars: int
    image_count: int
    word_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class FinancialCell:
    cell_id: str
    pdf_page: int
    printed_page: str | None
    table: str
    period: str
    row: str
    column: str
    raw_value: str
    numeric_value: float | None
    confidence: float
    source: str
    bbox: list[float]
    warnings: list[str] = field(default_factory=list)


@dataclass
class Citation:
    pdf_page: int
    printed_page: str | None
    table: str
    row: str
    column: str
    cell_id: str


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class Answer:
    question: str
    status: str
    answer: str
    confidence: float
    citations: list[Citation] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    retrieved_evidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
