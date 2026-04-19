#!/usr/bin/env bash
set -euo pipefail
CONFIG="${1:-bench_config.json}"
for GROUP in g1 g2 g3 g4; do
  ovbench smoke-continuity --config "$CONFIG" --group "$GROUP"
  ovbench smoke-sample --config "$CONFIG" --group "$GROUP" --sample 0 --sessions 1-2 --qa-count 5 --judge
done
