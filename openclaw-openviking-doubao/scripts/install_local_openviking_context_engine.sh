#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="$ROOT_DIR/plugin"
PROVIDER="openai"
REWRITE_CONFIG=0
SKIP_RESTART=0
INSTALL_OPENCLAW=0
OPENCLAW_VERSION="2026.4.14"
PORT=1933
AGENT_ID="default"
OV_HOME="${HOME}/.openviking"
OC_HOME="${HOME}/.openclaw"
OV_VERSION="0.3.8"

usage() {
  cat <<USAGE
Usage:
  bash scripts/install_local_openviking_context_engine.sh [options]

Options:
  --provider <openai|doubao|gemini-openai>  Select ov.conf template (default: openai)
  --rewrite-config                          Overwrite ~/.openviking/ov.conf with template
  --skip-restart                            Do not restart OpenClaw gateway at the end
  --install-openclaw                        Run: npm install -g openclaw@2026.4.14
  --openclaw-version <ver>                  Override pinned npm version (default: 2026.4.14)
  --port <number>                           OpenViking local port (default: 1933)
  --agent-id <value>                        Plugin agentId (default: default)
  -h, --help                                Show this help

Environment variables used by templates:
  OPENAI_API_KEY
  VOLCENGINE_API_KEY
  GEMINI_API_KEY
USAGE
}

log() { printf '[install] %s\n' "$*"; }
warn() { printf '[warn] %s\n' "$*" >&2; }
fail() { printf '[error] %s\n' "$*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing command: $1"
}

version_ge() {
  # returns 0 if $1 >= $2
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

while [ $# -gt 0 ]; do
  case "$1" in
    --provider)
      PROVIDER="${2:-}"; shift 2 ;;
    --rewrite-config)
      REWRITE_CONFIG=1; shift ;;
    --skip-restart)
      SKIP_RESTART=1; shift ;;
    --install-openclaw)
      INSTALL_OPENCLAW=1; shift ;;
    --openclaw-version)
      OPENCLAW_VERSION="${2:-}"; shift 2 ;;
    --port)
      PORT="${2:-}"; shift 2 ;;
    --agent-id)
      AGENT_ID="${2:-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      fail "Unknown argument: $1" ;;
  esac
done

case "$PROVIDER" in
  openai|doubao|gemini-openai) ;;
  *) fail "Unsupported provider: $PROVIDER" ;;
esac

require_cmd python3
require_cmd node
require_cmd npm

PY_VERSION="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
NODE_VERSION_RAW="$(node -v | sed 's/^v//')"
NODE_VERSION_MAJOR="$(printf '%s' "$NODE_VERSION_RAW" | cut -d. -f1)"

version_ge "$PY_VERSION" "3.10.0" || fail "Python >= 3.10 required, found $PY_VERSION"
[ "$NODE_VERSION_MAJOR" -ge 22 ] || fail "Node >= 22 required, found $NODE_VERSION_RAW"

if [ "$INSTALL_OPENCLAW" -eq 1 ]; then
  log "Installing OpenClaw npm package pinned to ${OPENCLAW_VERSION}..."
  npm install -g "openclaw@${OPENCLAW_VERSION}"
fi

require_cmd openclaw

OC_VERSION="$(openclaw --version 2>/dev/null || true)"
if [ -n "$OC_VERSION" ]; then
  log "OpenClaw version: $OC_VERSION"
fi

if ! command -v go >/dev/null 2>&1; then
  warn "Go not found. Upstream OpenViking docs list Go >= 1.22 as a prerequisite on systems that need local builds."
fi
if ! command -v gcc >/dev/null 2>&1 && ! command -v clang >/dev/null 2>&1; then
  warn "Neither gcc nor clang found. Upstream OpenViking docs list a C++ compiler as a prerequisite on systems that need local builds."
fi

mkdir -p "$OV_HOME" "$OC_HOME"

log "Creating/updating Python virtual environment at $OV_HOME/.venv"
python3 -m venv "$OV_HOME/.venv"
OV_PYTHON="$OV_HOME/.venv/bin/python"

"$OV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$OV_PYTHON" -m pip install --upgrade --force-reinstall "openviking==${OV_VERSION}"
if [ "$PROVIDER" = "gemini-openai" ]; then
  "$OV_PYTHON" -m pip install --upgrade 'google-genai>=1.0.0'
fi

cat > "$OC_HOME/openviking.env" <<ENVEOF
export OPENVIKING_PYTHON='$OV_PYTHON'
export OPENVIKING_CONFIG_FILE='$OV_HOME/ov.conf'
ENVEOF

cat > "$OC_HOME/openviking.env.ps1" <<ENVEOF
\$env:OPENVIKING_PYTHON = "$OV_PYTHON"
\$env:OPENVIKING_CONFIG_FILE = "$OV_HOME/ov.conf"
ENVEOF

TEMPLATE_PATH="$ROOT_DIR/templates/ov.conf.openai.example.json"
case "$PROVIDER" in
  openai) TEMPLATE_PATH="$ROOT_DIR/templates/ov.conf.openai.example.json" ;;
  doubao) TEMPLATE_PATH="$ROOT_DIR/templates/ov.conf.doubao.example.json" ;;
  gemini-openai) TEMPLATE_PATH="$ROOT_DIR/templates/ov.conf.gemini-embedding_openai-vlm.example.json" ;;
esac

if [ ! -f "$OV_HOME/ov.conf" ] || [ "$REWRITE_CONFIG" -eq 1 ]; then
  log "Writing $OV_HOME/ov.conf from template: $PROVIDER"
  sed \
    -e "s|__OPENVIKING_WORKSPACE__|$OV_HOME/data|g" \
    -e "s|__OPENAI_API_KEY__|${OPENAI_API_KEY:-__OPENAI_API_KEY__}|g" \
    -e "s|__VOLCENGINE_API_KEY__|${VOLCENGINE_API_KEY:-__VOLCENGINE_API_KEY__}|g" \
    -e "s|__GEMINI_API_KEY__|${GEMINI_API_KEY:-__GEMINI_API_KEY__}|g" \
    "$TEMPLATE_PATH" > "$OV_HOME/ov.conf"
else
  log "$OV_HOME/ov.conf already exists; keeping it"
fi

if [ ! -f "$OV_HOME/ovcli.conf" ]; then
  cp "$ROOT_DIR/templates/ovcli.conf.example.json" "$OV_HOME/ovcli.conf"
fi

if grep -q '__OPENAI_API_KEY__\|__VOLCENGINE_API_KEY__\|__GEMINI_API_KEY__' "$OV_HOME/ov.conf"; then
  warn "$OV_HOME/ov.conf still contains placeholder API keys. Edit it before expecting successful memory extraction/retrieval."
fi

log "Installing OpenViking plugin into OpenClaw from local path"
openclaw plugins install "$PLUGIN_DIR" --force
openclaw plugins enable openviking || true

log "Configuring OpenClaw to use openviking as the contextEngine slot"
openclaw config set plugins.slots.contextEngine openviking
openclaw config set plugins.entries.openviking.config.mode local
openclaw config set plugins.entries.openviking.config.configPath "$OV_HOME/ov.conf"
openclaw config set plugins.entries.openviking.config.port "$PORT"
openclaw config set plugins.entries.openviking.config.agentId "$AGENT_ID"
openclaw config set plugins.entries.openviking.config.autoCapture true
openclaw config set plugins.entries.openviking.config.autoRecall true
openclaw config set plugins.entries.openviking.config.emitStandardDiagnostics true
openclaw config set plugins.entries.openviking.config.logFindRequests false

if [ "$SKIP_RESTART" -eq 0 ]; then
  log "Restarting OpenClaw gateway"
  if ! openclaw gateway restart; then
    warn "OpenClaw gateway restart returned non-zero. If you have not onboarded OpenClaw yet, run: openclaw onboard --install-daemon"
  fi
fi

cat <<DONE

Install finished.

Next checks:
  openclaw config get plugins.slots.contextEngine
  openclaw config get plugins.entries.openviking.config
  openclaw plugins inspect openviking
  openclaw logs --follow

OpenViking runtime files:
  Python: $OV_PYTHON
  Config: $OV_HOME/ov.conf
  CLI config: $OV_HOME/ovcli.conf
  Env file: $OC_HOME/openviking.env

If logs show 'openviking: registered context-engine', the ContextEngine slot is mounted successfully.
DONE
