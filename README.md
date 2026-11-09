<p align="center">
  <img src="docs/screenshots/logo.png" alt="Homer" width="560">
</p>

Homer is a private AI assistant for Gmail and Google Calendar, built for Google Workspace teams
and running entirely on your machine. The model runs locally through Ollama, mail and calendar
work goes through MCP tool servers, and data stays in SQLite under `~/.homer`. Homer answers
questions, drafts replies in your tone, finds free time and proposes calendar changes; anything
another person would see waits for your approval, and every outbound request goes through one
allowlisted HTTP client with a local audit log.

<p align="center">
  <img src="docs/screenshots/main.png" alt="Homer chat screen showing calendar questions, a drafted reply and proposed changes waiting for approval" width="100%">
</p>

## Features

| Area | What it does |
| --- | --- |
| **Chat** | Streaming markdown answers, source chips, copy and timestamps, stop, regenerate, and a searchable conversation sidebar. |
| **Today** | A "Your day" card with meetings, emails that need you, follow-ups and waiting approvals. |
| **Inbox** | A live three-pane Gmail view with labels, search, sanitised HTML, attachments and a composer. |
| **Calendar** | Day/Week/Month views with drag-to-create and drag-to-move, all through approvals. |
| **Approvals** | Editable email and event cards, payload hashing, single-use decisions and 24-hour expiry. |
| **Memory and search** | "Remember that…" facts stored locally, plus DuckDuckGo answers with source links. |
| **Privacy and operations** | Outbound host log, web-search switch, backups, installer updates and rollback. |

## Quick start

You need macOS on Apple Silicon with 16 GB RAM or more, or Linux with an 8 GB GPU. Ollama, a
Google OAuth client for Gmail and Calendar, and uv plus pnpm 10 are also required; the full list is
in the [project guide](docs/PROJECT_GUIDE.md#requirements).

```sh
ollama pull qwen3.5:9b
ollama pull nomic-embed-text
OLLAMA_CONTEXT_LENGTH=16384 ollama serve
```

In a second terminal:

```sh
git clone https://github.com/Syed-Hamza10/homer.git
cd homer

uv sync --all-packages
mkdir -p ~/.homer
printf 'HOMER_PASSPHRASE=change-me\n' > ~/.homer/.env
chmod 600 ~/.homer/.env

make build
uv run homer doctor
uv run homer serve
```

Open **http://127.0.0.1:8000** and sign in with that passphrase. To connect Google, follow
[the Google setup guide](docs/GOOGLE_SETUP.md), then run `uv run homer-mcp-google-setup`.

## Install as a service

On a client machine, use the installer from a release. It pins `uv` and Ollama, verifies every
wheel against `SHA256SUMS`, installs into `~/.homer/venv`, registers a launchd or systemd user
service, and runs `homer doctor`.

```sh
bash install.sh
```

See [CLIENT_ONBOARDING.md](CLIENT_ONBOARDING.md) for the complete install, OAuth setup, operations
and troubleshooting procedure.

## Documentation

- [Project guide](docs/PROJECT_GUIDE.md) — architecture, features, testing and limitations
- [Architecture](docs/ARCHITECTURE.md) — request flow, API and approvals
- [Privacy](PRIVACY.md) — every host Homer contacts, and how to verify it
- [Client onboarding](CLIENT_ONBOARDING.md) — install, Google setup and operations

## License

Homer is proprietary software. The source is published for evaluation only; copying, modification,
distribution or use requires a written license. See [LICENSE](LICENSE).
