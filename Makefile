.PHONY: install install-dev test test-security test-integration lint typecheck compile-example clean help

PYTHON ?= python3
PIP ?= pip3
PROJECT_ROOT := $(shell pwd)

help: ## Show this help message
	@echo "WasmBox Compiler Pipeline — Make Targets"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install core dependencies
	$(PIP) install -e .

install-dev: ## Install with development dependencies
	$(PIP) install -e ".[all]"

test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v --tb=short

test-security: ## Run security tests only
	$(PYTHON) -m pytest tests/ -v -m security --tb=short

test-integration: ## Run integration tests only
	$(PYTHON) -m pytest tests/ -v -m integration --tb=short

test-cov: ## Run tests with coverage
	$(PYTHON) -m pytest tests/ -v --cov=backend --cov-report=term-missing

lint: ## Run linter
	$(PYTHON) -m ruff check backend/ tests/

typecheck: ## Run type checker
	$(PYTHON) -m mypy backend/

compile-example: ## Compile all example plugins
	@echo "Compiling example plugins..."
	@for f in examples/plugins/*.py; do \
		echo "--- Compiling $$f ---"; \
		$(PYTHON) -m backend.compiler.cli compile "$$f" --output-dir examples/compiled/ 2>&1 || true; \
		echo ""; \
	done

compile-hello: ## Compile the hello example plugin
	$(PYTHON) -m backend.compiler.cli compile examples/plugins/hello.py --output-dir examples/compiled/

validate: ## Validate a compiled WASM artifact (usage: make validate FILE=path/to/plugin.wasm)
	$(PYTHON) -m backend.compiler.cli validate $(FILE)

inspect: ## Inspect a WASM artifact (usage: make inspect FILE=path/to/plugin.wasm)
	$(PYTHON) -m backend.compiler.cli inspect $(FILE)

env: ## Show compiler environment diagnostics
	$(PYTHON) -m backend.compiler.cli env

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info
	rm -rf examples/compiled/*.wasm
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
