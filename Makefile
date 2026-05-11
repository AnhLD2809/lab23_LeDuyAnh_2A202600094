.PHONY: install test lint typecheck run-scenarios grade-local run-ui export-graph clean

install:
	pip install -e '.[dev,ui]'

test:
	pytest

lint:
	ruff check src tests

typecheck:
	mypy src

run-scenarios:
	python -m langgraph_agent_lab.cli run-scenarios --config configs/lab.yaml --output outputs/metrics.json

grade-local:
	python -m langgraph_agent_lab.cli validate-metrics --metrics outputs/metrics.json

run-ui:
	python -m streamlit run src/langgraph_agent_lab/streamlit_app.py

export-graph:
	python -m langgraph_agent_lab.cli export-graph --output outputs/graph.mmd

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov dist build *.egg-info outputs/*.json
