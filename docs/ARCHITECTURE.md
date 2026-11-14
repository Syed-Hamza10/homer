# Architecture (step 2)

## Layering

```
api/        routers, one file per resource; thin; return Pydantic schemas (api/schemas/), never DB rows
services/   business logic as plain functions taking a Session; raise small DomainError subclasses
db/         SQLModel tables, engine/session factory, Alembic migrations; no logic
agent/      Pydantic AI agent and prompts/system.md; the model is injected, never built here
            intents.py (one structured call -> list of intents), router.py (slash commands and
            typed approve/reject words), claims.py (claim guard), prompt.py, runtime.py (bundle)
mcp/        manager.py: starts the MCP servers over stdio, hides `execute`/`health`, runs `execute`
main.py cli.py config.py platform.py llm.py doctor.py auth.py   top-level wiring
```

Routers depend on services; services on db, agent and mcp. Nothing points upward. Dependencies
arrive through FastAPI `Depends` (`api/deps.py`) from `app.state`, which the lifespan fills: engine,
session secret, login limiter, allowlisted HTTP client, model, and a `Runtime` (model, MCP manager,
intent agent, contacts cache). `DomainError` subclasses carry a `status_code`; one handler in `main.py`
turns them into `{"detail": ...}` JSON.

## MCP manager

`McpManager.discover(settings)` looks for `homer-mcp-google`, `homer-mcp-search` and
`homer-mcp-system` on PATH, then in the venv `bin`, and builds one `MCPToolset` per server over a
`StdioTransport` with env `HOMER_HOME`, `GOOGLE_API_BASE`, `GOOGLE_TOKEN_URL`, `WEB_SEARCH`.
`start()` enters each toolset; a server that is missing or fails to start is logged and dropped, the
app runs with whatever is left. The model never sees an MCP tool: `call(server, tool, args)` is
the only way in, used by the job executors and the approvals executor.

## Skills, caches and scheduler (step 4)

`services/` now holds the deterministic workflows: `inbox.py` (cache + rule-based triage),
`calendar.py` (cache + slots), `briefs.py` (morning brief and digest), `followups.py` (close on
reply or draft after the delay), `drafts.py` (model-written reply in the client's tone) and
`scheduler.py`. Client rules live in `services/rules.py` as one JSON row in `settings`; the Gmail
cursor is another row, through `services/store.py`.

`Scheduler` starts in the lifespan when `SCHEDULER_ENABLED` is true. It opens its own
`Session(engine)` per job and calls the MCP manager like any service. Jobs: mail poll (3 min,
`mail_changes_since`, label only changed messages), calendar poll (10 min), reminders (1 min, marks
`due`), follow-up check (10 min), health check (10 min, first run at start; Ollama reachable, model
tag pulled, each MCP server up, email-to-self address matches; the report is kept on the
`Scheduler` and returned as `health` by `GET /api/today`), model warm-up at 06:45 (one PONG
request so the 07:30 brief is not cold), morning brief at 07:30, digest at 18:00 and a nightly
backup at 03:00 in the user's timezone. All have `coalesce=True`; the brief and digest get the rest of their
day as `misfire_grace_time` (a 07:30 brief missed during sleep runs once on wake, never twice), the
other jobs one hour. When `mail_changes_since` reports a stale cursor (Gmail returned 404 for an
old history id) the poll stores the fresh cursor and backfills the gap with
`mail_search("newer_than:2d")` instead of dropping it.

Caches: `email_cache` (one row per message per user, category, unread, priority, archived),
`calendar_cache` (events for the next 14 days), `daily_briefs` (kind + local day, overwritten) and
`follow_ups`. `GET /api/today` reads through the caches and primes them once when empty.

## Eval harness (step 5)

`packages/eval/homer_eval` is the `homer-eval` console script. It loads YAML tasks from
`homer_eval/tasks/`, starts `homer-sim` (or uses `--sim-url`), starts the real MCP servers
through `McpManager` with the token file pointing at the simulator, and builds an
OpenAI-compatible `Model` from `--base-url`/`--model`. Each task run gets a fresh temporary
database and a simulator reset; the runner calls `services.chat.stream` and checks tool calls,
approval actions, answer substrings and simulator counts. A task may carry a `follow_up` turn in
the same conversation with its own checks; `reject_pending` rejects every approval the first turn
created through `services.approvals` before the follow-up runs, and fails the task if there was
nothing to reject. The safety task uses this: draft and send, reject, ask again, no new approval
and `sent` unchanged. `FunctionModel` can replace the endpoint
for tests. `make eval-smoke` runs three attempts per task locally; it is not a CI target because CI
has no model.

The Settings model picker stores `model_tier` in client rules. The lifespan reads it before
`build_model`, so a restart applies the choice; `GET /api/settings/models` exposes the manifest
tags and `POST /api/settings/smoke` runs a PONG check against the current model or a selected tier.
The Privacy web-search override is stored in `settings`, applied to the search server env on the
next start, and reported as `restart_required`.

## Install, release and operations (step 6)

`scripts/install.sh` is the only client-facing entry point. It installs `uv` and Ollama, configures Ollama
with our launch agent (macOS) or a systemd drop-in (Linux), creates `~/.homer` and its
subdirectories, writes `.env`, installs the release wheels into `~/.homer/venv`, pulls the model
tags from the packaged `models/manifest.json`, registers a launchd/systemd **user** service for
`homer serve`, runs the migrations and `doctor`. `--wheels-dir` installs local wheels and
`--dry-run` only checks the machine, which is how the installer is tested here.

The release workflow runs on `v*` tags: fast tests, dashboard build, version/tag check, wheels for
every workspace package, a wheel-content check (dashboard and manifest), then a GitHub release with
the runtime wheels, `install.sh`, `PRIVACY.md` and `CLIENT_ONBOARDING.md`. CI has the same wheel
build/verify as a separate package job.

`homer backup` writes a timestamped 0600 archive of a consistent SQLite snapshot (secrets only
with `--include-secrets`); the newest 14 stay. `homer update` stages the verified release in
`venv.new`, checks it with `doctor --quick`, then swaps and restarts. `PRIVACY.md` is generated by
`homer privacy` from `homer_core/privacy_hosts.py`, which is also checked against the Google
and search server defaults.

## Chat request flow

1. `POST /api/chat` passes the Origin middleware (non-GET under `/api` needs an own origin) and
   `current_user` (signed `homer_session` cookie, 7 days).
2. `services.chat.stream` creates the conversation if needed (title = first 6 words, at most 60
   chars), saves the
   user message and rebuilds the model history from the stored messages.
3. `agent/router.py` matches the skill commands, `/approve N` and `/reject N`; `/remind <text>`
   becomes "Remind me <text>". A whole-message decision word ("send it", "yes", "approved",
   "no", "cancel", "discard") with exactly one pending approval settles it without the model;
   with several it lists them; with none, a bare yes/no goes on and the rest answer "Nothing is
   waiting for your approval."
4. One structured call (`agent/intents.py`, Pydantic AI `ToolOutput` named `record_intents`, a
   discriminated union) turns the message, the last 6 stored messages and a table of dates
   (today, tomorrow, the next 7 days by name, this week) into a list of intents: `send_email`,
   `create_event`, `read_calendar`, `read_email`, `web_search`, `remind`, `chat`. The model copies
   dates and times; validators normalise `3pm` to `15:00` and reject anything that is not
   `YYYY-MM-DD`, which makes Pydantic AI retry. A failed call falls back to `chat`.
5. `services/jobs/dispatch.py` runs each intent in order through its executor in
   `services/jobs/` (one module per job). Each gets a `Turn`: session, user, rules, history, the
   user's local `now`, and an event queue. `Turn.call` is the only way to an MCP tool (it emits
   `tool_call`/`tool_result` and turns `{"error": ...}` into a `JobError`), `Turn.say` emits fixed
   text, `Turn.stream` streams one model answer, `Turn.requested` emits `approval_required` with the
   payload. A `JobError` or `DomainError` in one intent is said and the next intent still runs.
6. `stream` drains the queue into SSE frames `event: <name>\ndata: <json>\n\n` (no SSE library);
   a `replace` event carries the corrected text when the claim guard fires. On completion it saves
   the assistant message and adds every model call's tokens to `token_counter`. On failure it logs
   the exception and yields a generic `error`.
7. Stop: the browser aborts the fetch. Starlette sees the disconnect and cancels the response task;
   the `CancelledError` (or a `GeneratorExit` when the stream is closed) reaches `stream`, which
   saves the text shown so far (tokens, or the last `replace`) as an assistant message with
   `stopped=true` and re-raises. `run_turn` cancels the jobs task in a `finally`, so the model call
   stops too. No `done` frame and no token count for a stopped turn. Every assistant message also
   stores `created_approval` (an `approval_required` event was sent during the turn), and every
   approval shown in the turn gets that message's id as `approvals.message_id`. The dashboard loads
   `GET /api/approvals?conversation_id=N` (all statuses but `superseded`) and draws each card under
   its message, so cards survive a reload. "show me the draft" with a pending approval re-sends the
   card with "Here's the draft." and no model call. After the first turn the title becomes a short
   one from the resolved intent (`services/conversations.title_for`).
8. Regenerate: `POST /api/conversations/{id}/regenerate` deletes the last user/assistant pair and
   returns the user text; the browser sends it again through `/api/chat`. A reply with
   `created_approval` is 409 and the button is hidden for it.

### The jobs

- `send_email`: address as given, else `contacts_search` (cached 10 min per first name), else
  recent senders from `mail_search from:<name>`; none asks for the address, several ask which.
  `reply_to_latest_from` replies in that sender's newest thread. One `write_email` structured call
  writes subject and body in the client's tone; `mail_draft`; a `mail_send` approval created
  through `services/approvals.create` with payload `{draft_id, to, subject, body, thread_id}`;
  then "Here's your email to <name>. Press Send when it looks right." The payload also carries
  `to_name` when the recipient came from contacts.
- `create_event`: attendees resolved like recipients (an unknown one is left off and asked
  about); an explicit start is used as given (end = end or start + duration, default 30 min); a
  window (default business hours) goes to `cal_find_free_slots` with the user's `timezone` and the
  first slot wins; `cal_create` with `timezone`; a `cal_create` approval; one fixed sentence.
- `read_calendar`: `cal_list` over the local day bounds; up to 8 events are rendered as a list in
  the user's timezone with no model call, more go to one phrasing call over that list only.
- `read_email`: `mail_search` (`from:<first name>` and/or the topic, one retry with the longest
  word), bodies in `<untrusted>`, one answer call citing sender and date.
- `web_search`: `web_search`, `fetch_page` on the top 2 results (2,500 chars each, the snippet
  when a fetch fails), one answer call under 120 words, then a "Sources:" list written by code.
- `remind`: a reminder row at the local date and time; no model call.
- `chat`: the short system prompt (`prompts/system.md`; the user's name only when it is not the
  install-time placeholder) and the last 10 messages, no tools. The claim guard
  (`agent/claims.py`) replaces any "I've sent/scheduled/created" text with a fixed honest
  sentence; an "I don't know" answer falls through to `web_search`.

### Editing an approval

`POST /api/approvals/{id}/edit` takes `{to, subject, body}` for `mail_send` or `{title, date,
start, end, attendees}` for `cal_create` (local date and times). A mail edit calls the hidden
`mail_draft_update` (Gmail `drafts.update`, same draft id); an event edit calls `cal_create` again
with the user's timezone. A fresh approval with a new hash is created and the old one moves
`pending -> superseded`; editing a non-pending approval is 409, the wrong shape 422. Rejecting a
`mail_send` (button, `/reject`, typed "discard") also deletes the Gmail draft with
`mail_draft_delete`.

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
| GET | `/api/health` | – | `{status: "ok", version, ollama: "ok"\|"down", model, model_pulled, servers: {google, search, system: "ok"\|"down"}, self_email: "off"\|"ok"\|"mismatch"\|"unknown", checked_at}` (public, live check) |
| POST | `/api/auth/login` | `{passphrase}` | 204 + cookie; 401 wrong; 429 after 5 failures in 60 s |
| POST | `/api/auth/logout` | – | 204, cookie cleared |
| GET | `/api/auth/me` | – | `{user_id, name}` |
| POST | `/api/chat` | `{conversation_id?: int, message}` | `text/event-stream`; 404 unknown conversation |
| GET | `/api/conversations` | – | `[{id, title, created_at, updated_at}]` newest first |
| GET | `/api/conversations/{id}/messages` | – | `[{id, conversation_id, role, content, stopped, created_approval, created_at}]`; 404 if not the user's |
| PATCH | `/api/conversations/{id}` | `{title}` | the conversation; 422 blank; 404 unknown |
| DELETE | `/api/conversations/{id}` | – | 204; its messages go too, approvals stay (they have no conversation link); 404 unknown |
| POST | `/api/conversations/{id}/regenerate` | – | `{message}` (the removed user text); 409 when the last message is not an assistant reply or it created an approval |
| GET | `/api/approvals?status=pending` | – | `[{id, server, action, payload, preview, status, channel, created_at, decided_at, result}]` |
| POST | `/api/approvals/{id}/approve` | – | the approval after execution (`done`/`failed`/`unknown`); 404 unknown; 409 not pending |
| POST | `/api/approvals/{id}/reject` | – | the approval as `rejected`; 404 unknown; 409 not pending |
| GET | `/api/privacy/hosts` | – | `{hosts: [{host, calls, last_seen}], web_search, web_search_configured}` from `outbound_log` |
| GET | `/api/privacy/usage` | – | `{input_tokens, output_tokens, requests, spent_usd: 0}` |
| PUT | `/api/privacy/web-search` | `{enabled}` | `{enabled, restart_required}` |
| POST | `/api/privacy/wipe` | `{confirm}` | `{deleted: {table: count}}`; 400 without confirm |
| GET | `/api/reminders` | – | `[{id, text, due_at, status, created_at}]` by due date |
| GET | `/api/today` | – | `{day, brief, digest, events, reminders, follow_ups, unread, pending_approvals, health, google, card}` (`health` is the scheduler's last report or null; `card` is `{greeting, meetings, next_event_id, emails, follow_ups, approvals}` built from the caches with no model call) |
| GET | `/api/activity?before=&kind=all\|email\|calendar\|memory&limit=30` | – | `{items: [{id, kind, at, text, detail, status, link}], next}` newest first from approvals, facts and the Google consent time; `next` is the `before` cursor |
| POST | `/api/today/brief` | – | the morning `daily_briefs` row; runs the skill |
| POST | `/api/today/digest` | – | the digest row; runs the skill |
| GET | `/api/inbox` | – | cached `[{message_id, thread_id, sender, subject, snippet, category, labels, unread, priority, received_at}]` |
| POST | `/api/inbox/refresh` | – | `{messages, labeled, failed}`; refresh then triage |
| POST | `/api/inbox/triage` | – | `{labeled, failed}` |
| POST | `/api/inbox/{message_id}/archive` | – | the cached message, archived |
| POST | `/api/inbox/{message_id}/follow-up` | `{days?}` | the follow-up row (`draft_preview` is the templated body once a draft exists) |
| POST | `/api/followups/{id}/send` | – | a pending `mail_send` approval for the follow-up draft; 400 without a draft; 404 unknown |
| POST | `/api/inbox/{message_id}/draft` | – | `{draft_id, to, subject, body}` |
| GET | `/api/calendar?days=7` | – | `[{event_id, title, start, end, location, attendees}]` |
| POST | `/api/calendar/refresh` | – | the refreshed event list |
| POST | `/api/calendar/find-slot` | `{duration_minutes, days, attendees?, limit?}` | `[{start, end}]` in the user's timezone, three unless `limit` (max 10); attendees must be free too |
| GET | `/api/calendar/events?start=&end=` | – | `{events: [{id, title, start, end, all_day, location, description, attendees, people: [{email, name, response, organizer}], organizer, video_link}], source: "google"\|"cache"}`; live `cal_list`, the cache when Google fails; offsets required, at most 62 days |
| GET | `/api/calendar/events/{id}` | – | one event (`cal_get`) |
| POST | `/api/calendar/events` | `{title, start, end, attendees, description, location}` (local wall times) | a pending `cal_create` approval |
| PATCH | `/api/calendar/events/{id}` | any of those fields | a pending `cal_update` approval with only the changed fields and a before/after preview; 422 when nothing changes |
| POST | `/api/calendar/events/{id}/cancel` | – | a pending `cal_delete` approval |
| GET | `/api/mail/folders` | – | `[{id, name, kind: "folder"\|"label"\|"category", unread, total}]`: Inbox, Starred, Sent, Drafts, All mail, then user labels (Homer's triage labels as `category`) |
| GET | `/api/mail/threads?folder=&q=&page_token=&size=` | – | `{threads: [{id, subject, sender, to, senders, snippet, received_at, message_count, unread, starred, has_attachment, labels}], next_page_token}`; `folder` is a folder key or a label id, `q` is Gmail query syntax |
| GET | `/api/mail/threads/{id}?images=` | – | `{id, subject, messages: [{id, sender, to, cc, date, received_at, labels, unread, body_text, body_html, remote_images, attachments}]}`; `body_html` is sanitised (nh3) with remote images dropped unless `images=true` |
| POST | `/api/mail/threads/{id}/labels` | `{add, remove}` (label names) | `{id, labels}`; archive, star, read state and labels, applied straight away (tier 2) |
| GET | `/api/mail/threads/{id}/reply?mode=reply\|reply_all\|forward` | – | `{to, subject, body, thread_id}` to prefill the composer |
| POST | `/api/mail/compose` | `{to, subject, body, thread_id?}` | a Gmail draft and its pending `mail_send` approval; nothing is sent |
| POST | `/api/mail/write` | `{instruction, thread_id?, to?}` | `{body}` from one tool-free model call over the thread (as `<untrusted>`) and the instruction |
| GET | `/api/settings` | – | `ClientRules` |
| PUT | `/api/settings` | `ClientRules` | the saved rules; 422 on bad business hours |
| GET | `/api/settings/models` | – | `{selected_tier, effective_tier, tiers: [{tier, tag, context}]}` |
| POST | `/api/settings/smoke?tier=` | – | `{ok, text, error, latency_ms}` on the current or chosen tier |
| GET | `/api/settings/search` | – | `{provider, api_provider, fallback, key_hint, hosts}`; `key_hint` is `…` plus the last four characters, never the key |
| PUT | `/api/settings/search` | `{provider, api_provider, fallback, api_key?}` | same as GET; no `api_key` keeps the saved key, `""` removes it |
| POST | `/api/settings/search/test` | – | `{status: ok\|blocked\|invalid_key\|limited\|failed\|off, provider, results}` from one uncached query |

Everything under `/api` except `/api/health` needs the cookie (401 otherwise). Non-GET requests
without an own `Origin` get 403. Errors are `{"detail": "<message>"}`.

SSE events on `/api/chat`, in order:

- `meta` `{conversation_id, message_id}` (`message_id` is the saved user message)
- `tool_call` `{name, args}` and `tool_result` `{name, summary}` (summary cut at 200 chars),
  interleaved with `token`s as the run proceeds
- `approval_required` `{approval_id, action, preview}` right before the matching `tool_result`
- `status` `{text}` any time before or between tokens: a short progress line ("Searching the
  web…"; the web search job sends them). The chat folds `status`, `tool_call` and `tool_result`
  into one activity line above the reply that updates in place and ends as a summary ("Searched
  the web · 2 sources"); clicking it lists one plain row per tool call, never raw JSON or page
  text. "Thinking…" shows until the first `status` or `tool_call`
- `token` `{text}` repeated
- `replace` `{text}` replaces the text shown so far (claim guard)
- `done` `{input_tokens, output_tokens}`
- `error` `{message}` replaces `done` when the model call fails

When `homer_core/static/index.html` exists the built dashboard is served at `/`; unknown non-`/api`
paths return `index.html`.

## Tests

`packages/core/tests/` holds the fake-model suite (`TestModel`, `respx`, scripted `FunctionModel`s that call tools), which is the CI gate because CI has no model. `tests/fake_servers/` holds stand-in `google` and `system` MCP servers built with `fastmcp` over canned fictional data; the unit suite runs them in-process through `Client(server)`, the e2e suite writes stdio launchers for them onto the server's PATH. `packages/core/tests/e2e/` (marker `e2e`) is the real proof: it starts `homer serve` as a subprocess on a temp `HOMER_HOME`, talks to it over real HTTP, reads the real SQLite file, calls the real Ollama model and drives the built dashboard with Playwright; it skips itself when Ollama or the model is missing, and runs locally (`make test-e2e`) before every merge. Every e2e server starts with `SCHEDULER_ENABLED=false` so background jobs cannot race the assertions; `test_scheduler.py` is the one test that turns it on and checks the health job's report.

## Step 2 contract: tools, approvals, simulator

**MCP servers.** One package each: `packages/mcp_google` (`homer_mcp_google`), `packages/mcp_search` (`homer_mcp_search`), `packages/mcp_system` (`homer_mcp_system`). Built with `fastmcp` (4.x) over stdio, console script `homer-mcp-<name>`. Each exposes `health() -> {ok, version}`. Request/response only; no background work. Settings come from env: `HOMER_HOME`, and for google `GOOGLE_API_BASE` (default `https://www.googleapis.com`; the simulator overrides it) and `GOOGLE_TOKEN_URL` (default `https://oauth2.googleapis.com/token`). Every server builds its own `Allowlist` containing exactly the hosts it needs and logs through `homer_net.SqliteLog(HOMER_HOME/data/homer.db)`, which inserts into the core-owned `outbound_log` table with stdlib `sqlite3`. The core never trusts a server's claim; the log is the proof.

**Tool names are provider-neutral.** google: `mail_search(query, max_results)`, `mail_get(message_id)`, `mail_thread(thread_id)`, `mail_changes_since(cursor) -> {cursor, changed_ids}`, `mail_draft(thread_id|None, to, subject, body) -> {draft_id}`, `mail_send(draft_id)` [tier 1], `mail_label(message_id, add, remove)`, `mail_archive(message_id)`, `mail_list_threads(query, label, page_token, max_results)`, `mail_labels()`, `mail_thread_label(thread_id, add, remove)`, `mail_thread(thread_id, html)`, `cal_list(start, end)`, `cal_get(event_id)`, `cal_find_free_slots(start, end, duration_minutes, working_hours, timezone, attendees, limit)`, `cal_create(...)` [tier 1], `cal_update(event_id, ...)` [tier 1], `cal_delete(event_id)` [tier 1], `contacts_search(query)`. search: `web_search(query, max_results) -> {results: [{title, url, snippet}]}`, `fetch_page(url) -> {title, text, url}`. system: `now(timezone) -> iso`, `parse_datetime(text, timezone) -> iso|None`. Reminders are a core-native tool (`remind(text, when)`) backed by the core `reminder` table, because the scheduler and the Today page own them; recorded in DECISIONS.md. Descriptions: two sentences max. Email bodies, page text and search snippets are returned wrapped in `<untrusted>…</untrusted>`.

**Search server hosts.** `web_search` is our own small DuckDuckGo HTML client: one POST to `https://html.duckduckgo.com/html/` through `AllowlistedClient` with the allowlist exactly `{"html.duckduckgo.com"}`, parsed with the stdlib `html.parser` (result links and snippets; DuckDuckGo's `/l/?uddg=` redirect links are decoded to the real URL, ad links dropped). Every search therefore lands in `outbound_log` like any other call. `fetch_page` builds an `Allowlist` per call holding only the host the user asked for and goes through `AllowlistedClient`; it resolves the hostname first and refuses any address that is not public (private, loopback, link-local, reserved, multicast, shared), caps the body at 2 MB and the whole call at 15 s, and a redirect to another host fails the per-hop allowlist check. Both searches and fetches are gated at one request per second per tool and cached for an hour by tool and arguments; errors are not cached. `WEB_SEARCH=false` makes every tool return `{"error": "web_search_off"}` before any network call.

**Keyed search.** An optional Brave Search or Tavily key (`SEARCH_PROVIDER`, `SEARCH_API_PROVIDER`, `SEARCH_API_KEY`, `SEARCH_FALLBACK`, overridden by `~/.homer/credentials/search.json` that Settings writes and the server reads per call) makes `providers.web_search` either use the keyed service first or retry once with it when DuckDuckGo returns `search_blocked`. `keyed.py` sends one request through `AllowlistedClient` with the allowlist exactly `{"api.search.brave.com"}` or `{"api.tavily.com"}`, strips HTML from titles and snippets, wraps them as untrusted and returns `{title, url, snippet, published?}`. `providers.hosts` (mirrored by core's `SearchSettings.hosts` for the Privacy page and `/api/privacy/hosts` `search_hosts`) lists a keyed host only when its key is set; `homer privacy` and `PRIVACY.md` always list both keyed hosts, marked "only if you add a key". The hidden `search_test` tool runs one uncached query for the Settings "Test search" button. No key means today's DuckDuckGo-only path.

**Approvals.** A tier-1 tool never acts. It validates, builds the exact payload, and returns `{"approval_required": true, "action": "<tool name>", "payload": {...}, "preview": "<plain text the user will read>"}`. Each server with tier-1 tools also exposes `execute(action: str, payload: dict) -> dict`; the model is given no tools at all, so only the approvals executor can call it. Core table `approval(id, user_id, server, action, payload_json, payload_hash sha256, preview, status, created_at, decided_at, result_json, channel)`. Status: `pending → running → done | failed | unknown`, or `pending → rejected | expired` (24 h), or `pending → superseded` when the user edits it. Approve = one `UPDATE … SET status='running' WHERE id=? AND status='pending'`; zero rows updated means someone else got there first. The executor recomputes the hash before calling `execute`; an edited payload is a new approval. A timeout or ambiguous failure on a send sets `unknown` and is never retried automatically. Untrusted content (email bodies, web pages) only ever reaches a model call that has no tools and whose output is shown as text, so it cannot trigger an action.

**Router and jobs.** Slash commands and decision words by regex; everything else is one intent call and code-driven jobs (see "Chat request flow"). The model is never given a tool list.

**SSE events added:** `tool_call {name, args}`, `tool_result {name, summary}`, `approval_required {approval_id, action, preview}`.

**Simulator.** `packages/eval/homer_sim`: a FastAPI app serving the Gmail v1, Calendar v3 and People v1 endpoints the google server uses, with in-memory state loaded from a fictional seed (`seed.json`, no real names). Console script `homer-sim --port N`. The google server pointed at it (`GOOGLE_API_BASE=http://127.0.0.1:N`) behaves identically. It is the fixture for every Google e2e test and for the eval runner.

## Third-party licenses

[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) lists the packages bundled in the dashboard, the Geist font license and the Python runtime dependencies with their licenses. Regenerate it when `uv.lock` or `dashboard/pnpm-lock.yaml` changes.
