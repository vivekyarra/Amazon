"""Explicit disaster recovery into an empty local household; never overwrites active state."""

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/mcp-orchestrator"))
from done_irl.aws_runtime import AWSRuntime  # noqa: E402
from done_irl.store import Store  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--household", required=True)
args = parser.parse_args()
key_file = os.environ.get("LEDGER_KEY_FILE")
if not key_file or not Path(key_file).is_file():
    raise SystemExit("Provision the exact original ledger key before recovery.")
if not args.household.startswith("house_"):
    raise SystemExit("Specify an owner household ID.")
store = Store(str(Path(os.environ.get("DATA_DIR", ".local")) / "ledger.db"), key_file=key_file)
cloud = AWSRuntime(store)
state = cloud.restore(args.household)
print(
    f"Restored {len(state['contracts'])} contracts; media and snapshot hashes verified. Start only one reducer."
)
