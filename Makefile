.PHONY: dev dashboard-dev preview test test-e2e test-all lint fmt build manifest eval-smoke

dev:
	EXTRA_ORIGINS='["http://localhost:5173"]' uv run uvicorn homer_core.main:create_app --factory --reload --host 127.0.0.1 --port 8000

dashboard-dev:
	cd dashboard && pnpm dev

preview:
	./scripts/preview_ui.sh

test:
	uv run pytest -m "not e2e"

test-e2e:
	uv run pytest -m e2e -v --durations=0

test-all:
	uv run pytest -v

lint:
	uv run ruff check .
	uv run ruff format --check .
	command -v actionlint >/dev/null && actionlint || echo "actionlint not installed, skipping workflow lint"

fmt:
	uv run ruff format .
	uv run ruff check --fix .

build: manifest
	cd dashboard && pnpm install --frozen-lockfile && pnpm build

manifest:
	mkdir -p packages/core/homer_core/models && cp models/manifest.json packages/core/homer_core/models/manifest.json

eval-smoke:
	uv run homer-eval --runs 3 $(ARGS)
