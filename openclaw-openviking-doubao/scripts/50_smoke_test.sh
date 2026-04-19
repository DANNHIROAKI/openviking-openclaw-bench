#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
Smoke test checklist:

1) Make sure the slot is active:
   openclaw config get plugins.slots.contextEngine

2) Watch logs in one terminal:
   openclaw logs --follow

3) Watch OpenViking log in another terminal:
   tail -f ~/.openviking/data/log/openviking.log

4) Send a message through OpenClaw:
   openclaw agent --message "记住：我最喜欢的编辑器是 Neovim。" --thinking low

5) Ask again:
   openclaw agent --message "我最喜欢的编辑器是什么？" --thinking low

Expected:
- The first turn should write session content
- The second turn should show recall or at least retrieval attempts in logs
EOF
