#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OV_HOME="${HOME}/.openviking"
mkdir -p "$OV_HOME"

sed   -e "s|__OPENVIKING_WORKSPACE__|$OV_HOME/data|g"   "$ROOT_DIR/templates/ov.conf.doubao.prefilled.local.json" > "$OV_HOME/ov.conf"

echo "Wrote $OV_HOME/ov.conf"
echo "Embedded key template source: templates/ov.conf.doubao.prefilled.local.json"
