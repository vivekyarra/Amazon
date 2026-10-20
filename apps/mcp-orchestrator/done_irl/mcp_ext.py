"""MCP transport hardening and the read-only orchestrator tools from spec section 7.2.

Kept separate from ``api.py`` so the transport/compliance policy and the read tools can be
reviewed (and tested) in isolation. Every tool here reads the same owner-scoped household
ledger as the REST API; none of them mutates state, dispatches anything, or claims device
delivery.
"""

import json
import os
import typing
from urllib.parse import urlsplit

import mcp.types as mcp_types
from fastapi.responses import JSONResponse, Response
from mcp.server.transport_security import TransportSecuritySettings

from .models import ApiError

PROTOCOL_VERSION = mcp_types.LATEST_PROTOCOL_VERSION  # "2025-11-25" with the pinned SDK
LOCAL_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOCAL_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def _methods(union) -> set[str]:
    root = union.model_fields["root"].annotation
    return {typing.get_args(m.model_fields["method"].annotation)[0] for m in typing.get_args(root)}


KNOWN_METHODS = _methods(mcp_types.ClientRequest) | _methods(mcp_types.ClientNotification)


def transport_security(demo: bool) -> TransportSecuritySettings:
    """DNS-rebinding protection: Host and Origin must match configured deployment origins.

    The SDK default only allows localhost hosts, which would reject a real deployment with
    421; here the allowed hosts are derived from ALLOWED_ORIGINS (plus MCP_ALLOWED_HOSTS).
    """
    origins = [o for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o]
    hosts = [urlsplit(o).netloc for o in origins if urlsplit(o).netloc]
    hosts += [h for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h]
    if demo:
        hosts += LOCAL_HOSTS
        origins += LOCAL_ORIGINS
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins
    )


def jsonrpc_error(code: int, message: str, request_id=None, status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
    )


async def guard(request, call_next, authenticate, error_response, tool_names=frozenset()):
    """Streamable HTTP edge policy applied before the SDK transport.

    - Authentication on every MCP request (initialize/discovery included); 401 carries
      ``WWW-Authenticate: Bearer`` as required by RFC 6750 / MCP authorization guidance.
    - GET: this server is stateless and never initiates server->client messages, so per the
      2025-11-25 transport spec it answers 405 instead of opening an idle SSE stream.
    - Unknown JSON-RPC request methods return -32601 (Method not found); an unknown tool name
      in ``tools/call`` is a protocol error -32602, as in the 2025-11-25 tools specification.
    - ``/mcp`` is served directly (no 307 redirect to ``/mcp/``).
    """
    if not request.url.path.startswith("/mcp"):
        return await call_next(request)
    if request.url.path == "/mcp":
        request.scope["path"] = "/mcp/"
        request.scope["raw_path"] = b"/mcp/"
    try:
        authenticate(request)
    except ApiError as error:
        response = error_response(error)
        if error.status == 401:
            response.headers["WWW-Authenticate"] = 'Bearer realm="done-irl-mcp"'
        return response
    if request.method == "GET":
        return Response(
            status_code=405,
            headers={"Allow": "POST"},
            content="Method Not Allowed: stateless server; no standalone SSE stream is offered.",
        )
    if request.method == "POST":
        body = await request.body()
        try:
            message = json.loads(body)
        except ValueError:
            message = None  # the SDK returns the JSON-RPC -32700 parse error
        if (
            isinstance(message, dict)
            and isinstance(message.get("method"), str)
            and message["method"] not in KNOWN_METHODS
        ):
            if "id" not in message:
                return Response(status_code=202)  # unknown notification: accept and ignore
            return jsonrpc_error(-32601, "Method not found: " + message["method"][:80], message["id"])
        if isinstance(message, dict) and message.get("method") == "tools/call" and tool_names:
            name = (
                (message.get("params") or {}).get("name") if isinstance(message.get("params"), dict) else None
            )
            if name not in tool_names:
                return jsonrpc_error(-32602, "Unknown tool: " + str(name)[:80], message.get("id"))
    return await call_next(request)


def register_read_tools(mcp, *, principal, initial, integrations):
    """Register the spec 7.2 read-only tools. ``principal`` authenticates the MCP request."""

    def household():
        p = principal()
        return p, initial(p["household"])

    def find_contract(s, contract_id):
        c = next((c for c in s["contracts"] if c["contract_id"] == contract_id), None)
        if not c:
            raise ApiError(404, "NOT_FOUND", "Contract not found in this household.")
        return c

    @mcp.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True, idempotentHint=True))
    def get_contract_state(contract_id: str) -> dict:
        """Read one Physical State Contract, its evidence metadata and audit timeline (owner-scoped)."""
        _, s = household()
        c = find_contract(s, contract_id)
        return {
            "contract": c,
            "evidence": [
                {k: v.get(k) for k in ("evidence_id", "kind", "source_mode", "provenance", "captured_at")}
                for v in s["evidence"]
                if v["evidence_id"] in c.get("evidence_ids", [])
            ],
            "timeline": [
                {k: v[k] for k in ("event_id", "event_type", "occurred_at", "source_mode")}
                for v in s["events"]
                if v["payload"].get("contract_id") == contract_id
            ],
            "incident_ids": [i["incident_id"] for i in s["incidents"] if i.get("contract_id") == contract_id],
            "server_clock": s["now"],
            "verified": c["status"] == "VERIFIED",
        }

    @mcp.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True, idempotentHint=True))
    def get_watchdog_status(contract_id: str = "") -> dict:
        """Read persistent sub-agent (PorchWatchdog etc.) status; optionally filtered by contract."""
        _, s = household()
        agents = [a for a in s["subagents"] if not contract_id or a["contract_id"] == contract_id]
        return {
            "subagents": agents,
            "consent": s["consent"],
            "failures": s.get("failures", []),
            "source_mode": s.get("source_mode"),
        }

    @mcp.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True, idempotentHint=True))
    def get_incident_packet(incident_id: str) -> dict:
        """Read an incident packet's metadata and hashes. Raw media stays behind authenticated REST."""
        _, s = household()
        inc = next((i for i in s["incidents"] if i["incident_id"] == incident_id), None)
        if not inc:
            raise ApiError(404, "NOT_FOUND", "Incident not found in this household.")
        ids = {v for v in inc.get("packet", {}).values() if isinstance(v, str)}
        return {
            "incident": inc,
            "evidence": [
                {
                    k: v.get(k)
                    for k in ("evidence_id", "kind", "source_mode", "sha256_original", "captured_at")
                }
                for v in s["evidence"]
                if v["evidence_id"] in ids
            ],
            "report_states_distinct": ["DRAFT", "OWNER_APPROVED", "SIMULATED_DISPATCH", "RECEIPT"],
            "official_case_id": None if not inc.get("receipt") else inc["receipt"].get("receipt_id"),
            "note": "Only an externally validated receipt is an official case ID.",
        }

    @mcp.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True, idempotentHint=True))
    def get_integration_health() -> dict:
        """Read truthful per-provider status (LIVE_VERIFIED / SIMULATED_VERIFIED / NOT_CONNECTED / BLOCKED)."""
        p = principal()
        return {"integrations": integrations(p)["integrations"]}

    @mcp.tool(annotations=mcp_types.ToolAnnotations(readOnlyHint=True, idempotentHint=True))
    def request_user_verification(contract_id: str) -> dict:
        """Describe how the owner can verify a contract. Changes nothing; never marks anything verified."""
        _, s = household()
        c = find_contract(s, contract_id)
        return {
            "contract_id": contract_id,
            "status": c["status"],
            "verification_modality": c.get("verification_modality"),
            "prompt": (
                "Already verified by recorded evidence."
                if c["status"] == "VERIFIED"
                else f"'{c['title']}' is not yet verified. Open the authenticated companion to "
                "provide accepted evidence; a spoken 'yes' is not proof."
            ),
            "action_url": "/?contract=" + contract_id,
            "state_changed": False,
        }
