.DEFAULT_GOAL := help

.PHONY: help install lint format format-check typecheck test test-unit test-cov check clean

help: ## List all targets with descriptions
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install all deps including dev
	uv sync --group dev

lint: ## Run ruff linter
	uv run ruff check src/ tests/

format: ## Format code with ruff
	uv run ruff format src/ tests/

format-check: ## Check formatting without changing files
	uv run ruff format --check src/ tests/

typecheck: ## Run ty type checker
	uv run ty check src/

test: ## Run all tests
	uv run pytest tests/

test-unit: ## Run unit tests only
	uv run pytest tests/ -m unit

test-cov: ## Run tests with coverage
	uv run pytest tests/ --cov=coding_agent

check: lint format-check typecheck ## Run all checks (CI-friendly)

clean: ## Remove build artifacts, caches, __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .coverage htmlcov/
