.DEFAULT_GOAL := help
UV ?= uv
IMAGE ?= mcp-frankfurter

.PHONY: help dev run-http test scenarios mutation lint fmt docker-build docker-run secrets-scan

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

dev: ## Install dependencies and run the server on stdio
	$(UV) sync
	$(UV) run mcp-frankfurter

run-http: ## Run over streamable HTTP (needs MCP_AUTH_TOKEN in the environment or .env)
	MCP_TRANSPORT=streamable-http $(UV) run mcp-frankfurter

test: ## Run the test suite with the 100 % line+branch coverage gate (no network needed)
	$(UV) run --locked pytest -q --cov --cov-report=term-missing

scenarios: ## Check that every ID in docs/scenarios.md is covered by both integration suites
	$(UV) run --locked python scripts/check_scenarios.py

mutation: ## Mutation testing on server.py/upstream.py/mappers.py; 0 survivors (Linux or WSL only)
	$(UV) run --locked mutmut run
	$(UV) run --locked mutmut export-cicd-stats
	$(UV) run --locked python scripts/check_mutants.py

lint: ## ruff check, ruff format --check, mypy src
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .
	$(UV) run --locked mypy src

fmt: ## Fix lint findings and reformat
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

docker-build: ## Build the image
	docker build -t $(IMAGE) .

docker-run: ## Run the image on port 8000 with the variables from .env
	docker run --rm -p 8000:8000 --env-file .env $(IMAGE)

secrets-scan: ## Local reproduction of the gitleaks-history CI job (full git history)
	bash scripts/scan-secrets-local.sh
