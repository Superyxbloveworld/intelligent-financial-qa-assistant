import json

from docqa.observability import audit_event


def test_audit_event_writes_structured_record_without_document_content(tmp_path):
    audit_event(
        tmp_path,
        "question_answered",
        question_hash="abc123",
        status="no_answer",
    )

    record = json.loads((tmp_path / "artifacts/events.jsonl").read_text(encoding="utf-8"))
    assert record["event"] == "question_answered"
    assert record["question_hash"] == "abc123"
    assert record["status"] == "no_answer"
    assert "timestamp" in record
