# Decisions

One line each. Newest at the bottom.

- 2026-10-15: Docker dropped from v1. Install is `uv` + Ollama + a launchd/systemd service. Reason: less memory on the client's Mac, one less thing to install, and the desktop app (v1.5) needs the same shape anyway.
- 2026-10-15: Dashboard is Vite + React, not Next.js. Reason: a plain static build served by FastAPI, no Node at runtime.
- 2026-10-15: Google is called through our own thin REST client over `achilles_net`, not `google-api-python-client`. Reason: the official library brings its own HTTP stack and would bypass the allowlist.
- 2026-10-15: Private repo under `Syed-Hamza10`, proprietary license. Reason: the code is the product; the demo video and case study are the public portfolio.
- 2026-10-16: Model tags verified on ollama.com: `qwen3.5:9b` (Q4_K_M, 6.6 GB) and `qwen3.5:4b-q8_0` (5.2 GB).
