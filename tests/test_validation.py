from docqa.models import FinancialCell
from docqa.validation import validate_cell


def make_cell(column, value, raw=None, confidence=1.0):
    return FinancialCell(
        cell_id=column,
        pdf_page=1,
        printed_page="1",
        table="金融负债合同现金流量",
        period="2025-06-30",
        row="示例",
        column=column,
        raw_value=raw or f"{value:,.2f}",
        numeric_value=value,
        confidence=confidence,
        source="ocr",
        bbox=[0, 0, 1, 1],
    )


def test_total_row_arithmetic_check_passes():
    cells = [
        make_cell("即期偿还", 40),
        make_cell("3个月内", 60),
        make_cell("合计", 100),
    ]
    checks = validate_cell(cells[-1], cells)
    assert next(check for check in checks if check.name == "row_sum_consistency").passed


def test_low_confidence_is_exposed():
    item = make_cell("合计", 100, confidence=0.3)
    checks = validate_cell(item, [item])
    assert not next(check for check in checks if check.name == "extraction_confidence").passed
