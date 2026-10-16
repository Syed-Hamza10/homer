# Decisions

One line each. Newest at the bottom.

- 2026-10-15: Docker dropped from v1. Install is `uv` + Ollama + a launchd/systemd service. Reason: less memory on the client's Mac, one less thing to install, and the desktop app (v1.5) needs the same shape anyway.
- 2026-10-15: Dashboard is Vite + React, not Next.js. Reason: a plain static build served by FastAPI, no Node at runtime.
- 2026-10-15: Google is called through our own thin REST client over `achilles_net`, not `google-api-python-client`. Reason: the official library brings its own HTTP stack and would bypass the allowlist.
- 2026-10-15: Private repo under `Syed-Hamza10`, proprietary license. Reason: the code is the product; the demo video and case study are the public portfolio.
- 2026-10-16: Model tags verified on ollama.com: `qwen3.5:9b` (Q4_K_M, 6.6 GB) and `qwen3.5:4b-q8_0` (5.2 GB).
- 2026-10-16: Spike on M3 Pro 18 GB, `qwen3.5:9b`, 16k context: 27–32 tok/s, first token <1 s warm, ~10 s cold load, 7.7 GB resident / 8.7 GB peak, tool-call round trip 6 s. 9B confirmed as the supported tier.
- 2026-10-16: Thinking is turned off with `reasoning_effort: "none"` on Ollama's OpenAI-compatible API (Pydantic AI `thinking=False` sends exactly this). `think: false` is ignored on that API, and the default thinks for 4–6 minutes per answer. Reason: measured in the spike.
- 2026-10-16: Ollama runs with `OLLAMA_CONTEXT_LENGTH=16384` in its service environment; the OpenAI-compatible API cannot set context per request.
- 2026-10-16: Build backend is `hatchling` for every package. Reason: plan was silent; it is the uv default and needs no config.
- 2026-10-16: Thinking is turned off with `openai_reasoning_effort="none"` in the model settings, not `thinking=False`. Reason: pydantic-ai 2.57's Qwen3.5 profile has `supports_thinking=False`, so `thinking=False` is silently dropped (verified: no `reasoning_effort` in the request, 2k thinking tokens); the explicit setting reaches Ollama.
- 2026-10-16: The agent uses `@agent.instructions`, not `@agent.system_prompt`. Reason: instructions are re-rendered on every run (current time stays fresh) and are not stored in message history.
- 2026-10-16: `achilles_net` stays on legacy `httpx`; pydantic-ai 2.57 warns that `httpx.AsyncClient` providers are deprecated in favour of `httpx2`. The warning is filtered in pytest. Reason: works today; moving the net package to httpx2 is a separate step once the API settles.
- 2026-10-16: Hardware tier is detected at startup (`platform.hardware_tier`) and picks the model tag from the manifest; no override setting yet. Reason: the Settings page (step 5) owns model choice.
- 2026-10-16: `CORSMiddleware` with `own_origins` and credentials is on, so the Vite dev server (`EXTRA_ORIGINS`) can call the API with the cookie. Reason: needed for `make dev`; harmless in production where the dashboard is same-origin.
- 2026-10-16: pytest runs with `--import-mode=importlib`. Reason: `packages/net/tests` and `packages/core/tests` are both named `tests`; the default mode cannot import two packages with the same name.
- 2026-10-16: `httpx` is allowed under `packages/*/tests/**` (ruff per-file-ignore for TID251). Reason: the e2e suite talks to the real server over real HTTP; production code still goes through `achilles_net` only.
- 2026-10-16: `test_login_rules` starts its own server process instead of using the session one. Reason: the login limiter is in-process state that blocks every login for 60 s once tripped, which would stall the chat and browser tests.
- 2026-10-16: e2e tests are moved to the end of the collection (`pytest_collection_modifyitems` in `tests/e2e/conftest.py`). Reason: pytest-playwright's sync API keeps an asyncio loop running for the rest of the session, and pytest-asyncio tests that run after it fail with "cannot be called from a running event loop".
- 2026-10-16: `remind(text, when_iso)` is a core-native tool writing the `reminders` table, not a system-server tool. Reason: the scheduler and the Today page own reminders; the server only parses dates.
- 2026-10-16: Tables are `approvals` and `reminders` (plural, as in plan §8.1), not the contract's singular `approval`. Reason: every existing table is plural.
- 2026-10-16: `health` is hidden from the model together with `execute`. Reason: every server has one, so the names collide in the combined toolset, and the model has no use for it.
- 2026-10-16: The toolset classifier is a second `Agent` on the same model, run non-streamed; its tokens are added to the chat's `done` totals and the token counter, with one `requests` increment per chat.
- 2026-10-16: MCP toolsets use `tool_error_behavior="failed"`. Reason: the model sees a tool error once as a result instead of a retry loop; for `execute`, a `ToolFailed` is a clear failure (`failed`) and anything else (timeout, transport) is `unknown`.
- 2026-10-16: Approvals expire lazily: `expire_stale` runs inside `list_pending`, `approve` and `reject`. Reason: no scheduler until step 4; the state is still correct whenever it is read.
- 2026-10-16: A tier-2 action (`mail_label`, `mail_archive`) proposed after `<untrusted>` content is turned into an approval by the core and later run through the same server `execute(action, payload)`. Assumes the google server's `execute` accepts those two actions.
- 2026-10-16: Chat `Deps` carries the DB session and user id. Reason: `remind` and the approval gate write rows during a run.
- 2026-10-16: `/remind <text>` runs the agent with the `system` toolset and the prompt "Set a reminder: <text>", skipping classification. `/reject N` exists next to `/approve N`.
- 2026-10-16: Unit tests use `TestModel(call_tools=[])`. Reason: the default calls every visible tool on the first turn.
- 2026-10-16: Full `fastmcp` (server extra) is a core dev dependency only; runtime stays on `fastmcp-slim` from `pydantic-ai-slim[mcp]`. Reason: the stand-in MCP servers in `tests/fake_servers/` need the server side.
- 2026-10-16: e2e starts the server from the venv's own `achilles` binary, not `uv run`. Reason: `uv run` puts the venv bin first on PATH, which would shadow the stand-in `achilles-mcp-google` once a real one is installed; the approval e2e must stay deterministic.
