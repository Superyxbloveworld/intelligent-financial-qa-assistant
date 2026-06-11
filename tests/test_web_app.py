import fitz
import pytest

from web_app import (
    ACTIVE_PDF,
    HTML,
    RELIABILITY_HTML,
    Handler,
    activate_builtin_sample,
    activate_pdf,
    load_summary,
)


def test_product_pages_use_capability_and_reliability_language():
    assert "<h1>智能财务问答助手</h1>" in HTML
    assert "<h1>可靠性与工程验证</h1>" in RELIABILITY_HTML


def test_web_summary_exposes_diagnostics_and_validation():
    summary = load_summary()
    assert len(summary["diagnostics"]) == 6
    assert summary["validation"]["cell_count"] > 100
    assert summary["validation"]["failed_checks"] > 0


def test_invalid_upload_is_rejected_without_changing_current_document():
    before = load_summary()["document"]
    with pytest.raises(ValueError, match="不是有效 PDF"):
        activate_pdf(b"not-a-pdf", "broken.pdf")
    assert load_summary()["document"] == before


def test_uploaded_pdf_is_automatically_parsed_and_sample_can_be_restored():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Uploaded document without a financial table")
    payload = document.tobytes()
    document.close()

    try:
        summary = activate_pdf(payload, "my-upload.pdf")
        assert summary["document"]["filename"] == "my-upload.pdf"
        assert summary["document"]["pages"] == 1
        assert summary["document"]["is_builtin_sample"] is False
        assert summary["diagnostics"][0]["page_type"] == "native"
        assert summary["validation"]["cell_count"] == 0
        assert Handler.agent.ask("2025 年短期借款合计是多少？").status == "no_answer"
    finally:
        restored = activate_builtin_sample()
        assert restored["document"]["is_builtin_sample"] is True
        assert not ACTIVE_PDF.exists()
