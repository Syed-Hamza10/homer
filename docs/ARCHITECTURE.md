# Architecture (step 2)

## Layering

```
api/        routers, one file per resource; thin; return Pydantic schemas (api/schemas/), never DB rows
services/   business logic as plain functions taking a Session; raise small DomainError subclasses
db/         SQLModel tables, engine/session factory, Alembic migrations; no logic
agent/      Pydantic AI agent and prompts/system.md; the model is injected, never built here
            tools.py (core-native `remind`), toolsets.py (five curated name lists), router.py
            (slash commands + one-word classifier), gate.py (approval wrapper), runtime.py (bundle)
mcp/        manager.py: starts the MCP servers over stdio, hides `execute`/`health`, runs `execute`
main.py cli.py config.py platform.py llm.py doctor.py auth.py   top-level wiring
```

Routers depend on services; services on db, agent and mcp. Nothing points upward. Dependencies
arrive through FastAPI `Depends` (`api/deps.py`) from `app.state`, which the lifespan fills: engine,
session secret, login limiter, allowlisted HTTP client, model, and a `Runtime` (agent, classifier,
toolsets, MCP manager). `DomainError` subclasses carry a `status_code`; one handler in `main.py`
turns them into `{"detail": ...}` JSON.

## MCP manager

`McpManager.discover(settings)` looks for `achilles-mcp-google`, `achilles-mcp-search` and
`achilles-mcp-system` on PATH, then in the venv `bin`, and builds one `MCPToolset` per server over a
`StdioTransport` with env `ACHILLES_HOME`, `GOOGLE_API_BASE`, `GOOGLE_TOKEN_URL`, `WEB_SEARCH`.
`start()` enters each toolset; a server that is missing or fails to start is logged and dropped, the
app runs with whatever is left. `model_toolset()` is the combined view with `execute` and `health`
filtered out; `call(server, tool, args)` is the only path to `execute`, used by the approvals
executor. Core tools (`remind`) live in a `FunctionToolset`; `agent/toolsets.py` builds the five
`FilteredToolset`s (`mail`, `calendar`, `mail+calendar`, `search`, `system`) over both.

## Chat request flow

1. `POST /api/chat` passes the Origin middleware (non-GET under `/api` needs an own origin) and
   `current_user` (signed `achilles_session` cookie, 7 days).
2. `services.chat.stream` creates the conversation if needed (title = first 60 chars), saves the
   user message and rebuilds the model history from the stored messages.
3. `agent/router.py` matches `/brief`, `/inbox` (fixed "not yet available" text), `/remind <text>`
   (agent run with the `system` toolset), `/approve N` and `/reject N` (service call, one line of
   text). Anything else gets one short non-streamed classification call on the same model that
   answers one of the five toolset names (`mail+calendar` on anything unexpected).
4. The agent runs with that toolset wrapped in an `ApprovalGate`. The gate stores any tool result
   shaped `{"approval_required": true, action, payload, preview}` as an `approvals` row and hands
   the model the text "Approval #N requested; the user will decide". It also remembers whether any
   result contained `<untrusted>`; from then on `mail_label` and `mail_archive` are turned into
   approvals instead of being called.
5. `stream` turns the run's events into `ChatEvent`s; `api/chat.py` writes each as an SSE frame
   `event: <name>\ndata: <json>\n\n` (no SSE library).
6. On completion it saves the assistant message and adds the run's tokens (classifier included) to
   `token_counter`. On failure it logs the exception with structlog and yields a generic `error`.

## Approvals

`services/approvals.py`. `create_from_tool_result` stores server, action, canonical-JSON payload,
its sha256, preview and `channel="web"`. `approve` does one `UPDATE … SET status='running' WHERE
id=? AND status='pending'`; zero rows means someone else decided first and the API answers 409. It
recomputes the payload hash (mismatch → `failed`, nothing runs), then calls
`manager.call(server, "execute", {action, payload})` with a 60 s timeout: a result → `done`, a
`ToolFailed` from the server or a missing server → `failed`, a timeout or any other exception →
`unknown` (never retried). `reject` is the same conditional update to `rejected`. `expire_stale`
moves pending rows older than 24 h to `expired` and runs before every list/approve/reject.

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
| GET | `/api/health` | – | `{status: "ok", version, ollama: "ok"\|"down", model, servers: {google, search, system: "ok"\|"down"}}` (public) |
| POST | `/api/auth/login` | `{passphrase}` | 204 + cookie; 401 wrong; 429 after 5 failures in 60 s |
| POST | `/api/auth/logout` | – | 204, cookie cleared |
| GET | `/api/auth/me` | – | `{user_id, name}` |
| POST | `/api/chat` | `{conversation_id?: int, message}` | `text/event-stream`; 404 unknown conversation |
| GET | `/api/conversations` | – | `[{id, title, created_at, updated_at}]` newest first |
| GET | `/api/conversations/{id}/messages` | – | `[{id, conversation_id, role, content, created_at}]`; 404 if not the user's |
| GET | `/api/approvals?status=pending` | – | `[{id, server, action, payload, preview, status, channel, created_at, decided_at, result}]` |
| POST | `/api/approvals/{id}/approve` | – | the approval after execution (`done`/`failed`/`unknown`); 404 unknown; 409 not pending |
| POST | `/api/approvals/{id}/reject` | – | the approval as `rejected`; 404 unknown; 409 not pending |
| GET | `/api/privacy/hosts` | – | `{hosts: [{host, calls, last_seen}], web_search}` from `outbound_log` |
| GET | `/api/privacy/usage` | – | `{input_tokens, output_tokens, requests, spent_usd: 0}` |
| GET | `/api/reminders` | – | `[{id, text, due_at, status, created_at}]` by due date |

Everything under `/api` except `/api/health` needs the cookie (401 otherwise). Non-GET requests
without an own `Origin` get 403. Errors are `{"detail": "<message>"}`.

SSE events on `/api/chat`, in order:

- `meta` `{conversation_id, message_id}` (`message_id` is the saved user message)
- `tool_call` `{name, args}` and `tool_result` `{name, summary}` (summary cut at 200 chars),
  interleaved with `token`s as the run proceeds
- `approval_required` `{approval_id, action, preview}` right before the matching `tool_result`
- `token` `{text}` repeated
- `done` `{input_tokens, output_tokens}`
- `error` `{message}` replaces `done` when the model call fails

When `achilles_core/static/index.html` exists the built dashboard is served at `/`; unknown non-`/api`
paths return `index.html`.

## Tests

`packages/core/tests/` holds the fake-model suite (`TestModel`, `respx`, scripted `FunctionModel`s that call tools), which is the CI gate because CI has no model. `tests/fake_servers/` holds stand-in `google` and `system` MCP servers built with `fastmcp` over canned fictional data; the unit suite runs them in-process through `Client(server)`, the e2e suite writes stdio launchers for them onto the server's PATH. `packages/core/tests/e2e/` (marker `e2e`) is the real proof: it starts `achilles serve` as a subprocess on a temp `ACHILLES_HOME`, talks to it over real HTTP, reads the real SQLite file, calls the real Ollama model and drives the built dashboard with Playwright; it skips itself when Ollama or the model is missing, and runs locally (`make test-e2e`) before every merge.

## Step 2 contract: tools, approvals, simulator

**MCP servers.** One package each: `packages/mcp_google` (`achilles_mcp_google`), `packages/mcp_search` (`achilles_mcp_search`), `packages/mcp_system` (`achilles_mcp_system`). Built with `fastmcp` (4.x) over stdio, console script `achilles-mcp-<name>`. Each exposes `health() -> {ok, version}`. Request/response only; no background work. Settings come from env: `ACHILLES_HOME`, and for google `GOOGLE_API_BASE` (default `https://www.googleapis.com`; the simulator overrides it) and `GOOGLE_TOKEN_URL` (default `https://oauth2.googleapis.com/token`). Every server builds its own `Allowlist` containing exactly the hosts it needs and logs through `achilles_net.SqliteLog(ACHILLES_HOME/data/achilles.db)`, which inserts into the core-owned `outbound_log` table with stdlib `sqlite3`. The core never trusts a server's claim; the log is the proof.

**Tool names are provider-neutral.** google: `mail_search(query, max_results)`, `mail_get(message_id)`, `mail_thread(thread_id)`, `mail_changes_since(cursor) -> {cursor, changed_ids}`, `mail_draft(thread_id|None, to, subject, body) -> {draft_id}`, `mail_send(draft_id)` [tier 1], `mail_label(message_id, add, remove)`, `mail_archive(message_id)`, `cal_list(start, end)`, `cal_find_free_slots(start, end, duration_minutes, working_hours)`, `cal_create(...)` [tier 1], `cal_update(event_id, ...)` [tier 1], `cal_delete(event_id)` [tier 1], `contacts_search(query)`. search: `web_search(query, max_results) -> {results: [{title, url, snippet}]}`, `fetch_page(url) -> {title, text, url}`. system: `now(timezone) -> iso`, `parse_datetime(text, timezone) -> iso|None`. Reminders are a core-native tool (`remind(text, when)`) backed by the core `reminder` table, because the scheduler and the Today page own them; recorded in DECISIONS.md. Descriptions: two sentences max. Email bodies, page text and search snippets are returned wrapped in `<untrusted>…</untrusted>`.

**Search server hosts.** `web_search` is our own small DuckDuckGo HTML client: one POST to `https://html.duckduckgo.com/html/` through `AllowlistedClient` with the allowlist exactly `{"html.duckduckgo.com"}`, parsed with the stdlib `html.parser` (result links and snippets; DuckDuckGo's `/l/?uddg=` redirect links are decoded to the real URL, ad links dropped). Every search therefore lands in `outbound_log` like any other call. `fetch_page` builds an `Allowlist` per call holding only the host the user asked for and goes through `AllowlistedClient`; it resolves the hostname first and refuses any address that is not public (private, loopback, link-local, reserved, multicast, shared), caps the body at 2 MB and the whole call at 15 s, and a redirect to another host fails the per-hop allowlist check. Both searches and fetches are gated at one request per second per tool and cached for an hour by tool and arguments; errors are not cached. `WEB_SEARCH=false` makes every tool return `{"error": "web_search_off"}` before any network call.

**Approvals.** A tier-1 tool never acts. It validates, builds the exact payload, and returns `{"approval_required": true, "action": "<tool name>", "payload": {...}, "preview": "<plain text the user will read>"}`. Each server with tier-1 tools also exposes `execute(action: str, payload: dict) -> dict`; the core removes `execute` from every model-visible toolset, so only the approvals executor can call it. Core table `approval(id, user_id, server, action, payload_json, payload_hash sha256, preview, status, created_at, decided_at, result_json, channel)`. Status: `pending → running → done | failed | unknown`, or `pending → rejected | expired` (24 h). Approve = one `UPDATE … SET status='running' WHERE id=? AND status='pending'`; zero rows updated means someone else got there first. The executor recomputes the hash before calling `execute`; an edited payload is a new approval. A timeout or ambiguous failure on a send sets `unknown` and is never retried automatically. Any tier-2 action proposed while untrusted content is in the current run's context is routed through approval too (the agent run tracks whether an `<untrusted>` block has been returned).

**Router and toolsets.** `/brief`, `/inbox`, `/remind`, `/approve N` by regex. Otherwise one short classification call picks one of `mail`, `calendar`, `mail+calendar`, `search`, `system`. Each is a `FilteredToolset` over the MCP toolsets plus core-native tools, at most 10 tools, defined as explicit name lists in `agent/toolsets.py`.

**SSE events added:** `tool_call {name, args}`, `tool_result {name, summary}`, `approval_required {approval_id, action, preview}`.

**Simulator.** `packages/eval/achilles_sim`: a FastAPI app serving the Gmail v1, Calendar v3 and People v1 endpoints the google server uses, with in-memory state loaded from a fictional seed (`seed.json`, no real names). Console script `achilles-sim --port N`. The google server pointed at it (`GOOGLE_API_BASE=http://127.0.0.1:N`) behaves identically. It is the fixture for every Google e2e test and for the eval runner.
