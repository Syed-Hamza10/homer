#!/usr/bin/env bash
set -euo pipefail

UV_VERSION="0.13.1"
OLLAMA_VERSION="0.40.5"
UV_INSTALLER="https://astral.sh/uv/${UV_VERSION}/install.sh"
OLLAMA_RELEASE="https://github.com/ollama/ollama/releases/download/v${OLLAMA_VERSION}"
OLLAMA_INSTALLER="https://ollama.com/install.sh"

REPO="Syed-Hamza10/homer"
RELEASES="${HOMER_RELEASE_URL:-https://github.com/$REPO/releases}"
VERSION="${HOMER_VERSION:-latest}"
HOMER_HOME="${HOMER_HOME:-$HOME/.homer}"
WHEELS_DIR=""
TOKEN="${GITHUB_TOKEN:-${HOMER_GITHUB_TOKEN:-}}"
PASSPHRASE="${HOMER_PASSPHRASE:-}"
PASSPHRASE_FLAG=0
NO_SERVICE=0
SKIP_OLLAMA=0
SKIP_MODELS=0
DRY_RUN=0
FORCE=0
RENDER=""

log() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: scripts/install.sh [options] (published as install.sh on each release)

  --version TAG     Release tag to install (default: latest)
  --home PATH       Homer home (default: ~/.homer)
  --wheels-dir DIR  Install from local wheels instead of a GitHub release
  --token TOKEN     GitHub token for the private release
  --passphrase P    Initial passphrase (discouraged: lands in shell history; prefer
                    HOMER_PASSPHRASE in the environment or the interactive prompt)
  --no-service      Do not register the Homer or Ollama launchd/systemd services
  --skip-ollama     Do not install or configure Ollama
  --skip-models     Do not pull the models (Ollama must already have them)
  --dry-run         Check the machine and print the plan; change nothing
  --force           Continue when RAM or disk is below the recommendation
  --render NAME     Print a service definition and exit
                    (ollama-plist, ollama-dropin, server-plist, server-unit)
  -h, --help        Show this help

Pinned: uv $UV_VERSION, Ollama $OLLAMA_VERSION. Release wheels are verified against SHA256SUMS
and installed with the release's requirements.lock as constraints.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --home) HOMER_HOME="$2"; shift 2 ;;
    --wheels-dir) WHEELS_DIR="$2"; shift 2 ;;
    --token) TOKEN="$2"; shift 2 ;;
    --passphrase) PASSPHRASE="$2"; PASSPHRASE_FLAG=1; shift 2 ;;
    --no-service) NO_SERVICE=1; shift ;;
    --skip-ollama) SKIP_OLLAMA=1; shift ;;
    --skip-models) SKIP_MODELS=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    --render) RENDER="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

export HOMER_HOME

VENV="$HOMER_HOME/venv"
LABEL="dev.homer.server"
OLLAMA_LABEL="dev.homer.ollama"
OLLAMA_BIN="${OLLAMA_BIN:-ollama}"
DEFAULT_OLLAMA_URL="http://127.0.0.1:11434"
OLLAMA_URL="${OLLAMA_URL:-$DEFAULT_OLLAMA_URL}"
PORT="${PORT:-8000}"
DASHBOARD="http://127.0.0.1:$PORT"

render_ollama_plist() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$OLLAMA_LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$OLLAMA_BIN</string><string>serve</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_CONTEXT_LENGTH</key><string>16384</string>
    <key>OLLAMA_KEEP_ALIVE</key><string>30m</string>
    <key>OLLAMA_FLASH_ATTENTION</key><string>1</string>
    <key>OLLAMA_KV_CACHE_TYPE</key><string>q8_0</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOMER_HOME/logs/ollama.log</string>
  <key>StandardErrorPath</key><string>$HOMER_HOME/logs/ollama.err.log</string>
</dict>
</plist>
EOF
}

render_ollama_dropin() {
  cat <<EOF
[Service]
Environment="OLLAMA_CONTEXT_LENGTH=16384"
Environment="OLLAMA_KEEP_ALIVE=30m"
Environment="OLLAMA_FLASH_ATTENTION=1"
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
EOF
}

render_server_plist() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$VENV/bin/homer</string><string>serve</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOMER_HOME</key><string>$HOMER_HOME</string>
    <key>PATH</key><string>$VENV/bin:$HOMER_HOME/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>WorkingDirectory</key><string>$HOMER_HOME</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOMER_HOME/logs/homer.log</string>
  <key>StandardErrorPath</key><string>$HOMER_HOME/logs/homer.err.log</string>
</dict>
</plist>
EOF
}

render_server_unit() {
  cat <<EOF
[Unit]
Description=Homer local assistant
After=network-online.target

[Service]
WorkingDirectory=$HOMER_HOME
Environment=HOMER_HOME=$HOMER_HOME
Environment=PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$VENV/bin/homer serve
Restart=always
RestartSec=3
StandardOutput=append:$HOMER_HOME/logs/homer.log
StandardError=append:$HOMER_HOME/logs/homer.err.log

[Install]
WantedBy=default.target
EOF
}

if [ -n "$RENDER" ]; then
  case "$RENDER" in
    ollama-plist) render_ollama_plist ;;
    ollama-dropin) render_ollama_dropin ;;
    server-plist) render_server_plist ;;
    server-unit) render_server_unit ;;
    *) die "unknown service definition: $RENDER" ;;
  esac
  exit 0
fi

if [ "$PASSPHRASE_FLAG" = "1" ]; then
  warn "--passphrase is saved in your shell history; next time set HOMER_PASSPHRASE or use the prompt"
fi

OS="$(uname -s)"
case "$OS" in
  Darwin|Linux) ;;
  *) die "supported platforms are macOS and Linux" ;;
esac

if [ "$OS" = "Darwin" ]; then
  RAM_BYTES="$(sysctl -n hw.memsize)"
else
  RAM_BYTES="$(awk '/MemTotal/ {print $2 * 1024}' /proc/meminfo)"
fi
RAM_GB=$((RAM_BYTES / 1073741824))
DISK_PATH="$HOMER_HOME"
while [ ! -d "$DISK_PATH" ]; do DISK_PATH="$(dirname "$DISK_PATH")"; done
FREE_BYTES="$(df -Pk "$DISK_PATH" | awk 'NR==2 {print $4 * 1024}')"
FREE_GB=$((FREE_BYTES / 1073741824))

zoneinfo_name() { readlink /etc/localtime 2>/dev/null | sed -n 's#.*zoneinfo/##p'; }

detect_timezone() {
  local tz=""
  if [ "$OS" = "Linux" ]; then
    command -v timedatectl >/dev/null 2>&1 && tz="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
    [ -n "$tz" ] || { [ -f /etc/timezone ] && tz="$(tr -d '[:space:]' </etc/timezone)"; }
  fi
  [ -n "$tz" ] || tz="$(zoneinfo_name)"
  printf '%s' "${tz:-UTC}"
}
TIMEZONE="$(detect_timezone)"

log "platform: $OS, RAM: ${RAM_GB} GB, free disk: ${FREE_GB} GB, timezone: $TIMEZONE"
if [ "$RAM_GB" -lt 16 ]; then
  if [ "$FORCE" = "1" ]; then
    warn "16 GB RAM is recommended for the supported model tier"
  else
    die "16 GB RAM is required (use --force to override)"
  fi
fi
if [ "$FREE_GB" -lt 30 ]; then
  if [ "$FORCE" = "1" ]; then
    warn "30 GB disk is recommended"
  else
    die "30 GB free disk is required (use --force to override)"
  fi
fi

port_used_by_another_program() {
  local code=0
  curl -s -o /dev/null -m 2 "$DASHBOARD/" || code=$?
  [ "$code" -ne 7 ] || return 1
  ! curl -fsS -m 2 "$DASHBOARD/api/health" 2>/dev/null | grep -q '"model_status"'
}
if port_used_by_another_program; then
  die "port $PORT is used by another program; run the installer again with PORT=8100 in front of the command"
fi

if [ "$DRY_RUN" = "1" ]; then
  if [ -n "$WHEELS_DIR" ]; then SOURCE="the wheels in $WHEELS_DIR"; else SOURCE="release $VERSION from $RELEASES"; fi
  if command -v uv >/dev/null 2>&1; then UV_STEP="use uv at $(command -v uv)"
  else UV_STEP="install uv $UV_VERSION (from $UV_INSTALLER)"; fi
  if [ "$SKIP_OLLAMA" = "1" ]; then OLLAMA_STEP="skip Ollama (--skip-ollama)"
  elif command -v ollama >/dev/null 2>&1; then OLLAMA_STEP="use Ollama at $(command -v ollama) and wait for it at $OLLAMA_URL"
  else OLLAMA_STEP="install Ollama $OLLAMA_VERSION, verified against its sha256sum.txt, and wait for it at $OLLAMA_URL"; fi
  if [ "$SKIP_MODELS" = "1" ] || [ "$SKIP_OLLAMA" = "1" ]; then MODELS_STEP="skip the model downloads"
  else MODELS_STEP="pull the manifest models (about 7 GB the first time)"; fi
  if [ "$NO_SERVICE" = "1" ]; then SERVICE_STEP="register no services (--no-service); you start it with homer serve"
  else SERVICE_STEP="register and start the Ollama and Homer services, then open $DASHBOARD"; fi
  cat <<EOF

Dry run only. The installer would:
  1. $UV_STEP
  2. $OLLAMA_STEP
  3. create $HOMER_HOME/{credentials,data,documents,logs,backups,venv} with mode 0700
  4. ask for a dashboard passphrase and write $HOMER_HOME/.env with TIMEZONE=$TIMEZONE
  5. fetch $SOURCE, SHA256SUMS and requirements.lock, and verify every wheel against SHA256SUMS
  6. install the verified wheels into $HOMER_HOME/venv with requirements.lock as constraints
  7. $MODELS_STEP
  8. $SERVICE_STEP
  9. run homer doctor
EOF
  exit 0
fi

sha256_check() {
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$1" && sha256sum -c --ignore-missing --quiet "$2")
  else
    (cd "$1" && shasum -a 256 -c --ignore-missing --quiet "$2")
  fi
}

verify_wheels() {
  local dir="$1" sums="$1/SHA256SUMS" wheel
  for wheel in "$dir"/*.whl; do
    grep -q " \*\{0,1\}$(basename "$wheel")\$" "$sums" \
      || die "$(basename "$wheel") is not listed in SHA256SUMS"
  done
  sha256_check "$dir" SHA256SUMS || die "checksum mismatch: refusing to install the wheels"
  log "Verified $(ls "$dir"/*.whl | wc -l | tr -d ' ') wheels against SHA256SUMS"
}

mkdir -p "$HOMER_HOME"/{credentials,data,documents,logs,backups}
chmod 700 "$HOMER_HOME" "$HOMER_HOME"/{credentials,data,documents,logs,backups}

if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv $UV_VERSION"
  curl -LsSf "$UV_INSTALLER" | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || die "uv is not on PATH after installation"

prompt_passphrase() {
  (: </dev/tty) 2>/dev/null \
    || die "set HOMER_PASSPHRASE in the environment, or run the installer in a terminal to be prompted"
  printf 'Choose a passphrase. You type it to open the Homer dashboard; keep it in your password manager.\n'
  local tries=0 confirm
  while [ "$tries" -lt 3 ]; do
    read -rsp "Passphrase: " PASSPHRASE </dev/tty; echo
    read -rsp "Repeat it: " confirm </dev/tty; echo
    if [ -n "$PASSPHRASE" ] && [ "$PASSPHRASE" = "$confirm" ]; then return 0; fi
    warn "the passphrases were empty or did not match; try again"
    tries=$((tries + 1))
  done
  die "no passphrase set"
}

ENV_FILE="$HOMER_HOME/.env"
if [ ! -f "$ENV_FILE" ]; then
  [ -n "$PASSPHRASE" ] || prompt_passphrase
  ESCAPED="$(printf '%s' "$PASSPHRASE" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')"
  cat >"$ENV_FILE" <<EOF
HOMER_HOME="$HOMER_HOME"
HOMER_PASSPHRASE="$ESCAPED"
WEB_SEARCH=true
SCHEDULER_ENABLED=true
TIMEZONE=$TIMEZONE
EOF
  [ "$OLLAMA_URL" = "$DEFAULT_OLLAMA_URL" ] || printf 'OLLAMA_URL=%s\n' "$OLLAMA_URL" >>"$ENV_FILE"
  [ "$PORT" = "8000" ] || printf 'PORT=%s\n' "$PORT" >>"$ENV_FILE"
  chmod 600 "$ENV_FILE"
  log "Wrote $ENV_FILE"
  log "Your passphrase is stored in $ENV_FILE (readable only by you). To change it later, run: homer passphrase"
elif grep -q '^TIMEZONE=' "$ENV_FILE"; then
  log "Keeping existing $ENV_FILE"
else
  printf 'TIMEZONE=%s\n' "$TIMEZONE" >>"$ENV_FILE"
  log "Keeping existing $ENV_FILE, added TIMEZONE=$TIMEZONE"
fi

if [ -n "$TOKEN" ]; then
  printf '%s\n' "$TOKEN" >"$HOMER_HOME/github_token"
  chmod 600 "$HOMER_HOME/github_token"
  log "Saved the GitHub token to $HOMER_HOME/github_token for homer update"
fi

install_ollama_darwin() {
  local tmp
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/ollama-darwin.tgz" "$OLLAMA_RELEASE/ollama-darwin.tgz"
  curl -fsSL -o "$tmp/sha256sum.txt" "$OLLAMA_RELEASE/sha256sum.txt"
  sha256_check "$tmp" sha256sum.txt || die "Ollama $OLLAMA_VERSION checksum mismatch"
  mkdir -p "$HOMER_HOME/bin"
  tar -xzf "$tmp/ollama-darwin.tgz" -C "$HOMER_HOME/bin"
  rm -rf "$tmp"
  export PATH="$HOMER_HOME/bin:$PATH"
}

ollama_up() { curl -fsS -m 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; }

register_ollama_darwin() {
  local plist="$HOME/Library/LaunchAgents/$OLLAMA_LABEL.plist"
  if [ ! -f "$plist" ] && ollama_up; then
    warn "Ollama is already running (probably the Ollama app), so Homer uses it as it is."
    warn "Set its context length to 16k in the Ollama app settings, or quit the app and re-run this installer."
    return 0
  fi
  mkdir -p "$HOME/Library/LaunchAgents"
  render_ollama_plist >"$plist"
  launchctl bootout "gui/$(id -u)" "$plist" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
}

register_ollama_linux() {
  if ! command -v systemctl >/dev/null 2>&1; then
    warn "systemctl not found; start Ollama yourself with the documented environment"
    return 0
  fi
  sudo mkdir -p /etc/systemd/system/ollama.service.d
  render_ollama_dropin | sudo tee /etc/systemd/system/ollama.service.d/homer.conf >/dev/null
  sudo systemctl daemon-reload
  sudo systemctl enable --now ollama
  sudo systemctl restart ollama
}

if [ "$SKIP_OLLAMA" = "0" ]; then
  if command -v ollama >/dev/null 2>&1; then
    log "Found Ollama at $(command -v ollama)"
  else
    log "Installing Ollama $OLLAMA_VERSION"
    if [ "$OS" = "Darwin" ]; then
      install_ollama_darwin
    else
      curl -fsSL "$OLLAMA_INSTALLER" | OLLAMA_VERSION="$OLLAMA_VERSION" sh
    fi
  fi
  OLLAMA_BIN="$(command -v ollama || true)"
  [ -n "$OLLAMA_BIN" ] || die "ollama is not on PATH after installation"

  if [ "$NO_SERVICE" = "1" ]; then
    log "Not registering the Ollama service (--no-service)"
  elif [ "$OS" = "Darwin" ]; then
    register_ollama_darwin
  else
    register_ollama_linux
  fi

  attempts=0
  until ollama_up || [ "$attempts" -ge 30 ]; do
    attempts=$((attempts + 1))
    sleep 1
  done
  ollama_up || die "Ollama is not answering at $OLLAMA_URL; start it with: ollama serve"
  log "Ollama is answering at $OLLAMA_URL"
fi

TMP_WHEELS=""
cleanup() {
  if [ -n "$TMP_WHEELS" ]; then
    rm -rf "$TMP_WHEELS"
  fi
}
trap cleanup EXIT

wanted_release_file() {
  case "$1" in
    */*|.*) return 1 ;;
    *.whl|SHA256SUMS|requirements.lock) return 0 ;;
    *) return 1 ;;
  esac
}

download_release_with_token() {
  local api json
  if [ "$VERSION" = "latest" ]; then
    api="https://api.github.com/repos/$REPO/releases/latest"
  else
    api="https://api.github.com/repos/$REPO/releases/tags/$VERSION"
  fi
  json="$(curl -fsSL -H "Accept: application/vnd.github+json" -H "Authorization: Bearer $TOKEN" "$api")"
  printf '%s\n' "$json" | awk -F'"' '
    /"url": "https:\/\/api.github.com\/repos\/.*\/releases\/assets\/[0-9]+"/ { url = $4 }
    /"name": / && url != "" { print url, $4; url = "" }
  ' | while read -r url name; do
    wanted_release_file "$name" || continue
    curl -fsSL -H "Accept: application/octet-stream" -H "Authorization: Bearer $TOKEN" \
      -o "$WHEELS/$name" "$url"
  done
}

download_public_release() {
  local base name
  if [ "$VERSION" = "latest" ]; then base="$RELEASES/latest/download"; else base="$RELEASES/download/$VERSION"; fi
  curl -fsSL -o "$WHEELS/SHA256SUMS" "$base/SHA256SUMS" \
    || die "could not download release $VERSION from $RELEASES. While the repo is private, install gh and run gh auth login, or pass --token"
  for name in $(awk '{ sub(/^\*/, "", $2); print $2 }' "$WHEELS/SHA256SUMS"); do
    wanted_release_file "$name" || die "unexpected file in SHA256SUMS: $name"
    curl -fsSL -o "$WHEELS/$name" "$base/$name" || die "could not download $name"
  done
}

if [ -n "$WHEELS_DIR" ]; then
  WHEELS="$WHEELS_DIR"
  log "Using local wheels from $WHEELS"
else
  TMP_WHEELS="$(mktemp -d)"
  WHEELS="$TMP_WHEELS"
  if [ -n "$TOKEN" ]; then
    log "Downloading release $VERSION with a token"
    download_release_with_token
  elif command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    log "Downloading release $VERSION with gh"
    set -- -R "$REPO" -D "$WHEELS" -p '*.whl' -p SHA256SUMS -p requirements.lock
    if [ "$VERSION" = "latest" ]; then
      gh release download "$@"
    else
      gh release download "$VERSION" "$@"
    fi
  else
    log "Downloading release $VERSION"
    download_public_release
  fi
fi

ls "$WHEELS"/homer_core-*.whl >/dev/null 2>&1 || die "no homer_core wheel in $WHEELS"
if [ -f "$WHEELS/SHA256SUMS" ]; then
  verify_wheels "$WHEELS"
elif [ -n "$WHEELS_DIR" ]; then
  warn "no SHA256SUMS in $WHEELS; local wheels are installed unverified"
else
  die "release $VERSION has no SHA256SUMS; refusing to install unverified wheels"
fi

CONSTRAINTS=()
if [ -f "$WHEELS/requirements.lock" ]; then
  CONSTRAINTS=(-c "$WHEELS/requirements.lock")
elif [ -z "$WHEELS_DIR" ]; then
  die "release $VERSION has no requirements.lock"
else
  warn "no requirements.lock in $WHEELS; dependencies are not pinned"
fi

if [ ! -x "$VENV/bin/python" ]; then
  log "Creating the Python environment"
  uv venv --relocatable --python 3.12 "$VENV"
fi
log "Installing Homer"
uv pip install --python "$VENV/bin/python" \
  ${CONSTRAINTS[@]+"${CONSTRAINTS[@]}"} "$WHEELS"/*.whl
"$VENV/bin/homer" db upgrade

if [ "$SKIP_OLLAMA" = "0" ] && [ "$SKIP_MODELS" = "0" ]; then
  CHAT_TAG="$("$VENV/bin/python" -c 'from homer_core.llm import chat_model_tag; from homer_core.platform import hardware_tier; print(chat_model_tag(hardware_tier()))')"
  EMBED_TAG="$("$VENV/bin/python" -c 'from homer_core.llm import load_manifest; from homer_core.platform import hardware_tier; print(load_manifest()[hardware_tier()]["embed"])')"
  log "Pulling $CHAT_TAG and $EMBED_TAG"
  OLLAMA_HOST="$OLLAMA_URL" "$OLLAMA_BIN" pull "$CHAT_TAG"
  OLLAMA_HOST="$OLLAMA_URL" "$OLLAMA_BIN" pull "$EMBED_TAG"
fi

if [ "$OS" = "Darwin" ]; then
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
else
  UNIT_DIR="$HOME/.config/systemd/user"
  UNIT="$UNIT_DIR/homer.service"
fi

if [ "$NO_SERVICE" = "0" ]; then
  log "Registering the Homer service"
  if [ "$OS" = "Darwin" ]; then
    mkdir -p "$HOME/Library/LaunchAgents"
    render_server_plist >"$PLIST"
    launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  else
    mkdir -p "$UNIT_DIR"
    render_server_unit >"$UNIT"
    systemctl --user daemon-reload || warn "systemctl --user is unavailable"
    systemctl --user enable --now homer || warn "could not start the user service"
    loginctl enable-linger "$USER" >/dev/null 2>&1 || true
  fi
fi

"$VENV/bin/homer" doctor || warn "doctor reported a problem; see the table above"

if [ "$NO_SERVICE" = "0" ]; then
  attempts=0
  until curl -fsS "$DASHBOARD/api/health" >/dev/null 2>&1 || [ "$attempts" -ge 60 ]; do
    attempts=$((attempts + 1))
    sleep 1
  done
  if curl -fsS "$DASHBOARD/api/health" >/dev/null 2>&1; then
    START="Homer is running and starts again when you log in."
    [ "$OS" = "Darwin" ] && open "$DASHBOARD" >/dev/null 2>&1 || true
  else
    START="The service did not answer yet; read $HOMER_HOME/logs/homer.err.log."
  fi
else
  START="Start it with: $VENV/bin/homer serve"
fi

cat <<EOF

Homer is installed. $START

  Dashboard:  $DASHBOARD
  Data:       $HOMER_HOME
  Logs:       $VENV/bin/homer logs -f

Next:
  1. Open $DASHBOARD and sign in with your passphrase.
  2. Connect Google: follow GOOGLE_SETUP.md (published with the release), save the file as
       $HOMER_HOME/credentials/client_secret.json
     then press Connect in Settings, or run: $VENV/bin/homer setup google
  3. Check everything: $VENV/bin/homer doctor
  To remove Homer later: $VENV/bin/homer uninstall
EOF
