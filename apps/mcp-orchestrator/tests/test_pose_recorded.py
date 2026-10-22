"""P0-039 / F17 / F18: real MediaPipe pose inference on the committed RECORDED WORKOUT fixtures.

The fixtures are generated humanoid videos (scripts/generate-squats.py).
These tests decode the video pixels, run the SHA-pinned MediaPipe Pose Landmarker model and
feed the same reducer used by live Ring frames. No landmarks or counts are injected.

The model is fetched exactly like scripts/fetch-pose-model.py (official URL, pinned SHA-256,
size-limited) into ignored artifacts/vision/. If mediapipe cannot load or the model cannot be
fetched (offline sandbox), these tests skip with the reason instead of passing silently.
"""

import hashlib
import json
import time

import pytest

from done_irl import engine as e, recorded
from done_irl.camera_reducers import frame_received
from done_irl.store import Store

HOUSE = "house_owner"


@pytest.fixture(scope="module")
def detector_factory():
    try:
        import mediapipe  # noqa: F401
    except (ImportError, OSError) as error:
        pytest.skip(f"MediaPipe runtime unavailable ({type(error).__name__}); install the ring-video extra")
    path, sha = recorded.pose_model_location()
    if path == str(recorded.DEFAULT_POSE_MODEL):
        try:
            recorded.fetch_pose_model()
        except Exception as error:  # network-restricted sandboxes only
            pytest.skip(f"Pinned pose model could not be fetched ({type(error).__name__})")
    from done_irl.camera import PoseDetector

    return lambda: PoseDetector(path, sha)


@pytest.fixture(scope="module")
def full_frames():
    return [(ts, frame) for _, ts, frame in recorded.decode(recorded.fixture_path("squats-15"))]


@pytest.fixture(scope="module")
def plan():
    return json.loads((recorded.FIXTURE_DIR / "squats-15-generated.plan.json").read_text())["reps"]


def ledger(tmp_path, model_hash):
    store = Store(str(tmp_path / "ledger.db"))
    state = e.fresh()
    state.update(household_id=HOUSE, consent=True)
    e.create_contract(state, "squats", "15 squats", "I'll do 15 squats", "Self", "FIRE_TV_LIVE_POSE_CAMERA")
    recorded.open_studio(state, "recorded_test", "squats-15", model_hash)
    with store.transaction() as db:
        store.save(db, HOUSE, state)
    camera = {"id": "recorded_test", "model_sha256": model_hash, "source": recorded.SOURCE}
    return store, camera


def replay(tmp_path, detector_factory, frames):
    detector = detector_factory()
    try:
        store, camera = ledger(tmp_path, detector.model_hash)
        on_frame = lambda *args: frame_received(store, HOUSE, *args)  # noqa: E731
        observations = [
            (o["studio"]["count"], o["studio"]["gate"], o["points"] is not None)
            for o in recorded.replay(frames, detector, on_frame, camera)
        ]
    finally:
        detector.close()
    return store.read(HOUSE), observations


def rep_events(state):
    return [x for x in state["events"] if x["event_type"] == "studio.rep_verified"]


def test_fixtures_are_pinned_small_and_labelled_scripted():
    manifest = json.loads((recorded.REPO_ROOT / "packages/testing-fixtures/manifest.json").read_text())
    pose = {f["id"]: f for f in manifest["pose_video_fixtures"]}
    for name, (filename, sha) in recorded.FIXTURES.items():
        data = (recorded.FIXTURE_DIR / filename).read_bytes()
        assert hashlib.sha256(data).hexdigest() == sha
        assert len(data) < 10 * 1024 * 1024
        assert pose[name]["sha256"] == sha and pose[name]["provenance"] == "SCRIPTED"
    with pytest.raises(Exception):
        recorded.fixture_path("../../etc/passwd")


def test_F18_truncated_to_14_reps_stays_locked(tmp_path, detector_factory, full_frames, plan):
    cut = plan[14]["start_frame"]  # from the generator plan, never from pose output
    state, observations = replay(tmp_path, detector_factory, full_frames[:cut])
    assert sum(seen for *_, seen in observations) > 0.95 * len(observations)  # real landmarks found
    assert len(rep_events(state)) == 14
    assert state["studio"]["count"] == 14 and state["studio"]["gate"] == "LOCKED"
    assert e.contract(state, "squats")["status"] == "ACTIVE"
    assert not [x for x in state["evidence"] if x["kind"] == "POSE_15_CYCLES"]


def test_F18_half_squats_count_zero(tmp_path, detector_factory):
    frames = ((ts, f) for _, ts, f in recorded.decode(recorded.fixture_path("squats-half-15")))
    state, observations = replay(tmp_path, detector_factory, frames)
    assert sum(seen for *_, seen in observations) > 0.95 * len(observations)
    assert rep_events(state) == [] and state["studio"]["count"] == 0
    assert state["studio"]["gate"] == "LOCKED"


def test_F18_frozen_frames_and_looped_rep_cannot_add_reps(tmp_path, detector_factory, full_frames, plan):
    step = full_frames[1][0]
    stand, bottom = full_frames[0][1], full_frames[plan[0]["bottom_frame"]][1]
    frozen = [stand] * 15 + [bottom] * 30 + [stand] * 30
    state, _ = replay(tmp_path / "frozen", detector_factory, [(i * step, f) for i, f in enumerate(frozen)])
    assert rep_events(state) == [] and state["studio"]["count"] == 0
    # Standing lead-in, then one physically complete rep looped 15 times on a monotonic clock.
    # The first pass is pixel-identical to the canonical opening rep; the 14 replays must not count.
    lead = [f for _, f in full_frames[: plan[0]["start_frame"]]]
    first = [f for _, f in full_frames[plan[0]["start_frame"] : plan[0]["end_frame"] + 1]]
    looped = [(i * step, f) for i, f in enumerate(lead + first * 15)]
    state, observations = replay(tmp_path / "loop", detector_factory, looped)
    assert len(rep_events(state)) == 1 and state["studio"]["count"] == 1
    assert observations[len(lead) + len(first) - 1][0] == 1  # the single count came from the first pass
    assert state["studio"]["gate"] == "LOCKED"
    assert e.contract(state, "squats")["status"] == "ACTIVE"


def test_F17_recorded_workout_api_streams_15_reps_and_unlocks_after_15th(app, client, post, detector_factory):
    app.state.recorded_workout.realtime = False
    app.state.recorded_workout.detector_factory = detector_factory
    post("/admin/scenarios/1/run", {"branch": "deposit"})
    started = post("/studio/recorded/start", {"fixture": "squats-15"})
    assert started["label"] == "RECORDED WORKOUT" and started["source"] == "RECORDED_WORKOUT_VIDEO"
    deadline = time.monotonic() + 300
    while client.get("/api/studio/recorded/status").json()["status"] != "ENDED":
        assert time.monotonic() < deadline, "recorded workout did not finish"
        time.sleep(0.5)
    status = client.get("/api/studio/recorded/status").json()
    assert status["end_reason"] == "COMPLETED"
    assert status["frames_decoded"] > 700 and status["frames_with_pose"] > 0.95 * status["frames_decoded"]
    frame = client.get("/api/studio/recorded/frame")
    assert frame.status_code == 200 and frame.content.startswith(b"\xff\xd8")
    s = client.get("/api/state").json()["state"]
    reps = rep_events(s)
    assert [r["payload"]["count"] for r in reps] == list(range(1, 16))
    assert s["studio"]["count"] == 15 and s["studio"]["gate"] == "UNLOCKED"
    assert (
        s["studio"]["source"] == "RECORDED_WORKOUT_VIDEO" and s["studio"]["source_mode"] == "REPLAY_VERIFIED"
    )
    assert all(
        r["source"] == "RECORDED_WORKOUT_VIDEO" and r["source_mode"] == "REPLAY_VERIFIED" for r in reps
    )
    assert e.contract(s, "squats")["status"] == "VERIFIED"
    order = [x["event_type"] for x in s["events"]]
    unlock = order.index("studio.reality_lock_unlocked")
    assert order.index("commitment.verified", order.index("studio.recorded_workout_opened")) < unlock
    assert max(i for i, t in enumerate(order) if t == "studio.rep_verified") < unlock
    proof = [x for x in s["evidence"] if x["kind"] == "POSE_15_CYCLES"]
    assert len(proof) == 1 and proof[0]["provenance"] == "RECORDED_WORKOUT"
    assert proof[0]["source_platform"] == "RECORDED_WORKOUT_VIDEO"
    assert "LIVE" not in json.dumps(proof[0])
    body = json.loads(app.state.store.uow.get_artifact(proof[0]["evidence_id"], "guided")["data"])
    assert body["label"] == "RECORDED WORKOUT" and len(body["verified_reps"]) == 15
    assert len({r["frame_sha256"] for r in body["verified_reps"]}) == 15


def test_recorded_workout_is_refused_outside_guided_and_never_labelled_live(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from done_irl.api import create_app

    key = tmp_path / "ledger.key"
    key.write_bytes(b"k" * 32)
    key.chmod(0o600)  # POSIX ledger-key permission check
    monkeypatch.setenv("GUIDED_MODE", "false")
    monkeypatch.setenv("LEDGER_KEY_FILE", str(key))
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://example.test")
    try:
        app = create_app(tmp_path / "data", {"owner": "owner-password-long-enough"})
    except RuntimeError as error:  # live certification guards differ by deployment
        pytest.skip(str(error))
    with TestClient(app, base_url="https://testserver") as c:
        c.post("/api/auth/login", json={"username": "owner", "password": "owner-password-long-enough"})
        r = c.post("/api/studio/recorded/start", json={}, headers={"Idempotency-Key": "k1"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "LIVE_DEPLOYMENT"
    assert recorded.LABEL == "RECORDED WORKOUT" and "LIVE" not in recorded.SOURCE


def test_recorded_workout_stop_pauses_without_unlock(app, client, post, detector_factory):
    app.state.recorded_workout.detector_factory = detector_factory  # realtime pacing kept
    post("/admin/scenarios/1/run", {"branch": "deposit"})
    post("/studio/recorded/start", {"fixture": "squats-15"})
    post("/studio/recorded/start", {"fixture": "squats-15"}, status=409)
    status = post("/studio/recorded/stop")
    assert status["status"] == "ENDED" and status["end_reason"] == "OWNER_CLOSED"
    s = client.get("/api/state").json()["state"]
    assert s["studio"]["status"] == "PAUSED" and s["studio"]["gate"] == "LOCKED"
    assert s["studio"]["source"] == "RECORDED_WORKOUT_VIDEO"
    assert e.contract(s, "squats")["status"] == "ACTIVE"
