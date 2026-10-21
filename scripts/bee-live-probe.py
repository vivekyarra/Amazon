"""Probe the live Bee developer API with BEE_TOKEN and record a REDACTED structural report.

Usage: BEE_TOKEN=... uv run python scripts/bee-live-probe.py [--seconds 120] [--out docs/evidence/bee-live-probe.json]

The report keeps only HTTP statuses, event types, JSON key paths, value types, counts and whether
Muni's normalizer accepted each event. It never writes transcript text, todo text, names,
locations or the token. Run it while speaking a few promises near the Bee device to exercise the stream.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "mcp-orchestrator"))
from done_irl.adapters import BeeAdapter, normalize_bee_event  # noqa: E402

BASE = BeeAdapter.base


def shape(value, prefix=""):
    """Key paths and JSON types only — no values."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out.update(shape(v, f"{prefix}.{k}" if prefix else k))
        return out or {prefix: "object"}
    if isinstance(value, list):
        return {prefix + "[]": f"list(len={len(value)})", **(shape(value[0], prefix + "[0]") if value else {})}
    return {prefix: type(value).__name__}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=120)
    ap.add_argument("--out", default="docs/evidence/bee-live-probe.json")
    args = ap.parse_args()
    token = os.environ.get("BEE_TOKEN")
    report = {
        "probe": "bee-live-probe/1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "token_present": bool(token),
        "token_sha256_prefix": hashlib.sha256(token.encode()).hexdigest()[:8] if token else None,
        "endpoints": {},
        "stream": {"events": [], "normalized_accepted": 0, "ignored": 0},
        "redaction": "Only statuses, key paths, types and counts are recorded. No text values.",
    }
    if not token:
        report["verdict"] = "BLOCKED_NO_TOKEN"
    else:
        headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
            for path in ["/v1/me", "/v1/todos", "/v1/conversations", "/v1/facts"]:
                try:
                    r = await client.get(path, headers=headers)
                    entry = {"status": r.status_code}
                    if r.status_code == 200:
                        body = r.json()
                        entry["shape"] = dict(list(shape(body).items())[:60])
                        if path == "/v1/todos":
                            items = body.get("todos", body.get("data", body)) if isinstance(body, dict) else body
                            normalized = [
                                normalize_bee_event("todo-created", {"todo": t}) for t in (items or [])
                            ] if isinstance(items, list) else []
                            entry["todos_total"] = len(items) if isinstance(items, list) else None
                            entry["todos_normalized_open"] = sum(1 for n in normalized if n)
                    report["endpoints"][path] = entry
                except httpx.HTTPError as error:
                    report["endpoints"][path] = {"error": type(error).__name__}
            stream_headers = {**headers, "Accept": "text/event-stream"}
            try:
                async with client.stream(
                    "GET", "/v1/stream?types=" + BeeAdapter.types, headers=stream_headers,
                    timeout=httpx.Timeout(30, read=args.seconds + 10),
                ) as r:
                    report["stream"]["status"] = r.status_code
                    if r.status_code == 200:
                        event_type, data = "message", []
                        deadline = asyncio.get_event_loop().time() + args.seconds
                        async for line in r.aiter_lines():
                            if asyncio.get_event_loop().time() > deadline:
                                break
                            if line.startswith(":"):
                                report["stream"]["heartbeats"] = report["stream"].get("heartbeats", 0) + 1
                            elif line.startswith("event:"):
                                event_type = line[6:].strip()
                            elif line.startswith("data:"):
                                data.append(line[5:].lstrip())
                            elif not line and data:
                                try:
                                    payload = json.loads("\n".join(data))
                                except ValueError:
                                    payload = None
                                ok = bool(payload is not None and normalize_bee_event(event_type, payload))
                                report["stream"]["events"].append(
                                    {"type": event_type, "shape": shape(payload) if payload is not None else None,
                                     "normalized": ok}
                                )
                                report["stream"]["normalized_accepted" if ok else "ignored"] += 1
                                event_type, data = "message", []
            except httpx.ReadTimeout:
                report["stream"]["ended"] = "read-timeout"
            except httpx.HTTPError as error:
                report["stream"]["error"] = type(error).__name__
        ok_api = report["endpoints"].get("/v1/me", {}).get("status") == 200
        report["verdict"] = (
            "LIVE_VERIFIED_STREAM_EVENTS" if report["stream"]["normalized_accepted"]
            else "LIVE_API_REACHABLE_NO_STREAM_EVENTS" if ok_api else "BLOCKED_API_REJECTED"
        )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["verdict"], json.dumps({k: v.get("status") for k, v in report["endpoints"].items()}))


if __name__ == "__main__":
    asyncio.run(main())
