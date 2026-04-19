#!/usr/bin/env bash
set -euo pipefail

TARGET="${HOME}/.openviking/data"
if [ -d "$TARGET" ]; then
  echo "Removing $TARGET"
  rm -rf "$TARGET"
else
  echo "$TARGET does not exist"
fi

echo "OpenViking data reset complete."
echo "Your config file ~/.openviking/ov.conf was left untouched."
