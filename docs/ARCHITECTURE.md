# Architecture (step 1)

## Layering

```
api/        routers, one file per resource; thin; return Pydantic schemas (api/schemas/), never DB rows
services/   business logic as plain functions taking a Session; raise small DomainError subclasses
db/         SQLModel tables, engine/session factory, Alembic migrations; no logic
agent/      Pydantic AI agent and prompts/system.md; the model is injected, never built here
main.py cli.py config.py platform.py llm.py doctor.py auth.py   top-level wiring
```

Routers depend on services; services on db and agent. Nothing points upward. Dependencies arrive
through FastAPI `Depends` (`api/deps.py`) from `app.state`, which the lifespan fills: engine,
session secret, login limiter, allowlisted HTTP client, model, agent. `DomainError` subclasses carry
a `status_code`; one handler in `main.py` turns them into `{"detail": ...}` JSON.

## Chat request flow

1. `POST /api/chat` passes the Origin middleware (non-GET under `/api` needs an own origin) and
   `current_user` (signed `achilles_session` cookie, 7 days).
2. `services.chat.stream` creates the conversation if needed (title = first 60 chars), saves the
   user message, rebuilds the model history from the stored messages, and runs
   `agent.run_stream`.
3. It yields `ChatEvent`s; `api/chat.py` writes each as an SSE frame
   `event: <name>\ndata: <json>\n\n` (no SSE library).
4. On completion it saves the assistant message and adds the run's tokens to `token_counter`.
   On failure it logs the exception with structlog and yields a generic `error` event.

The agent's instructions are rendered per run from `agent/prompts/system.md` (user name, timezone,
current time, and the line that `<untrusted>` content is data, not instructions).

## Outbound log

`llm.build_http_client` returns the one `AllowlistedClient` whose allowlist holds exactly the
Ollama host from `OLLAMA_URL`. Its `log` callable (`services/outbound_log.py`) inserts an
`outbound_log` row (method, host, path, status, duration) per call, including refused calls
(status NULL), using its own short-lived session. The model, health check and doctor all share
this client, so anything else the app contacted would show up here.

## API contract

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/health` | – | `{status: "ok", version, ollama: "ok"\|"down", model}` (public) |
| POST | `/api/auth/login` | `{passphrase}` | 204 + cookie; 401 wrong; 429 after 5 failures in 60 s |
| POST | `/api/auth/logout` | – | 204, cookie cleared |
| GET | `/api/auth/me` | – | `{user_id, name}` |
| POST | `/api/chat` | `{conversation_id?: int, message}` | `text/event-stream`; 404 unknown conversation |
| GET | `/api/conversations` | – | `[{id, title, created_at, updated_at}]` newest first |
| GET | `/api/conversations/{id}/messages` | – | `[{id, conversation_id, role, content, created_at}]`; 404 if not the user's |

Everything under `/api` except `/api/health` needs the cookie (401 otherwise). Non-GET requests
without an own `Origin` get 403. Errors are `{"detail": "<message>"}`.

SSE events on `/api/chat`, in order:

- `meta` `{conversation_id, message_id}` (`message_id` is the saved user message)
- `token` `{text}` repeated
- `done` `{input_tokens, output_tokens}`
- `error` `{message}` replaces `done` when the model call fails

When `achilles_core/static/index.html` exists the built dashboard is served at `/`; unknown non-`/api`
paths return `index.html`.

## Tests

`packages/core/tests/` holds the fake-model suite (`TestModel`, `respx`), which is the CI gate because CI has no model. `packages/core/tests/e2e/` (marker `e2e`) is the real proof: it starts `achilles serve` as a subprocess on a temp `ACHILLES_HOME`, talks to it over real HTTP, reads the real SQLite file, calls the real Ollama model and drives the built dashboard with Playwright; it skips itself when Ollama or the model is missing, and runs locally (`make test-e2e`) before every merge.
