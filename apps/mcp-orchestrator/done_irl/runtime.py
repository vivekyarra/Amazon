"""Restart-safe provider inbox and wall-clock deadline reconciliation.

Provider receipts are facts about delivery, not proof of a physical action. Network calls
must happen outside ledger transactions; reducers and receipt completion commit together.
"""

import time
from datetime import datetime, timezone


from . import engine as e
from . import privacy
from .models import ApiError, BeeInput


class Runtime:
    def __init__(self, store, clock=time.time):
        self.store = store
        self.clock = clock

    def enqueue(self, household, provider, event_id, payload, cursor=None):
        with self.store.transaction() as db:
            state = self.store.read(household)
            if not state or not state["consent"] or state.get("clock_mode") != "WALL":
                raise ApiError(409, "CONSENT_REQUIRED", "Enable consent in the linked live household first.")
            # Revocation is durable; no provider event may silently reconnect collection (spec 12.4).
            privacy.require_provider(state, provider)
            result = self.store.enqueue(db, household, provider, event_id, payload, self.clock())
            if cursor:
                db.execute(
                    "INSERT INTO provider_cursors VALUES (?,?,?) ON CONFLICT(household,provider) "
                    "DO UPDATE SET cursor=excluded.cursor",
                    (household, provider, cursor),
                )
            return result

    def claim(self):
        now = self.clock()
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT * FROM inbox WHERE (status='PENDING' AND available<=?) "
                "OR (status='PROCESSING' AND lease_until<=?) ORDER BY received LIMIT 1",
                (now, now),
            ).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE inbox SET status='PROCESSING',attempts=attempts+1,lease_until=? WHERE id=?",
                (now + 60, row["id"]),
            )
            return dict(row)

    def process(self, receipt):
        now = self.clock()
        try:
            with self.store.transaction() as db:
                row = db.execute("SELECT * FROM inbox WHERE id=?", (receipt["id"],)).fetchone()
                if not row or row["status"] != "PROCESSING":
                    return
                # A newer claimant supersedes an expired lease. Never acknowledge its work.
                if row["attempts"] != receipt["attempts"] + 1 or row["lease_until"] <= now:
                    return
                state = self.store.read(row["household"])
                if not state or not state["consent"]:
                    db.execute(
                        "UPDATE inbox SET status='CANCELLED',payload=NULL,completed=?,lease_until=NULL "
                        "WHERE id=?",
                        (now, row["id"]),
                    )
                    return
                payload = self.store.decode(row["payload"], f"inbox:{row['id']}")
                blocked = privacy.inbox_block_reason(state, row["provider"], payload)
                if blocked:
                    # Acknowledged, never reduced into an observation; payload is discarded.
                    db.execute(
                        "UPDATE inbox SET status='CANCELLED',payload=NULL,completed=?,lease_until=NULL,"
                        "error_code=? WHERE id=?",
                        (now, blocked, row["id"]),
                    )
                    return
                state["now"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
                state["_trace_id"] = row["id"]
                state["_event_source"] = {
                    "source": row["provider"].upper(),
                    "source_mode": "LIVE_VERIFIED",
                    "consent_scope": "household",
                }
                if row["provider"] == "bee":
                    e.compile_bee(state, BeeInput.model_validate(payload))
                elif row["provider"] == "ring":
                    event = payload["data"]
                    duplicate = any(
                        item["payload"].get("provider_event_id") == event["id"] and item["source"] == "RING"
                        for item in state["events"]
                    )
                    if duplicate:
                        db.execute(
                            "UPDATE inbox SET status='DONE',payload=NULL,completed=?,lease_until=NULL "
                            "WHERE id=?",
                            (now, row["id"]),
                        )
                        return
                    e.emit(
                        state,
                        "ring." + event["type"],
                        {
                            "provider_event_id": event["id"],
                            "device_id": event["attributes"]["source"],
                            "provider_timestamp": event["attributes"]["timestamp"],
                            "physical_verification": False,
                        },
                    )
                    if event["type"] in {"motion_detected", "button_press"}:
                        e.emit(
                            state,
                            "watchdog.monitoring_gap",
                            {
                                "reason": "VIDEO_ANALYSIS_REQUIRED",
                                "device_id": event["attributes"]["source"],
                                "decision": "NO_PHYSICAL_CONCLUSION_FROM_MOTION",
                            },
                        )
                else:
                    raise ApiError(422, "UNKNOWN_PROVIDER", "Provider has no registered reducer.")
                state.pop("_event_source", None)
                state.pop("_trace_id", None)
                self.store.save(db, row["household"], state)
                db.execute(
                    "UPDATE inbox SET status='DONE',payload=NULL,completed=?,lease_until=NULL,"
                    "error_code=NULL WHERE id=?",
                    (now, row["id"]),
                )
        except Exception as error:  # noqa: BLE001 - any reducer failure must settle the inbox item
            permanent = not isinstance(error, ApiError)
            code = error.code if isinstance(error, ApiError) else "INVALID_PROVIDER_EVENT"
            if isinstance(error, ApiError) and error.status < 500:
                permanent = True
            with self.store.transaction() as db:
                row = db.execute("SELECT attempts FROM inbox WHERE id=?", (receipt["id"],)).fetchone()
                attempts = row["attempts"]
                dead = permanent or attempts >= 6
                db.execute(
                    "UPDATE inbox SET status=?,available=?,lease_until=NULL,error_code=? WHERE id=?",
                    ("DEAD" if dead else "PENDING", now + min(300, 2**attempts), code, receipt["id"]),
                )
        # Unexpected programming/storage failures escape to the supervisor; the lease is recovered on restart.

    def step(self, limit=25):
        now = self.clock()
        with self.store.transaction() as db:
            self.store.purge_expired(db, now)
            # Payload retention is bounded even for poison events; receipt hashes support provider retries.
            db.execute(
                "UPDATE inbox SET payload=NULL WHERE received<? AND status IN ('DEAD','CANCELLED')",
                (now - 7 * 86400,),
            )
            for row in db.execute("SELECT id FROM households").fetchall():
                state = self.store.read(row["id"])
                if state.get("clock_mode") != "WALL" or not state["consent"]:
                    continue
                current = datetime.fromtimestamp(now, timezone.utc).isoformat()
                if datetime.fromisoformat(current) < datetime.fromisoformat(state["now"]):
                    continue
                before = e.digest({k: v for k, v in state.items() if k != "now"})
                e.tick(state, current)
                if before != e.digest({k: v for k, v in state.items() if k != "now"}):
                    self.store.save(db, row["id"], state)
        processed = 0
        for _ in range(limit):
            receipt = self.claim()
            if not receipt:
                break
            self.process(receipt)
            processed += 1
        return processed
