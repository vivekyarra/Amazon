"""Backend-only external adapters. No credentials are ever sent to a browser."""

import asyncio
import json
import os
import time
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


class BeeAdapter:
    base = "https://api.developer.bee.amazon.dev"

    def __init__(self, token=None, transport=None):
        self.token = token or os.getenv("BEE_TOKEN")
        self.client = httpx.AsyncClient(
            base_url=self.base, transport=transport, timeout=httpx.Timeout(60, read=90)
        )
        self.cursor = None
        self.stopped = False

    async def stream_once(self, handle):
        if not self.token:
            raise ApiError(503, "BEE_NOT_CONNECTED", "Bee token is unavailable; live ingestion is blocked.")
        headers = {"Authorization": "Bearer " + self.token, "Accept": "text/event-stream"}
        if self.cursor:
            headers["Last-Event-ID"] = self.cursor
        async with self.client.stream(
            "GET", "/v1/stream?types=new-utterance,new-conversation", headers=headers
        ) as response:
            if response.status_code != 200:
                raise ApiError(
                    503, "BEE_ACCESS_REJECTED", f"Bee stream returned status {response.status_code}."
                )
            data = []
            event_id = None
            async for line in response.aiter_lines():
                if self.stopped:
                    return
                if len("".join(data)) > 65536:
                    raise ApiError(502, "BEE_EVENT_TOO_LARGE", "Bee event exceeded the bounded input size.")
                if line.startswith("id:"):
                    event_id = line[3:].strip()
                elif line.startswith("data:"):
                    data.append(line[5:].lstrip())
                elif not line and data:
                    await handle(json.loads("\n".join(data)), event_id)
                    self.cursor = event_id or self.cursor
                    data = []

    async def run(self, handle):
        delay = 1
        while not self.stopped:
            try:
                await self.stream_once(handle)
                delay = 1
            except (httpx.HTTPError, ApiError, ValueError):
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
