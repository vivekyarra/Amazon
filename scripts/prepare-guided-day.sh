#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --frozen python scripts/prepare-guided-day.py "$@"
