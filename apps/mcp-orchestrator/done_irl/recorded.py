"""RECORDED DEMO video source for the REALITY-LOCK studio.

A committed, hash-pinned video fixture is decoded frame by frame, every decoded frame goes
through the same MediaPipe ``PoseDetector`` and the same ``frame_received`` reducer as the
live Ring WHEP path. Nothing here sets a count: reps only come from pose inference on the
decoded pixels. The source is always labelled ``RECORDED DEMO`` and never ``LIVE RING``.
"""

import asyncio
import hashlib
import os
import time
import uuid
from pathlib import Path

import cv2

from .models import ApiError

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE = "RECORDED_DEMO_VIDEO"
LABEL = "RECORDED DEMO"

# Official MediaPipe Pose Landmarker (lite, float16, v1). Same URL/hash as scripts/check-public-pose.py.
POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
)
POSE_MODEL_SHA256 = "59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a"
DEFAULT_POSE_MODEL = REPO_ROOT / "artifacts" / "vision" / "pose-lite.task"

FIXTURE_DIR = REPO_ROOT / "packages" / "testing-fixtures" / "pose"
FIXTURES = {
    "squats-15": (
        "squats-15-synthetic.mp4",
        "2a35a46dd85d419bc38fdbcf2baa7a22272fbee8b9ab74e9e7c012e101e19162",
    ),
    "squats-half-15": (
        "squats-half-15-synthetic.mp4",
        "cdb46543128196ace704df0d7706e921cb256ff9edf8a74a1f31fd823d97c47a",
    ),
}
SKELETON = (
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 31), (24, 26), (26, 28), (28, 32),
)  # fmt: skip


def pose_model_location():
    """Server-configured model, else the SHA-pinned default fetched by scripts/fetch-pose-model.py."""
    configured = os.getenv("POSE_MODEL_FILE")
    if configured:
        return configured, os.getenv("POSE_MODEL_SHA256")
    return str(DEFAULT_POSE_MODEL), POSE_MODEL_SHA256


def fetch_pose_model(destination=DEFAULT_POSE_MODEL):
    """Download the official model only if missing/corrupt; refuse anything but the pinned hash."""
    import httpx

    path = Path(destination)
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == POSE_MODEL_SHA256:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    with httpx.stream("GET", POSE_MODEL_URL, timeout=60, follow_redirects=False) as response:
        response.raise_for_status()
        size = 0
        with partial.open("wb") as target:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 32 * 1024 * 1024:
                    raise RuntimeError("Pose model exceeds the download limit.")
                target.write(chunk)
    if hashlib.sha256(partial.read_bytes()).hexdigest() != POSE_MODEL_SHA256:
        partial.unlink()
        raise RuntimeError("Pose model checksum mismatch.")
    partial.replace(path)
    return path


def fixture_path(name):
    if name not in FIXTURES:
        raise ApiError(404, "FIXTURE_UNKNOWN", "Choose a published recorded demo fixture.")
    filename, expected = FIXTURES[name]
    path = FIXTURE_DIR / filename
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ApiError(503, "FIXTURE_INVALID", "Recorded demo fixture failed its integrity check.")
    return path


def decode(path):
    """Yield (index, timestamp_ms, bgr_frame) from the container clock; never a client timestamp."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ApiError(503, "FIXTURE_UNDECODABLE", "Recorded demo video could not be decoded.")
    fps = capture.get(cv2.CAP_PROP_FPS)
    if not 1 <= fps <= 240:
        capture.release()
        raise ApiError(503, "FIXTURE_FPS_INVALID", "Recorded demo video has no valid frame rate.")
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                return
            if frame.shape[1] > 1280:
                frame = cv2.resize(frame, (1280, round(frame.shape[0] * 1280 / frame.shape[1])))
            yield index, int(index * 1000 / fps), frame
            index += 1
    finally:
        capture.release()


def video_fps(path):
    capture = cv2.VideoCapture(str(path))
    try:
        return capture.get(cv2.CAP_PROP_FPS)
    finally:
        capture.release()


def annotate(frame, points, studio=None):
    """Overlay skeleton + counter on a copy. Drawing never feeds back into inference."""
    image = frame.copy()
    h, w = image.shape[:2]
    if points:
        for a, b in SKELETON:
            if min(points[a][3], points[b][3]) >= 0.5:
                cv2.line(
                    image,
                    (int(points[a][0] * w), int(points[a][1] * h)),
                    (int(points[b][0] * w), int(points[b][1] * h)),
                    (90, 240, 180),
                    3,
                    cv2.LINE_AA,
                )
        for i in (11, 12, 23, 24, 25, 26, 27, 28):
            if points[i][3] >= 0.5:
                cv2.circle(image, (int(points[i][0] * w), int(points[i][1] * h)), 5, (40, 90, 250), -1)
    else:
        cv2.putText(image, "POSE UNAVAILABLE", (16, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (60, 60, 230), 2)
    cv2.rectangle(image, (0, 0), (w, 34), (20, 20, 20), -1)
    cv2.putText(
        image,
        "DONE/IRL - Reality-Lock studio",
        (10, 23),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (230, 230, 230),
        1,
        cv2.LINE_AA,
    )
    # The console renders the authoritative rep counter and gate beside the frame; no burned-in copy.
    del studio
    return image


def open_studio(state, camera_id, fixture, model_sha256):
    """Bind the REALITY-LOCK studio to a recorded-demo session (same reducer as live frames)."""
    from . import engine as e

    if not state["consent"]:
        raise ApiError(409, "CONSENT_REQUIRED", "Enable camera consent first.")
    e.pose_contract(state)
    current = state["studio"]
    if current and current["status"] in {"COMPLETED", "OVERRIDDEN"}:
        raise ApiError(409, "STUDIO_FINISHED", "This REALITY-LOCK session already finished; reset the demo.")
    if current and current.get("count", 0) and current.get("source") != SOURCE:
        raise ApiError(409, "STUDIO_IN_PROGRESS", "Another source already has verified reps; reset first.")
    if current:
        # Each playback must earn all fifteen reps itself; partial recorded runs never accumulate.
        state["studio"] = None
    e.studio_start(state, source=SOURCE, source_mode="SIMULATED_VERIFIED")
    session = state["studio"]
    session.update(
        camera_id=camera_id,
        fixture=fixture,
        label=LABEL,
        model_sha256=model_sha256,
        timestamp_base=max(0, session["last_timestamp_ms"]) + 1,
        status="RUNNING",
        phase="STANDING",
        stable=0,
        quality="AWAITING_FRAMES",
    )
    return session


def replay(frames, detector, on_frame, camera):
    """Synchronously run (timestamp_ms, frame) pairs through pose inference and the reducer.

    Yields per-frame observations for evidence/test assertions. Timestamps must increase,
    exactly as a decoder clock would; repeated pixels stay repeated pixels.
    """
    for timestamp, frame in frames:
        points = detector.infer(frame, timestamp)
        raw_hash = hashlib.sha256(frame.tobytes()).hexdigest()
        studio = on_frame(camera, frame, points, timestamp, raw_hash)
        yield {"timestamp_ms": timestamp, "points": points, "studio": studio, "frame": frame}


class RecordedDemoBridge:
    """Plays a pinned fixture through the real pose engine; mirrors CameraBridge's lifecycle."""

    def __init__(self, on_frame, on_end, detector_factory=None):
        self.on_frame, self.on_end = on_frame, on_end
        self.sessions = {}
        self.finished = {}
        self.realtime = True  # tests/evaluation may process as fast as inference allows
        self.detector_factory = detector_factory

    def _detector(self):
        if self.detector_factory:
            return self.detector_factory()
        from .camera import PoseDetector

        return PoseDetector(*pose_model_location())

    async def start(self, household, fixture, realtime=None, session_id=None):
        if household in self.sessions:
            raise ApiError(409, "RECORDED_DEMO_ALREADY_OPEN", "Stop the current recorded demo first.")
        path = await asyncio.to_thread(fixture_path, fixture)
        detector = await asyncio.to_thread(self._detector)
        session = {
            "id": session_id or "recorded_" + uuid.uuid4().hex,
            "fixture": fixture,
            "source": SOURCE,
            "label": LABEL,
            "source_mode": "SIMULATED_VERIFIED",
            "status": "STREAMING",
            "frames_decoded": 0,
            "frames_with_pose": 0,
            "model_sha256": detector.model_hash,
            "fps": await asyncio.to_thread(video_fps, path),
            "jpeg": None,
            "detector": detector,
            "started": time.monotonic(),
        }
        self.finished.pop(household, None)
        self.sessions[household] = session
        realtime = self.realtime if realtime is None else realtime
        session["task"] = asyncio.create_task(self.play(household, session, path, realtime))
        return self.status(household)

    def status(self, household):
        session = self.sessions.get(household) or self.finished.get(household)
        if not session:
            return {"status": "CLOSED", "source": SOURCE, "label": LABEL}
        public = ("id", "fixture", "source", "label", "source_mode", "status", "frames_decoded",
                  "frames_with_pose", "model_sha256", "fps")  # fmt: skip
        return {key: session[key] for key in public} | {"end_reason": session.get("end_reason")}

    def frame(self, household):
        session = self.sessions.get(household) or self.finished.get(household)
        return session["jpeg"] if session else None

    async def play(self, household, session, path, realtime):
        camera = {"id": session["id"], "model_sha256": session["model_sha256"], "source": SOURCE}
        reason = "RECORDING_ENDED"
        try:
            frames = decode(path)
            started = time.monotonic()
            while self.sessions.get(household) is session:
                item = await asyncio.to_thread(next, frames, None)
                if item is None:
                    break
                index, timestamp, frame = item
                points = await asyncio.to_thread(session["detector"].infer, frame, timestamp)
                raw_hash = hashlib.sha256(frame.tobytes()).hexdigest()
                studio = await asyncio.to_thread(
                    self.on_frame, household, camera, frame, points, timestamp, raw_hash
                )
                ok, jpeg = cv2.imencode(
                    ".jpg", annotate(frame, points, studio), [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                session.update(
                    jpeg=bytes(jpeg) if ok else session["jpeg"],
                    frames_decoded=index + 1,
                    frames_with_pose=session["frames_with_pose"] + (1 if points else 0),
                )
                if studio and studio.get("gate") == "UNLOCKED":
                    reason = "COMPLETED"
                if realtime:
                    # Pace to the container clock so viewers see real playback speed.
                    await asyncio.sleep(
                        max(0.0, started + timestamp / 1000 + 1 / session["fps"] - time.monotonic())
                    )
                else:
                    await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except ApiError as error:
            reason = error.code
        except Exception:
            reason = "RECORDED_DEMO_FAILED"
        reason = session.get("stop_reason", reason)
        session["status"] = "ENDED"
        session["end_reason"] = reason
        await self._release(household, session, reason)

    async def _release(self, household, session, reason):
        if self.sessions.get(household) is session:
            self.sessions.pop(household)
        session.setdefault("end_reason", reason)
        session["status"] = "ENDED"
        self.finished[household] = session
        if session.get("released"):
            return
        session["released"] = True
        await asyncio.to_thread(session["detector"].close)
        await asyncio.to_thread(self.on_end, household, session["id"], reason)

    async def stop(self, household, reason="OWNER_CLOSED"):
        session = self.sessions.pop(household, None)
        if not session:
            return
        session["stop_reason"] = reason
        task = session.get("task")
        if task and task is not asyncio.current_task():
            # Let the in-flight inference thread finish (the loop exits once the session is
            # unregistered) so the detector is never closed underneath a running inference.
            await asyncio.gather(task, return_exceptions=True)
        await self._release(household, session, reason)

    async def shutdown(self):
        await asyncio.gather(*(self.stop(h, "SERVICE_SHUTDOWN") for h in list(self.sessions)))
