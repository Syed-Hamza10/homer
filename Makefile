.PHONY: dev test lint fmt build

dev:
	@echo "todo"

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

build:
	@echo "todo"
