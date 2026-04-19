#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_VERSION="${OPENCLAW_VERSION:-2026.4.14}"

command -v npm >/dev/null 2>&1 || { echo "npm not found"; exit 1; }

echo "[install] Installing OpenClaw npm stable pinned to $OPENCLAW_VERSION"
npm install -g "openclaw@${OPENCLAW_VERSION}"

echo
echo "Next step:"
echo "  openclaw onboard --install-daemon"
echo
echo "That command is interactive. It installs the Gateway daemon and completes OpenClaw onboarding."
