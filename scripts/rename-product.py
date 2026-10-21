"""One-off product rename DONE/IRL -> Muni across user-facing text (idempotent).

Internal identifiers (python package done_irl, env vars DONE_IRL_*, Android package dev.doneirl,
repo paths) are intentionally unchanged. Historical evidence records and the archived original
specification are not rewritten.
"""

import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
SKIP = {
    "docs/product-spec.md",
    "scripts/rename-product.py",
    "package-lock.json",
    "uv.lock",
    "apps/firetv-vega-hud/package-lock.json",
}
SKIP_PREFIX = ("docs/evidence/", "packages/testing-fixtures/")
SPECIAL = [
    ("DONE<span>/</span>IRL", "Muni"),
    ("DONE slash I R L proves what actually happened.", "Muni proves what actually happened."),
    ("DONE I R L. A P Is lie. Reality doesn't.", "Muni. Promises, kept. Proven by reality."),
    ("DONE I R L", "Muni"),
    ("<title>DONE/IRL · Reality ledger</title>", "<title>Muni · Promises, kept.</title>"),
    ('content="DONE/IRL: evidence-backed commitments, a durable reality ledger and transparent multi-device replay."',
     'content="Muni keeps your spoken promises and closes them only when real-world evidence proves them."'),
    ("DONE/IRL. APIs lie. Reality doesn't.", "Muni. APIs lie. Reality doesn't."),
    ("DONE/IRL HUD", "Muni"),
    ("DONE/IRL Command HUD", "Muni"),
]
GENERIC = re.compile(r"DONE ?/ ?IRL|DONE IRL")

files = subprocess.check_output(["git", "-C", str(root), "ls-files"], text=True).split()
changed = []
for rel in files:
    if rel in SKIP or rel.startswith(SKIP_PREFIX):
        continue
    path = root / rel
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".mp4", ".webm", ".ico", ".task", ".tflite", ".apk"}:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    new = text
    for a, b in SPECIAL:
        new = new.replace(a, b)
    new = GENERIC.sub("Muni", new)
    if new != text:
        path.write_text(new, encoding="utf-8", newline="\n")
        changed.append(rel)
print(f"{len(changed)} files renamed")
for rel in changed:
    print(" ", rel)
sys.exit(0)
