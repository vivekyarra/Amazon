"""Shared, durable reducers used by API, MCP, scheduler and judge replay."""

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .models import ApiError, BeeInput
from . import vision

DAY = "2026-10-20"
ZONE = "Asia/Kolkata"
MODE = "SIMULATED_VERIFIED"
TERMINAL = {"VERIFIED", "CANCELLED", "REJECTED"}


def at(hm):
    return (
        datetime.fromisoformat(f"{DAY}T{hm}:00")
        .replace(tzinfo=ZoneInfo(ZONE))
        .astimezone(timezone.utc)
        .isoformat()
    )


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def fresh():
    return dict(
        schema_version="1.0",
        now=at("08:00"),
        timezone=ZONE,
        consent=True,
        contracts=[],
        events=[],
        alerts=[],
        subagents=[],
        incidents=[],
        evidence=[],
        studio=None,
        scenario=0,
        branch="deposit",
        paused=False,
        source_mode=MODE,
        failures=[],
    )


def emit(s, event_type, payload, trace=None):
    event = dict(
        event_id=f"evt_{len(s['events']) + 1:06d}",
        schema_version="1.0",
        event_type=event_type,
        household_id=s.get("household_id", "demo"),
        actor_id="owner",
        source="SYNTHETIC_REPLAY",
        source_mode=MODE,
        occurred_at=s["now"],
        received_at=datetime.now(timezone.utc).isoformat(),
        trace_id=trace or f"trace_{s.get('scenario', 0)}",
        idempotency_key=f"event:{len(s['events']) + 1}",
        consent_scope="demo",
        payload=payload,
    )
    s["events"].append(event)
    return event


def contract(s, kind):
    c = next((c for c in s["contracts"] if c["key"] == kind), None)
    if not c:
        raise ApiError(409, "PREREQUISITE", "Run Morning Promises first.")
    return c


def revise(s, c, status, reason, evidence_id=None):
    if c["status"] in TERMINAL and status != c["status"]:
        raise ApiError(409, "TERMINAL_STATE", "Resolved contracts cannot be silently regressed.")
    if status == "VERIFIED" and not evidence_id:
        raise ApiError(409, "PROOF_REQUIRED", "Accepted, policy-matched evidence is required.")
    if status == "VERIFIED":
        record = next(
            (
                v
                for v in s["evidence"]
                if v["evidence_id"] == evidence_id
                and v["contract_id"] == c["contract_id"]
                and v["decision"] == "VALIDATED"
            ),
            None,
        )
        allowed = {
            "teacher": {"AUTHORIZED_PARTICIPATION"},
            "sister": {"AUTHORIZED_PARTICIPATION"},
            "drinks": {"USER_CONFIRMATION"},
            "parcel": {"AUTHORIZED_TRANSFER", "AUTHORIZED_INWARD_TRANSFER"},
            "squats": {"POSE_15_CYCLES"},
        }
        if not record or record["kind"] not in allowed.get(c["key"], set()):
            raise ApiError(
                409, "EVIDENCE_POLICY_REJECTED", "Evidence does not satisfy this contract's verifier policy."
            )
    c.update(status=status, revision=c["revision"] + 1, updated_at=s["now"])
    if evidence_id:
        c["evidence_ids"].append(evidence_id)
    emit(
        s,
        "commitment.verified" if status == "VERIFIED" else "commitment.updated",
        dict(contract_id=c["contract_id"], status=status, reason=reason, evidence_id=evidence_id),
    )


def add_evidence(s, db, household, c, kind, body, mime="application/json", provenance="SYNTHETIC_SENSOR"):
    evidence_id = "ev_" + uuid.uuid4().hex
    data = body if isinstance(body, bytes) else json.dumps(body, sort_keys=True).encode()
    sha = hashlib.sha256(data).hexdigest()
    previous = s["evidence"][-1]["chain_hash"] if s["evidence"] else "0" * 64
    item = dict(
        evidence_id=evidence_id,
        contract_id=c["contract_id"],
        kind=kind,
        source_platform="SYNTHETIC_FIXTURE",
        source_mode=MODE,
        provenance=provenance,
        captured_at=s["now"],
        received_at=s["now"],
        sha256_original=sha,
        previous_hash=previous,
        mime=mime,
        media_duration_ms=0,
        consent_grant_id="demo-explicit-consent",
        retention_expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        decision="VALIDATED",
        capture_gaps=[],
        confidence=1.0,
        model_name_version="synthetic-calibrated-markers-v1",
    )
    item["chain_hash"] = digest(item)
    db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?)", (evidence_id, household, mime, data, sha))
    s["evidence"].append(item)
    emit(s, "commitment.evidence_collected", dict(evidence_id=evidence_id, kind=kind, sha256=sha))
    return evidence_id


def create_contract(s, key, title, quote, counterparty, modality, due=None, trigger=None, uncertain=False):
    cid = "psc_" + key
    if any(c["contract_id"] == cid for c in s["contracts"]):
        return next(c for c in s["contracts"] if c["contract_id"] == cid)
    c = dict(
        contract_id=cid,
        key=key,
        schema_version="1.0",
        household_id=s["household_id"],
        actor={"id": "owner", "role": "SELF"},
        counterparty={"label": counterparty},
        original_utterance=quote,
        speaker_context="Consented synthetic household conversation",
        title=title,
        type={"drinks": "INBOUND_ITEM", "squats": "PHYSICAL_ACTION", "parcel": "PARCEL_CUSTODY"}.get(
            key, "SCHEDULED_SOCIAL_COMMITMENT"
        ),
        status="NEEDS_CONFIRMATION" if uncertain else "ACTIVE",
        confidence=0.6 if uncertain else 0.95,
        due_at=due,
        timezone=ZONE,
        deadline_trigger=trigger,
        verification_modality=modality,
        required_evidence=[modality],
        privacy_scope="HOUSEHOLD",
        evidence_ids=[],
        revision=1,
        source_mode=MODE,
        created_at=s["now"],
        updated_at=s["now"],
        scheduled_jobs=[],
    )
    if due:
        for tier, minutes in [("T60", 60), ("T25", 25), ("DEADLINE", 0)]:
            c["scheduled_jobs"].append(
                dict(
                    kind=tier,
                    at=(datetime.fromisoformat(due) - timedelta(minutes=minutes)).isoformat(),
                    status="PENDING",
                )
            )
        s["subagents"].append(
            dict(
                subagent_id="social_" + key,
                kind="SocialGraphAuditor",
                contract_id=cid,
                status="WATCHING",
                last_observation_at=s["now"],
            )
        )
    s["contracts"].append(c)
    emit(
        s,
        "commitment.confirmation_required" if uncertain else "commitment.created",
        dict(contract_id=cid, title=title, status=c["status"]),
    )
    return c


def compile_bee(s, bee: BeeInput):
    if not s["consent"]:
        raise ApiError(409, "CONSENT_REVOKED", "Processing is paused until consent is restored.")
    from zoneinfo import ZoneInfoNotFoundError

    try:
        zone = ZoneInfo(bee.timezone)
    except ZoneInfoNotFoundError:
        raise ApiError(422, "INVALID_TIMEZONE", "Use a valid IANA timezone.")
    existing = [
        e
        for e in s["events"]
        if e["event_type"] == "bee.utterance.received" and e["payload"]["source_event_id"] == bee.event_id
    ]
    if existing:
        return []
    emit(
        s,
        "bee.utterance.received",
        dict(source_event_id=bee.event_id, utterance=bee.utterance, speaker=bee.speaker),
    )
    text = bee.utterance.lower()
    if not re.search(
        r"\b(i(?:'ll| will| promise)|i promised|i need to|i should|can you|please|bring)\b", text
    ):
        return []
    if re.search(r"\b(called|already|finished|ignore .*instructions|mark .*verified)\b", text):
        return []
    uncertain = bee.speaker != "SELF" or not re.search(r"\bi(?:'ll| will| promise| promised)\b", text)
    specs = [
        (
            "drinks",
            r"drink|bottle",
            "Bring cold drinks home",
            "Wife",
            "RING_THRESHOLD_OBJECT_SCAN",
            None,
            "ARRIVAL_HOME",
        ),
        ("sister", r"sister", "Call your sister", "Sister", "BEE_CONVERSATION_AUDIT", "18:00", None),
        (
            "teacher",
            r"teacher|meeting",
            "Attend nephew’s teacher meeting",
            "Nephew’s teacher",
            "BEE_CONVERSATION_AUDIT",
            "16:00",
            None,
        ),
        (
            "squats",
            r"squat",
            "15 squats before TV",
            "Self",
            "FIRE_TV_LIVE_POSE_CAMERA",
            None,
            "BEFORE_ENTERTAINMENT",
        ),
    ]
    created = []
    for key, pattern, title, person, modality, hm, trigger in specs:
        if re.search(pattern, text):
            due = None
            if hm:
                match = re.search(r"(?:at|before|by)\s+(\d{1,2})(?::(\d\d))?\s*(am|pm)", text)
                hh, mm = map(int, hm.split(":"))
                if match:
                    hh = int(match[1]) % 12 + (12 if match[3] == "pm" else 0)
                    mm = int(match[2] or 0)
                due = (
                    bee.occurred_at.astimezone(zone)
                    .replace(hour=hh, minute=mm, second=0, microsecond=0)
                    .astimezone(timezone.utc)
                    .isoformat()
                )
            existing_c = next((c for c in s["contracts"] if c["key"] == key), None)
            if existing_c and due and existing_c["due_at"] != due and existing_c["status"] not in TERMINAL:
                existing_c["due_at"] = due
                existing_c["revision"] += 1
                existing_c["scheduled_jobs"] = [
                    dict(
                        kind=t,
                        at=(datetime.fromisoformat(due) - timedelta(minutes=m)).isoformat(),
                        status="PENDING",
                    )
                    for t, m in [("T60", 60), ("T25", 25), ("DEADLINE", 0)]
                ]
                emit(
                    s,
                    "commitment.updated",
                    dict(contract_id=existing_c["contract_id"], reason="Authorized deadline amendment"),
                )
                created.append(existing_c["contract_id"])
            else:
                created.append(
                    create_contract(s, key, title, bee.utterance, person, modality, due, trigger, uncertain)[
                        "contract_id"
                    ]
                )
    return created


def alert(s, c, kind, message, action=None):
    item = dict(
        alert_id="alert_" + str(len(s["alerts"]) + 1),
        contract_id=c["contract_id"],
        kind=kind,
        message=message,
        action=action or "/?contract=" + c["contract_id"],
        at=s["now"],
        source_mode=MODE,
        provider="AUTHENTICATED_COMPANION",
        delivered=True,
    )
    s["alerts"].append(item)
    emit(s, "commitment.escalation_dispatched", item)


def tick(s, now):
    current = datetime.fromisoformat(now)
    if current < datetime.fromisoformat(s["now"]):
        raise ApiError(409, "CLOCK_REWIND", "Reset the isolated demo before moving time backwards.")
    s["now"] = now
    if not s["consent"]:
        return
    for c in s["contracts"]:
        for job in c["scheduled_jobs"]:
            if job["status"] != "PENDING" or datetime.fromisoformat(job["at"]) > current:
                continue
            if c["status"] in TERMINAL or c["status"] == "NEEDS_CONFIRMATION":
                job["status"] = "SKIPPED"
                continue
            job.update(status="EXECUTED", executed_at=now)
            late = current >= datetime.fromisoformat(c["due_at"])
            if job["kind"] == "DEADLINE":
                revise(
                    s,
                    c,
                    "MISSED",
                    "Deadline passed without accepted proof; delayed evidence remains possible.",
                )
            elif late:
                emit(
                    s,
                    "commitment.engagement_evaluated",
                    dict(contract_id=c["contract_id"], tier=job["kind"], decision="STALE_SKIPPED"),
                )
            elif job["kind"] == "T25" and c.get("engagement") == "ENGAGED":
                emit(
                    s,
                    "commitment.engagement_evaluated",
                    dict(contract_id=c["contract_id"], tier="T25", decision="QUIET_ON_TRACK"),
                )
            else:
                tier = "SILENT_PREP" if job["kind"] == "T60" else "ACTIVE_ESCALATION"
                remaining = round((datetime.fromisoformat(c["due_at"]) - current).total_seconds() / 60)
                alert(
                    s,
                    c,
                    tier,
                    f"{c['title']} is due in {remaining} minutes. "
                    + (
                        "Prepare quietly."
                        if tier == "SILENT_PREP"
                        else "Preparation is unconfirmed. Open details to act."
                    ),
                )


def verify_social(s, db, household, key):
    c = contract(s, key)
    if c["status"] == "VERIFIED":
        return
    ev = add_evidence(
        s,
        db,
        household,
        c,
        "AUTHORIZED_PARTICIPATION",
        dict(target=key, participation=True, source="SYNTHETIC_AUTHORIZED_TRANSCRIPT", occurred_at=s["now"]),
    )
    revise(s, c, "VERIFIED", "Matching authorized participation evidence; simulated source.", ev)


def studio_start(s):
    c = contract(s, "squats")
    if not s["consent"]:
        raise ApiError(409, "CONSENT_REVOKED", "Camera processing is paused.")
    if s["studio"]:
        return
    s["studio"] = dict(
        session_id="studio_" + uuid.uuid4().hex,
        contract_id=c["contract_id"],
        source_mode=MODE,
        source="SYNTHETIC_MARKER_FRAMES",
        status="RUNNING",
        count=0,
        phase="STANDING",
        stable=0,
        gate="LOCKED",
        quality="AWAITING_FRAMES",
        angle=178,
        last_timestamp_ms=-1,
    )
    emit(s, "studio.camera_session_opened", dict(session_id=s["studio"]["session_id"], source_mode=MODE))


def pose_frame(s, db, household, frame_id, timestamp_ms, landmarks):
    session = s["studio"]
    if not session:
        raise ApiError(409, "NO_SESSION", "Start a studio session first.")
    if not s["consent"]:
        raise ApiError(409, "CONSENT_REVOKED", "Pose collection is disabled.")
    rep = vision.pose_update(session, frame_id, timestamp_ms, landmarks)
    if rep:
        emit(
            s,
            "studio.rep_verified",
            dict(
                session_id=session["session_id"],
                count=session["count"],
                angle=session["angle"],
                source_mode=MODE,
            ),
        )
        if session["count"] == 15 and session["gate"] != "UNLOCKED":
            c = contract(s, "squats")
            ev = add_evidence(
                s,
                db,
                household,
                c,
                "POSE_15_CYCLES",
                dict(count=15, source="SYNTHETIC_PIXELS", session_id=session["session_id"]),
            )
            revise(
                s,
                c,
                "VERIFIED",
                "15 complete cycles from synthetic marker pixel extraction, not live human verification.",
                ev,
            )
            session.update(gate="UNLOCKED", status="COMPLETED")
            emit(s, "studio.reality_lock_unlocked", dict(scope="IN_APP_ONLY", evidence_id=ev))
    return rep


def one_rep(s, db, household, half=False):
    studio_start(s)
    for i, frame in enumerate(vision.cycle_frames(half)):
        ts = s["studio"]["last_timestamp_ms"] + 160
        pose_frame(s, db, household, f"frame_{ts}_{i}", ts, vision.extract_marker_pose(frame))


def run_scenario(s, db, household, stage, branch):
    if not s["consent"]:
        raise ApiError(409, "CONSENT_REVOKED", "Restore explicit demo consent before replay.")
    if stage in {2, 4, 5, 6} and s["failures"]:
        raise ApiError(
            503,
            "SOURCE_UNAVAILABLE",
            "An injected source/storage failure is active; clear it before observation.",
        )
    s["scenario"] = stage
    if stage == 1:
        if not s["contracts"]:
            s["now"] = at("08:15")
        for key, text, person in [
            ("drinks", "I'll bring cold drinks home tonight.", "Wife"),
            ("sister", "I'll call my sister before 6 PM.", "Sister"),
            ("teacher", "I'll cover the teacher meeting at 4 PM.", "Teacher"),
            ("squats", "I'll do 15 squats before watching TV.", "Self"),
        ]:
            compile_bee(
                s,
                BeeInput(
                    event_id="morning_" + key,
                    utterance=text,
                    counterparty=person,
                    occurred_at=datetime.fromisoformat(at("08:15")),
                ),
            )
        return
    if not s["contracts"]:
        run_scenario(s, db, household, 1, "deposit")
        s["scenario"] = stage
    stage_time = {2: "14:10", 3: "15:00", 4: "16:30", 5: "19:45", 6: "20:30"}[stage]
    if datetime.fromisoformat(at(stage_time)) < datetime.fromisoformat(s["now"]):
        raise ApiError(
            409,
            "SCENARIO_ORDER",
            "This stage is earlier than the current clock. Reset to replay another branch.",
        )
    tick(s, at(stage_time))
    if stage == 2:
        c = create_contract(
            s,
            "parcel",
            "Keep parcel in safe custody",
            "I'm leaving the parcel at your doorstep.",
            "Courier",
            "RING_SPATIAL_CUSTODY",
            trigger="AUTHORIZED_INWARD_TRANSFER",
        )
        if c.get("deposit_status"):
            return
        verdict = vision.deposit_verdict(vision.fixture_frames("fake" if branch == "fake" else "deposit"))
        frame = vision.fixture_frames("fake" if branch == "fake" else "deposit")[-1]
        ev = add_evidence(s, db, household, c, "DEPOSIT_OBSERVATION", vision.png(frame), "image/png")
        if verdict == "DEPOSIT_CONFIRMED":
            c.update(deposit_status="DEPOSIT_VERIFIED", custody_status="DEPOSIT_VERIFIED_CUSTODY_ACTIVE")
            c["evidence_ids"].append(ev)
            s["subagents"].append(
                dict(
                    subagent_id="porch_parcel",
                    kind="PorchWatchdog",
                    contract_id=c["contract_id"],
                    status="WATCHING",
                    last_observation_at=s["now"],
                    restart_cursor="deposit-v1",
                    target_roi=[200 / 640, 150 / 360, 300 / 640, 185 / 360],
                    observation_gaps=["Event-driven monitoring; no continuous camera coverage."],
                )
            )
            emit(s, "parcel.deposit_verified", dict(contract_id=c["contract_id"], evidence_id=ev))
            alert(
                s,
                c,
                "DEPOSIT_OBSERVED",
                "Parcel was observed on your porch. PorchWatchdog is active; custody is not yet complete.",
            )
        else:
            c.update(deposit_status="DELIVERY_MISMATCH", custody_status="UNCONFIRMED")
            revise(s, c, "DISPUTED", "Courier departure did not establish deposit.")
            alert(
                s,
                c,
                "DELIVERY_MISMATCH",
                "Courier said the package was left, but I could not confirm a deposit. Review the camera evidence.",
            )
    elif stage == 3:
        c = contract(s, "teacher")
        c["engagement"] = "ENGAGED" if branch == "engaged" else "UNKNOWN"
        tick(s, at("15:35"))
        tick(s, at("16:05"))
        verify_social(s, db, household, "teacher")
    elif stage == 4:
        c = contract(s, "parcel")
        if c.get("custody_status") != "DEPOSIT_VERIFIED_CUSTODY_ACTIVE":
            raise ApiError(409, "NO_CUSTODY", "Removal requires an observed deposit and active custody.")
        if branch == "retained":
            emit(
                s, "watchdog.observation_updated", dict(contract_id=c["contract_id"], result="PARCEL_REMAINS")
            )
            return
        frames = vision.fixture_frames("removal")
        if vision.removal_verdict(frames) != "REMOVAL_UNDER_REVIEW":
            return
        if s["incidents"]:
            return
        ev = add_evidence(s, db, household, c, "REMOVAL_FRAME", vision.png(frames[-1]), "image/png")
        crop = frames[-1][80:270, 45:110]
        crop_ev = add_evidence(s, db, household, c, "PERSON_CROP", vision.png(crop), "image/png")
        packet = {
            "deposit_evidence_ids": c["evidence_ids"][:],
            "removal_evidence_id": ev,
            "person_crop_evidence_id": crop_ev,
            "trajectory": [[280, 265], [160, 265], [70, 265]],
            "coordinate_system": "SYNTHETIC_PIXELS",
            "capture_gaps": ["No live Ring footage. Synthetic snapshots only; 15-second clip unavailable."],
        }
        incident = dict(
            incident_id="inc_parcel",
            contract_id=c["contract_id"],
            status="AWAITING_HUMAN_DECISION",
            detected_at=s["now"],
            source_mode=MODE,
            packet=packet,
            manifest_hash=digest(packet),
            revision=1,
            receipt=None,
            approval=None,
            clip_actual_duration_seconds=0,
            quality="EVIDENCE_INCOMPLETE",
            destination="DEMO_RECEIVER_ONLY",
        )
        s["incidents"].append(incident)
        c["custody_status"] = "REMOVAL_UNDER_REVIEW"
        revise(s, c, "DISPUTED", "Observed streetward movement. Authorization requires owner review.")
        emit(s, "parcel.removal_observed", dict(incident_id=incident["incident_id"]))
        alert(s, c, "PORCH_REMOVAL", "A person moved the package from the porch. Was this authorized?")
        if branch == "family":
            incident_action(s, db, household, "inc_parcel", "authorize-pickup", {})
    elif stage == 5:
        c = contract(s, "drinks")
        frame = vision.scene(
            280 if not s["incidents"] else None,
            310,
            drinks=branch == "visible",
            occluded=branch == "ambiguous",
        )
        obs = vision.detect(frame)
        result = (
            "VISIBLE_MATCH" if "drinks" in obs else ("AMBIGUOUS" if "person" not in obs else "NOT_VISIBLE")
        )
        ev = add_evidence(s, db, household, c, "THRESHOLD_OBSERVATION", vision.png(frame), "image/png")
        c.update(
            visibility=result,
            observation_status="SUPPORTING_OBSERVATION" if result == "VISIBLE_MATCH" else "NEEDS_USER_CHECK",
        )
        c["evidence_ids"].append(ev)
        emit(
            s,
            "threshold.item_visible" if result == "VISIBLE_MATCH" else "threshold.item_not_visible",
            dict(
                result=result,
                contract_id=c["contract_id"],
                latency_ms=None,
                timing="Replay; no before-entry latency claim",
            ),
        )
        if result != "VISIBLE_MATCH":
            alert(
                s,
                c,
                "ARRIVAL_ITEM_CHECK",
                "Your drinks weren't visible as you approached the door. Check whether you have them.",
            )
    elif stage == 6:
        studio_start(s)
        emit(
            s, "studio.replay_ready", dict(message="Process synthetic frames in studio. No counter shortcut.")
        )


def incident_action(s, db, household, incident_id, action, data):
    inc = next((i for i in s["incidents"] if i["incident_id"] == incident_id), None)
    if not inc:
        raise ApiError(404, "NOT_FOUND", "Incident not found.")
    if action == "authorize-pickup":
        if inc["status"] not in {"AWAITING_HUMAN_DECISION", "EVIDENCE_PREPARED"}:
            raise ApiError(409, "INCIDENT_STATE", "This incident cannot accept pickup confirmation.")
        c = contract(s, "parcel")
        ev = add_evidence(
            s,
            db,
            household,
            c,
            "AUTHORIZED_TRANSFER",
            dict(statement="Owner confirms authorized family/friend transfer"),
            provenance="USER_CONFIRMED",
        )
        revise(s, c, "VERIFIED", "Owner-confirmed authorized transfer; not inferred identity.", ev)
        c["custody_status"] = "VERIFIED_SAFE_TRANSFER"
        inc["status"] = "AUTHORIZED_TRANSFER"
        for a in s["subagents"]:
            if a["kind"] == "PorchWatchdog":
                a["status"] = "CLOSED"
        emit(s, "parcel.transfer_authorized", dict(incident_id=incident_id, provenance="USER_CONFIRMED"))
    elif action == "prepare-report":
        if inc["status"] != "AWAITING_HUMAN_DECISION":
            raise ApiError(409, "INCIDENT_STATE", "Report preparation requires an unresolved incident.")
        inc["status"] = "EVIDENCE_PREPARED"
        emit(
            s, "incident.dossier_prepared", dict(incident_id=incident_id, manifest_hash=inc["manifest_hash"])
        )
    elif action == "approve-report":
        if (
            inc["status"] != "EVIDENCE_PREPARED"
            or data.get("manifest_hash") != inc["manifest_hash"]
            or data.get("destination") != "DEMO_RECEIVER_ONLY"
            or data.get("confirmation") != "APPROVE SIMULATED REPORT"
        ):
            raise ApiError(
                409,
                "EXACT_APPROVAL_REQUIRED",
                "Review the exact manifest, demo destination and confirmation phrase.",
            )
        verify_artifacts(s, db, household)
        inc.update(
            status="REPORT_APPROVED",
            approval=dict(
                manifest_hash=inc["manifest_hash"],
                destination="DEMO_RECEIVER_ONLY",
                approved_at=s["now"],
                owner="authenticated-owner",
            ),
        )
        emit(s, "incident.owner_approved", dict(incident_id=incident_id, destination="DEMO_RECEIVER_ONLY"))
    elif action == "dispatch-report":
        if inc["status"] != "REPORT_APPROVED" or not inc["approval"]:
            raise ApiError(403, "OWNER_APPROVAL_REQUIRED", "A model boolean is not owner approval.")
        verify_artifacts(s, db, household)
        inc.update(
            status="SIMULATED_DISPATCH",
            receipt=dict(
                label="SIMULATED DISPATCH — NOT SENT TO POLICE",
                receipt_id="DEMO-" + incident_id,
                official_case_id=None,
            ),
        )
        emit(
            s,
            "incident.dispatch_acknowledged",
            dict(incident_id=incident_id, simulated=True, external_sends=0),
        )
    elif action == "cancel-report":
        if inc["status"] not in {"EVIDENCE_PREPARED", "REPORT_APPROVED"}:
            raise ApiError(409, "INCIDENT_STATE", "No report review to cancel.")
        inc.update(status="AWAITING_HUMAN_DECISION", approval=None)
    else:
        raise ApiError(422, "UNKNOWN_ACTION", "Unsupported incident action.")
    inc["revision"] += 1


def verify_artifacts(s, db, household):
    previous = "0" * 64
    for item in s["evidence"]:
        row = db.execute(
            "SELECT data,sha256 FROM artifacts WHERE id=? AND household=?", (item["evidence_id"], household)
        ).fetchone()
        if not row or hashlib.sha256(row["data"]).hexdigest() != item["sha256_original"]:
            raise ApiError(409, "EVIDENCE_TAMPERED", "Evidence integrity check failed.")
        expected = {k: v for k, v in item.items() if k != "chain_hash"}
        if item["previous_hash"] != previous or digest(expected) != item["chain_hash"]:
            raise ApiError(409, "CHAIN_TAMPERED", "Evidence manifest chain is invalid.")
        previous = item["chain_hash"]
    for inc in s["incidents"]:
        if digest(inc["packet"]) != inc["manifest_hash"]:
            raise ApiError(409, "MANIFEST_TAMPERED", "Incident manifest integrity check failed.")
    return True
