"""Ring v1.1 webhook verification per developer.amazon.com/ring/notifications.

The signature authenticates the raw bytes. Account and device bindings are server-side
configuration; a browser cannot select another household or claim a live source.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

from .models import ApiError


def verify_ring(body, signature, key, bindings_file, now=None):
    expected = "sha256=" + hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ApiError(401, "BAD_SIGNATURE", "Webhook signature is invalid.")
    if not bindings_file:
        raise ApiError(503, "RING_ACCOUNT_NOT_LINKED", "A server-side Ring account binding is required.")
    try:
        bindings = json.loads(Path(bindings_file).read_text())
        payload = json.loads(body)
        meta, event = payload["meta"], payload["data"]
        account, event_id = meta["account_id"], meta["request_id"]
        timestamp = datetime.fromisoformat(meta["time"].replace("Z", "+00:00"))
        if (
            not timestamp.tzinfo
            or timestamp.timestamp() > (now or datetime.now(timezone.utc).timestamp()) + 300
        ):
            raise ValueError
        # Ring retries can be delayed. Dedupe receipts instead of rejecting legitimate retries after five minutes.
        if meta["version"] != "1.1" or not isinstance(event_id, str) or not 1 <= len(event_id) <= 200:
            raise ValueError
        binding = bindings.get(account)
        if not binding or event["attributes"]["source"] not in binding["devices"]:
            raise ApiError(403, "RING_DEVICE_NOT_LINKED", "This account/device is not linked to a household.")
        if not isinstance(event["id"], str) or not 1 <= len(event["id"]) <= 500:
            raise ValueError
        allowed = {
            "motion_detected",
            "button_press",
            "device_added",
            "device_removed",
            "device_online",
            "device_offline",
        }
        if event["type"] not in allowed:
            raise ApiError(422, "RING_EVENT_UNSUPPORTED", "This Ring notification has no registered reducer.")
        if not isinstance(event["attributes"]["timestamp"], (int, float)):
            raise ValueError
        household = binding["household"]
        if not isinstance(household, str) or not household.startswith("house_"):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        raise ApiError(422, "INVALID_RING_EVENT", "Ring event or server binding is invalid.") from None
    return household, event_id, payload
