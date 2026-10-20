# Privacy

Achilles runs on your machine. Conversations, mail cache, calendar cache, approvals and the
outbound log live in `~/.achilles`. The language model runs through Ollama locally; nothing is sent
to a hosted model API, and there is no per-token bill.

## Hosts Achilles contacts at runtime

| Host | Why |
|---|---|
| `127.0.0.1:11434` | The local Ollama server. No email or document leaves the machine. |
| `www.googleapis.com` | Gmail, Calendar and People, using the client's own OAuth project. |
| `oauth2.googleapis.com` | Refreshing the Google access token. |
| `html.duckduckgo.com` | DuckDuckGo HTML search, only when web search is on. |
| a host the user asks `fetch_page` to open | One host per call, re-checked on every redirect. |

Every runtime call goes through one allowlisted HTTP client. The client refuses any other host
before opening a connection, re-checks every redirect hop, and writes one row per call to the
`outbound_log` table. The Privacy page reads that table.

## Install-time hosts

The installer and updater contact these hosts and nothing else:

- `astral.sh`
- `ollama.com`
- `github.com`
- `api.github.com`
- `objects.githubusercontent.com`
- `release-assets.githubusercontent.com`
- `pypi.org`
- `files.pythonhosted.org`

They are used to install `uv`, install Ollama, download the release wheels and install their Python
dependencies. They are not contacted at runtime.

## What Achilles never does

- It never sends a hosted-model request. There is no OpenAI, Anthropic or other model API key.
- It never opens a host outside the list above unless the user explicitly asks `fetch_page` to open
  it.
- It never sends mail or changes a calendar event without an approval, except email-to-self, which
  is tier 2 by policy.

## Verify it

Open the Privacy page, or query the database:

```sh
sqlite3 ~/.achilles/data/achilles.db "select host, count(*) from outbound_log group by host;"
```

The only rows you should see for normal use are `127.0.0.1:11434`, `www.googleapis.com`,
`oauth2.googleapis.com` and, when web search is on, `html.duckduckgo.com`.

This is application-level enforcement, not a network sandbox. Say it that way to clients.
