from __future__ import annotations

from collections import defaultdict

from .models import CheckResult, FinancialCell
from .numbers import amounts_close


def validate_cell(cell: FinancialCell, all_cells: list[FinancialCell]) -> list[CheckResult]:
    checks = [
        CheckResult(
            name="citation_exists",
            passed=bool(cell.cell_id and cell.pdf_page),
            detail=f"cell_id={cell.cell_id}, pdf_page={cell.pdf_page}",
        ),
        CheckResult(
            name="numeric_format",
            passed=cell.numeric_value is not None or cell.raw_value in {"-", "—", "–"},
            detail=(
                "valid financial number or explicit blank"
                if cell.numeric_value is not None or cell.raw_value in {"-", "—", "–"}
                else f"unparseable: {cell.raw_value}"
            ),
        ),
        CheckResult(
            name="extraction_confidence",
            passed=cell.confidence >= 0.6,
            detail=f"source={cell.source}, confidence={cell.confidence:.2f}",
        ),
    ]
    if cell.column == "合计" and cell.numeric_value is not None:
        siblings = [
            candidate
            for candidate in all_cells
            if candidate.pdf_page == cell.pdf_page
            and candidate.table == cell.table
            and candidate.period == cell.period
            and candidate.row == cell.row
            and candidate.column != "合计"
            and candidate.numeric_value is not None
        ]
        if len(siblings) >= 2:
            subtotal = sum(candidate.numeric_value or 0 for candidate in siblings)
            passed = amounts_close(subtotal, cell.numeric_value)
            checks.append(
                CheckResult(
                    name="row_sum_consistency",
                    passed=passed,
                    detail=f"components={subtotal:,.2f}, total={cell.numeric_value:,.2f}",
                )
            )
    return checks


def build_validation_report(cells: list[FinancialCell]) -> dict[str, object]:
    warning_counts: dict[str, int] = defaultdict(int)
    for cell in cells:
        for warning in cell.warnings:
            warning_counts[warning] += 1

    total_checks = 0
    failed_checks = 0
    failures: list[dict[str, object]] = []
    for cell in cells:
        for check in validate_cell(cell, cells):
            total_checks += 1
            if not check.passed:
                failed_checks += 1
                failures.append(
                    {
                        "cell_id": cell.cell_id,
                        "page": cell.pdf_page,
                        "row": cell.row,
                        "column": cell.column,
                        "check": check.name,
                        "detail": check.detail,
                    }
                )
    return {
        "cell_count": len(cells),
        "warning_counts": dict(warning_counts),
        "checks": total_checks,
        "failed_checks": failed_checks,
        "failures": failures[:100],
    }
