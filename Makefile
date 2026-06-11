PYTHON := PYTHONPATH=src uv run python
PDF := data/input/financial-report-sample.pdf

.PHONY: setup ingest run ask test eval report all

setup:
	uv sync --dev

ingest:
	$(PYTHON) -m docqa.cli ingest "$(PDF)"

run: ingest
	$(PYTHON) web_app.py

run-streamlit: ingest
	uv run --extra streamlit streamlit run app.py

ask:
	$(PYTHON) -m docqa.cli ask "2025 年 6 月 30 日短期借款合计是多少？"

test:
	uv run pytest -q

eval: ingest
	$(PYTHON) -m docqa.cli evaluate eval/golden_questions.jsonl

report: ingest eval
	$(PYTHON) scripts/generate_reliability_report.py
	$(PYTHON) scripts/render_reliability_screenshots.py

all: ingest test eval report
