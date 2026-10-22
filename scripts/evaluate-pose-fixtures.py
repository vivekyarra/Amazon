"""Run the recorded pose fixtures through the real MediaPipe engine and ledger reducers.

Writes docs/evidence/pose-15-fixture.json and docs/evidence/pose-15-annotated.mp4.
Every count in the output is read back from the reducer/ledger after inference; nothing is
asserted or written by hand. Requires the ring-video extra (mediapipe) and ffmpeg.
"""

import hashlib
import json
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "apps/mcp-orchestrator"))

import mediapipe  # noqa: E402
from done_irl import engine as e, recorded  # noqa: E402
from done_irl.camera import PoseDetector  # noqa: E402
from done_irl.camera_reducers import frame_received  # noqa: E402
from done_irl.store import Store  # noqa: E402

HOUSE = "house_owner"


def plan(name):
    filename = recorded.FIXTURES[name][0].replace(".mp4", ".plan.json")
    return json.loads((recorded.FIXTURE_DIR / filename).read_text())


def scenarios():
    full = recorded.fixture_path("squats-15")
    half = recorded.fixture_path("squats-half-15")
    reps = plan("squats-15")["reps"]
    frames = [(ts, f) for _, ts, f in recorded.decode(full)]
    step = frames[1][0] - frames[0][0]
    cut = reps[14]["start_frame"]  # end of the 14th physical rep, taken from the generator plan
    lead = frames[: reps[0]["start_frame"]]
    first = frames[reps[0]["start_frame"] : reps[0]["end_frame"] + 1]
    stand, bottom = frames[0][1], frames[reps[0]["bottom_frame"]][1]

    def retime(images):
        return [(i * step, img) for i, img in enumerate(images)]

    return {
        "F17_full_15": ("squats-15", lambda: iter(frames), 15),
        "F17_truncated_14": ("squats-15 frames [0, %d)" % cut, lambda: iter(frames[:cut]), 14),
        "F18_half_squats_15": ("squats-half-15", lambda: ((ts, f) for _, ts, f in recorded.decode(half)), 0),
        "F18_frozen_static_frames": (
            "squats-15 stills (standing + rep-1 bottom) repeated",
            lambda: iter(retime([stand] * 15 + [bottom] * 30 + [stand] * 30)),
            0,
        ),
        "F18_one_rep_looped_15x": (
            "squats-15 standing lead-in, then rep-1 frames looped 15 times",
            lambda: iter(retime([f for _, f in lead] + [f for _ in range(15) for _, f in first])),
            1,
        ),
    }


def run(model, frames, annotate_to=None):
    with tempfile.TemporaryDirectory(prefix="done-irl-pose-", ignore_cleanup_errors=True) as temp:
        store = Store(str(Path(temp) / "ledger.db"))
        state = e.fresh()
        state.update(household_id=HOUSE, consent=True)
        e.create_contract(
            state, "squats", "15 squats", "I'll do 15 squats", "Self", "FIRE_TV_LIVE_POSE_CAMERA"
        )
        detector = PoseDetector(model, recorded.POSE_MODEL_SHA256)
        recorded.open_studio(state, "recorded_eval", "evaluation", detector.model_hash)
        with store.transaction() as db:
            store.save(db, HOUSE, state)
        camera = {"id": "recorded_eval", "model_sha256": detector.model_hash, "source": recorded.SOURCE}
        on_frame = lambda *a: frame_received(store, HOUSE, *a)  # noqa: E731
        reps, gate_history, angles, n, with_pose = [], [], [], 0, 0
        writer = None
        if annotate_to:
            width, height = plan("squats-15")["size"]
            writer = subprocess.Popen(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pixel_format",
                 "bgr24", "-video_size", f"{width}x{height}", "-framerate", "15", "-i", "pipe:0", "-an", "-c:v", "libx264",
                 "-preset", "medium", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                 str(annotate_to)],
                stdin=subprocess.PIPE,
            )  # fmt: skip
        started = time.monotonic()
        previous = 0
        for obs in recorded.replay(frames, detector, on_frame, camera):
            n += 1
            studio = obs["studio"]
            with_pose += 1 if obs["points"] else 0
            if obs["points"] and studio.get("quality") == "TRACKED":
                angles.append(studio["angle"])
            if studio["count"] != previous:
                reps.append(
                    dict(
                        rep=studio["count"],
                        frame_index=n - 1,
                        timestamp_ms=obs["timestamp_ms"],
                        min_knee_angle_deg=min(angles) if angles else None,
                        gate_after=studio["gate"],
                    )
                )
                angles, previous = [], studio["count"]
            gate_history.append(studio["gate"])
            if writer:
                writer.stdin.write(recorded.annotate(obs["frame"], obs["points"], studio).tobytes())
        elapsed = time.monotonic() - started
        if writer:
            writer.stdin.close()
            writer.wait()
        detector.close()
        final = store.read(HOUSE)
        contract = next(c for c in final["contracts"] if c["key"] == "squats")
        events = [x for x in final["events"] if x["event_type"] == "studio.rep_verified"]
        unlocked_before_15 = any(r["gate_after"] == "UNLOCKED" and r["rep"] < 15 for r in reps)
        first_unlock = next((i for i, g in enumerate(gate_history) if g == "UNLOCKED"), None)
        return dict(
            frames_processed=n,
            frames_with_pose=with_pose,
            processing_fps=round(n / max(elapsed, 1e-6), 1),
            rep_verified_events=len(events),
            reducer_count=final["studio"]["count"],
            gate=final["studio"]["gate"],
            contract_status=contract["status"],
            first_unlocked_frame=first_unlock,
            unlocked_before_15=unlocked_before_15,
            evidence_provenance=[x["provenance"] for x in final["evidence"] if x["kind"] == "POSE_15_CYCLES"],
            reps=reps,
        )  # fmt: skip


def main():
    model = recorded.fetch_pose_model()
    out_json = root / "docs/evidence/pose-15-fixture.json"
    out_clip = root / "docs/evidence/pose-15-annotated.mp4"
    results = {}
    for name, (description, frames, expected) in scenarios().items():
        result = run(str(model), frames(), annotate_to=out_clip if name == "F17_full_15" else None)
        result.update(input=description, expected_rep_events=expected,
                      matches_expectation=result["rep_verified_events"] == expected)  # fmt: skip
        results[name] = result
        print(
            name,
            {k: result[k] for k in ("frames_processed", "rep_verified_events", "gate", "contract_status")},
        )
    fixtures = {
        name: dict(path=str((recorded.FIXTURE_DIR / f).relative_to(root)).replace("\\", "/"), sha256=sha)
        for name, (f, sha) in recorded.FIXTURES.items()
    }
    evidence = {
        "schema_version": "1.0",
        "label": "RECORDED DEMO — SYNTHETIC GENERATED HUMANOID VIDEO — NOT LIVE RING, NOT A REAL PERSON",
        "provenance": "SYNTHETIC",
        "source": recorded.SOURCE,
        "source_mode": "SIMULATED_VERIFIED",
        "generator": "scripts/generate-synthetic-squats.py (seed 20261020)",
        "pipeline": "done_irl.recorded.decode -> camera.PoseDetector (MediaPipe PoseLandmarker VIDEO mode) "
        "-> camera_reducers.frame_received -> engine.pose_frame/vision.pose_update",
        "model": dict(url=recorded.POSE_MODEL_URL, sha256=recorded.POSE_MODEL_SHA256),
        "mediapipe_version": mediapipe.__version__,
        "platform": platform.platform(),
        "fixtures": fixtures,
        "annotated_clip": dict(
            path="docs/evidence/pose-15-annotated.mp4",
            sha256=hashlib.sha256(out_clip.read_bytes()).hexdigest(),
            note="Derived overlay of F17_full_15; skeleton/counter drawn after inference, never fed back.",
        ),
        "scenarios": results,
        "limitations": [
            "Generated ray-traced humanoid, not human footage; proves the pipeline counts complete "
            "movements from pixels, not real-world accuracy across bodies, clothing or cameras.",
            "Pinned lite model; the full model was also observed locally to miss reps on this fixture "
            "(see docs/public-references.md).",
            "processing_fps is offline throughput on the recording machine, not live Fire TV FPS.",
            "Inference is not bit-identical across platforms: a bare rep-1 clip with no standing lead-in "
            "counted 1 on Windows but 0 on the Ubuntu CI runner, so the loop scenario starts from the "
            "fixture's standing lead-in.",
        ],
    }
    out_json.write_text(json.dumps(evidence, indent=2) + "\n", newline="\n")
    print(json.dumps({k: v["matches_expectation"] for k, v in results.items()}))
    if not all(v["matches_expectation"] for v in results.values()):
        raise SystemExit("A pose fixture did not match its expectation; inspect the evidence JSON.")


if __name__ == "__main__":
    main()
