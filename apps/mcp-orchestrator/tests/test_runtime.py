import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from done_irl import engine as e
from done_irl.api import create_app
from done_irl.models import ApiError, BeeInput
from done_irl.runtime import Runtime
from done_irl.store import Store
from done_irl.webhooks import verify_ring


NOW = datetime(2026, 10, 20, 7, tzinfo=timezone.utc)


def live_house(store, now=NOW):
    state = e.fresh()
    state.update(
        household_id="house_owner",
        clock_mode="WALL",
        source_mode="STANDBY",
        now=now.isoformat(),
        consent=True,
    )
    with store.transaction() as db:
        store.save(db, "house_owner", state)
    return state


def utterance():
    return {
        "event_id": "bee-1",
        "utterance": "I will attend the teacher meeting at 4 pm",
        "occurred_at": NOW.isoformat(),
        "speaker": "SELF",
    }


def test_encrypted_state_and_commands_survive_restart(app, post, tmp_path):
    post("/admin/scenarios/1/run")
    store = app.state.store
    raw = store.db.execute("SELECT state FROM households WHERE id='guided'").fetchone()["state"]
    response = store.db.execute("SELECT response FROM commands LIMIT 1").fetchone()["response"]
    assert "teacher" not in raw and "utterance" not in response
    reopened = Store(str(tmp_path / "ledger.db"))
    assert len(reopened.read("guided")["contracts"]) == 4
    reopened.db.close()


def test_ciphertext_is_bound_to_household_identity(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    live_house(store)
    with store.transaction() as db:
        ciphertext = db.execute("SELECT state FROM households WHERE id='house_owner'").fetchone()["state"]
        db.execute("INSERT INTO households VALUES (?,?)", ("house_other", ciphertext))
    with pytest.raises(ApiError) as exc:
        store.read("house_other")
    assert exc.value.code == "EVIDENCE_TAMPERED"


def test_missing_key_does_not_silently_create_another(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    live_house(store)
    store.db.close()
    (tmp_path / "ledger.db.key").unlink()
    with pytest.raises(RuntimeError, match="key is missing"):
        Store(str(tmp_path / "ledger.db"))


def test_artifact_is_encrypted_and_retention_physically_deletes(app, post):
    post("/admin/scenarios/1/run")
    post("/admin/scenarios/2/run")
    store = app.state.store
    state = store.read("guided")
    item = state["evidence"][0]
    raw = store.db.execute("SELECT data FROM artifacts WHERE id=?", (item["evidence_id"],)).fetchone()["data"]
    with store.lock:
        decoded = store.uow.get_artifact(item["evidence_id"], "guided")
    assert raw != decoded["data"]
    assert hashlib.sha256(decoded["data"]).hexdigest() == item["sha256_original"]
    expiry = datetime.fromisoformat(item["retention_expires_at"]).timestamp() + 1
    with store.transaction() as db:
        assert store.purge_expired(db, expiry) >= 1
        assert not db.get_artifact(item["evidence_id"], "guided")
        assert db.execute("SELECT id FROM retention_tombstones WHERE id=?", (item["evidence_id"],)).fetchone()
    assert store.read("guided")["evidence"] == state["evidence"]  # Immutable hash chain retained.
    with pytest.raises(ApiError) as exc:
        e.verify_artifacts(state, store.uow, "guided")
    assert exc.value.code == "EVIDENCE_EXPIRED"


def test_inbox_restart_lease_recovery_and_exactly_once_reducer(tmp_path):
    path = str(tmp_path / "ledger.db")
    store = Store(path)
    live_house(store)
    clock = [NOW.timestamp()]
    runtime = Runtime(store, lambda: clock[0])
    receipt, created = runtime.enqueue("house_owner", "bee", "bee-1", utterance(), cursor="bee-1")
    assert created
    assert runtime.enqueue("house_owner", "bee", "bee-1", utterance())[1] is False
    assert runtime.claim()["id"] == receipt
    store.db.close()  # Crash after claiming, before reducer commit.
    reopened = Store(path)
    worker = Runtime(reopened, lambda: clock[0])
    assert worker.step() == 0
    clock[0] += 61
    assert worker.step() == 1
    assert worker.step() == 0
    state = reopened.read("house_owner")
    assert len(state["contracts"]) == 1
    assert state["contracts"][0]["source_mode"] == "LIVE_VERIFIED"
    assert len([event for event in state["events"] if event["event_type"] == "bee.utterance.received"]) == 1
    assert state["events"][0]["source"] == "BEE"
    assert state["events"][0]["trace_id"] == state["contracts"][0]["trace_id"]
    assert state["events"][1]["trace_id"] == state["contracts"][0]["trace_id"]
    assert "_event_source" not in state
    row = reopened.db.execute("SELECT * FROM inbox WHERE id=?", (receipt,)).fetchone()
    assert row["status"] == "DONE" and row["payload"] is None and row["attempts"] == 2
    assert reopened.db.execute("SELECT cursor FROM provider_cursors").fetchone()["cursor"] == "bee-1"


def test_wall_clock_deadlines_reconcile_without_guided_controls(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    state = live_house(store)
    e.compile_bee(state, BeeInput.model_validate(utterance()))
    with store.transaction() as db:
        store.save(db, "house_owner", state)
        guided = e.fresh()
        guided["household_id"] = "guided"
        store.save(db, "guided", guided)
    # 16:00 IST = 10:30 UTC. First tier at 09:30 UTC.
    runtime = Runtime(store, lambda: NOW.replace(hour=9, minute=31).timestamp())
    runtime.step()
    assert len(store.read("house_owner")["alerts"]) == 1
    runtime.step()
    assert len(store.read("house_owner")["alerts"]) == 1
    assert store.read("guided")["now"] == e.at("08:00")
    runtime.clock = lambda: NOW.replace(hour=10, minute=31).timestamp()
    runtime.step()
    state = store.read("house_owner")
    assert state["contracts"][0]["status"] == "MISSED"
    assert len(state["alerts"]) == 1  # Stale T25 does not spam on restart.


def test_invalid_provider_event_dead_letters_without_partial_commit(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    live_house(store)
    runtime = Runtime(store, lambda: NOW.timestamp())
    receipt, _ = runtime.enqueue("house_owner", "bee", "bad", {"utterance": "missing timestamp"})
    runtime.step()
    row = store.db.execute("SELECT * FROM inbox WHERE id=?", (receipt,)).fetchone()
    assert row["status"] == "DEAD" and row["error_code"] == "INVALID_PROVIDER_EVENT"
    assert store.read("house_owner")["events"] == []


def test_reused_provider_identity_with_changed_payload_rejected(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    live_house(store)
    runtime = Runtime(store, lambda: NOW.timestamp())
    runtime.enqueue("house_owner", "bee", "same", utterance())
    with pytest.raises(ApiError) as exc:
        runtime.enqueue("house_owner", "bee", "same", {**utterance(), "utterance": "changed"})
    assert exc.value.code == "PROVIDER_EVENT_CONFLICT"


def test_revoked_consent_cancels_previously_received_work(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    state = live_house(store)
    runtime = Runtime(store, lambda: NOW.timestamp())
    receipt, _ = runtime.enqueue("house_owner", "bee", "bee-1", utterance())
    state["consent"] = False
    with store.transaction() as db:
        store.save(db, "house_owner", state)
    runtime.step()
    assert store.read("house_owner")["contracts"] == []
    assert (
        store.db.execute("SELECT status FROM inbox WHERE id=?", (receipt,)).fetchone()["status"]
        == "CANCELLED"
    )
    with pytest.raises(ApiError) as exc:
        runtime.enqueue("house_owner", "bee", "bee-2", utterance())
    assert exc.value.code == "CONSENT_REQUIRED"


def ring_payload():
    return {
        "meta": {
            "version": "1.1",
            "time": "2026-10-20T07:00:00Z",
            "request_id": "request-1",
            "account_id": "account-1",
        },
        "data": {
            "id": "motion-1",
            "type": "motion_detected",
            "attributes": {"source": "camera-1", "timestamp": int(NOW.timestamp() * 1000)},
        },
    }


def signing(payload, key="private-test-key"):
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    return body, signature


def bindings(tmp_path):
    path = tmp_path / "bindings.json"
    path.write_text(json.dumps({"account-1": {"household": "house_owner", "devices": ["camera-1"]}}))
    return str(path)


def test_official_ring_raw_body_signature_and_delayed_retry(tmp_path):
    body, signature = signing(ring_payload())
    result = verify_ring(body, signature, "private-test-key", bindings(tmp_path), NOW.timestamp() + 86400)
    assert result[:2] == ("house_owner", "request-1")
    for bad_body, bad_signature in [(body + b" ", signature), (body, "forged"), (body, signature.upper())]:
        with pytest.raises(ApiError) as exc:
            verify_ring(bad_body, bad_signature, "private-test-key", bindings(tmp_path))
        assert exc.value.code == "BAD_SIGNATURE"


def test_ring_signed_unknown_device_cannot_cross_households(tmp_path):
    payload = ring_payload()
    payload["data"]["attributes"]["source"] = "other-camera"
    body, signature = signing(payload)
    with pytest.raises(ApiError) as exc:
        verify_ring(body, signature, "private-test-key", bindings(tmp_path))
    assert exc.value.code == "RING_DEVICE_NOT_LINKED"


def test_configured_live_webhook_persists_receipt_without_claiming_video(tmp_path, monkeypatch):
    key = tmp_path / "key"
    key.write_bytes(bytes(range(32)))
    key.chmod(0o600)
    monkeypatch.setenv("GUIDED_MODE", "false")
    monkeypatch.setenv("LEDGER_KEY_FILE", str(key))
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://testserver")
    monkeypatch.setenv("RING_HMAC_KEY", "private-test-key")
    monkeypatch.setenv("RING_BINDINGS_FILE", bindings(tmp_path))
    app = create_app(tmp_path / "live", {"owner": "long-test-owner-password"})
    with TestClient(app, base_url="https://testserver") as client:
        assert (
            client.post(
                "/api/auth/login", json={"username": "owner", "password": "long-test-owner-password"}
            ).status_code
            == 200
        )
        assert client.get("/api/state").json()["state"]["consent"] is False
        body, signature = signing(ring_payload())
        assert (
            client.post("/api/webhooks/ring", content=body, headers={"X-Signature": signature}).status_code
            == 409
        )
        assert (
            client.post(
                "/api/consent", json={"enabled": True}, headers={"Idempotency-Key": "consent"}
            ).status_code
            == 200
        )
        for expected_duplicate in [False, True]:
            result = client.post("/api/webhooks/ring", content=body, headers={"X-Signature": signature})
            assert result.status_code == 202
            assert result.json()["duplicate"] is expected_duplicate
        app.state.runtime.step()
        state = client.get("/api/state").json()["state"]
        assert any(event["event_type"] == "ring.motion_detected" for event in state["events"])
        assert state["evidence"] == [] and state["contracts"] == []
        assert client.post("/api/studio/sessions", headers={"Idempotency-Key": "studio"}).status_code == 503
        assert client.post("/api/admin/reset", headers={"Idempotency-Key": "reset"}).status_code == 403


def test_tv_session_registration_is_owner_scoped_bounded_and_not_device_proof(client, post):
    registered = post("/tv/sessions", key="register-tv")["result"]
    repeated = post("/tv/sessions", key="register-tv")["result"]
    assert registered == repeated
    assert registered["device_runtime_verified"] is False
    for _ in range(10):
        post("/tv/sessions")
    state = client.get("/api/state").json()["state"]
    assert len(state["tv_sessions"]) == 8
    assert (
        client.post(
            "/api/auth/login", json={"username": "other", "password": "test-other-password"}
        ).status_code
        == 200
    )
    other = client.get("/api/state").json()["state"]
    assert other.get("tv_sessions", []) == []


def test_legacy_scripted_clock_owner_household_migrates_to_wall_clock_and_reconciles(tmp_path):
    """Regression: an owner household created on the scripted clock was never ticked by the wall-clock worker."""
    from datetime import datetime, timedelta, timezone
    from fastapi.testclient import TestClient

    from done_irl import engine as e
    from done_irl.api import create_app
    from done_irl.models import BeeInput

    passwords = {"judge": "migration-admin-pass", "owner": "migration-owner-pass"}
    app = create_app(tmp_path, passwords)
    store = app.state.store
    legacy = e.fresh()
    legacy["household_id"] = "house_owner"
    past = datetime.now(timezone.utc) - timedelta(hours=3)
    e.compile_bee(legacy, BeeInput(event_id="m", utterance="I will call Mom in 2 hours.", occurred_at=past.isoformat()))
    guest = e.fresh()
    guest["household_id"] = "guest_0a1b2c"
    with store.transaction() as db:
        store.save(db, "house_owner", legacy)
        store.save(db, "guest_0a1b2c", guest)
    restarted = create_app(tmp_path, passwords)
    with TestClient(restarted):
        # Guided households ("guided" and "guest_*") keep their scripted clock across restarts.
        assert restarted.state.store.read("guest_0a1b2c")["clock_mode"] != "WALL"
        s = restarted.state.store.read("house_owner")
        assert s["clock_mode"] == "WALL"
        assert any(ev["event_type"] == "household.clock_migrated" for ev in s["events"])
        restarted.state.runtime.step()
        s = restarted.state.store.read("house_owner")
        [c] = [c for c in s["contracts"] if c["key"].startswith("gen_")]
        assert c["status"] == "MISSED"
        assert {j["kind"]: j["status"] for j in c["scheduled_jobs"]} == {
            "T60": "EXECUTED", "T25": "EXECUTED", "DEADLINE": "EXECUTED"}
        assert not [a for a in s["alerts"] if a["contract_id"] == c["contract_id"]]  # stale: no late nudges
