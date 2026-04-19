#!/usr/bin/env bash
set -euo pipefail
CONFIG="${1:-bench_config.json}"
ovbench install-tools --config "$CONFIG"
