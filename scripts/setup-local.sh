#!/usr/bin/env bash
# One-time setup: Python deps (with MediaPipe/WebRTC extras), pinned models, and the built console.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo 'Install uv from https://docs.astral.sh/uv/ first.' >&2; exit 1; }
node -e 'if(Number(process.versions.node.split(".")[0])<22) process.exit(1)' || { echo 'Node.js 22.12+ required.' >&2; exit 1; }
uv sync --frozen --extra ring-video --extra aws
uv run --frozen --extra ring-video --extra aws python scripts/fetch-pose-model.py
npm ci --no-audit --no-fund
npm run build
echo "Setup complete. Start with ./scripts/start-local.sh"
