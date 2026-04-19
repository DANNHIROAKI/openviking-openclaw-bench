#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${VOLCENGINE_API_KEY:-}" ]; then
  export VOLCENGINE_API_KEY="1ed34ba3-ccfb-4326-8587-ca0c0d304301"
fi

echo "[install] Using Doubao Local Mode template"
echo "[install] If you want to override the embedded experimental key, export VOLCENGINE_API_KEY first."

exec bash "$SCRIPT_DIR/install_local_openviking_context_engine.sh" --provider doubao --rewrite-config "$@"
