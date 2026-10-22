"""One-click judge access: every guest gets a private, isolated copy of the demo day."""

import time
import uuid

from fastapi.testclient import TestClient


def key():
    return {"Idempotency-Key": uuid.uuid4().hex}


def guest(app):
    c = TestClient(app)
    r = c.post("/api/auth/guest")
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"
    return c


def test_guest_gets_isolated_demo_household_with_replay_controls(app):
    with TestClient(app):
        a, b = guest(app), guest(app)
        assert a.post("/api/admin/scenarios/1/run", json={"branch": "deposit"}, headers=key()).status_code == 200
        sa, sb = a.get("/api/state").json()["state"], b.get("/api/state").json()["state"]
        assert sa["household_id"].startswith("demo_") and sb["household_id"].startswith("demo_")
        assert sa["household_id"] != sb["household_id"]
        assert len(sa["contracts"]) > 0 and len(sb["contracts"]) == 0
        assert sa.get("clock_mode") != "WALL"  # guests replay the scripted demo clock, never AWS schedules


def test_guest_cannot_reach_owner_or_shared_demo_household(app):
    with TestClient(app) as owner:
        owner.post("/api/auth/login", json={"username": "owner", "password": "test-owner-password"})
        owner.post("/api/owner/promises", json={"utterance": "I'll pay the electricity bill by Friday"}, headers=key())
        owned = owner.get("/api/state").json()["state"]
        s = guest(app).get("/api/state").json()["state"]
        assert s["household_id"] not in {owned["household_id"], "demo"}
        assert not any("electricity" in x["title"].lower() for x in s["contracts"])


def test_guest_rate_limited_per_network(app, monkeypatch):
    monkeypatch.setenv("DEMO_GUEST_PER_HOUR", "2")
    with TestClient(app) as c:
        assert c.post("/api/auth/guest").status_code == 200
        assert c.post("/api/auth/guest").status_code == 200
        r = c.post("/api/auth/guest")
        assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"


def test_guest_disabled_outside_demo_or_by_flag(app, monkeypatch):
    monkeypatch.setenv("DEMO_GUEST", "0")
    with TestClient(app) as c:
        assert c.post("/api/auth/guest").status_code == 404


def test_expired_guest_households_are_erased(app):
    with TestClient(app) as other:
        hid = guest(app).get("/api/state").json()["state"]["household_id"]
        store = app.state.store
        with store.transaction() as db:
            db.execute("UPDATE sessions SET expires=? WHERE household=?", (time.time() - 1, hid))
        assert other.post("/api/auth/guest").status_code == 200
    assert store.db.execute("SELECT 1 FROM households WHERE id=?", (hid,)).fetchone() is None
    assert store.db.execute("SELECT 1 FROM sessions WHERE household=?", (hid,)).fetchone() is None
