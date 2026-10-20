#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
export npm_config_cache="${npm_config_cache:-/workspace/.cache/npm}"
command -v uv >/dev/null || { echo 'Install uv from https://docs.astral.sh/uv/ first.' >&2; exit 1; }
node -e 'if(Number(process.versions.node.split(".")[0])<22) process.exit(1)'
uv sync --frozen
npm ci --no-audit --no-fund
npm run build
