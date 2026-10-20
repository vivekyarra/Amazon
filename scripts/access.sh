#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# Run only in your own private terminal. Never attach output to a public issue or CI log.
python3 - <<'PY'
import json, os
from pathlib import Path
p=Path(os.getenv('DATA_DIR','.local'))/'access.json'
if not p.exists():
    raise SystemExit('Start the server once to generate private workspace access.')
for username,password in json.loads(p.read_text()).items():
    print(f'{username}: {password}')
PY
