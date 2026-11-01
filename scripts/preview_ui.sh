#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASSPHRASE="${PREVIEW_PASSPHRASE:-preview}"
HOME_DIR="$(mktemp -d "${TMPDIR:-/tmp}/homer-preview.XXXXXX")"

printf 'HOMER_PASSPHRASE=%s\nSCHEDULER_ENABLED=false\n' "$PASSPHRASE" >"$HOME_DIR/.env"
chmod 600 "$HOME_DIR/.env"

if ! command -v uv >/dev/null 2>&1; then
  printf 'uv is required: https://docs.astral.sh/uv/\n' >&2
  exit 1
fi

if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  printf 'Port 8000 already serves a Homer instance. Stop it, then rerun.\n' >&2
  exit 1
fi

export HOMER_HOME="$HOME_DIR"
export SCHEDULER_ENABLED=false
export HOST=127.0.0.1
export PORT=8000
export EXTRA_ORIGINS='["http://localhost:5173","http://127.0.0.1:5173"]'

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  rm -rf "$HOME_DIR"
}
trap cleanup EXIT INT TERM

cd "$ROOT"
if [ -x "$ROOT/.venv/bin/homer" ]; then
  "$ROOT/.venv/bin/homer" serve >"$HOME_DIR/server.log" 2>&1 &
else
  uv run homer serve >"$HOME_DIR/server.log" 2>&1 &
fi
SERVER_PID=$!

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    printf 'Homer server failed to start:\n' >&2
    tail -n 40 "$HOME_DIR/server.log" >&2
    exit 1
  fi
  sleep 0.5
done

if ! curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  printf 'Homer server did not become healthy:\n' >&2
  tail -n 40 "$HOME_DIR/server.log" >&2
  exit 1
fi

printf '\nUI:         http://localhost:5173/login\n'
printf 'Passphrase: %s\n' "$PASSPHRASE"
printf 'Ollama is not needed. Chat renders but cannot answer; Google pages stay empty.\n\n'

cd "$ROOT/dashboard"
if [ ! -d node_modules ]; then
  printf 'Dashboard dependencies are missing. Run `make build` first.\n' >&2
  exit 1
fi
if command -v pnpm >/dev/null 2>&1; then
  pnpm dev
else
  npm run dev
fi
