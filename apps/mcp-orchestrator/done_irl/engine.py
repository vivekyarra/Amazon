"""Shared, durable reducers used by API, MCP, scheduler and judge replay."""

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .models import ApiError, BeeInput
from . import vision
from . import scene
from . import commitments as nl
from . import privacy

DAY = "2026-10-20"
ZONE = "Asia/Kolkata"
MODE = "SIMULATED_VERIFIED"
RECORDED_DEMO_SOURCE = "RECORDED_DEMO_VIDEO"
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
        clock_mode="VIRTUAL",
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
    linked = next((c for c in s["contracts"] if c["contract_id"] == payload.get("contract_id")), None)
    trace = trace or (linked or {}).get("trace_id") or s.get("_trace_id")
    event = dict(
        event_id=f"evt_{len(s['events']) + 1:06d}",
        schema_version="1.0",
        event_type=event_type,
        household_id=s.get("household_id", "demo"),
        actor_id="owner",
        source=s.get("_event_source", {}).get(
            "source", "SYNTHETIC_REPLAY" if s.get("clock_mode") != "WALL" else "HOUSEHOLD_SERVICE"
        ),
        source_mode=s.get("_event_source", {}).get("source_mode", s.get("source_mode", MODE)),
        occurred_at=s["now"],
        received_at=datetime.now(timezone.utc).isoformat(),
        trace_id=trace
        or (uuid.uuid4().hex if s.get("clock_mode") == "WALL" else f"trace_{s.get('scenario', 0)}"),
        idempotency_key=f"event:{len(s['events']) + 1}",
        consent_scope=s.get("_event_source", {}).get(
            "consent_scope", "demo" if s.get("clock_mode") != "WALL" else "household"
        ),
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
        by_modality = {
            "BEE_CONVERSATION_AUDIT": {"AUTHORIZED_PARTICIPATION", "USER_CONFIRMATION"},
            "AUTHORIZED_MANUAL_CONFIRMATION": {"USER_CONFIRMATION"},
            "RING_THRESHOLD_OBJECT_SCAN": {"USER_CONFIRMATION"},
            "FIRE_TV_LIVE_POSE_CAMERA": {"POSE_15_CYCLES", "POSE_CYCLES"},
        }
        policy = (
            by_modality.get(c["verification_modality"], set())
            if c["key"].startswith("gen_")
            else allowed.get(c["key"], set())
        )
        if not record or record["kind"] not in policy:
            raise ApiError(
                409, "EVIDENCE_POLICY_REJECTED", "Evidence does not satisfy this contract's verifier policy."
            )
    c.update(status=status, revision=c["revision"] + 1, updated_at=s["now"])
    if evidence_id:
        c["evidence_ids"].append(evidence_id)
    if status == "VERIFIED":
        # Spec 4.3: an owner tap (USER_CONFIRMED) is never presented as sensor proof.
        c["verification_provenance"] = record["provenance"]
    if status == "VERIFIED":
        roll_recurrence(s, c)
    emit(
        s,
        "commitment.verified" if status == "VERIFIED" else "commitment.updated",
        dict(contract_id=c["contract_id"], status=status, reason=reason, evidence_id=evidence_id),
    )


def add_evidence(
    s,
    db,
    household,
    c,
    kind,
    body,
    mime="application/json",
    provenance="SYNTHETIC_SENSOR",
    duration_ms=0,
    parent_evidence_id=None,
    sensor=None,
    privacy_mask=None,
    confidence=1.0,
):
    if not s["consent"]:
        raise ApiError(409, "CONSENT_REVOKED", "Evidence collection is paused.")
    evidence_id = "ev_" + uuid.uuid4().hex
    data = body if isinstance(body, bytes) else json.dumps(body, sort_keys=True).encode()
    sha = hashlib.sha256(data).hexdigest()
    previous = s["evidence"][-1]["chain_hash"] if s["evidence"] else "0" * 64
    sensor = sensor or {}
    item = dict(
        evidence_id=evidence_id,
        contract_id=c["contract_id"],
        trace_id=c.get("trace_id", s.get("_trace_id", f"trace_{s.get('scenario', 0)}")),
        kind=kind,
        source_platform=sensor.get(
            "platform", "OWNER_CONFIRMATION" if provenance == "USER_CONFIRMED" else "SYNTHETIC_FIXTURE"
        ),
        source_mode=sensor.get("source_mode", s.get("source_mode", MODE)),
        provenance=provenance,
        captured_at=s["now"],
        received_at=s["now"],
        sha256_original=sha,
        previous_hash=previous,
        mime=mime,
        media_duration_ms=duration_ms,
        parent_evidence_id=parent_evidence_id,
        consent_grant_id="household-explicit-consent"
        if s.get("clock_mode") == "WALL"
        else "demo-explicit-consent",
        retention_expires_at=(
            datetime.now(timezone.utc) + timedelta(days=privacy.retention_days(s))
        ).isoformat(),
        retention_days_at_capture=privacy.retention_days(s),
        decision="VALIDATED",
        capture_gaps=[],
        confidence=confidence,
        model_name_version=sensor.get(
            "model",
            "owner-statement-v1" if provenance == "USER_CONFIRMED" else "synthetic-calibrated-markers-v1",
        ),
    )
    if privacy_mask is not None:
        item["privacy_mask"] = privacy_mask
    item["chain_hash"] = digest(item)
    db.put_artifact(evidence_id, household, mime, data, sha)
    s["evidence"].append(item)
    emit(
        s,
        "commitment.evidence_collected",
        dict(contract_id=c["contract_id"], evidence_id=evidence_id, kind=kind, sha256=sha),
    )
    return evidence_id


def frame_evidence(s, db, household, c, kind, frame, crop=None, camera=privacy.SYNTHETIC_CAMERA):
    """Store a camera-derived snapshot/crop with PRIVATE_MASKS zeroed before encoding and hashing."""
    privacy.require_camera_allowed(s, camera)
    masked, meta = privacy.mask_frame(s, camera, frame)
    if crop:
        y0, y1, x0, x1 = crop
        masked = masked[y0:y1, x0:x1]
        meta = {**meta, "crop_pixels_y0_y1_x0_x1": list(crop)}
    return add_evidence(s, db, household, c, kind, vision.png(masked), "image/png", privacy_mask=meta)


def create_contract(s, key, title, quote, counterparty, modality, due=None, trigger=None, uncertain=False):
    cid = "psc_" + key
    if any(c["contract_id"] == cid for c in s["contracts"]):
        return next(c for c in s["contracts"] if c["contract_id"] == cid)
    c = dict(
        contract_id=cid,
        trace_id=s.get("_trace_id")
        or (uuid.uuid4().hex if s.get("clock_mode") == "WALL" else f"trace_{s.get('scenario', 0)}"),
        key=key,
        schema_version="1.0",
        household_id=s["household_id"],
        actor={"id": "owner", "role": "SELF"},
        counterparty={"label": counterparty},
        original_utterance=quote,
        speaker_context="Consented household conversation"
        if s.get("clock_mode") == "WALL"
        else "Consented synthetic household conversation",
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
        source_mode=s.get("_event_source", {}).get("source_mode", s.get("source_mode", MODE)),
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
    except (ZoneInfoNotFoundError, ValueError):
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
    text = bee.utterance.lower().replace("’", "'")
    if nl.INJECTION.search(text):
        emit(s, "commitment.rejected_input", {"source_event_id": bee.event_id, "decision": "POLICY_TEXT_IGNORED"})
        return []
    if bee.source_kind in {"BEE_TODO", "BEE_TODO_COMPLETED"}:
        return _compile_bee_todo(s, bee, zone)
    claim = nl.completion_claim(bee.utterance)
    if claim and bee.speaker == "SELF":
        _completion_claim(s, bee, claim)
        return []
    if not re.search(
        r"\b(i(?:'ll| will| promise)|i promised|i need to|i should|can you|please|bring)\b", text
    ) and not nl.PROMISE.search(text):
        return []
    if re.search(r"\b(i will not|i won't|i'll not|i cannot|i can't|do not|don't|did not|didn't)\b", text) and not (
        nl.NOT_FORGET.search(text)
    ):
        emit(
            s,
            "commitment.negation_observed",
            {"source_event_id": bee.event_id, "decision": "NO_NEW_OBLIGATION"},
        )
        return []
    uncertain = (
        bee.speaker != "SELF"
        or not re.search(r"^i(?:'ll| will| promise| promised)\b", text)
        or bool(re.search(r"\b(if|maybe|might)\b", text))
    )
    # The four canonical demo promises keep their named verifiers and sub-agents.
    specs = [
        (
            "drinks",
            r"\bdrinks?\b",
            "Bring cold drinks home",
            "Wife",
            "RING_THRESHOLD_OBJECT_SCAN",
            None,
            "ARRIVAL_HOME",
        ),
        ("sister", r"\bcall\b.*\bsister\b", "Call your sister", "Sister", "BEE_CONVERSATION_AUDIT", "18:00", None),
        (
            "teacher",
            r"\bteacher\b",
            "Attend nephew’s teacher meeting",
            "Nephew’s teacher",
            "BEE_CONVERSATION_AUDIT",
            "16:00",
            None,
        ),
        (
            "squats",
            r"\bsquats?\b.*\b(tv|television|watch)",
            "15 squats before TV",
            "Self",
            "FIRE_TV_LIVE_POSE_CAMERA",
            None,
            "BEFORE_ENTERTAINMENT",
        ),
    ]
    created = []
    # Canonical scene patterns (fixed 16:00/18:00 defaults) belong to the virtual judge day only;
    # real wall-clock households always use the general parser so relative times are honoured.
    canonical = s.get("clock_mode") != "WALL" and not re.search(r"\b(called|already|finished)\b", text)
    for key, pattern, title, person, modality, hm, trigger in specs if canonical else []:
        if re.search(pattern, text):
            due = None
            if hm:
                match = re.search(r"(?:at|before|by)\s+(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*(am|pm)", text)
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
            created.append(_upsert(s, bee, key, title, person, modality, due, trigger, uncertain)[0])
    if not created:
        now_local = bee.occurred_at.astimezone(zone)
        for cand in nl.parse(bee.utterance, now_local, request=bee.speaker != "SELF"):
            if cand.get("negated"):
                emit(
                    s,
                    "commitment.negation_observed",
                    {"source_event_id": bee.event_id, "decision": "NO_NEW_OBLIGATION"},
                )
                continue
            due = cand["due_local"].astimezone(timezone.utc).isoformat() if cand["due_local"] else None
            cid, writable = _upsert(
                s,
                bee,
                cand["key"],
                cand["title"],
                cand["counterparty"] if bee.speaker == "SELF" else bee.counterparty,
                cand["modality"],
                due,
                cand["trigger"],
                bee.speaker != "SELF" or cand["hedged"],
            )
            created.append(cid)
            if not writable:
                continue
            c = next(c for c in s["contracts"] if c["contract_id"] == cid)
            c.setdefault("commitment_origin", "GENERAL_PARSER")
            c.update(
                type=cand["type"],
                item_class=cand["item_class"],
                target_reps=cand["reps"],
                deadline_assumption=cand["assumption"],
                original_utterance=cand["sentence"],
                recurrence=cand.get("recurrence"),
            )
            if cand["modality"] == "AUTHORIZED_MANUAL_CONFIRMATION":
                c["verification_note"] = "No sensor can prove this task; completion is recorded as USER_CONFIRMED."
    for cid in created:
        next(c for c in s["contracts"] if c["contract_id"] == cid)["timezone"] = bee.timezone
    return created


def _compile_bee_todo(s, bee, zone):
    """A todo Bee itself extracted is the wearer's own list item: track it, keep Bee's alarm.

    The contract key is bound to the Bee todo id, so edits amend it; a todo the wearer ticks off in
    Bee closes it as USER_CONFIRMED (the owner's own action), never as sensor proof.
    """
    todo_id = bee.event_id.split(":")[2] if bee.event_id.startswith("bee:todo:") else None
    key = "gen_beetodo_" + re.sub(r"[^A-Za-z0-9_-]", "", todo_id)[:40] if todo_id else None
    if bee.source_kind == "BEE_TODO_COMPLETED":
        c = next((c for c in s["contracts"] if key and c["key"] == key), None)
        if not c or c["status"] in TERMINAL or c["verification_modality"] == "FIRE_TV_LIVE_POSE_CAMERA":
            return []
        c["completion_claim"] = dict(source_event_id=bee.event_id, utterance="Marked done in Bee", at=s["now"])
        if c["status"] in {"ACTIVE", "ENGAGED"}:
            revise(s, c, "EVIDENCE_PENDING", "Marked done in the Bee app; confirm to close (USER_CONFIRMED).")
        return [c["contract_id"]]
    text = bee.utterance.strip()
    phrased = "I need to " + text[:1].lower() + text[1:]
    cands = [c for c in nl.parse(phrased, bee.occurred_at.astimezone(zone)) if not c.get("negated")]
    if not cands:
        return []
    cand = cands[0]
    due = cand["due_local"].astimezone(timezone.utc).isoformat() if cand["due_local"] else None
    if bee.due_at:
        due = bee.due_at.astimezone(timezone.utc).isoformat()
    cid, writable = _upsert(s, bee, key or cand["key"], cand["title"], cand["counterparty"], cand["modality"], due,
                            cand["trigger"], bee.speaker != "SELF")
    if writable:
        c = next(c for c in s["contracts"] if c["contract_id"] == cid)
        c.update(
            commitment_origin="BEE_TODO" if bee.speaker == "SELF" else "UNVERIFIED_TODO_INPUT",
            type=cand["type"],
            item_class=cand["item_class"],
            target_reps=cand["reps"],
            deadline_assumption=None if bee.due_at else cand["assumption"],
            original_utterance=bee.utterance,
            timezone=bee.timezone,
            recurrence=cand.get("recurrence"),
        )
        if cand["modality"] == "AUTHORIZED_MANUAL_CONFIRMATION":
            c["verification_note"] = "No sensor can prove this task; completion is recorded as USER_CONFIRMED."
    return [cid]


def _upsert(s, bee, key, title, person, modality, due, trigger, uncertain):
    """Create or amend a contract. Returns (contract_id, writable)."""
    existing_c = next((c for c in s["contracts"] if c["key"] == key), None)
    if existing_c and existing_c["status"] in TERMINAL:
        # A promise repeated after it was resolved is a new obligation (e.g. trash again tomorrow).
        day = bee.occurred_at.date().isoformat()
        key = f"{key}@{day}"
        if any(c["key"] == key for c in s["contracts"]):
            key = f"{key}#{digest(bee.event_id)[:6]}"
        existing_c = next((c for c in s["contracts"] if c["key"] == key), None)
    if existing_c:
        accepted = existing_c["status"] not in {"NEEDS_CONFIRMATION", "DISCOVERED"}
        if bee.speaker != "SELF" and accepted:
            existing_c["proposed_amendment"] = dict(due_at=due, source_event_id=bee.event_id, at=s["now"])
            emit(s, "commitment.amendment_proposed",
                 dict(contract_id=existing_c["contract_id"], reason="Another speaker; owner confirmation required"))
            return existing_c["contract_id"], False
        if due and existing_c["due_at"] != due:
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
            if not any(a.get("contract_id") == existing_c["contract_id"] for a in s["subagents"]):
                s["subagents"].append(
                    dict(
                        subagent_id="social_" + key,
                        kind="SocialGraphAuditor",
                        contract_id=existing_c["contract_id"],
                        status="WATCHING",
                        last_observation_at=s["now"],
                    )
                )
            emit(
                s,
                "commitment.updated",
                dict(contract_id=existing_c["contract_id"], reason="Authorized deadline amendment"),
            )
        return existing_c["contract_id"], bee.speaker == "SELF"
    c = create_contract(s, key, title, bee.utterance, person, modality, due, trigger, uncertain)
    return c["contract_id"], True


def _completion_claim(s, bee, claim):
    """A spoken "I already did it" is a lead, never proof: EVIDENCE_PENDING until the owner confirms."""
    words = nl.tokens(claim)
    best, score = None, 0
    for c in s["contracts"]:
        if not c["key"].startswith("gen_") or c["status"] not in {"ACTIVE", "ENGAGED", "MISSED"}:
            continue
        target = nl.tokens(c["title"] + " " + c["counterparty"]["label"])
        if not nl.specific(words) & nl.specific(target):
            continue
        overlap = len(words & target)
        if overlap > score:
            best, score = c, overlap
    if not best or score < 2:
        emit(s, "commitment.completion_unmatched", {"source_event_id": bee.event_id})
        return
    best["completion_claim"] = dict(source_event_id=bee.event_id, utterance=bee.utterance, at=s["now"])
    if best["status"] in {"ACTIVE", "ENGAGED"}:
        revise(s, best, "EVIDENCE_PENDING", "Spoken completion claim; owner confirmation still required.")
    else:
        emit(s, "commitment.updated", dict(contract_id=best["contract_id"], reason="Late completion claim recorded"))


ROLLABLE = {"ACTIVE", "ENGAGED", "EVIDENCE_PENDING", "MISSED", "VERIFIED"}


def roll_recurrence(s, c):
    """Create the next occurrence of an accepted recurring promise exactly once (after proof or deadline).

    Never-accepted, rejected or cancelled series stop. After downtime the series jumps to the next
    future occurrence instead of replaying every missed day. Steps are taken in local days (DST-safe).
    """
    series = c.get("recurrence")
    if not series or not c.get("due_at") or c.get("next_occurrence_id") or c["status"] not in ROLLABLE:
        return None
    zone = ZoneInfo(c.get("timezone") or ZONE)
    local = datetime.fromisoformat(c["due_at"]).astimezone(zone)
    now = datetime.fromisoformat(s["now"])
    for _ in range(400):
        local = nl.next_occurrence(series, local).replace(tzinfo=zone)
        if local > now:
            break
    due = local.astimezone(timezone.utc)
    base = c.get("series_key") or c["key"]
    key = f"{base}~{local.date().isoformat()}"
    if any(x["key"] == key for x in s["contracts"]):
        c["next_occurrence_id"] = next(x["contract_id"] for x in s["contracts"] if x["key"] == key)
        return None
    nxt = create_contract(
        s, key, c["title"], c["original_utterance"], c["counterparty"]["label"], c["verification_modality"],
        due.isoformat(), c.get("deadline_trigger"), False,
    )
    for field in ("type", "item_class", "target_reps", "verification_note", "commitment_origin", "recurrence", "timezone"):
        if c.get(field) is not None:
            nxt[field] = c[field]
    nxt["series_key"] = base
    nxt["deadline_assumption"] = "Next occurrence of a recurring promise."
    c["next_occurrence_id"] = nxt["contract_id"]
    emit(s, "commitment.recurrence_scheduled", dict(contract_id=nxt["contract_id"], previous=c["contract_id"]))
    return nxt


def morning_briefing(s, current):
    """Wall-clock households get one private summary between 08:00 and 11:00 local time."""
    zone = ZoneInfo(s.get("timezone") or ZONE)
    local = current.astimezone(zone)
    today = local.date().isoformat()
    if s.get("last_briefing_date") == today or not 8 <= local.hour < 11:
        return
    s["last_briefing_date"] = today
    open_ = [c for c in s["contracts"] if c["status"] in {"ACTIVE", "ENGAGED", "EVIDENCE_PENDING", "MISSED",
                                                           "NEEDS_CONFIRMATION", "DISPUTED"}]
    if not open_:
        return
    due_today = [
        c for c in open_
        if c.get("due_at") and datetime.fromisoformat(c["due_at"]).astimezone(zone).date() == local.date()
        and c["status"] in {"ACTIVE", "ENGAGED"}
    ]
    parts = []
    if due_today:
        listed = ", ".join(
            f"{c['title']} ({datetime.fromisoformat(c['due_at']).astimezone(zone):%H:%M})" for c in due_today[:4]
        )
        parts.append(f"{len(due_today)} due today: {listed}")
    for label, status in [("overdue", "MISSED"), ("awaiting your confirmation", "EVIDENCE_PENDING"),
                          ("to accept or decline", "NEEDS_CONFIRMATION"), ("disputed", "DISPUTED")]:
        n = sum(1 for c in open_ if c["status"] == status)
        if n:
            parts.append(f"{n} {label}")
    triggered = sum(1 for c in open_ if c.get("deadline_trigger") and not c.get("due_at"))
    if triggered:
        parts.append(f"{triggered} waiting on a trigger (arrival home / before TV)")
    item = dict(
        alert_id="alert_" + str(len(s["alerts"]) + 1),
        contract_id=None,
        kind="DAILY_BRIEFING",
        message="Good morning. " + "; ".join(parts) + ".",
        action="/",
        at=s["now"],
        source_mode=s.get("source_mode", MODE),
        provider="AUTHENTICATED_COMPANION",
        delivery_status="STORED_FOR_COMPANION",
        device_delivery_verified=False,
    )
    s["alerts"].append(item)
    emit(s, "commitment.daily_briefing", dict(alert_id=item["alert_id"], open_contracts=len(open_)))


def alert(s, c, kind, message, action=None):
    item = dict(
        alert_id="alert_" + str(len(s["alerts"]) + 1),
        contract_id=c["contract_id"],
        kind=kind,
        message=message,
        action=action or "/?contract=" + c["contract_id"],
        at=s["now"],
        source_mode=s.get("source_mode", MODE),
        provider="AUTHENTICATED_COMPANION",
        delivery_status="STORED_FOR_COMPANION",
        device_delivery_verified=False,
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
    if s.get("clock_mode") == "WALL":
        morning_briefing(s, current)
    for c in list(s["contracts"]):
        for job in c["scheduled_jobs"]:
            if job["status"] != "PENDING" or datetime.fromisoformat(job["at"]) > current:
                continue
            if c["status"] in TERMINAL or c["status"] == "NEEDS_CONFIRMATION":
                job["status"] = "SKIPPED"
                continue
            job.update(status="EXECUTED", executed_at=now)
            late = current >= datetime.fromisoformat(c["due_at"])
            if c["status"] == "EVIDENCE_PENDING":
                emit(
                    s,
                    "commitment.engagement_evaluated",
                    dict(contract_id=c["contract_id"], tier=job["kind"], decision="AWAITING_OWNER_CONFIRMATION"),
                )
                if job["kind"] == "DEADLINE":
                    alert(s, c, "CONFIRMATION_REQUEST",
                          f"You said '{c['title']}' was done. Confirm it in DONE/IRL so it can close.")
            elif job["kind"] == "DEADLINE":
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
        if c.get("recurrence") and any(
            j["kind"] == "DEADLINE" and j["status"] in {"EXECUTED", "SKIPPED"} for j in c["scheduled_jobs"]
        ):
            roll_recurrence(s, c)


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


def pose_contract(s):
    """The promise Reality-Lock verifies: the canonical squats or any open pose-camera promise."""
    c = next((c for c in s["contracts"] if c["key"] == "squats"), None)
    if c:
        return c
    c = next(
        (c for c in s["contracts"]
         if c["verification_modality"] == "FIRE_TV_LIVE_POSE_CAMERA" and c["status"] not in TERMINAL),
        None,
    )
    if not c:
        raise ApiError(409, "PREREQUISITE", "No pending pose-verified promise (e.g. 'I'll do 15 squats before TV').")
    return c


def studio_start(s, source="SYNTHETIC_MARKER_FRAMES", source_mode=MODE):
    c = pose_contract(s)
    if not s["consent"]:
        raise ApiError(409, "CONSENT_REVOKED", "Camera processing is paused.")
    if s["studio"]:
        return
    s["studio"] = dict(
        session_id="studio_" + uuid.uuid4().hex,
        contract_id=c["contract_id"],
        source_mode=source_mode,
        source=source,
        status="RUNNING",
        target_reps=int(c.get("target_reps") or 15),
        count=0,
        phase="STANDING",
        stable=0,
        gate="LOCKED",
        quality="AWAITING_FRAMES",
        angle=178,
        last_timestamp_ms=-1,
    )
    emit(
        s, "studio.camera_session_opened", dict(session_id=s["studio"]["session_id"], source_mode=source_mode)
    )


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
                contract_id=session["contract_id"],
                count=session["count"],
                angle=session["angle"],
                source_mode=session["source_mode"],
            ),
        )
        target = int(session.get("target_reps") or 15)
        if session["count"] == target and session["gate"] != "UNLOCKED":
            c = next(c for c in s["contracts"] if c["contract_id"] == session["contract_id"])
            live = session["source"] == "LIVE_RING_WHEP"
            recorded = session["source"] == RECORDED_DEMO_SOURCE
            body = dict(
                count=target,
                source=session["source"],
                session_id=session["session_id"],
                verified_reps=session.get("verified_reps", []),
                model_sha256=session.get("model_sha256"),
            )
            if recorded:
                body.update(label="RECORDED DEMO", fixture=session.get("fixture"))
            ev = add_evidence(
                s,
                db,
                household,
                c,
                "POSE_15_CYCLES" if target == 15 else "POSE_CYCLES",
                body,
                provenance="LIVE_SENSOR" if live else "RECORDED_DEMO" if recorded else "SYNTHETIC_SENSOR",
                sensor={
                    "platform": "RING_WHEP",
                    "source_mode": "LIVE_VERIFIED",
                    "model": "MediaPipe-PoseLandmarker:" + session.get("model_sha256", ""),
                }
                if live
                else {
                    "platform": RECORDED_DEMO_SOURCE,
                    "source_mode": "SIMULATED_VERIFIED",
                    "model": "MediaPipe-PoseLandmarker:" + session.get("model_sha256", ""),
                }
                if recorded
                else None,
            )
            revise(
                s,
                c,
                "VERIFIED",
                f"{target} complete MediaPipe cycles from decoded Ring WHEP frames."
                if live
                else f"{target} complete MediaPipe cycles from a RECORDED DEMO video fixture, not a live Ring camera."
                if recorded
                else f"{target} complete cycles from synthetic marker pixel extraction, not live human verification.",
                ev,
            )
            session.update(gate="UNLOCKED", status="COMPLETED")
            emit(s, "studio.reality_lock_unlocked", dict(scope="IN_APP_ONLY", evidence_id=ev))
    return rep


def one_rep(s, db, household, half=False):
    studio_start(s)
    cycle_index = s["studio"].get("fixture_cycle_index", 0)
    s["studio"]["fixture_cycle_index"] = cycle_index + 1
    for i, frame in enumerate(vision.cycle_frames(half, offset=cycle_index * 3)):
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
    if stage in {2, 4, 5}:
        # The synthetic porch camera honors owner exclusion exactly like a linked device.
        privacy.require_camera_allowed(s, privacy.SYNTHETIC_CAMERA)
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
        if branch.startswith("real_"):
            return scene.real_deposit_stage(s, db, household, c, branch)
        frames = [
            privacy.mask_frame(s, privacy.SYNTHETIC_CAMERA, f)[0]
            for f in vision.fixture_frames("fake" if branch == "fake" else "deposit")
        ]
        verdict = vision.deposit_verdict(frames)
        ev = frame_evidence(s, db, household, c, "DEPOSIT_OBSERVATION", frames[-1])
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
        if branch.startswith("real_"):
            return scene.real_watchdog_stage(s, db, household, c, branch)
        frames = [
            privacy.mask_frame(s, privacy.SYNTHETIC_CAMERA, f)[0] for f in vision.fixture_frames("removal")
        ]
        if vision.removal_verdict(frames) != "REMOVAL_UNDER_REVIEW":
            return
        if s["incidents"]:
            return
        ev = frame_evidence(s, db, household, c, "REMOVAL_FRAME", frames[-1])
        crop_ev = frame_evidence(s, db, household, c, "PERSON_CROP", frames[-1], crop=(80, 270, 45, 110))
        regions = privacy.polygons(s, privacy.SYNTHETIC_CAMERA)
        clip_mask = privacy.mask_frame(s, privacy.SYNTHETIC_CAMERA, frames[-1])[1]
        video = vision.synthetic_removal_video(regions)
        source_clip = None
        annotated_clip = None
        if video:
            source_clip = add_evidence(
                s,
                db,
                household,
                c,
                "REMOVAL_CLIP_ORIGINAL",
                video[0],
                "video/webm",
                duration_ms=15000,
                privacy_mask={**clip_mask, "masked_regions": 0, "scope": "ORIGINAL_UNMASKED_ENCRYPTED"},
            )
            annotated_clip = add_evidence(
                s,
                db,
                household,
                c,
                "REMOVAL_CLIP_DERIVED",
                video[1],
                "video/webm",
                duration_ms=15000,
                parent_evidence_id=source_clip,
                privacy_mask=clip_mask,
            )
        packet = {
            "deposit_evidence_ids": c["evidence_ids"][:],
            "removal_evidence_id": ev,
            "source_clip_evidence_id": source_clip,
            "annotated_clip_evidence_id": annotated_clip,
            "person_crop_evidence_id": crop_ev,
            "trajectory": [[280, 265], [160, 265], [70, 265]],
            "coordinate_system": "SYNTHETIC_PIXELS",
            "capture_gaps": [
                "No live Ring footage. Generated 15-second synthetic clip."
                if video
                else "No live Ring footage; encoder unavailable, snapshots only."
            ],
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
            clip_actual_duration_seconds=15 if video else 0,
            quality="SYNTHETIC_CLIP_AVAILABLE" if video else "EVIDENCE_INCOMPLETE",
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
        if branch.startswith("real_"):
            return scene.real_threshold_stage(s, db, household, c, branch)
        frame = vision.scene(
            280 if not s["incidents"] else None,
            310,
            drinks=branch == "visible",
            occluded=branch == "ambiguous",
        )
        frame = privacy.mask_frame(s, privacy.SYNTHETIC_CAMERA, frame)[0]
        obs = vision.detect(frame)
        result = (
            "VISIBLE_MATCH" if "drinks" in obs else ("AMBIGUOUS" if "person" not in obs else "NOT_VISIBLE")
        )
        ev = frame_evidence(s, db, household, c, "THRESHOLD_OBSERVATION", frame)
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
        row = db.get_artifact(item["evidence_id"], household)
        if (
            not row
            and db.execute(
                "SELECT id FROM retention_tombstones WHERE id=? AND household=?",
                (item["evidence_id"], household),
            ).fetchone()
        ):
            raise ApiError(
                410, "EVIDENCE_EXPIRED", "Retained manifest references an expired, deleted artifact."
            )
        if not row or hashlib.sha256(row["data"]).hexdigest() != item["sha256_original"]:
            raise ApiError(409, "EVIDENCE_TAMPERED", "Evidence integrity check failed.")
        # Owner retention changes update the effective expiry; the chain covers the at-capture value.
        expected = {k: v for k, v in item.items() if k not in {"chain_hash", "retention_expires_at_original"}}
        if "retention_expires_at_original" in item:
            expected["retention_expires_at"] = item["retention_expires_at_original"]
        if item["previous_hash"] != previous or digest(expected) != item["chain_hash"]:
            raise ApiError(409, "CHAIN_TAMPERED", "Evidence manifest chain is invalid.")
        previous = item["chain_hash"]
    for inc in s["incidents"]:
        if digest(inc["packet"]) != inc["manifest_hash"]:
            raise ApiError(409, "MANIFEST_TAMPERED", "Incident manifest integrity check failed.")
    return True
