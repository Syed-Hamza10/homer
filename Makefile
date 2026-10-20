.PHONY: dev dashboard-dev test test-e2e test-all lint fmt build eval-smoke

dev:
	EXTRA_ORIGINS='["http://localhost:5173"]' uv run uvicorn achilles_core.main:create_app --factory --reload --host 127.0.0.1 --port 8000

dashboard-dev:
	cd dashboard && pnpm dev

test:
	uv run pytest -m "not e2e"

test-e2e:
	uv run pytest -m e2e -v --durations=0

test-all:
	uv run pytest -v

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

build:
	cd dashboard && pnpm install --frozen-lockfile && pnpm build

eval-smoke:
	uv run achilles-eval --runs 3 $(ARGS)
