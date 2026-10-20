import asyncio
import hashlib
import hmac
import json
import logging
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
from .runtime import Runtime
from .webhooks import verify_ring
from .adapters import BeeAdapter
from .camera import CameraBridge
from .camera_reducers import frame_received, camera_ended
from .models import CameraInput, RecordedInput
from . import recorded as recorded_source
from . import engine as e
from . import privacy
from .push import PushNotifier
from .models import PushSubscribeInput, PushUnsubscribeInput
from . import mcp_ext


def create_app(data_dir=None, passwords=None):
    root = Path(__file__).resolve().parents[3]
    data = Path(data_dir or os.getenv("DATA_DIR", str(root / ".local")))
    data.mkdir(parents=True, exist_ok=True)
    os.chmod(data, 0o700)
    demo = os.getenv("DEMO_MODE", "true").lower() == "true"
    key_file = os.getenv("LEDGER_KEY_FILE")
    if not demo:
        origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
        if not key_file or not Path(key_file).is_file() or not all(o.startswith("https://") for o in origins):
            raise RuntimeError(
                "Live deployment is not certified without a provisioned ledger key and HTTPS origins."
            )
        if passwords is None and not os.getenv("OWNER_PASSWORD"):
            raise RuntimeError("Live deployment requires an explicit owner password.")
    credentials = data / "access.json"
    if passwords is None:
        if credentials.exists():
            passwords = json.loads(credentials.read_text())
        else:
            passwords = {"owner": os.getenv("OWNER_PASSWORD") or secrets.token_urlsafe(20)}
            if demo:
                passwords["demo-admin"] = os.getenv("DEMO_ADMIN_PASSWORD") or secrets.token_urlsafe(20)
            fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(passwords, f)
    if not demo and ("demo-admin" in passwords or any(len(p) < 16 for p in passwords.values())):
        raise RuntimeError(
            "Live deployment requires owner passwords of at least 16 characters and no demo administrator."
        )
    # Passwords are salted/hashed in memory; bootstrap file is local, private and ignored.
    salts = {name: secrets.token_bytes(16) for name in passwords}
    hashes = {
        name: hashlib.scrypt(p.encode(), salt=salts[name], n=16384, r=8, p=1) for name, p in passwords.items()
    }
    store = Store(str(data / "ledger.db"), key_file=key_file)
    pusher = PushNotifier(data)
    runtime = Runtime(store)
    bee = BeeAdapter()
    camera = CameraBridge(
        lambda *args: frame_received(store, *args),
        lambda *args: camera_ended(store, *args),
        masks=lambda household, device: privacy.polygons(store.read(household), device),
    )
    # RECORDED DEMO: pinned fixture frames through the same pose detector and reducer as live frames.
    recorded_demo = recorded_source.RecordedDemoBridge(
        lambda *args: frame_received(store, *args), lambda *args: camera_ended(store, *args)
    )
    if os.getenv("AWS_LEDGER_TABLE"):
        required = [
            "AWS_REGION",
            "S3_EVIDENCE_BUCKET",
            "AWS_WAKE_QUEUE_URL",
            "AWS_WAKE_QUEUE_ARN",
            "AWS_SCHEDULER_ROLE_ARN",
        ]
        if any(not os.getenv(name) for name in required):
            raise RuntimeError("AWS synchronization configuration is incomplete.")
    mcp = FastMCP(
        "DONE/IRL",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=mcp_ext.transport_security(demo),
    )
    rates = {}

    def fresh(household):
        s = e.fresh()
        s["household_id"] = household
        # Only the isolated judge namespace replays the virtual canonical day. Every real
        # household (including the owner of a demo deployment) runs on wall-clock time.
        if not demo or household != "demo":
            from datetime import datetime, timezone

            s.update(
                clock_mode="WALL",
                now=datetime.now(timezone.utc).isoformat(),
                consent=False,
                source_mode="NOT_CONNECTED",
            )
        return s

    def initial(household):
        s = store.read(household)
        if s is None:
            if not demo and os.getenv("AWS_LEDGER_TABLE"):
                from .aws_runtime import AWSRuntime

                cloud = AWSRuntime(store)
                pointer = cloud.table.get_item(
                    Key={"pk": "HOUSE#" + household, "sk": "SNAPSHOT"}, ConsistentRead=True
                ).get("Item")
                if pointer:
                    raise ApiError(
                        503,
                        "RESTORE_REQUIRED",
                        "A cloud household exists. Restore the original ledger before starting this reducer.",
                    )
            with store.transaction() as db:
                s = store.read(household)
                if s is None:
                    s = fresh(household)
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
                return store.decode(previous["response"], f"command:{household}:{key}")
            s = store.read(household) or fresh(household)
            s["household_id"] = household
            if s.get("clock_mode") == "WALL":
                s["_trace_id"] = uuid.uuid4().hex
            result = fn(s, db)
            s.pop("_trace_id", None)
            response = {"schema_version": "1.0", "trace_id": uuid.uuid4().hex, "result": result, "state": s}
            store.save(db, household, s)
            db.execute(
                "INSERT INTO commands VALUES (?,?,?,?)",
                (household, key, fingerprint, store.encode(response, f"command:{household}:{key}")),
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
                try:
                    await asyncio.to_thread(runtime.step)
                    for household in list(camera.sessions):
                        state = store.read(household)
                        if not state or not state["consent"]:
                            await camera.stop(household, "CONSENT_REVOKED")
                        elif household in camera.sessions and privacy.camera_session_blocked(
                            state, camera.sessions[household]["device_id"]
                        ):
                            await camera.stop(household, "PRIVACY_EXCLUDED")
                    for household in list(recorded_demo.sessions):
                        state = store.read(household)
                        if not state or not state["consent"]:
                            await recorded_demo.stop(household, "CONSENT_REVOKED")
                    app.state.worker_status = "RUNNING"
                except Exception as error:
                    app.state.worker_status = "DEGRADED"
                    # Do not log provider payloads, URLs, credentials or household data.
                    logging.getLogger(__name__).error("Ledger worker failed: %s", type(error).__name__)
                await asyncio.sleep(1)

        async def push_worker():
            while True:
                try:
                    await asyncio.to_thread(pusher.deliver, store)
                    app.state.push_status = "RUNNING"
                except Exception as error:
                    app.state.push_status = "DEGRADED"
                    logging.getLogger(__name__).error("Push delivery failed: %s", type(error).__name__)
                await asyncio.sleep(3)

        async def receive_bee(payload, event_id):
            household = os.getenv("BEE_HOUSEHOLD", "house_owner")
            # The adapter already mapped documented Bee shapes onto BeeInput; unknown shapes
            # never reach this point, and the envelope is validated again here.
            if not event_id:
                event_id = payload.get("event_id")
            if not event_id:
                raise ApiError(422, "BEE_EVENT_ID_REQUIRED", "Provider event requires a stable event ID.")
            normalized = BeeInput.model_validate({**payload, "event_id": event_id}).model_dump(mode="json")
            runtime.enqueue(household, "bee", event_id, normalized, cursor=event_id)

        async def cloud_sync():
            from .aws_runtime import AWSRuntime

            cloud = AWSRuntime(store)
            delay = 1
            while True:
                try:
                    await asyncio.to_thread(cloud.flush)
                    await asyncio.to_thread(cloud.wake, runtime)
                    app.state.cloud_status = "RUNNING"
                    delay = 1
                except Exception as error:
                    app.state.cloud_status = "DEGRADED"
                    logging.getLogger(__name__).error("AWS synchronization failed: %s", type(error).__name__)
                    delay = min(delay * 2, 60)
                await asyncio.sleep(delay)

        async with mcp.session_manager.run():
            app.state.worker_status = "STARTING"
            with store.transaction() as db:
                for row in db.execute("SELECT id FROM households").fetchall():
                    s = store.read(row["id"])
                    if s.get("camera_request", {}).get("status") in {"OPEN", "PENDING", "CONNECTING"}:
                        s["camera_request"]["status"] = "CLOSED"
                        if s["studio"] and s["studio"]["status"] not in {"COMPLETED", "OVERRIDDEN"}:
                            s["studio"].update(
                                status="PAUSED", phase="STANDING", stable=0, quality="PROCESS_RESTART_GAP"
                            )
                        e.emit(s, "watchdog.monitoring_gap", {"reason": "PROCESS_RESTART_GAP"})
                        store.save(db, row["id"], s)
            tasks = [asyncio.create_task(reconcile()), asyncio.create_task(push_worker())]
            if os.getenv("AWS_LEDGER_TABLE"):
                app.state.cloud_status = "STARTING"
                tasks.append(asyncio.create_task(cloud_sync()))
            if bee.token and privacy.provider_revoked(
                store.read(os.getenv("BEE_HOUSEHOLD", "house_owner")), "bee"
            ):
                # Owner revocation survives restarts; never auto-reconnect the wearable stream.
                bee.token = None
                bee.stopped = True
            if bee.token:
                with store.lock:
                    row = store.db.execute(
                        "SELECT cursor FROM provider_cursors WHERE household=? AND provider='bee'",
                        (os.getenv("BEE_HOUSEHOLD", "house_owner"),),
                    ).fetchone()
                bee.cursor = row["cursor"] if row else None
                tasks.append(asyncio.create_task(bee.run(receive_bee)))
            try:
                yield
            finally:
                bee.stopped = True
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await camera.shutdown()
                await recorded_demo.shutdown()
                await bee.client.aclose()

    app = FastAPI(title="DONE/IRL", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    app.state.runtime = runtime
    app.state.camera = camera
    app.state.recorded_demo = recorded_demo
    app.state.mutate = mutate
    app.state.bee = bee

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
            if (
                origin
                and origin not in allowed
                and not (demo and origin == str(request.base_url).rstrip("/"))
            ):
                raise ApiError(403, "ORIGIN_DENIED", "This origin is not authorized.")
            if not demo and request.url.scheme != "https" and request.url.path.startswith(("/api", "/mcp")):
                raise ApiError(426, "HTTPS_REQUIRED", "Live household access requires HTTPS.")
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
        if getattr(app.state, "worker_status", "STARTING") == "DEGRADED" or (
            os.getenv("AWS_LEDGER_TABLE") and getattr(app.state, "cloud_status", "STARTING") != "RUNNING"
        ):
            raise ApiError(503, "WORKER_NOT_READY", "Durable worker or AWS synchronization is not ready.")
        return {
            "status": "ready",
            "storage": "encrypted-sqlite-wal",
            "mode": "SYNTHETIC_DEMO" if demo else "LIVE_CONFIGURED_UNVERIFIED",
            "worker": getattr(app.state, "worker_status", "STARTING"),
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
            secure=not demo or request.url.scheme == "https",
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
        s = initial(p["household"])
        if s.get("clock_mode") == "WALL":
            from datetime import datetime, timezone

            s["now"] = datetime.now(timezone.utc).isoformat()
        return {"schema_version": "1.0", "trace_id": uuid.uuid4().hex, "state": s, "role": p["role"]}

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
            elif (
                body.action == "confirm-done"
                and c["key"].startswith("gen_")
                and c["status"] in {"ACTIVE", "ENGAGED", "EVIDENCE_PENDING", "MISSED"}
                and c["verification_modality"] != "FIRE_TV_LIVE_POSE_CAMERA"
            ):
                ev = e.add_evidence(
                    s,
                    db,
                    p["household"],
                    c,
                    "USER_CONFIRMATION",
                    {"owner_statement": "Owner confirms this commitment was completed"},
                    provenance="USER_CONFIRMED",
                )
                e.revise(s, c, "VERIFIED", "Explicit owner confirmation (USER_CONFIRMED), not sensor proof.", ev)
            else:
                raise ApiError(409, "PROOF_REQUIRED", "This action cannot bypass contract evidence policy.")

        return command(request, p, op)

    @app.get("/api/push/config")
    def push_config(p=Depends(principal)):
        return {
            "schema_version": "1.0",
            "trace_id": uuid.uuid4().hex,
            "public_key": pusher.public_key(),
            "delivery_claim": "ACCEPTED_BY_PUSH_SERVICE is not proof the device displayed the alert.",
        }

    @app.post("/api/push/subscribe")
    def push_subscribe(body: PushSubscribeInput, request: Request, p=Depends(owner)):
        return command(
            request,
            p,
            lambda s, db: PushNotifier.subscribe(s, body.endpoint, body.keys.p256dh, body.keys.auth, s["now"]),
        )

    @app.post("/api/push/unsubscribe")
    def push_unsubscribe(body: PushUnsubscribeInput, request: Request, p=Depends(owner)):
        return command(request, p, lambda s, db: PushNotifier.unsubscribe(s, body.endpoint))

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
            if not body.enabled:
                db.execute(
                    "UPDATE inbox SET status='CANCELLED',payload=NULL,lease_until=NULL WHERE household=? "
                    "AND status IN ('PENDING','PROCESSING')",
                    (p["household"],),
                )
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
            row = store.uow.get_artifact(eid, p["household"])
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
            e.verify_artifacts(s, store.uow, p["household"])
        return JSONResponse(
            {
                "schema_version": "1.0",
                "trace_id": uuid.uuid4().hex,
                "label": "SYNTHETIC DEMO — NOT AN OFFICIAL REPORT"
                if demo
                else "PRIVATE EVIDENCE EXPORT — NOT AN OFFICIAL REPORT",
                "state": s,
            },
            headers={"Content-Disposition": 'attachment; filename="done-irl-evidence.json"'},
        )

    @app.post("/api/camera/start")
    async def camera_start(body: CameraInput, request: Request, p=Depends(owner)):
        if demo:
            raise ApiError(409, "ISOLATED_DEMO", "Choose a live deployment to connect a Ring camera.")

        # Commit the command before the external effect; retries cannot reopen a completed session.
        def intent(s, db):
            if not s["consent"]:
                raise ApiError(409, "CONSENT_REQUIRED", "Enable camera consent first.")
            privacy.require_provider(s, "ring")
            privacy.require_camera_allowed(s, body.device_id)
            previous = s.get("camera_request", {})
            if previous.get("status") in {"PENDING", "OPEN", "CONNECTING"}:
                raise ApiError(
                    409, "CAMERA_ALREADY_OPEN", "Close or recover the current camera session first."
                )
            e.contract(s, "squats")
            operation = {"id": uuid.uuid4().hex, "device_id": body.device_id, "status": "PENDING"}
            s["camera_request"] = operation
            e.emit(s, "studio.camera_requested", operation.copy())
            return operation.copy()

        operation = command(request, p, intent)["result"]
        with store.transaction() as db:
            s = store.read(p["household"])
            current = s.get("camera_request", {})
            if current.get("id") != operation["id"] or current.get("status") != "PENDING":
                return camera.status(p["household"])
            s["camera_request"]["status"] = "CONNECTING"
            store.save(db, p["household"], s)
        try:
            result = await camera.start(p["household"], body.device_id)
            with store.transaction() as db:
                s = store.read(p["household"])
                if not s["consent"]:
                    raise ApiError(409, "CONSENT_REVOKED", "Consent was revoked while connecting.")
                e.studio_start(s, source="LIVE_RING_WHEP", source_mode="NOT_CONNECTED")
                session = s["studio"]
                session.update(
                    camera_id=result["id"],
                    timestamp_base=max(0, session["last_timestamp_ms"]) + 1,
                    status="RUNNING",
                    phase="STANDING",
                    stable=0,
                    quality="AWAITING_FRAMES",
                )
                s["camera_request"]["status"] = "OPEN"
                store.save(db, p["household"], s)
            return result
        except BaseException:
            await camera.stop(p["household"], "CONNECTION_FAILED")
            with store.transaction() as db:
                s = store.read(p["household"])
                s["camera_request"]["status"] = "FAILED"
                e.emit(s, "watchdog.monitoring_gap", {"reason": "CAMERA_CONNECTION_FAILED"})
                store.save(db, p["household"], s)
            raise

    @app.get("/api/camera/status")
    def camera_status(p=Depends(principal)):
        return camera.status(p["household"])

    @app.post("/api/camera/stop")
    async def camera_stop(request: Request, p=Depends(owner)):
        operation = command(
            request,
            p,
            lambda s, db: e.emit(
                s, "studio.camera_close_requested", {"camera_id": camera.status(p["household"]).get("id")}
            ),
        )["result"]
        if camera.status(p["household"]).get("id") == operation["payload"]["camera_id"]:
            await camera.stop(p["household"])
        return camera.status(p["household"])

    @app.get("/api/camera/frame")
    def camera_frame(p=Depends(principal)):
        s = initial(p["household"])
        session = camera.sessions.get(p["household"])
        if not s["consent"] or not session or not session["jpeg"]:
            raise ApiError(
                503, "CAMERA_FRAME_UNAVAILABLE", "No current authorized decoded frame is available."
            )
        return Response(
            session["jpeg"], media_type="image/jpeg", headers={"Cache-Control": "private, no-store"}
        )

    @app.post("/api/studio/sessions")
    def start_studio(request: Request, p=Depends(owner)):
        if not demo:
            raise ApiError(
                503,
                "CAMERA_NOT_CONNECTED",
                "A verified live camera session is required to start live pose verification.",
            )
        return command(request, p, lambda s, db: e.studio_start(s))

    @app.post("/api/studio/recorded/start")
    async def recorded_start(body: RecordedInput, request: Request, p=Depends(owner)):
        """Stream a pinned RECORDED DEMO fixture through MediaPipe and the REALITY-LOCK reducer."""
        if not demo:
            raise ApiError(
                409, "LIVE_DEPLOYMENT", "Recorded demo sources are only available in demo deployments."
            )
        if p["household"] in recorded_demo.sessions:
            raise ApiError(409, "RECORDED_DEMO_ALREADY_OPEN", "Stop the current recorded demo first.")
        camera_id = "recorded_" + uuid.uuid4().hex
        model_sha = recorded_source.pose_model_location()[1] or ""

        def bind(s, db):
            recorded_source.open_studio(s, camera_id, body.fixture, model_sha)
            e.emit(
                s,
                "studio.recorded_demo_opened",
                {"camera_id": camera_id, "fixture": body.fixture, "label": recorded_source.LABEL},
            )

        command(request, p, bind)
        try:
            return await recorded_demo.start(p["household"], body.fixture, session_id=camera_id)
        except BaseException:
            await asyncio.to_thread(camera_ended, store, p["household"], camera_id, "RECORDED_DEMO_FAILED")
            raise

    @app.get("/api/studio/recorded/status")
    def recorded_status(p=Depends(principal)):
        return recorded_demo.status(p["household"])

    @app.post("/api/studio/recorded/stop")
    async def recorded_stop(p=Depends(owner)):
        await recorded_demo.stop(p["household"])
        return recorded_demo.status(p["household"])

    @app.get("/api/studio/recorded/frame")
    def recorded_frame(p=Depends(principal)):
        s = initial(p["household"])
        jpeg = recorded_demo.frame(p["household"])
        if not s["consent"] or not jpeg:
            raise ApiError(503, "RECORDED_FRAME_UNAVAILABLE", "No recorded demo frame has been decoded yet.")
        return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

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
        key = os.getenv("RING_HMAC_KEY")
        if not key:
            raise ApiError(503, "RING_NOT_CONNECTED", "Ring webhook verification is not configured.")
        body = await request.body()
        household, event_id, payload = verify_ring(
            body, request.headers.get("x-signature", ""), key, os.getenv("RING_BINDINGS_FILE")
        )
        if demo:
            raise ApiError(409, "ISOLATED_DEMO", "Live webhooks require a separate live deployment.")
        blocked = privacy.inbox_block_reason(store.read(household), "ring", payload)
        if blocked:
            # Acknowledge so the provider stops retrying; nothing is stored or reduced.
            return JSONResponse(
                {"receipt_id": None, "duplicate": False, "processed": False, "reason": blocked},
                status_code=202,
            )
        receipt, created = runtime.enqueue(household, "ring", event_id, payload)
        return JSONResponse({"receipt_id": receipt, "duplicate": not created}, status_code=202)

    @app.post("/api/tv/sessions")
    def register_tv(request: Request, p=Depends(owner)):
        def op(s, db):
            sessions = [session for session in s.get("tv_sessions", []) if session["expires"] > time.time()][
                -7:
            ]
            session = {
                "session_id": "tv_" + uuid.uuid4().hex,
                "expires": time.time() + 8 * 3600,
                "device_runtime_verified": False,
            }
            s["tv_sessions"] = [*sessions, session]
            e.emit(s, "tv.session_registered", session.copy())
            return session

        return command(request, p, op)

    @app.get("/api/camera/devices")
    def camera_devices(p=Depends(owner)):
        path = os.getenv("RING_BINDINGS_FILE")
        if not path or demo:
            return {"devices": []}
        try:
            bindings = json.loads(Path(path).read_text())
            devices = sorted(
                {
                    device
                    for binding in bindings.values()
                    if binding["household"] == p["household"]
                    for device in binding["devices"]
                }
            )
        except (OSError, ValueError, TypeError, KeyError):
            raise ApiError(503, "RING_BINDINGS_INVALID", "Camera bindings could not be loaded.")
        return {"devices": devices}

    @app.get("/api/integrations/status")
    def integrations(p=Depends(principal)):
        s = initial(p["household"])
        with store.lock:
            receipts = store.db.execute(
                "SELECT provider,MAX(completed) AS last_success FROM inbox "
                "WHERE household=? AND status='DONE' GROUP BY provider",
                (p["household"],),
            ).fetchall()
        last = {row["provider"]: row["last_success"] for row in receipts}
        stream = camera.status(p["household"])

        def provider(name, receipt):
            if privacy.provider_revoked(s, receipt):
                return {
                    "name": name,
                    "status": "NOT_CONNECTED",
                    "last_verified_at": None,
                    "reason": "Owner disconnected this provider; automatic reconnection is disabled.",
                }
            return {
                "name": name,
                "status": "LIVE_VERIFIED" if last.get(receipt) else "BLOCKED",
                "last_verified_at": last.get(receipt),
                "reason": (
                    "Authenticated provider event processed; physical/device runtime proof is separate."
                    if last.get(receipt)
                    else "No authenticated live event processed for this household."
                ),
            }

        return {
            "schema_version": "1.0",
            "trace_id": uuid.uuid4().hex,
            "integrations": [
                provider("Bee", "bee"),
                provider("Ring", "ring"),
                {
                    "name": "Ring video",
                    "status": "NOT_CONNECTED"
                    if privacy.provider_revoked(s, "ring")
                    else stream["source_mode"],
                    "reason": "Decoded frames: "
                    + str(stream.get("frames_decoded", 0))
                    + "; no silent fallback to demo.",
                },
                {
                    "name": "Alexa+",
                    "status": "NOT_CONNECTED",
                    "reason": "No verified Alexa account/device connection. Judge console offers a labeled "
                    + "SIMULATED Alexa+ experience over the real MCP server.",
                },
                {
                    "name": "Fire TV",
                    "status": "BLOCKED",
                    "reason": "Native client builds; actual device runtime proof pending.",
                },
                {
                    "name": "MCP",
                    "status": "SIMULATED_VERIFIED" if demo else "NOT_CONNECTED",
                    "reason": "Official SDK tested; source provenance is recorded per household event.",
                },
                {
                    "name": "Companion",
                    "status": "SIMULATED_VERIFIED" if demo else "NOT_CONNECTED",
                    "reason": "Authenticated notification inbox; no native push/haptic claim.",
                },
                {
                    "name": "Worker",
                    "status": "SIMULATED_VERIFIED" if demo else "NOT_CONNECTED",
                    "reason": getattr(app.state, "worker_status", "STARTING")
                    + "; "
                    + s.get("clock_mode", "VIRTUAL")
                    + " clock.",
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
        s = initial(p["household"])
        return {
            "contracts": s["contracts"],
            "source_mode": s["source_mode"],
            "tv_sessions": [
                session for session in s.get("tv_sessions", []) if session["expires"] > time.time()
            ],
        }

    @mcp.tool()
    def compile_ambient_commitment(utterance_json: dict, speaker_context: dict) -> dict:
        """Compile owner-provided speech/text with explicit provenance; never claim Bee capture or physical completion."""
        bee = BeeInput.model_validate(
            {**utterance_json, "speaker": speaker_context.get("speaker", "UNKNOWN")}
        )

        def op(s, db, p):
            s["_event_source"] = {
                "source": "MCP_OWNER_INPUT",
                "source_mode": "SIMULATED_VERIFIED" if demo else "NOT_CONNECTED",
                "consent_scope": "demo" if demo else "household",
            }
            ids = e.compile_bee(s, bee)
            s.pop("_event_source", None)
            return {"contract_ids": ids, "source_mode": s["source_mode"]}

        return tool_command("compile", [utterance_json, speaker_context], op)

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
        if (
            camera_device_id != "synthetic-porch"
            or not agent
            or not s["consent"]
            or privacy.camera_excluded(s, camera_device_id)
        ):
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

        def op(s, db, p):
            # Audited denial: the attempt is recorded, nothing is approved or sent.
            s["_event_source"] = {"source": "MCP_TOOL_CALL"}
            e.emit(
                s,
                "incident.mcp_dispatch_denied",
                dict(
                    incident_id=incident_id,
                    human_confirmed_boolean=bool(human_confirmed_boolean),
                    reason="OWNER_APPROVAL_REQUIRED",
                    external_sends=0,
                ),
            )
            s.pop("_event_source", None)
            return {
                "status": "DENIED",
                "code": "OWNER_APPROVAL_REQUIRED",
                "external_sends": 0,
                "reason": "Use authenticated owner review. MCP cannot grant report approval.",
            }

        return tool_command("dispatch", [incident_id, bool(human_confirmed_boolean)], op)

    @mcp.tool()
    async def bridge_ring_camera_to_firetv(
        camera_device_id: str, firetv_session_id: str, verification_mode: str
    ) -> dict:
        """Open an authorized backend WHEP/pose relay for a registered owner TV session."""
        from types import SimpleNamespace

        p = mcp_principal()
        s = initial(p["household"])
        if demo:
            return {
                "status": "BLOCKED",
                "source_mode": "BLOCKED",
                "reason": "Live Ring requires the separate live deployment.",
            }
        if verification_mode != "POSE_SQUATS":
            raise ApiError(
                422, "VERIFICATION_MODE_UNSUPPORTED", "Only POSE_SQUATS is supported by this bridge."
            )
        if not any(
            session["session_id"] == firetv_session_id and session["expires"] > time.time()
            for session in s.get("tv_sessions", [])
        ):
            raise ApiError(
                403, "TV_SESSION_NOT_AUTHORIZED", "Register this TV session in the same household first."
            )
        args = [camera_device_id, firetv_session_id, verification_mode]
        request = SimpleNamespace(
            headers={"idempotency-key": "mcp:bridge:" + e.digest(args)},
            state=SimpleNamespace(fingerprint=e.digest(args)),
        )
        result = await camera_start(CameraInput(device_id=camera_device_id), request, p)
        return {
            **result,
            "frame_url": "/api/camera/frame",
            "household_authenticated": True,
            "tv_device_runtime_verified": False,
        }

    privacy.register(
        app,
        owner=owner,
        command=command,
        initial=initial,
        fresh=fresh,
        store=store,
        camera=camera,
        bee=bee,
        demo=demo,
    )

    mcp_ext.register_read_tools(mcp, principal=mcp_principal, initial=initial, integrations=integrations)
    mcp_tool_names = frozenset(t.name for t in mcp._tool_manager.list_tools())
    app.mount("/mcp", mcp.streamable_http_app())

    # Authentication applies to discovery/initialize as well as tool calls.
    @app.middleware("http")
    async def protect_mcp(request, call_next):
        return await mcp_ext.guard(request, call_next, authenticate, error_response, mcp_tool_names)

    dist = root / "dist"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith(("api/", "health/")):
                raise ApiError(404, "NOT_FOUND", "Endpoint not found.")
            static = (dist / path).resolve()
            if path and static.is_file() and dist.resolve() in static.parents:
                return FileResponse(static)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
