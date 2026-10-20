# Vision and camera sources

The shared vision engine is `apps/mcp-orchestrator/done_irl/vision.py`; placing policy-critical processing in the same Python package keeps replay and API state transitions consistent. OpenCV really segments generated frame pixels, follows parcel positions across frames, extracts marker coordinates and evaluates knee angles. It is a deterministic geometric fixture engine, not a trained real-world person/parcel model.

A second, clearly separated source runs on real recorded frames: `apps/mcp-orchestrator/done_irl/scene.py` decodes REAL_RECORDED_STOCK clips (public Pexels / CC BY Commons footage, never Ring or household media), detects COCO objects with the SHA-256-pinned MediaPipe EfficientDet-Lite0 model, tracks people with ephemeral IoU track IDs, infers parcels from persistent person-free change inside the calibrated `PORCH_DEPOSIT_ROI` (COCO has no parcel class), and returns the same porch/threshold verdict contract with confidence, pixel trajectories and "world-space trajectory unavailable". Scenario branches `real_deposit`, `real_no_deposit`, `real_removal`, `real_pickup`, `real_passerby`, `real_visible`, `real_empty` and `real_bags` feed it through the same reducers. `scripts/scene-vision-evidence.py` regenerates [the recorded results](../../docs/evidence/scene-vision.json).

`process-video.py` is a separate optional MediaPipe worker for consented human footage. It requires an official Pose Landmarker model, extra dependency installation, system `libgles2`/`libegl1`, and a real validation recording. The worker was also exercised against a generated 20-frame no-human negative fixture using the official lite model; it decoded 20 frames and counted zero reps. This does not validate 15 actual human repetitions. It outputs 33-landmark observations and counted cycles; it does not bypass the service's authorization/evidence policy or claim a Ring connection.

```bash
uv sync --frozen --extra human-pose
uv run --extra human-pose python apps/vision-webrtc-engine/process-video.py \
  --model /private/pose_landmarker.task --input /private/consented-squats.mp4 \
  --output artifacts/human-pose.json --provenance CONSENTED_RECORDED
```

Keep private footage and generated outputs outside Git. Obtain the model from the official [MediaPipe Pose Landmarker documentation](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python), verify its published integrity metadata where provided, and record the local model SHA-256 with the test results. Do not use third-party videos without permission. No reference video or live camera was available during the initial synthetic implementation.

Live Ring WHEP requires an authorized backend account, supported decoder, bounded session renewal, camera capability testing, and a secure renderer/relay. The backend adapter supplies discovery/history/capability/signaling scaffolding and tests URL trust/session budgets. It is **not** wired to a functioning live video relay yet. That remains a tracked release blocker rather than a mislabeled synthetic fallback.
