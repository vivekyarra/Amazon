"""Web Push companion delivery: owner-only subscriptions, generic lock-screen copy, honest status."""

import base64
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from done_irl import engine as e
from done_irl.push import PushNotifier


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


_CLIENT = ec.generate_private_key(ec.SECP256R1())
SUB = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
    "keys": {
        "p256dh": _b64(_CLIENT.public_key().public_bytes(serialization.Encoding.X962,
                                                         serialization.PublicFormat.UncompressedPoint)),
        "auth": _b64(os.urandom(16)),
    },
}


def test_vapid_public_key_is_stable_and_private_file_persists(tmp_path):
    first = PushNotifier(tmp_path)
    again = PushNotifier(tmp_path)
    assert first.public_key() == again.public_key() and len(first.public_key()) == 87
    assert (tmp_path / "vapid-private.pem").exists()


def test_subscription_requires_auth_and_https(app, client, post):
    assert client.get("/api/push/config").json()["public_key"]
    post("/push/subscribe", {**SUB, "endpoint": "http://insecure.example.test/x"}, status=422)
    post("/push/subscribe", {**SUB, "endpoint": "https://169.254.169.254/latest/meta-data"}, status=422)
    post("/push/subscribe", {**SUB, "keys": {"p256dh": "B" * 87, "auth": "A" * 22}}, status=422)
    r = post("/push/subscribe", SUB)
    assert r["result"]["subscriptions"] == 1
    client.cookies.clear()
    anon = client.post("/api/push/subscribe", json=SUB, headers={"Idempotency-Key": "anon"})
    assert anon.status_code == 401


def test_only_new_alerts_are_pushed_with_generic_incident_copy(app, post, monkeypatch, tmp_path):
    post("/admin/scenarios/1/run", {"branch": "deposit"})
    post("/push/subscribe", SUB)  # cursor: earlier alerts are history, not pushed
    post("/admin/scenarios/2/run", {"branch": "fake"})  # DELIVERY_MISMATCH
    post("/admin/scenarios/3/run", {"branch": "disengaged"})  # SILENT_PREP + ACTIVE_ESCALATION
    pusher = PushNotifier(tmp_path)
    sent = []
    monkeypatch.setattr(pusher, "send", lambda sub, payload: sent.append(payload) or "ACCEPTED_BY_PUSH_SERVICE")
    pusher.deliver(app.state.store)
    kinds = {p["title"] for p in sent}
    assert any("Delivery needs review" in t for t in kinds)
    mismatch = next(p for p in sent if "Delivery" in p["title"])
    assert mismatch["body"] == "Open DONE/IRL to review."  # no incident detail on the lock screen
    prep = next(p for p in sent if "Coming up" in p["title"])
    assert prep["silent"] is True and "teacher" in prep["body"].lower()
    s = app.state.store.read("demo")
    statuses = {a["kind"]: a.get("delivery_status") for a in s["alerts"]}
    assert statuses["DELIVERY_MISMATCH"] == "ACCEPTED_BY_PUSH_SERVICE"
    assert all(a.get("device_delivery_verified") is False for a in s["alerts"])
    before = len(sent)
    pusher.deliver(app.state.store)
    assert len(sent) == before  # each alert attempted once per subscription


def test_gone_subscription_is_pruned(app, post, monkeypatch, tmp_path):
    post("/push/subscribe", SUB)
    post("/admin/scenarios/1/run", {"branch": "deposit"})
    post("/admin/scenarios/2/run", {"branch": "fake"})
    pusher = PushNotifier(tmp_path)
    monkeypatch.setattr(pusher, "send", lambda sub, payload: "SUBSCRIPTION_GONE")
    pusher.deliver(app.state.store)
    assert app.state.store.read("demo")["push_subscriptions"] == []


def test_service_worker_is_served_from_built_console(client):
    r = client.get("/sw.js")
    if r.status_code == 200 and "javascript" in r.headers.get("content-type", ""):
        assert "showNotification" in r.text
    else:  # backend-only checkout without a built console still serves the SPA shell
        assert r.status_code in {200, 404}
    traversal = client.get("/..%2fledger.db")
    assert "SQLite format" not in traversal.text


def test_revoked_consent_stops_push(app, post, monkeypatch, tmp_path):
    post("/push/subscribe", SUB)
    post("/admin/scenarios/1/run", {"branch": "deposit"})
    post("/admin/scenarios/2/run", {"branch": "fake"})
    post("/consent", {"enabled": False})
    pusher = PushNotifier(tmp_path)
    sent = []
    monkeypatch.setattr(pusher, "send", lambda sub, payload: sent.append(payload) or "ACCEPTED_BY_PUSH_SERVICE")
    pusher.deliver(app.state.store)
    assert sent == []
    assert e.MODE == "SIMULATED_VERIFIED"


def test_real_vapid_signing_and_encryption_reach_the_push_service(tmp_path, monkeypatch):
    """Regression: the VAPID key format previously failed before any HTTP call."""
    import pywebpush

    seen = {}

    class Response:
        status_code = 201
        text = ""
        headers = {}

    def fake_post(url, data=None, headers=None, timeout=None, **_):
        seen.update(url=url, headers=headers, body=data)
        return Response()

    monkeypatch.setattr(pywebpush.requests, "post", fake_post)
    pusher = PushNotifier(tmp_path)
    status = pusher.send(SUB, {"title": "DONE/IRL", "body": "x"})
    assert status == "ACCEPTED_BY_PUSH_SERVICE"
    assert seen["url"] == SUB["endpoint"]
    assert seen["headers"]["Authorization"].startswith("vapid t=") and seen["headers"]["Content-Encoding"] == "aes128gcm"
    assert b"DONE/IRL" not in seen["body"]  # payload is encrypted


def test_unreachable_endpoint_is_recorded_not_raised(tmp_path, monkeypatch):
    import pywebpush

    def boom(*a, **k):
        raise pywebpush.requests.ConnectionError("down")

    monkeypatch.setattr(pywebpush.requests, "post", boom)
    assert PushNotifier(tmp_path).send(SUB, {"title": "t", "body": "b"}).startswith("FAILED_")
