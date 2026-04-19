#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${VOLCENGINE_API_KEY:-}" ]; then
  echo "VOLCENGINE_API_KEY is empty."
  echo "Set it first, then rerun this script."
  exit 1
fi

exec bash "$SCRIPT_DIR/install_local_openviking_context_engine.sh" --provider doubao --rewrite-config "$@"
