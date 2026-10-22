"""Prepare the guided day: run the canonical scenarios through authenticated API requests; never print credentials."""

import argparse
import json
import os
from pathlib import Path
import sys
import uuid
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8080")
parser.add_argument("--branch", choices=["unknown", "family", "retained"], default="unknown")
args = parser.parse_args()
credentials = json.loads((Path(os.getenv("DATA_DIR", ".local")) / "access.json").read_text())
with httpx.Client(base_url=args.base_url, timeout=30) as client:
    response = client.post(
        "/api/auth/login", json={"username": "judge", "password": credentials["judge"]}
    )
    response.raise_for_status()

    def command(path, body=None):
        response = client.post("/api" + path, json=body or {}, headers={"Idempotency-Key": uuid.uuid4().hex})
        if response.is_error:
            print("Replay failed:", response.status_code, response.json().get("error", {}).get("code"))
            sys.exit(1)
        return response.json()

    command("/admin/reset")
    for i in range(1, 7):
        command(f"/admin/scenarios/{i}/run", {"branch": args.branch if i == 4 else "deposit"})
    for _ in range(15):
        result = command("/admin/studio/rep")
    state = result["state"]
    expected = {
        "drinks": "ACTIVE",
        "sister": "MISSED",
        "teacher": "VERIFIED",
        "squats": "VERIFIED",
        "parcel": "VERIFIED"
        if args.branch == "family"
        else ("ACTIVE" if args.branch == "retained" else "DISPUTED"),
    }
    actual = {c["key"]: c["status"] for c in state["contracts"]}
    if actual != expected:
        raise SystemExit("Golden-state mismatch. Run only one replay writer in the guided namespace at a time.")
    output = {
        "source": "SCRIPTED",
        "contracts": {c["key"]: c["status"] for c in state["contracts"]},
        "pose_cycles": state["studio"]["count"],
        "gate": state["studio"]["gate"],
        "official_dispatches": 0,
    }
    print(json.dumps(output, indent=2))
