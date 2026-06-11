from __future__ import annotations

import json
import sys
from pathlib import Path

from .evaluation import evaluate
from .models import FinancialCell, to_dict
from .pipeline import ingest
from .qa_agent import FinancialQAAgent
from .storage import read_jsonl, write_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CELLS_PATH = PROJECT_ROOT / "artifacts" / "cells.jsonl"


def load_agent() -> FinancialQAAgent:
    if not CELLS_PATH.exists():
        raise SystemExit("Missing artifacts/cells.jsonl. Run ingest first.")
    return FinancialQAAgent(read_jsonl(CELLS_PATH, FinancialCell))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m docqa.cli [ingest|ask|evaluate] ...")
    command = sys.argv[1]
    if command == "ingest":
        pdf_path = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT_ROOT / "data/input/financial-report-sample.pdf"
        result = ingest(PROJECT_ROOT, pdf_path.resolve())
        print(
            json.dumps(
                {
                    "pages": len(result["diagnostics"]),
                    "cells": len(result["cells"]),
                    "validation_report": result["validation_report"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif command == "ask":
        question = sys.argv[2] if len(sys.argv) > 2 else "2025年短期借款合计是多少？"
        print(json.dumps(to_dict(load_agent().ask(question)), ensure_ascii=False, indent=2))
    elif command == "evaluate":
        dataset = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT_ROOT / "eval/golden_questions.jsonl"
        report = evaluate(load_agent(), dataset)
        write_json(PROJECT_ROOT / "artifacts" / "evaluation_report.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["pass_rate"] < 1:
            raise SystemExit(1)
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main()
