# Achilles

Achilles is a local-first AI assistant for email, calendar and web search. It runs entirely on the client's machine: a FastAPI backend drives a Pydantic AI agent against a local Ollama model, tools run as MCP servers, and data stays in SQLite and LanceDB under `~/.achilles`. Every outbound HTTP call goes through one allowlisted client, so the assistant can only talk to the hosts the client has approved.

## Running the tests

```
uv sync --all-packages
make test
```

Unit tests never need Ollama or a network connection.
