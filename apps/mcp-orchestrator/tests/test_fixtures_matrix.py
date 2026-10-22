"""Machine-checked golden assertions that close the spec section 13 fixture matrix and P0 hardening rows.

docs/evidence/fixture-matrix.md maps every fixture F01-F24 to its tests. This module holds the tests
that did not exist elsewhere:

* P0-004  every POST route is authenticated, authorized, idempotent, validated and audited.
* F19     Ring session budget / token expiry: coverage gap recorded, truthful fallback label.
* F20     full service restart mid-watchdog/scheduler: state recovers, no duplicate actions.
* F21     duplicate removal / duplicate provider event: one incident, one alert, one reduction.
* F22     another household cannot read or act on incident media.
* F23     model/tool dispatch attempts are denied with zero outbound network calls.
* P0-007 / P0-045  lifecycle (startup, failure, reconnect, resume, teardown) and degraded paths.
* F01, F04-F07, F13-F16  golden-table assertions the original scenario tests left implicit.

Everything here is synthetic or mocked transport; nothing is a live Ring/Bee/device proof.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from done_irl import engine as e, privacy, vision
from done_irl.adapters import BeeAdapter, RingAdapter
from done_irl.api import create_app
from done_irl.camera import CameraBridge
from done_irl.camera_reducers import camera_ended
from done_irl.models import ApiError
from done_irl.runtime import Runtime
from done_irl.store import Store

PASSWORDS = {"demo-admin": "test-admin-password", "owner": "test-owner-password", "other": "test-other-password"}
LIVE_PASSWORDS = {"owner": "long-test-owner-password", "other": "long-test-other-password"}


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


_PUSH_KEY = ec.generate_private_key(ec.SECP256R1()).public_key()
PUSH = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/matrix-test",
    "keys": {
        "p256dh": _b64(
            _PUSH_KEY.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        ),
        "auth": _b64(os.urandom(16)),
    },
}
STAGE1 = ("/api/admin/scenarios/1/run", {"branch": "deposit"})
STAGE2 = ("/api/admin/scenarios/2/run", {"branch": "deposit"})
STAGE4 = ("/api/admin/scenarios/4/run", {"branch": "unknown"})
STUDIO = ("/api/studio/sessions", {})


def landmarks():
    return vision.extract_marker_pose(vision.synthetic_pose_frame(170))


# ---------------------------------------------------------------------------------------------
# P0-004: the write matrix. Every POST route of the FastAPI app must appear in exactly one of
# WRITES (household ledger writes through the shared command path) or EXEMPT (with the reason and
# the property that replaces the session/idempotency-key contract). A new route fails the
# classification test until someone decides which contract it follows.
# ---------------------------------------------------------------------------------------------

EXEMPT = {
    "/api/auth/login": "Credential exchange cannot require a session; validated, rate-limited, no ledger write.",
    "/api/auth/guest": "One-click judge access in demo deployments only: issues a session for a new isolated demo_* household; rate-limited and capped, no ledger write.",
    "/api/auth/logout": "Requires the session it revokes; repeat is a no-op 401; no household data is written.",
    "/api/webhooks/ring": "Provider callback: raw-body HMAC + account/device binding instead of a session; "
    "idempotent by provider event id; receipts are audited through the durable inbox.",
}

# path template -> concrete request, setup writes (as the demo administrator), principal and mode.
WRITES = {
    "/api/contracts/{cid}/confirm": dict(
        path="/api/contracts/psc_teacher/confirm", body={"action": "cancel"}, setup=[STAGE1]
    ),
    "/api/push/subscribe": dict(path="/api/push/subscribe", body=PUSH),
    "/api/push/unsubscribe": dict(path="/api/push/unsubscribe", body={"endpoint": PUSH["endpoint"]}),
    "/api/ingest/bee-simulated": dict(
        path="/api/ingest/bee-simulated",
        body={"event_id": "matrix", "utterance": "I'll call my sister before 6 PM.", "occurred_at": e.at("08:15")},
        admin=True,
    ),
    "/api/owner/promises": dict(path="/api/owner/promises", body={"utterance": "I'll water the plants at 7 PM."}),
    "/api/admin/scenarios/{stage}/run": dict(path=STAGE1[0], body=STAGE1[1], admin=True),
    "/api/admin/reset": dict(path="/api/admin/reset", body=None, admin=True, setup=[STAGE1]),
    "/api/admin/clock/advance": dict(path="/api/admin/clock/advance", body={"minutes": 1}, admin=True),
    "/api/admin/sister-proof": dict(path="/api/admin/sister-proof", body=None, admin=True, setup=[STAGE1]),
    "/api/admin/owner-pickup": dict(path="/api/admin/owner-pickup", body=None, admin=True, setup=[STAGE1, STAGE2]),
    "/api/consent": dict(path="/api/consent", body={"enabled": True}),
    "/api/incidents/{iid}/{action}": dict(
        path="/api/incidents/inc_parcel/prepare-report",
        body={"action": "prepare-report"},
        setup=[STAGE1, STAGE2, STAGE4],
    ),
    "/api/camera/start": dict(path="/api/camera/start", body={"device_id": "camera-1"}, live=True),
    "/api/camera/stop": dict(path="/api/camera/stop", body=None),
    "/api/studio/sessions": dict(path=STUDIO[0], body=None, setup=[STAGE1]),
    "/api/studio/recorded/start": dict(path="/api/studio/recorded/start", body={"fixture": "squats-15"}, setup=[STAGE1]),
    "/api/studio/recorded/stop": dict(path="/api/studio/recorded/stop", body=None),
    "/api/admin/studio/rep": dict(path="/api/admin/studio/rep", body=None, admin=True, setup=[STAGE1]),
    "/api/admin/studio/frame-step": dict(path="/api/admin/studio/frame-step", body=None, admin=True, setup=[STAGE1]),
    "/api/studio/control": dict(path="/api/studio/control", body={"action": "pause"}, setup=[STAGE1, STUDIO]),
    "/api/admin/studio/landmarks": dict(
        path="/api/admin/studio/landmarks",
        body={"frame_id": "matrix-frame", "timestamp_ms": 100, "landmarks": landmarks()},
        admin=True,
        setup=[STAGE1, STUDIO],
    ),
    "/api/admin/failures/{kind}": dict(path="/api/admin/failures/camera-offline", body=None, admin=True),
    "/api/tv/sessions": dict(path="/api/tv/sessions", body=None),
    "/api/privacy/cameras/exclusion": dict(
        path="/api/privacy/cameras/exclusion", body={"device_id": privacy.SYNTHETIC_CAMERA, "excluded": True}
    ),
    "/api/privacy/cameras/masks": dict(
        path="/api/privacy/cameras/masks",
        body={"device_id": privacy.SYNTHETIC_CAMERA, "polygons": [[[0.7, 0.0], [1.0, 0.0], [1.0, 0.3], [0.7, 0.3]]]},
    ),
    "/api/privacy/retention": dict(path="/api/privacy/retention", body={"days": 3}),
    "/api/privacy/providers/{provider}/{action}": dict(path="/api/privacy/providers/ring/disconnect", body=None),
    "/api/privacy/household/delete": dict(
        path="/api/privacy/household/delete",
        body={"household_id": "demo", "confirmation": privacy.DELETE_PHRASE},
        setup=[STAGE1],
    ),
}


def post_routes(app):
    return {
        route.path: route
        for route in app.routes
        if isinstance(route, APIRoute) and "POST" in route.methods
    }


def test_P0_004_every_post_route_is_classified(app):
    routes = set(post_routes(app))
    assert not set(WRITES) & set(EXEMPT)
    assert routes == set(WRITES) | set(EXEMPT), (
        "Unclassified POST routes: %s; stale entries: %s"
        % (sorted(routes - set(WRITES) - set(EXEMPT)), sorted((set(WRITES) | set(EXEMPT)) - routes))
    )


def ledger(store, household):
    with store.lock:
        commands = store.db.execute("SELECT COUNT(*) FROM commands WHERE household=?", (household,)).fetchone()[0]
        artifacts = store.db.execute("SELECT COUNT(*) FROM artifacts WHERE household=?", (household,)).fetchone()[0]
    return json.dumps(store.read(household), sort_keys=True), commands, artifacts


def event_keys(state):
    return {(v["event_id"], v["received_at"]) for v in state["events"]}


def live_app(tmp_path, monkeypatch):
    key = tmp_path / "ledger.key"
    key.write_bytes(bytes(range(32)))
    key.chmod(0o600)
    bindings = tmp_path / "bindings.json"
    bindings.write_text(json.dumps({"account-1": {"household": "house_owner", "devices": ["camera-1"]}}))
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("LEDGER_KEY_FILE", str(key))
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://testserver")
    monkeypatch.setenv("RING_BINDINGS_FILE", str(bindings))
    monkeypatch.delenv("BEE_TOKEN", raising=False)
    return create_app(tmp_path / "live", LIVE_PASSWORDS)


@pytest.mark.parametrize("template", sorted(WRITES))
def test_P0_004_write_is_authenticated_authorized_idempotent_validated_and_audited(
    template, tmp_path, monkeypatch
):
    spec = WRITES[template]
    live = spec.get("live", False)
    app = live_app(tmp_path, monkeypatch) if live else create_app(tmp_path / "demo", PASSWORDS)
    route = post_routes(app)[template]
    base = "https://testserver" if live else "http://testserver"
    body = spec["body"]
    household = "house_owner" if live else "demo"
    store = app.state.store

    async def fake_camera(household_id, device):  # no Ring account in tests: the external effect is stubbed
        return {"id": "matrix-camera", "status": "CONNECTING", "source_mode": "NOT_CONNECTED"}

    async def fake_recorded(household_id, fixture, session_id):
        return {"id": session_id, "status": "STREAMING", "label": "RECORDED DEMO"}

    app.state.camera.start = fake_camera
    app.state.recorded_demo.start = fake_recorded

    def send(c, payload=body, key="auto", path=spec["path"]):
        headers = {} if key is None else {"Idempotency-Key": uuid.uuid4().hex if key == "auto" else key}
        return c.post(path, json=payload if payload is not None else {}, headers=headers)

    with TestClient(app, base_url=base) as c:
        # Authenticated: no session -> 401 and nothing is written.
        anonymous = send(c)
        assert anonymous.status_code == 401, anonymous.text
        assert anonymous.json()["error"]["code"] == "AUTH_REQUIRED"

        if live:
            login = {"username": "owner", "password": LIVE_PASSWORDS["owner"]}
            assert c.post("/api/auth/login", json=login).status_code == 200
            for path, payload in [("/api/consent", {"enabled": True}),
                                  ("/api/owner/promises", {"utterance": "I'll do 15 squats before TV."})]:
                assert c.post(path, json=payload, headers={"Idempotency-Key": uuid.uuid4().hex}).status_code == 200
        else:
            if spec.get("admin"):
                # Authorized: an authenticated owner is not the isolated demo administrator.
                assert c.post("/api/auth/login", json={"username": "owner", "password": PASSWORDS["owner"]}).status_code == 200
                owner_before = ledger(store, "house_owner")
                denied = send(c)
                assert denied.status_code == 403, denied.text
                assert denied.json()["error"]["code"] == "ADMIN_REQUIRED"
                assert ledger(store, "house_owner") == owner_before
            assert c.post("/api/auth/login", json={"username": "demo-admin", "password": PASSWORDS["demo-admin"]}).status_code == 200
            for path, payload in spec.get("setup", []):
                r = c.post(path, json=payload, headers={"Idempotency-Key": uuid.uuid4().hex})
                assert r.status_code == 200, (path, r.text)

        before = ledger(store, household)

        # Idempotent: a write without an Idempotency-Key is refused before any reducer runs.
        missing = send(c, key=None)
        assert missing.status_code == 400, missing.text
        assert missing.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
        assert ledger(store, household) == before

        # Validated: strict models reject unknown fields with a generic 422 (no input echo).
        if route.body_field is not None:
            invalid = send(c, payload={**(body or {}), "unexpected_field": "do-not-echo"})
            assert invalid.status_code == 422, invalid.text
            assert invalid.json()["error"]["code"] == "VALIDATION_FAILED"
            assert "do-not-echo" not in invalid.text
            assert ledger(store, household) == before

        # Audited: the accepted write appends at least one new ledger event with a trace.
        key = "matrix-" + uuid.uuid4().hex
        old = store.read(household)
        accepted = send(c, key=key)
        assert accepted.status_code == 200, accepted.text
        after = store.read(household)
        new = [v for v in after["events"] if (v["event_id"], v["received_at"]) not in event_keys(old)]
        assert new, f"{template} wrote without an audit event"
        assert all(v["trace_id"] and v["household_id"] == household for v in new)
        with store.lock:
            assert store.db.execute(
                "SELECT 1 FROM commands WHERE household=? AND key=?", (household, key)
            ).fetchone()
        audited = [v for v in new if v["event_type"] == "command.audited"]
        for v in audited:  # generic records never carry the raw key or request body
            assert v["payload"]["idempotency_key_sha256"] == hashlib.sha256(key.encode()).hexdigest()
            assert key not in json.dumps(v)

        # Idempotent: replaying the same key does not reapply the command or add events.
        snapshot = ledger(store, household)
        replay = send(c, key=key)
        assert replay.status_code == 200, replay.text
        assert ledger(store, household)[0] == snapshot[0]
        if template not in {"/api/camera/start", "/api/camera/stop", "/api/studio/recorded/start",
                            "/api/studio/recorded/stop"}:
            assert replay.json() == accepted.json()
        # ...and reusing it for a different command is a conflict, not a silent overwrite.
        other_path, other_body = (
            ("/api/consent", {"enabled": True}) if template == "/api/tv/sessions" else ("/api/tv/sessions", {})
        )
        conflict = send(c, payload=other_body, key=key, path=other_path)
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
        assert ledger(store, household)[0] == snapshot[0]


def test_P0_004_exempt_routes_keep_their_replacement_contract(app, monkeypatch):
    with TestClient(app) as c:
        # logout needs the session it revokes
        assert c.post("/api/auth/logout", json={}).status_code == 401
        # login validates strictly and never echoes input
        bad = c.post("/api/auth/login", json={"username": "x", "password": "y", "extra": "do-not-echo"})
        assert bad.status_code == 422 and "do-not-echo" not in bad.text
        # webhook: unconfigured -> not connected; configured but forged -> 401, no state change
        assert c.post("/api/webhooks/ring", content=b"{}").status_code == 503
        monkeypatch.setenv("RING_HMAC_KEY", "matrix-secret")
        assert c.post("/api/webhooks/ring", content=b"{}", headers={"X-Signature": "sha256=forged"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "owner", "password": PASSWORDS["owner"]}).status_code == 200
        assert c.post("/api/auth/logout", json={}).status_code == 200
        assert c.post("/api/auth/logout", json={}).status_code == 401
        assert c.get("/api/state").status_code == 401


def test_P0_004_mcp_tool_writes_are_authenticated_idempotent_and_audited(app):
    with TestClient(app, base_url="http://127.0.0.1:8080") as c:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "evaluate_deadline_escalation",
                           "arguments": {"contract_id": "psc_teacher", "current_time": "x", "user_activity_state": "y"}}}
        accept = {"Accept": "application/json, text/event-stream"}
        assert c.post("/mcp/", json=body, headers=accept).status_code == 401
        r = c.post("/api/auth/login", json={"username": "demo-admin", "password": PASSWORDS["demo-admin"]})
        assert r.status_code == 200
        auth = {**accept, "Authorization": "Bearer " + c.cookies.get("done_session")}
        c.post(STAGE1[0], json=STAGE1[1], headers={"Idempotency-Key": "stage1"})
        before = c.get("/api/state").json()["state"]["events"]
        first = c.post("/mcp/", json=body, headers=auth).json()
        second = c.post("/mcp/", json=body, headers=auth).json()
        assert first["result"] == second["result"] and not first["result"].get("isError")
        events = c.get("/api/state").json()["state"]["events"]
        new = events[len(before):]
        assert [v["event_type"] for v in new] == ["command.audited"]
        assert new[0]["payload"]["channel"] == "MCP" and new[0]["payload"]["operation"] == "deadline"
        invalid = dict(body, params={"name": "evaluate_deadline_escalation", "arguments": {"contract_id": 5}})
        out = c.post("/mcp/", json=invalid, headers=auth).json()
        assert out["result"]["isError"] is True
        assert c.get("/api/state").json()["state"]["events"] == events


# ---------------------------------------------------------------------------------------------
# F19 Ring session expires / token expires
# ---------------------------------------------------------------------------------------------


class _Closable:
    def __init__(self, log, name, fail=False):
        self.log, self.name, self.fail = log, name, fail
        self.client = self

    async def close(self, *args):
        self.log.append((self.name, args))
        if self.fail:
            raise httpx.ConnectError("upstream unavailable")

    async def aclose(self):
        self.log.append((self.name + ".aclose", ()))


class _Detector:
    def __init__(self, log):
        self.log = log

    def close(self):
        self.log.append(("detector.close", ()))


def _live_studio(store, reps=3):
    state = e.fresh()
    state.update(household_id="house_owner", clock_mode="WALL", consent=True)
    e.create_contract(state, "squats", "15 squats", "I'll do 15 squats", "Self", "FIRE_TV_LIVE_POSE_CAMERA")
    e.studio_start(state, source="LIVE_RING_WHEP", source_mode="NOT_CONNECTED")
    state["studio"].update(camera_id="ring-session", timestamp_base=0, count=reps, status="RUNNING")
    state["camera_request"] = {"status": "OPEN"}
    with store.transaction() as db:
        store.save(db, "house_owner", state)


def _ring_session(log, fail_upstream=False, mains=False):
    return {
        "id": "ring-session",
        "device_id": "camera-1",
        "status": "STREAMING",
        "source": "LIVE_RING_WHEP",
        "source_mode": "LIVE_VERIFIED",
        "frames_decoded": 42,
        "model_sha256": "a" * 64,
        "jpeg": b"\xff\xd8last-frame",
        "landmarks": None,
        "started": time.monotonic(),
        "detector": _Detector(log),
        "adapter": _Closable(log, "whep", fail=fail_upstream),
        "pc": _Closable(log, "pc"),
        "location": "https://api.amazonvision.com/sessions/matrix",
        "max_seconds": 60 if mains else 30,
        "tracks": [],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_upstream", [False, True])
async def test_F19_ring_session_budget_expiry_records_gap_and_drops_live_label(tmp_path, fail_upstream):
    store = Store(str(tmp_path / "ledger.db"))
    _live_studio(store, reps=3)
    log = []
    bridge = CameraBridge(lambda *a: None, lambda *a: camera_ended(store, *a))
    bridge.sessions["house_owner"] = _ring_session(log, fail_upstream)
    assert bridge.status("house_owner")["source_mode"] == "LIVE_VERIFIED"

    await bridge.expire("house_owner", 0)  # the 30 s (battery) / 60 s (mains) budget elapsed

    reason = "SESSION_LIMIT_REACHED" + ("_UPSTREAM_CLEANUP_FAILED" if fail_upstream else "")
    # Bounded WHEP cleanup always runs and local resources are released even if upstream fails.
    assert ("whep", ("https://api.amazonvision.com/sessions/matrix",)) in log
    assert {"pc", "detector.close"} <= {name for name, _ in log}
    # Source status: no lingering LIVE label and no silent switch to a simulated/replay source.
    status = bridge.status("house_owner")
    assert status == {"status": "CLOSED", "source_mode": "NOT_CONNECTED"}
    state = store.read("house_owner")
    assert state["camera_request"]["status"] == "CLOSED"
    assert state["studio"]["status"] == "PAUSED" and state["studio"]["quality"] == reason
    assert state["studio"]["gate"] == "LOCKED" and state["studio"]["count"] == 3
    assert state["studio"]["source"] == "LIVE_RING_WHEP"  # never relabelled as replay/simulation
    gap = state["events"][-1]
    assert gap["event_type"] == "watchdog.monitoring_gap"
    assert gap["payload"]["reason"] == reason and gap["payload"]["camera_session_id"] == "ring-session"
    assert e.contract(state, "squats")["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_F19_ring_session_budget_is_30s_battery_and_60s_mains():
    def handler(request):
        return httpx.Response(201, headers={"Location": "https://api.amazonvision.com/sessions/x"}, text="v=0\r\n")

    adapter = RingAdapter("test", httpx.MockTransport(handler))
    assert (await adapter.whep("d", "v=0\r\n", battery=True))["max_seconds"] == 30
    assert (await adapter.whep("d", "v=0\r\n", battery=False))["max_seconds"] == 60
    await adapter.client.aclose()


def test_F19_token_expiry_shows_gap_fallback_label_and_recovers_without_reset(client, post):
    post("/admin/scenarios/1/run")
    post("/studio/sessions")
    for _ in range(3):
        post("/admin/studio/rep")
    s = post("/admin/failures/token-expired")["state"]
    gap = s["events"][-1]
    assert gap["event_type"] == "watchdog.monitoring_gap"
    assert gap["payload"] == {"reason": "token-expired", "source": "EXPLICIT_SIMULATED_FAILURE"}
    assert s["studio"]["status"] == "PAUSED" and s["studio"]["quality"] == "CAMERA_UNAVAILABLE"
    assert s["studio"]["gate"] == "LOCKED" and s["studio"]["count"] == 3
    # Fallback label stays explicit: synthetic source, never promoted to live.
    assert s["studio"]["source"] == "SYNTHETIC_MARKER_FRAMES" and s["studio"]["source_mode"] == e.MODE != "LIVE_VERIFIED"
    statuses = {i["name"]: i for i in client.get("/api/integrations/status").json()["integrations"]}
    assert statuses["Ring"]["status"] == "BLOCKED" and statuses["Ring"]["last_verified_at"] is None
    assert statuses["Ring video"]["status"] == "NOT_CONNECTED"
    post("/admin/studio/frame-step", status=503)
    assert client.get("/api/state").json()["state"]["studio"]["count"] == 3
    # Recovery: clearing the fault and resuming continues the same count (no reset, no duplicates).
    post("/admin/failures/clear")
    post("/studio/control", {"action": "resume"})
    s = post("/admin/studio/rep")["state"]
    assert s["studio"]["count"] == 4 and s["studio"]["status"] == "RUNNING"
    assert len([v for v in s["events"] if v["event_type"] == "studio.rep_verified"]) == 4


@pytest.mark.asyncio
async def test_F19_ring_access_token_expiry_is_rejected_not_live():
    adapter = RingAdapter("expired-token", httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(ApiError) as error:
        await adapter.whep("d", "v=0\r\n")
    assert error.value.code in {"RING_ACCESS_REJECTED", "WHEP_REJECTED"} and "expired-token" not in error.value.message
    await adapter.client.aclose()


def test_F19_expired_owner_session_token_is_refused(app, client):
    with app.state.store.transaction() as db:
        db.execute("UPDATE sessions SET expires=?", (time.time() - 1,))
    r = client.get("/api/state")
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_EXPIRED"


# ---------------------------------------------------------------------------------------------
# F20 restart midway through watchdog / scheduler
# ---------------------------------------------------------------------------------------------


def _admin(c):
    assert c.post("/api/auth/login", json={"username": "demo-admin", "password": PASSWORDS["demo-admin"]}).status_code == 200

    def call(path, body=None, key=None, status=200):
        r = c.post("/api" + path, json=body or {}, headers={"Idempotency-Key": key or uuid.uuid4().hex})
        assert r.status_code == status, r.text
        return r.json()

    return call


def _minutes_until(state, hm):
    return round((datetime.fromisoformat(e.at(hm)) - datetime.fromisoformat(state["now"])).total_seconds() / 60)


def test_F20_full_service_restart_mid_watchdog_and_scheduler_recovers_without_duplicates(tmp_path):
    data = tmp_path / "data"
    with TestClient(create_app(data, PASSWORDS)) as c:
        call = _admin(c)
        call("/admin/scenarios/1/run")
        s = call("/admin/scenarios/2/run")["state"]
        advance = {"minutes": _minutes_until(s, "15:00")}
        first = call("/admin/clock/advance", advance, key="advance-to-1500")
        s = first["state"]
        teacher = [a for a in s["alerts"] if a["contract_id"] == "psc_teacher"]
        assert [a["kind"] for a in teacher] == ["SILENT_PREP"]
        before = {k: s[k] for k in ("contracts", "subagents", "alerts", "incidents", "now")}
    # Process killed between the T-60 and T-25 jobs, with an active PorchWatchdog.
    with TestClient(create_app(data, PASSWORDS)) as c:
        call = _admin(c)
        s = c.get("/api/state").json()["state"]
        assert {k: s[k] for k in before} == before  # PSCs, watchdog, schedule and alerts persisted
        watchdogs = [a for a in s["subagents"] if a["kind"] == "PorchWatchdog"]
        assert len(watchdogs) == 1 and watchdogs[0]["status"] == "WATCHING"
        jobs = {j["kind"]: j["status"] for j in e.contract(s, "teacher")["scheduled_jobs"]}
        assert jobs["T60"] == "EXECUTED" and jobs["T25"] == "PENDING"
        # A client retry of the pre-crash command returns the stored response; nothing re-fires.
        assert call("/admin/clock/advance", advance, key="advance-to-1500") == first
        s = call("/admin/clock/advance", {"minutes": 1})["state"]
        assert len(s["alerts"]) == len(before["alerts"])
        s = call("/admin/clock/advance", {"minutes": _minutes_until(s, "15:35")})["state"]
        teacher = [a for a in s["alerts"] if a["contract_id"] == "psc_teacher"]
        assert [(a["kind"], a["at"]) for a in teacher] == [
            ("SILENT_PREP", e.at("15:00")),
            ("ACTIVE_ESCALATION", e.at("15:35")),
        ]
        s = call("/admin/clock/advance", {"minutes": 1})["state"]
        assert len([a for a in s["alerts"] if a["contract_id"] == "psc_teacher"]) == 2
        # The recovered watchdog still guards custody: one removal -> one incident.
        s = call("/admin/scenarios/4/run", {"branch": "unknown"})["state"]
        assert len(s["incidents"]) == 1
        assert len([a for a in s["alerts"] if a["kind"] == "PORCH_REMOVAL"]) == 1


def test_F20_restart_during_open_camera_session_records_gap_and_keeps_count(tmp_path):
    data = tmp_path / "data"
    with TestClient(create_app(data, PASSWORDS)) as c:
        call = _admin(c)
        call("/admin/scenarios/1/run")
        call("/studio/sessions")
        call("/admin/studio/rep")
        call("/admin/studio/rep")
        app_store = c.app.state.store
        with app_store.transaction() as db:
            s = app_store.read("demo")
            s["camera_request"] = {"status": "OPEN", "id": "pre-crash"}
            app_store.save(db, "demo", s)
    with TestClient(create_app(data, PASSWORDS)) as c:
        _admin(c)
        s = c.get("/api/state").json()["state"]
        assert s["camera_request"]["status"] == "CLOSED"
        assert s["studio"]["status"] == "PAUSED" and s["studio"]["quality"] == "PROCESS_RESTART_GAP"
        assert s["studio"]["count"] == 2 and s["studio"]["gate"] == "LOCKED"
        gaps = [v for v in s["events"] if v["event_type"] == "watchdog.monitoring_gap"]
        assert gaps[-1]["payload"] == {"reason": "PROCESS_RESTART_GAP"}


# ---------------------------------------------------------------------------------------------
# F21 duplicate removal delivery
# ---------------------------------------------------------------------------------------------


def test_F21_duplicate_removal_and_duplicate_provider_event_produce_one_of_each(post, client, tmp_path):
    post("/admin/scenarios/2/run", {"branch": "deposit"})
    s = post("/admin/scenarios/4/run", {"branch": "unknown"})["state"]
    post("/admin/scenarios/4/run", {"branch": "unknown"}, status=409)
    s = client.get("/api/state").json()["state"]
    assert len(s["incidents"]) == 1
    assert len([a for a in s["alerts"] if a["kind"] == "PORCH_REMOVAL"]) == 1
    assert len([v for v in s["events"] if v["event_type"] == "parcel.removal_observed"]) == 1
    # Provider level: the same Ring event delivered twice is reduced once (the signed HTTP path is
    # test_runtime.py::test_configured_live_webhook_persists_receipt_without_claiming_video).
    store = Store(str(tmp_path / "ring.db"))
    state = e.fresh()
    state.update(household_id="house_owner", clock_mode="WALL", consent=True)
    with store.transaction() as db:
        store.save(db, "house_owner", state)
    runtime = Runtime(store)
    payload = {"meta": {"request_id": "r-1", "account_id": "a"},
               "data": {"id": "removal-1", "type": "motion_detected",
                        "attributes": {"source": "camera-1", "timestamp": 1_792_000_000_000}}}
    assert runtime.enqueue("house_owner", "ring", "r-1", payload)[1] is True
    assert runtime.enqueue("house_owner", "ring", "r-1", payload)[1] is False
    runtime.step()
    runtime.step()
    events = [v for v in store.read("house_owner")["events"] if v["event_type"] == "ring.motion_detected"]
    assert len(events) == 1


# ---------------------------------------------------------------------------------------------
# F22 household isolation (writes as well as reads)
# ---------------------------------------------------------------------------------------------


def test_F22_other_household_cannot_read_or_act_on_incident_media(app, client, post):
    post("/admin/scenarios/2/run", {"branch": "deposit"})
    s = post("/admin/scenarios/4/run", {"branch": "unknown"})["state"]
    media = [v["evidence_id"] for v in s["evidence"]]
    incident = s["incidents"][0]
    assert client.post("/api/auth/login", json={"username": "other", "password": PASSWORDS["other"]}).status_code == 200
    for eid in media:
        r = client.get("/api/evidence/" + eid)
        assert r.status_code == 404 and incident["incident_id"] not in r.text
    for action in ("prepare-report", "authorize-pickup", "dispatch-report"):
        r = client.post(f"/api/incidents/{incident['incident_id']}/{action}", json={"action": action},
                        headers={"Idempotency-Key": uuid.uuid4().hex})
        assert r.status_code == 404, r.text
    export = client.get("/api/export").json()
    assert export["state"]["incidents"] == [] and export["state"]["evidence"] == []
    assert incident["manifest_hash"] not in json.dumps(export)
    demo = app.state.store.read("demo")["incidents"][0]
    assert demo["status"] == "AWAITING_HUMAN_DECISION" and demo["revision"] == incident["revision"]


# ---------------------------------------------------------------------------------------------
# F23 unauthorized official dispatch: denied, zero outbound network calls
# ---------------------------------------------------------------------------------------------


def test_F23_unauthorized_dispatch_attempts_make_no_outbound_request(app, monkeypatch):
    outbound = []

    def no_network(self, request, *args, **kwargs):
        outbound.append(str(request.url))
        raise AssertionError("outbound network call during dispatch: " + str(request.url))

    async def no_network_async(self, request, *args, **kwargs):
        outbound.append(str(request.url))
        raise AssertionError("outbound network call during dispatch: " + str(request.url))

    with TestClient(app, base_url="http://127.0.0.1:8080") as c:
        call = _admin(c)
        call("/admin/scenarios/2/run")
        call("/admin/scenarios/4/run", {"branch": "unknown"})
        auth = {"Accept": "application/json, text/event-stream",
                "Authorization": "Bearer " + c.cookies.get("done_session")}
        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network_async)
        # 1. Direct dispatch with no owner approval.
        r = c.post("/api/incidents/inc_parcel/dispatch-report", json={"action": "dispatch-report"},
                   headers={"Idempotency-Key": uuid.uuid4().hex})
        assert r.status_code == 403 and r.json()["error"]["code"] == "OWNER_APPROVAL_REQUIRED"
        # 2. A model-supplied boolean is not a field the API accepts.
        r = c.post("/api/incidents/inc_parcel/dispatch-report",
                   json={"action": "dispatch-report", "human_confirmed_boolean": True},
                   headers={"Idempotency-Key": uuid.uuid4().hex})
        assert r.status_code == 422
        # 3. The MCP tool, even with human_confirmed_boolean=True.
        rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "dispatch_police_evidence_dossier",
                          "arguments": {"incident_id": "inc_parcel", "human_confirmed_boolean": True}}}
        out = c.post("/mcp/", json=rpc, headers=auth).json()["result"]
        denied = out.get("structuredContent") or json.loads(out["content"][0]["text"])
        assert denied["status"] == "DENIED" and denied["external_sends"] == 0
        s = c.get("/api/state").json()["state"]
        inc = s["incidents"][0]
        assert inc["status"] == "AWAITING_HUMAN_DECISION" and inc["receipt"] is None and inc["approval"] is None
        assert not any(v["event_type"] == "incident.dispatch_acknowledged" for v in s["events"])
        # Even the fully approved path only reaches the labelled demo receiver, offline.
        inc_hash = inc["manifest_hash"]
        call("/incidents/inc_parcel/prepare-report", {"action": "prepare-report"})
        call("/incidents/inc_parcel/approve-report", {"action": "approve-report", "manifest_hash": inc_hash,
                                                      "destination": "DEMO_RECEIVER_ONLY",
                                                      "confirmation": "APPROVE REPORT"})
        s = call("/incidents/inc_parcel/dispatch-report", {"action": "dispatch-report"})["state"]
        receipt = s["incidents"][0]["receipt"]
        assert receipt["official_case_id"] is None and "NOT SENT TO POLICE" in receipt["label"]
    assert outbound == []


# ---------------------------------------------------------------------------------------------
# P0-007 lifecycle and P0-045 degraded paths
# ---------------------------------------------------------------------------------------------


def test_P0_007_startup_failure_recovery_and_teardown(tmp_path):
    app = create_app(tmp_path / "data", PASSWORDS)
    runtime_step = app.state.runtime.step
    log = []
    with TestClient(app) as c:
        # Startup: liveness immediately, readiness once the durable worker is running.
        assert c.get("/health/live").status_code == 200
        for _ in range(50):
            if getattr(app.state, "worker_status", None) == "RUNNING":
                break
            time.sleep(0.1)
        ready = c.get("/health/ready")
        assert ready.status_code == 200 and ready.json()["worker"] == "RUNNING"

        # Failure: a crashing worker turns readiness red instead of pretending to be healthy.
        def broken():
            raise RuntimeError("simulated worker crash")

        app.state.runtime.step = broken
        for _ in range(50):
            if app.state.worker_status == "DEGRADED":
                break
            time.sleep(0.1)
        degraded = c.get("/health/ready")
        assert degraded.status_code == 503 and degraded.json()["error"]["code"] == "WORKER_NOT_READY"
        assert degraded.json()["error"]["retryable"] is True

        # Recovery: the next successful loop restores readiness without a restart.
        app.state.runtime.step = runtime_step
        for _ in range(50):
            if app.state.worker_status == "RUNNING":
                break
            time.sleep(0.1)
        assert c.get("/health/ready").status_code == 200

        # A live camera session is open when the service is torn down.
        app.state.camera.sessions["demo"] = _ring_session(log)
    # Teardown: lifespan exit closes WHEP upstream, peer connection and detector, and stops Bee.
    assert app.state.camera.sessions == {}
    assert ("whep", ("https://api.amazonvision.com/sessions/matrix",)) in log
    assert {"pc", "detector.close"} <= {name for name, _ in log}
    assert app.state.bee.stopped is True


@pytest.mark.asyncio
async def test_P0_007_P0_045_bee_stream_failure_backs_off_then_reconnects_with_cursor(monkeypatch):
    from done_irl import adapters

    calls, delays, seen = [], [], []
    stream = ('id: 77\nevent: new-utterance\ndata: {"conversation_uuid":"c","utterance":'
              '{"id":1,"text":"I will call my sister at 6 pm","speaker":"me","spoken_at":1792488600000}}\n\n')

    def handler(request):
        calls.append(dict(request.headers))
        if "/todos" in request.url.path:
            return httpx.Response(503)
        if len(calls) <= 3:
            return httpx.Response(503)  # provider outage / expired session upstream
        return httpx.Response(200, text=stream, headers={"Content-Type": "text/event-stream"})

    adapter = BeeAdapter("bee-secret-token", httpx.MockTransport(handler))

    async def fast_sleep(seconds):
        delays.append(seconds)
        if len(seen) >= 1 or len(delays) > 8:
            adapter.stopped = True

    monkeypatch.setattr(adapters.asyncio, "sleep", fast_sleep)

    async def handle(body, event_id):
        seen.append((event_id, body["utterance"]))

    adapter.cursor = "41"
    await adapter.run(handle)
    # Failures were recorded (redacted), retried with exponential backoff, nothing fabricated.
    assert delays[:2] == [1, 2]
    assert seen == [("bee:utt:c:1", "I will call my sister at 6 pm")]
    assert adapter.cursor == "77" and adapter.last_connected_at
    assert "bee-secret-token" not in str(adapter.last_error)
    # Reconnect resumes from the persisted cursor rather than replaying from the beginning.
    assert any(h.get("last-event-id") == "41" for h in calls)
    await adapter.client.aclose()


def test_P0_045_storage_failure_mid_write_rolls_back_and_reports_retryable(app, client, post):
    post("/admin/scenarios/1/run")
    before = client.get("/api/state").json()["state"]
    store = app.state.store
    original = store.save

    def failing_save(*args, **kwargs):
        raise OSError("disk full")

    store.save = failing_save
    try:
        with pytest.raises(OSError):
            client.post("/api/admin/scenarios/2/run", json={"branch": "deposit"},
                        headers={"Idempotency-Key": "during-outage"})
    finally:
        store.save = original
    assert client.get("/api/state").json()["state"] == before
    with store.lock:
        assert not store.db.execute("SELECT 1 FROM commands WHERE key='during-outage'").fetchone()
        assert not store.db.execute("SELECT 1 FROM artifacts WHERE household='demo'").fetchone()
    # The same key succeeds once storage is back: no half-applied command was cached.
    r = client.post("/api/admin/scenarios/2/run", json={"branch": "deposit"},
                    headers={"Idempotency-Key": "during-outage"})
    assert r.status_code == 200 and len(r.json()["state"]["evidence"]) >= 1


def test_P0_045_unauthorized_and_cross_household_webhooks_change_nothing(tmp_path, monkeypatch):
    app = live_app(tmp_path, monkeypatch)
    monkeypatch.setenv("RING_HMAC_KEY", "private-test-key")
    with TestClient(app, base_url="https://testserver") as c:
        assert c.post("/api/auth/login", json={"username": "owner", "password": LIVE_PASSWORDS["owner"]}).status_code == 200
        c.post("/api/consent", json={"enabled": True}, headers={"Idempotency-Key": "consent"})
        before = ledger(app.state.store, "house_owner")
        payload = {"meta": {"version": "1.1", "time": "2026-10-20T07:00:00Z", "request_id": "x",
                            "account_id": "account-1"},
                   "data": {"id": "m", "type": "motion_detected",
                            "attributes": {"source": "camera-9", "timestamp": 1_792_000_000_000}}}
        body = json.dumps(payload).encode()
        good = "sha256=" + hmac.new(b"private-test-key", body, hashlib.sha256).hexdigest()
        assert c.post("/api/webhooks/ring", content=body, headers={"X-Signature": "sha256=" + "0" * 64}).status_code == 401
        unknown_device = c.post("/api/webhooks/ring", content=body, headers={"X-Signature": good})
        assert unknown_device.status_code in {401, 403}
        assert ledger(app.state.store, "house_owner") == before
        with app.state.store.lock:
            assert not app.state.store.db.execute("SELECT 1 FROM inbox").fetchone()


# ---------------------------------------------------------------------------------------------
# Golden assertions the original scenario tests did not state explicitly (F01, F04-F07, F13-F16)
# ---------------------------------------------------------------------------------------------


def test_F01_golden_actors_types_deadlines_modalities_and_zero_verified(post):
    s = post("/admin/scenarios/1/run")["state"]
    golden = {
        "teacher": ("Nephew’s teacher", "SCHEDULED_SOCIAL_COMMITMENT", "BEE_CONVERSATION_AUDIT", e.at("16:00"), None),
        "sister": ("Sister", "SCHEDULED_SOCIAL_COMMITMENT", "BEE_CONVERSATION_AUDIT", e.at("18:00"), None),
        "drinks": ("Wife", "INBOUND_ITEM", "RING_THRESHOLD_OBJECT_SCAN", None, "ARRIVAL_HOME"),
        "squats": ("Self", "PHYSICAL_ACTION", "FIRE_TV_LIVE_POSE_CAMERA", None, "BEFORE_ENTERTAINMENT"),
    }
    assert len({c["contract_id"] for c in s["contracts"]}) == 4
    for c in s["contracts"]:
        counterparty, kind, modality, due, trigger = golden[c["key"]]
        assert c["actor"]["role"] == "SELF" and c["counterparty"]["label"] == counterparty
        assert (c["type"], c["verification_modality"], c["due_at"], c["deadline_trigger"]) == (
            kind, modality, due, trigger
        )
        assert c["required_evidence"] == [modality] and c["evidence_ids"] == []
    assert not any(c["status"] == "VERIFIED" for c in s["contracts"])
    assert s["evidence"] == []


def test_F04_F05_F07_alert_times_actions_and_no_premature_verification(post):
    post("/admin/scenarios/1/run")
    s = post("/admin/scenarios/3/run", {"branch": "disengaged"})["state"]
    teacher = [a for a in s["alerts"] if a["contract_id"] == "psc_teacher"]
    assert [(a["kind"], a["at"]) for a in teacher] == [("SILENT_PREP", e.at("15:00")), ("ACTIVE_ESCALATION", e.at("15:35"))]
    assert all(a["action"] == "/?contract=psc_teacher" for a in teacher)  # actionable bridge to the PSC
    verified = [v for v in s["events"] if v["event_type"] == "commitment.verified"
                and v["payload"]["contract_id"] == "psc_teacher"]
    assert [v["occurred_at"] for v in verified] == [e.at("16:05")]
    # F07: separate sister T-60/T-25 at 17:00/17:35, never merged with the teacher schedule.
    s = post("/admin/clock/advance", {"minutes": _minutes_until(s, "17:00")})["state"]
    s = post("/admin/clock/advance", {"minutes": _minutes_until(s, "17:35")})["state"]
    sister = [a for a in s["alerts"] if a["contract_id"] == "psc_sister"]
    assert [(a["kind"], a["at"]) for a in sister] == [("SILENT_PREP", e.at("17:00")), ("ACTIVE_ESCALATION", e.at("17:35"))]
    assert len([a for a in s["alerts"] if a["contract_id"] == "psc_teacher"]) == 2
    assert e.contract(s, "sister")["status"] == "ACTIVE"


def test_F05_engaged_branch_never_verifies_before_attendance_evidence(post):
    post("/admin/scenarios/1/run")
    s = post("/admin/scenarios/3/run", {"branch": "engaged"})["state"]
    assert not [a for a in s["alerts"] if a["kind"] == "ACTIVE_ESCALATION"]
    quiet = [v for v in s["events"] if v["payload"].get("decision") == "QUIET_ON_TRACK"]
    assert [v["occurred_at"] for v in quiet] == [e.at("15:35")]
    verified = [v for v in s["events"] if v["event_type"] == "commitment.verified"]
    assert [v["occurred_at"] for v in verified] == [e.at("16:05")]


@pytest.mark.parametrize(
    "branch,visibility,observation,alerts",
    [("empty", "NOT_VISIBLE", "NEEDS_USER_CHECK", 1), ("visible", "VISIBLE_MATCH", "SUPPORTING_OBSERVATION", 0),
     ("ambiguous", "AMBIGUOUS", "NEEDS_USER_CHECK", 1)],
)
def test_F13_F14_F15_threshold_golden(post, branch, visibility, observation, alerts):
    post("/admin/scenarios/1/run")
    s = post("/admin/scenarios/5/run", {"branch": branch})["state"]
    c = e.contract(s, "drinks")
    assert (c["visibility"], c["observation_status"]) == (visibility, observation)
    # User-intent policy: a camera view never verifies or fails the promise; only the owner closes it.
    assert c["status"] == "ACTIVE"
    arrival = [a for a in s["alerts"] if a["kind"] == "ARRIVAL_ITEM_CHECK"]
    assert len(arrival) == alerts
    for a in arrival:  # private, owner-only companion delivery; no definitive "you forgot" claim
        assert a["provider"] == "AUTHENTICATED_COMPANION" and a["device_delivery_verified"] is False
        assert "forgot" not in a["message"].lower() and "weren't visible" in a["message"]
    assert len([v for v in s["evidence"] if v["kind"] == "THRESHOLD_OBSERVATION"]) == 1


def test_F16_owner_pickup_verifies_custody_and_terminates_watchdog(post):
    post("/admin/scenarios/2/run")
    post("/admin/scenarios/4/run", {"branch": "retained"})
    s = post("/admin/owner-pickup")["state"]
    parcel = e.contract(s, "parcel")
    assert parcel["status"] == "VERIFIED" and parcel["custody_status"] == "VERIFIED_SAFE_TRANSFER"
    assert [a["status"] for a in s["subagents"] if a["kind"] == "PorchWatchdog"] == ["CLOSED"]
    assert not s["incidents"]


# ---------------------------------------------------------------------------------------------
# P0-054: the acceptance documents cannot drift from the manifest
# ---------------------------------------------------------------------------------------------

