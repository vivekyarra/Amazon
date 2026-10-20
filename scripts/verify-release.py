"""Fail closed on incomplete original-vision requirements; never equate CI with product completion."""

import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "docs/acceptance-manifest.json").read_text(encoding="utf-8"))
requirements = manifest["requirements"]
expected = {f"P0-{i:03}" for i in range(1, 56)}
errors = []
if {r["requirement_id"] for r in requirements} != expected or len(requirements) != 55:
    errors.append("All 55 unique original requirements must be retained.")
for r in requirements:
    if r["verification_result"] != "VERIFIED":
        errors.append(r["requirement_id"] + ": " + r["verification_result"])
    elif not r["automated_tests"] or not r["evidence"] or not (root / r["evidence"]).is_file():
        errors.append(r["requirement_id"] + ": passing evidence missing")
    for path in r["code_paths"]:
        if not (root / path).is_file():
            errors.append(r["requirement_id"] + ": source missing: " + path)
checks = {}
for name, path in [
    ("backend", "artifacts/backend-results.xml"),
    ("browser", "artifacts/playwright/results.xml"),
]:
    file = root / path
    if not file.exists():
        checks[name] = "NOT_RUN"
        errors.append(name + ": result file missing")
        continue
    tree = ET.parse(file)
    suites = [tree.getroot()] if tree.getroot().tag == "testsuite" else list(tree.getroot().iter("testsuite"))
    tests = sum(int(s.get("tests", "0")) for s in suites)
    failed = sum(int(s.get("failures", "0")) + int(s.get("errors", "0")) for s in suites)
    checks[name] = {"tests": tests, "failures": failed}
    if not tests or failed:
        errors.append(name + ": no tests or failing tests")
for key in ["primary_track_runtime_verified", "independent_release_review_passed"]:
    if not manifest[key]:
        errors.append(key + ": false")
if manifest["target"] == "FULL_ORIGINAL_VISION_COMPLETE" and not manifest["all_original_live_verified"]:
    errors.append("Original live capabilities are not verified.")
report = {
    "target": manifest["target"],
    "verdict": "NOT_COMPLETE" if errors else "GOAL_ACHIEVED",
    "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "p0_verified": sum(r["verification_result"] == "VERIFIED" for r in requirements),
    "p0_total": 55,
    "checks": checks,
    "remaining_gates": errors,
}
(root / "artifacts/release").mkdir(parents=True, exist_ok=True)
(root / "artifacts/release/release-result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
sys.exit(1 if errors else 0)
