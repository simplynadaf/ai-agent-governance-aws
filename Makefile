# AI Agent Governance on AWS - one-command demo targets.
# .env is auto-loaded by the code (src/_env.py via python-dotenv), so you do NOT need to
# `source .env`. The repo already ships a .env (keys commented out) - just paste your key
# into it for the platform payoff, then `make demo`.

# Auto-detect a Python 3 interpreter (python3 on most systems; python on some). Override:
#   make PY=python3.11 setup
PY ?= $(shell command -v python3 || command -v python)
VENV ?= .venv
VPY := $(VENV)/bin/python

.DEFAULT_GOAL := help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create venv + install pinned deps + git hooks
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install -U pip
	$(VPY) -m pip install -r requirements.txt
	bash scripts/install-hooks.sh || true
	@echo "Setup done. The repo already has .env (keys commented). Paste your TRACCIA_API_KEY into .env for the platform payoff (optional - the \$$0 beats run without it)."

demo:  ## Run the 3 governance beats ($0, no key needed) -> traces_gov.jsonl
	$(VPY) -m src.loan_crew

scenarios:  ## Run the 5 named scenarios (approve/refer/decline/EU/injection)
	$(VPY) -m src.demo_scenarios

verify:  ## Print the plain-language governance report + 3-tier coverage from the trace
	$(VPY) -m src.verify_trace

platform:  ## Run the crew under @govern (needs TRACCIA_API_KEY + TRACCIA_ENDPOINT in .env)
	$(VPY) -m src.govern_platform

test:  ## Run unit tests
	$(VPY) -m pytest tests/ -q

all: demo verify test  ## $0 demo + report + tests

clean:  ## Remove trace output + caches
	rm -f traces_gov.jsonl
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

.PHONY: help setup demo scenarios verify platform test all clean
