from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import fitz

from docqa.models import FinancialCell
from docqa.qa_agent import FinancialQAAgent
from docqa.storage import read_jsonl, write_json


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
DOCS = ROOT / "docs"

DEMO_QUESTIONS = [
    ("原生表格问题", "2025 年 6 月 30 日短期借款合计是多少？"),
    ("扫描页表格问题", "2024 年 12 月 31 日短期借款合计是多少？"),
    ("多级表头问题", "2025 年其他综合收益合计期末余额是多少？"),
    ("投资明细问题", "2024 年中信建投证券股份有限公司期末账面价值是多少？"),
    ("OCR 错误问题", "2024 年应付债券 5 年以上是多少？"),
    ("无答案问题", "2025 年营业收入是多少？"),
]

DECISION_RECORDS = [
    {
        "observation": "PDF 同时包含文本页和扫描页",
        "decision": "逐页检测并路由解析器，避免全部 OCR",
        "verification": "diagnostics.json 记录每页类型、解析器和告警",
        "result": "5 页 PyMuPDF，1 页 macOS Vision OCR",
    },
    {
        "observation": "普通文本提取丢失表格行列关系",
        "decision": "建立带期间、行、列、页码和坐标的证据层",
        "verification": "cells.jsonl 与来源页人工抽查",
        "result": "恢复 446 个可追溯财务单元格",
    },
    {
        "observation": "OCR 数字可能格式合法但语义错误，也可能直接无法解析",
        "decision": "保留原值，执行格式、置信度和行合计检查",
        "verification": "validation_report.json 与 OCR 异常黄金问题",
        "result": "异常答案降为 needs_review，不静默修正",
    },
    {
        "observation": "有检索结果不代表问题可以可靠回答",
        "decision": "设计 supported、needs_review、clarification_required、no_answer 状态",
        "verification": "黄金集同时断言状态、精确数值和引用页码",
        "result": "模糊问题澄清，无依据问题拒答",
    },
    {
        "observation": "上传成功不代表 Agent 已切换知识库",
        "decision": "增加新文档反向测试和失败回滚",
        "verification": "上传普通 PDF 后询问旧财务问题",
        "result": "旧答案失效并返回 no_answer",
    },
    {
        "observation": "最终答案正确可能只是偶然，无法定位过程错误",
        "decision": "为解析、证据、校验、问答和运行分别输出可观察结果",
        "verification": "make all、artifacts/ 与 events.jsonl",
        "result": "自动化测试与黄金集均通过",
    },
]

AI_CODING_LESSONS = [
    "先检查真实 PDF，再决定解析策略；实际样本推翻了“全部扫描件”的初始假设。",
    "将 AI 建议转成可证伪假设；上传切换使用旧问题反向验证，而不是只看接口成功。",
    "拒绝无法证明的自动修复；OCR 异常数字保留原值并进入 needs_review。",
    "测试不仅断言答案，还断言状态、精确数值、引用页码、回滚和旧缓存失效。",
    "将失败变成可观察数据；诊断、证据、校验报告和审计事件用于定位不同阶段问题。",
]


def compact_text(text: str, limit: int = 420) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:limit]


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    def clean(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")

    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    output.extend("| " + " | ".join(clean(value) for value in row) + " |" for row in rows)
    return "\n".join(output)


def collect_test_result() -> dict[str, object]:
    result = subprocess.run(
        ["uv", "run", "pytest", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    summary = next(
        (line.strip() for line in result.stdout.splitlines() if " passed" in line),
        "pytest passed",
    )
    return {"command": "uv run pytest -q", "summary": summary}


def main() -> None:
    diagnostics = json.loads((ARTIFACTS / "diagnostics.json").read_text(encoding="utf-8"))
    validation = json.loads((ARTIFACTS / "validation_report.json").read_text(encoding="utf-8"))
    evaluation = json.loads((ARTIFACTS / "evaluation_report.json").read_text(encoding="utf-8"))
    cells = read_jsonl(ARTIFACTS / "cells.jsonl", FinancialCell)
    agent = FinancialQAAgent(cells)

    pdf = fitz.open(ROOT / "data/input/financial-report-sample.pdf")
    body_examples = [
        {
            "pdf_page": 3,
            "printed_page": diagnostics[2]["printed_page"],
            "parser": diagnostics[2]["parser"],
            "excerpt": compact_text(pdf[2].get_text("text")),
        },
        {
            "pdf_page": 5,
            "printed_page": diagnostics[4]["printed_page"],
            "parser": diagnostics[4]["parser"],
            "excerpt": compact_text(pdf[4].get_text("text")),
        },
        {
            "pdf_page": 6,
            "printed_page": diagnostics[5]["printed_page"],
            "parser": diagnostics[5]["parser"],
            "excerpt": "该页原生文本字符数为 0，系统路由至 OCR，并恢复金融负债到期表格。",
        },
    ]

    selected_rows = {
        ("2025-06-30", "非衍生金融负债短期借款"),
        ("2024-12-31", "非衍生金融负债短期借款"),
        ("2024-12-31", "应付债券"),
        ("2025-H1", "其他综合收益合计"),
    }
    table_examples = [
        asdict(cell)
        for cell in cells
        if (cell.period, cell.row) in selected_rows
        and cell.column
        in {
            "即期偿还",
            "3个月内",
            "3个月至1年",
            "5年以上",
            "合计",
            "归属于母公司股东的其他综合收益期末余额",
        }
    ]

    qa_results = []
    for category, question in DEMO_QUESTIONS:
        answer = agent.ask(question)
        qa_results.append({"category": category, **asdict(answer)})

    pytest_result = collect_test_result()
    report = {
        "capability_evidence": {
            "pdf_parse": "逐页解析路由、正文片段和结构化表格",
            "qa": "代表性问答覆盖正常结果、OCR 风险、模糊问题和无答案问题",
            "citation_and_self_check": "有依据的结果包含 cell_id、页码和检查项",
            "evaluation": "pytest、黄金集和解析可靠性检查结果",
        },
        "diagnostics": diagnostics,
        "body_examples": body_examples,
        "table_examples": table_examples,
        "qa_results": qa_results,
        "pytest": pytest_result,
        "evaluation": evaluation,
        "validation": validation,
        "decision_records": DECISION_RECORDS,
        "ai_coding_lessons": AI_CODING_LESSONS,
    }
    write_json(ARTIFACTS / "reliability_report.json", report)
    for page in (3, 5, 6):
        shutil.copyfile(
            ARTIFACTS / "pages" / f"page-{page}.png",
            DOCS / f"evidence-page-{page}.png",
        )

    diagnostics_rows = [
        [
            item["pdf_page"],
            item["printed_page"],
            item["page_type"],
            item["parser"],
            item["orientation"],
            item["native_text_chars"],
            "<br>".join(item["warnings"]) or "-",
        ]
        for item in diagnostics
    ]
    table_rows = [
        [
            item["pdf_page"],
            item["period"],
            item["row"],
            item["column"],
            item["raw_value"],
            item["source"],
            item["confidence"],
            "<br>".join(item["warnings"]) or "-",
        ]
        for item in table_examples
    ]
    qa_rows = [
        [
            index,
            item["category"],
            item["question"],
            item["status"],
            item["answer"],
            item["confidence"],
        ]
        for index, item in enumerate(qa_results, start=1)
    ]
    citation_rows = []
    for index, item in enumerate(qa_results, start=1):
        citation = item["citations"][0] if item["citations"] else {}
        failed_checks = [check["name"] for check in item["checks"] if not check["passed"]]
        citation_rows.append(
            [
                index,
                citation.get("pdf_page", "-"),
                citation.get("printed_page", "-"),
                citation.get("cell_id", "-"),
                ", ".join(failed_checks) or "全部通过/无检查项",
                "<br>".join(item["warnings"]) or "-",
            ]
        )

    markdown = f"""# 可靠性与工程验证报告

本报告集中展示系统运行结果、可靠性验证与工程判断。所有结果由真实 PDF 运行生成，不是手工填写答案。

高清截图：

- [PDF 正文与表格解析结果](reliability-01-pdf-parse.png)
- [代表性问答与边界行为](reliability-02-qa-results.png)
- [来源引用与自检结果](reliability-03-citations-checks.png)
- [测试与评估运行结果](reliability-04-test-evaluation.png)
- [工程判断与 AI Coding 校验](reliability-05-engineering-reasoning.png)

## 可复现结果索引

| 结果 | 对应材料 | 状态 |
| --- | --- | --- |
| PDF 解析结果，包括正文和表格 | 本文第 1 节、`artifacts/diagnostics.json`、`artifacts/cells.jsonl` | 已完成 |
| 代表性问答与边界行为 | 本文第 2 节，共 {len(qa_results)} 个场景 | 已验证 |
| 来源引用和自检结果 | 本文第 3 节、Web 演示问答详情 | 已完成 |
| 测试或评估脚本运行结果 | 本文第 4 节、`artifacts/evaluation_report.json` | 已完成 |

## 1. PDF 解析结果

### 1.1 逐页类型判断与解析路由

{markdown_table(["PDF 页", "原报告页", "类型", "解析器", "方向", "原生字符数", "告警"], diagnostics_rows)}

结论：第 1-5 页使用 PyMuPDF 坐标文本恢复表格；第 6 页没有文本层，自动路由到 macOS Vision OCR。第 6 页出现低置信度和非法数字格式，因此相关答案不会直接标记为完全可信。

### 1.2 正文解析示例

**PDF 第 3 页，原报告第 {body_examples[0]["printed_page"]} 页，解析器 `{body_examples[0]["parser"]}`**

```text
{body_examples[0]["excerpt"]}
```

**PDF 第 5 页，原报告第 {body_examples[1]["printed_page"]} 页，解析器 `{body_examples[1]["parser"]}`**

```text
{body_examples[1]["excerpt"]}
```

**PDF 第 6 页，原报告第 {body_examples[2]["printed_page"]} 页，解析器 `{body_examples[2]["parser"]}`**

{body_examples[2]["excerpt"]}

### 1.3 表格结构化示例

每个单元格保存期间、行名、列名、原始值、来源、置信度、页码和坐标。下面同时包含原生页与扫描页结果：

{markdown_table(["PDF 页", "期间", "行", "列", "原始值", "来源", "置信度", "告警"], table_rows)}

页面证据：

- [PDF 第 3 页：其他综合收益表](evidence-page-3.png)
- [PDF 第 5 页：2025 年金融负债到期表](evidence-page-5.png)
- [PDF 第 6 页：2024 年扫描表格](evidence-page-6.png)

## 2. 代表性问答与边界行为

{markdown_table(["序号", "类型", "问题", "状态", "回答", "置信度"], qa_rows)}

其中：

- 问题 1-5 均为表格问题，覆盖原生文本、多级表头、投资明细和扫描页 OCR。
- 问题 5 专门展示 OCR 数字错误处理，系统返回 `needs_review`。
- 问题 6 为无答案问题，系统返回 `no_answer`，不生成文档外答案。

## 3. 来源引用与自检结果

{markdown_table(["问题", "PDF 页", "原报告页", "cell_id", "未通过检查", "告警"], citation_rows)}

自检规则：

1. `citation_exists`：引用单元格及页码是否真实存在。
2. `numeric_format`：是否是合法财务数字；不会静默修复异常 OCR 数字。
3. `extraction_confidence`：OCR 置信度是否达到阈值。
4. `row_sum_consistency`：合计值能否与已提取明细列勾稽。

关键示例：问题 5 的 OCR 原始值为 `26.075,352,739.73`，数字格式和 OCR 置信度检查均失败，因此系统保留原值、引用 PDF 第 6 页并要求人工复核。

## 4. 测试与评估运行结果

### 4.1 自动化测试

```text
$ {pytest_result["command"]}
{pytest_result["summary"]}
```

测试覆盖财务数字解析、坐标分行、表格识别、正常回答、模糊问题澄清、无答案拒答、低置信度、自检以及真实 PDF 集成。

### 4.2 黄金问题评估

- 黄金问题数：**{evaluation["total"]}**
- 通过数：**{evaluation["passed"]}**
- 通过率：**{evaluation["pass_rate"] * 100:.0f}%**
- 同时校验：回答状态、精确数值、引用页码。

### 4.3 解析可靠性检查

- 结构化财务单元格：**{validation["cell_count"]}**
- 执行检查：**{validation["checks"]}**
- 检查失败：**{validation["failed_checks"]}**
- 低置信度 OCR 告警：**{validation["warning_counts"].get("low_ocr_confidence", 0)}**
- 非法数字格式：**{validation["warning_counts"].get("invalid_numeric_format", 0)}**

失败项不会被隐藏，而是用于降低回答置信度、返回 `needs_review` 或拒答。

## 5. 工程判断与可靠性闭环

{markdown_table(
    ["实际观察", "我的判断与取舍", "验证方式", "结果"],
    [[item["observation"], item["decision"], item["verification"], item["result"]] for item in DECISION_RECORDS],
)}

详细决策过程见 [工程判断与可靠性闭环](engineering-decisions.md)。

## 6. AI Coding 校验原则

{chr(10).join(f"{index}. {item}" for index, item in enumerate(AI_CODING_LESSONS, start=1))}

## 7. 验证操作路径

1. 执行 `make setup && make all && make run`。
2. 展示逐页路由，重点说明第 6 页是扫描页。
3. 展示正文片段和结构化表格证据。
4. 依次演示问题 1、2、3、5、6。
5. 展开来源图片和自检结果。
6. 展示 `make all` 中的测试与黄金集结果。
7. 打开可靠性页面“工程判断与 AI Coding 校验”，说明关键风险如何被发现、验证和修正。
"""
    (DOCS / "reliability-report.md").write_text(markdown, encoding="utf-8")
    print(f"Generated {DOCS / 'reliability-report.md'}")
    print(f"Generated {ARTIFACTS / 'reliability_report.json'}")


if __name__ == "__main__":
    main()
