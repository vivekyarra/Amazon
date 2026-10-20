"""Backend-only external adapters. No credentials are ever sent to a browser."""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
import httpx
from .models import ApiError


class RingAdapter:
    base = "https://api.amazonvision.com"

    def __init__(self, token=None, transport=None):
        self.token = token or os.getenv("RING_ACCESS_TOKEN")
        self.client = httpx.AsyncClient(base_url=self.base, transport=transport, timeout=20)
        self.sessions = {}

    async def request(self, method, path, **kwargs):
        if not self.token:
            raise ApiError(
                503,
                "RING_NOT_CONNECTED",
                "Ring is not connected. Synthetic replay remains separately available.",
            )
        response = await self.client.request(
            method,
            path,
            headers={"Authorization": "Bearer " + self.token, **kwargs.pop("headers", {})},
            **kwargs,
        )
        if response.status_code in (401, 403):
            raise ApiError(
                503,
                "RING_ACCESS_REJECTED",
                "Ring access is expired or unauthorized; no silent source switch.",
            )
        if response.status_code >= 400:
            raise ApiError(503, "RING_UNAVAILABLE", f"Ring returned status {response.status_code}.")
        return response

    async def devices(self):
        return (await self.request("GET", "/v1/devices")).json()

    async def capabilities(self, device):
        return (await self.request("GET", f"/v1/devices/{quote(device, safe='')}/capabilities")).json()

    async def history(self, device):
        return (await self.request("GET", f"/v1/history/devices/{quote(device, safe='')}/events")).json()

    async def whep(self, device, sdp, battery=True):
        response = await self.request(
            "POST",
            f"/v1/devices/{quote(device, safe='')}/media/streaming/whep/sessions",
            content=sdp,
            headers={"Content-Type": "application/sdp"},
        )
        location = response.headers.get("location", "")
        parsed = urlsplit(location)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.amazonvision.com"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or parsed.fragment
        ):
            raise ApiError(502, "UNTRUSTED_SESSION_URL", "Ring returned an untrusted session URL.")
        self.sessions[location] = time.monotonic() + (30 if battery else 60)
        return dict(answer=response.text, location=location, max_seconds=30 if battery else 60)

    async def close(self, location):
        if location not in self.sessions:
            raise ApiError(404, "NO_SESSION", "Session is not owned by this backend.")
        try:
            await self.request("DELETE", location)
        finally:
            self.sessions.pop(location, None)

    async def cleanup(self):
        for location, expiry in list(self.sessions.items()):
            if expiry <= time.monotonic():
                await self.close(location)


def _epoch(value):
    """Bee timestamps are epoch numbers (seconds or milliseconds, per bee-cli normalizeEpochMs)."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    seconds = value / 1000 if value > 10_000_000_000 else value
    return datetime.fromtimestamp(seconds, timezone.utc)


def normalize_bee_event(event_type, data, received_at=None, self_speakers=None, tz="Asia/Kolkata"):
    """Map a documented Bee SSE event onto the typed BeeInput envelope, or return None.

    Shapes follow the official bee-cli stream formatter (github.com/bee-computer/bee-cli,
    sources/commands/stream/index.ts): ``new-utterance`` → {utterance:{id,text,speaker,spoken_at,start},
    conversation_uuid}; ``todo-created`` → {todo:{id,text,completed,alarmAt}}. Any other or incomplete
    shape is ignored rather than guessed. Speaker labels count as the wearer only when configured.
    """
    received_at = received_at or datetime.now(timezone.utc)
    selves = {x.strip().lower() for x in (self_speakers or os.getenv("BEE_SELF_SPEAKERS", "")).split(",") if x.strip()}
    if not isinstance(data, dict):
        return None
    if event_type == "new-utterance":
        u = data.get("utterance")
        if not isinstance(u, dict) or not isinstance(u.get("text"), str) or not u["text"].strip():
            return None
        uid = u.get("id")
        conv = data.get("conversation_uuid") or ""
        if uid is None:
            return None
        speaker = str(u.get("speaker") or "")
        occurred = _epoch(u.get("spoken_at")) or _epoch(u.get("start")) or received_at
        return dict(
            event_id=f"bee:utt:{conv}:{uid}"[:120],
            utterance=u["text"].strip()[:4000],
            speaker="SELF" if speaker.lower() in selves else "UNKNOWN",
            counterparty="Household",
            occurred_at=occurred.isoformat(),
            timezone=tz,
        )
    if event_type in {"todo-created", "todo-updated"}:
        t = data.get("todo")
        if not isinstance(t, dict) or t.get("id") is None or not isinstance(t.get("text"), str):
            return None
        if t.get("completed"):
            return None
        due = _epoch(t.get("alarmAt") or t.get("alarm_at"))
        return dict(
            event_id=f"bee:todo:{t['id']}"[:120],
            utterance=t["text"].strip()[:4000],
            speaker="SELF",
            counterparty="Self",
            occurred_at=received_at.isoformat(),
            timezone=tz,
            source_kind="BEE_TODO",
            due_at=due.isoformat() if due else None,
        )
    return None


class BeeAdapter:
    base = "https://api.developer.bee.amazon.dev"
    types = "new-utterance,todo-created,todo-updated,new-conversation,update-conversation"

    def __init__(self, token=None, transport=None):
        self.token = token or os.getenv("BEE_TOKEN")
        self.client = httpx.AsyncClient(
            base_url=self.base, transport=transport, timeout=httpx.Timeout(60, read=90)
        )
        self.cursor = None
        self.stopped = False
        self.last_connected_at = None
        self.last_event_at = None
        self.last_error = None
        self.ignored = 0

    def _headers(self, accept="application/json"):
        if not self.token:
            raise ApiError(503, "BEE_NOT_CONNECTED", "Bee token is unavailable; live ingestion is blocked.")
        return {"Authorization": "Bearer " + self.token, "Accept": accept}

    async def backfill_todos(self, handle):
        """Open Bee todos are commitments the wearer already captured; replay them idempotently."""
        response = await self.client.get("/v1/todos", headers=self._headers())
        if response.status_code != 200:
            raise ApiError(503, "BEE_ACCESS_REJECTED", f"Bee todos returned status {response.status_code}.")
        body = response.json()
        items = body.get("todos", body.get("data", body)) if isinstance(body, dict) else body
        for todo in items if isinstance(items, list) else []:
            normalized = normalize_bee_event("todo-created", {"todo": todo})
            if normalized:
                await handle(normalized, normalized["event_id"])

    async def stream_once(self, handle):
        headers = self._headers("text/event-stream")
        if self.cursor:
            headers["Last-Event-ID"] = self.cursor
        async with self.client.stream("GET", "/v1/stream?types=" + self.types, headers=headers) as response:
            if response.status_code != 200:
                raise ApiError(
                    503, "BEE_ACCESS_REJECTED", f"Bee stream returned status {response.status_code}."
                )
            self.last_connected_at = datetime.now(timezone.utc).isoformat()
            data = []
            event_id = None
            event_type = "message"
            async for line in response.aiter_lines():
                if self.stopped:
                    return
                if len("".join(data)) > 65536:
                    raise ApiError(502, "BEE_EVENT_TOO_LARGE", "Bee event exceeded the bounded input size.")
                if line.startswith(":"):
                    continue
                if line.startswith("id:"):
                    event_id = line[3:].strip()
                elif line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].lstrip())
                elif not line and data:
                    payload = json.loads("\n".join(data))
                    normalized = normalize_bee_event(event_type, payload)
                    if normalized:
                        await handle(normalized, normalized["event_id"])
                    else:
                        self.ignored += 1
                    self.last_event_at = datetime.now(timezone.utc).isoformat()
                    self.cursor = event_id or self.cursor
                    data, event_id, event_type = [], None, "message"

    async def run(self, handle):
        delay = 1
        try:
            await self.backfill_todos(handle)
        except (httpx.HTTPError, ApiError, ValueError) as error:
            self.last_error = type(error).__name__
        while not self.stopped:
            try:
                await self.stream_once(handle)
                delay = 1
                await asyncio.sleep(delay)  # Bound normal EOF reconnects as well as failure retries.
            except (httpx.HTTPError, ApiError, ValueError) as error:
                self.last_error = getattr(error, "code", type(error).__name__)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)


class NotificationAdapter:
    def __init__(self, provider):
        self.provider = provider

    def capabilities(self):
        return {"available": self.provider == "companion", "native_device_delivery": False}

    def send(self, message):
        return {
            "status": "STORED_FOR_AUTHENTICATED_COMPANION" if self.provider == "companion" else "UNAVAILABLE",
            "provider": self.provider,
            "device_delivery_verified": False,
        }
