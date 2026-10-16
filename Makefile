.PHONY: dev dashboard-dev test lint fmt build

dev:
	@echo "todo"

dashboard-dev:
	cd dashboard && pnpm dev

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

build:
	cd dashboard && pnpm install --frozen-lockfile && pnpm build
