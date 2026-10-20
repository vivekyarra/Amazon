"""Backend Ring WHEP receiver, bounded decode and MediaPipe pose processing.

Credentials and upstream SDP/session locations never leave this process. MJPEG output
is owner-authenticated by the API. A motion notification alone never enters this path.
"""

import asyncio
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import cv2

from .adapters import RingAdapter
from .models import ApiError


class PoseDetector:
    def __init__(self, model_file, expected_hash):
        if not model_file or not expected_hash or len(expected_hash) != 64:
            raise ApiError(503, "POSE_MODEL_MISSING", "Configure a verified local pose model and SHA-256.")
        path = Path(model_file)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ApiError(503, "POSE_MODEL_INVALID", "Pose model integrity check failed.")
        try:
            import mediapipe as mp
        except (ImportError, OSError):
            raise ApiError(
                503, "POSE_RUNTIME_MISSING", "Install the ring-video extra and required system libraries."
            ) from None
        self.mp = mp
        self.model_hash = expected_hash
        self.detector = mp.tasks.vision.PoseLandmarker.create_from_options(
            mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=0.7,
                min_pose_presence_confidence=0.7,
                min_tracking_confidence=0.7,
            )
        )

    def infer(self, frame, timestamp):
        mp = self.mp
        result = self.detector.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), timestamp
        )
        if not result.pose_landmarks:
            return None
        return [[p.x, p.y, p.z, p.visibility] for p in result.pose_landmarks[0]]

    def close(self):
        self.detector.close()


def authorized_device(household, device, bindings_file):
    if not bindings_file:
        raise ApiError(503, "RING_ACCOUNT_NOT_LINKED", "Server-side camera bindings are required.")
    try:
        bindings = json.loads(Path(bindings_file).read_text())
        for binding in bindings.values():
            if binding["household"] == household and device in binding["devices"]:
                # Default to battery limits when capability is unknown; never assume mains power.
                return device in binding.get("mains_powered_devices", [])
    except (OSError, ValueError, TypeError, KeyError):
        raise ApiError(503, "RING_BINDINGS_INVALID", "Camera bindings could not be loaded.") from None
    raise ApiError(403, "CAMERA_NOT_AUTHORIZED", "This camera is not linked to your household.")


class CameraBridge:
    def __init__(self, on_frame, on_end):
        self.on_frame, self.on_end = on_frame, on_end
        self.sessions = {}

    async def start(self, household, device):
        if household in self.sessions:
            raise ApiError(409, "CAMERA_ALREADY_OPEN", "Close the current camera session first.")
        mains = authorized_device(household, device, os.getenv("RING_BINDINGS_FILE"))
        if not os.getenv("RING_ACCESS_TOKEN"):
            raise ApiError(503, "RING_NOT_CONNECTED", "An authorized Ring access token is required.")
        try:
            from aiortc import RTCPeerConnection, RTCConfiguration, RTCSessionDescription, RTCIceServer
        except (ImportError, OSError):
            raise ApiError(503, "WHEP_RUNTIME_MISSING", "Install the ring-video extra.") from None
        detector = await asyncio.to_thread(
            PoseDetector, os.getenv("POSE_MODEL_FILE"), os.getenv("POSE_MODEL_SHA256")
        )
        adapter = RingAdapter()
        stun = os.getenv("RING_STUN_URL", "stun:stun.l.google.com:19302")
        if not stun.startswith(("stun:", "stuns:")):
            raise ApiError(503, "STUN_CONFIG_INVALID", "Only configured STUN URLs are accepted.")
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[RTCIceServer(urls=stun)] if stun else []))
        session = {
            "id": uuid.uuid4().hex,
            "device_id": device,
            "status": "CONNECTING",
            "source": "LIVE_RING_WHEP",
            "source_mode": "NOT_CONNECTED",
            "frames_decoded": 0,
            "model_sha256": detector.model_hash,
            "jpeg": None,
            "landmarks": None,
            "started": time.monotonic(),
            "detector": detector,
            "adapter": adapter,
            "pc": pc,
            "location": None,
            "max_seconds": 60 if mains else 30,
            "tracks": [],
        }
        self.sessions[household] = session

        @pc.on("track")
        def track_received(track):
            if track.kind == "video":
                session["tracks"].append(asyncio.create_task(self.consume(household, session, track)))

        try:
            capability = await adapter.capabilities(device)
            if not capability.get("data", {}).get("attributes", {}).get("video"):
                raise ApiError(
                    409, "VIDEO_NOT_SUPPORTED", "The linked device does not advertise video capability."
                )
            # recvonly creates a real video m-line; no dummy transmitted camera or audio.
            pc.addTransceiver("video", direction="recvonly")
            await pc.setLocalDescription(await pc.createOffer())
            result = await adapter.whep(device, pc.localDescription.sdp, battery=not mains)
            session["location"] = result["location"]
            await pc.setRemoteDescription(RTCSessionDescription(sdp=result["answer"], type="answer"))
            session["timeout_task"] = asyncio.create_task(self.expire(household, session["max_seconds"]))
            return self.status(household)
        except BaseException:
            await self.stop(household, "CONNECTION_FAILED")
            raise

    def status(self, household):
        session = self.sessions.get(household)
        if not session:
            return {"status": "CLOSED", "source_mode": "NOT_CONNECTED"}
        public = (
            "id",
            "device_id",
            "status",
            "source",
            "source_mode",
            "frames_decoded",
            "model_sha256",
            "max_seconds",
        )
        return {key: session[key] for key in public}

    async def consume(self, household, session, track):
        previous = -1
        next_inference = 0
        try:
            while self.sessions.get(household) is session:
                frame = await track.recv()
                if time.monotonic() < next_inference:
                    continue
                next_inference = time.monotonic() + 0.1
                # Timestamp derives from this session's decoder clock, never browser input.
                timestamp = max(previous + 1, int((time.monotonic() - session["started"]) * 1000))
                previous = timestamp
                image = frame.to_ndarray(format="bgr24")
                if image.ndim != 3 or image.shape[0] > 2160 or image.shape[1] > 3840:
                    raise ApiError(502, "VIDEO_DIMENSIONS_INVALID", "Camera frame exceeds decoder limits.")
                if image.shape[1] > 1280:
                    image = cv2.resize(image, (1280, round(image.shape[0] * 1280 / image.shape[1])))
                inference = asyncio.create_task(
                    asyncio.to_thread(session["detector"].infer, image, timestamp)
                )
                session["inference"] = inference
                points = await asyncio.shield(inference)
                raw_hash = hashlib.sha256(image.tobytes()).hexdigest()
                await asyncio.to_thread(self.on_frame, household, session, image, points, timestamp, raw_hash)
                annotated = image.copy()
                if points:
                    h, w = image.shape[:2]
                    for a, b in (
                        (11, 12),
                        (11, 23),
                        (12, 24),
                        (23, 24),
                        (23, 25),
                        (25, 27),
                        (24, 26),
                        (26, 28),
                    ):
                        if min(points[a][3], points[b][3]) >= 0.7:
                            cv2.line(
                                annotated,
                                (int(points[a][0] * w), int(points[a][1] * h)),
                                (int(points[b][0] * w), int(points[b][1] * h)),
                                (90, 240, 180),
                                3,
                            )
                ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    session.update(
                        jpeg=bytes(jpeg),
                        landmarks=points,
                        status="STREAMING",
                        source_mode="LIVE_VERIFIED",
                        frames_decoded=session["frames_decoded"] + 1,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.stop(household, "CAMERA_GAP")

    async def expire(self, household, seconds):
        await asyncio.sleep(seconds)
        await self.stop(household, "SESSION_LIMIT_REACHED")

    async def stop(self, household, reason="OWNER_CLOSED"):
        session = self.sessions.pop(household, None)
        if not session:
            return
        for task in [*session["tracks"], session.get("timeout_task")]:
            if task and task is not asyncio.current_task():
                task.cancel()
        try:
            if session["location"]:
                try:
                    await session["adapter"].close(session["location"])
                except Exception:
                    # Always release local resources even if upstream cleanup fails.
                    reason += "_UPSTREAM_CLEANUP_FAILED"
        finally:
            await session["pc"].close()
            await session["adapter"].client.aclose()
            inference = session.get("inference")
            if inference:
                await asyncio.gather(inference, return_exceptions=True)
            await asyncio.to_thread(session["detector"].close)
            await asyncio.to_thread(self.on_end, household, session["id"], reason)

    async def shutdown(self):
        await asyncio.gather(*(self.stop(h, "SERVICE_SHUTDOWN") for h in list(self.sessions)))
