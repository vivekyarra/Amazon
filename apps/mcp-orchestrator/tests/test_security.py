import time
import pytest
from fastapi.testclient import TestClient
from done_irl import engine as e


def stage(post, n, branch="deposit"):
    return post(f"/admin/scenarios/{n}/run", {"branch": branch})["state"]


def test_F22_household_isolation(app, client, post):
    stage(post, 2)
    s = stage(post, 4, "unknown")
    eid = s["evidence"][0]["evidence_id"]
    client.post("/api/auth/login", json={"username": "other", "password": "test-other-password"})
    assert client.get("/api/incidents/inc_parcel").status_code == 404
    assert client.get("/api/evidence/" + eid).status_code == 404
    assert client.get("/api/contracts/psc_parcel").status_code == 404
    assert not client.get("/api/state").json()["state"]["contracts"]
    post("/admin/scenarios/1/run", status=403)


def test_F23_official_dispatch_boolean_and_unauthorized(post):
    stage(post, 2)
    stage(post, 4, "unknown")
    post("/incidents/inc_parcel/dispatch-report", {"action": "dispatch-report"}, status=403)
    post(
        "/incidents/inc_parcel/dispatch-report",
        {"action": "dispatch-report", "human_confirmed_boolean": True},
        status=422,
    )


def test_no_anonymous_reads_writes_mcp(app):
    with TestClient(app) as c:
        assert c.get("/api/state").status_code == 401
        assert c.get("/api/contracts").status_code == 401
        assert c.post("/api/admin/reset", json={}).status_code == 401
        assert c.post("/mcp/", json={}).status_code == 401


def test_idempotency_exact_response_and_conflict(post):
    first = post("/admin/scenarios/1/run", {"branch": "deposit"}, key="same-command")
    again = post("/admin/scenarios/1/run", {"branch": "deposit"}, key="same-command")
    assert first == again
    post("/admin/scenarios/2/run", {"branch": "deposit"}, key="same-command", status=409)


def test_missing_idempotency_key(client):
    assert client.post("/api/admin/reset", json={}).status_code == 400


def test_invalid_origin_blocked(client):
    assert (
        client.post(
            "/api/admin/reset",
            json={},
            headers={"Origin": "https://attacker.example", "Idempotency-Key": "x"},
        ).status_code
        == 403
    )


def test_forged_webhook_no_state_change(client, post, monkeypatch):
    monkeypatch.setenv("RING_HMAC_KEY", "test-webhook-secret")
    stage(post, 1)
    before = client.get("/api/state").json()["state"]
    r = client.post(
        "/api/webhooks/ring",
        json={"event": "remove"},
        headers={"x-ring-signature": "forged", "x-ring-timestamp": str(int(time.time()))},
    )
    assert r.status_code == 401
    assert client.get("/api/state").json()["state"] == before


def test_evidence_tampering_refuses_export_and_preview(app, client, post):
    s = stage(post, 2)
    eid = s["evidence"][0]["evidence_id"]
    with app.state.store.transaction() as db:
        db.execute("UPDATE artifacts SET data=? WHERE id=?", (b"tampered", eid))
    assert client.get("/api/export").status_code == 409
    assert client.get("/api/evidence/" + eid).status_code == 409


def test_manifest_tampering_refuses_approval(app, post):
    stage(post, 2)
    stage(post, 4, "unknown")
    post("/incidents/inc_parcel/prepare-report", {"action": "prepare-report"})
    with app.state.store.transaction() as db:
        s = app.state.store.read("demo")
        s["incidents"][0]["packet"]["trajectory"] = [[999, 999]]
        app.state.store.save(db, "demo", s)
    post(
        "/incidents/inc_parcel/approve-report",
        {
            "action": "approve-report",
            "manifest_hash": s["incidents"][0]["manifest_hash"],
            "destination": "DEMO_RECEIVER_ONLY",
            "confirmation": "APPROVE SIMULATED REPORT",
        },
        status=409,
    )


def test_consent_revocation_stops_processing(post):
    stage(post, 2)
    s = post("/consent", {"enabled": False})["state"]
    assert all(a["status"] == "PAUSED_CONSENT" for a in s["subagents"])
    post("/admin/scenarios/5/run", status=409)
    post(
        "/ingest/bee-simulated",
        {"event_id": "blocked", "utterance": "I'll do squats", "occurred_at": e.at("08:15")},
        status=409,
    )
    post("/consent", {"enabled": True})
    stage(post, 5)


def test_expired_evidence_not_publicly_accessible(app, client, post):
    s = stage(post, 2)
    eid = s["evidence"][0]["evidence_id"]
    with app.state.store.transaction() as db:
        s["evidence"][0]["retention_expires_at"] = "2000-01-01T00:00:00+00:00"
        app.state.store.save(db, "demo", s)
    assert client.get("/api/evidence/" + eid).status_code == 410


def test_no_direct_count_setter(post):
    stage(post, 6)
    post("/studio/control", {"action": "count=15"}, status=422)
    post("/studio/control", {"action": "finish", "count": 15}, status=422)


def test_rate_limited_login(app):
    with TestClient(app) as c:
        for _ in range(12):
            assert (
                c.post("/api/auth/login", json={"username": "missing", "password": "wrong"}).status_code
                == 401
            )
        assert c.post("/api/auth/login", json={"username": "missing", "password": "wrong"}).status_code == 429


def test_revision_conflict_rejects_stale_owner_action(post):
    stage(post, 1)
    post("/contracts/psc_drinks/confirm", {"action": "confirm-drinks", "revision": 999}, status=409)


def test_production_mode_fails_closed(tmp_path, monkeypatch):
    from done_irl.api import create_app

    monkeypatch.setenv("DEMO_MODE", "false")
    with pytest.raises(RuntimeError, match="not certified"):
        create_app(tmp_path, {"owner": "test"})
