.PHONY: setup test lint eval-hello run-hello ingest-rfp eval-rfp-fast eval-rfp-full
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
ingest-rfp:
	python -m agents.rfp.ingest
# Cheap: 6 key cases, Haiku, 1 run, hard cap. Use this while iterating.
eval-rfp-fast:
	AGENT_MODEL=claude-haiku-4-5-20251001 python -m evals.runner rfp --tag smoke --runs 1 --max-cost 0.25
# Milestones only (baseline, after each improvement). Haiku by default; drop AGENT_MODEL to use Sonnet.
eval-rfp-full:
	AGENT_MODEL=claude-haiku-4-5-20251001 python -m evals.runner rfp --runs 3 --max-cost 1.00
