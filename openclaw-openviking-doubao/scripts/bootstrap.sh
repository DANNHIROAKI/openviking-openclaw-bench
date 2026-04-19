#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_PREFIX="${OPENCLAW_PREFIX:-$HOME/.openclaw}"
OPENVIKING_HOME="${OPENVIKING_HOME:-$HOME/.openviking}"

VOLCANO_ENGINE_API_KEY="${VOLCANO_ENGINE_API_KEY:-}"
if [[ -z "$VOLCANO_ENGINE_API_KEY" ]]; then
  echo "ERROR: 请先 export VOLCANO_ENGINE_API_KEY=你的豆包API Key" >&2
  exit 1
fi

if [[ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]]; then
  OPENCLAW_GATEWAY_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
fi

mkdir -p "$HOME/.openclaw" "$OPENVIKING_HOME"

# 让 daemon 也能读到 provider key / gateway token
cat > "$HOME/.openclaw/.env" <<EOF
VOLCANO_ENGINE_API_KEY=${VOLCANO_ENGINE_API_KEY}
OPENCLAW_GATEWAY_TOKEN=${OPENCLAW_GATEWAY_TOKEN}
EOF

# 1) 安装 OpenClaw（本地前缀，避免系统 Node / nvm 混乱）
curl -fsSL --proto '=https' --tlsv1.2 https://openclaw.ai/install-cli.sh | \
  bash -s -- --prefix "$OPENCLAW_PREFIX" --version 2026.4.14

export PATH="$OPENCLAW_PREFIX/bin:$PATH"
export VOLCANO_ENGINE_API_KEY
export OPENCLAW_GATEWAY_TOKEN

# 2) 非交互 onboarding：本地 gateway + Volcengine + env-backed secret refs
openclaw onboard --non-interactive \
  --mode local \
  --install-daemon \
  --auth-choice volcengine-api-key \
  --secret-input-mode ref \
  --gateway-auth token \
  --gateway-token-ref-env OPENCLAW_GATEWAY_TOKEN \
  --accept-risk

# 3) 安装 OpenViking runtime
python3 -m venv "$OPENVIKING_HOME/.venv"
"$OPENVIKING_HOME/.venv/bin/pip" install -U pip setuptools wheel
"$OPENVIKING_HOME/.venv/bin/pip" install "openviking==0.3.8"

# 4) 生成 Local Mode 的 ov.conf
cat > "$OPENVIKING_HOME/ov.conf" <<EOF
{
  "storage": {
    "workspace": "$OPENVIKING_HOME"
  },
  "embedding": {
    "dense": {
      "api_base": "https://ark.cn-beijing.volces.com/api/v3",
      "api_key": "$VOLCANO_ENGINE_API_KEY",
      "provider": "volcengine",
      "dimension": 1024,
      "model": "doubao-embedding-vision-251215",
      "input": "multimodal"
    }
  },
  "vlm": {
    "api_base": "https://ark.cn-beijing.volces.com/api/v3",
    "api_key": "$VOLCANO_ENGINE_API_KEY",
    "provider": "volcengine",
    "max_retries": 2,
    "model": "doubao-seed-2-0-pro-260215"
  }
}
EOF

# 5) 给 OpenViking Local Mode runtime 明确 Python / config 路径
cat > "$HOME/.openclaw/openviking.env" <<EOF
export OPENVIKING_PYTHON="$OPENVIKING_HOME/.venv/bin/python"
export OPENVIKING_CONFIG_FILE="$OPENVIKING_HOME/ov.conf"
EOF

# 6) 安装你仓库里 vendored 的插件快照
openclaw plugins install "$ROOT/plugin" --force --dangerously-force-unsafe-install
openclaw plugins enable openviking || true

# 7) 切 slot + 写 plugin config
openclaw config set plugins.slots.contextEngine openviking
openclaw config set plugins.entries.openviking.config.mode local
openclaw config set plugins.entries.openviking.config.configPath "$OPENVIKING_HOME/ov.conf"
openclaw config set plugins.entries.openviking.config.port 1933
openclaw config set plugins.entries.openviking.config.agentId default
openclaw config set plugins.entries.openviking.config.autoCapture true
openclaw config set plugins.entries.openviking.config.autoRecall true
openclaw config set plugins.entries.openviking.config.emitStandardDiagnostics true
openclaw config set plugins.entries.openviking.config.logFindRequests true

# 8) 重启并验证
source "$HOME/.openclaw/openviking.env"
openclaw gateway restart

echo
echo "== verify =="
openclaw config get plugins.slots.contextEngine
openclaw plugins inspect openviking
echo
echo "Dashboard:"
openclaw dashboard --no-open