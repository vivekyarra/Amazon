#!/usr/bin/env python3
"""External MCP client proof for Muni.

Starts the real FastAPI/uvicorn server on a free localhost port (isolated temporary DATA_DIR,
random demo-admin password that is never printed), then drives it over real HTTP with the
official ``mcp`` Python SDK client (Streamable HTTP transport):

    initialize -> tools/list -> a realistic simulated Alexa+ flow calling every tool

Every JSON-RPC request/response on the wire is captured and written, with credentials
redacted, to docs/evidence/mcp-external-client.json. Judge-replay steps that the MCP surface
intentionally does not expose (camera fixture scenarios) are performed through the
authenticated REST API and are labeled as such in the transcript.

Optionally (``--inspector``) also runs the official MCP Inspector CLI
(``npx @modelcontextprotocol/inspector --cli``) against the same server and records the
outcome honestly in docs/evidence/mcp-inspector-cli.json.

Usage:  uv run --extra ring-video --extra aws python scripts/mcp-external-client.py [--inspector]
"""

import argparse
import asyncio
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"
SECRET_KEYS = {"authorization", "cookie", "set-cookie", "password", "token", "done_session"}


def redact(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k.lower() in SECRET_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def parse(raw: bytes):
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return raw.decode("utf-8", "replace")[:500]


class Transcript:
    def __init__(self):
        self.entries = []
        self.step = "startup"

    async def on_request(self, request: httpx.Request):
        request.extensions["t0"] = time.perf_counter()

    async def on_response(self, response: httpx.Response):
        await response.aread()
        request = response.request
        if not request.url.path.startswith("/mcp"):
            return
        body = parse(request.content)
        method = body.get("method", "") if isinstance(body, dict) else ""
        self.entries.append(
            {
                "step": "initialize (notification)" if method.startswith("notifications/") else self.step,
                "http": {
                    "method": request.method,
                    "path": request.url.path,
                    "request_headers": {
                        k: v
                        for k, v in request.headers.items()
                        if k.lower() in {"accept", "content-type", "mcp-protocol-version", "origin"}
                    },
                    "authorization": "Bearer [REDACTED]" if "authorization" in request.headers else None,
                    "status": response.status_code,
                    "response_headers": {
                        k: v
                        for k, v in response.headers.items()
                        if k.lower() in {"content-type", "allow", "www-authenticate", "mcp-session-id"}
                    },
                    "elapsed_ms": round((time.perf_counter() - request.extensions.get("t0", 0)) * 1000, 1),
                },
                "jsonrpc_request": redact(parse(request.content)),
                "jsonrpc_response": redact(parse(response.content)),
            }
        )


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def structured(result):
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def run(base: str, password: str, transcript: Transcript, summary: list):
    hooks = {"request": [transcript.on_request], "response": [transcript.on_response]}
    async with httpx.AsyncClient(base_url=base, timeout=20, event_hooks=hooks) as http:
        login = await http.post("/api/auth/login", json={"username": "demo-admin", "password": password})
        login.raise_for_status()
        token = http.cookies.get("done_session")
        http.cookies.clear()  # MCP calls authenticate with the bearer header only
        http.headers["Authorization"] = "Bearer " + token

        async def rest(path, body=None):
            r = await http.post("/api" + path, json=body or {}, headers={"Idempotency-Key": uuid.uuid4().hex})
            r.raise_for_status()
            summary.append({"step": transcript.step, "rest": path, "status": r.status_code})
            return r.json()

        # Negative edge checks with a raw HTTP client (no credentials) before the SDK session.
        transcript.step = "negative: unauthenticated tools/list is rejected (401)"
        async with httpx.AsyncClient(base_url=base, timeout=10, event_hooks=hooks) as anon:
            await anon.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 0, "method": "tools/list"},
                headers={"Accept": "application/json, text/event-stream"},
            )
        transcript.step = "negative: GET has no standalone SSE stream (405)"
        await http.get("/mcp/", headers={"Accept": "text/event-stream"})

        async with streamable_http_client(base + "/mcp/", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                transcript.step = "initialize"
                init = await session.initialize()
                summary.append(
                    {
                        "step": "initialize",
                        "protocolVersion": init.protocolVersion,
                        "server": init.serverInfo.name,
                    }
                )

                transcript.step = "tools/list"
                tools = sorted(t.name for t in (await session.list_tools()).tools)
                summary.append({"step": "tools/list", "tools": tools})

                async def call(step, name, args=None):
                    transcript.step = step
                    result = await session.call_tool(name, args or {})
                    data = {"_error": result.content[0].text} if result.isError else structured(result)
                    summary.append({"step": step, "tool": name, "isError": result.isError})
                    return data

                morning = [
                    "I'll bring cold drinks home tonight.",
                    "I'll call my sister before 6 PM.",
                    "I'll cover the teacher meeting at 4 PM.",
                    "I'll do 15 squats before watching TV.",
                ]
                for i, utterance in enumerate(morning):
                    await call(
                        f'"Alexa, remember: {utterance}" (owner text via MCP, not Bee capture)',
                        "compile_ambient_commitment",
                        {
                            "utterance_json": {
                                "event_id": f"alexa-sim-morning-{i}",
                                "utterance": utterance,
                                "occurred_at": "2026-10-20T08:15:00+05:30",
                            },
                            "speaker_context": {"speaker": "SELF"},
                        },
                    )
                listed = await call('"Alexa, what did I promise today?"', "list_active_contracts")
                by_key = {c["key"]: c["contract_id"] for c in listed["contracts"]}

                transcript.step = "judge replay (REST): 2:10 PM verified deposit"
                await rest("/admin/scenarios/2/run", {"branch": "deposit"})
                listed = await call("refresh contracts after deposit", "list_active_contracts")
                by_key = {c["key"]: c["contract_id"] for c in listed["contracts"]}
                await call(
                    '"Alexa, keep an eye on the parcel"',
                    "spawn_watchdog_subagent",
                    {
                        "contract_id": by_key["parcel"],
                        "camera_device_id": "synthetic-porch",
                        "target_roi": [0.2, 0.55, 0.45, 0.95],
                        "invariant_type": "PARCEL_PRESENT",
                    },
                )
                await call(
                    '"Alexa, is my parcel safe?"', "get_watchdog_status", {"contract_id": by_key["parcel"]}
                )
                await call(
                    '"Alexa, is my parcel safe?" (custody detail)',
                    "get_contract_state",
                    {"contract_id": by_key["parcel"]},
                )

                transcript.step = "judge replay (REST): 3:00/3:35 PM escalation, user not engaged"
                await rest("/admin/scenarios/3/run", {"branch": "disengaged"})
                await call(
                    "evaluate teacher-meeting escalation at the server clock",
                    "evaluate_deadline_escalation",
                    {
                        "contract_id": by_key["teacher"],
                        "current_time": "2026-10-20T15:35:00+05:30",
                        "user_activity_state": "CODING",
                    },
                )
                await call(
                    '"Alexa, did I call my sister?"', "get_contract_state", {"contract_id": by_key["sister"]}
                )
                await call(
                    '"Alexa, did I call my sister?" (how to verify)',
                    "request_user_verification",
                    {"contract_id": by_key["sister"]},
                )

                transcript.step = "judge replay (REST): 4:30 PM package removal"
                await rest("/admin/scenarios/4/run", {"branch": "unknown"})
                state = (await http.get("/api/state")).json()["state"]
                incident = state["incidents"][0]["incident_id"]
                await call(
                    '"Alexa, what happened to my package?"', "get_incident_packet", {"incident_id": incident}
                )
                await call(
                    '"Alexa, report it to the police" (model boolean only -> must be denied)',
                    "dispatch_police_evidence_dossier",
                    {"incident_id": incident, "human_confirmed_boolean": True},
                )
                await call(
                    '"Alexa, start Reality-Lock"',
                    "bridge_ring_camera_to_firetv",
                    {
                        "camera_device_id": "synthetic-porch",
                        "firetv_session_id": "none",
                        "verification_mode": "POSE_SQUATS",
                    },
                )
                await call('"Alexa, are my devices connected?"', "get_integration_health")

        state = (await http.get("/api/state")).json()["state"]
        return {
            "contracts": {c["key"]: c["status"] for c in state["contracts"]},
            "incident_status": state["incidents"][0]["status"] if state["incidents"] else None,
            "incident_receipt": state["incidents"][0]["receipt"] if state["incidents"] else None,
            "mcp_dispatch_denied_events": sum(
                e["event_type"] == "incident.mcp_dispatch_denied" for e in state["events"]
            ),
            "alerts": [{"kind": a["kind"], "message": a["message"]} for a in state["alerts"]],
        }, token


def run_inspector(base: str, token: str):
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    record = {
        "tool": "@modelcontextprotocol/inspector --cli",
        "command": f"npx -y @modelcontextprotocol/inspector --cli {base}/mcp/ --transport http "
        "--method tools/list --header 'Authorization: Bearer [REDACTED]'",
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }
    if not npx:
        return {**record, "outcome": "NOT_RUN", "reason": "npx not found on PATH"}
    try:
        proc = subprocess.run(
            [
                npx,
                "-y",
                "@modelcontextprotocol/inspector",
                "--cli",
                base + "/mcp/",
                "--transport",
                "http",
                "--method",
                "tools/list",
                "--header",
                "Authorization: Bearer " + token,
            ],
            capture_output=True,
            text=True,
            timeout=240,
            cwd=tempfile.gettempdir(),
        )
    except subprocess.TimeoutExpired:
        return {**record, "outcome": "TIMEOUT"}
    out = (proc.stdout or "").replace(token, "[REDACTED]")
    err = (proc.stderr or "").replace(token, "[REDACTED]")
    try:
        names = sorted(t["name"] for t in json.loads(out)["tools"])
    except (ValueError, KeyError, TypeError):
        names = None
    return {
        **record,
        "exit_code": proc.returncode,
        "outcome": "PASS" if proc.returncode == 0 and names else "FAIL",
        "tools": names,
        "stdout_head": out[:1500] if not names else None,
        "stderr_tail": err[-1500:],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspector", action="store_true", help="also try the MCP Inspector CLI")
    parser.add_argument("--out", default=str(EVIDENCE / "mcp-external-client.json"))
    args = parser.parse_args()
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    password = secrets.token_urlsafe(24)
    data_dir = tempfile.mkdtemp(prefix="done-irl-mcp-")
    env = {
        **os.environ,
        "DATA_DIR": data_dir,
        "DEMO_MODE": "true",
        "DEMO_ADMIN_PASSWORD": password,
        "PYTHONPATH": str(ROOT / "apps" / "mcp-orchestrator"),
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "done_irl.api:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    transcript, summary = Transcript(), []
    try:
        for _ in range(200):
            try:
                if httpx.get(base + "/health/ready", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        final, token = asyncio.run(run(base, password, transcript, summary))
        inspector = run_inspector(base, token) if args.inspector else None
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(data_dir, ignore_errors=True)

    import mcp

    doc = {
        "title": "Muni MCP external-client transcript (simulated Alexa+ flow)",
        "honesty": "Official MCP Python SDK client over real localhost HTTP against the real server. "
        "This is NOT an Alexa device or Alexa+ account connection. Utterances are typed owner text "
        "labeled MCP_OWNER_INPUT, not Bee captures. Camera stages are synthetic judge-replay fixtures "
        "triggered through authenticated REST, labeled per step.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "client": {
            "sdk": "mcp (python)",
            "version": getattr(mcp, "__version__", None) or _sdk_version(),
            "python": platform.python_version(),
            "transport": "streamable-http",
        },
        "server": {"url": base + "/mcp/", "mode": "DEMO_MODE=true, isolated temporary ledger"},
        "redaction": "Authorization headers, cookies, tokens and passwords are replaced with [REDACTED].",
        "summary": summary,
        "final_ledger": final,
        "jsonrpc_transcript": transcript.entries,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=2, ensure_ascii=False)
    assert token not in text and password not in text, "secret leaked into transcript"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(transcript.entries)} HTTP exchanges)")
    if inspector is not None:
        ipath = EVIDENCE / "mcp-inspector-cli.json"
        ipath.write_text(json.dumps(inspector, indent=2) + "\n", encoding="utf-8")
        print(f"inspector: {inspector['outcome']} -> {ipath.relative_to(ROOT)}")


def _sdk_version():
    from importlib.metadata import version

    return version("mcp")


if __name__ == "__main__":
    main()
