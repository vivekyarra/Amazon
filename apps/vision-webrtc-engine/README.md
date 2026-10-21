# Vision and camera sources

Muni's vision runs inside the orchestrator package so that live, recorded and replay sources drive the same reducers and state transitions. Every source keeps its provenance label end to end.

| Source | Module | What it does |
|---|---|---|
| Live Ring video | `done_irl/camera.py` | WHEP receive-only session through the backend, server-side frame decode, SHA-pinned MediaPipe Pose on each frame, authenticated JPEG relay with skeleton overlay. Verified live on the Ring Developer Playground device ([probe](../../docs/evidence/ring-live-probe.json), [studio](../../docs/evidence/ring-live-studio.json)). |
| Recorded scene footage | `done_irl/scene.py` | Decodes `REAL_RECORDED_STOCK` clips (licensed Pexels / CC BY Commons footage, never Ring or household media), detects COCO objects with the SHA-pinned MediaPipe EfficientDet-Lite0 model, tracks people with ephemeral IoU track IDs and infers parcels from persistent person-free change inside the calibrated `PORCH_DEPOSIT_ROI` (COCO has no parcel class). Returns the porch/threshold verdict contract with confidence and pixel trajectories. Scenario branches `real_deposit`, `real_no_deposit`, `real_removal`, `real_pickup`, `real_passerby`, `real_visible`, `real_empty` and `real_bags` feed it; `scripts/scene-vision-evidence.py` regenerates [the results](../../docs/evidence/scene-vision.json). |
| Recorded workout | `scripts/evaluate-pose-fixtures.py` | Runs the pinned MediaPipe Pose model over the generated fifteen-rep fixture through the same reducer as live frames ([results](../../docs/evidence/pose-15-fixture.json)). |
| Scripted replay | `done_irl/vision.py` | Deterministic OpenCV engine for the replay scenarios: segments marker frames, follows parcel positions and evaluates knee angles. |

Live sessions are bounded (30/60 seconds per Ring session); reconnecting preserves the verified count, and camera loss pauses verification.

## Offline pose worker

`process-video.py` is an optional standalone MediaPipe worker for consented human footage. It needs the official Pose Landmarker model, the `human-pose` extra and system `libgles2`/`libegl1`. It outputs 33-landmark observations and counted cycles; it does not bypass the service's authorization or evidence policy.

```bash
uv sync --frozen --extra human-pose
uv run --extra human-pose python apps/vision-webrtc-engine/process-video.py \
  --model /private/pose_landmarker.task --input /private/consented-squats.mp4 \
  --output artifacts/human-pose.json --provenance CONSENTED_RECORDED
```

Keep private footage and outputs outside Git. Obtain the model from the official [MediaPipe Pose Landmarker documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python) and record its SHA-256 with your results. Use third-party video only with permission; sources and licenses used by Muni are listed in [public references](../../docs/public-references.md).
