#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts/release
# Browser runs generate screenshots; do not copy credentials, databases or private media.
npm run test:e2e
UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}" uv run --frozen python - <<'PY'
import hashlib,json
from pathlib import Path
files=[p for p in Path('artifacts/screenshots').glob('*.png') if p.is_file()]
Path('artifacts/release/screenshot-manifest.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
print(f'Captured {len(files)} screenshots. These are web preview evidence, not device-runtime proof.')
PY
