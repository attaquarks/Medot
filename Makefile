# AIA — common operations.  Run `make help` for the list.
SHELL := /bin/bash
COMPOSE := docker compose

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## First-run: copy env, build images, pull local models, run migrations
	@test -f .env || cp .env.example .env
	$(COMPOSE) build
	$(COMPOSE) up -d postgres redis ollama
	./scripts/pull-models.sh
	$(MAKE) migrate

.PHONY: onboard
onboard: ## Launch the setup wizard at http://localhost:8088
	$(COMPOSE) up -d onboarding
	@echo "Open http://localhost:8088 to connect your accounts."

.PHONY: up
up: ## Start the whole stack
	$(COMPOSE) up -d

.PHONY: down
down: ## Stop the stack (keeps data volumes)
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail logs for all services
	$(COMPOSE) logs -f --tail=100

.PHONY: migrate
migrate: ## Initialise/upgrade the database schema (idempotent)
	$(COMPOSE) run --rm gateway python -m aia.db.init

.PHONY: test
test: ## Run the test suite
	$(COMPOSE) run --rm gateway pytest -q

.PHONY: fmt
fmt: ## Format & lint
	ruff check --fix . && ruff format .

.PHONY: clean
clean: ## Stop and DELETE all data volumes (irreversible)
	$(COMPOSE) down -v
