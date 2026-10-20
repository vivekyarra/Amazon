"""Real-scene porch / threshold vision on decoded video frames (REAL_RECORDED_STOCK source).

Pipeline (spec 11.2 / 11.3), deliberately conservative:

1. Decode the recorded clip with OpenCV and sample it at the configured analysis rate.
2. Detect COCO objects with the MediaPipe Object Detector (EfficientDet-Lite0, SHA-256 pinned).
   COCO has no parcel/box class. A parcel is inferred as a *persistent, person-free change*
   inside the calibrated PORCH_DEPOSIT_ROI relative to a person-free baseline (after global
   translation compensation), optionally supported by luggage-like COCO detections. This is a
   change detector, not a parcel classifier.
3. Associate person detections into ephemeral track IDs (greedy IoU / centroid, ByteTrack-style
   two-stage high/low score matching). Static detections that never move are treated as scene
   fixtures, never as actors. No identity, face or biometric inference is performed.
4. Reason over normalized calibrated zones (STREET_PERIMETER, PORCH_DEPOSIT_ROI,
   DOOR_THRESHOLD_PLANE, PRIVATE_MASKS) and produce the same verdict contract as the synthetic
   path: DEPOSIT_CONFIRMED / MISMATCH / REMOVAL_UNDER_REVIEW / TRANSFER_OBSERVED / NO_REMOVAL /
   UNKNOWN for the porch, VISIBLE_MATCH / NOT_VISIBLE / AMBIGUOUS / CAMERA_UNAVAILABLE for the
   threshold. Low confidence never becomes theft, delivery fraud or "forgot".

Trajectories are pixel paths only: world-space trajectory unavailable (no homography).
Confidences are documented heuristics over observable quantities, not calibrated probabilities.
"""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .models import ApiError

SOURCE = "REAL_RECORDED_STOCK"
PIPELINE_VERSION = "scene-tracker-v1"
MODEL_NAME = "mediapipe-efficientdet-lite0-float32-v1"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/object_detector/"
    "efficientdet_lite0/float32/1/efficientdet_lite0.tflite"
)
MODEL_SHA256 = "40338edf5ec70d43e318b0a716a84d4564cd1802759a7a07170c7e43796dbf58"
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "packages/testing-fixtures/real-stock"
WORLD = "world-space trajectory unavailable"
DRINKS = {"bottle", "cup", "wine glass"}
CARRIERS = {"handbag", "backpack", "suitcase"}
PARCEL_SUPPORT = {"suitcase", "handbag", "backpack"}
ZONE_NAMES = ("STREET_PERIMETER", "PORCH_DEPOSIT_ROI", "DOOR_THRESHOLD_PLANE")

# Branch -> (stage, fixture clip). A real branch requested on a stage it does not belong to uses
# that stage's default real clip, so the source label stays truthful either way.
REAL_BRANCHES = {
    "real_deposit": (2, "RS01_DEPOSIT_DOORSTEP_STACK"),
    "real_no_deposit": (2, "RS03_COURIER_NO_DEPOSIT"),
    "real_removal": (4, "RS04_PORCH_REMOVAL_CCTV"),
    "real_pickup": (4, "RS06_PICKUP_INWARD"),
    "real_passerby": (4, "RS07_PASSERBY_DRIVEWAY"),
    "real_visible": (5, "RS08_ARRIVAL_BOTTLE_VISIBLE"),
    "real_empty": (5, "RS09_ARRIVAL_HANDS_EMPTY"),
    "real_bags": (5, "RS10_ARRIVAL_PAPER_BAGS"),
}
STAGE_DEFAULT = {2: "real_deposit", 4: "real_removal", 5: "real_empty"}


# --------------------------------------------------------------------------- configuration


@lru_cache(maxsize=1)
def config():
    return json.loads((FIXTURES / "scene-fixtures.json").read_text())


def clip_config(clip_id):
    for clip in config()["clips"]:
        if clip["id"] == clip_id:
            return clip
    raise KeyError(clip_id)


def clip_for(stage, branch):
    target = REAL_BRANCHES.get(branch)
    if not target or target[0] != stage:
        target = REAL_BRANCHES[STAGE_DEFAULT[stage]]
    return target[1]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_path(download=True):
    """Return a verified local detector model, fetching the pinned official file if allowed."""
    path = Path(os.getenv("DONE_IRL_DETECTOR_MODEL") or ROOT / "artifacts/vision/efficientdet_lite0.tflite")
    if path.is_file() and _sha(path) == MODEL_SHA256:
        return path
    if not download or os.getenv("DONE_IRL_DETECTOR_DOWNLOAD", "1") == "0":
        raise ApiError(503, "DETECTOR_MODEL_MISSING", "Install the pinned object-detector model.")
    import httpx

    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    try:
        with httpx.stream("GET", MODEL_URL, timeout=60, follow_redirects=False) as response:
            response.raise_for_status()
            size = 0
            with partial.open("wb") as target:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 32 * 1024 * 1024:
                        raise ValueError("model too large")
                    target.write(chunk)
    except (httpx.HTTPError, OSError, ValueError):
        partial.unlink(missing_ok=True)
        raise ApiError(
            503, "DETECTOR_MODEL_MISSING", "The pinned detector model could not be fetched."
        ) from None
    if _sha(partial) != MODEL_SHA256:
        partial.unlink(missing_ok=True)
        raise ApiError(503, "DETECTOR_MODEL_INVALID", "Detector model integrity check failed.")
    partial.replace(path)
    return path


# --------------------------------------------------------------------------- detector


class Detector:
    def __init__(self, path=None, score=0.25):
        try:
            import mediapipe as mp
        except (ImportError, OSError):
            raise ApiError(
                503, "DETECTOR_RUNTIME_MISSING", "Install the ring-video extra (MediaPipe)."
            ) from None
        self.mp = mp
        path = path or model_path()

        def make(threshold):
            return mp.tasks.vision.ObjectDetector.create_from_options(
                mp.tasks.vision.ObjectDetectorOptions(
                    base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
                    running_mode=mp.tasks.vision.RunningMode.IMAGE,
                    score_threshold=threshold,
                    max_results=15,
                )
            )

        self.full = make(score)
        self.crop = make(0.2)

    def _run(self, detector, frame):
        image = self.mp.Image(
            image_format=self.mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        )
        out = []
        for d in detector.detect(image).detections:
            c, b = d.categories[0], d.bounding_box
            out.append(
                dict(
                    label=c.category_name,
                    score=round(float(c.score), 3),
                    box=[int(b.origin_x), int(b.origin_y), int(b.width), int(b.height)],
                )
            )
        return out

    def detect(self, frame):
        return self._run(self.full, frame)

    def carried_items(self, frame, box):
        """Second-stage pass on an enlarged person crop: small hand-held items become detectable."""
        h, w = frame.shape[:2]
        x, y, bw, bh = box
        x0, y0 = max(0, int(x - 0.25 * bw)), max(0, int(y - 0.05 * bh))
        x1, y1 = min(w, int(x + 1.25 * bw)), min(h, int(y + 1.05 * bh))
        if x1 - x0 < 16 or y1 - y0 < 16:
            return []
        items = []
        for d in self._run(self.crop, np.ascontiguousarray(frame[y0:y1, x0:x1])):
            if d["label"] in DRINKS | CARRIERS:
                bx, by, bw2, bh2 = d["box"]
                d["box"] = [bx + x0, by + y0, bw2, bh2]
                items.append(d)
        return items

    def close(self):
        self.full.close()
        self.crop.close()


# --------------------------------------------------------------------------- geometry / zones


def iou(a, b):
    ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0, min(ax1, bx1) - max(a[0], b[0])), max(0, min(ay1, by1) - max(a[1], b[1]))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union else 0.0


def center(box):
    return (box[0] + box[2] / 2, box[1] + box[3] / 2)


def foot(box):
    return (box[0] + box[2] / 2, box[1] + box[3])


class Zones:
    def __init__(self, zones, w, h):
        self.w, self.h = w, h
        self.poly = {
            name: np.array([[x * w, y * h] for x, y in zones.get(name) or []], dtype=np.int32)
            for name in ZONE_NAMES
        }
        self.masks = [
            np.array([[x * w, y * h] for x, y in m], dtype=np.int32) for m in zones.get("PRIVATE_MASKS", [])
        ]
        self.roi = self.fill([self.poly["PORCH_DEPOSIT_ROI"]])
        self.private = self.fill(self.masks)
        pad = max(3, int(0.03 * max(w, h)))
        self.roi_dilated = cv2.dilate(self.roi, np.ones((2 * pad + 1, 2 * pad + 1), np.uint8))
        wide = max(6, int(0.08 * max(w, h)))
        ring = cv2.dilate(self.roi, np.ones((2 * wide + 1, 2 * wide + 1), np.uint8))
        self.ring = np.uint8(((ring > 0) & (self.roi_dilated == 0) & (self.private == 0)) * 255)

    def fill(self, polygons):
        mask = np.zeros((self.h, self.w), np.uint8)
        for p in polygons:
            if len(p) >= 3:
                cv2.fillPoly(mask, [p], 255)
        return mask

    def contains(self, name, point):
        p = self.poly[name]
        return len(p) >= 3 and cv2.pointPolygonTest(p, (float(point[0]), float(point[1])), False) >= 0

    def box_touches_roi(self, box):
        x, y, w, h = [int(v) for v in box]
        x0, y0, x1, y1 = max(0, x), max(0, y), min(self.w, x + w), min(self.h, y + h)
        return x1 > x0 and y1 > y0 and bool(self.roi_dilated[y0:y1, x0:x1].any())


# --------------------------------------------------------------------------- tracker


class Tracker:
    """Greedy two-stage IoU/centroid association with ephemeral IDs (ByteTrack-like)."""

    def __init__(self, diag, max_gap):
        self.diag, self.max_gap = diag, max_gap
        self.tracks, self.next_id = [], 1

    def update(self, index, t, detections):
        live = [tr for tr in self.tracks if index - tr["last"] <= self.max_gap]
        assigned = [None] * len(detections)
        for stage_min, stage_max in ((0.5, 1.01), (0.25, 0.5)):
            pairs = []
            for di, d in enumerate(detections):
                if assigned[di] is not None or not stage_min <= d["score"] < stage_max:
                    continue
                for tr in live:
                    if tr["last"] == index:
                        continue
                    prev = tr["boxes"][-1][2]
                    overlap = iou(prev, d["box"])
                    (cx, cy), (px, py) = center(d["box"]), center(prev)
                    dist = ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 / self.diag
                    gap = index - tr["last"]
                    if overlap >= 0.2 or (stage_min >= 0.5 and dist < 0.08 + 0.02 * gap):
                        pairs.append((overlap - dist, di, tr))
            for _, di, tr in sorted(pairs, key=lambda p: -p[0]):
                if assigned[di] is None and tr["last"] != index:
                    assigned[di] = tr["id"]
                    tr["boxes"].append((index, t, d_box(detections[di]), detections[di]["score"]))
                    tr["last"] = index
        for di, d in enumerate(detections):
            if assigned[di] is None and d["score"] >= 0.3:
                tr = dict(id=f"trk_{self.next_id}", boxes=[(index, t, d_box(d), d["score"])], last=index)
                self.next_id += 1
                self.tracks.append(tr)
                assigned[di] = tr["id"]
        return assigned

    def summarize(self):
        out = []
        for tr in self.tracks:
            centers = np.array([center(b[2]) for b in tr["boxes"]])
            spread = float(np.max(np.linalg.norm(centers - centers[0], axis=1))) if len(centers) else 0.0
            out.append(
                dict(
                    track_id=tr["id"],
                    frames=len(tr["boxes"]),
                    first_index=tr["boxes"][0][0],
                    last_index=tr["last"],
                    max_displacement_norm=round(spread / self.diag, 4),
                    static=len(tr["boxes"]) >= 5 and spread / self.diag < 0.03,
                    mean_score=round(float(np.mean([b[3] for b in tr["boxes"]])), 3),
                    trajectory_px=[
                        [round(b[1], 2), int(foot(b[2])[0]), int(foot(b[2])[1])] for b in tr["boxes"]
                    ],
                    boxes=[[b[0], list(b[2])] for b in tr["boxes"]],
                )
            )
        return out


def d_box(d):
    return [int(v) for v in d["box"]]


# --------------------------------------------------------------------------- decoding


def sampled_frames(path, analysis_fps):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return [], 0, 0.0
    native = cap.get(cv2.CAP_PROP_FPS) or analysis_fps
    step = max(1, round(native / analysis_fps))
    frames, decoded = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if decoded % step == 0:
            frames.append((round(decoded / native, 3), frame))
        decoded += 1
    cap.release()
    return frames, decoded, native


def _shift(base_gray, gray):
    window = cv2.createHanningWindow(base_gray.shape[::-1], cv2.CV_32F)
    (dx, dy), _ = cv2.phaseCorrelate(base_gray, gray, window)
    return dx, dy


def _usable(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(gray.mean()) >= 20 and float(gray.std()) >= 8


# --------------------------------------------------------------------------- analysis


def analyze_clip(clip, detector=None, frames=None):
    """Run the real pipeline on a configured clip (or injected frames for negative tests)."""
    started = time.perf_counter()
    own = detector is None
    if frames is None:
        frames, decoded, native = sampled_frames(FIXTURES / clip["file"], clip["analysis_fps"])
    else:
        decoded, native = len(frames), clip["analysis_fps"]
    base = dict(
        clip_id=clip["id"],
        source=SOURCE,
        source_label="REAL_RECORDED_STOCK - public licensed footage; not Ring, not this household",
        mode=clip["mode"],
        attribution=dict(
            (k, clip["source"][k])
            for k in ("platform", "title", "page_url", "author", "license", "license_url")
        ),
        frames_decoded=decoded,
        frames_analyzed=len(frames),
        analysis_fps=clip["analysis_fps"],
        native_fps=round(native, 3),
        model=dict(name=MODEL_NAME, sha256=MODEL_SHA256),
        pipeline_version=PIPELINE_VERSION,
        coordinate_system="IMAGE_PIXELS",
        world_trajectory=WORLD,
        zones={k: clip["zones"].get(k) for k in (*ZONE_NAMES, "PRIVATE_MASKS")},
    )
    if not frames:
        base.update(
            _camera_unavailable(clip, "NO_DECODABLE_FRAMES"), processing_seconds=0.0, processing_fps=0.0
        )
        return base
    detector = detector or Detector()
    try:
        if clip["mode"] == "threshold":
            body = _threshold(clip, detector, frames)
        else:
            body = _porch(clip, detector, frames)
    finally:
        if own:
            detector.close()
    elapsed = time.perf_counter() - started
    h, w = frames[0][1].shape[:2]
    base.update(body)
    base.update(
        frame_size=[w, h],
        duration_seconds=round(frames[-1][0], 2),
        processing_seconds=round(elapsed, 2),
        processing_fps=round(len(frames) / elapsed, 2) if elapsed else None,
    )
    return base


def _camera_unavailable(clip, reason):
    if clip["mode"] == "threshold":
        return dict(result="CAMERA_UNAVAILABLE", verdict=None, confidence=0.0, reason=reason)
    return dict(verdict="UNKNOWN", result=None, confidence=0.0, reason=reason)


def _porch(clip, detector, frames):
    h, w = frames[0][1].shape[:2]
    zones = Zones(clip["zones"], w, h)
    diag = (w * w + h * h) ** 0.5
    tracker = Tracker(diag, max_gap=max(3, int(clip["analysis_fps"] * 1.6)))
    records, base_stack, baseline, base_gray = [], [], None, None
    roi_area = max(1, int((zones.roi > 0).sum()))
    keep = {}
    for index, (t, frame) in enumerate(frames):
        dets = detector.detect(frame)
        persons = [d for d in dets if d["label"] == "person" and d["score"] >= 0.25]
        ids = tracker.update(index, t, persons)
        for d, tid in zip(persons, ids):
            d["track_id"] = tid
        items = [d for d in dets if d["label"] in PARCEL_SUPPORT]
        rec = dict(index=index, t=t, persons=persons, items=items, usable=_usable(frame))
        near = [d for d in persons if d["score"] >= 0.3 and zones.box_touches_roi(d["box"])]
        rec["person_in_roi"] = bool(near)
        if baseline is None:
            if rec["usable"] and not near:
                base_stack.append(frame)
                if len(base_stack) == 3 or index >= max(2, len(frames) // 4):
                    baseline = np.median(np.stack(base_stack), axis=0).astype(np.uint8)
                    base_gray = Registrar(baseline, zones)
                    rec["baseline_ready"] = True
            records.append(rec)
            continue
        rec.update(_change(frame, baseline, base_gray, zones, persons, roi_area))
        if rec["clean"]:
            keep["final"] = (index, frame)
        if near:
            best = max(near, key=lambda d: d["score"])
            if "event" not in keep or best["score"] >= keep["event"][2] - 0.05:
                keep["event"] = (index, frame, best["score"])
        records.append(rec)
    tracks = tracker.summarize()
    out = _porch_verdict(clip, zones, records, tracks, baseline is not None)
    out["tracks"] = [{k: v for k, v in tr.items() if k != "boxes"} for tr in tracks]
    out["_records"] = records
    out["_track_boxes"] = {tr["track_id"]: tr["boxes"] for tr in tracks}
    out["_keyframes"] = {k: v[0] for k, v in keep.items()}
    out["roi_change_series"] = [
        [r["t"], r.get("roi_change")] for r in records if r.get("roi_change") is not None
    ][:: max(1, len(records) // 40)]
    return out


class Registrar:
    """Similarity registration of a frame onto the baseline using ORB features from static scenery.

    Features inside the deposit ROI, private masks and person boxes are excluded, so a parcel
    appearing/disappearing or a person walking cannot be mistaken for camera motion. A scene with
    too little static texture falls back to an explicitly labeled fixed-camera assumption.
    """

    def __init__(self, baseline, zones):
        self.orb = cv2.ORB_create(1500)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        gray = cv2.cvtColor(baseline, cv2.COLOR_BGR2GRAY)
        self.static = np.uint8(((zones.roi_dilated == 0) & (zones.private == 0)) * 255)
        self.kp, self.des = self.orb.detectAndCompute(gray, self.static)
        self.fixed = self.des is None or len(self.kp) < 40

    def align(self, frame, occupied):
        if self.fixed:
            return np.float32([[1, 0, 0], [0, 1, 0]]), "ASSUMED_FIXED"
        mask = cv2.bitwise_and(self.static, cv2.bitwise_not(occupied))
        kp, des = self.orb.detectAndCompute(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), mask)
        if des is None or len(kp) < 15:
            return None, "FEW_FEATURES"
        matches = self.matcher.match(des, self.des)
        if len(matches) < 15:
            return None, "FEW_MATCHES"
        src = np.float32([kp[m.queryIdx].pt for m in matches])
        dst = np.float32([self.kp[m.trainIdx].pt for m in matches])
        matrix, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if matrix is None or int(inliers.sum()) < 12:
            return None, "NO_CONSENSUS"
        return np.float32(matrix), "REGISTERED"


def _change(frame, baseline, registrar, zones, persons, roi_area):
    h, w = frame.shape[:2]
    occupied = np.zeros((h, w), np.uint8)
    for d in persons:
        if d["score"] >= 0.25:
            x, y, bw, bh = d["box"]
            px, py = int(0.1 * bw), int(0.05 * bh)
            cv2.rectangle(occupied, (x - px, y - py), (x + bw + px, y + bh + py), 255, -1)
    if (occupied > 0).mean() > 0.6:
        return dict(clean=False, registration="PERSON_FILLS_VIEW")
    matrix, status = registrar.align(frame, occupied)
    if matrix is None:
        return dict(clean=False, registration=status)
    scale = float(np.hypot(matrix[0, 0], matrix[1, 0]))
    dx, dy = float(matrix[0, 2]), float(matrix[1, 2])
    if abs(scale - 1) > 0.2 or abs(dx) > 0.2 * w or abs(dy) > 0.2 * h:
        return dict(clean=False, registration="VIEW_CHANGED", shift=[round(dx, 1), round(dy, 1)])
    aligned = cv2.warpAffine(frame, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)
    occupied = cv2.warpAffine(occupied, matrix, (w, h))
    diff = cv2.absdiff(cv2.GaussianBlur(aligned, (5, 5), 0), cv2.GaussianBlur(baseline, (5, 5), 0)).max(
        axis=2
    )
    changed = np.uint8(diff > 32) * 255
    changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    changed[zones.private > 0] = 0
    in_roi = (zones.roi > 0) & (occupied == 0)
    visible_roi = int(in_roi.sum())
    roi_change = float(((changed > 0) & in_roi).sum()) / roi_area
    outside = (zones.roi_dilated == 0) & (zones.private == 0) & (occupied == 0)
    global_change = float(((changed > 0) & outside).sum()) / max(1, int(outside.sum()))
    # A parcel change stays inside the calibrated ROI; an occluder, lens obstruction or lighting
    # change also floods the band around it. Such frames are not evidence either way.
    ring = (zones.ring > 0) & (occupied == 0)
    ring_change = float(((changed > 0) & ring).sum()) / max(1, int(ring.sum()))
    clean = visible_roi >= 0.85 * roi_area and global_change < 0.25 and ring_change < 0.35
    blob = None
    roi_changed = np.uint8(((changed > 0) & (zones.roi > 0)) * 255)
    contours, _ = cv2.findContours(roi_changed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    significant = [c for c in contours if cv2.contourArea(c) >= 0.02 * roi_area]
    if significant:
        blob = [int(v) for v in cv2.boundingRect(np.vstack(significant))]
    return dict(
        clean=clean,
        roi_change=round(roi_change, 4),
        global_change=round(global_change, 4),
        ring_change=round(ring_change, 4),
        shift=[round(dx, 1), round(dy, 1)],
        scale=round(scale, 3),
        registration=status,
        change_blob=blob,
    )


def _exit_mode(zones, box):
    fx, fy = foot(box)
    if zones.contains("DOOR_THRESHOLD_PLANE", (fx, fy)):
        return "DOOR"
    x, y, w, h = box
    m = 0.02
    border = x <= m * zones.w or x + w >= (1 - m) * zones.w or y + h >= (1 - m) * zones.h
    if zones.contains("STREET_PERIMETER", (fx, fy)) or border:
        return "STREET"
    return "UNRESOLVED"


def _porch_verdict(clip, zones, records, tracks, has_baseline):
    mode = clip["mode"]
    n = len(records)
    usable = sum(r["usable"] for r in records)
    moving = {tr["track_id"]: tr for tr in tracks if not tr["static"] and tr["frames"] >= 2}
    contacts = {}
    for r in records:
        for d in r["persons"]:
            tid = d.get("track_id")
            if tid in moving and d["score"] >= 0.3 and zones.box_touches_roi(d["box"]):
                contacts.setdefault(tid, []).append(r["index"])
    actor = None
    if contacts:
        actor = max(contacts, key=lambda tid: (max(contacts[tid]), len(contacts[tid])))
    last_contact = max(contacts[actor]) if actor else -1
    out = dict(
        actor_track_id=actor,
        roi_contact_frames=len(contacts.get(actor, [])),
        static_tracks_ignored=[tr["track_id"] for tr in tracks if tr["static"]],
        exit_mode=None,
        actor_trajectory_px=moving[actor]["trajectory_px"] if actor else [],
        detector_support=[],
    )
    if usable < 3:
        return dict(out, verdict="UNKNOWN", result=None, confidence=0.0, reason="CAMERA_UNAVAILABLE")
    if not has_baseline:
        return dict(out, verdict="UNKNOWN", result=None, confidence=0.0, reason="NO_PERSON_FREE_BASELINE")
    post = [r for r in records if r["index"] > last_contact and r.get("clean")]
    end = post[-4:]
    end_change = float(np.median([r["roi_change"] for r in end])) if end else None
    stable = (
        bool(end)
        and len(end) >= 2
        and max(r["roi_change"] for r in end) - min(r["roi_change"] for r in end) < 0.05
    )
    support = sorted(
        {
            d["label"]
            for r in end
            for d in r["items"]
            if zones.contains("PORCH_DEPOSIT_ROI", center(d["box"])) and d["score"] >= 0.3
        }
    )
    out.update(roi_change_final=None if end_change is None else round(end_change, 4), end_frames=len(end))
    out["detector_support"] = support
    out["change_blob_px"] = end[-1].get("change_blob") if end else None
    if actor:
        last_box = moving[actor]["boxes"][-1][1]
        departed = moving[actor]["last_index"] <= n - 3
        out["exit_mode"] = _exit_mode(zones, last_box)
        if not departed and out["exit_mode"] != "STREET":
            return dict(out, verdict="UNKNOWN", result=None, confidence=0.3, reason="ACTOR_STILL_IN_VIEW")
    if mode == "porch_deposit":
        if not actor:
            return dict(out, verdict="UNKNOWN", result=None, confidence=0.2, reason="NO_COURIER_AT_PORCH")
        if len(end) < 2:
            return dict(
                out, verdict="UNKNOWN", result=None, confidence=0.3, reason="NO_CLEAR_VIEW_AFTER_DEPARTURE"
            )
        if end_change >= 0.06 and stable:
            conf = (
                0.6 + 0.2 * min(1.0, (end_change - 0.06) / 0.14) + 0.1 * (len(end) >= 3) + 0.1 * bool(support)
            )
            return _gate(out, "DEPOSIT_CONFIRMED", conf, "PERSISTENT_OBJECT_IN_ROI_AFTER_DEPARTURE")
        if end_change <= 0.02 and stable:
            conf = 0.6 + 0.2 * min(1.0, out["roi_contact_frames"] / 5) + 0.15 * (1 - end_change / 0.02)
            return _gate(out, "MISMATCH", conf, "COURIER_DEPARTED_NO_RESTING_OBJECT_IN_ROI")
        return dict(out, verdict="UNKNOWN", result=None, confidence=0.4, reason="ROI_CHANGE_INCONCLUSIVE")
    # porch_watchdog: the baseline already contains the custodied parcel.
    if not actor:
        if len(end) < 2:
            return dict(out, verdict="UNKNOWN", result=None, confidence=0.2, reason="NO_CLEAR_VIEW_OF_ROI")
        if end_change <= 0.04:
            return dict(out, verdict="NO_REMOVAL", result=None, confidence=0.8, reason="NO_PORCH_INTERACTION")
        return dict(out, verdict="UNKNOWN", result=None, confidence=0.3, reason="UNEXPLAINED_ROI_CHANGE")
    if len(end) < 2:
        return dict(
            out, verdict="UNKNOWN", result=None, confidence=0.3, reason="NO_CLEAR_VIEW_AFTER_DEPARTURE"
        )
    if end_change <= 0.04 and stable:
        return dict(out, verdict="NO_REMOVAL", result=None, confidence=0.75, reason="PARCEL_REGION_UNCHANGED")
    if end_change >= 0.06 and stable:
        conf = (
            0.6 + 0.2 * min(1.0, (end_change - 0.06) / 0.14) + 0.1 * (out["roi_contact_frames"] >= 2) + 0.05
        )
        if out["exit_mode"] == "STREET":
            return _gate(out, "REMOVAL_UNDER_REVIEW", conf, "ROI_EMPTIED_ACTOR_EXITED_STREETWARD")
        if out["exit_mode"] == "DOOR":
            return _gate(out, "TRANSFER_OBSERVED", conf, "ROI_EMPTIED_ACTOR_EXITED_THROUGH_DOOR")
        return dict(out, verdict="UNKNOWN", result=None, confidence=0.4, reason="EXIT_DIRECTION_UNRESOLVED")
    return dict(out, verdict="UNKNOWN", result=None, confidence=0.4, reason="ROI_CHANGE_INCONCLUSIVE")


def _gate(out, verdict, conf, reason):
    conf = round(min(0.95, conf), 3)
    if conf < 0.6:
        return dict(out, verdict="UNKNOWN", result=None, confidence=conf, reason="LOW_CONFIDENCE:" + reason)
    return dict(out, verdict=verdict, result=None, confidence=conf, reason=reason)


def _threshold(clip, detector, frames):
    h, w = frames[0][1].shape[:2]
    zones = Zones(clip["zones"], w, h)
    diag = (w * w + h * h) ** 0.5
    tracker = Tracker(diag, max_gap=max(3, int(clip["analysis_fps"] * 1.6)))
    records, keep = [], {}
    for index, (t, frame) in enumerate(frames):
        usable = _usable(frame)
        dets = detector.detect(frame) if usable else []
        persons = [d for d in dets if d["label"] == "person" and d["score"] >= 0.25]
        ids = tracker.update(index, t, persons)
        for d, tid in zip(persons, ids):
            d["track_id"] = tid
            d["items"] = []
            if d["score"] >= 0.35 and d["box"][3] >= 0.15 * h:
                d["items"] = detector.carried_items(frame, d["box"])
                for item in (x for x in dets if x["label"] in DRINKS | CARRIERS):
                    if zones_overlap(item["box"], d["box"]) and item not in d["items"]:
                        d["items"].append(item)
        records.append(dict(index=index, t=t, persons=persons, usable=usable))
        drink = [i for d in persons for i in d["items"] if i["label"] in DRINKS]
        if drink and ("event" not in keep or max(i["score"] for i in drink) > keep["event"][2]):
            keep["event"] = (index, frame, max(i["score"] for i in drink))
        if persons and ("person" not in keep or max(d["score"] for d in persons) > keep["person"][2]):
            keep["person"] = (index, frame, max(d["score"] for d in persons))
    tracks = tracker.summarize()
    out = _threshold_verdict(zones, records, tracks)
    out["tracks"] = [{k: v for k, v in tr.items() if k != "boxes"} for tr in tracks]
    out["_records"] = records
    out["_track_boxes"] = {tr["track_id"]: tr["boxes"] for tr in tracks}
    event = keep.get("event") or keep.get("person")
    out["_keyframes"] = {"event": event[0]} if event else {}
    return out


def zones_overlap(a, b):
    cx, cy = center(a)
    return b[0] <= cx <= b[0] + b[2] and b[1] <= cy <= b[1] + b[3]


def _threshold_verdict(zones, records, tracks):
    usable = sum(r["usable"] for r in records)
    moving = [tr for tr in tracks if not tr["static"]]
    out = dict(
        subject_track_id=None, subject_frames=0, drink_frames=0, carrier_frames=0, threshold_reached=False
    )
    if usable < 3:
        return dict(out, result="CAMERA_UNAVAILABLE", verdict=None, confidence=0.0, reason="NO_USABLE_FRAMES")
    if not moving:
        return dict(
            out, result="AMBIGUOUS", verdict=None, confidence=0.3, reason="NO_ARRIVING_PERSON_TRACKED"
        )
    subject = max(moving, key=lambda tr: (tr["frames"], tr["mean_score"]))
    sid = subject["track_id"]
    drink_frames = carrier_frames = 0
    drink_scores, carriers = [], set()
    for r in records:
        for d in r["persons"]:
            if d.get("track_id") != sid:
                continue
            labels = {i["label"] for i in d["items"]}
            if labels & DRINKS:
                drink_frames += 1
                drink_scores.append(max(i["score"] for i in d["items"] if i["label"] in DRINKS))
            elif labels & CARRIERS:
                carrier_frames += 1
                carriers |= labels & CARRIERS
    frames = subject["frames"]
    out.update(
        subject_track_id=sid,
        subject_frames=frames,
        subject_mean_score=subject["mean_score"],
        drink_frames=drink_frames,
        drink_max_score=round(max(drink_scores), 3) if drink_scores else 0.0,
        carrier_frames=carrier_frames,
        carriers_seen=sorted(carriers),
        subject_trajectory_px=subject["trajectory_px"],
        threshold_reached=any(
            zones.contains("DOOR_THRESHOLD_PLANE", (x, y)) for _, x, y in subject["trajectory_px"]
        ),
    )
    ratio = drink_frames / frames if frames else 0.0
    if drink_frames >= 3 and ratio >= 0.15 and max(drink_scores) >= 0.3:
        conf = round(min(0.95, 0.55 + 0.4 * min(1.0, ratio / 0.5)), 3)
        return dict(
            out, result="VISIBLE_MATCH", verdict=None, confidence=conf, reason="DRINK_CLASS_ON_SUBJECT"
        )
    if drink_frames:
        return dict(out, result="AMBIGUOUS", verdict=None, confidence=0.4, reason="SPORADIC_DRINK_DETECTIONS")
    if carrier_frames >= 2:
        return dict(
            out, result="AMBIGUOUS", verdict=None, confidence=0.5, reason="CARRIER_VISIBLE_CONTENTS_UNKNOWN"
        )
    if frames >= 8 and subject["mean_score"] >= 0.45:
        conf = round(min(0.9, 0.5 + 0.02 * frames + 0.2 * (subject["mean_score"] - 0.45)), 3)
        return dict(
            out, result="NOT_VISIBLE", verdict=None, confidence=conf, reason="SUBJECT_TRACKED_NO_ITEM_SEEN"
        )
    return dict(out, result="AMBIGUOUS", verdict=None, confidence=0.3, reason="SUBJECT_POORLY_OBSERVED")


@lru_cache(maxsize=16)
def _cached(clip_id, model_sha):
    return analyze_clip(clip_config(clip_id))


def analyze_fixture(clip_id):
    """Analyze a committed fixture (cached per process). Returns a private deep copy."""
    return copy.deepcopy(_cached(clip_id, MODEL_SHA256))


def public(result):
    """Strip internal per-frame records; keep everything an auditor needs."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


# --------------------------------------------------------------------------- rendering


COLORS = {
    "STREET_PERIMETER": (235, 160, 60),
    "PORCH_DEPOSIT_ROI": (40, 170, 255),
    "DOOR_THRESHOLD_PLANE": (90, 220, 120),
}


def _frame_at(clip, index):
    frames, _, _ = sampled_frames(FIXTURES / clip["file"], clip["analysis_fps"])
    return frames[min(index, len(frames) - 1)][1] if frames else None


def annotate(clip, result, frame, index):
    out = frame.copy()
    h, w = out.shape[:2]
    zones = Zones(clip["zones"], w, h)
    overlay = out.copy()
    for name, color in COLORS.items():
        p = zones.poly[name]
        if len(p) >= 3:
            cv2.polylines(overlay, [p], True, color, 2)
            cv2.putText(overlay, name, tuple(int(v) for v in p[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
    for m in zones.masks:
        cv2.fillPoly(overlay, [m], (60, 60, 60))
    cv2.addWeighted(overlay, 0.75, out, 0.25, 0, out)
    record = next((r for r in result.get("_records", []) if r["index"] == index), None)
    if record:
        for d in record["persons"]:
            x, y, bw, bh = d["box"]
            cv2.rectangle(out, (x, y), (x + bw, y + bh), (255, 255, 255), 2)
            cv2.putText(out, f"{d.get('track_id')} person {d['score']:.2f}", (x, max(12, y - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)  # fmt: skip
            for i in d.get("items", []):
                ix, iy, iw, ih = i["box"]
                cv2.rectangle(out, (ix, iy), (ix + iw, iy + ih), (0, 230, 255), 2)
                cv2.putText(out, f"{i['label']} {i['score']:.2f}", (ix, max(12, iy - 3)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 230, 255), 1)  # fmt: skip
        for i in record.get("items", []):
            ix, iy, iw, ih = i["box"]
            cv2.rectangle(out, (ix, iy), (ix + iw, iy + ih), (200, 120, 255), 1)
        blob = record.get("change_blob")
        if blob:
            cv2.rectangle(out, (blob[0], blob[1]), (blob[0] + blob[2], blob[1] + blob[3]), (0, 0, 255), 2)
            cv2.putText(out, "ROI change (parcel-candidate region)", (blob[0], blob[1] + blob[3] + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)  # fmt: skip
    path = result.get("actor_trajectory_px") or result.get("subject_trajectory_px") or []
    if len(path) >= 2:
        cv2.polylines(out, [np.array([[x, y] for _, x, y in path], np.int32)], False, (255, 0, 255), 2)
    label = result.get("verdict") or result.get("result")
    lines = [
        (f"{SOURCE} | {clip['id']}", (230, 230, 230)),
        (
            f"{label} (conf {result.get('confidence', 0):.2f}) t={record['t'] if record else '?'}s",
            (120, 255, 160),
        ),
        ("public licensed clip - not Ring, not this household - pixel paths only", (180, 200, 230)),
    ]
    cv2.rectangle(out, (0, h - 14 * len(lines) - 6), (w, h), (20, 20, 20), -1)
    for i, (text, color) in enumerate(lines):
        y = h - 14 * (len(lines) - i) + 6
        cv2.putText(out, text, (6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.36, color, 1)
    return out


def jpeg(frame, quality=82):
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return bytes(buf)


def keyframe_index(result):
    k = result.get("_keyframes", {})
    if result.get("verdict") == "DEPOSIT_CONFIRMED" and "final" in k:
        return k["final"]
    return k.get("event", k.get("final", 0))


def render_keyframe(clip, result, index=None):
    index = keyframe_index(result) if index is None else index
    frame = _frame_at(clip, index)
    if frame is None:
        return None
    return dict(
        index=index, original=jpeg(frame), annotated=jpeg(annotate(clip, result, frame, index)), frame=frame
    )


def person_crop(clip, result):
    """Best-scoring actor box from an original frame. No face/identity processing."""
    tid = result.get("actor_track_id") or result.get("subject_track_id")
    boxes = result.get("_track_boxes", {}).get(tid) or []
    if not boxes:
        return None
    records = {r["index"]: r for r in result.get("_records", [])}
    best = max(
        boxes,
        key=lambda b: next(
            (d["score"] for d in records.get(b[0], {}).get("persons", []) if d["box"] == b[1]), 0
        ),
    )
    frame = _frame_at(clip, best[0])
    x, y, w, h = best[1]
    crop = frame[max(0, y) : y + h, max(0, x) : x + w]
    return jpeg(crop) if crop.size else None


def annotated_video(clip, result):
    """Derived annotated clip (WebM) at the analysis rate; None when ffmpeg is unavailable."""
    if not shutil.which("ffmpeg"):
        return None
    frames, _, _ = sampled_frames(FIXTURES / clip["file"], clip["analysis_fps"])
    if not frames:
        return None
    h, w = frames[0][1].shape[:2]
    raw = b"".join(annotate(clip, result, f, i).tobytes() for i, (_, f) in enumerate(frames))
    with tempfile.TemporaryDirectory(prefix="done-irl-scene-") as temp:
        path = Path(temp) / "annotated.webm"
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
            "-pixel_format", "bgr24", "-video_size", f"{w}x{h}", "-framerate", str(clip["analysis_fps"]),
            "-i", "pipe:0", "-an", "-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "5",
            "-b:v", "400k", str(path),
        ]  # fmt: skip
        done = subprocess.run(command, input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        if done.returncode:
            return None
        return path.read_bytes()


# --------------------------------------------------------------------------- engine stages


def observe(stage, branch):
    clip_id = clip_for(stage, branch)
    return clip_config(clip_id), analyze_fixture(clip_id)


def _sensor():
    return dict(platform=SOURCE, source_mode=SOURCE, model=f"{MODEL_NAME}+{PIPELINE_VERSION}")


def record_observation(e, s, db, household, c, clip, result, kind):
    """Persist original frame, annotated derived frame (parent-linked) and the observation summary."""
    sensor, conf = _sensor(), float(result.get("confidence") or 0.0)
    ids = {}
    key = render_keyframe(clip, result)
    if key:
        ids["source_frame"] = e.add_evidence(
            s, db, household, c, kind + "_SOURCE_FRAME", key["original"], "image/jpeg",
            provenance=SOURCE, sensor=sensor, confidence=conf,
        )  # fmt: skip
        ids["annotated_frame"] = e.add_evidence(
            s, db, household, c, kind + "_ANNOTATED_FRAME", key["annotated"], "image/jpeg",
            provenance=SOURCE, sensor=sensor, parent_evidence_id=ids["source_frame"], confidence=conf,
        )  # fmt: skip
    summary = public(result)
    summary["evidence_frame_index"] = key["index"] if key else None
    summary["fixture_sha256"] = _sha(FIXTURES / clip["file"])
    ids["observation"] = e.add_evidence(
        s, db, household, c, kind, summary, provenance=SOURCE, sensor=sensor,
        parent_evidence_id=ids.get("source_frame"), confidence=conf,
    )  # fmt: skip
    e.emit(
        s,
        "vision.scene_observed",
        dict(
            contract_id=c["contract_id"],
            source=SOURCE,
            clip_id=clip["id"],
            verdict=result.get("verdict") or result.get("result"),
            confidence=conf,
            reason=result.get("reason"),
            evidence_id=ids["observation"],
            world_trajectory=WORLD,
        ),
    )
    return ids


def real_deposit_stage(s, db, household, c, branch):
    from . import engine as e

    clip, result = observe(2, branch)
    verdict = result["verdict"]
    ids = record_observation(e, s, db, household, c, clip, result, "DEPOSIT_OBSERVATION")
    c["scene_source"] = dict(
        source=SOURCE, clip_id=clip["id"], verdict=verdict, confidence=result["confidence"]
    )
    if verdict == "DEPOSIT_CONFIRMED":
        c.update(deposit_status="DEPOSIT_VERIFIED", custody_status="DEPOSIT_VERIFIED_CUSTODY_ACTIVE")
        c["evidence_ids"].append(ids["observation"])
        roi = clip["zones"]["PORCH_DEPOSIT_ROI"]
        xs, ys = [p[0] for p in roi], [p[1] for p in roi]
        s["subagents"].append(
            dict(
                subagent_id="porch_parcel",
                kind="PorchWatchdog",
                contract_id=c["contract_id"],
                status="WATCHING",
                last_observation_at=s["now"],
                restart_cursor="deposit-real-v1",
                target_roi=[min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)],
                source=SOURCE,
                observation_gaps=[
                    "Event-driven monitoring; no continuous camera coverage.",
                    "Recorded public stock clip; later stages replay independent scenes.",
                ],
            )
        )
        e.emit(
            s, "parcel.deposit_verified", dict(contract_id=c["contract_id"], evidence_id=ids["observation"])
        )
        e.alert(
            s,
            c,
            "DEPOSIT_OBSERVED",
            "Parcel was observed on the porch (recorded stock clip). PorchWatchdog is active; custody is not complete.",
        )
    elif verdict == "MISMATCH":
        c.update(deposit_status="DELIVERY_MISMATCH", custody_status="UNCONFIRMED")
        e.revise(s, c, "DISPUTED", "Courier departure did not establish deposit (recorded clip).")
        e.alert(
            s,
            c,
            "DELIVERY_MISMATCH",
            "Courier said the package was left, but I could not confirm a deposit. Review the camera evidence.",
        )
    else:
        c.update(deposit_status="DEPOSIT_UNCONFIRMED", custody_status="UNCONFIRMED")
        e.alert(
            s,
            c,
            "DEPOSIT_REVIEW",
            "I couldn't tell whether a parcel was left. Please review the camera evidence.",
        )


def real_watchdog_stage(s, db, household, c, branch):
    from . import engine as e

    clip, result = observe(4, branch)
    verdict = result["verdict"]
    for a in s["subagents"]:
        if a["kind"] == "PorchWatchdog" and a["status"] == "WATCHING":
            a["last_observation_at"] = s["now"]
    if verdict == "REMOVAL_UNDER_REVIEW" and s["incidents"]:
        return
    ids = record_observation(e, s, db, household, c, clip, result, "REMOVAL_OBSERVATION")
    if verdict != "REMOVAL_UNDER_REVIEW":
        e.emit(
            s,
            "watchdog.observation_updated",
            dict(contract_id=c["contract_id"], result=verdict, source=SOURCE, evidence_id=ids["observation"]),
        )
        if verdict == "TRANSFER_OBSERVED":
            c["transfer_observation"] = "TRANSFER_OBSERVED_PENDING_OWNER_CONFIRMATION"
            e.alert(
                s,
                c,
                "PORCH_TRANSFER_OBSERVED",
                "Someone carried the package inside. Confirm it was your household to close custody.",
            )
        elif verdict == "UNKNOWN":
            e.alert(
                s, c, "PORCH_REVIEW", "Porch activity could not be interpreted. Review the camera evidence."
            )
        return
    sensor = _sensor()
    crop = person_crop(clip, result)
    crop_ev = (
        e.add_evidence(
            s,
            db,
            household,
            c,
            "PERSON_CROP",
            crop,
            "image/jpeg",
            provenance=SOURCE,
            sensor=sensor,
            parent_evidence_id=ids.get("source_frame"),
            confidence=result["confidence"],
        )  # fmt: skip
        if crop
        else None
    )
    clip_bytes = (FIXTURES / clip["file"]).read_bytes()
    duration_ms = int(round((clip["trim"]["end"] - clip["trim"]["start"]) * 1000))
    source_clip = e.add_evidence(
        s, db, household, c, "REMOVAL_CLIP_ORIGINAL", clip_bytes, "video/mp4", provenance=SOURCE,
        duration_ms=duration_ms, sensor=sensor,
    )  # fmt: skip
    video = annotated_video(clip, result)
    annotated_clip = (
        e.add_evidence(
            s,
            db,
            household,
            c,
            "REMOVAL_CLIP_DERIVED",
            video,
            "video/webm",
            provenance=SOURCE,
            duration_ms=duration_ms,
            parent_evidence_id=source_clip,
            sensor=sensor,
        )  # fmt: skip
        if video
        else None
    )
    gaps = [
        "REAL_RECORDED_STOCK public clip: not Ring, not this household, independent of the deposit scene."
    ]
    if duration_ms < 15000:
        gaps.append(f"Only {duration_ms / 1000:.1f}s of footage exists; a 15-second segment is unavailable.")
    if not video:
        gaps.append("Annotated derived clip unavailable (encoder missing); annotated keyframe only.")
    packet = {
        "deposit_evidence_ids": c["evidence_ids"][:],
        "removal_evidence_id": ids["observation"],
        "source_frame_evidence_id": ids.get("source_frame"),
        "annotated_frame_evidence_id": ids.get("annotated_frame"),
        "source_clip_evidence_id": source_clip,
        "annotated_clip_evidence_id": annotated_clip,
        "person_crop_evidence_id": crop_ev,
        "trajectory": [[x, y] for _, x, y in result.get("actor_trajectory_px", [])],
        "trajectory_timestamps_s": [t for t, _, _ in result.get("actor_trajectory_px", [])],
        "coordinate_system": "IMAGE_PIXELS",
        "world_trajectory": WORLD,
        "model": dict(name=MODEL_NAME, sha256=MODEL_SHA256, confidence=result["confidence"]),
        "source": dict(label=SOURCE, clip_id=clip["id"], **result["attribution"]),
        "capture_gaps": gaps,
    }
    incident = dict(
        incident_id="inc_parcel",
        contract_id=c["contract_id"],
        status="AWAITING_HUMAN_DECISION",
        detected_at=s["now"],
        source_mode=SOURCE,
        packet=packet,
        manifest_hash=e.digest(packet),
        revision=1,
        receipt=None,
        approval=None,
        clip_actual_duration_seconds=round(duration_ms / 1000, 2),
        quality="REAL_RECORDED_CLIP_AVAILABLE" if duration_ms >= 15000 else "EVIDENCE_INCOMPLETE",
        destination="DEMO_RECEIVER_ONLY",
    )
    s["incidents"].append(incident)
    c["custody_status"] = "REMOVAL_UNDER_REVIEW"
    e.revise(
        s, c, "DISPUTED", "Observed streetward removal in recorded clip. Authorization requires owner review."
    )
    e.emit(s, "parcel.removal_observed", dict(incident_id=incident["incident_id"], source=SOURCE))
    e.alert(s, c, "PORCH_REMOVAL", "A person moved the package from the porch. Was this authorized?")


def real_threshold_stage(s, db, household, c, branch):
    from . import engine as e

    clip, result = observe(5, branch)
    outcome = result["result"]
    ids = record_observation(e, s, db, household, c, clip, result, "THRESHOLD_OBSERVATION")
    c.update(
        visibility=outcome,
        visibility_source=SOURCE,
        observation_status="SUPPORTING_OBSERVATION" if outcome == "VISIBLE_MATCH" else "NEEDS_USER_CHECK",
    )
    c["evidence_ids"].append(ids["observation"])
    e.emit(
        s,
        "threshold.item_visible" if outcome == "VISIBLE_MATCH" else "threshold.item_not_visible",
        dict(
            result=outcome,
            contract_id=c["contract_id"],
            source=SOURCE,
            confidence=result["confidence"],
            latency_ms=None,
            timing="Recorded clip replay; no before-entry latency claim",
        ),
    )
    if outcome != "VISIBLE_MATCH":
        e.alert(
            s,
            c,
            "ARRIVAL_ITEM_CHECK",
            "Your drinks weren't visible as you approached the door. Check whether you have them.",
        )
