#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="$ROOT_DIR/plugin"
BASE_URL="${1:-http://127.0.0.1:1933}"
API_KEY="${2:-}"
AGENT_ID="${3:-default}"

log() { printf '[install-remote] %s\n' "$*"; }
warn() { printf '[warn] %s\n' "$*" >&2; }
fail() { printf '[error] %s\n' "$*" >&2; exit 1; }

command -v openclaw >/dev/null 2>&1 || fail "Missing command: openclaw"

log "Installing OpenViking plugin from local path"
openclaw plugins install "$PLUGIN_DIR" --force
openclaw plugins enable openviking || true

log "Configuring remote OpenViking endpoint"
openclaw config set plugins.slots.contextEngine openviking
openclaw config set plugins.entries.openviking.config.mode remote
openclaw config set plugins.entries.openviking.config.baseUrl "$BASE_URL"
openclaw config set plugins.entries.openviking.config.agentId "$AGENT_ID"
openclaw config set plugins.entries.openviking.config.autoCapture true
openclaw config set plugins.entries.openviking.config.autoRecall true
openclaw config set plugins.entries.openviking.config.emitStandardDiagnostics true
openclaw config set plugins.entries.openviking.config.logFindRequests false

if [ -n "$API_KEY" ]; then
  openclaw config set plugins.entries.openviking.config.apiKey "$API_KEY"
fi

if ! openclaw gateway restart; then
  warn "OpenClaw gateway restart returned non-zero. If needed, run: openclaw onboard --install-daemon"
fi

cat <<DONE

Remote-mode install finished.

Check:
  openclaw config get plugins.slots.contextEngine
  openclaw config get plugins.entries.openviking.config
  openclaw logs --follow

DONE
