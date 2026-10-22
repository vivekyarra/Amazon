import asyncio
import hashlib
import json
from fractions import Fraction

import numpy as np
import pytest

from done_irl import engine as e, vision
from done_irl.camera import CameraBridge, authorized_device, PoseDetector
from done_irl.camera_reducers import frame_received, camera_ended
from done_irl.models import ApiError
from done_irl.store import Store


def test_camera_binding_cannot_select_another_households_device(tmp_path):
    path = tmp_path / "bindings.json"
    path.write_text(
        json.dumps({"account": {"household": "house_one", "devices": ["one"], "mains_powered_devices": []}})
    )
    assert authorized_device("house_one", "one", str(path)) is False
    with pytest.raises(ApiError) as exc:
        authorized_device("house_two", "one", str(path))
    assert exc.value.code == "CAMERA_NOT_AUTHORIZED"


def test_model_requires_known_hash_before_loading_runtime(tmp_path):
    path = tmp_path / "model.task"
    path.write_bytes(b"not a model")
    with pytest.raises(ApiError) as exc:
        PoseDetector(str(path), "0" * 64)
    assert exc.value.code == "POSE_MODEL_INVALID"


def camera_house(store):
    state = e.fresh()
    state.update(household_id="house_owner", clock_mode="WALL", consent=True)
    e.create_contract(state, "squats", "15 squats", "I'll do 15 squats", "Self", "FIRE_TV_LIVE_POSE_CAMERA")
    e.studio_start(state, source="LIVE_RING_WHEP", source_mode="STANDBY")
    state["studio"].update(camera_id="test-camera", timestamp_base=0)
    state["camera_request"] = {"status": "OPEN"}
    with store.transaction() as db:
        store.save(db, "house_owner", state)
    return {"id": "test-camera", "model_sha256": "a" * 64}


def test_decoded_frames_use_shared_14_vs_15_gate_and_preserve_hashes(tmp_path):
    # Calibrated scripted landmarks test the decoder callback reducer, not MediaPipe accuracy.
    store = Store(str(tmp_path / "ledger.db"))
    camera = camera_house(store)
    timestamp = 0
    for cycle in range(15):
        for image in vision.cycle_frames(offset=cycle * 3):
            timestamp += 160
            points = vision.extract_marker_pose(image)
            # Marker geometry normalizes both axes to width; convert back to normalized image y.
            points = [[p[0], p[1] * image.shape[1] / image.shape[0], p[2], p[3]] for p in points]
            frame_received(
                store,
                "house_owner",
                camera,
                image,
                points,
                timestamp,
                hashlib.sha256(image.tobytes()).hexdigest(),
            )
        state = store.read("house_owner")
        assert state["studio"]["count"] == cycle + 1
        assert state["studio"]["gate"] == ("UNLOCKED" if cycle == 14 else "LOCKED")
    state = store.read("house_owner")
    assert len(state["studio"]["verified_reps"]) == 15
    assert (
        state["evidence"][-1]["provenance"] == "LIVE_SENSOR"
    )  # Label selected by server callback, never a client field.
    proof = store.uow.get_artifact(state["evidence"][-1]["evidence_id"], "house_owner")
    assert len(json.loads(proof["data"])["verified_reps"]) == 15
    camera_ended(store, "house_owner", "test-camera", "SESSION_LIMIT_REACHED")
    assert store.read("house_owner")["studio"]["gate"] == "UNLOCKED"


def test_no_pose_or_duplicate_video_cannot_complete_cycle(tmp_path):
    store = Store(str(tmp_path / "ledger.db"))
    camera = camera_house(store)
    image = np.zeros((480, 640, 3), np.uint8)
    frame_received(store, "house_owner", camera, image, None, 100, "first")
    assert store.read("house_owner")["studio"]["quality"] == "POSE_UNAVAILABLE"
    for timestamp, marker in enumerate(vision.cycle_frames(), start=1):
        points = vision.extract_marker_pose(marker)
        frame_received(store, "house_owner", camera, marker, points, timestamp * 160, "same-frame-hash")
    assert store.read("house_owner")["studio"]["count"] == 0
    camera_ended(store, "house_owner", "test-camera", "CAMERA_GAP")
    assert store.read("house_owner")["studio"]["status"] == "PAUSED"


@pytest.mark.asyncio
async def test_real_webrtc_codec_loopback_is_explicit_scripted_transport(monkeypatch, tmp_path):
    aiortc = pytest.importorskip("aiortc")
    av = pytest.importorskip("av")
    from done_irl import camera as module

    path = tmp_path / "bindings.json"
    path.write_text(json.dumps({"account": {"household": "house_owner", "devices": ["one"]}}))
    monkeypatch.setenv("RING_BINDINGS_FILE", str(path))
    monkeypatch.setenv("RING_ACCESS_TOKEN", "test-only")
    real_peer = aiortc.RTCPeerConnection
    remote = real_peer(aiortc.RTCConfiguration(iceServers=[]))
    monkeypatch.setattr(
        aiortc, "RTCPeerConnection", lambda config: real_peer(aiortc.RTCConfiguration(iceServers=[]))
    )
    cleaned = []

    class GeneratedVideo(aiortc.VideoStreamTrack):
        n = 0

        async def recv(self):
            await asyncio.sleep(1 / 20)
            self.n += 1
            image = np.full((180, 320, 3), self.n % 255, np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            frame.pts = self.n * 4500
            frame.time_base = Fraction(1, 90000)
            return frame

    class ScriptedAdapter:
        client = None

        def __init__(self):
            self.client = self

        async def capabilities(self, device):
            return {"data": {"attributes": {"video": {"codecs": ["H264"]}}}}

        async def whep(self, device, sdp, battery):
            await remote.setRemoteDescription(aiortc.RTCSessionDescription(sdp=sdp, type="offer"))
            remote.addTrack(GeneratedVideo())
            await remote.setLocalDescription(await remote.createAnswer())
            return {"answer": remote.localDescription.sdp, "location": "https://api.amazonvision.com/test"}

        async def close(self, location):
            cleaned.append(location)

        async def aclose(self):
            pass

    class ScriptedPose:
        model_hash = "a" * 64

        def __init__(self, *args):
            pass

        def infer(self, image, timestamp):
            return None

        def close(self):
            pass

    monkeypatch.setattr(module, "RingAdapter", ScriptedAdapter)
    monkeypatch.setattr(module, "PoseDetector", ScriptedPose)
    decoded, ended = [], []
    bridge = CameraBridge(
        lambda *args: decoded.append(hashlib.sha256(args[2].tobytes()).hexdigest()),
        lambda *args: ended.append(args),
    )
    try:
        result = await bridge.start("house_owner", "one")
        assert result["source_mode"] == "STANDBY"
        async with asyncio.timeout(10):
            while len(decoded) < 3:
                await asyncio.sleep(0.05)
        assert len(set(decoded)) >= 2
        assert bridge.status("house_owner")["frames_decoded"] >= 2
        assert bridge.sessions["house_owner"]["jpeg"].startswith(b"\xff\xd8")
        assert not {"location", "pc", "adapter"} & bridge.status("house_owner").keys()
        await bridge.stop("house_owner")
        assert cleaned and ended
        assert bridge.status("house_owner")["source_mode"] == "STANDBY"
    finally:
        await bridge.shutdown()
        await remote.close()
