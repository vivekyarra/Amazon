import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.fastmcp import FastMCP
from .models import (
    ApiError,
    BeeInput,
    ScenarioInput,
    LoginInput,
    ActionInput,
    ClockInput,
    ConsentInput,
    PoseInput,
)
from .store import Store
from . import engine as e


def create_app(data_dir=None, passwords=None):
    root = Path(__file__).resolve().parents[3]
    data = Path(data_dir or os.getenv("DATA_DIR", str(root / ".local")))
    data.mkdir(parents=True, exist_ok=True)
    os.chmod(data, 0o700)
    demo = os.getenv("DEMO_MODE", "true").lower() == "true"
    if not demo:
        raise RuntimeError(
            "Live deployment is not certified. Use explicit DEMO_MODE=true for the isolated synthetic workflow."
        )
    credentials = data / "access.json"
    if passwords is None:
        if credentials.exists():
            passwords = json.loads(credentials.read_text())
        else:
            passwords = {
                "demo-admin": os.getenv("DEMO_ADMIN_PASSWORD") or secrets.token_urlsafe(20),
                "owner": os.getenv("OWNER_PASSWORD") or secrets.token_urlsafe(20),
            }
            fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(passwords, f)
    # Passwords are salted/hashed in memory; bootstrap file is local, private and ignored.
    salts = {name: secrets.token_bytes(16) for name in passwords}
    hashes = {
        name: hashlib.scrypt(p.encode(), salt=salts[name], n=16384, r=8, p=1) for name, p in passwords.items()
    }
    store = Store(str(data / "ledger.db"))
    mcp = FastMCP("DONE/IRL", stateless_http=True, json_response=True, streamable_http_path="/")
    rates = {}

    def initial(household):
        s = store.read(household)
        if s is None:
            with store.transaction() as db:
                s = e.fresh()
                s["household_id"] = household
                store.save(db, household, s)
        return s

    def mutate(household, key, fingerprint, fn):
        with store.transaction() as db:
            previous = db.execute(
                "SELECT fingerprint,response FROM commands WHERE household=? AND key=?", (household, key)
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ApiError(
                        409, "IDEMPOTENCY_CONFLICT", "This key was already used for another command."
                    )
                return json.loads(previous["response"])
            row = db.execute("SELECT state FROM households WHERE id=?", (household,)).fetchone()
            s = json.loads(row["state"]) if row else e.fresh()
            s["household_id"] = household
            result = fn(s, db)
            response = {"schema_version": "1.0", "trace_id": uuid.uuid4().hex, "result": result, "state": s}
            store.save(db, household, s)
            db.execute(
                "INSERT INTO commands VALUES (?,?,?,?)", (household, key, fingerprint, json.dumps(response))
            )
            return response

    def authenticate(request):
        token = request.cookies.get("done_session")
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        if not token:
            raise ApiError(401, "AUTH_REQUIRED", "Sign in to view this household.")
        with store.lock:
            row = store.db.execute(
                "SELECT * FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)
            ).fetchone()
        if not row or row["expires"] <= time.time():
            raise ApiError(401, "SESSION_EXPIRED", "Sign in again; your session expired.")
        return dict(row)

    def principal(request: Request):
        return authenticate(request)

    def admin(p=Depends(principal)):
        if p["role"] != "admin" or p["household"] != "demo":
            raise ApiError(
                403, "ADMIN_REQUIRED", "Judge replay controls require the isolated demo administrator."
            )
        return p

    def owner(p=Depends(principal)):
        if p["role"] not in {"owner", "admin"}:
            raise ApiError(403, "OWNER_REQUIRED", "Owner approval is required.")
        return p

    def command(request, p, fn):
        key = request.headers.get("idempotency-key")
        if not key or len(key) > 200:
            raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Supply an Idempotency-Key of 1–200 characters.")
        return mutate(p["household"], key, request.state.fingerprint, fn)

    @asynccontextmanager
    async def lifespan(app):
        async def reconcile():
            while True:
                # Demo deadlines are evaluated only by the persisted virtual clock.
                # Cleanup expired sessions and evidence according to wall-clock retention.
                with store.transaction() as db:
                    db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
                await asyncio.sleep(30)

        async with mcp.session_manager.run():
            worker = asyncio.create_task(reconcile())
            try:
                yield
            finally:
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="DONE/IRL", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.mutate = mutate

    @app.middleware("http")
    async def perimeter(request, call_next):
        try:
            origin = request.headers.get("origin")
            allowed = set(
                os.getenv(
                    "ALLOWED_ORIGINS",
                    "http://127.0.0.1:8080,http://localhost:8080,http://localhost:5173,http://127.0.0.1:5173",
                ).split(",")
            )
            if origin and origin not in allowed and origin != str(request.base_url).rstrip("/"):
                raise ApiError(403, "ORIGIN_DENIED", "This origin is not authorized.")
            if int(request.headers.get("content-length", "0")) > 1_000_000:
                raise ApiError(413, "BODY_TOO_LARGE", "Request exceeds 1 MB.")
            if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
                client = request.client.host if request.client else "unknown"
                bucket = (client, request.url.path)
                now = time.monotonic()
                recent = [t for t in rates.get(bucket, []) if now - t < 60]
                limit = 12 if request.url.path.endswith("/auth/login") else 240
                if len(recent) >= limit:
                    raise ApiError(429, "RATE_LIMITED", "Too many requests. Retry in one minute.")
                rates[bucket] = [*recent, now]
                if len(rates) > 5000:
                    for k in list(rates):
                        if not rates[k] or now - rates[k][-1] > 60:
                            rates.pop(k, None)
                body = await request.body()
                if len(body) > 1_000_000:
                    raise ApiError(413, "BODY_TOO_LARGE", "Request exceeds 1 MB.")
                request.state.fingerprint = hashlib.sha256(
                    request.method.encode() + request.url.path.encode() + body
                ).hexdigest()
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Cache-Control"] = (
                "no-store" if request.url.path.startswith(("/api", "/mcp")) else "no-cache"
            )
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; frame-ancestors 'none'"
            )
            return response
        except ApiError as error:
            return error_response(error)

    def error_response(error):
        return JSONResponse(
            status_code=error.status,
            content=dict(
                schema_version="1.0",
                trace_id=uuid.uuid4().hex,
                error={"code": error.code, "message": error.message, "retryable": error.status >= 500},
            ),
        )

    @app.exception_handler(ApiError)
    async def api_error(request, error):
        return error_response(error)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return error_response(
            ApiError(422, "VALIDATION_FAILED", "Request fields are invalid or unsupported.")
        )

    @app.get("/health/live")
    def live():
        return {"status": "ok", "schema_version": "1.0", "trace_id": uuid.uuid4().hex}

    @app.get("/health/ready")
    def ready():
        with store.lock:
            store.db.execute("SELECT 1").fetchone()
        return {
            "status": "ready",
            "storage": "sqlite-wal",
            "mode": "SYNTHETIC_DEMO",
            "schema_version": "1.0",
            "trace_id": uuid.uuid4().hex,
        }

    @app.post("/api/auth/login")
    def login(body: LoginInput, request: Request):
        candidate = hashlib.scrypt(
            body.password.encode(), salt=salts.get(body.username, b"0" * 16), n=16384, r=8, p=1
        )
        if body.username not in hashes or not hmac.compare_digest(candidate, hashes[body.username]):
            raise ApiError(401, "BAD_CREDENTIALS", "Username or password is incorrect.")
        token = secrets.token_urlsafe(32)
        role = "admin" if body.username == "demo-admin" else "owner"
        household = "demo" if role == "admin" else "house_" + body.username
        with store.transaction() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    body.username,
                    household,
                    role,
                    time.time() + 8 * 3600,
                ),
            )
        initial(household)
        response = JSONResponse(
            {"schema_version": "1.0", "trace_id": uuid.uuid4().hex, "user": body.username, "role": role}
        )
        response.set_cookie(
            "done_session",
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=8 * 3600,
        )
        return response

    @app.post("/api/auth/logout")
    def logout(request: Request, p=Depends(principal)):
        with store.transaction() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (p["token_hash"],))
        response = JSONResponse({"ok": True, "schema_version": "1.0", "trace_id": uuid.uuid4().hex})
        response.delete_cookie("done_session")
        return response

    @app.get("/api/state")
    def state(p=Depends(principal)):
        return {
            "schema_version": "1.0",
            "trace_id": uuid.uuid4().hex,
            "state": initial(p["household"]),
            "role": p["role"],
        }

    @app.get("/api/contracts")
    def contracts(status: str | None = None, offset: int = 0, limit: int = 100, p=Depends(principal)):
        values = initial(p["household"])["contracts"]
        if status:
            values = [v for v in values if v["status"] == status]
        return {
            "schema_version": "1.0",
            "trace_id": uuid.uuid4().hex,
            "contracts": values[max(0, offset) : max(0, offset) + max(1, min(limit, 100))],
        }

    @app.get("/api/contracts/{cid}")
    def contract_detail(cid: str, p=Depends(principal)):
        s = initial(p["household"])
        c = next((c for c in s["contracts"] if c["contract_id"] == cid), None)
        if not c:
            raise ApiError(404, "NOT_FOUND", "Contract not found.")
        return {
            "schema_version": "1.0",
            "trace_id": uuid.uuid4().hex,
            "contract": c,
            "events": [v for v in s["events"] if v["payload"].get("contract_id") == cid],
        }

    @app.post("/api/contracts/{cid}/confirm")
    def confirm(cid: str, body: ActionInput, request: Request, p=Depends(owner)):
        def op(s, db):
            c = next((c for c in s["contracts"] if c["contract_id"] == cid), None)
            if not c:
                raise ApiError(404, "NOT_FOUND", "Contract not found.")
            if body.revision is not None and body.revision != c["revision"]:
                raise ApiError(409, "REVISION_CONFLICT", "Reload the latest contract before confirming.")
            if body.action == "accept" and c["status"] == "NEEDS_CONFIRMATION":
                e.revise(s, c, "ACTIVE", "Owner accepted the proposed obligation.")
            elif body.action == "reject" and c["status"] == "NEEDS_CONFIRMATION":
                e.revise(s, c, "REJECTED", "Owner declined the proposed obligation.")
            elif body.action == "cancel" and c["status"] not in e.TERMINAL:
                e.revise(s, c, "CANCELLED", "Owner cancelled the commitment.")
            elif body.action == "confirm-drinks" and c["key"] == "drinks":
                ev = e.add_evidence(
                    s,
                    db,
                    p["household"],
                    c,
                    "USER_CONFIRMATION",
                    {"owner_statement": "Drinks obtained"},
                    provenance="USER_CONFIRMED",
                )
                e.revise(s, c, "VERIFIED", "Explicit owner confirmation, not sensor proof.", ev)
            else:
                raise ApiError(409, "PROOF_REQUIRED", "This action cannot bypass contract evidence policy.")

        return command(request, p, op)

    @app.get("/api/subagents")
    def subagents(p=Depends(principal)):
        return {
            "schema_version": "1.0",
            "trace_id": uuid.uuid4().hex,
            "subagents": initial(p["household"])["subagents"],
        }

    @app.post("/api/ingest/bee-simulated")
    def ingest(body: BeeInput, request: Request, p=Depends(admin)):
        return command(request, p, lambda s, db: e.compile_bee(s, body))

    @app.post("/api/admin/scenarios/{stage}/run")
    def scenario(stage: int, body: ScenarioInput, request: Request, p=Depends(admin)):
        if not 1 <= stage <= 6:
            raise ApiError(404, "NOT_FOUND", "Choose a stage from 1 to 6.")
        return command(request, p, lambda s, db: e.run_scenario(s, db, p["household"], stage, body.branch))

    @app.post("/api/admin/reset")
    def reset(request: Request, p=Depends(admin)):
        def op(s, db):
            db.execute("DELETE FROM artifacts WHERE household=?", (p["household"],))
            s.clear()
            s.update(e.fresh(), household_id=p["household"])
            e.emit(s, "replay.reset", {"scope": "ISOLATED_DEMO_ONLY"})

        # Reset is deliberately a new replay generation; old dedupe responses must not revive old state.
        result = command(request, p, op)
        with store.transaction() as db:
            db.execute(
                "DELETE FROM commands WHERE household=? AND key!=?",
                (p["household"], request.headers["idempotency-key"]),
            )
        return result

    @app.post("/api/admin/clock/advance")
    def clock(body: ClockInput, request: Request, p=Depends(admin)):
        from datetime import datetime, timedelta

        def op(s, db):
            e.tick(s, (datetime.fromisoformat(s["now"]) + timedelta(minutes=body.minutes)).isoformat())

        return command(request, p, op)

    @app.post("/api/admin/sister-proof")
    def sister(request: Request, p=Depends(admin)):
        return command(request, p, lambda s, db: e.verify_social(s, db, p["household"], "sister"))

    @app.post("/api/admin/owner-pickup")
    def pickup(request: Request, p=Depends(admin)):
        def op(s, db):
            c = e.contract(s, "parcel")
            if c.get("custody_status") != "DEPOSIT_VERIFIED_CUSTODY_ACTIVE" or s["incidents"]:
                raise ApiError(
                    409, "INVALID_CUSTODY", "An owner pickup cannot resolve a parcel already removed."
                )
            ev = e.add_evidence(
                s,
                db,
                p["household"],
                c,
                "AUTHORIZED_INWARD_TRANSFER",
                {"direction": "INWARD", "authorization": "SYNTHETIC_OWNER_CONTEXT"},
            )
            e.revise(s, c, "VERIFIED", "Synthetic authorized inward-transfer evidence.", ev)
            c["custody_status"] = "VERIFIED_SAFE_TRANSFER"
            for a in s["subagents"]:
                if a["kind"] == "PorchWatchdog":
                    a["status"] = "CLOSED"

        return command(request, p, op)

    @app.post("/api/consent")
    def consent(body: ConsentInput, request: Request, p=Depends(owner)):
        def op(s, db):
            s["consent"] = body.enabled
            for a in s["subagents"]:
                if a["status"] != "CLOSED":
                    a["status"] = "WATCHING" if body.enabled else "PAUSED_CONSENT"
            if s["studio"] and not body.enabled:
                s["studio"]["status"] = "PAUSED"
            e.emit(s, "consent.changed", {"enabled": body.enabled})

        return command(request, p, op)

    @app.get("/api/incidents/{iid}")
    def incident(iid: str, p=Depends(principal)):
        inc = next((i for i in initial(p["household"])["incidents"] if i["incident_id"] == iid), None)
        if not inc:
            raise ApiError(404, "NOT_FOUND", "Incident not found.")
        return {"schema_version": "1.0", "trace_id": uuid.uuid4().hex, "incident": inc}

    @app.post("/api/incidents/{iid}/{action}")
    def incident_mutation(iid: str, action: str, body: ActionInput, request: Request, p=Depends(owner)):
        def op(s, db):
            inc = next((i for i in s["incidents"] if i["incident_id"] == iid), None)
            if inc and body.revision is not None and body.revision != inc["revision"]:
                raise ApiError(409, "REVISION_CONFLICT", "Review the latest incident revision.")
            return e.incident_action(s, db, p["household"], iid, action, body.model_dump())

        return command(request, p, op)

    @app.get("/api/evidence/{eid}")
    def evidence(eid: str, p=Depends(principal)):
        s = initial(p["household"])
        metadata = next((v for v in s["evidence"] if v["evidence_id"] == eid), None)
        if not metadata:
            raise ApiError(404, "NOT_FOUND", "Evidence not found.")
        from datetime import datetime, timezone

        if datetime.fromisoformat(metadata["retention_expires_at"]) <= datetime.now(timezone.utc):
            raise ApiError(410, "EVIDENCE_EXPIRED", "Evidence retention period has ended.")
        with store.lock:
            row = store.db.execute(
                "SELECT * FROM artifacts WHERE id=? AND household=?", (eid, p["household"])
            ).fetchone()
        if (
            not row
            or hashlib.sha256(row["data"]).hexdigest() != row["sha256"]
            or hashlib.sha256(row["data"]).hexdigest() != metadata["sha256_original"]
        ):
            raise ApiError(409, "EVIDENCE_TAMPERED", "The artifact failed its integrity check.")
        return Response(row["data"], media_type=row["mime"], headers={"Cache-Control": "private, no-store"})

    @app.get("/api/export")
    def export(p=Depends(principal)):
        s = initial(p["household"])
        with store.lock:
            e.verify_artifacts(s, store.db, p["household"])
        return JSONResponse(
            {
                "schema_version": "1.0",
                "trace_id": uuid.uuid4().hex,
                "label": "SYNTHETIC DEMO — NOT AN OFFICIAL REPORT",
                "state": s,
            },
            headers={"Content-Disposition": 'attachment; filename="done-irl-evidence.json"'},
        )

    @app.post("/api/studio/sessions")
    def start_studio(request: Request, p=Depends(owner)):
        return command(request, p, lambda s, db: e.studio_start(s))

    @app.post("/api/admin/studio/rep")
    def demo_rep(request: Request, p=Depends(admin)):
        return command(request, p, lambda s, db: e.one_rep(s, db, p["household"]))

    @app.post("/api/admin/studio/frame-step")
    def frame_step(request: Request, p=Depends(admin)):
        from . import vision

        def op(s, db):
            if s["failures"]:
                raise ApiError(
                    503, "SOURCE_UNAVAILABLE", "Clear the injected failure before processing frames."
                )
            e.studio_start(s)
            session = s["studio"]
            if session["status"] != "RUNNING":
                return
            index = session.get("fixture_frame_index", 0)
            frames = vision.cycle_frames(offset=(index // 9) * 3)
            frame = frames[index % len(frames)]
            session["fixture_frame_index"] = index + 1
            ts = max(0, session["last_timestamp_ms"]) + 160
            e.pose_frame(s, db, p["household"], f"pixel_{index}", ts, vision.extract_marker_pose(frame))

        return command(request, p, op)

    @app.post("/api/studio/control")
    def control(body: ActionInput, request: Request, p=Depends(owner)):
        def op(s, db):
            session = s["studio"]
            if not session:
                raise ApiError(409, "NO_SESSION", "Start a studio session first.")
            if body.action in {"pause", "resume"}:
                if not s["consent"] or session["status"] == "COMPLETED":
                    raise ApiError(409, "SESSION_STATE", "This session cannot resume.")
                session.update(
                    status="PAUSED" if body.action == "pause" else "RUNNING", phase="STANDING", stable=0
                )
            elif body.action == "accessible-override":
                session.update(gate="USER_OVERRIDE", status="OVERRIDDEN")
                e.emit(
                    s,
                    "studio.accessible_override",
                    {"provenance": "USER_OVERRIDE", "contract_still_pending": True},
                )
            else:
                raise ApiError(422, "UNKNOWN_ACTION", "Count setters are not supported.")

        return command(request, p, op)

    @app.post("/api/admin/studio/landmarks")
    def landmarks(body: PoseInput, request: Request, p=Depends(admin)):
        def op(s, db):
            try:
                return e.pose_frame(s, db, p["household"], body.frame_id, body.timestamp_ms, body.landmarks)
            except ValueError:
                raise ApiError(422, "INVALID_LANDMARKS", "Expected 33 finite x, y, z, visibility landmarks.")

        return command(request, p, op)

    @app.get("/api/studio/frame")
    def studio_frame(p=Depends(principal)):
        import cv2
        import numpy as np
        from . import vision

        s = initial(p["household"])
        if not s["studio"]:
            raise ApiError(409, "NO_SESSION", "Studio has not started.")
        knee = s["studio"].get("angle", 178)
        frame = vision.synthetic_pose_frame(knee)
        points = vision.extract_marker_pose(frame)
        for a, b in [(23, 25), (25, 27), (24, 26), (26, 28), (23, 24)]:
            cv2.line(
                frame,
                tuple(int(v * 640) for v in points[a][:2]),
                tuple(int(v * 640) for v in points[b][:2]),
                (110, 230, 220),
                3,
            )
        cv2.putText(
            frame,
            "SYNTHETIC MARKER SOURCE / NOT LIVE RING",
            (18, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (220, 220, 220),
            1,
        )
        return Response(vision.png(np.asarray(frame)), media_type="image/png")

    @app.post("/api/admin/failures/{kind}")
    def failure(kind: str, request: Request, p=Depends(admin)):
        if kind not in {"camera-offline", "token-expired", "storage-unavailable", "clear"}:
            raise ApiError(422, "UNKNOWN_FAILURE", "Unsupported failure injection.")

        def op(s, db):
            s["failures"] = [] if kind == "clear" else [kind]
            if s["studio"] and kind != "clear":
                s["studio"].update(status="PAUSED", quality="CAMERA_UNAVAILABLE")
            e.emit(s, "watchdog.monitoring_gap", {"reason": kind, "source": "EXPLICIT_SIMULATED_FAILURE"})

        return command(request, p, op)

    @app.post("/api/webhooks/ring")
    async def ring_webhook(request: Request):
        # Public webhook stays fail-closed until a documented account/device mapping is configured.
        key = os.getenv("RING_HMAC_KEY")
        if not key:
            raise ApiError(503, "RING_NOT_CONNECTED", "Ring webhook verification is not configured.")
        body = await request.body()
        timestamp = request.headers.get("x-ring-timestamp", "")
        try:
            if abs(time.time() - int(timestamp)) > 300:
                raise ValueError
        except ValueError:
            raise ApiError(401, "STALE_WEBHOOK", "Webhook timestamp is missing or stale.")
        expected = hmac.new(key.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, request.headers.get("x-ring-signature", "")):
            raise ApiError(401, "BAD_SIGNATURE", "Webhook signature is invalid.")
        raise ApiError(
            503, "RING_ACCOUNT_NOT_LINKED", "Live account mapping is not configured. No state was changed."
        )

    @app.get("/api/integrations/status")
    def integrations(p=Depends(principal)):
        return {
            "schema_version": "1.0",
            "trace_id": uuid.uuid4().hex,
            "integrations": [
                {
                    "name": "Bee",
                    "status": "BLOCKED",
                    "reason": "No authorized device/token; synthetic utterances available.",
                },
                {
                    "name": "Ring",
                    "status": "BLOCKED",
                    "reason": "No linked camera/token; calibrated synthetic pixels only.",
                },
                {
                    "name": "Alexa+",
                    "status": "NOT_CONNECTED",
                    "reason": "MCP server implemented; no Alexa account connection.",
                },
                {
                    "name": "Fire TV",
                    "status": "BLOCKED",
                    "reason": "Native Fire OS client supplied; device/runtime proof pending.",
                },
                {
                    "name": "MCP",
                    "status": "SIMULATED_VERIFIED",
                    "reason": "Official Python SDK; isolated synthetic household.",
                },
                {
                    "name": "Companion",
                    "status": "SIMULATED_VERIFIED",
                    "reason": "Authenticated notification inbox; no native push/haptic claim.",
                },
            ],
        }

    @app.get("/api/events/stream")
    async def stream(request: Request, after: int = 0, p=Depends(principal)):
        try:
            cursor = max(0, int(request.headers.get("last-event-id", after)))
        except ValueError:
            raise ApiError(422, "INVALID_CURSOR", "SSE cursor must be a nonnegative integer.")

        async def generate():
            nonlocal cursor
            while not await request.is_disconnected():
                if p["expires"] <= time.time():
                    yield "event: auth-expired\ndata: {}\n\n"
                    break
                with store.lock:
                    active = store.db.execute(
                        "SELECT 1 FROM sessions WHERE token_hash=?", (p["token_hash"],)
                    ).fetchone()
                if not active:
                    break
                s = initial(p["household"])
                if cursor > len(s["events"]):
                    cursor = 0
                for idx, event in enumerate(s["events"][cursor:], start=cursor + 1):
                    yield f"id: {idx}\nevent: ledger\ndata: {json.dumps(event)}\n\n"
                    cursor = idx
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    # MCP uses the official SDK transport and shares these exact reducers/store.
    def mcp_principal():
        from mcp.server.transport_security import TransportSecuritySettings
        from mcp.server.fastmcp.server import Context

        del TransportSecuritySettings, Context
        from mcp.server.lowlevel.server import request_ctx

        ctx = request_ctx.get()
        return authenticate(ctx.request)

    def tool_command(name, args, fn, require_admin=False):
        p = mcp_principal()
        if require_admin and p["role"] != "admin":
            raise ApiError(403, "ADMIN_REQUIRED", "Synthetic ingestion requires judge role.")
        key = "mcp:" + name + ":" + e.digest(args)
        return mutate(p["household"], key, e.digest([name, args]), lambda s, db: fn(s, db, p))["result"]

    @mcp.tool()
    def list_active_contracts() -> dict:
        """Read owner-scoped contracts and truthful source labels."""
        p = mcp_principal()
        return {"contracts": initial(p["household"])["contracts"], "source_mode": e.MODE}

    @mcp.tool()
    def compile_ambient_commitment(utterance_json: dict, speaker_context: dict) -> dict:
        """Compile consented synthetic utterances; cannot mark a promise verified."""
        bee = BeeInput.model_validate(
            {**utterance_json, "speaker": speaker_context.get("speaker", "UNKNOWN")}
        )
        ids = tool_command(
            "compile", [utterance_json, speaker_context], lambda s, db, p: e.compile_bee(s, bee), True
        )
        return {"contract_ids": ids, "source_mode": e.MODE}

    @mcp.tool()
    def spawn_watchdog_subagent(
        contract_id: str, camera_device_id: str, target_roi: list[float], invariant_type: str
    ) -> dict:
        """Return an existing evidence-backed logical watchdog; never invent camera authorization."""
        p = mcp_principal()
        s = initial(p["household"])
        agent = next(
            (a for a in s["subagents"] if a["contract_id"] == contract_id and a["kind"] == "PorchWatchdog"),
            None,
        )
        if camera_device_id != "synthetic-porch" or not agent or not s["consent"]:
            return {"status": "BLOCKED", "reason": "Approved synthetic camera and observed deposit required."}
        return {"status": agent["status"], "subagent_id": agent["subagent_id"], "source_mode": e.MODE}

    @mcp.tool()
    def evaluate_deadline_escalation(contract_id: str, current_time: str, user_activity_state: str) -> dict:
        """Evaluate at the server's stored clock; client time/activity cannot fabricate telemetry."""

        def op(s, db, p):
            c = next((c for c in s["contracts"] if c["contract_id"] == contract_id), None)
            if not c:
                raise ApiError(404, "NOT_FOUND", "Contract not found.")
            e.tick(s, s["now"])
            return {"status": c["status"], "clock": s["now"], "client_telemetry_ignored": True}

        return tool_command("deadline", [contract_id, current_time, user_activity_state], op)

    @mcp.tool()
    def dispatch_police_evidence_dossier(incident_id: str, human_confirmed_boolean: bool) -> dict:
        """Never dispatch from a model's boolean. Owner must approve exact packet in the UI."""
        mcp_principal()
        return {
            "status": "DENIED",
            "code": "OWNER_APPROVAL_REQUIRED",
            "external_sends": 0,
            "reason": "Use authenticated owner review. MCP cannot grant report approval.",
        }

    @mcp.tool()
    def bridge_ring_camera_to_firetv(
        camera_device_id: str, firetv_session_id: str, verification_mode: str
    ) -> dict:
        """Report camera bridge availability without pretending synthetic frames are live Ring."""
        mcp_principal()
        return {
            "status": "BLOCKED",
            "source_mode": "BLOCKED",
            "reason": "Live Ring/Fire TV session has not been authorized or runtime-verified. Synthetic studio uses separate labeled API.",
        }

    app.mount("/mcp", mcp.streamable_http_app())

    # Authentication applies to discovery/initialize as well as tool calls.
    @app.middleware("http")
    async def protect_mcp(request, call_next):
        if request.url.path.startswith("/mcp"):
            try:
                authenticate(request)
            except ApiError as error:
                return error_response(error)
        return await call_next(request)

    dist = root / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith(("api/", "health/")):
                raise ApiError(404, "NOT_FOUND", "Endpoint not found.")
            return FileResponse(dist / "index.html")

    return app


app = create_app()
