from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from .models import FinancialCell, Word
from .numbers import is_financial_number, looks_like_numeric_token, parse_financial_number


TABLE_COLUMNS = {
    "长期股权投资变动明细": ["期初账面价值", "本期增加", "本期减少", "期末账面价值", "减值准备"],
    "其他综合收益": [
        "归属于母公司股东的其他综合收益期初余额",
        "本期所得税前发生额",
        "减：所得税",
        "减：前期计入其他综合收益当期转入损益",
        "减：前期计入其他综合收益当期转入留存收益",
        "小计",
        "税后归属于母公司",
        "税后归属于少数股东",
        "归属于母公司股东的其他综合收益期末余额",
    ],
    "金融负债合同现金流量": ["即期偿还", "3个月内", "3个月至1年", "1至5年", "5年以上", "无期限", "合计"],
}


@dataclass
class Line:
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def compact_text(self) -> str:
        return "".join(word.text for word in self.words)

    @property
    def y(self) -> float:
        return median(word.y_center for word in self.words)


def group_lines(words: list[Word], tolerance: float = 3.5) -> list[Line]:
    lines: list[list[Word]] = []
    for word in sorted(words, key=lambda item: (item.y_center, item.x0)):
        target = next(
            (
                line
                for line in reversed(lines[-6:])
                if abs(median(item.y_center for item in line) - word.y_center) <= tolerance
            ),
            None,
        )
        if target is None:
            lines.append([word])
        else:
            target.append(word)
    return [Line(sorted(line, key=lambda item: item.x0)) for line in lines]


def identify_table(page_text: str) -> str | None:
    compact = page_text.replace(" ", "")
    if "被投资单位名称" in compact:
        return "长期股权投资变动明细"
    if "其他综合收益" in compact:
        return "其他综合收益"
    if "合同现金流量" in compact or "非衍生金融负债" in compact:
        return "金融负债合同现金流量"
    return None


def identify_period(page_text: str, table: str, fallback: str = "") -> str:
    compact = page_text.replace(" ", "")
    if table == "金融负债合同现金流量":
        if "2025年6月30日" in compact:
            return "2025-06-30"
        if "2024年12月31日" in compact:
            return "2024-12-31"
    if table == "其他综合收益":
        return "2025-H1" if "2025年1月1日至2025年6月30日" in compact else "2024-H1"
    if table == "长期股权投资变动明细":
        return "2025-06-30" if "2025年1月1日至6月30日止期间" in compact else "2024-12-31"
    return fallback


def _cluster_positions(values: list[float], tolerance: float = 24.0) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        target = next(
            (cluster for cluster in clusters if abs(median(cluster) - value) <= tolerance),
            None,
        )
        if target is None:
            clusters.append([value])
        else:
            target.append(value)
    return [median(cluster) for cluster in clusters]


def _select_column_positions(values: list[float], count: int, tolerance: float = 24.0) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(values):
        target = next(
            (cluster for cluster in clusters if abs(median(cluster) - value) <= tolerance),
            None,
        )
        if target is None:
            clusters.append([value])
        else:
            target.append(value)
    strongest = sorted(clusters, key=lambda cluster: (len(cluster), median(cluster)), reverse=True)[:count]
    return sorted(median(cluster) for cluster in strongest)


def _numeric_words(line: Line) -> list[Word]:
    return [
        word
        for word in line.words
        if is_financial_number(word.text) or looks_like_numeric_token(word.text)
    ]


def _clean_label(text: str) -> str:
    return re.sub(r"\s+", "", text).strip("：:-—–")


def extract_financial_cells(
    words_by_page: dict[int, list[Word]],
    printed_pages: dict[int, str | None],
) -> list[FinancialCell]:
    cells: list[FinancialCell] = []
    current_investment_period = "2025-06-30"
    for page_number, words in words_by_page.items():
        lines = group_lines(words, tolerance=4.5 if any(w.source != "native" for w in words) else 3.2)
        page_text = "\n".join(line.text for line in lines)
        table = identify_table(page_text)
        if table is None:
            continue
        columns = TABLE_COLUMNS[table]
        period = identify_period(page_text, table, current_investment_period)

        candidate_lines = [line for line in lines if any(is_financial_number(w.text) for w in line.words)]
        numeric_positions = [
            word.x1
            for line in candidate_lines
            for word in _numeric_words(line)
            if is_financial_number(word.text)
        ]
        all_clusters = _cluster_positions(numeric_positions)
        if len(all_clusters) < len(columns):
            continue
        # Real financial columns repeat on most rows; dates and printed page numbers are isolated.
        column_positions = _select_column_positions(numeric_positions, len(columns))

        label_buffer: list[str] = []
        for line in lines:
            compact = line.compact_text.replace(" ", "")
            if table == "长期股权投资变动明细" and "2024年度" in compact:
                current_investment_period = "2024-12-31"
                period = current_investment_period
                label_buffer.clear()
                continue
            numeric_words = _numeric_words(line)
            valid_numbers = [word for word in numeric_words if is_financial_number(word.text)]
            if not valid_numbers:
                possible_label = _clean_label(
                    "".join(
                        word.text
                        for word in line.words
                        if word.x_center < column_positions[0] - 15
                    )
                )
                if possible_label and not _looks_like_header(possible_label):
                    label_buffer.append(possible_label)
                    label_buffer = label_buffer[-3:]
                continue

            first_value_x = min(word.x0 for word in numeric_words)
            inline_label = _clean_label(
                "".join(word.text for word in line.words if word.x1 < first_value_x - 2)
            )
            label_parts = label_buffer + ([inline_label] if inline_label else [])
            row_label = _clean_label("".join(label_parts))
            label_buffer.clear()
            if not row_label or _looks_like_header(row_label):
                continue

            for word in numeric_words:
                nearest_index = min(
                    range(len(column_positions)),
                    key=lambda index: abs(column_positions[index] - word.x1),
                )
                if abs(column_positions[nearest_index] - word.x1) > 35:
                    continue
                numeric_value, warnings = parse_financial_number(word.text)
                if word.confidence < 0.6:
                    warnings.append("low_ocr_confidence")
                cell_id = f"p{page_number}-{len(cells) + 1}"
                cells.append(
                    FinancialCell(
                        cell_id=cell_id,
                        pdf_page=page_number,
                        printed_page=printed_pages.get(page_number),
                        table=table,
                        period=period,
                        row=row_label,
                        column=columns[nearest_index],
                        raw_value=word.text,
                        numeric_value=numeric_value,
                        confidence=round(word.confidence, 3),
                        source=word.source,
                        bbox=[round(word.x0, 2), round(word.y0, 2), round(word.x1, 2), round(word.y1, 2)],
                        warnings=warnings,
                    )
                )
    return _deduplicate_cells(cells)


def _looks_like_header(label: str) -> bool:
    markers = (
        "中信证券股份有限公司",
        "财务报表",
        "被投资单位名称",
        "项目",
        "账面价值",
        "本期发生额",
        "归属于母公司股东",
        "年月日",
        "即期偿还",
        "3个月内",
        "3个月至1年",
        "1至5年",
        "5年以上",
        "无期限",
    )
    return any(marker in label for marker in markers) or label.isdigit()


def _deduplicate_cells(cells: list[FinancialCell]) -> list[FinancialCell]:
    output: list[FinancialCell] = []
    seen: set[tuple[int, str, str, str]] = set()
    for cell in cells:
        key = (cell.pdf_page, cell.row, cell.column, cell.raw_value)
        if key not in seen:
            output.append(cell)
            seen.add(key)
    return output
