#!/usr/bin/env bash
# Starts the API, MCP endpoint and built console on http://127.0.0.1:8080 (override with HOST/PORT).
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run --frozen --extra ring-video --extra aws uvicorn --app-dir apps/mcp-orchestrator done_irl.api:app \
  --host "${HOST:-127.0.0.1}" --port "${PORT:-8080}"
