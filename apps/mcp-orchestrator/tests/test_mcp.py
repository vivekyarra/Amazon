"""Real external SDK client over TCP, not an in-process JSON route test."""

import asyncio
import os
import socket
import subprocess
import sys
from pathlib import Path
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.mark.asyncio
async def test_mcp_streamable_http_handshake_discovery_and_shared_state(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    environment = {
        **os.environ,
        "DATA_DIR": str(tmp_path),
        "JUDGE_PASSWORD": "external-client-password",
        "GUIDED_MODE": "true",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "done_irl.api:app", "--host", "127.0.0.1", "--port", str(port)],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(base_url=base, timeout=10) as http:
            for _ in range(100):
                try:
                    if (await http.get("/health/ready")).status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)
            login = await http.post(
                "/api/auth/login", json={"username": "judge", "password": "external-client-password"}
            )
            assert login.status_code == 200
            token = http.cookies.get("done_session")
            http.headers["Authorization"] = "Bearer " + token
            async with streamable_http_client(base + "/mcp/", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    assert initialized.protocolVersion >= "2025-11-25"
                    tools = await session.list_tools()
                    assert {t.name for t in tools.tools} >= {
                        "compile_ambient_commitment",
                        "spawn_watchdog_subagent",
                        "evaluate_deadline_escalation",
                        "dispatch_police_evidence_dossier",
                        "bridge_ring_camera_to_firetv",
                    }
                    result = await session.call_tool(
                        "compile_ambient_commitment",
                        {
                            "utterance_json": {
                                "event_id": "external-client",
                                "utterance": "I'll call my sister before 6 PM.",
                                "occurred_at": "2026-10-20T08:15:00+05:30",
                            },
                            "speaker_context": {"speaker": "SELF"},
                        },
                    )
                    assert not result.isError, str(result)
                    contracts = (await http.get("/api/contracts")).json()["contracts"]
                    assert len(contracts) == 1 and contracts[0]["status"] == "ACTIVE"
                    denied = await session.call_tool(
                        "dispatch_police_evidence_dossier",
                        {"incident_id": "any", "human_confirmed_boolean": True},
                    )
                    assert "OWNER_APPROVAL_REQUIRED" in str(denied)
                    read_result = await session.call_tool("list_active_contracts", {})
                    assert "psc_sister" in str(read_result)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def test_mcp_accepts_configured_public_host_and_rejects_others(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from done_irl.api import create_app

    monkeypatch.setenv("PUBLIC_HOSTS", "judge.example.test")
    app = create_app(tmp_path, {"judge": "public-host-password"})
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    }
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with TestClient(app, base_url="https://judge.example.test") as client:
        client.post("/api/auth/login", json={"username": "judge", "password": "public-host-password"})
        auth = {**headers, "Authorization": "Bearer " + client.cookies.get("done_session")}
        assert client.post("/mcp/", json=body, headers=auth).status_code == 200
        rejected = client.post("/mcp/", json=body, headers={**auth, "Host": "attacker.example.test"})
        assert rejected.status_code == 421
