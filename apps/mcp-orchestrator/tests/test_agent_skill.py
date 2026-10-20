"""The open-source Agent Skill ships the same compiler the product runs, plus a working auditor."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "packages" / "agent-skills" / "evidence-backed-commitments"


def test_skill_compiler_is_identical_to_product_compiler():
    product = (ROOT / "apps/mcp-orchestrator/done_irl/commitments.py").read_bytes()
    assert (SKILL / "scripts" / "commitments.py").read_bytes() == product


def test_skill_frontmatter_and_cli():
    head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
    assert "name: evidence-backed-commitments" in head and "description:" in head
    out = subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "compile_commitments.py"), "--now", "2026-10-20T08:15:00+05:30",
         "I'll call Mom tonight."],
        capture_output=True, text=True, check=True,
    ).stdout
    [c] = json.loads(out)
    assert c["title"] == "Call Mom" and c["due_local"] == "2026-10-20T21:00:00+05:30"


def test_check_contract_flags_unproven_verification(tmp_path):
    bad = {"contracts": [{"contract_id": "c1", "status": "VERIFIED", "verification_modality": "BEE_CONVERSATION_AUDIT",
                          "evidence_ids": ["e1"]}],
           "evidence": [{"evidence_id": "e1", "contract_id": "c1", "kind": "REMINDER_SENT"}]}
    good = {"contracts": [{"contract_id": "c1", "status": "VERIFIED", "verification_modality": "AUTHORIZED_MANUAL_CONFIRMATION",
                           "evidence_ids": ["e1"]}],
            "evidence": [{"evidence_id": "e1", "contract_id": "c1", "kind": "USER_CONFIRMATION",
                          "provenance": "USER_CONFIRMED"}]}
    script = str(SKILL / "scripts" / "check_contract.py")
    for doc, code in [(bad, 1), (good, 0)]:
        path = tmp_path / "c.json"
        path.write_text(json.dumps(doc))
        assert subprocess.run([sys.executable, script, str(path)], capture_output=True).returncode == code
