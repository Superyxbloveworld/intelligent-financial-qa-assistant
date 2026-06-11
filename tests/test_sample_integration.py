import json
from pathlib import Path

import pytest

from docqa.models import FinancialCell
from docqa.pipeline import ingest
from docqa.qa_agent import FinancialQAAgent
from docqa.storage import read_jsonl


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def sample_agent():
    cells_path = ROOT / "artifacts/cells.jsonl"
    if not cells_path.exists():
        ingest(ROOT, ROOT / "data/input/financial-report-sample.pdf")
    return FinancialQAAgent(read_jsonl(cells_path, FinancialCell))


def test_sample_routes_scanned_page_to_ocr():
    diagnostics_path = ROOT / "artifacts/diagnostics.json"
    if not diagnostics_path.exists():
        ingest(ROOT, ROOT / "data/input/financial-report-sample.pdf")
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert len(diagnostics) == 6
    assert diagnostics[-1]["page_type"] == "scanned"
    assert diagnostics[-1]["parser"] in {"macos-vision", "unavailable"}


def test_sample_native_page_answer_is_supported(sample_agent):
    answer = sample_agent.ask("2025年短期借款合计是多少？")
    assert answer.status == "supported"
    assert "27,257,591,390.02" in answer.answer
    assert answer.citations[0].pdf_page == 5


def test_sample_ocr_error_is_exposed(sample_agent):
    answer = sample_agent.ask("2024年应付债券5年以上是多少？")
    if not answer.citations:
        pytest.skip("OCR backend unavailable on this platform")
    assert answer.status == "needs_review"
    assert any(not check.passed for check in answer.checks)
