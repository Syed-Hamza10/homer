# Changelog

## Unreleased

- Step 0 spike: model benchmarked on the dev machine; 9B tier and thinking-off method settled.
- Step 1 skeleton: uv workspace; `achilles_net` allowlisted client with outbound log and lint rule; settings, platform checks, model factory; SQLite with Alembic; passphrase login with rate limit, signed cookie and Origin check; streaming chat over SSE with persisted conversations and token counter; `achilles serve`, `doctor`, `db upgrade`; React dashboard with login and chat; CI on ubuntu and macos.
- Step 2 core: MCP manager over stdio with hidden `execute`/`health`; five curated toolsets; slash-command router plus one-word classification; `remind` tool and `reminders` table; approvals queue (`pending → running → done | failed | unknown`, `rejected`, `expired`) with payload hash check and untrusted-content gating of tier-2 actions; `tool_call`, `tool_result` and `approval_required` SSE events; `/api/approvals`, `/api/privacy`, `/api/reminders`; dashboard nav with Approvals and Privacy pages and inline approval cards; stand-in MCP servers for the test suites.
