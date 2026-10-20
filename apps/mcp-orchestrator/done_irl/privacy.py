"""Owner privacy controls (spec 11.1 PRIVATE_MASKS, 12.1, 12.2, 12.4).

Per-camera exclusion, private masks, adjustable evidence retention, provider disconnect and
household deletion. Settings live inside the household's encrypted ledger aggregate; every
change is an owner-authenticated, idempotent command that emits an audit event.

Honest limits (documented in docs/privacy-security.md):
- Provider credentials are server-provisioned secrets (environment/secret store), never stored in
  the ledger. Disconnect removes the household's connection records (cursors, queued inbox work,
  in-process Bee token copy, live Ring session) and enforces revocation at every entry point; it
  cannot revoke upstream tokens at Amazon/Ring and does not erase the operator's secret store.
- Masks zero pixels in frames used for detection, live relay output and stored derived evidence
  (snapshots, crops, annotated clips) before encoding/hashing. The synthetic source clip
  (REMOVAL_CLIP_ORIGINAL) is preserved unmasked under AES-256-GCM as the chain-of-custody original.
"""

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, Request
from pydantic import Field, field_validator

from .models import ApiError, StrictModel

SYNTHETIC_CAMERA = "synthetic-porch"
PROVIDERS = ("bee", "ring")
DEFAULT_RETENTION_DAYS = 7
MIN_RETENTION_DAYS, MAX_RETENTION_DAYS = 1, 30
DELETE_PHRASE = "DELETE ALL HOUSEHOLD DATA"


class CameraExclusionInput(StrictModel):
    device_id: str = Field(min_length=1, max_length=200)
    excluded: bool


class MaskInput(StrictModel):
    device_id: str = Field(min_length=1, max_length=200)
    polygons: list[list[list[float]]] = Field(max_length=16)
    # Optimistic concurrency against the current calibration revision.
    revision: int | None = Field(default=None, ge=0)

    @field_validator("polygons")
    @classmethod
    def normalized(cls, polygons):
        for polygon in polygons:
            if not 3 <= len(polygon) <= 64:
                raise ValueError("Each polygon needs 3 to 64 points.")
            for point in polygon:
                if len(point) != 2 or not all(math.isfinite(v) and 0 <= v <= 1 for v in point):
                    raise ValueError("Points must be normalized [x, y] pairs in [0, 1].")
        return polygons


class RetentionInput(StrictModel):
    days: int = Field(ge=MIN_RETENTION_DAYS, le=MAX_RETENTION_DAYS)


class DeletionInput(StrictModel):
    household_id: str = Field(min_length=1, max_length=200)
    confirmation: str = Field(min_length=1, max_length=200)


def _defaults():
    return {"excluded_cameras": [], "masks": {}, "retention_days": DEFAULT_RETENTION_DAYS, "providers": {}}


def view(s):
    """Read-only settings view; never mutates the aggregate."""
    return {**_defaults(), **((s or {}).get("privacy") or {})}


def settings(s):
    current = s.setdefault("privacy", {})
    for key, value in _defaults().items():
        current.setdefault(key, value)
    return current


def camera_excluded(s, device):
    return device in view(s)["excluded_cameras"]


def provider_revoked(s, provider):
    return view(s)["providers"].get(provider, {}).get("status") == "REVOKED"


def require_camera_allowed(s, device):
    if camera_excluded(s, device):
        raise ApiError(409, "CAMERA_EXCLUDED", "The owner excluded this camera; no collection is allowed.")


def require_provider(s, provider):
    if provider_revoked(s, provider):
        raise ApiError(
            409, "PROVIDER_DISCONNECTED", "The owner disconnected this provider; re-authorize it explicitly."
        )


def inbox_block_reason(s, provider, payload):
    """Reason a received provider event must not become an observation, if any."""
    if provider_revoked(s, provider):
        return "PROVIDER_DISCONNECTED"
    if provider == "ring":
        try:
            device = payload["data"]["attributes"]["source"]
        except (KeyError, TypeError):
            return None
        if camera_excluded(s, device):
            return "CAMERA_EXCLUDED"
    return None


def camera_session_blocked(s, device):
    return provider_revoked(s, "ring") or camera_excluded(s, device)


def polygons(s, device):
    mask = view(s)["masks"].get(device)
    if not mask:
        return ()
    return tuple(tuple(tuple(point) for point in polygon) for polygon in mask["polygons"])


def apply_masks(frame, regions):
    """Return a copy with every normalized polygon region set to zero (black)."""
    if not regions:
        return frame
    import cv2
    import numpy as np

    out = frame.copy()
    h, w = out.shape[:2]
    shapes = [np.round(np.array(polygon, dtype=np.float64) * [w, h]).astype(np.int32) for polygon in regions]
    cv2.fillPoly(out, shapes, (0,) * (out.shape[2] if out.ndim == 3 else 1))
    return out


def mask_frame(s, device, frame):
    regions = polygons(s, device)
    mask = view(s)["masks"].get(device) or {}
    meta = {
        "camera_device_id": device,
        "calibration_revision": mask.get("calibration_revision", 0),
        "masked_regions": len(regions),
        "scope": "DERIVED_PIXELS_ZEROED_BEFORE_ENCODE_AND_HASH",
    }
    return apply_masks(frame, regions), meta


def retention_days(s):
    return view(s)["retention_days"]


def _delete_artifact(db, household, item, now):
    deleted = db.execute(
        "DELETE FROM artifacts WHERE id=? AND household=?", (item["evidence_id"], household)
    ).rowcount
    if deleted:
        db.execute(
            "INSERT OR IGNORE INTO retention_tombstones VALUES (?,?,?,?)",
            (item["evidence_id"], household, item["sha256_original"], now.timestamp()),
        )
    return deleted


def apply_retention(s, db, household, days, now=None):
    """Recompute effective expiry from each artifact's capture time; expired bytes are deleted now.

    The hash-chained manifest keeps the at-capture expiry in `retention_expires_at_original`
    (verify_artifacts uses it), so a policy change never rewrites the evidence chain. Artifacts
    already past expiry are never resurrected.
    """
    now = now or datetime.now(timezone.utc)
    updated = purged = 0
    for item in s["evidence"]:
        current = datetime.fromisoformat(item["retention_expires_at"])
        if current <= now:
            continue
        original = item.get("retention_expires_at_original", item["retention_expires_at"])
        captured_days = item.get("retention_days_at_capture", DEFAULT_RETENTION_DAYS)
        expiry = datetime.fromisoformat(original) - timedelta(days=captured_days) + timedelta(days=days)
        if expiry != current:
            item.setdefault("retention_expires_at_original", original)
            item["retention_expires_at"] = expiry.isoformat()
            updated += 1
        if expiry <= now:
            purged += _delete_artifact(db, household, item, now)
    return {"updated": updated, "purged": purged}


def known_cameras(household, demo):
    if demo:
        return [SYNTHETIC_CAMERA]
    path = os.getenv("RING_BINDINGS_FILE")
    if not path:
        return []
    try:
        bindings = json.loads(Path(path).read_text())
        return sorted(
            {
                device
                for binding in bindings.values()
                if binding["household"] == household
                for device in binding["devices"]
            }
        )
    except (OSError, ValueError, TypeError, KeyError):
        raise ApiError(503, "RING_BINDINGS_INVALID", "Camera bindings could not be loaded.") from None


def disconnect(s, db, household, provider):
    from . import engine as e

    privacy = settings(s)
    cursors = db.execute(
        "DELETE FROM provider_cursors WHERE household=? AND provider=?", (household, provider)
    ).rowcount
    cancelled = db.execute(
        "UPDATE inbox SET status='CANCELLED',payload=NULL,lease_until=NULL,error_code='PROVIDER_DISCONNECTED' "
        "WHERE household=? AND provider=? AND status IN ('PENDING','PROCESSING')",
        (household, provider),
    ).rowcount
    privacy["providers"][provider] = {
        "status": "REVOKED",
        "revoked_at": datetime.now(timezone.utc).isoformat(),
        "auto_reconnect": False,
    }
    if provider == "ring" and s.get("camera_request", {}).get("status") in {"PENDING", "CONNECTING", "OPEN"}:
        s["camera_request"]["status"] = "CLOSED"
    result = {
        "provider": provider,
        "status": "NOT_CONNECTED",
        "cancelled_inbox": cancelled,
        "cursors_removed": cursors,
    }
    e.emit(s, "privacy.provider_disconnected", result.copy())
    return result


def reauthorize(s, provider):
    from . import engine as e

    privacy = settings(s)
    if not provider_revoked(s, provider):
        raise ApiError(409, "PROVIDER_NOT_REVOKED", "This provider is not disconnected.")
    privacy["providers"][provider] = {
        "status": "OWNER_REAUTHORIZED",
        "reauthorized_at": datetime.now(timezone.utc).isoformat(),
    }
    e.emit(s, "privacy.provider_reauthorized", {"provider": provider, "requires_restart_for_streams": True})
    return {"provider": provider, "status": "OWNER_REAUTHORIZED"}


def delete_household(s, db, household, fresh_state):
    """Erase one household's content; leave a minimal receipt with counts only (no personal content)."""
    from . import engine as e
    from .aws_runtime import schedule_name

    schedules = sorted(
        {
            schedule_name(household, contract["contract_id"], job["kind"])
            for contract in s.get("contracts", [])
            for job in contract.get("scheduled_jobs", [])
        }
    )
    counts = {
        "contracts": len(s.get("contracts", [])),
        "evidence_records": len(s.get("evidence", [])),
        "incidents": len(s.get("incidents", [])),
        "subagents": len(s.get("subagents", [])),
        "schedules": sum(len(c.get("scheduled_jobs", [])) for c in s.get("contracts", [])),
        "events": len(s.get("events", [])),
    }
    for table, key in [
        ("artifacts", "evidence_artifacts"),
        ("retention_tombstones", "retention_tombstones"),
        ("inbox", "inbox_receipts"),
        ("provider_cursors", "provider_cursors"),
        ("commands", "command_responses"),
        ("cloud_outbox", "cloud_outbox"),
    ]:
        counts[key] = db.execute(f"DELETE FROM {table} WHERE household=?", (household,)).rowcount
    cloud = bool(os.getenv("AWS_LEDGER_TABLE"))
    if cloud:
        db.execute(
            "INSERT INTO cloud_deletions(household,schedules,requested) VALUES (?,?,?)",
            (household, json.dumps(schedules), datetime.now(timezone.utc).timestamp()),
        )
    previous = view(s)
    receipt = {
        "receipt_id": "del_" + uuid.uuid4().hex,
        "household_id": household,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "HOUSEHOLD_ONLY",
        "deleted": counts,
        "cloud_deletion": "QUEUED" if cloud else "NOT_CONFIGURED",
        "not_covered": [
            "Operator backups/snapshots and upstream provider-held data follow their own policies."
        ],
    }
    s.clear()
    s.update(fresh_state)
    s["household_id"] = household
    s["consent"] = False
    # Keep only non-content safety settings so deletion never re-enables collection.
    s["privacy"] = {
        **_defaults(),
        "excluded_cameras": previous["excluded_cameras"],
        "providers": previous["providers"],
        "retention_days": previous["retention_days"],
    }
    s["deletion_receipts"] = [receipt]
    e.emit(s, "privacy.household_deleted", receipt.copy())
    return receipt


def public(s, household, demo):
    privacy = view(s)
    return {
        "schema_version": "1.0",
        "household_id": household,
        "cameras": known_cameras(household, demo),
        "excluded_cameras": privacy["excluded_cameras"],
        "masks": privacy["masks"],
        "retention_days": privacy["retention_days"],
        "retention_bounds": [MIN_RETENTION_DAYS, MAX_RETENTION_DAYS],
        "providers": {name: privacy["providers"].get(name, {"status": "NOT_REVOKED"}) for name in PROVIDERS},
        "deletion_receipts": s.get("deletion_receipts", []),
        "delete_phrase": DELETE_PHRASE,
        "original_artifact_policy": "Source clips are kept unmasked under AES-256-GCM; derived snapshots, "
        "crops and annotated clips are masked before hashing.",
    }


def register(app, *, owner, command, initial, fresh, store, camera, bee, demo):
    """Attach owner-only privacy routes. All writes reuse the shared idempotent command path."""

    def bee_household():
        return os.getenv("BEE_HOUSEHOLD", "house_owner")

    def require_known(household, device):
        if device not in known_cameras(household, demo):
            raise ApiError(404, "CAMERA_NOT_FOUND", "This camera is not linked to your household.")

    @app.get("/api/privacy")
    def privacy_settings(p=Depends(owner)):
        s = initial(p["household"])
        return {**public(s, p["household"], demo), "trace_id": uuid.uuid4().hex}

    @app.post("/api/privacy/cameras/exclusion")
    async def camera_exclusion(body: CameraExclusionInput, request: Request, p=Depends(owner)):
        from . import engine as e

        require_known(p["household"], body.device_id)

        def op(s, db):
            privacy = settings(s)
            excluded = [d for d in privacy["excluded_cameras"] if d != body.device_id]
            if body.excluded:
                excluded.append(body.device_id)
            privacy["excluded_cameras"] = sorted(excluded)
            e.emit(
                s,
                "privacy.camera_exclusion_changed",
                {"device_id": body.device_id, "excluded": body.excluded},
            )
            return {"device_id": body.device_id, "excluded": body.excluded}

        response = command(request, p, op)
        if body.excluded and camera.status(p["household"]).get("device_id") == body.device_id:
            await camera.stop(p["household"], "CAMERA_EXCLUDED")
        return response

    @app.post("/api/privacy/cameras/masks")
    def camera_masks(body: MaskInput, request: Request, p=Depends(owner)):
        from . import engine as e

        require_known(p["household"], body.device_id)

        def op(s, db):
            privacy = settings(s)
            current = privacy["masks"].get(body.device_id, {}).get("calibration_revision", 0)
            if body.revision is not None and body.revision != current:
                raise ApiError(409, "REVISION_CONFLICT", "Reload the latest camera calibration first.")
            mask = {
                "calibration_revision": current + 1,
                "polygons": body.polygons,
                "coordinate_system": "NORMALIZED_IMAGE_XY",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            privacy["masks"][body.device_id] = mask
            e.emit(
                s,
                "privacy.masks_updated",
                {
                    "device_id": body.device_id,
                    "calibration_revision": mask["calibration_revision"],
                    "regions": len(body.polygons),
                    "polygons_sha256": hashlib.sha256(json.dumps(body.polygons).encode()).hexdigest(),
                },
            )
            return {"device_id": body.device_id, **mask}

        return command(request, p, op)

    @app.post("/api/privacy/retention")
    def retention(body: RetentionInput, request: Request, p=Depends(owner)):
        from . import engine as e

        def op(s, db):
            settings(s)["retention_days"] = body.days
            result = apply_retention(s, db, p["household"], body.days)
            e.emit(s, "privacy.retention_changed", {"days": body.days, **result})
            return {"days": body.days, **result}

        return command(request, p, op)

    @app.post("/api/privacy/providers/{provider}/{action}")
    async def provider_control(provider: str, action: str, request: Request, p=Depends(owner)):
        if provider not in PROVIDERS or action not in {"disconnect", "reauthorize"}:
            raise ApiError(404, "NOT_FOUND", "Choose bee or ring and disconnect or reauthorize.")
        if action == "disconnect":
            response = command(request, p, lambda s, db: disconnect(s, db, p["household"], provider))
            if provider == "ring":
                await camera.stop(p["household"], "PROVIDER_DISCONNECTED")
            if provider == "bee" and not demo and p["household"] == bee_household():
                # Drop the in-process credential copy and end the stream; startup also honors revocation.
                bee.stopped = True
                bee.token = None
            return response
        return command(request, p, lambda s, db: reauthorize(s, provider))

    @app.post("/api/privacy/household/delete")
    async def household_delete(body: DeletionInput, request: Request, p=Depends(owner)):
        if body.household_id != p["household"]:
            raise ApiError(403, "HOUSEHOLD_MISMATCH", "You can only delete your own household.")
        if body.confirmation != DELETE_PHRASE:
            raise ApiError(422, "CONFIRMATION_REQUIRED", f"Type exactly: {DELETE_PHRASE}")
        response = command(
            request, p, lambda s, db: delete_household(s, db, p["household"], fresh(p["household"]))
        )
        await camera.stop(p["household"], "HOUSEHOLD_DELETED")
        with store.lock:
            store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return response
