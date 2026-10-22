"""MCP 2025-11-25 Streamable HTTP edge behavior and the spec 7.2 read-only tools."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "http://127.0.0.1:8080"
ACCEPT = "application/json, text/event-stream"
READ_TOOLS = {
    "list_active_contracts",
    "get_contract_state",
    "get_watchdog_status",
    "get_incident_packet",
    "get_integration_health",
    "request_user_verification",
}
ORIGINAL_TOOLS = {
    "compile_ambient_commitment",
    "spawn_watchdog_subagent",
    "evaluate_deadline_escalation",
    "dispatch_police_evidence_dossier",
    "bridge_ring_camera_to_firetv",
}


def login(c, user="judge", password="test-admin-password"):
    r = c.post("/api/auth/login", json={"username": user, "password": password})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + c.cookies.get("done_session")}


@pytest.fixture
def mcp(app):
    with TestClient(app, base_url=BASE) as c:
        auth = login(c)
        c.cookies.clear()  # prove bearer auth alone is enough

        def rpc(method, params=None, headers=None, rid=None, raw=False):
            body = {"jsonrpc": "2.0", "id": rid or uuid.uuid4().hex[:8], "method": method}
            if params is not None:
                body["params"] = params
            r = c.post(
                "/mcp/",
                json=body,
                headers={"Accept": ACCEPT, "MCP-Protocol-Version": "2025-11-25", **auth, **(headers or {})},
            )
            return r if raw else r.json()

        def call(name, arguments=None):
            out = rpc("tools/call", {"name": name, "arguments": arguments or {}})
            assert "result" in out, out
            result = out["result"]
            if result.get("isError"):
                return {"_error": result["content"][0]["text"]}
            return result.get("structuredContent") or json.loads(result["content"][0]["text"])

        def post(path, body=None):
            r = c.post("/api" + path, json=body or {}, headers={**auth, "Idempotency-Key": uuid.uuid4().hex})
            assert r.status_code == 200, r.text
            return r.json()

        c.rpc, c.call, c.post_api, c.bearer = rpc, call, post, auth
        yield c


def test_initialize_negotiates_2025_11_25(mcp):
    init = {"capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"}}
    ok = mcp.rpc("initialize", {**init, "protocolVersion": "2025-11-25"})
    assert ok["result"]["protocolVersion"] == "2025-11-25"
    assert ok["result"]["capabilities"]["tools"] is not None
    # An unsupported requested version gets the server's latest supported version back.
    other = mcp.rpc("initialize", {**init, "protocolVersion": "1999-01-01"})
    assert other["result"]["protocolVersion"] == "2025-11-25"
    # The MCP-Protocol-Version header is validated on subsequent requests.
    bad = mcp.rpc("tools/list", headers={"MCP-Protocol-Version": "1999-01-01"}, raw=True)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == -32600


def test_tools_list_includes_original_and_read_only_tools(mcp):
    tools = {t["name"]: t for t in mcp.rpc("tools/list")["result"]["tools"]}
    assert set(tools) >= ORIGINAL_TOOLS | READ_TOOLS
    for name in READ_TOOLS - {"list_active_contracts"}:
        assert tools[name]["annotations"]["readOnlyHint"] is True


def test_jsonrpc_errors(mcp):
    assert mcp.rpc("nope/nope")["error"]["code"] == -32601
    assert mcp.rpc("tools/call", {"name": "zzz", "arguments": {}})["error"]["code"] == -32602
    r = mcp.post(
        "/mcp/",
        content=b"{not json",
        headers={"Accept": ACCEPT, "Content-Type": "application/json", **mcp.bearer},
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700
    r = mcp.post(
        "/mcp/",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Accept": "text/html", **mcp.bearer},
    )
    assert r.status_code == 406


def test_transport_http_semantics(mcp):
    r = mcp.get("/mcp/", headers={"Accept": "text/event-stream", **mcp.bearer})
    assert r.status_code == 405 and r.headers["allow"] == "POST"
    # /mcp without trailing slash is served, not redirected.
    r = mcp.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Accept": ACCEPT, **mcp.bearer},
        follow_redirects=False,
    )
    assert r.status_code == 200 and r.json()["result"] == {}
    assert mcp.rpc("notifications/unknown", raw=True).status_code in {200, 202}


def test_auth_origin_and_host_validation(app):
    with TestClient(app, base_url=BASE) as c:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        r = c.post("/mcp/", json=body, headers={"Accept": ACCEPT})
        assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Bearer")
        r = c.post("/mcp/", json=body, headers={"Accept": ACCEPT, "Authorization": "Bearer forged"})
        assert r.status_code == 401
        auth = login(c)
        c.cookies.clear()
        r = c.post("/mcp/", json=body, headers={"Accept": ACCEPT, "Origin": "https://evil.example", **auth})
        assert r.status_code == 403
        r = c.post("/mcp/", json=body, headers={"Accept": ACCEPT, "Host": "evil.example", **auth})
        assert r.status_code == 421  # DNS-rebinding protection
        r = c.post("/mcp/", json=body, headers={"Accept": ACCEPT, "Origin": BASE, **auth})
        assert r.status_code == 200


def test_read_tools_reflect_shared_ledger_without_mutation(mcp):
    for stage in (1, 2, 3, 4):
        mcp.post_api(f"/admin/scenarios/{stage}/run", {"branch": "deposit" if stage == 2 else "unknown"})
    before = mcp.get("/api/state", headers=mcp.bearer).json()["state"]
    contracts = mcp.call("list_active_contracts")["contracts"]
    by_key = {c["key"]: c for c in contracts}
    sister = mcp.call("get_contract_state", {"contract_id": by_key["sister"]["contract_id"]})
    assert sister["contract"]["key"] == "sister" and sister["timeline"]
    parcel_id = by_key["parcel"]["contract_id"]
    watch = mcp.call("get_watchdog_status", {"contract_id": parcel_id})
    assert watch["subagents"] and watch["subagents"][0]["kind"] == "PorchWatchdog"
    incident = before["incidents"][0]["incident_id"]
    packet = mcp.call("get_incident_packet", {"incident_id": incident})
    assert packet["official_case_id"] is None and packet["evidence"]
    assert all("sha256_original" in v for v in packet["evidence"])
    health = {i["name"]: i for i in mcp.call("get_integration_health")["integrations"]}
    assert health["Alexa+"]["status"] == "STANDBY"
    verify = mcp.call("request_user_verification", {"contract_id": by_key["drinks"]["contract_id"]})
    assert verify["state_changed"] is False and verify["status"] != "VERIFIED"
    after = mcp.get("/api/state", headers=mcp.bearer).json()["state"]
    assert after["events"] == before["events"] and after["contracts"] == before["contracts"]
    assert "_error" in mcp.call("get_contract_state", {"contract_id": "psc_missing"})
    assert "_error" in mcp.call("get_incident_packet", {"incident_id": "inc_missing"})


def test_dispatch_is_denied_audited_and_idempotent(mcp):
    for stage in (1, 2, 4):
        mcp.post_api(f"/admin/scenarios/{stage}/run", {"branch": "deposit" if stage == 2 else "unknown"})
    incident = mcp.get("/api/state", headers=mcp.bearer).json()["state"]["incidents"][0]
    args = {"incident_id": incident["incident_id"], "human_confirmed_boolean": True}
    first = mcp.call("dispatch_police_evidence_dossier", args)
    second = mcp.call("dispatch_police_evidence_dossier", args)
    assert first == second and first["status"] == "DENIED" and first["external_sends"] == 0
    state = mcp.get("/api/state", headers=mcp.bearer).json()["state"]
    denials = [e for e in state["events"] if e["event_type"] == "incident.mcp_dispatch_denied"]
    assert len(denials) == 1 and denials[0]["source"] == "MCP_TOOL_CALL"
    after = state["incidents"][0]
    assert after["status"] == incident["status"] and after["receipt"] is None


def test_read_tools_are_household_scoped(app):
    with TestClient(app, base_url=BASE) as c:
        admin = login(c)
        c.cookies.clear()
        r = c.post(
            "/api/admin/scenarios/1/run",
            json={"branch": "deposit"},
            headers={**admin, "Idempotency-Key": uuid.uuid4().hex},
        )
        cid = r.json()["state"]["contracts"][0]["contract_id"]
        other = login(c, "other", "test-other-password")
        c.cookies.clear()
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_contract_state", "arguments": {"contract_id": cid}},
        }
        out = c.post("/mcp/", json=body, headers={"Accept": ACCEPT, **other}).json()
        assert out["result"]["isError"] is True and "not found" in out["result"]["content"][0]["text"].lower()
