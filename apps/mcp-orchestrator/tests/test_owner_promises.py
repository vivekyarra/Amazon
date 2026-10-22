"""Owner "Add a promise" route: owner-scoped, idempotent, labelled exactly like the MCP compile tool."""

import uuid

import pytest


def login(c, username, password):
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["role"]


@pytest.fixture
def owner(client):
    # One TestClient per app (the MCP session manager runs once); switch the session cookie instead.
    assert login(client, "owner", "test-owner-password") == "owner"
    return client


def add(c, text, key=None, status=200):
    r = c.post("/api/owner/promises", json={"utterance": text}, headers={"Idempotency-Key": key or uuid.uuid4().hex})
    assert r.status_code == status, r.text
    return r.json()


def consent(c):
    r = c.post("/api/consent", json={"enabled": True}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 200, r.text


def test_owner_promise_compiles_with_owner_input_label_and_is_idempotent(owner):
    consent(owner)
    first = add(owner, "I will pay the electricity bill by 6 pm.", key="add-1")
    [cid] = first["result"]["contract_ids"]
    assert first["result"]["source"] == "MCP_OWNER_INPUT"
    s = first["state"]
    c = next(c for c in s["contracts"] if c["contract_id"] == cid)
    assert c["title"] == "Pay the electricity bill" and c["status"] in {"ACTIVE", "NEEDS_CONFIRMATION"}
    created = [v for v in s["events"] if v["event_type"] == "bee.utterance.received"]
    assert created[-1]["source"] == "MCP_OWNER_INPUT"
    assert created[-1]["source_mode"] == first["result"]["source_mode"]
    # A retried request with the same key replays the stored response; no duplicate contract.
    again = add(owner, "I will pay the electricity bill by 6 pm.", key="add-1")
    assert again["result"] == first["result"]
    s = owner.get("/api/state").json()["state"]
    assert sum(1 for c in s["contracts"] if c["title"] == "Pay the electricity bill") == 1
    # Owner can then close it only with an explicit, labelled confirmation.
    r = owner.post(
        f"/api/contracts/{cid}/confirm",
        json={"action": "confirm-done"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"]["evidence"][-1]["provenance"] == "USER_CONFIRMED"


def test_owner_promise_requires_consent_session_and_key(owner):
    add(owner, "I will call Mom tonight.", status=409)  # live household starts with collection paused
    consent(owner)
    r = owner.post("/api/owner/promises", json={"utterance": "I will call Mom tonight."})
    assert r.status_code == 400
    add(owner, "", status=422)
    owner.cookies.clear()
    r = owner.post("/api/owner/promises", json={"utterance": "I will call Mom."}, headers={"Idempotency-Key": "x"})
    assert r.status_code == 401


def test_owner_promise_stays_in_the_owner_household(owner):
    consent(owner)
    add(owner, "I will water the plants at 7 pm.")
    assert login(owner, "judge", "test-admin-password") == "admin"
    guided = owner.get("/api/state").json()["state"]
    assert not any(c["title"] == "Water the plants" for c in guided["contracts"])
