from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Answer, Citation, FinancialCell
from .numbers import format_financial_number
from .validation import validate_cell


COLUMN_ALIASES = {
    "期末账面价值": ["期末账面价值", "期末价值", "2025年6月30日账面价值", "2024年12月31日账面价值"],
    "期初账面价值": ["期初账面价值", "期初价值"],
    "本期增加": ["本期增加", "本年增加", "增加额"],
    "本期减少": ["本期减少", "本年减少", "减少额"],
    "减值准备": ["减值准备"],
    "即期偿还": ["即期偿还"],
    "3个月内": ["3个月内", "三个月内"],
    "3个月至1年": ["3个月至1年", "三个月至一年"],
    "1至5年": ["1至5年", "一年至五年"],
    "5年以上": ["5年以上", "五年以上"],
    "无期限": ["无期限"],
    "合计": ["合计", "总计", "总额"],
    "归属于母公司股东的其他综合收益期初余额": ["期初余额"],
    "本期所得税前发生额": ["本期所得税前发生额", "所得税前发生额"],
    "减：所得税": ["减所得税", "所得税"],
    "小计": ["小计"],
    "税后归属于母公司": ["税后归属于母公司"],
    "税后归属于少数股东": ["税后归属于少数股东"],
    "归属于母公司股东的其他综合收益期末余额": ["期末余额"],
}

PERIOD_ALIASES = {
    "2025-06-30": ["2025年6月30日", "2025年", "本期"],
    "2024-12-31": ["2024年12月31日", "2024年", "上期"],
    "2025-H1": ["2025年1月1日至2025年6月30日", "2025年", "本期"],
    "2024-H1": ["2024年1月1日至6月30日", "2024年", "上年同期"],
}

STOP_WORDS = [
    "是多少",
    "多少",
    "请问",
    "分别",
    "请查询",
    "2025年6月30日",
    "2024年12月31日",
    "2025年",
    "2024年",
    "本期",
    "上期",
]


def normalize(value: str) -> str:
    return re.sub(r"[\s，。、“”‘’：:？?（）()|]", "", value).lower()


class FinancialQAAgent:
    def __init__(self, cells: list[FinancialCell]):
        self.cells = cells

    def ask(self, question: str) -> Answer:
        compact_question = normalize(question)
        period = self._detect_period(compact_question)
        column = self._detect_column(compact_question)
        row, row_score = self._detect_row(compact_question)

        if row is None or row_score < 0.48:
            evidence = self.retrieve(question)
            return Answer(
                question=question,
                status="no_answer",
                answer="当前文档中未检索到足够依据，无法可靠回答。",
                confidence=round(row_score, 3),
                retrieved_evidence=evidence,
                warnings=["No sufficiently similar structured row was found"],
            )

        row_cells = [cell for cell in self.cells if cell.row == row]
        possible_periods = sorted({cell.period for cell in row_cells})
        if period is None and len(possible_periods) > 1:
            return Answer(
                question=question,
                status="clarification_required",
                answer=f"问题缺少期间。请明确选择：{', '.join(possible_periods)}。",
                confidence=0.0,
                warnings=["Multiple periods match the requested row"],
            )
        if period is None and possible_periods:
            period = possible_periods[0]

        candidates = [
            cell for cell in row_cells if cell.period == period and cell.column == column
        ]
        if not candidates:
            available_columns = sorted(
                {cell.column for cell in row_cells if cell.period == period}
            )
            return Answer(
                question=question,
                status="no_answer",
                answer=(
                    "找到了相关项目，但没有找到所需列。"
                    f"可用列：{', '.join(available_columns)}。"
                ),
                confidence=round(row_score * 0.6, 3),
                retrieved_evidence=self.retrieve(question),
                warnings=["Requested period/column combination is unavailable"],
            )

        best = max(candidates, key=lambda cell: (cell.confidence, cell.numeric_value is not None))
        checks = validate_cell(best, self.cells)
        failed = [check for check in checks if not check.passed]
        status = "supported" if not failed else "needs_review"
        confidence = min(best.confidence, row_score)
        if failed:
            confidence *= 0.55
        citation = Citation(
            pdf_page=best.pdf_page,
            printed_page=best.printed_page,
            table=best.table,
            row=best.row,
            column=best.column,
            cell_id=best.cell_id,
        )
        if best.numeric_value is None:
            value_statement = (
                f"{best.period}，{best.row}的“{best.column}”OCR 原始值为 "
                f"{best.raw_value}，但无法可靠解析为财务数字"
            )
        else:
            value_statement = (
                f"{best.period}，{best.row}的“{best.column}”为 "
                f"{format_financial_number(best.numeric_value)}"
            )
        answer = (
            value_statement
            + f"。来源：PDF 第 {best.pdf_page} 页"
            + (f"（原报告第 {best.printed_page} 页）" if best.printed_page else "")
            + "。"
        )
        return Answer(
            question=question,
            status=status,
            answer=answer,
            confidence=round(confidence, 3),
            citations=[citation],
            checks=checks,
            retrieved_evidence=self.retrieve(question),
            warnings=best.warnings,
        )

    def retrieve(self, question: str, limit: int = 5) -> list[dict[str, object]]:
        query = normalize(question)
        target_period = self._detect_period(query)
        target_column = self._detect_column(query)
        target_row, target_row_score = self._detect_row(query)
        scored: list[tuple[float, FinancialCell]] = []
        for cell in self.cells:
            document = normalize(f"{cell.period}{cell.table}{cell.row}{cell.column}")
            score = SequenceMatcher(None, query, document).ratio()
            for token in self._query_tokens(query):
                if token and token in document:
                    score += min(len(token) / 20, 0.25)
            if target_period and cell.period == target_period:
                score += 0.4
            if target_column and cell.column == target_column:
                score += 0.3
            if target_row_score >= 0.48 and cell.row == target_row:
                score += 0.8
            scored.append((score, cell))
        return [
            {
                "score": round(score, 3),
                "page": cell.pdf_page,
                "period": cell.period,
                "table": cell.table,
                "row": cell.row,
                "column": cell.column,
                "raw_value": cell.raw_value,
                "cell_id": cell.cell_id,
            }
            for score, cell in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]
        ]

    def _detect_period(self, question: str) -> str | None:
        table_hint = self._detect_table_hint(question)
        for period, aliases in PERIOD_ALIASES.items():
            if table_hint == "其他综合收益" and period not in {"2025-H1", "2024-H1"}:
                continue
            if table_hint != "其他综合收益" and period in {"2025-H1", "2024-H1"}:
                continue
            if any(normalize(alias) in question for alias in aliases):
                return period
        return None

    def _detect_table_hint(self, question: str) -> str | None:
        if "综合收益" in question:
            return "其他综合收益"
        if any(token in question for token in ["借款", "金融负债", "应付债券", "现金流"]):
            return "金融负债合同现金流量"
        if any(token in question for token in ["投资", "被投资", "公司", "limited"]):
            return "长期股权投资变动明细"
        return None

    def _detect_column(self, question: str) -> str:
        matches: list[tuple[int, str]] = []
        for column, aliases in COLUMN_ALIASES.items():
            for alias in aliases:
                normalized = normalize(alias)
                if normalized in question:
                    matches.append((len(normalized), column))
        if matches:
            return max(matches)[1]
        table = self._detect_table_hint(question)
        if table == "长期股权投资变动明细":
            return "期末账面价值"
        if table == "其他综合收益":
            return "归属于母公司股东的其他综合收益期末余额"
        return "合计"

    def _detect_row(self, question: str) -> tuple[str | None, float]:
        stripped = question
        for word in STOP_WORDS:
            stripped = stripped.replace(normalize(word), "")
        for aliases in COLUMN_ALIASES.values():
            for alias in aliases:
                stripped = stripped.replace(normalize(alias), "")
        rows = sorted({cell.row for cell in self.cells}, key=len, reverse=True)
        exact_in_question = [
            row for row in rows if len(normalize(row)) >= 4 and normalize(row) in question
        ]
        if exact_in_question:
            return max(exact_in_question, key=len), 1.0
        hierarchical = [
            row for row in rows if len(stripped) >= 4 and stripped in normalize(row)
        ]
        if hierarchical:
            return min(hierarchical, key=len), 1.0
        if not rows:
            return None, 0.0
        scored = [
            (SequenceMatcher(None, stripped, normalize(row)).ratio(), row) for row in rows
        ]
        score, row = max(scored)
        return row, score

    @staticmethod
    def _query_tokens(question: str) -> list[str]:
        return [token for token in re.split(r"\d+|年|月|日|至|的|为", question) if len(token) >= 2]
