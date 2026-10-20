#!/usr/bin/env bash
# Prints the generated local passwords. Run only in your own private terminal.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --frozen python -c "
import json, os
from pathlib import Path
p = Path(os.getenv('DATA_DIR', '.local')) / 'access.json'
if not p.exists():
    raise SystemExit('Start the server once to generate private workspace access.')
for name, password in json.loads(p.read_text()).items():
    print(f'{name}: {password}')
"
