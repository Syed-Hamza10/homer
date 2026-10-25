# Client onboarding

This is the install and hand-over guide for a new Achilles machine. It assumes macOS on Apple
Silicon with 16 GB RAM or more, or Linux with an NVIDIA GPU and 8 GB VRAM or more. You need about
10 GB of disk for the models and 30 GB free for the install and backups.

Everything runs on the client's machine. The dashboard is `http://127.0.0.1:8000`; the language
model runs through Ollama; there is no hosted-model API key and no per-token bill.

## 1. Get the release

The repository is private. On the target machine, install and authenticate GitHub CLI first:

```sh
brew install gh            # Linux: see https://github.com/cli/cli#installation
gh auth login
```

Download the latest release into a directory:

```sh
mkdir -p ~/achilles-release
gh release download -R Syed-Hamza10/achilles -p '*.whl' -D ~/achilles-release
gh release download -R Syed-Hamza10/achilles -p 'install.sh' -D ~/achilles-release
```

If you do not have `gh`, run the installer with a token instead:

```sh
GITHUB_TOKEN=<token> bash install.sh
```

## 2. Install

```sh
cd ~/achilles-release
bash install.sh
```

The installer:

1. checks RAM and disk
2. installs `uv` and Ollama if missing
3. configures Ollama with a 16k context (our launch agent or systemd drop-in, not brew services)
4. creates `~/.achilles/{credentials,data,documents,logs,backups}` with mode 0700
5. writes `~/.achilles/.env` and asks for a passphrase
6. installs the release wheels into `~/.achilles/venv`
7. pulls the model tags from `models/manifest.json`
8. registers a launchd (macOS) or systemd user (Linux) service
9. runs `achilles doctor`

Useful options:

```sh
bash install.sh --wheels-dir ./wheels      # install from local wheels
bash install.sh --no-service               # install without registering the service
bash install.sh --skip-ollama              # do not install or configure Ollama
bash install.sh --dry-run --force          # check the machine, change nothing
```

The passphrase is the only login. Store it in the client's password manager. It is written to
`~/.achilles/.env` with mode 0600; the server compares it in constant time and rate-limits five
failures per minute. Type it at the prompt, or set `ACHILLES_PASSPHRASE` in the environment for an
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
   `~/.achilles/credentials/client_secret.json` with mode 0600
4. run:

```sh
~/.achilles/venv/bin/achilles setup google
```

Workspace admins should publish the app as Internal so tokens do not expire weekly. A plain Gmail
account in Testing mode must re-run `achilles setup google` about every 7 days; mail tools answer
`google_not_connected` when the token has expired.

## 5. Verify

```sh
~/.achilles/venv/bin/achilles doctor
```

All checks should read `ok`. Then open the Privacy page. For normal use the host list should contain
only `127.0.0.1:11434`, `www.googleapis.com`, `oauth2.googleapis.com` and, if web search is on,
`html.duckduckgo.com`. The page also shows `$0.00` spent on inference and the live token counts.

## 6. Operations

The CLI lives at `~/.achilles/venv/bin/achilles`. Add that directory to `PATH` or use the path
directly; the examples below use a short variable:

```sh
ACHILLES=~/.achilles/venv/bin/achilles

$ACHILLES restart          # restart the service
$ACHILLES logs -f          # follow ~/.achilles/logs/achilles.log
$ACHILLES backup           # write ~/.achilles/backups/achilles-<time>.tar.gz (no secrets)
$ACHILLES backup --include-secrets   # also archive credentials/ and .env
$ACHILLES update           # download the latest release and restart
$ACHILLES model use supported   # or degraded, or a tag from models/manifest.json
$ACHILLES privacy -o PRIVACY.md
$ACHILLES forget --yes     # delete the local user and all data; credentials stay
```

A nightly backup runs at 03:00 in the user's timezone. The newest 14 archives are kept. A backup
is a consistent SQLite snapshot, mode 0600. By default it leaves out `credentials/` (the Google
token) and `.env` (the passphrase), so an archive copied off the machine carries no secrets.
`achilles backup --include-secrets` adds them for a full migration to a new machine; treat that
archive like a password.

To restore, stop the service, unpack the archive into `~/.achilles` (keep the existing
`credentials/` and `.env` if the archive has none), and start it:

```sh
~/.achilles/venv/bin/achilles restart
```

## 7. Data and privacy

| Path | Contents |
|---|---|
| `~/.achilles/data/achilles.db` | conversations, mail/calendar cache, approvals, reminders, settings, outbound log |
| `~/.achilles/credentials/` | Google client secret and token, mode 0600 |
| `~/.achilles/backups/` | nightly archives, 14 retained |
| `~/.achilles/logs/` | server and Ollama logs |
| `~/.achilles/documents/` | reserved for the documents feature |

Every outbound runtime call goes through one allowlisted client. The Privacy page and `PRIVACY.md`
describe the host list. This is application-level enforcement, not a network sandbox.

## 8. Troubleshooting

| Symptom | What to do |
|---|---|
| `Ollama unreachable` | `achilles restart`; check `launchctl print gui/$(id -u)/dev.achilles.ollama` or `systemctl --user status ollama` |
| `CONTEXT` is 4096 | Ollama was started by brew services; stop it and let the Achilles launch agent run |
| `google_not_connected` | run `achilles setup google` again; Testing-mode tokens expire weekly |
| Dashboard will not load | `achilles logs -f` and read `~/.achilles/logs/achilles.err.log` |
| Port 8000 is busy | stop the other process, or set `PORT` in `~/.achilles/.env` and restart |
| Model is slow | run `ollama ps`; if the model is not the supported tier, `achilles model use supported` and restart |

## 9. Uninstall

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/dev.achilles.server.plist   # macOS
systemctl --user disable --now achilles                                          # Linux
rm -rf ~/.achilles
```

Remove the Ollama launch agent or drop-in only if Ollama was installed for Achilles alone.
