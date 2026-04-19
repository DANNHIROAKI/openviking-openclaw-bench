#!/usr/bin/env bash
set -euo pipefail
CONFIG="${1:-bench_config.json}"
for GROUP in g1 g2 g3 g4; do
  ovbench setup-group --config "$CONFIG" --group "$GROUP" --reset
  ovbench verify-group --config "$CONFIG" --group "$GROUP"
done
