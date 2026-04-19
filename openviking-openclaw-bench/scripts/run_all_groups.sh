#!/usr/bin/env bash
set -euo pipefail
CONFIG="${1:-bench_config.json}"
ovbench run-all --config "$CONFIG" --groups g1 g2 g3 g4 --run-label full --judge
ovbench report --config "$CONFIG" --groups g1 g2 g3 g4 --run-label full \
  --output-md "${HOME}/ov-bench/final_report.md" \
  --output-json "${HOME}/ov-bench/final_report.json"
