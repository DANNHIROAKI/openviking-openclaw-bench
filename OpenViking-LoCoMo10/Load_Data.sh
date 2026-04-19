#!/usr/bin/env bash
set -Eeuo pipefail

# Reproduce the 1540-case LoCoMo10 subset used by the OpenViking/OpenClaw experiment:
# - source: openclaw-eval's pinned locomo10.json
# - filter: remove all QA items with category == 5
# - output: a filtered conversation-level JSON + a flat JSONL of 1540 QA cases

REPO_COMMIT="75e07d696e0db5923ac767109f920df2fc807888"
DEFAULT_SOURCE_URL="https://raw.githubusercontent.com/ZaynJarvis/openclaw-eval/${REPO_COMMIT}/locomo10.json"
SOURCE_URL="${SOURCE_URL:-$DEFAULT_SOURCE_URL}"
OUT_DIR="${1:-./data/openviking-locomo10-1540}"

RAW_JSON_NAME="locomo10.openclaw-eval.${REPO_COMMIT}.json"
FILTERED_JSON_NAME="locomo10_openviking_1540.json"
FLAT_JSONL_NAME="locomo10_openviking_1540.jsonl"
MANIFEST_NAME="manifest.json"

mkdir -p "$OUT_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
  else
    echo "[ERROR] python3/python not found" >&2
    exit 1
  fi
fi

download() {
  local url="$1"
  local dest="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --retry-delay 2 "$url" -o "$dest"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$dest" "$url"
  else
    echo "[ERROR] curl or wget is required" >&2
    exit 1
  fi
}

RAW_JSON_PATH="$OUT_DIR/$RAW_JSON_NAME"
FILTERED_JSON_PATH="$OUT_DIR/$FILTERED_JSON_NAME"
FLAT_JSONL_PATH="$OUT_DIR/$FLAT_JSONL_NAME"
MANIFEST_PATH="$OUT_DIR/$MANIFEST_NAME"

printf '[1/3] Downloading source dataset...\n'
download "$SOURCE_URL" "$TMP_DIR/locomo10.json"
cp "$TMP_DIR/locomo10.json" "$RAW_JSON_PATH"

printf '[2/3] Filtering out category 5 QA items...\n'
"$PYTHON_BIN" - "$TMP_DIR/locomo10.json" "$FILTERED_JSON_PATH" "$FLAT_JSONL_PATH" "$MANIFEST_PATH" "$SOURCE_URL" "$REPO_COMMIT" <<'PY'
import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

src_path = Path(sys.argv[1])
filtered_json_path = Path(sys.argv[2])
flat_jsonl_path = Path(sys.argv[3])
manifest_path = Path(sys.argv[4])
source_url = sys.argv[5]
repo_commit = sys.argv[6]

expected_sample_ids = [
    "conv-26",
    "conv-30",
    "conv-41",
    "conv-42",
    "conv-43",
    "conv-44",
    "conv-47",
    "conv-48",
    "conv-49",
    "conv-50",
]
expected_total_before = 1986
expected_total_after = 1540
expected_before = {"1": 282, "2": 321, "3": 96, "4": 841, "5": 446}
expected_after = {"1": 282, "2": 321, "3": 96, "4": 841}

with src_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

if not isinstance(data, list):
    raise SystemExit("[ERROR] Source JSON is not a list of samples")

sample_ids = [item.get("sample_id") for item in data]
if sample_ids != expected_sample_ids:
    raise SystemExit(
        "[ERROR] Unexpected sample order or sample IDs.\n"
        f"expected={expected_sample_ids}\nactual={sample_ids}"
    )

before_counter = Counter()
after_counter = Counter()
flat_cases = []
filtered_samples = []
per_sample = []
case_id = 0

for sample_idx, item in enumerate(data):
    qas = item.get("qa", [])
    before_counter.update(str(q.get("category", "")) for q in qas)

    kept_qas = [q for q in qas if str(q.get("category", "")) != "5"]
    after_counter.update(str(q.get("category", "")) for q in kept_qas)

    new_item = copy.deepcopy(item)
    new_item["qa"] = kept_qas
    filtered_samples.append(new_item)

    sample_counter = Counter(str(q.get("category", "")) for q in kept_qas)
    per_sample.append(
        {
            "sample_id": item.get("sample_id"),
            "kept_cases": len(kept_qas),
            "category_breakdown": dict(sorted(sample_counter.items(), key=lambda kv: kv[0])),
        }
    )

    for local_idx, qa in enumerate(kept_qas, start=1):
        case_id += 1
        flat_cases.append(
            {
                "case_id": case_id,
                "sample_idx": sample_idx,
                "sample_id": item.get("sample_id"),
                "qa_idx_within_sample": local_idx,
                "category": qa.get("category"),
                "question": qa.get("question"),
                "answer": qa.get("answer"),
                "evidence": qa.get("evidence", []),
            }
        )

before_counter = dict(sorted(before_counter.items(), key=lambda kv: kv[0]))
after_counter = dict(sorted(after_counter.items(), key=lambda kv: kv[0]))

total_before = sum(before_counter.values())
total_after = sum(after_counter.values())

if total_before != expected_total_before or before_counter != expected_before:
    raise SystemExit(
        "[ERROR] Source dataset stats do not match the expected openclaw-eval LoCoMo10 snapshot.\n"
        f"expected_total_before={expected_total_before}, actual_total_before={total_before}\n"
        f"expected_before={expected_before}, actual_before={before_counter}"
    )

if total_after != expected_total_after or after_counter != expected_after:
    raise SystemExit(
        "[ERROR] Filtered dataset stats do not match the expected 1540-case subset.\n"
        f"expected_total_after={expected_total_after}, actual_total_after={total_after}\n"
        f"expected_after={expected_after}, actual_after={after_counter}"
    )

with filtered_json_path.open("w", encoding="utf-8") as f:
    json.dump(filtered_samples, f, ensure_ascii=False, indent=2)
    f.write("\n")

with flat_jsonl_path.open("w", encoding="utf-8") as f:
    for row in flat_cases:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

manifest = {
    "name": "openviking-locomo10-1540",
    "description": "LoCoMo10 subset used to reproduce the OpenViking/OpenClaw experiment: category 5 removed, 1540 QA cases retained.",
    "source": {
        "repo": "ZaynJarvis/openclaw-eval",
        "commit": repo_commit,
        "url": source_url,
    },
    "stats": {
        "sample_count": len(filtered_samples),
        "total_cases_before_filter": total_before,
        "total_cases_after_filter": total_after,
        "category_counts_before_filter": before_counter,
        "category_counts_after_filter": after_counter,
        "per_sample": per_sample,
    },
    "files": {
        "filtered_json": {
            "path": str(filtered_json_path),
            "sha256": sha256_of(filtered_json_path),
        },
        "flat_jsonl": {
            "path": str(flat_jsonl_path),
            "sha256": sha256_of(flat_jsonl_path),
        },
    },
}

with manifest_path.open("w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(f"sample_count={len(filtered_samples)}")
print(f"total_before={total_before}")
print(f"total_after={total_after}")
print(f"category_before={before_counter}")
print(f"category_after={after_counter}")
for item in per_sample:
    print(f"{item['sample_id']}: {item['kept_cases']}")
print(f"filtered_json_sha256={manifest['files']['filtered_json']['sha256']}")
print(f"flat_jsonl_sha256={manifest['files']['flat_jsonl']['sha256']}")
PY

printf '[3/3] Done.\n\n'
printf 'Generated files:\n'
printf '  - %s\n' "$RAW_JSON_PATH"
printf '  - %s\n' "$FILTERED_JSON_PATH"
printf '  - %s\n' "$FLAT_JSONL_PATH"
printf '  - %s\n\n' "$MANIFEST_PATH"
printf 'Use this file with openclaw-eval:\n'
printf '  uv run python eval.py ingest %q --sample 0 --sessions 1-4\n' "$FILTERED_JSON_PATH"
printf '  uv run python eval.py qa %q --sample 0 --user <UUID> --output qa_results.txt\n' "$FILTERED_JSON_PATH"