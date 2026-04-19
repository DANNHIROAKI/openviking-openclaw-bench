#!/usr/bin/env bash
set -euo pipefail

show() {
  printf '\n== %s ==\n' "$1"
  shift
  "$@" || true
}

show "openclaw --version" openclaw --version
show "node -v" node -v
show "python3 --version" python3 --version
show "plugins.slots.contextEngine" openclaw config get plugins.slots.contextEngine
show "plugins.entries.openviking.config" openclaw config get plugins.entries.openviking.config
show "plugin inspect" openclaw plugins inspect openviking

printf '\nIf the slot is openviking and logs contain "openviking: registered context-engine", installation is good.\n'
