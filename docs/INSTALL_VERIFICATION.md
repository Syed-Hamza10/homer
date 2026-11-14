# Install verification, 2026-11-14

A new-user run of the one-line install on the dev Mac (Apple Silicon, 18 GB, macOS `/bin/bash`
3.2.57), branch `fix/install-verify`. Nothing touched the real `~/.homer`, the real launch agents
or the running Ollama service.

## How it was run

- **Release build**, the commands from `.github/workflows/release.yml`: `uv build --all-packages`,
  drop `homer_eval` and sdists, check the wheel holds `static/index.html` and the manifest,
  `uv export ... -o requirements.lock`, `sha256sum` into `SHA256SUMS`. Output in a temp `dist/`.
- **New user**: a temp `HOME` and `HOMER_HOME`, `env -i` with `PATH=/usr/bin:/bin:/usr/sbin:/sbin`
  plus a folder holding only an `ollama` link, so `uv`, Homebrew and `gh` were all missing.
  `HOMER_PASSPHRASE` fed the passphrase. Command:
  `/bin/bash scripts/install.sh --wheels-dir dist --skip-models --no-service`, after a `--dry-run`.
- **Ollama**: the already-running service on 11434 was used read-only; no model was pulled and
  no chat was sent.
- **Serve**: `homer serve` on a free port (`SCHEDULER_ENABLED=false`), then `/api/health`, `/`,
  login, `/api/google/status`, and a headless Chromium (Playwright) that signed in and read the
  Settings page.
- **Update and rollback**: a local HTTP server shaped like the GitHub releases API
  (`HOMER_RELEASE_API`) serving the real wheels; `homer update`, a tampered wheel, `homer rollback`
  twice, `homer doctor --quick` after each.
- **Uninstall**: decline, default (keeps data), reinstall over the kept data, `--purge`.

## Timings

| Step | Time |
|---|---|
| Release build (dashboard already built; wheels, lock, checksums) | 1 to 2 s (dashboard build about 3 s) |
| Dry run | under 1 s |
| Install `uv` 0.13.1 | 4 to 7 s |
| `uv venv` with a download of CPython 3.12 | 8 s |
| Install 121 packages, cold cache | 24 to 35 s |
| `homer db upgrade` and `homer doctor` (first run compiles bytecode) | 11 to 13 s |
| Whole install without Ollama install and models | 43 to 72 s over four runs |
| `homer doctor --quick` | 2 s |
| `homer serve` until `/api/health` answers | 4 to 10 s |
| `homer update` from the local release | 13 to 16 s |
| `homer update` refused for a bad checksum | 2 s |
| `homer rollback` | 1 s |
| `homer uninstall --purge` | 1 s |

## Bugs found and fixed

1. **Release checksums could never verify.** The workflow wrote `./name.whl` into `SHA256SUMS`;
   the installer and `homer update` look for bare names, so every wheel was "not listed". Now
   `sha256sum -- *.whl ...`, with a test.
2. **The dashboard was blank when the install path had a symlink** (`/tmp` is `/private/tmp`).
   The SPA route resolved the asset path but compared it with the unresolved static folder, so
   every `.js`/`.css` request got `index.html`. The root is resolved now; test added.
3. **`homer update` broke the `homer` command.** The new venv was built as `venv.new` and renamed;
   its scripts kept a `#!.../venv.new/bin/python` line, so the command and the launchd service
   failed after every update. Venvs are now `uv venv --relocatable`; the test runs the swapped
   command.
4. **`homer uninstall` crashed** halfway in the first try: it read the model manifest from the venv
   it had just deleted. It reads first now; test added.
5. **The passphrase prompt could not work with a `curl` one-liner** (it needed stdin to be a
   terminal). It reads `/dev/tty`, explains what the passphrase is for and allows three tries.
6. **No way to install without `gh` or a token.** With neither, the installer now downloads
   `SHA256SUMS` from the public release page and each file it lists (names checked, no paths).
   An authenticated `gh` is still used first; an unauthenticated one no longer stops the install.
7. **Homer packages were looked up by name with `--find-links`**, which also asks PyPI, where the
   `homer-*` names are free to register. The installer now installs the verified wheel files by
   path. The first run with the old command also spent 3 min 6 s resolving; the new one 3.7 s.
8. **`--no-service` still registered the Ollama launch agent** with the real launchd. It now skips
   both services. **`--skip-models`** was added. `--dry-run` reports which tools it found and
   which steps the flags skip.
9. **An already-running Ollama (the Ollama app) would get a second `ollama serve`** from our launch
   agent fighting for port 11434 and restarting forever. The installer now uses the running one
   and says how to set the 16k context. `OLLAMA_URL` and `PORT` are honoured and written to
   `.env`.
10. **A busy port 8000 gave a crash-looping service.** The installer stops early with the fix.
11. **The database migrated while the new service was starting** (both at once). `db upgrade`
    now runs before the service is registered.
12. **`homer update` / `homer restart` called `launchctl kickstart`** even with no service
    installed. They check for the launch agent or unit first and say "start with homer serve".
13. **Settings said "Not connected" with no way forward**: the Connect button only failed with
    "client_secret.json is missing". The Google card now shows the setup steps, the guide link and
    the exact file path until that file exists. `GOOGLE_SETUP.md` is attached to each release.
14. **No uninstall command.** `homer uninstall` removes the launch agents or unit and the venvs,
    keeps the data, asks first; `--purge` deletes `~/.homer`; `--yes` skips the question.
15. **CLI help was bare** (`homer --help` listed names only). Each command has a one-line help.
16. **The smoke job did not run the installer.** It now installs with `/bin/bash
    scripts/install.sh --wheels-dir dist` on macOS and Linux runners.

No stale "achilles" strings remain in the installer, service labels, CLI help or user docs. The
dev Mac itself still runs Ollama from `~/Library/LaunchAgents/dev.achilles.ollama.plist`; it was
left alone. With the fix in item 9, re-running the installer there uses that Ollama as it is.

## What still needs a truly fresh Mac

- The one-line `curl` command itself: the repository is private, so the public release URL
  returns 404 until a release is public (or use `gh`, see `CLIENT_ONBOARDING.md`).
- First-time Ollama install: download, checksum, unpacking `ollama-darwin.tgz` into
  `~/.homer/bin`, and Gatekeeper's view of that binary.
- Model download time for about 7 GB (`qwen3.5:9b` and `nomic-embed-text`).
- Real launchd registration of `dev.homer.ollama` and `dev.homer.server`, the service start, the
  browser opening on its own, and restart at login.
- `homer update` against a real GitHub release (asset URLs, token or anonymous rate limits).
- The interactive passphrase prompt in Terminal.app.
- A Mac with the Ollama app already running, and a Mac below 16 GB (the installer refuses).
