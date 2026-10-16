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
