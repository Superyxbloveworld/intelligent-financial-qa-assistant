from __future__ import annotations

import json
from pathlib import Path

from .qa_agent import FinancialQAAgent


def evaluate(agent: FinancialQAAgent, dataset_path: Path) -> dict[str, object]:
    cases = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    results: list[dict[str, object]] = []
    for case in cases:
        answer = agent.ask(case["question"])
        status_ok = answer.status == case["expected_status"]
        value_ok = (
            case.get("expected_value") is None
            or case["expected_value"] in answer.answer
        )
        citation_ok = (
            case.get("expected_page") is None
            or any(item.pdf_page == case["expected_page"] for item in answer.citations)
        )
        results.append(
            {
                "question": case["question"],
                "passed": status_ok and value_ok and citation_ok,
                "status_ok": status_ok,
                "value_ok": value_ok,
                "citation_ok": citation_ok,
                "actual_status": answer.status,
                "actual_answer": answer.answer,
            }
        )
    passed = sum(bool(item["passed"]) for item in results)
    return {
        "total": len(results),
        "passed": passed,
        "pass_rate": round(passed / len(results), 3) if results else 0,
        "results": results,
    }
