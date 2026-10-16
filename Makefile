.PHONY: dev test lint fmt build

dev:
	EXTRA_ORIGINS='["http://localhost:5173"]' uv run uvicorn achilles_core.main:create_app --factory --reload --host 127.0.0.1 --port 8000

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
