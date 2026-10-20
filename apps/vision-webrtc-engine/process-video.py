"""Offline consented-video pose evaluation. Output is evidence metadata, never a live Ring claim."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
import cv2
import mediapipe as mp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp-orchestrator"))
from done_irl.vision import pose_update  # noqa: E402


def process(model_path, input_path, output_path):
    model = Path(model_path)
    source = Path(input_path)
    if not model.is_file() or not source.is_file():
        raise SystemExit("A verified local model and consented input video are required.")
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise SystemExit("Could not decode the input video.")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not 1 <= fps <= 240:
        raise SystemExit("Video FPS is invalid; provide correctly timestamped footage.")
    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.7,
        min_pose_presence_confidence=0.7,
        min_tracking_confidence=0.7,
    )
    session = dict(status="RUNNING", count=0, phase="STANDING", stable=0, gate="LOCKED", last_timestamp_ms=-1)
    observations = []
    started = time.monotonic()
    count = 0
    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as detector:
        while True:
            success, frame = capture.read()
            if not success:
                break
            timestamp = int(count * 1000 / fps)
            result = detector.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)),
                timestamp,
            )
            count += 1
            if not result.pose_landmarks:
                session.update(phase="STANDING", stable=0, quality="POSE_UNAVAILABLE")
                continue
            points = [[p.x, p.y, p.z, p.visibility] for p in result.pose_landmarks[0]]
            # Normalize y to x units to preserve image aspect ratio for angle geometry.
            points_for_angles = [[p[0], p[1] * frame.shape[0] / frame.shape[1], p[2], p[3]] for p in points]
            rep = pose_update(session, f"video-{count}", timestamp, points_for_angles)
            observations.append(
                dict(
                    timestamp_ms=timestamp,
                    landmarks=points,
                    rep_verified=rep,
                    count=session["count"],
                    quality=session.get("quality"),
                    phase=session["phase"],
                )
            )
    capture.release()
    output = {
        "schema_version": "1.0",
        "source": "CONSENTED_RECORDED_VIDEO",
        "source_mode": "NOT_CONNECTED",
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "video_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "frames_decoded": count,
        "processing_fps": count / max(0.001, time.monotonic() - started),
        "rep_count": session["count"],
        "observations": observations,
        "limitations": [
            "Offline output requires human review and authorized server ingestion; not live Ring or Fire TV runtime proof."
        ],
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output))
    print(json.dumps({k: v for k, v in output.items() if k != "observations"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    process(args.model, args.input, args.output)
