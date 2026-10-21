# Product feedback — observed use only

Written from what actually happened while building Muni (October 2026). Tools that have not yet been exercised against a live account say so explicitly; nothing here is inferred from documentation alone. Friction entries with full repro steps: [friction-log.md](friction-log.md).

## Alexa+ — MCP Streamable HTTP (primary track)

| Field | Feedback |
|---|---|
| Purpose | Muni's orchestrator is a self-hosted MCP server (`apps/mcp-orchestrator/done_irl/api.py`, `mcp_ext.py`) exposing 11 tools: the five original actions (`compile_ambient_commitment`, `spawn_watchdog_subagent`, `evaluate_deadline_escalation`, `dispatch_police_evidence_dossier`, `bridge_ring_camera_to_firetv`) plus read-only state tools. A labelled simulated Alexa+ panel calls them over real JSON-RPC. |
| Zero-to-hello-world | Under an hour with the official Python SDK (FastMCP, stateless JSON responses) mounted in FastAPI. Hosted HTTPS took longer because of Host validation (below). |
| Best part | Streamable HTTP is just HTTP: the same authenticated household API backs REST, the browser panel and any MCP client; `2025-11-25` negotiation and tool discovery worked with the official SDK client and the MCP Inspector CLI. |
| Friction | The SDK's DNS-rebinding defaults allow only localhost, so the first public deployment answered `421 Invalid Host header` (friction A5). No public way to connect a self-hosted server to a real Alexa+ device for testing. |
| Workaround | Explicit allowed hosts/origins from deployment config plus a regression test; simulated Alexa+ panel clearly badged. |
| Requested improvement | (Important) A sandbox Alexa+ client or test console that can call a public MCP URL; a deployment checklist for Host/Origin/auth/protocol headers. |
| Build again? | Yes — the tool contract is a good fit for "act on the physical world, but only with evidence". |

## Bee developer API and bee-cli

| Field | Feedback |
|---|---|
| Purpose | Ambient commitment capture: `GET /v1/stream` (`new-utterance`, `todo-created`) and `GET /v1/todos` feed the commitment compiler (`done_irl/adapters.py`). |
| Zero-to-hello-world | Docs list endpoints and event types clearly; the payload shapes had to be read from the official bee-cli source. |
| Best part | SSE with typed events plus Bee's own extracted todos (with alarms) are exactly the primitives a commitment tracker needs. |
| Friction | No per-event JSON schema or timestamp units in the docs (friction A1); no documented wearer attribution on utterances (A2). |
| Workaround | Normalizer mirroring bee-cli, ignore unknown shapes, unattributed speech held for owner confirmation. |
| Requested improvement | (Critical for integrators) Published event schemas and samples; (Important) an `is_wearer` field. |
| Build again? | Yes. **Live account test pending** — `scripts/bee-live-probe.py` is ready; results will be added when run. |

## Ring Partner API

| Field | Feedback |
|---|---|
| Purpose | Backend-only device discovery, capabilities, event history, signed webhooks and WHEP live view feeding porch/threshold/pose pipelines (`adapters.py`, `camera.py`, `webhooks.py`). |
| Zero-to-hello-world | The WHEP flow (recvonly offer, gathered ICE, `201` + `Location`, `DELETE`) is well specified; implemented and tested with a real aiortc codec loopback. |
| Best part | Standard WHEP means any WebRTC stack can decode Ring video server-side. |
| Friction | 30-minute Playground tokens and 30/60-second live sessions make a judging window weeks later impossible to support live; designs must be event-driven with honest coverage gaps. |
| Workaround | Durable event-driven watchdog, labelled recorded sources, redacted live probe for when a token exists. |
| Requested improvement | (Important) Longer-lived hackathon/sandbox tokens or an official recorded-device simulator endpoint. |
| Build again? | Yes. **No live camera run yet** — `scripts/ring-live-probe.py` is ready. |

## Fire TV — Fire OS (Android) tooling

| Field | Feedback |
|---|---|
| Purpose | `apps/firetv-command-hud`: native Fire OS shell with leanback launcher and D-pad focus around the authenticated four-view HUD. |
| Zero-to-hello-world | APK builds in minutes with Gradle 8.13/AGP; validated on an Android TV API 30 emulator (33/33 scripted D-pad checks). |
| Best part | Standard Android TV focus APIs; the same APK can be sideloaded on Fire OS. |
| Friction | No Fire OS emulator; the older system WebView lacked `crypto.randomUUID`, breaking sign-in until a fallback was added; web key handlers trapped D-pad focus. |
| Workaround | Fallback UUID, native/web focus hand-off and Back handling. |
| Requested improvement | (Important) An official Fire OS emulator image or cloud device for teams without hardware. |
| Build again? | Yes. **Physical Fire TV untested** (no device available). |

## Vega OS SDK / Vega Virtual Device

Being evaluated in WSL2 (KVM available). Feedback will be recorded here only after the SDK install and Virtual Device run actually complete.

## AWS (AWS Builder mini challenge)

| Service | How Muni uses it (live in stack `done-irl-judge`) |
|---|---|
| CloudFormation | `infra/aws/judge-demo.yaml` provisions everything below; `cfn-lint` in CI. |
| EC2 + SSM | Single active reducer building an exact public commit; SSM Run Command redeploys (`scripts/judge-redeploy.sh`), no SSH. |
| DynamoDB | Encrypted (KMS), PITR projection of contracts, sub-agents, incidents, evidence and audit (`HOUSE#…` partitions); conditional revision writes. |
| S3 + KMS | Private, versioned, SSE-KMS evidence replica and hash-checked state snapshots; lifecycle expiry. |
| EventBridge Scheduler | One-time `at()` schedules for every T-60 / T-25 / deadline job of wall-clock promises. |
| SQS (+ DLQ) | Scheduler wake-ups to the reconciler; KMS-encrypted, dead-letter after six receives. |
| Secrets Manager | Ledger key and owner/admin passwords, never in stack parameters or git. |
| CloudWatch | Container logs and queue-age / DLQ alarms. |
| Bedrock (attempted) | Nova Converse returned `Operation not allowed` in three regions (friction A3); the product ships a deterministic compiler instead. |

What worked: Scheduler `at()` expressions with `ActionAfterCompletion=DELETE` are a clean fit for per-promise escalations; DynamoDB/S3/KMS wiring was straightforward. What needs work: CloudFront's account-verification block surfaced mid-stack (A4), and Bedrock's error gave no remedy (A3). Would build again: Yes.

## Other tools

| Tool | Purpose | Feedback |
|---|---|---|
| MediaPipe Pose / Object Detector | Rep counting and porch/threshold detection on decoded frames | Pinned models are easy to verify; native libs (`libGLESv2`, `libEGL`) must be installed separately on Linux; the larger pose model counted fewer reps on the generated fixture than lite. |
| GitHub Actions | Clean-checkout CI: backend/MCP, browser journeys, APK, container | Reliable; `setup-android` defaulted to a removed `tools` package. |
