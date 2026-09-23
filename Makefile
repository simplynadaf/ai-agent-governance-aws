# AI Agent Governance on AWS — one-command demo targets.
# .env is auto-loaded by the code (src/_env.py via python-dotenv), so you do NOT need to
# `source .env`. Just: cp .env.example .env, paste your key, then `make demo`.

PY ?= python
VENV ?= .venv

.DEFAULT_GOAL := help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create venv + install pinned deps + git hooks
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install -U pip
	$(VENV)/bin/pip install -r requirements.txt
	@[ -f .env ] || cp .env.example .env
	bash scripts/install-hooks.sh || true
	@echo "Setup done. Put your TRACCIA_API_KEY in .env (optional — the \$$0 beats run without it)."

demo:  ## Run the 3 governance beats ($0, no key needed) -> traces_gov.jsonl
	$(VENV)/bin/python -m src.loan_crew

scenarios:  ## Run the 5 named scenarios (approve/refer/decline/EU/injection)
	$(VENV)/bin/python -m src.demo_scenarios

verify:  ## Print the plain-language governance report + 3-tier coverage from the trace
	$(VENV)/bin/python -m src.verify_trace

platform:  ## Run the crew under @govern (needs TRACCIA_API_KEY + TRACCIA_ENDPOINT in .env)
	$(VENV)/bin/python -m src.govern_platform

test:  ## Run unit tests
	$(VENV)/bin/python -m pytest tests/ -q

all: demo verify test  ## $0 demo + report + tests

clean:  ## Remove trace output + caches
	rm -f traces_gov.jsonl
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

.PHONY: help setup demo scenarios verify platform test all clean
