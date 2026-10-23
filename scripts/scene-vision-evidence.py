"""Run the real-scene pipeline on every REAL_RECORDED_STOCK fixture and record actual results.

Writes docs/evidence/scene-vision.json and annotated keyframes under docs/evidence/scene/.
Results are whatever the pipeline produces on this machine; mismatches are recorded, not hidden.

  uv run --extra ring-video python scripts/scene-vision-evidence.py
"""

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "apps/mcp-orchestrator"))

import cv2  # noqa: E402
import mediapipe  # noqa: E402
from done_irl import scene  # noqa: E402

out_dir = root / "docs/evidence/scene"
out_dir.mkdir(parents=True, exist_ok=True)
detector = scene.Detector()
clips = []
for clip in scene.config()["clips"]:
    result = scene.analyze_clip(clip, detector)
    outcome = result["result"] if clip["mode"] == "threshold" else result["verdict"]
    key = scene.render_keyframe(clip, result)
    annotated = None
    if key:
        image = scene.annotate(clip, result, key["frame"], key["index"])
        h, w = image.shape[:2]
        if w > 480:
            image = cv2.resize(image, (480, int(h * 480 / w)))
        data = scene.jpeg(image, quality=72)
        annotated = f"scene/{clip['id']}.jpg"
        (root / "docs/evidence" / annotated).write_bytes(data)
    public = scene.public(result)
    clips.append(
        dict(
            clip_id=clip["id"],
            provenance=scene.SOURCE,
            mode=clip["mode"],
            expected=clip["expected"],
            observed=outcome,
            matches_expected=outcome == clip["expected"],
            confidence=result["confidence"],
            reason=result["reason"],
            frames_decoded=result["frames_decoded"],
            frames_analyzed=result["frames_analyzed"],
            analysis_fps=result["analysis_fps"],
            processing_seconds=result["processing_seconds"],
            processing_fps=result["processing_fps"],
            fixture_sha256=hashlib.sha256((scene.FIXTURES / clip["file"]).read_bytes()).hexdigest(),
            source=dict(clip["source"]),
            evidence_frame_index=key["index"] if key else None,
            original_frame_sha256=hashlib.sha256(key["original"]).hexdigest() if key else None,
            annotated_frame=annotated,
            details={
                k: public.get(k)
                for k in (
                    "actor_track_id",
                    "roi_contact_frames",
                    "exit_mode",
                    "roi_change_final",
                    "end_frames",
                    "detector_support",
                    "static_tracks_ignored",
                    "subject_track_id",
                    "subject_frames",
                    "subject_mean_score",
                    "drink_frames",
                    "drink_max_score",
                    "carrier_frames",
                    "carriers_seen",
                    "threshold_reached",
                    "coordinate_system",
                    "world_trajectory",
                )
                if k in public
            },
            trajectory_px=public.get("actor_trajectory_px") or public.get("subject_trajectory_px") or [],
        )
    )
    print(clip["id"], clip["expected"], "->", outcome, result["confidence"], result["reason"])
detector.close()
report = dict(
    generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    provenance=scene.SOURCE,
    statement=(
        "Actual pipeline output on public licensed recordings. Not Ring footage, not the user's home, "
        "not live capture. Verifies the real-frame pipeline behavior only; live Ring is covered by ring-live-probe.json and ring-live-studio.json."
    ),
    pipeline_version=scene.PIPELINE_VERSION,
    model=dict(name=scene.MODEL_NAME, url=scene.MODEL_URL, sha256=scene.MODEL_SHA256),
    runtime=dict(
        python=platform.python_version(),
        opencv=cv2.__version__,
        mediapipe=mediapipe.__version__,
        machine=platform.machine(),
        system=platform.system(),
    ),  # fmt: skip
    summary=dict(clips=len(clips), matching_expected=sum(c["matches_expected"] for c in clips)),
    clips=clips,
)
(root / "docs/evidence/scene-vision.json").write_bytes((json.dumps(report, indent=2) + "\n").encode())
