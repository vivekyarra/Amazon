"""Pixel-processing synthetic fixtures + conservative landmark verifier.

This calibrated color-marker detector validates the synthetic test source, not general
real-world human recognition. MediaPipe input is supported through the optional worker.
"""

import hashlib
import math
import cv2
import numpy as np

COLORS = {"person": (200, 120, 40), "parcel": (30, 180, 220), "drinks": (100, 220, 80)}


def scene(parcel_x=280, person_x=100, drinks=False, occluded=False):
    frame = np.full((360, 640, 3), (26, 32, 40), dtype=np.uint8)
    cv2.rectangle(frame, (200, 150), (500, 335), (45, 55, 65), -1)
    cv2.rectangle(frame, (430, 35), (555, 290), (65, 80, 90), 3)
    cv2.line(frame, (0, 320), (640, 320), (95, 110, 125), 2)
    if parcel_x is not None:
        cv2.rectangle(frame, (int(parcel_x), 265), (int(parcel_x) + 45, 305), COLORS["parcel"], -1)
    if person_x is not None:
        cv2.circle(frame, (int(person_x), 110), 22, COLORS["person"], -1)
        cv2.rectangle(frame, (int(person_x) - 22, 135), (int(person_x) + 22, 260), COLORS["person"], -1)
        if drinks:
            cv2.rectangle(frame, (int(person_x) + 25, 200), (int(person_x) + 55, 250), COLORS["drinks"], -1)
    if occluded:
        cv2.rectangle(frame, (0, 0), (640, 360), (20, 20, 20), -1)
    cv2.putText(
        frame,
        "DEMO / SYNTHETIC - CALIBRATED MARKERS",
        (16, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (210, 220, 230),
        1,
    )
    return frame


def detect(frame):
    found = {}
    for label, color in COLORS.items():
        lo = np.clip(np.array(color) - 5, 0, 255).astype(np.uint8)
        hi = np.clip(np.array(color) + 5, 0, 255).astype(np.uint8)
        mask = cv2.inRange(frame, lo, hi)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            c = max(contours, key=cv2.contourArea)
            if cv2.contourArea(c) > 100:
                found[label] = tuple(int(n) for n in cv2.boundingRect(c))
    return found


def deposit_verdict(frames):
    obs = [detect(f) for f in frames]
    if len(obs) < 3 or not all("parcel" in o for o in obs):
        return "UNKNOWN"
    last = obs[-1]
    x = last["parcel"][0]
    stationary = abs(obs[-2]["parcel"][0] - x) < 8
    if stationary and 200 <= x <= 455 and "person" not in last:
        return "DEPOSIT_CONFIRMED"
    if "person" in last and abs(last["person"][0] - x) < 70 and x < 150:
        return "MISMATCH"
    return "UNKNOWN"


def fixture_frames(kind):
    if kind == "deposit":
        return [scene(270, 270), scene(280, 380), scene(280, None)]
    if kind == "fake":
        return [scene(270, 270), scene(190, 190), scene(80, 80)]
    if kind == "removal":
        return [scene(280, 450), scene(280, 300), scene(160, 160), scene(70, 70)]
    return [scene(None, None, occluded=True)] * 3


def removal_verdict(frames):
    observations = [detect(f) for f in frames]
    if len(observations) < 3 or not all("parcel" in o for o in observations):
        return "UNKNOWN"
    xs = [o["parcel"][0] for o in observations]
    if xs[0] >= 200 and xs[-1] < 150 and xs[-1] < xs[-2] and "person" in observations[-1]:
        return "REMOVAL_UNDER_REVIEW"
    return "NO_REMOVAL"


def png(frame):
    ok, buf = cv2.imencode(".png", frame)
    if not ok:
        raise ValueError("Image encoding failed")
    return bytes(buf)


def angle(a, b, c):
    u, v = np.array(a[:2]) - np.array(b[:2]), np.array(c[:2]) - np.array(b[:2])
    den = np.linalg.norm(u) * np.linalg.norm(v)
    if den < 1e-8:
        return 0.0
    return math.degrees(math.acos(float(np.clip(np.dot(u, v) / den, -1, 1))))


def pose_update(session, frame_id, timestamp_ms, landmarks):
    if session["status"] != "RUNNING":
        return False
    if timestamp_ms <= session.get("last_timestamp_ms", -1):
        return False
    if any(len(p) != 4 or not all(math.isfinite(v) for v in p) for p in landmarks):
        raise ValueError("Expected finite x, y, z, visibility landmarks")
    signature = hashlib.sha256(str(landmarks).encode()).hexdigest()
    # Consecutive unchanged frames cannot cause phase transitions.
    if frame_id == session.get("last_frame_id") or signature == session.get("last_signature"):
        session["last_timestamp_ms"] = timestamp_ms
        return False
    session.update(last_frame_id=frame_id, last_signature=signature, last_timestamp_ms=timestamp_ms)
    points = [landmarks[i] for i in (23, 25, 27, 24, 26, 28)]
    if min(p[3] for p in points) < 0.7:
        session.update(phase="STANDING", stable=0, quality="LOW_VISIBILITY")
        return False
    left, right = angle(*points[:3]), angle(*points[3:])
    if abs(left - right) > 22:
        session.update(phase="STANDING", stable=0, quality="ASYMMETRIC")
        return False
    knee = (left + right) / 2
    previous = session.get("angle", knee)
    session.update(angle=round(knee, 1), quality="TRACKED")
    if abs(knee - previous) > 75:
        session.update(phase="STANDING", stable=0, quality="IMPLAUSIBLE_JUMP")
        return False
    phase = session["phase"]
    if phase == "STANDING" and 100 < knee < 160:
        session.update(phase="DESCENDING", started_ms=timestamp_ms)
    elif phase == "DESCENDING" and knee < 95:
        session["stable"] = session.get("stable", 0) + 1
        if session["stable"] >= 2:
            session.update(phase="BOTTOM_VALID", stable=0)
    elif phase == "BOTTOM_VALID" and 105 < knee < 160:
        session["phase"] = "ASCENDING"
    elif phase == "ASCENDING" and knee > 165:
        session["stable"] = session.get("stable", 0) + 1
        if session["stable"] >= 2 and timestamp_ms - session.get("started_ms", timestamp_ms) >= 600:
            session.update(count=min(15, session["count"] + 1), phase="STANDING", stable=0)
            return True
    return False


def synthetic_pose_frame(degrees, jitter=0):
    """Render marker pixels; extraction below reconstructs landmarks from image, not count."""
    f = np.zeros((480, 640, 3), dtype=np.uint8)
    r = math.radians(degrees)
    for indices, x in [((23, 25, 27), 220), ((24, 26, 28), 400)]:
        points = [(x, 140), (x, 260), (x + int(105 * math.sin(r)), 260 - int(105 * math.cos(r)))]
        for i, (px, py) in zip(indices, points):
            # Every joint has a unique B channel marker.
            cv2.circle(f, (px + jitter, py), 5, (50 + i * 5, 255, 150), -1)
    return f


def extract_marker_pose(frame):
    landmarks = [[0.0, 0.0, 0.0, 0.0] for _ in range(33)]
    for i in (23, 25, 27, 24, 26, 28):
        color = np.array((50 + i * 5, 255, 150), dtype=np.uint8)
        mask = cv2.inRange(frame, color, color)
        coords = cv2.findNonZero(mask)
        if coords is not None:
            m = cv2.moments(mask)
            landmarks[i] = [m["m10"] / m["m00"] / 640, m["m01"] / m["m00"] / 640, 0.0, 1.0]
    return landmarks


def cycle_frames(half=False):
    angles = [178, 145, 115, 88, 85, 120, 150, 173, 178] if not half else [178, 145, 120, 125, 150, 173, 178]
    return [synthetic_pose_frame(a, i % 2) for i, a in enumerate(angles)]
