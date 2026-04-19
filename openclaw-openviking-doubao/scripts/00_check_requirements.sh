#!/usr/bin/env bash
set -euo pipefail

show() {
  printf '\n== %s ==\n' "$1"
  shift
  "$@" || true
}

printf 'OpenClaw + OpenViking (Doubao + Local Mode) preflight\n'
show "python3 --version" python3 --version
show "node -v" node -v
show "npm -v" npm -v
show "openclaw --version" openclaw --version

cat <<INFO

Expected baseline:
- Python >= 3.10
- Node >= 22.16 (Node 24 recommended by OpenClaw)
- OpenClaw CLI installed
- Later tutorial pins npm install to openclaw@2026.4.14

If "openclaw --version" failed, run:
  bash scripts/10_install_openclaw_stable.sh
INFO
