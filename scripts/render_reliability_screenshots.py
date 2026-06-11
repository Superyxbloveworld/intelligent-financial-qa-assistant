from __future__ import annotations

import json
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPORT = json.loads((ROOT / "artifacts/reliability_report.json").read_text(encoding="utf-8"))
FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"

WIDTH = 1600
HEIGHT = 1000
SCALE = 1.5
INK = (0.07, 0.13, 0.24)
MUTED = (0.34, 0.41, 0.52)
BLUE = (0.09, 0.36, 0.80)
LIGHT_BLUE = (0.93, 0.96, 1.0)
GREEN = (0.02, 0.47, 0.28)
LIGHT_GREEN = (0.91, 0.98, 0.94)
ORANGE = (0.71, 0.28, 0.03)
LIGHT_ORANGE = (1.0, 0.95, 0.87)
RED = (0.70, 0.13, 0.10)
LIGHT_RED = (1.0, 0.92, 0.92)
WHITE = (1, 1, 1)
LINE = (0.84, 0.87, 0.91)
BACKGROUND = (0.96, 0.97, 0.99)


def page() -> tuple[fitz.Document, fitz.Page]:
    document = fitz.open()
    item = document.new_page(width=WIDTH, height=HEIGHT)
    item.draw_rect(item.rect, color=BACKGROUND, fill=BACKGROUND)
    return document, item


def text(
    item: fitz.Page,
    box: fitz.Rect,
    value: object,
    size: float = 18,
    color: tuple[float, float, float] = INK,
    align: int = fitz.TEXT_ALIGN_LEFT,
) -> None:
    item.insert_textbox(
        box,
        str(value),
        fontsize=size,
        fontname="zh",
        fontfile=FONT_PATH,
        color=color,
        align=align,
        lineheight=1.25,
    )


def header(item: fitz.Page, title: str, subtitle: str) -> None:
    item.draw_rect(fitz.Rect(0, 0, WIDTH, 125), color=(0.04, 0.17, 0.36), fill=(0.04, 0.17, 0.36))
    text(item, fitz.Rect(56, 30, 1500, 76), title, 32, WHITE)
    text(item, fitz.Rect(56, 80, 1500, 112), subtitle, 16, (0.78, 0.87, 1.0))


def section_title(item: fitz.Page, y: float, title: str) -> float:
    text(item, fitz.Rect(56, y, 1500, y + 36), title, 22, INK)
    item.draw_line(fitz.Point(56, y + 38), fitz.Point(1544, y + 38), color=LINE, width=1)
    return y + 52


def metric(item: fitz.Page, x: float, y: float, label: str, value: object, color=BLUE) -> None:
    rect = fitz.Rect(x, y, x + 330, y + 112)
    item.draw_rect(rect, radius=0.08, color=color, fill=LIGHT_BLUE, width=1.2)
    text(item, fitz.Rect(x + 18, y + 15, x + 312, y + 43), label, 15, MUTED)
    text(item, fitz.Rect(x + 18, y + 49, x + 312, y + 94), value, 28, color)


def pill(
    item: fitz.Page,
    x: float,
    y: float,
    value: str,
    status: str,
) -> None:
    colors = {
        "supported": (GREEN, LIGHT_GREEN),
        "needs_review": (ORANGE, LIGHT_ORANGE),
        "no_answer": (RED, LIGHT_RED),
        "clarification_required": (RED, LIGHT_RED),
    }
    ink, fill = colors.get(status, (BLUE, LIGHT_BLUE))
    width = max(118, len(value) * 9 + 24)
    item.draw_rect(fitz.Rect(x, y, x + width, y + 29), radius=0.5, color=ink, fill=fill)
    text(item, fitz.Rect(x + 8, y + 5, x + width - 6, y + 25), value, 12, ink)


def table(
    item: fitz.Page,
    x: float,
    y: float,
    widths: list[float],
    headers: list[str],
    rows: list[list[object]],
    row_height: float = 42,
    sizes: list[float] | None = None,
) -> None:
    sizes = sizes or [13] * len(headers)
    current_x = x
    for width, header_value, size in zip(widths, headers, sizes):
        box = fitz.Rect(current_x, y, current_x + width, y + row_height)
        item.draw_rect(box, color=LINE, fill=(0.95, 0.97, 1.0), width=0.8)
        text(item, box + (8, 8, -6, -4), header_value, size, INK)
        current_x += width
    for index, row in enumerate(rows):
        row_y = y + row_height * (index + 1)
        current_x = x
        for width, value, size in zip(widths, row, sizes):
            box = fitz.Rect(current_x, row_y, current_x + width, row_y + row_height)
            item.draw_rect(box, color=LINE, fill=WHITE, width=0.6)
            text(item, box + (8, 6, -5, -4), value, size, INK)
            current_x += width


def card(
    item: fitz.Page,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    body: str,
    status: str,
    footer: str,
) -> None:
    item.draw_rect(fitz.Rect(x, y, x + width, y + height), radius=0.04, color=LINE, fill=WHITE)
    pill(item, x + 14, y + 13, status, status)
    text(item, fitz.Rect(x + 14, y + 52, x + width - 14, y + 88), title, 15, INK)
    text(item, fitz.Rect(x + 14, y + 91, x + width - 14, y + height - 36), body, 13, MUTED)
    text(item, fitz.Rect(x + 14, y + height - 29, x + width - 14, y + height - 8), footer, 11, BLUE)


def save(document: fitz.Document, name: str) -> None:
    pixmap = document[0].get_pixmap(matrix=fitz.Matrix(SCALE, SCALE), alpha=False)
    pixmap.save(DOCS / name)
    document.close()


def render_parse() -> None:
    document, item = page()
    header(item, "可靠性验证 1/5：PDF 解析结果", "展示正文、表格、逐页类型判断与解析路由")
    metric(item, 56, 155, "PDF 页数", 6)
    metric(item, 429, 155, "原生文本页", 5)
    metric(item, 802, 155, "扫描 OCR 页", 1, ORANGE)
    metric(item, 1175, 155, "结构化单元格", REPORT["validation"]["cell_count"], GREEN)
    y = section_title(item, 300, "逐页解析路由")
    rows = [
        [
            value["pdf_page"],
            value["printed_page"],
            value["page_type"],
            value["parser"],
            value["orientation"],
            value["native_text_chars"],
            "；".join(value["warnings"]) or "-",
        ]
        for value in REPORT["diagnostics"]
    ]
    table(item, 56, y, [90, 120, 150, 190, 150, 150, 530], ["PDF页", "原报告页", "类型", "解析器", "方向", "原生字符", "告警"], rows, 45)
    y2 = section_title(item, 685, "表格结构化示例")
    excerpt = REPORT["body_examples"][1]["excerpt"].replace("\n", " ")[:115]
    text(item, fitz.Rect(70, y2, 1510, y2 + 48), f"正文解析示例（PDF 第 5 页）：{excerpt}…", 13, MUTED)
    examples = [
        value
        for value in REPORT["table_examples"]
        if value["column"] in {"合计", "5年以上", "归属于母公司股东的其他综合收益期末余额"}
    ][:3]
    table(
        item,
        56,
        y2 + 52,
        [90, 160, 330, 370, 230, 160, 140],
        ["页", "期间", "行", "列", "原始值", "来源", "置信度"],
        [[x["pdf_page"], x["period"], x["row"], x["column"], x["raw_value"], x["source"], x["confidence"]] for x in examples],
        40,
        [13, 13, 12, 11, 13, 12, 12],
    )
    save(document, "reliability-01-pdf-parse.png")


def render_qa() -> None:
    document, item = page()
    header(item, "可靠性验证 2/5：代表性问答与边界行为", "覆盖表格、扫描 OCR、模糊问题与无答案问题")
    positions = [(56, 155), (812, 155), (56, 418), (812, 418), (56, 681), (812, 681)]
    for (x, y), value in zip(positions, REPORT["qa_results"]):
        card(
            item,
            x,
            y,
            700,
            230,
            f'{value["category"]}：{value["question"]}',
            value["answer"],
            value["status"],
            f'confidence={value["confidence"]}',
        )
    save(document, "reliability-02-qa-results.png")


def render_checks() -> None:
    document, item = page()
    header(item, "可靠性验证 3/5：来源引用与自检", "每个答案可追溯至 PDF 页、原报告页和结构化 cell_id")
    y = section_title(item, 155, "代表性回答的引用与检查")
    selected = [REPORT["qa_results"][0], REPORT["qa_results"][1], REPORT["qa_results"][4], REPORT["qa_results"][5]]
    rows = []
    for value in selected:
        citation = value["citations"][0] if value["citations"] else {}
        failed = [check["name"] for check in value["checks"] if not check["passed"]]
        rows.append(
            [
                value["category"],
                value["status"],
                citation.get("pdf_page", "-"),
                citation.get("printed_page", "-"),
                citation.get("cell_id", "-"),
                "，".join(failed) or "全部通过/无检查项",
            ]
        )
    table(item, 56, y, [260, 190, 130, 160, 210, 530], ["问题类型", "状态", "PDF页", "原报告页", "cell_id", "未通过检查"], rows, 54)
    y2 = section_title(item, 480, "OCR 错误处理示例")
    item.draw_rect(fitz.Rect(56, y2, 1544, y2 + 190), radius=0.04, color=ORANGE, fill=LIGHT_ORANGE, width=1.2)
    text(item, fitz.Rect(80, y2 + 22, 1500, y2 + 58), "问题：2024 年应付债券 5 年以上是多少？", 18, INK)
    text(item, fitz.Rect(80, y2 + 67, 1500, y2 + 104), "OCR 原始值：26.075,352,739.73", 24, ORANGE)
    text(item, fitz.Rect(80, y2 + 112, 1500, y2 + 168), "numeric_format 失败 + extraction_confidence=0.30，因此返回 needs_review；保留原始值和来源页，不静默修正。", 15, INK)
    y3 = section_title(item, 755, "自检规则")
    rules = [
        "citation_exists：引用单元格与页码真实存在",
        "numeric_format：财务数字格式合法",
        "extraction_confidence：OCR 置信度达到阈值",
        "row_sum_consistency：合计值与已提取明细勾稽",
    ]
    for index, rule in enumerate(rules):
        text(item, fitz.Rect(70 + (index % 2) * 740, y3 + (index // 2) * 52, 760 + (index % 2) * 740, y3 + 40 + (index // 2) * 52), f"{index + 1}. {rule}", 15, INK)
    save(document, "reliability-03-citations-checks.png")


def render_test() -> None:
    document, item = page()
    header(item, "可靠性验证 4/5：测试与评估结果", "同时验证状态、精确数值、引用页码和 OCR 风险")
    metric(item, 56, 155, "自动化测试", REPORT["pytest"]["summary"].split(",")[0], GREEN)
    metric(item, 429, 155, "黄金问题", REPORT["evaluation"]["total"])
    metric(item, 802, 155, "黄金集通过率", f'{REPORT["evaluation"]["pass_rate"] * 100:.0f}%', GREEN)
    metric(item, 1175, 155, "可靠性失败项", REPORT["validation"]["failed_checks"], ORANGE)
    y = section_title(item, 305, "黄金问题评估结果")
    rows = [
        [value["question"], value["actual_status"], "通过" if value["passed"] else "失败", "正确" if value["citation_ok"] else "错误"]
        for value in REPORT["evaluation"]["results"][:8]
    ]
    table(item, 56, y, [850, 220, 190, 220], ["问题", "实际状态", "整体结果", "引用页码"], rows, 50, [13, 13, 13, 13])
    y2 = section_title(item, 805, "评估覆盖与解析风险")
    text(item, fitz.Rect(70, y2, 760, y2 + 100), "覆盖：原生表格、扫描 OCR、多级表头、投资明细、模糊问题、无答案问题、OCR 非法数字格式。", 15, INK)
    text(item, fitz.Rect(810, y2, 1500, y2 + 100), f'解析检查：{REPORT["validation"]["checks"]} 项；低置信度 OCR {REPORT["validation"]["warning_counts"].get("low_ocr_confidence", 0)} 项；非法数字格式 {REPORT["validation"]["warning_counts"].get("invalid_numeric_format", 0)} 项。', 15, INK)
    save(document, "reliability-04-test-evaluation.png")


def render_reasoning() -> None:
    document, item = page()
    header(item, "可靠性验证 5/5：工程判断与 AI Coding 校验", "展示真实观察如何改变方案，以及每个判断如何被验证")
    y = section_title(item, 155, "关键决策与验证记录")
    rows = [
        [value["observation"], value["decision"], value["verification"], value["result"]]
        for value in REPORT["decision_records"]
    ]
    table(
        item,
        56,
        y,
        [300, 430, 410, 340],
        ["实际观察", "我的判断与取舍", "验证方式", "结果"],
        rows,
        72,
        [12, 11, 11, 11],
    )
    y2 = section_title(item, 700, "AI Coding 校验原则")
    for index, value in enumerate(REPORT["ai_coding_lessons"]):
        x = 70 + (index % 2) * 740
        row_y = y2 + (index // 2) * 62
        text(item, fitz.Rect(x, row_y, x + 690, row_y + 55), f"{index + 1}. {value}", 13, INK)
    save(document, "reliability-05-engineering-reasoning.png")


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    render_parse()
    render_qa()
    render_checks()
    render_test()
    render_reasoning()
    for name in [
        "reliability-01-pdf-parse.png",
        "reliability-02-qa-results.png",
        "reliability-03-citations-checks.png",
        "reliability-04-test-evaluation.png",
        "reliability-05-engineering-reasoning.png",
    ]:
        print(f"Generated {DOCS / name}")


if __name__ == "__main__":
    main()
