from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

from docqa.models import FinancialCell
from docqa.pipeline import ingest
from docqa.qa_agent import FinancialQAAgent
from docqa.storage import read_jsonl


ROOT = Path(__file__).parent
PDF = ROOT / "data/input/financial-report-sample.pdf"
CELLS = ROOT / "artifacts/cells.jsonl"

st.set_page_config(page_title="智能财务问答助手", layout="wide")
st.title("智能财务问答助手")
st.caption("混合 PDF 解析、表格证据恢复、可追溯问答与可靠性校验")

if st.sidebar.button("重新解析 PDF", type="primary") or not CELLS.exists():
    with st.spinner("正在逐页检测并解析 PDF..."):
        ingest(ROOT, PDF)
    st.sidebar.success("解析完成")

diagnostics = json.loads((ROOT / "artifacts/diagnostics.json").read_text(encoding="utf-8"))
validation = json.loads((ROOT / "artifacts/validation_report.json").read_text(encoding="utf-8"))
cells = read_jsonl(CELLS, FinancialCell)
agent = FinancialQAAgent(cells)

tab_qa, tab_parse, tab_validation = st.tabs(["问答 Agent", "解析结果", "可靠性评估"])

with tab_qa:
    examples = [
        "2025 年 6 月 30 日短期借款合计是多少？",
        "2024 年 12 月 31 日短期借款合计是多少？",
        "2025 年其他综合收益合计期末余额是多少？",
        "短期借款是多少？",
        "2025 年营业收入是多少？",
    ]
    question = st.selectbox("示例问题", examples)
    question = st.text_input("问题", question)
    if st.button("开始问答"):
        answer = agent.ask(question)
        if answer.status == "supported":
            st.success(answer.answer)
        elif answer.status == "needs_review":
            st.warning(answer.answer)
        else:
            st.error(answer.answer)
        left, right = st.columns(2)
        with left:
            st.subheader("引用")
            st.json([asdict(item) for item in answer.citations])
            if answer.citations:
                page = answer.citations[0].pdf_page
                st.image(str(ROOT / f"artifacts/pages/page-{page}.png"), caption=f"PDF 第 {page} 页")
        with right:
            st.subheader("自检")
            st.json([asdict(item) for item in answer.checks])
            st.subheader("检索证据")
            st.json(answer.retrieved_evidence)

with tab_parse:
    st.subheader("逐页路由诊断")
    st.dataframe(pd.DataFrame(diagnostics), use_container_width=True)
    st.subheader("结构化财务单元格")
    table = pd.DataFrame([asdict(cell) for cell in cells])
    selected = st.selectbox("表格", sorted(table["table"].unique()))
    st.dataframe(table[table["table"] == selected], use_container_width=True)

with tab_validation:
    col1, col2, col3 = st.columns(3)
    col1.metric("结构化单元格", validation["cell_count"])
    col2.metric("执行检查", validation["checks"])
    col3.metric("失败检查", validation["failed_checks"])
    st.subheader("失败明细")
    st.dataframe(pd.DataFrame(validation["failures"]), use_container_width=True)
