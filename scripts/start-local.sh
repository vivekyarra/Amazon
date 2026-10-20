#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
export PYTHONPATH="$PWD/apps/mcp-orchestrator${PYTHONPATH:+:$PYTHONPATH}"
exec uv run --frozen uvicorn done_irl.api:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}"
