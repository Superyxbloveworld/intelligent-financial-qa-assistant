from __future__ import annotations

from pathlib import Path

from .models import to_dict
from .observability import audit_event
from .pdf_parser import PDFParser
from .storage import write_json, write_jsonl
from .table_parser import extract_financial_cells
from .validation import build_validation_report


def ingest(project_root: Path, pdf_path: Path) -> dict[str, object]:
    parser = PDFParser(project_root)
    diagnostics, words_by_page = parser.parse(pdf_path)
    printed_pages = {item.pdf_page: item.printed_page for item in diagnostics}
    cells = extract_financial_cells(words_by_page, printed_pages)

    artifacts = project_root / "artifacts"
    write_json(artifacts / "diagnostics.json", [to_dict(item) for item in diagnostics])
    write_jsonl(artifacts / "cells.jsonl", cells)
    write_json(artifacts / "validation_report.json", build_validation_report(cells))
    write_json(
        artifacts / "manifest.json",
        {
            "source_pdf": str(pdf_path),
            "pages": len(diagnostics),
            "cells": len(cells),
            "scanned_pages": [
                item.pdf_page for item in diagnostics if item.page_type == "scanned"
            ],
            "ocr_pages": [
                item.pdf_page for item in diagnostics if item.parser != "pymupdf"
            ],
        },
    )
    audit_event(
        project_root,
        "ingest_completed",
        source_pdf=pdf_path.name,
        pages=len(diagnostics),
        cells=len(cells),
        scanned_pages=sum(item.page_type == "scanned" for item in diagnostics),
        ocr_pages=sum(item.parser != "pymupdf" for item in diagnostics),
    )
    return {
        "diagnostics": diagnostics,
        "cells": cells,
        "validation_report": build_validation_report(cells),
    }
