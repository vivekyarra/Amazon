"""Amazon Bedrock (Nova) fallback: proposes contracts the rules miss, never verifies, never blocks."""

import json

import pytest

from done_irl import engine as e
from done_irl import nova
from done_irl.models import BeeInput

NOW = "2026-10-22T04:30:00+00:00"  # 10:00 IST, Thursday


def house():
    s = e.fresh()
    s.update(household_id="h", clock_mode="WALL", now=NOW)
    return s


def reply(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return lambda **kw: {"output": {"message": {"content": [{"text": text}]}}}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("MUNI_NOVA", "1")
    nova._calls.clear()

    def use(payload):
        monkeypatch.setattr(nova, "interpret", lambda t, n, converse=None: ORIGINAL(t, n, converse=reply(payload)))

    return use


ORIGINAL = nova.interpret


def say(s, text, speaker="SELF"):
    out = e.compile_bee(s, BeeInput(event_id=f"n{len(s['events'])}", utterance=text, speaker=speaker, occurred_at=NOW))
    return [c for c in s["contracts"] if c["contract_id"] in out]


def test_nova_reads_an_intention_the_rules_miss(on):
    on({"is_commitment": True, "title": "service the car", "due_local": "2026-10-24T18:00",
        "recurrence": None, "confidence": 0.9})  # fmt: skip
    s = house()
    [c] = say(s, "Ugh, the car needs servicing this weekend, I'm on it.")
    assert c["title"] == "Service the car" and c["status"] == "ACTIVE"
    assert c["commitment_origin"] == "BEDROCK_NOVA" and c["interpreted_by"]["confidence"] == 0.9
    assert c["verification_modality"] == "AUTHORIZED_MANUAL_CONFIRMATION"  # Nova proposes; it never proves
    assert any(ev["event_type"] == "commitment.ai_interpreted" for ev in s["events"])


def test_low_confidence_or_family_readings_wait_for_the_owner(on):
    on({"is_commitment": True, "title": "Get flowers", "due_local": None, "recurrence": None, "confidence": 0.6})
    s = house()
    [c] = say(s, "I'm thinking flowers for mom this weekend maybe.")
    assert c["status"] == "NEEDS_CONFIRMATION"


def test_rules_stay_first_and_small_talk_never_reaches_the_model(on, monkeypatch):
    calls = []
    monkeypatch.setattr(nova, "interpret", lambda *a, **k: calls.append(a))
    s = house()
    assert say(s, "I'll call Amma at 7 tonight.")[0]["commitment_origin"] == "GENERAL_PARSER"
    assert say(s, "This coffee is really good.") == []
    assert say(s, "I already paid the rent.") == []
    assert calls == []


@pytest.mark.parametrize("payload", ["not json", {"is_commitment": False}, {"is_commitment": True, "title": ""},
                                     {"is_commitment": True, "title": "x", "confidence": 7}])  # fmt: skip
def test_invalid_or_negative_model_output_creates_nothing(on, payload):
    on(payload)
    assert say(house(), "Gonna sort out the garage this weekend, for real.") == []


def test_disabled_by_default_and_capped_per_hour(monkeypatch):
    monkeypatch.delenv("MUNI_NOVA", raising=False)
    assert say(house(), "Gonna sort out the garage this weekend, for real.") == []
    monkeypatch.setenv("MUNI_NOVA", "1")
    monkeypatch.setenv("NOVA_MAX_PER_HOUR", "1")
    nova._calls.clear()
    ok = reply({"is_commitment": True, "title": "Sort the garage", "due_local": None, "recurrence": None,
                "confidence": 0.9})  # fmt: skip
    from datetime import datetime

    now = datetime.fromisoformat(NOW)
    assert nova.interpret("a b c", now, converse=ok) is not None
    assert nova.interpret("a b c", now, converse=ok) is None


def test_model_failure_never_blocks_the_ledger(on, monkeypatch):
    def boom(**kw):
        raise TimeoutError

    monkeypatch.setattr(nova, "interpret", lambda t, n, converse=None: ORIGINAL(t, n, converse=boom))
    s = house()
    assert say(s, "Gonna sort out the garage this weekend, for real.") == []
    assert any(ev["event_type"] == "commitment.ai_reviewed" for ev in s["events"])
