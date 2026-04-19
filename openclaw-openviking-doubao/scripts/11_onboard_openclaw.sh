#!/usr/bin/env bash
set -euo pipefail

command -v openclaw >/dev/null 2>&1 || { echo "openclaw not found. Run scripts/10_install_openclaw_stable.sh first."; exit 1; }

exec openclaw onboard --install-daemon
