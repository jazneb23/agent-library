.PHONY: setup test lint eval-hello run-hello
setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
test:
	python -m pytest -q
lint:
	ruff check .
eval-hello:
	python -m evals.runner hello --runs 3
run-hello:
	python -m agents.hello.agent
