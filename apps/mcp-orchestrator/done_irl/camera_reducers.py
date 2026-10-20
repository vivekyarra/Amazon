"""Authorized camera callbacks; atomic state transitions share the normal pose verifier."""

from datetime import datetime, timezone

from . import engine as e
from . import privacy
from .models import ApiError


def frame_received(store, household, camera, frame, points, timestamp, frame_hash):
    with store.transaction() as db:
        state = store.read(household)
        if not state or not state["consent"]:
            raise ApiError(409, "CONSENT_REVOKED", "Camera processing has stopped.")
        # Exclusion/disconnect is rechecked per frame inside the same transaction as any evidence.
        if camera.get("device_id"):
            privacy.require_camera_allowed(state, camera["device_id"])
        privacy.require_provider(state, "ring")
        session = state["studio"]
        if not session or session.get("camera_id") != camera["id"]:
            raise ApiError(409, "CAMERA_SESSION_CHANGED", "Camera session is no longer current.")
        if session["status"] in {"COMPLETED", "OVERRIDDEN"}:
            return summary(session)
        # The server-side bridge, never a client field, decides the source label.
        recorded = camera.get("source") == e.RECORDED_DEMO_SOURCE
        source_mode = "SIMULATED_VERIFIED" if recorded else "LIVE_VERIFIED"
        session.update(
            source=e.RECORDED_DEMO_SOURCE if recorded else "LIVE_RING_WHEP",
            source_mode=source_mode,
            model_sha256=camera["model_sha256"],
        )
        timestamp += session["timestamp_base"]
        if state.get("clock_mode") == "WALL":
            state["now"] = datetime.now(timezone.utc).isoformat()
        state["_event_source"] = {
            "source": e.RECORDED_DEMO_SOURCE if recorded else "RING_WHEP",
            "source_mode": source_mode,
            "consent_scope": "household",
        }
        if points:
            # A fresh decoder frame and a fresh pose are both required. Recorded duplicate frames
            # reset the phase even if model jitter could otherwise create a new landmark signature.
            hashes = session.setdefault("seen_video_hashes", [])
            if frame_hash in hashes:
                session.update(phase="STANDING", stable=0, quality="DUPLICATE_VIDEO_FRAME")
            else:
                hashes.append(frame_hash)
                del hashes[:-900]
                corrected = [[p[0], p[1] * frame.shape[0] / frame.shape[1], p[2], p[3]] for p in points]
                # Include the current rep's provenance before the 15th-cycle evidence is committed.
                before = session["count"]
                proof = {
                    "frame_sha256": frame_hash,
                    "timestamp_ms": timestamp,
                    "camera_session_id": camera["id"],
                }
                session.setdefault("verified_reps", []).append(proof)
                rep = e.pose_frame(
                    state, db, household, camera["id"] + ":" + str(timestamp), timestamp, corrected
                )
                if not rep:
                    session["verified_reps"].pop()
                elif session["count"] != before + 1:
                    raise ApiError(409, "POSE_COUNT_INVALID", "Verifier count did not advance correctly.")
                session["landmarks"] = points
        else:
            session.update(
                phase="STANDING", stable=0, quality="POSE_UNAVAILABLE", last_timestamp_ms=timestamp
            )
        state.pop("_event_source", None)
        store.save(db, household, state)
        return summary(session)


def summary(session):
    """Read-only counter snapshot for overlays; the reducer above is the only writer."""
    return {k: session.get(k) for k in ("count", "gate", "phase", "angle", "quality", "status")}


def camera_ended(store, household, camera_id, reason):
    with store.transaction() as db:
        state = store.read(household)
        if not state or not state["studio"] or state["studio"].get("camera_id") != camera_id:
            return
        session = state["studio"]
        if session["status"] not in {"COMPLETED", "OVERRIDDEN"}:
            session.update(status="PAUSED", phase="STANDING", stable=0, quality=reason)
        state.setdefault("camera_request", {})["status"] = "CLOSED"
        e.emit(
            state,
            "watchdog.monitoring_gap",
            {"contract_id": session["contract_id"], "camera_session_id": camera_id, "reason": reason},
        )
        store.save(db, household, state)
