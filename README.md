# Achilles

Achilles is a local-first AI assistant for email, calendar and web search. It runs entirely on the client's machine: a FastAPI backend drives a Pydantic AI agent against a local Ollama model, tools run as MCP servers, and data stays in SQLite and LanceDB under `~/.achilles`. Every outbound HTTP call goes through one allowlisted client, so the assistant can only talk to the hosts the client has approved.

## Install

Fresh machine: follow `CLIENT_ONBOARDING.md`. From a checkout you can build local wheels and test
the installer end to end:

```sh
make build
uv build --all-packages --out-dir dist
./install.sh --wheels-dir dist --dry-run --force
```

## Running the tests

```
uv sync --all-packages
make test
```

Unit tests never need Ollama or a network connection.

## Evaluating a model

```
make eval-smoke
```

Runs ten YAML tasks against the Google simulator, three times each, and reports pass rate, latency and tokens. It needs Ollama (or any OpenAI-compatible endpoint via `achilles-eval --base-url ... --model ...`).
