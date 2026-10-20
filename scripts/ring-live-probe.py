"""Probe the Ring Partner API with a short-lived token and record a REDACTED proof report.

Usage (token from the Ring Developer Playground, valid ~30 minutes):
  RING_ACCESS_TOKEN=... uv run --extra ring-video python scripts/ring-live-probe.py [--seconds 8]

Steps: GET /v1/devices → capabilities → event history → one receive-only WHEP session that decodes
real video frames for a few seconds → DELETE the session. The report stores counts, codec/size,
hashed device ids and frame digests only. No images, addresses, names or tokens are written.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "mcp-orchestrator"))
from done_irl.adapters import RingAdapter  # noqa: E402
from done_irl.models import ApiError  # noqa: E402


def anon(value):
    return "dev_" + hashlib.sha256(str(value).encode()).hexdigest()[:10]


def keys(obj, prefix=""):
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            out += keys(v, f"{prefix}.{k}" if prefix else k)
        return out or [prefix]
    if isinstance(obj, list):
        return keys(obj[0], prefix + "[]") if obj else [prefix + "[]"]
    return [prefix]


async def whep_probe(adapter, device, seconds, battery):
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

    stun = os.getenv("RING_STUN_URL", "stun:stun.l.google.com:19302")
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[RTCIceServer(urls=stun)]))
    result = {"frames_decoded": 0, "distinct_frame_digests": 0}
    digests = set()
    done = asyncio.Event()

    @pc.on("track")
    def on_track(track):
        async def consume():
            start = time.monotonic()
            while time.monotonic() - start < seconds:
                try:
                    frame = await asyncio.wait_for(track.recv(), timeout=5)
                except Exception as error:  # noqa: BLE001 - recorded, not hidden
                    result["track_error"] = type(error).__name__
                    break
                image = frame.to_ndarray(format="bgr24")
                result["frames_decoded"] += 1
                result["resolution"] = f"{image.shape[1]}x{image.shape[0]}"
                digests.add(hashlib.sha256(image[::8, ::8].tobytes()).hexdigest()[:16])
            done.set()

        if track.kind == "video":
            asyncio.ensure_future(consume())

    pc.addTransceiver("video", direction="recvonly")
    await pc.setLocalDescription(await pc.createOffer())
    started = time.monotonic()
    session = await adapter.whep(device, pc.localDescription.sdp, battery=battery)
    result["whep_status"] = "201_ANSWER_RECEIVED"
    result["session_budget_seconds"] = session["max_seconds"]
    answer = session["answer"]
    result["negotiated_codecs"] = sorted({line.split()[1].split("/")[0] for line in answer.splitlines()
                                          if line.startswith("a=rtpmap:")})
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type="answer"))
    try:
        await asyncio.wait_for(done.wait(), timeout=seconds + 15)
    except asyncio.TimeoutError:
        result["track_error"] = result.get("track_error", "NO_FRAMES_BEFORE_TIMEOUT")
    result["seconds_open"] = round(time.monotonic() - started, 1)
    result["distinct_frame_digests"] = len(digests)
    try:
        await adapter.close(session["location"])
        result["session_closed"] = True
    except ApiError as error:
        result["session_closed"] = error.code
    await pc.close()
    return result


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=8)
    ap.add_argument("--device", help="device id to stream (default: first device advertising video)")
    ap.add_argument("--out", default="docs/evidence/ring-live-probe.json")
    args = ap.parse_args()
    report = {"probe": "ring-live-probe/1", "started_at": datetime.now(timezone.utc).isoformat(),
              "base_url": RingAdapter.base, "token_present": bool(os.getenv("RING_ACCESS_TOKEN")),
              "redaction": "Device ids hashed; no images, names, addresses or tokens stored."}
    adapter = RingAdapter()
    try:
        devices = await adapter.devices()
        items = devices.get("data", devices if isinstance(devices, list) else [])
        report["devices"] = {"count": len(items), "shape": sorted(set(keys(items[0])))[:40] if items else []}
        chosen = None
        report["capabilities"] = []
        for item in items:
            device_id = item.get("id") if isinstance(item, dict) else item
            caps = await adapter.capabilities(device_id)
            attrs = caps.get("data", {}).get("attributes", {})
            entry = {"device": anon(device_id), "video": bool(attrs.get("video")),
                     "attribute_keys": sorted(attrs)[:30]}
            report["capabilities"].append(entry)
            if (args.device and device_id == args.device) or (not args.device and not chosen and entry["video"]):
                chosen = device_id
        if chosen:
            history = await adapter.history(chosen)
            events = history.get("data", [])
            report["history"] = {"device": anon(chosen), "events": len(events),
                                 "types": sorted({str(e.get("type") or e.get("attributes", {}).get("event_type"))
                                                  for e in events})[:20]}
            report["whep"] = await whep_probe(adapter, chosen, args.seconds, battery=True)
        report["verdict"] = (
            "LIVE_VERIFIED_RING_VIDEO" if report.get("whep", {}).get("frames_decoded", 0) > 0
            else "LIVE_API_REACHABLE_NO_VIDEO" if items else "LIVE_API_REACHABLE_NO_DEVICES"
        )
    except ApiError as error:
        report["verdict"] = "BLOCKED_" + error.code
    finally:
        await adapter.client.aclose()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["verdict"])


if __name__ == "__main__":
    asyncio.run(main())
