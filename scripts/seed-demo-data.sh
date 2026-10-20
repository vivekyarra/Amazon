#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}" uv run --frozen python scripts/seed-demo-data.py "$@"
