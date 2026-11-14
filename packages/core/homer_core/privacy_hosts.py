CORE_HOSTS = ("127.0.0.1:11434",)
GOOGLE_HOSTS = ("www.googleapis.com", "oauth2.googleapis.com")
SEARCH_HOSTS = ("html.duckduckgo.com",)
KEYED_SEARCH_HOSTS = {"brave": "api.search.brave.com", "tavily": "api.tavily.com"}
SEARCH_REASONS = {
    SEARCH_HOSTS[0]: "DuckDuckGo HTML search, only when web search is on.",
    KEYED_SEARCH_HOSTS["brave"]: "Brave Search API, only if you add a key. Only the search "
    "question is sent.",
    KEYED_SEARCH_HOSTS["tavily"]: "Tavily search API, only if you add a key. Only the search "
    "question is sent.",
}
INSTALL_HOSTS = (
    "astral.sh",
    "ollama.com",
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
    "pypi.org",
    "files.pythonhosted.org",
)


def privacy_markdown() -> str:
    search_hosts = (*SEARCH_HOSTS, *KEYED_SEARCH_HOSTS.values())
    search_rows = "\n".join(f"| `{host}` | {SEARCH_REASONS[host]} |" for host in search_hosts)
    search_names = ", ".join(f"`{host}`" for host in search_hosts)
    return f"""# Privacy

Homer runs on your machine. Conversations, mail cache, calendar cache, approvals and the
outbound log live in `~/.homer`. The language model runs through Ollama locally; nothing is sent
to a hosted model API, and there is no per-token bill.

## Hosts Homer contacts at runtime

| Host | Why |
|---|---|
| `{CORE_HOSTS[0]}` | The local Ollama server. Model input stays on this machine. |
| `{GOOGLE_HOSTS[0]}` | Gmail, Calendar and People, using the client's own OAuth project. |
| `{GOOGLE_HOSTS[1]}` | Refreshing the Google access token. |
{search_rows}
| a host the user asks `fetch_page` to open | One host per call, re-checked on every redirect. |

Every runtime call goes through one allowlisted HTTP client. The client refuses any other host
before opening a connection, re-checks every redirect hop, and writes one row per call to the
`outbound_log` table. The Privacy page reads that table.

## Install-time hosts

The installer and updater contact these hosts and nothing else:

{chr(10).join(f"- `{host}`" for host in INSTALL_HOSTS)}

They are used to install `uv`, install Ollama, download the release wheels and install their Python
dependencies. They are not contacted at runtime.

## What Homer never does

- It never sends a hosted-model request. There is no OpenAI, Anthropic or other model API key.
- It never opens a host outside the list above unless the user explicitly asks `fetch_page` to open
  it.
- It never sends mail or changes a calendar event without an approval, except email-to-self, which
  is tier 2 by policy.

## Verify it

Open the Privacy page, or query the database:

```sh
sqlite3 ~/.homer/data/homer.db "select host, count(*) from outbound_log group by host;"
```

The only rows you should see for normal use are `127.0.0.1:11434`, `www.googleapis.com`,
`oauth2.googleapis.com` and, when web search is on, one of
{search_names} (the last two only if you add a key).

This is application-level enforcement, not a network sandbox. Say it that way to clients.
"""
