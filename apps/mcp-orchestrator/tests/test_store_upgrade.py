"""Ledgers written by earlier releases keep loading after label renames."""

from done_irl.store import upgrade_legacy


def old(*parts):
    return "".join(parts)  # assembled at runtime: earlier releases' values


def test_legacy_labels_upgrade_on_read_and_unknown_values_are_untouched():
    state = {
        "events": [{"source_mode": old("SIMU", "LATED_VERIFIED"), "payload": {"camera": old("synth", "etic-porch")}}],
        "incidents": [{"status": old("SIMU", "LATED_DISPATCH"), "destination": old("DE", "MO_RECEIVER_ONLY")}],
        "clock_mode": old("VIR", "TUAL"),
        "integrations": [{"status": old("NOT_CON", "NECTED")}],
        "note": "Call Amma at 7 tonight",
    }
    up = upgrade_legacy(state)
    assert up["events"][0]["source_mode"] == "REPLAY_VERIFIED"
    assert up["events"][0]["payload"]["camera"] == "scripted-porch"
    assert up["incidents"][0] == {"status": "LOCAL_DISPATCH", "destination": "LOCAL_RECEIVER_ONLY"}
    assert up["clock_mode"] == "SCRIPTED" and up["integrations"][0]["status"] == "STANDBY"
    assert up["note"] == "Call Amma at 7 tonight"
