"""Standard Web Push (RFC 8030 + VAPID RFC 8292) delivery of companion alerts.

The household's encrypted ledger stores subscriptions and per-alert delivery results. Lock-screen
text is deliberately generic for incident kinds; details require opening the authenticated app.
"Accepted by the push service" is recorded as such: it never claims the device displayed it.
"""

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .models import ApiError

MAX_SUBSCRIPTIONS = 5
COPY = {
    "SILENT_PREP": ("Coming up", True),
    "ACTIVE_ESCALATION": ("Due soon — not confirmed yet", False),
    "ARRIVAL_ITEM_CHECK": ("Before you go in", False),
    "DELIVERY_MISMATCH": ("Delivery needs review", False),
    "DEPOSIT_OBSERVED": ("Parcel observed on porch", True),
    "PORCH_REMOVAL": ("Porch activity needs your review", False),
    "DAILY_BRIEFING": ("Your day", True),
}
PRIVATE_KINDS = {"DELIVERY_MISMATCH", "PORCH_REMOVAL", "DEPOSIT_OBSERVED"}
# Browser push services only (prevents using the server as a request relay to arbitrary hosts).
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com",
              ".notify.windows.com", ".push.apple.com", "push.services.mozilla.com")


class PushNotifier:
    def __init__(self, data_dir, subject=None):
        self.key_path = Path(data_dir) / "vapid-private.pem"
        if not self.key_path.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            pem = key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            )
            fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(pem)
        self.private = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        self.subject = subject or os.getenv("VAPID_SUBJECT", "mailto:done-irl@users.noreply.github.com")
        self.sent = 0
        self.failed = 0

    def public_key(self):
        raw = self.private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    # ---- ledger helpers (pure; run inside the caller's transaction) ----
    @staticmethod
    def subscribe(s, endpoint, p256dh, auth, now):
        from urllib.parse import urlsplit

        parts = urlsplit(endpoint)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or parts.port not in (None, 443) or parts.username or not any(
            host == h or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS
        ):
            raise ApiError(422, "PUSH_ENDPOINT_INVALID", "Use the push endpoint issued by the browser's push service.")
        try:
            point = base64.urlsafe_b64decode(p256dh + "=" * (-len(p256dh) % 4))
            secret = base64.urlsafe_b64decode(auth + "=" * (-len(auth) % 4))
            ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
        except (ValueError, TypeError):
            raise ApiError(422, "PUSH_KEYS_INVALID", "Subscription keys are not a valid P-256 key/auth pair.")
        if len(point) != 65 or len(secret) != 16:
            raise ApiError(422, "PUSH_KEYS_INVALID", "Subscription keys are not a valid P-256 key/auth pair.")
        subs = s.setdefault("push_subscriptions", [])
        subs[:] = [x for x in subs if x["endpoint"] != endpoint]
        if len(subs) >= MAX_SUBSCRIPTIONS:
            subs.pop(0)
        subs.append(dict(endpoint=endpoint, keys=dict(p256dh=p256dh, auth=auth), created_at=now,
                         alert_cursor=len(s.get("alerts", []))))
        return {"subscriptions": len(subs)}

    @staticmethod
    def unsubscribe(s, endpoint):
        subs = s.setdefault("push_subscriptions", [])
        subs[:] = [x for x in subs if x["endpoint"] != endpoint]
        return {"subscriptions": len(subs)}

    @staticmethod
    def message(alert, title=None):
        heading, silent = COPY.get(alert["kind"], ("DONE/IRL update", False))
        if alert["kind"] == "DAILY_BRIEFING":
            body = alert["message"][:240]
        else:
            body = "Open DONE/IRL to review." if alert["kind"] in PRIVATE_KINDS or not title else title
        return {"title": "DONE/IRL · " + heading, "body": body, "silent": silent,
                "url": alert.get("action") or "/", "tag": alert["alert_id"]}

    def pending(self, s):
        """(subscription, alert, payload) triples not yet attempted, oldest first."""
        out = []
        titles = {c["contract_id"]: c["title"] for c in s.get("contracts", [])}
        titles[None] = None
        alerts = s.get("alerts", [])
        for sub in s.get("push_subscriptions", []):
            for alert in alerts[sub.get("alert_cursor", 0):]:
                if sub["endpoint"] in alert.get("push_attempts", {}):
                    continue
                out.append((sub, alert, self.message(alert, titles.get(alert["contract_id"]))))
        return out

    def send(self, sub, payload):
        from py_vapid import Vapid
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                data=json.dumps(payload),
                vapid_private_key=Vapid.from_pem(self.key_path.read_bytes()),
                vapid_claims={"sub": self.subject},
                ttl=3600,
                timeout=10,
            )
            self.sent += 1
            return "ACCEPTED_BY_PUSH_SERVICE"
        except WebPushException as error:
            self.failed += 1
            code = getattr(error.response, "status_code", None)
            return "SUBSCRIPTION_GONE" if code in {404, 410} else f"FAILED_{code or 'NETWORK'}"
        except Exception as error:  # noqa: BLE001 - one bad subscription must not stall delivery
            self.failed += 1
            return "FAILED_" + type(error).__name__

    def deliver(self, store):
        """Attempt every pending alert for every household once; record results durably."""
        with store.lock:
            households = [r["id"] for r in store.db.execute("SELECT id FROM households").fetchall()]
        for household in households:
            s = store.read(household)
            if not s or not s.get("push_subscriptions") or not s.get("consent", False):
                continue
            work = self.pending(s)
            if not work:
                continue
            results = [(sub["endpoint"], alert["alert_id"], self.send(sub, payload)) for sub, alert, payload in work]
            with store.transaction() as db:
                s = store.read(household)
                by_id = {a["alert_id"]: a for a in s.get("alerts", [])}
                gone = set()
                for endpoint, alert_id, status in results:
                    if alert_id in by_id:
                        by_id[alert_id].setdefault("push_attempts", {})[endpoint] = status
                        if status == "ACCEPTED_BY_PUSH_SERVICE":
                            by_id[alert_id]["delivery_status"] = "ACCEPTED_BY_PUSH_SERVICE"
                    if status == "SUBSCRIPTION_GONE":
                        gone.add(endpoint)
                if gone:
                    s["push_subscriptions"] = [x for x in s["push_subscriptions"] if x["endpoint"] not in gone]
                store.save(db, household, s)
