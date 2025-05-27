.PHONY: help install install-dev test lint format clean build upload

help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package
	uv sync

install-dev:  ## Install the package with development dependencies
	uv sync --dev

test:  ## Run tests
	uv run pytest tests/ -v

test-cov:  ## Run tests with coverage
	uv run pytest tests/ --cov=gmail_to_sqlite --cov-report=html --cov-report=term

lint:  ## Run linting
	uv run flake8 gmail_to_sqlite tests
	uv run mypy gmail_to_sqlite

format:  ## Format code
	uv run black gmail_to_sqlite tests

format-check:  ## Check code formatting
	uv run black --check gmail_to_sqlite tests

clean:  ## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:  ## Build the package
	uv build

upload:  ## Upload to PyPI (requires authentication)
	uv publish

dev-setup:  ## Set up development environment
	uv sync --dev
	uv run pre-commit install

run:  ## Run the application (requires credentials.json)
	uv run python -m gmail_to_sqlite

run-cli:  ## Run via installed CLI command
	uv run gmail-to-sqlite
