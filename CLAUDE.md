# Homer

Local-first AI assistant (email, calendar, search) running on the client's machine through Ollama.

## Source of truth

`HOMER_IMPLEMENTATION_PLAN_v3.md`. Read it before each build step. Section 13 is the build order; section 15 is the rules. Record every deviation in `docs/DECISIONS.md` with a one-line reason.

## Code style

- SOLID, KISS, DRY. No overengineering.
- No comments. A docstring only when a function's behaviour is not obvious from its name and types.
- No abstraction without a second implementation.
- All outbound HTTP goes through `homer_net`. Nothing else imports `httpx`, `requests`, `aiohttp` or `urllib.request`.
- Model tags live only in `models/manifest.json`.
- Tests ship with the code. Prefer end-to-end functional tests through the real API, real SQLite, the real Ollama model and a real browser (Playwright), marked `e2e` and auto-skipped when Ollama is unreachable. A thin fake-model suite (Pydantic AI `TestModel`) stays only as the CI gate, because CI has no model.
- No real credentials, emails or names anywhere in the repo.

## Commands

- `make dev` runs the API with reload and the dashboard dev server.
- `make test`, `make lint`, `make build`.

## Keeping Hamza in the loop

After every build step: a chat summary in simple technical English, and `docs/EXPLAINERS/<step>.md` (one page max: what was built, why, how to explain it in an interview, what a client may ask).

## Conventions

- Git: `main` is trunk. One branch per build step, `feat/<nn>-<slug>` (e.g. `feat/01-skeleton`). Conventional commits: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `ci`, with a scope when useful (`feat(net): add allowlist`). Imperative subject, under 72 characters, no trailer lines of any kind. Never add `Co-Authored-By`.
- Python: `ruff` for lint and format, `snake_case` modules and functions, `PascalCase` classes, type hints everywhere, `pyproject.toml` per package, tests in `tests/` mirroring the package layout, `test_<module>.py`.
- TypeScript: `PascalCase` components, `camelCase` hooks and functions, one component per file, feature folders under `src/features/<page>/`.
- Directories: `kebab-case` for repo-level folders, Python packages `snake_case`.
- Commits use the repo-local identity already configured.
