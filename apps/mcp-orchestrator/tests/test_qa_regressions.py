"""Regressions for the QA findings of 21 October 2026 (one test per reproduced issue)."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from done_irl import commitments as nl
from done_irl import engine as e
from done_irl.adapters import normalize_bee_event
from done_irl.models import ApiError, BeeInput

IST = ZoneInfo("Asia/Kolkata")


def wall(now="2026-10-21T04:30:00+00:00"):  # 10:00 IST, a Wednesday
    s = e.fresh()
    s.update(household_id="h", clock_mode="WALL", now=now, timezone="Asia/Kolkata")
    return s


def say(s, text, at=None, speaker="SELF", eid=None, **extra):
    at = at or s["now"]
    return e.compile_bee(s, BeeInput(event_id=eid or f"ev{len(s['events'])}", utterance=text, speaker=speaker,
                                     occurred_at=at, **extra))


def gen(s):
    return [c for c in s["contracts"] if c["key"].startswith("gen_")]


def test_h2_negated_completion_does_not_silence_a_promise():
    s = wall()
    say(s, "I'll pay rent by 6 pm")
    say(s, "I did not pay rent")
    [c] = gen(s)
    assert c["status"] == "ACTIVE"


def test_h2_generic_verbs_do_not_match_the_wrong_bill_and_claims_get_a_deadline_check():
    s = wall()
    say(s, "I'll pay the internet bill by 6 pm")
    say(s, "I paid the electricity bill")
    [c] = gen(s)
    assert c["status"] == "ACTIVE"
    say(s, "I paid the internet bill")
    assert c["status"] == "EVIDENCE_PENDING"
    e.tick(s, "2026-10-21T13:00:00+00:00")
    assert [a["kind"] for a in s["alerts"] if a["contract_id"] == c["contract_id"]][-1] == "CONFIRMATION_REQUEST"


def test_h3_unaccepted_or_rejected_recurring_requests_never_spawn():
    s = wall()
    say(s, "Can you water the plants every day at 7 pm", speaker="FAMILY_MEMBER")
    [c] = gen(s)
    assert c["status"] == "NEEDS_CONFIRMATION"
    e.tick(s, "2026-10-23T16:00:00+00:00")
    assert len(gen(s)) == 1
    e.revise(s, c, "REJECTED", "owner declined")
    e.tick(s, "2026-10-25T16:00:00+00:00")
    assert len(gen(s)) == 1


def test_h4_repeating_a_resolved_promise_creates_a_new_obligation():
    s = wall()
    say(s, "I'll take out the trash tonight")
    [first] = gen(s)
    e.revise(s, first, "CANCELLED", "done earlier")
    say(s, "I'll take out the trash tonight", at="2026-10-22T04:30:00+00:00", eid="next-day")
    first, second = gen(s)
    assert second["status"] == "ACTIVE" and second["contract_id"] != first["contract_id"]
    assert first["status"] == "CANCELLED"


def test_h5_briefing_fires_on_a_server_running_through_midnight():
    s = wall(now="2026-10-20T18:29:00+00:00")  # 23:59 IST
    say(s, "I'll call Mom at 9 pm tomorrow")
    t = datetime.fromisoformat(s["now"])
    for _ in range(11 * 60):
        t += timedelta(minutes=1)
        e.tick(s, t.isoformat())
    assert len([a for a in s["alerts"] if a["kind"] == "DAILY_BRIEFING"]) == 1


@pytest.mark.parametrize("text", ["I'll call mom at 12:75 pm", "I'll do it in 99999999 days", "I'll call at 12:99 am"])
def test_h6_odd_times_never_crash(text):
    s = wall()
    say(s, text)


@pytest.mark.parametrize("tz", ["../../x", "", "UTC\x00"])
def test_h6_bad_timezones_are_422(tz):
    s = wall()
    with pytest.raises(ApiError) as err:
        e.compile_bee(s, BeeInput(event_id="tz", utterance="I'll call mom tonight", occurred_at=s["now"], timezone=tz))
    assert err.value.status == 422


def test_h7_real_household_squat_promise_binds_the_studio_with_its_own_target():
    s = wall()
    say(s, "I'll do 20 squats before watching TV")
    c = e.pose_contract(s)
    assert c["key"].startswith("gen_") and c["target_reps"] == 20
    e.studio_start(s)
    assert s["studio"]["contract_id"] == c["contract_id"] and s["studio"]["target_reps"] == 20


def test_m1_other_speakers_cannot_move_an_accepted_deadline():
    s = wall()
    say(s, "I'll call my mom at 6 pm")
    [c] = gen(s)
    due = c["due_at"]
    say(s, "Can you call my mom at 9 pm", speaker="UNKNOWN")
    assert c["due_at"] == due and c["proposed_amendment"]["due_at"]


def test_m2_unattributed_todo_input_needs_confirmation():
    s = wall()
    say(s, "Renew passport", speaker="UNKNOWN", source_kind="BEE_TODO", eid="bee:todo:9:abc")
    [c] = gen(s)
    assert c["status"] == "NEEDS_CONFIRMATION" and c["commitment_origin"] != "BEE_TODO"


def test_m3_negative_and_not_forget_forms():
    s = wall()
    say(s, "I'll not go to the party tonight")
    assert not gen(s)
    say(s, "I won't forget to call mom tonight")
    assert gen(s)[0]["title"] == "Call mom"


def test_m4_weekly_plural_weekday_lands_on_that_weekday():
    [c] = nl.parse("I'll call grandma on Sundays", datetime(2026, 10, 21, 10, 0, tzinfo=IST))
    assert c["due_local"].weekday() == 6 and c["recurrence"] == {"freq": "WEEKLY", "weekday": 6}


def test_m5_downtime_catch_up_jumps_to_the_next_future_occurrence():
    s = wall()
    say(s, "I'll water the plants every day at 7 pm")
    e.tick(s, "2026-11-20T04:30:00+00:00")
    assert len(gen(s)) == 2
    assert datetime.fromisoformat(gen(s)[1]["due_at"]) > datetime.fromisoformat(s["now"])


def test_m6_weekend_said_late_saturday_is_not_born_overdue():
    sat_night = datetime(2026, 10, 24, 20, 0, tzinfo=IST)
    [c] = nl.parse("I'll clean the garage this weekend", sat_night)
    assert c["due_local"] > sat_night


def test_m7_user_confirmed_provenance_is_recorded(app, post):
    say_body = dict(event_id="m7", utterance="I'll pay the electricity bill by 6 pm", speaker="SELF",
                    occurred_at=e.at("08:15"))
    s = post("/ingest/bee-simulated", say_body)["state"]
    [c] = [c for c in s["contracts"] if c["key"].startswith("gen_")]
    s = post(f"/contracts/{c['contract_id']}/confirm", {"action": "confirm-done"})["state"]
    [c] = [c for c in s["contracts"] if c["key"].startswith("gen_")]
    assert c["status"] == "VERIFIED" and c["verification_provenance"] == "USER_CONFIRMED"


@pytest.mark.parametrize("bad", [1e20, 9e15, float("inf"), True, -5])
def test_m8_bee_epoch_poison_is_ignored(bad):
    data = {"conversation_uuid": "c", "utterance": {"id": 1, "text": "I'll pay rent", "spoken_at": bad}}
    assert normalize_bee_event("new-utterance", data)["occurred_at"]


def test_l2_bee_todo_edits_amend_and_completion_needs_confirmation():
    todo = {"id": 5, "text": "Renew passport", "completed": False, "alarmAt": 1792575000000}
    first = normalize_bee_event("todo-created", {"todo": todo})
    edited = normalize_bee_event("todo-updated", {"todo": {**todo, "alarmAt": 1792661400000}})
    done = normalize_bee_event("todo-updated", {"todo": {**todo, "completed": True}})
    assert len({first["event_id"], edited["event_id"], done["event_id"]}) == 3
    s = wall()
    for ev in (first, edited):
        e.compile_bee(s, BeeInput(**ev))
    [c] = gen(s)
    assert c["due_at"] == datetime.fromtimestamp(1792661400, timezone.utc).isoformat()
    e.compile_bee(s, BeeInput(**done))
    assert c["status"] == "EVIDENCE_PENDING"


def test_l3_daily_series_keeps_local_wall_time_across_dst():
    s = e.fresh()
    s.update(household_id="h", clock_mode="WALL", now="2026-10-30T12:00:00+00:00", timezone="America/New_York")
    e.compile_bee(s, BeeInput(event_id="d", utterance="I'll walk the dog every day at 7 pm",
                              occurred_at="2026-10-30T12:00:00+00:00", timezone="America/New_York"))
    e.tick(s, "2026-11-02T12:00:00+00:00")
    local_hours = {datetime.fromisoformat(c["due_at"]).astimezone(ZoneInfo("America/New_York")).hour for c in gen(s)}
    assert local_hours == {19}


def test_l5_legitimate_sentence_with_verified_is_not_dropped():
    s = wall()
    say(s, "I'll mark the papers and get them verified by Friday")
    assert gen(s)
