# Integration status

Checked 2026-10-20. These labels describe observed capabilities, never adapter filenames.

| Surface / capability | Status | Actual proof / gap |
|---|---|---|
| Bee canonical ingestion | SIMULATED_VERIFIED | Protected fixtures create four persisted contracts; duplicate/ambiguity tests pass |
| Bee live SSE | BLOCKED | Durable SSE/cursor/inbox wiring and parser/backoff tests exist; actual event-envelope/device verification and authorized token are unavailable |
| MCP Streamable HTTP | SIMULATED_VERIFIED | Official SDK (`mcp` 1.30), protocol `2025-11-25`, stateless JSON responses. Verified locally: version negotiation and `MCP-Protocol-Version` header validation, bearer/cookie auth on every request (401 + `WWW-Authenticate`), Origin and Host (DNS-rebinding) validation, `GET` → 405 (no standalone SSE stream offered), JSON-RPC -32700/-32601/-32602 errors (`test_mcp_compliance.py`). Eleven tools: the original five plus read-only `list_active_contracts`, `get_contract_state`, `get_watchdog_status`, `get_incident_packet`, `get_integration_health`, `request_user_verification`. `dispatch_police_evidence_dossier` always denies and writes an audited, idempotent `incident.mcp_dispatch_denied` event. External proof: `scripts/mcp-external-client.py` (official Python SDK client over real localhost HTTP) → `docs/evidence/mcp-external-client.json`; official MCP Inspector CLI `tools/list` → `docs/evidence/mcp-inspector-cli.json` (PASS, localhost). Not tested: a hosted/HTTPS deployment, OAuth-based MCP authorization (session bearer tokens are used instead), server-initiated notifications |
| Alexa+ account/device | NOT_CONNECTED | No actual Alexa+ account connection, skill/connector registration or voice delivery verified |
| Simulated Alexa+ experience (judge console) | SIMULATED_VERIFIED | Judge replay page panel badged "SIMULATED ALEXA+ — not an Alexa device": typed or Web Speech API input, deterministic intent router (no LLM), real same-origin authenticated JSON-RPC to `/mcp/`, request/response log, `speechSynthesis` replies, and spec 5.4 T-25 / arrival copy rendered as a "SIMULATED WHISPER — not delivered to any device". Typed path proven by `tests/e2e/alexa-sim.spec.ts`; microphone path is browser-dependent and not automated |
| Ring camera/API account | BLOCKED | Documented webhook, account/device binding and WHEP/MediaPipe relay implemented; no linked camera/token or actual runtime proof |
| Ring-like porch/threshold replay | SIMULATED_VERIFIED | Actual generated marker pixels segmented/tracked by OpenCV; not an official Ring simulator |
| Vision human pose | BLOCKED | Optional MediaPipe worker supplied; model fetched from official host; native runtime libraries resolved through authenticated Debian package metadata; actual CPU inference counted zero on 20 nonhuman frames and one on a licensed public 363-frame human sample; fifteen-rep acceptance is still outstanding |
| Fire OS client build | SIMULATED_VERIFIED | Native debug APK compiled; CI build evidence tracked separately |
| Actual Fire TV runtime | BLOCKED | No install/launch/device recording; web preview is not a Fire OS/Vega runtime |
| Web TV/companion | SIMULATED_VERIFIED | Shared authenticated ledger, inbox, D-pad web preview and mobile browser tests |
| Official incident filing | BLOCKED | No authorized official receiver; export and isolated labeled demo receiver only |
| Bee haptics / earbud whisper | BLOCKED | No supported, authorized delivery API verified; no fake-success adapter |
| Cross-app entertainment lock | BLOCKED | Only voluntary DONE/IRL in-app gate; no third-party app control |
| AWS runtime | NOT_CONNECTED | AWS outbox/S3/DynamoDB/Scheduler/SQS/restore and validated infrastructure implemented; eight Moto tests pass, actual credentials/deployment unavailable |

A logical WATCHING subagent is persisted event-driven work. It never promises uninterrupted camera observation. Live source failures do not silently become live-looking replay. Last successful live probe is **none** for the blocked connections.
