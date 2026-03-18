.PHONY: install dev test lint format clean run help eval eval-quick eval-dry

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies using uv
	uv sync
	@echo "✓ Dependencies installed"

dev: ## Run development server with hot reload
	uv run uvicorn omni_agent.main:app --reload --host 0.0.0.0 --port 8000

run: ## Run production server
	uv run uvicorn omni_agent.main:app --host 0.0.0.0 --port 8000

test: ## Run tests with pytest
	uv run pytest -v

test-cov: ## Run tests with coverage report
	uv run pytest -v --cov=src/omni_agent --cov-report=term-missing --cov-report=html

lint: ## Run linter (ruff check)
	uv run ruff check .

lint-fix: ## Run linter and fix issues automatically
	uv run ruff check --fix .

format: ## Format code with ruff
	uv run ruff format .

format-check: ## Check code formatting without making changes
	uv run ruff format --check .

type-check: ## Run type checking with mypy
	uv run mypy src/omni_agent

check: lint format-check type-check ## Run all checks (lint, format, type)

clean: ## Clean up temporary files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	@echo "✓ Cleaned up temporary files"

verify: ## Verify project setup and configuration
	uv run python verify_setup.py

eval: ## Run full evaluation suite
	uv run python -m omni_agent.eval evals/

eval-quick: ## Run quick eval (tool_usage only, 30s timeout)
	uv run python -m omni_agent.eval evals/tool_usage/ --timeout 30

eval-dry: ## List eval cases without running
	uv run python -m omni_agent.eval evals/ --dry-run

.DEFAULT_GOAL := help
