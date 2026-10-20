"""Reproduce a limited positive MediaPipe check using a pinned MIT-licensed public sample.

This deliberately does not assert fifteen reps or certify a person's fitness/identity.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import httpx

root = Path(__file__).resolve().parents[1]
output = root / "artifacts/vision"
output.mkdir(parents=True, exist_ok=True)
assets = [
    (
        "pose-lite.task",
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a",
    ),
    (
        "public-reference-squats.mp4",
        "https://raw.githubusercontent.com/Srustika-18/squat-counter/9b64cbf1c1f6bfdbfd87a158911dc624d5573c14/video.mp4",
        "29a6ef63da5e1b12d0bb976ddf3d527b93f699b80e14ee4d66ece81ec4e505b1",
    ),
]
for filename, url, sha in assets:
    path = output / filename
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        with httpx.stream("GET", url, timeout=60, follow_redirects=False) as response:
            response.raise_for_status()
            size = 0
            with path.open("wb") as target:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 32 * 1024 * 1024:
                        raise SystemExit("Reference asset exceeds the download limit.")
                    target.write(chunk)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            path.unlink()
            raise SystemExit("Reference asset checksum mismatch.")
command = [
    sys.executable,
    str(root / "apps/vision-webrtc-engine/process-video.py"),
    "--model",
    str(output / "pose-lite.task"),
    "--input",
    str(output / "public-reference-squats.mp4"),
    "--output",
    str(output / "public-reference-result.json"),
    "--provenance",
    "PUBLIC_LICENSED_RECORDED",
]
subprocess.run(command, check=True, cwd=root, env={**os.environ, "MPLCONFIGDIR": str(output / "matplotlib")})
result = json.loads((output / "public-reference-result.json").read_text())
if result["frames_decoded"] != 363 or not 1 <= result["rep_count"] < 15:
    raise SystemExit("Limited positive reference check failed; review actual model/pose results.")
print("PASS: limited positive public reference. Fifteen-rep canonical acceptance remains NOT MET.")
