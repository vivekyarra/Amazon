"""Real-scene pipeline on REAL_RECORDED_STOCK clips (public licensed footage, not Ring).

Every verdict below comes from decoding the committed clips, running the pinned MediaPipe
detector, tracking and zone reasoning. Nothing is mocked. Negative cases use the same real frames
truncated, darkened or occluded; those derived inputs are labeled as such.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from done_irl import engine as e, scene

ROOT = Path(__file__).resolve().parents[3]
CLIPS = scene.config()["clips"]


@pytest.fixture(scope="module")
def detector():
    pytest.importorskip("mediapipe")
    try:
        scene.model_path()
    except Exception as exc:  # pragma: no cover - offline machine without the pinned model
        pytest.skip(f"pinned detector model unavailable: {exc}")
    d = scene.Detector()
    yield d
    d.close()


def frames_of(clip_id, until=None):
    clip = scene.clip_config(clip_id)
    frames, _, _ = scene.sampled_frames(scene.FIXTURES / clip["file"], clip["analysis_fps"])
    return clip, [f for f in frames if until is None or f[0] <= until]


def test_fixture_provenance_hashes_and_size():
    manifest = json.loads((ROOT / "packages/testing-fixtures/manifest.json").read_text())
    pinned = {f["id"]: f for f in manifest["real_recorded_stock"]["clips"]}
    total = 0
    for clip in CLIPS:
        path = scene.FIXTURES / clip["file"]
        data = path.read_bytes()
        total += len(data)
        assert hashlib.sha256(data).hexdigest() == pinned[clip["id"]]["sha256"]
        assert pinned[clip["id"]]["provenance"] == "REAL_RECORDED_STOCK"
        src = clip["source"]
        assert src["license"] in {"Pexels License", "CC BY 3.0", "CC0", "Pixabay Content License"}
        assert src["download_url"].startswith(("https://videos.pexels.com/", "https://upload.wikimedia.org/"))
        assert len(src["source_sha256"]) == 64 and src["author"]
        for name in ("STREET_PERIMETER", "PORCH_DEPOSIT_ROI", "DOOR_THRESHOLD_PLANE"):
            assert all(0 <= v <= 1 for point in clip["zones"][name] for v in point)
    assert total < 15 * 1024 * 1024


@pytest.mark.parametrize("clip", CLIPS, ids=[c["id"] for c in CLIPS])
def test_real_clip_verdicts(detector, clip):
    result = scene.analyze_fixture(clip["id"])
    outcome = result["result"] if clip["mode"] == "threshold" else result["verdict"]
    assert outcome == clip["expected"], (result.get("reason"), result.get("confidence"))
    assert result["source"] == "REAL_RECORDED_STOCK"
    assert result["frames_analyzed"] >= 40 and result["frames_decoded"] >= result["frames_analyzed"]
    assert result["world_trajectory"] == "world-space trajectory unavailable"
    assert result["coordinate_system"] == "IMAGE_PIXELS"
    assert result["model"]["sha256"] == scene.MODEL_SHA256
    if outcome not in {"UNKNOWN", "AMBIGUOUS"}:
        assert result["confidence"] >= 0.6
    if clip["mode"] != "threshold" and outcome != "NO_REMOVAL":
        assert result["actor_trajectory_px"], "actor pixel trajectory must be recorded"


def test_static_false_person_is_scene_fixture_not_actor(detector):
    # The FedEx door camera has a wall lamp the detector reports as a "person" in every frame.
    result = scene.analyze_fixture("RS03_COURIER_NO_DEPOSIT")
    assert result["static_tracks_ignored"]
    assert result["actor_track_id"] not in result["static_tracks_ignored"]


@pytest.mark.parametrize(
    "clip_id,until",
    [
        ("RS04_PORCH_REMOVAL_CCTV", 5.0),  # video interrupted while the person is at the parcel
        ("RS05_PORCH_REMOVAL_DOORBELL", 16.0),  # interrupted before a clear post-event view
        ("RS01_DEPOSIT_DOORSTEP_STACK", 6.0),  # courier still placing the parcel
        ("RS03_COURIER_NO_DEPOSIT", 40.0),  # courier still at the door
    ],
)
def test_interrupted_video_never_concludes(detector, clip_id, until):
    clip, frames = frames_of(clip_id, until)
    result = scene.analyze_clip(clip, detector, frames=frames)
    assert result["verdict"] == "UNKNOWN"


def test_passerby_and_non_deposit_do_not_raise_incidents(detector):
    clip, frames = frames_of("RS07_PASSERBY_DRIVEWAY")
    as_deposit = scene.analyze_clip(dict(clip, mode="porch_deposit"), detector, frames=frames)
    assert as_deposit["verdict"] == "UNKNOWN"  # no courier at the porch: not a mismatch accusation
    assert scene.analyze_fixture("RS07_PASSERBY_DRIVEWAY")["verdict"] == "NO_REMOVAL"


def test_camera_loss_dark_and_occluded_frames_are_not_evidence(detector):
    clip, frames = frames_of("RS04_PORCH_REMOVAL_CCTV")
    assert scene.analyze_clip(clip, detector, frames=[])["verdict"] == "UNKNOWN"
    dark = [(t, np.zeros_like(f)) for t, f in frames]
    assert scene.analyze_clip(clip, detector, frames=dark)["reason"] == "CAMERA_UNAVAILABLE"
    occluded = []
    for t, f in frames:  # derived: real frames with a painted board over the porch after t=4s
        g = f.copy()
        if t > 4.0:
            h, w = g.shape[:2]
            g[int(0.15 * h) : int(0.5 * h), int(0.24 * w) : int(0.6 * w)] = 15
        occluded.append((t, g))
    assert scene.analyze_clip(clip, detector, frames=occluded)["verdict"] == "UNKNOWN"
    tclip, tframes = frames_of("RS08_ARRIVAL_BOTTLE_VISIBLE")
    dark = [(t, np.zeros_like(f)) for t, f in tframes]
    assert scene.analyze_clip(tclip, detector, frames=dark)["result"] == "CAMERA_UNAVAILABLE"
    assert scene.analyze_clip(tclip, detector, frames=[])["result"] == "CAMERA_UNAVAILABLE"


def stage(post, n, branch="deposit"):
    return post(f"/admin/scenarios/{n}/run", {"branch": branch})["state"]


def evidence(s, kind):
    return [v for v in s["evidence"] if v["kind"] == kind]


def test_real_deposit_stage_uses_shared_reducers_and_labels_source(detector, client, post):
    stage(post, 1)
    s = stage(post, 2, "real_deposit")
    c = e.contract(s, "parcel")
    assert c["custody_status"] == "DEPOSIT_VERIFIED_CUSTODY_ACTIVE" and c["status"] != "VERIFIED"
    assert c["scene_source"]["source"] == "REAL_RECORDED_STOCK"
    watchdog = [a for a in s["subagents"] if a["kind"] == "PorchWatchdog"]
    assert len(watchdog) == 1 and watchdog[0]["source"] == "REAL_RECORDED_STOCK"
    original = evidence(s, "DEPOSIT_OBSERVATION_SOURCE_FRAME")[0]
    annotated = evidence(s, "DEPOSIT_OBSERVATION_ANNOTATED_FRAME")[0]
    assert annotated["parent_evidence_id"] == original["evidence_id"]
    for item in (original, annotated):
        assert item["source_platform"] == item["source_mode"] == item["provenance"] == "REAL_RECORDED_STOCK"
        body = client.get(f"/api/evidence/{item['evidence_id']}")
        assert body.status_code == 200
        assert hashlib.sha256(body.content).hexdigest() == item["sha256_original"]
    observed = [x for x in s["events"] if x["event_type"] == "vision.scene_observed"]
    assert observed[-1]["payload"]["verdict"] == "DEPOSIT_CONFIRMED"


def test_real_no_deposit_is_disputed_without_watchdog(detector, post):
    stage(post, 1)
    s = stage(post, 2, "real_no_deposit")
    c = e.contract(s, "parcel")
    assert c["status"] == "DISPUTED" and c["deposit_status"] == "DELIVERY_MISMATCH"
    assert not [a for a in s["subagents"] if a["kind"] == "PorchWatchdog"]


def test_real_removal_creates_one_incident_with_truthful_clip_labels(detector, client, post):
    stage(post, 1)
    stage(post, 2, "real_deposit")
    s = stage(post, 4, "real_removal")
    post("/admin/scenarios/4/run", {"branch": "real_removal"}, status=409)  # duplicate event
    assert len(client.get("/api/state").json()["state"]["incidents"]) == 1
    assert len(s["incidents"]) == 1
    inc = s["incidents"][0]
    assert inc["status"] == "AWAITING_HUMAN_DECISION" and inc["source_mode"] == "REAL_RECORDED_STOCK"
    assert inc["quality"] == "EVIDENCE_INCOMPLETE" and inc["clip_actual_duration_seconds"] < 15
    packet = inc["packet"]
    assert packet["world_trajectory"] == "world-space trajectory unavailable"
    assert packet["coordinate_system"] == "IMAGE_PIXELS" and len(packet["trajectory"]) >= 5
    assert packet["person_crop_evidence_id"] and packet["source_clip_evidence_id"]
    clip = next(v for v in s["evidence"] if v["evidence_id"] == packet["source_clip_evidence_id"])
    fixture = (scene.FIXTURES / "RS04_PORCH_REMOVAL_CCTV.mp4").read_bytes()
    assert clip["sha256_original"] == hashlib.sha256(fixture).hexdigest() and clip["mime"] == "video/mp4"
    if packet["annotated_clip_evidence_id"]:
        derived = next(v for v in s["evidence"] if v["evidence_id"] == packet["annotated_clip_evidence_id"])
        assert derived["parent_evidence_id"] == clip["evidence_id"]
    assert e.contract(s, "parcel")["status"] == "DISPUTED"
    assert len([a for a in s["alerts"] if a["kind"] == "PORCH_REMOVAL"]) == 1


def test_real_inward_pickup_and_passerby_do_not_open_incidents(detector, post):
    stage(post, 1)
    stage(post, 2, "real_deposit")
    s = stage(post, 4, "real_pickup")
    c = e.contract(s, "parcel")
    assert not s["incidents"] and c["status"] != "VERIFIED"
    assert c["transfer_observation"] == "TRANSFER_OBSERVED_PENDING_OWNER_CONFIRMATION"
    s = post("/admin/owner-pickup")["state"]  # only explicit owner confirmation closes custody
    assert e.contract(s, "parcel")["status"] == "VERIFIED"


def test_real_passerby_branch(detector, post):
    stage(post, 1)
    stage(post, 2, "real_deposit")
    s = stage(post, 4, "real_passerby")
    assert not s["incidents"]
    assert e.contract(s, "parcel")["custody_status"] == "DEPOSIT_VERIFIED_CUSTODY_ACTIVE"


@pytest.mark.parametrize(
    "branch,result",
    [("real_visible", "VISIBLE_MATCH"), ("real_empty", "NOT_VISIBLE"), ("real_bags", "AMBIGUOUS")],
)
def test_real_threshold_branches(detector, post, branch, result):
    stage(post, 1)
    s = stage(post, 5, branch)
    c = e.contract(s, "drinks")
    assert c["visibility"] == result and c["visibility_source"] == "REAL_RECORDED_STOCK"
    assert c["status"] == "ACTIVE"  # never verified or failed from vision alone
    checks = [a for a in s["alerts"] if a["kind"] == "ARRIVAL_ITEM_CHECK"]
    assert len(checks) == (0 if result == "VISIBLE_MATCH" else 1)
