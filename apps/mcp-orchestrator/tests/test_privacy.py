"""Owner privacy controls: per-camera exclusion, PRIVATE_MASKS, retention, disconnect, deletion."""

import hashlib
import hmac
import json
import shutil
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from done_irl import engine as e, privacy
from done_irl.api import create_app
from done_irl.camera_reducers import frame_received
from done_irl.models import ApiError
from done_irl.store import Store

MASK = [[0.75, 0.0], [1.0, 0.0], [1.0, 0.3], [0.75, 0.3]]
OWNER_PASSWORD = "long-test-owner-password"
OTHER_PASSWORD = "long-test-other-password"


def stage(post, n, branch="deposit"):
    return post(f"/admin/scenarios/{n}/run", {"branch": branch})["state"]


def login(client, username, password):
    assert (
        client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    )


def write(client, path, body=None, key=None):
    return client.post("/api" + path, json=body or {}, headers={"Idempotency-Key": key or uuid.uuid4().hex})


def ring_payload(request_id="request-1", event_id="motion-1", device="camera-1"):
    return {
        "meta": {
            "version": "1.1",
            "time": "2026-10-20T07:00:00Z",
            "request_id": request_id,
            "account_id": "account-1",
        },
        "data": {
            "id": event_id,
            "type": "motion_detected",
            "attributes": {"source": device, "timestamp": 1_792_000_000_000},
        },
    }


def signed(payload, key="private-test-key"):
    body = json.dumps(payload).encode()
    return body, "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def live(tmp_path, monkeypatch):
    key = tmp_path / "key"
    key.write_bytes(bytes(range(32)))
    key.chmod(0o600)
    bindings = tmp_path / "bindings.json"
    bindings.write_text(
        json.dumps(
            {
                "account-1": {"household": "house_owner", "devices": ["camera-1", "camera-2"]},
                "account-2": {"household": "house_other", "devices": ["camera-9"]},
            }
        )
    )
    monkeypatch.setenv("GUIDED_MODE", "false")
    monkeypatch.setenv("LEDGER_KEY_FILE", str(key))
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://testserver")
    monkeypatch.setenv("RING_HMAC_KEY", "private-test-key")
    monkeypatch.setenv("RING_BINDINGS_FILE", str(bindings))
    monkeypatch.delenv("BEE_TOKEN", raising=False)
    passwords = {"owner": OWNER_PASSWORD, "other": OTHER_PASSWORD}

    def make():
        return create_app(tmp_path / "live", passwords)

    return make


def test_privacy_controls_require_authenticated_owner_and_idempotency(app):
    with TestClient(app) as c:
        assert c.get("/api/privacy").status_code == 401
        assert c.post("/api/privacy/retention", json={"days": 3}).status_code == 401
        assert c.post("/api/privacy/providers/ring/disconnect", json={}).status_code == 401
        login(c, "owner", "test-owner-password")
        assert c.post("/api/privacy/retention", json={"days": 3}).status_code == 400
        assert write(c, "/privacy/retention", {"days": 0}).status_code == 422
        assert write(c, "/privacy/retention", {"days": 31}).status_code == 422
        assert write(c, "/privacy/retention", {"days": 3, "extra": True}).status_code == 422
        assert write(c, "/privacy/providers/alexa/disconnect").status_code == 404
        first = write(c, "/privacy/retention", {"days": 3}, key="same")
        assert first.status_code == 200 and first.json()["trace_id"]
        assert write(c, "/privacy/retention", {"days": 3}, key="same").json() == first.json()
        assert write(c, "/privacy/retention", {"days": 4}, key="same").status_code == 409


def test_camera_exclusion_blocks_scripted_collection_and_is_audited(client, post):
    stage(post, 1)
    post("/privacy/cameras/exclusion", {"device_id": "unknown-camera", "excluded": True}, status=404)
    s = post("/privacy/cameras/exclusion", {"device_id": privacy.SCRIPTED_CAMERA, "excluded": True})["state"]
    assert s["privacy"]["excluded_cameras"] == [privacy.SCRIPTED_CAMERA]
    assert s["events"][-1]["event_type"] == "privacy.camera_exclusion_changed"
    for n in (2, 5):
        post(f"/admin/scenarios/{n}/run", {"branch": "deposit"}, status=409)
    state = client.get("/api/state").json()["state"]
    assert state["evidence"] == [] and not any(c["key"] == "parcel" for c in state["contracts"])
    # Another household's exclusion does not change this one.
    login(client, "other", "test-other-password")
    assert client.get("/api/privacy").json()["excluded_cameras"] == []
    login(client, "judge", "test-admin-password")
    post("/privacy/cameras/exclusion", {"device_id": privacy.SCRIPTED_CAMERA, "excluded": False})
    assert stage(post, 2)["evidence"]


def test_live_excluded_camera_cannot_start_and_webhook_is_acknowledged_not_processed(live):
    app = live()
    with TestClient(app, base_url="https://testserver") as client:
        login(client, "owner", OWNER_PASSWORD)
        assert write(client, "/consent", {"enabled": True}).status_code == 200
        assert client.get("/api/privacy").json()["cameras"] == ["camera-1", "camera-2"]
        # Cross-household device ids cannot be configured.
        assert (
            write(
                client, "/privacy/cameras/exclusion", {"device_id": "camera-9", "excluded": True}
            ).status_code
            == 404
        )
        body, signature = signed(ring_payload())
        queued = client.post("/api/webhooks/ring", content=body, headers={"X-Signature": signature})
        assert queued.status_code == 202 and queued.json()["receipt_id"]
        assert (
            write(
                client, "/privacy/cameras/exclusion", {"device_id": "camera-1", "excluded": True}
            ).status_code
            == 200
        )
        start = write(client, "/camera/start", {"device_id": "camera-1"})
        assert start.status_code == 409 and start.json()["error"]["code"] == "CAMERA_EXCLUDED"
        assert client.get("/api/camera/status").json()["status"] == "CLOSED"
        body, signature = signed(ring_payload("request-2", "motion-2"))
        ignored = client.post("/api/webhooks/ring", content=body, headers={"X-Signature": signature})
        assert ignored.status_code == 202
        assert ignored.json() == {
            "receipt_id": None,
            "duplicate": False,
            "processed": False,
            "reason": "CAMERA_EXCLUDED",
        }
        app.state.runtime.step()
        state = client.get("/api/state").json()["state"]
        assert not any(event["event_type"].startswith("ring.") for event in state["events"])
        rows = app.state.store.db.execute("SELECT status,payload,error_code FROM inbox").fetchall()
        assert [(r["status"], r["payload"], r["error_code"]) for r in rows] == [
            ("CANCELLED", None, "CAMERA_EXCLUDED")
        ]
        # A non-excluded camera in the same household is still processed.
        body, signature = signed(ring_payload("request-3", "motion-3", "camera-2"))
        assert (
            client.post("/api/webhooks/ring", content=body, headers={"X-Signature": signature}).status_code
            == 202
        )
        app.state.runtime.step()
        state = client.get("/api/state").json()["state"]
        assert [
            e["payload"]["device_id"] for e in state["events"] if e["event_type"] == "ring.motion_detected"
        ] == ["camera-2"]


def test_frame_callback_refuses_excluded_camera_without_evidence(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    state = e.fresh()
    state.update(household_id="house_owner", clock_mode="WALL", consent=True)
    state["privacy"] = {"excluded_cameras": ["camera-1"]}
    with store.transaction() as db:
        store.save(db, "house_owner", state)
    session = {"id": "cam", "device_id": "camera-1", "model_sha256": "a" * 64}
    with pytest.raises(ApiError) as exc:
        frame_received(store, "house_owner", session, np.zeros((4, 4, 3), np.uint8), None, 1, "h")
    assert exc.value.code == "CAMERA_EXCLUDED"
    assert store.read("house_owner")["evidence"] == []


def test_apply_masks_zeroes_exact_normalized_region():
    frame = np.full((100, 200, 3), 77, np.uint8)
    out = privacy.apply_masks(frame, (((0.5, 0.0), (1.0, 0.0), (1.0, 0.5), (0.5, 0.5)),))
    assert not out[0:50, 100:200].any()
    assert (out[51:, :] == 77).all() and (out[:, :99] == 77).all()
    assert (frame == 77).all()  # Input is not modified in place.


def _decode_png(data):
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def test_private_masks_zero_pixels_in_derived_evidence_before_hashing(client, post):
    mask = post(
        "/privacy/cameras/masks", {"device_id": privacy.SCRIPTED_CAMERA, "polygons": [MASK], "revision": 0}
    )
    assert mask["result"]["calibration_revision"] == 1
    assert mask["state"]["events"][-1]["event_type"] == "privacy.masks_updated"
    post(
        "/privacy/cameras/masks",
        {"device_id": privacy.SCRIPTED_CAMERA, "polygons": [MASK], "revision": 0},
        status=409,
    )
    post(
        "/privacy/cameras/masks",
        {"device_id": privacy.SCRIPTED_CAMERA, "polygons": [[[0, 0], [2, 0], [0, 1]]]},
        status=422,
    )
    stage(post, 2)
    stage(post, 4, "unknown")
    s = stage(post, 5, "empty")
    images = [item for item in s["evidence"] if item["mime"] == "image/png"]
    assert {item["kind"] for item in images} >= {
        "DEPOSIT_OBSERVATION",
        "REMOVAL_FRAME",
        "THRESHOLD_OBSERVATION",
    }
    for item in images:
        data = client.get("/api/evidence/" + item["evidence_id"]).content
        assert hashlib.sha256(data).hexdigest() == item["sha256_original"]
        assert item["privacy_mask"]["calibration_revision"] == 1
        if item["kind"] == "PERSON_CROP":
            continue
        image = _decode_png(data)
        h, w = image.shape[:2]
        assert not image[: int(0.3 * h) - 1, int(0.75 * w) + 1 :].any()
        assert image[int(0.3 * h) + 2 :, : int(0.75 * w) - 2].any()
    assert client.get("/api/export").status_code == 200  # Chain/hash verification still passes.
    clips = {item["kind"]: item for item in s["evidence"] if item["mime"] == "video/webm"}
    if not clips:
        assert not shutil.which("ffmpeg")
        return
    assert clips["REMOVAL_CLIP_ORIGINAL"]["privacy_mask"]["scope"] == "ORIGINAL_UNMASKED_ENCRYPTED"
    means = {}
    for kind, item in clips.items():
        data = client.get("/api/evidence/" + item["evidence_id"]).content
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "clip.webm"
            path.write_bytes(data)
            capture = cv2.VideoCapture(str(path))
            ok, frame = capture.read()
            capture.release()
        assert ok
        h, w = frame.shape[:2]
        means[kind] = frame[4 : int(0.3 * h) - 4, int(0.75 * w) + 4 : w - 4].mean()
    assert means["REMOVAL_CLIP_DERIVED"] < 3 < means["REMOVAL_CLIP_ORIGINAL"]


def test_retention_setting_updates_existing_and_new_artifacts_without_breaking_chain(app, client, post):
    s = stage(post, 2)
    first = s["evidence"][0]
    original = datetime.fromisoformat(first["retention_expires_at"])
    assert first["retention_days_at_capture"] == 7
    s = post("/privacy/retention", {"days": 30})["state"]
    item = s["evidence"][0]
    assert datetime.fromisoformat(item["retention_expires_at"]) == original + timedelta(days=23)
    assert item["retention_expires_at_original"] == first["retention_expires_at"]
    assert item["chain_hash"] == first["chain_hash"]
    assert s["events"][-1]["event_type"] == "privacy.retention_changed"
    assert client.get("/api/export").status_code == 200
    s = stage(post, 4, "unknown")
    assert s["evidence"][-1]["retention_days_at_capture"] == 30
    s = post("/privacy/retention", {"days": 1})["state"]
    item = s["evidence"][0]
    expiry = datetime.fromisoformat(item["retention_expires_at"])
    assert expiry == original - timedelta(days=6)
    assert client.get("/api/export").status_code == 200
    # Another household keeps its own default policy.
    login(client, "other", "test-other-password")
    assert client.get("/api/privacy").json()["retention_days"] == 7
    login(client, "judge", "test-admin-password")
    store = app.state.store
    with store.transaction() as db:
        assert store.purge_expired(db, expiry.timestamp() + 1) >= 1
        assert not db.get_artifact(item["evidence_id"], "guided")
        assert db.execute("SELECT id FROM retention_tombstones WHERE id=?", (item["evidence_id"],)).fetchone()
    login(client, "judge", "test-admin-password")  # The fast-forwarded purge also expired sessions.
    assert client.get("/api/export").status_code == 410  # Expired, distinguished from tampering.


def test_shortened_retention_deletes_due_bytes_immediately_and_never_resurrects(app, post):
    stage(post, 2)
    store = app.state.store
    state = store.read("guided")
    later = datetime.now(timezone.utc) + timedelta(days=3)
    with store.transaction() as db:
        result = privacy.apply_retention(state, db, "guided", 2, now=later)
        assert result["purged"] == len(state["evidence"])
        assert not db.execute("SELECT id FROM artifacts WHERE household='guided'").fetchall()
        tombstones = db.execute("SELECT id FROM retention_tombstones WHERE household='guided'").fetchall()
        assert len(tombstones) == len(state["evidence"])
        before = [item["retention_expires_at"] for item in state["evidence"]]
        assert privacy.apply_retention(state, db, "guided", 30, now=later)["updated"] == 0
        assert [item["retention_expires_at"] for item in state["evidence"]] == before


def test_provider_disconnect_cancels_work_and_never_auto_reconnects(live, monkeypatch):
    app = live()
    with TestClient(app, base_url="https://testserver") as client:
        login(client, "owner", OWNER_PASSWORD)
        assert write(client, "/consent", {"enabled": True}).status_code == 200
        utterance = {
            "event_id": "bee-1",
            "utterance": "I will call mom",
            "occurred_at": "2026-10-20T07:00:00+00:00",
        }
        receipt, _ = app.state.runtime.enqueue("house_owner", "bee", "bee-1", utterance, cursor="bee-1")
        app.state.bee.token = "in-memory-test-token"
        result = write(client, "/privacy/providers/bee/disconnect")
        assert result.status_code == 200
        assert result.json()["result"] == {
            "provider": "bee",
            "status": "STANDBY",
            "cancelled_inbox": 1,
            "cursors_removed": 1,
        }
        assert result.json()["state"]["events"][-1]["event_type"] == "privacy.provider_disconnected"
        db = app.state.store.db
        assert tuple(db.execute("SELECT status,payload FROM inbox WHERE id=?", (receipt,)).fetchone()) == (
            "CANCELLED",
            None,
        )
        assert not db.execute("SELECT * FROM provider_cursors WHERE household='house_owner'").fetchall()
        assert app.state.bee.token is None and app.state.bee.stopped
        with pytest.raises(ApiError) as exc:
            app.state.runtime.enqueue("house_owner", "bee", "bee-2", {**utterance, "event_id": "bee-2"})
        assert exc.value.code == "PROVIDER_DISCONNECTED"
        # Toggling global consent does not silently reconnect a revoked provider.
        write(client, "/consent", {"enabled": False})
        write(client, "/consent", {"enabled": True})
        statuses = {
            i["name"]: i["status"] for i in client.get("/api/integrations/status").json()["integrations"]
        }
        assert statuses["Bee"] == "STANDBY"
        assert write(client, "/privacy/providers/ring/disconnect").status_code == 200
        body, signature = signed(ring_payload())
        ignored = client.post("/api/webhooks/ring", content=body, headers={"X-Signature": signature})
        assert ignored.status_code == 202 and ignored.json()["reason"] == "PROVIDER_DISCONNECTED"
        start = write(client, "/camera/start", {"device_id": "camera-1"})
        assert start.json()["error"]["code"] == "PROVIDER_DISCONNECTED"
        statuses = {
            i["name"]: i["status"] for i in client.get("/api/integrations/status").json()["integrations"]
        }
        assert statuses["Ring"] == statuses["Ring video"] == "STANDBY"
        # Another household is unaffected.
        login(client, "other", OTHER_PASSWORD)
        assert client.get("/api/privacy").json()["providers"]["bee"]["status"] == "NOT_REVOKED"
    # Restart with a provisioned token: revocation persists and the stream is not started.
    monkeypatch.setenv("BEE_TOKEN", "provisioned-test-token")
    restarted = live()
    with TestClient(restarted, base_url="https://testserver") as client:
        assert restarted.state.bee.token is None and restarted.state.bee.stopped
        login(client, "owner", OWNER_PASSWORD)
        assert client.get("/api/privacy").json()["providers"]["bee"]["status"] == "REVOKED"
        assert (
            write(client, "/privacy/providers/bee/reauthorize").json()["result"]["status"]
            == "OWNER_REAUTHORIZED"
        )
        assert write(client, "/privacy/providers/bee/reauthorize").status_code == 409


def populate_other_household(store):
    state = e.fresh()
    state["household_id"] = "house_other"
    c = e.create_contract(
        state, "teacher", "Meeting", "Other family private promise", "Teacher", "BEE_CONVERSATION_AUDIT"
    )
    with store.transaction() as db:
        evidence = e.add_evidence(state, db, "house_other", c, "TEST", b"other-private-media")
        store.save(db, "house_other", state)
    return state, evidence


def test_household_deletion_requires_confirmation_and_is_household_scoped(app, client, post):
    stage(post, 2)
    before = stage(post, 4, "unknown")
    assert before["incidents"] and before["subagents"] and before["evidence"]
    store = app.state.store
    other_state, other_evidence = populate_other_household(store)
    phrase = privacy.DELETE_PHRASE
    post("/privacy/household/delete", {"household_id": "guided", "confirmation": "delete"}, status=422)
    post("/privacy/household/delete", {"household_id": "house_other", "confirmation": phrase}, status=403)
    # The other owner cannot delete the guided household.
    login(client, "other", "test-other-password")
    assert (
        write(
            client, "/privacy/household/delete", {"household_id": "guided", "confirmation": phrase}
        ).status_code
        == 403
    )
    login(client, "judge", "test-admin-password")
    response = post(
        "/privacy/household/delete", {"household_id": "guided", "confirmation": phrase}, key="erase"
    )
    receipt = response["result"]
    assert receipt["deleted"]["contracts"] == len(before["contracts"])
    assert receipt["deleted"]["evidence_artifacts"] == len(before["evidence"])
    assert receipt["deleted"]["incidents"] == 1 and receipt["deleted"]["schedules"] > 0
    assert receipt["cloud_deletion"] == "NOT_CONFIGURED"
    s = client.get("/api/state").json()["state"]
    assert s["contracts"] == s["evidence"] == s["incidents"] == s["subagents"] == s["alerts"] == []
    assert s["consent"] is False and s["deletion_receipts"] == [receipt]
    assert [event["event_type"] for event in s["events"]] == ["privacy.household_deleted"]
    serialized = json.dumps(s)
    for text in ("sister", "teacher", "drinks", "squats", "parcel"):
        assert text not in serialized.lower()
    assert not store.db.execute("SELECT id FROM artifacts WHERE household='guided'").fetchall()
    assert [r["key"] for r in store.db.execute("SELECT key FROM commands WHERE household='guided'")] == [
        "erase"
    ]
    assert (
        post("/privacy/household/delete", {"household_id": "guided", "confirmation": phrase}, key="erase")
        == response
    )
    assert client.get("/api/evidence/" + before["evidence"][0]["evidence_id"]).status_code == 404
    # The other household is untouched.
    assert store.read("house_other") == other_state
    with store.lock:
        assert store.uow.get_artifact(other_evidence, "house_other")["data"] == b"other-private-media"
