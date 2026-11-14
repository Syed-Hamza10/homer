# Client onboarding

## Quick start for a new Mac

**You need:** a Mac with Apple Silicon (M1 or newer), 16 GB of memory, 30 GB of free disk, and an
internet connection. Nothing else: no Homebrew, Python or developer tools.

Open **Terminal** (press Cmd+Space, type "Terminal", press Return), paste this line and press
Return:

```sh
/bin/bash -c "$(curl -fsSL https://github.com/Syed-Hamza10/homer/releases/latest/download/install.sh)"
```

> The repository is private for now, so this link only works once a release is public. Until then,
> see "Before the release is public" below.

The installer asks one thing: **a passphrase**, typed twice. It is how you sign in to Homer, so
save it in your password manager. Nothing shows on screen while you type it.

What happens and how long it takes (measured on an M-series Mac with 18 GB, see
`docs/INSTALL_VERIFICATION.md`):

| Step | Time |
|---|---|
| Check memory, disk and timezone | under 1 s |
| Install `uv` (the Python installer) | about 5 s |
| Install Ollama (skipped if it is already there) | about 1 min (estimate, not yet measured) |
| Set up Python and install Homer | 30 to 60 s |
| Download the AI models, about 7 GB, only the first time | about 10 min at 100 Mbit/s (estimate) |
| Start Homer and check it | about 15 s |

When it finishes, Homer is running and your browser opens **http://127.0.0.1:8000**. Sign in
with your passphrase. Homer starts again by itself when you log in to your Mac.

**Connect Google** (about 15 minutes, once): open Settings in Homer. The Google card shows the
steps and the exact file path. In short, follow `docs/GOOGLE_SETUP.md` (also attached to each
release as `GOOGLE_SETUP.md`) to create a Google sign-in file, save it as
`~/.homer/credentials/client_secret.json`, then press **Connect**.

If the Ollama app is already running, the installer uses it as it is and asks you to set its
context length to 16k in the Ollama settings (or quit the app and run the installer again).
If port 8000 is taken, the installer stops and tells you; put `PORT=8100 ` in front of the line.

**To remove Homer:** `~/.homer/venv/bin/homer uninstall` removes the background services and the
program and keeps your data; add `--purge` to delete `~/.homer` too. It asks before removing
anything.

### Before the release is public

Install GitHub CLI and sign in with an account that can read the repository, then run the
installer; it downloads the private release with `gh`:

```sh
brew install gh && gh auth login
gh release download -R Syed-Hamza10/homer -p install.sh -D ~/homer-release
/bin/bash ~/homer-release/install.sh
```

Without `gh`, pass a token instead: `GITHUB_TOKEN=<token> /bin/bash install.sh`. The token is
saved to `~/.homer/github_token` (mode 0600) so `homer update` can use it later.

## Details for the person doing the install

Homer runs on macOS on Apple Silicon with 16 GB RAM or more, or Linux with an NVIDIA GPU and 8 GB
VRAM or more. Everything runs on the client's machine. The dashboard is `http://127.0.0.1:8000`;
the language model runs through Ollama; there is no hosted-model API key and no per-token bill.

## 1. What the release holds

Each release holds the wheels, a `SHA256SUMS` file, the locked dependency set
`requirements.lock`, `install.sh`, this guide, `PRIVACY.md` and `GOOGLE_SETUP.md`. With no
`gh` and no token, the installer downloads `SHA256SUMS` from the public release page and then each
file it lists.

## 2. Install

The installer:

1. checks RAM, disk and that port 8000 is free
2. installs pinned versions of `uv` and Ollama if missing (the versions are at the top of the
   script; the Ollama download is checked against its published checksum)
3. configures Ollama with a 16k context (our launch agent or systemd drop-in, not brew services),
   unless an Ollama it did not set up is already running
4. creates `~/.homer/{credentials,data,documents,logs,backups}` with mode 0700
5. writes `~/.homer/.env` with the detected timezone and asks for a passphrase
6. verifies every wheel against `SHA256SUMS` and refuses to continue on a mismatch
7. installs the wheels into `~/.homer/venv` with `requirements.lock` pinning every dependency
8. pulls the model tags from `models/manifest.json`
9. registers a launchd (macOS) or systemd user (Linux) service
10. runs `homer doctor` and opens the dashboard

Useful options:

```sh
bash install.sh --wheels-dir ./wheels      # install from local wheels (warns if unverified)
bash install.sh --no-service               # register no launchd/systemd service (Homer or Ollama)
bash install.sh --skip-ollama              # do not install or configure Ollama
bash install.sh --skip-models              # do not pull the models
bash install.sh --dry-run --force          # check the machine, print the plan, change nothing
bash install.sh --render server-plist      # print a service definition without installing
HOMER_PASSPHRASE=... bash install.sh       # unattended install, no prompt
PORT=8100 bash install.sh                  # serve the dashboard on another port
```

The passphrase is the only login. Store it in the client's password manager. It is written to
`~/.homer/.env` with mode 0600; the server compares it in constant time and rate-limits five
failures per minute. Type it at the prompt, or set `HOMER_PASSPHRASE` in the environment for an
unattended install. Avoid `--passphrase`: it stays in the shell history, and the installer warns.

## 3. First sign-in

Open `http://127.0.0.1:8000`, enter the passphrase, and ask one short question (for example
"What is on my calendar tomorrow?"). The first answer is about 10 seconds slower while the model
loads.

Verify the model settings once:

```sh
ollama ps
```

`CONTEXT` must be `16384` and the model size about 7.7 GB. If it says 4096, the service environment
is wrong; re-run the installer and do not start Ollama with `brew services`.

## 4. Connect Google

Use the client's own Google Cloud project and account. The full click-by-click guide is
`docs/GOOGLE_SETUP.md` in the repository. In short:

1. create a GCP project and enable Gmail, Calendar and People APIs
2. configure the OAuth consent screen (Internal for Workspace, External + Testing for Gmail)
3. create a Desktop OAuth client and save the JSON as
   `~/.homer/credentials/client_secret.json` with mode 0600
4. run:

```sh
~/.homer/venv/bin/homer setup google
```

Workspace admins should publish the app as Internal so tokens do not expire weekly. A plain Gmail
account in Testing mode must re-run `homer setup google` about every 7 days; mail tools answer
`google_not_connected` when the token has expired.

## 5. Verify

```sh
~/.homer/venv/bin/homer doctor
```

All checks should read `ok`. Then open the Privacy page. For normal use the host list should contain
only `127.0.0.1:11434`, `www.googleapis.com`, `oauth2.googleapis.com` and, if web search is on,
`html.duckduckgo.com`. The page also shows `$0.00` spent on inference and the live token counts.

### Optional: a search API key

DuckDuckGo needs no key but sometimes blocks a burst of searches for 20 minutes or more. A free key
from [Brave Search](https://brave.com/search/api/) ($5 of free credit a month, about 1,000
searches; a card is asked for to prevent abuse) or [Tavily](https://tavily.com/) (1,000 free
credits a month, no card) fixes that.

1. Create the key on the provider's site.
2. Open Settings, Web search. Pick "DuckDuckGo" with that service as the backup (the key is used
   only when DuckDuckGo blocks), or pick Brave or Tavily to use the key for every search.
3. Paste the key and press Save. The field then shows `Saved · …abcd`, the last four characters.
4. Press "Test search". It reports ok, blocked or "did not accept the key".

The change applies on the next search; no restart. The key is stored in
`~/.homer/credentials/search.json` (mode 600), left out of backups unless `--include-secrets`, and
no API returns it. Only the search question goes to the provider, never emails or documents; the
Privacy page then lists `api.search.brave.com` or `api.tavily.com`. Without the dashboard, set
`SEARCH_PROVIDER` (`duckduckgo`, `brave` or `tavily`), `SEARCH_API_PROVIDER` (`brave` or `tavily`,
the backup when the provider is DuckDuckGo), `SEARCH_API_KEY` and `SEARCH_FALLBACK` (default
`true`) in `~/.homer/.env` and restart.

## 6. Operations

The CLI lives at `~/.homer/venv/bin/homer`. Add that directory to `PATH` or use the path
directly; the examples below use a short variable:

```sh
HOMER=~/.homer/venv/bin/homer

$HOMER restart          # restart the service
$HOMER logs -f          # follow ~/.homer/logs/homer.log
$HOMER backup           # write ~/.homer/backups/homer-<time>.tar.gz (no secrets)
$HOMER backup --include-secrets   # also archive credentials/ and .env
$HOMER update           # install the latest release next to the current one, then swap
$HOMER rollback         # swap the previous release back
$HOMER doctor --quick   # check the install only, skipping Ollama and hardware
$HOMER model use supported   # or degraded, or a tag from models/manifest.json
$HOMER privacy -o PRIVACY.md
$HOMER forget --yes     # delete the local user and all data; credentials stay
$HOMER uninstall        # remove the services and program, keep the data (see section 9)
```

A nightly backup runs at 03:00 in the user's timezone. The newest 14 archives are kept. A backup
is a consistent SQLite snapshot, mode 0600. By default it leaves out `credentials/` (the Google
token) and `.env` (the passphrase), so an archive copied off the machine carries no secrets.
`homer backup --include-secrets` adds them for a full migration to a new machine; treat that
archive like a password.

To restore, stop the service, unpack the archive into `~/.homer` (keep the existing
`credentials/` and `.env` if the archive has none), and start it:

```sh
~/.homer/venv/bin/homer restart
```

### Updates

`homer update` never changes the running install in place. It downloads the newest release
(with `curl`, no `gh` needed; the token comes from `GITHUB_TOKEN` or `~/.homer/github_token`), verifies the wheels
against `SHA256SUMS`, installs them with the release's `requirements.lock` into
`~/.homer/venv.new`, and runs `homer doctor --quick` from that new environment. Only when
that passes does it rename `venv` to `venv.prev` and `venv.new` to `venv`, then restart the
service. If anything fails it prints why and the current install is untouched.
`homer rollback` swaps `venv.prev` back and restarts; pass `--version vX.Y.Z` to `update` to
install a specific release.

## 7. Data and privacy

| Path | Contents |
|---|---|
| `~/.homer/data/homer.db` | conversations, mail/calendar cache, approvals, reminders, settings, outbound log |
| `~/.homer/credentials/` | Google client secret and token, mode 0600 |
| `~/.homer/backups/` | nightly archives, 14 retained |
| `~/.homer/logs/` | server and Ollama logs |
| `~/.homer/documents/` | reserved for the documents feature |

Every outbound runtime call goes through one allowlisted client. The Privacy page and `PRIVACY.md`
describe the host list. This is application-level enforcement, not a network sandbox.

## 8. Troubleshooting

| Symptom | What to do |
|---|---|
| `Ollama unreachable` | `homer restart`; check `launchctl print gui/$(id -u)/dev.homer.ollama` or `systemctl --user status ollama` |
| `CONTEXT` is 4096 | Ollama was started by brew services; stop it and let the Homer launch agent run |
| `google_not_connected` | run `homer setup google` again; Testing-mode tokens expire weekly |
| Dashboard will not load | `homer logs -f` and read `~/.homer/logs/homer.err.log` |
| Port 8000 is busy | stop the other process, or set `PORT` in `~/.homer/.env` and restart |
| Model is slow | run `ollama ps`; if the model is not the supported tier, `homer model use supported` and restart |

## 9. Uninstall

```sh
~/.homer/venv/bin/homer uninstall           # services and program; data stays in ~/.homer
~/.homer/venv/bin/homer uninstall --purge   # also delete ~/.homer: data, credentials, backups
```

It lists what it will remove and asks first (`--yes` skips the question). The models stay in
Ollama; the command prints the `ollama rm` line that frees the space. `uv`, its Python and its
cache stay in `~/.local` and `~/.cache/uv`. If the program is already gone, remove the services by
hand:

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/dev.homer.server.plist   # macOS
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/dev.homer.ollama.plist   # macOS
systemctl --user disable --now homer                                          # Linux
rm -rf ~/.homer
```
