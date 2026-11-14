# Contributing

Thanks for your interest in Homer. Issues with bug reports and ideas are welcome. Please open an
issue before starting a pull request so we can agree on the change first. Security problems go
through [SECURITY.md](SECURITY.md), not public issues.

## Development

- `make dev` runs the API with reload; `make dashboard-dev` runs the dashboard dev server.
- `make test` runs the unit suite (no Ollama needed); `make test-e2e` needs a local Ollama.
- `make lint` runs `ruff` and, if installed, `actionlint`.

## Conventions

- Python: type hints everywhere, `ruff` for lint and format, tests in `tests/` mirroring the
  package layout.
- Every outbound HTTP call goes through `homer_net`. No other module may import an HTTP library.
- Model tags live only in `models/manifest.json`.
- Conventional commits (`feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`), imperative
  subject under 72 characters.
- No real credentials, email addresses or names in code, tests, fixtures or screenshots.

By submitting a pull request you agree that your contribution is licensed under the same terms as
the rest of the repository (see [LICENSE](LICENSE)).
