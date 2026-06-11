from docqa.models import FinancialCell
from docqa.qa_agent import FinancialQAAgent


def cell(period, row, column, value, page=1):
    return FinancialCell(
        cell_id=f"{period}-{row}-{column}",
        pdf_page=page,
        printed_page="100",
        table="金融负债合同现金流量",
        period=period,
        row=row,
        column=column,
        raw_value=value,
        numeric_value=float(value.replace(",", "")),
        confidence=1.0,
        source="native",
        bbox=[0, 0, 1, 1],
    )


def test_agent_answers_with_citation():
    agent = FinancialQAAgent(
        [
            cell("2025-06-30", "短期借款", "合计", "27,257,591,390.02", 5),
            cell("2024-12-31", "短期借款", "合计", "14,101,152,744.56", 6),
        ]
    )
    answer = agent.ask("2025 年短期借款合计是多少？")
    assert answer.status == "supported"
    assert "27,257,591,390.02" in answer.answer
    assert answer.citations[0].pdf_page == 5


def test_agent_requires_period_for_ambiguous_question():
    agent = FinancialQAAgent(
        [
            cell("2025-06-30", "短期借款", "合计", "27,257,591,390.02"),
            cell("2024-12-31", "短期借款", "合计", "14,101,152,744.56"),
        ]
    )
    assert agent.ask("短期借款是多少？").status == "clarification_required"


def test_agent_refuses_unsupported_question():
    agent = FinancialQAAgent([cell("2025-06-30", "短期借款", "合计", "1.00")])
    assert agent.ask("营业收入是多少？").status == "no_answer"
