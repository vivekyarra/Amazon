# Product feedback

Written from hands-on use while building Muni (October 2026); every point below comes from something we actually ran. Full repro steps for each friction item are in the [friction log](friction-log.md).

## Alexa+ — MCP Streamable HTTP (primary track)

| Field | Feedback |
|---|---|
| Purpose | Muni's orchestrator is a self-hosted MCP server (`apps/mcp-orchestrator/done_irl/api.py`, `mcp_ext.py`) exposing 11 tools: five actions (`compile_ambient_commitment`, `spawn_watchdog_subagent`, `evaluate_deadline_escalation`, `dispatch_police_evidence_dossier`, `bridge_ring_camera_to_firetv`) plus read-only state tools. A clearly badged Alexa+ console panel calls them over real JSON-RPC. |
| Zero-to-hello-world | Under an hour with the official Python SDK (FastMCP, stateless JSON responses) mounted in FastAPI. Hosted HTTPS took longer because of Host validation (below). |
| Best part | Streamable HTTP is just HTTP: the same authenticated household API backs REST, the browser panel and any MCP client. `2025-11-25` negotiation and tool discovery worked with the official SDK client, the MCP Inspector CLI and the hosted HTTPS endpoint, where `compile_ambient_commitment` created real EventBridge schedules. |
| Friction | The SDK's DNS-rebinding defaults allow only localhost, so the first public deployment answered `421 Invalid Host header` (friction A5). No public way to connect a self-hosted server to an Alexa+ device for testing. |
| Workaround | Explicit allowed hosts/origins from deployment config plus a regression test; the console panel is badged so it is never mistaken for an Alexa device. |
| Requested improvement | (Important) A sandbox Alexa+ client or test console that can call a public MCP URL; a deployment checklist for Host/Origin/auth/protocol headers. |
| Build again? | Yes — the tool contract is a good fit for "act on the physical world, but only with evidence". |

## Bee developer API and bee-cli

| Field | Feedback |
|---|---|
| Purpose | Ambient commitment capture: `GET /v1/stream` (`new-utterance`, `todo-created`) and `GET /v1/todos` feed the commitment compiler (`done_irl/adapters.py`). |
| Zero-to-hello-world | Docs list endpoints and event types clearly; the payload shapes had to be read from the official bee-cli source. Once mirrored, the live stream from a Bee device compiled into contracts on the first run ([verification](evidence/bee-live-verification.md)). |
| Best part | SSE with typed events plus Bee's own extracted todos (with alarms) are exactly the primitives a commitment tracker needs. |
| Friction | No per-event JSON schema or timestamp units in the docs (friction A1); no documented wearer attribution on utterances (A2). |
| Workaround | Normalizer mirroring bee-cli, unknown shapes ignored, unattributed speech held for owner confirmation. |
| Requested improvement | (Critical for integrators) Published event schemas and samples; (Important) an `is_wearer` field. |
| Build again? | Yes. |

## Ring Partner API

| Field | Feedback |
|---|---|
| Purpose | Backend-only device discovery, capabilities, event history, signed webhooks and WHEP live view feeding the porch, threshold and pose pipelines (`adapters.py`, `camera.py`, `webhooks.py`). |
| Zero-to-hello-world | The WHEP flow (recvonly offer, gathered ICE, `201` + `Location`, `DELETE`) is well specified. Against the Ring Developer Playground device it worked end to end: device discovery, capabilities, event history and 176 decoded 1280×720 H.264 frames ([probe](evidence/ring-live-probe.json)), then the same stream through the Reality-Lock studio with MediaPipe on every frame ([studio](evidence/ring-live-studio.json)). |
| Best part | Standard WHEP means any WebRTC stack can decode Ring video server-side. |
| Friction | 30-minute Playground tokens and 30/60-second live sessions mean a judging window days later cannot be served live; designs must be event-driven with explicit coverage gaps. |
| Workaround | Durable event-driven watchdog, labelled recorded sources, and a redacted live probe (`scripts/ring-live-probe.py`) that re-verifies whenever a token is available. |
| Requested improvement | (Important) Longer-lived hackathon/sandbox tokens or an official recorded-device endpoint. |
| Build again? | Yes. |

## Fire TV — Vega OS SDK and Vega Virtual Device

| Field | Feedback |
|---|---|
| Purpose | `apps/firetv-vega-hud`: React Native for Vega app with four D-pad views over the hosted backend. |
| Zero-to-hello-world | The official installer and `helloWorld` template got an app onto the Vega Virtual Device in WSL2 with KVM; `vega run-app -d VirtualDevice` installs and launches in one step ([report](../tests/firetv/vega-device-report.md)). |
| Best part | Familiar React Native with first-class D-pad focus; the same `.vpkg` build targets x86_64, armv7 and aarch64. |
| Friction | The Vega Virtual Device did not raise a system IME for `TextInput`; scripted input through `vda shell inputd-cli button_press` was reliable only one key at a time; under WSL the launching shell must stay alive. |
| Workaround | An in-app 5×10 D-pad keyboard for sign-in; single-key test helpers in `tests/firetv/vega/`. |
| Requested improvement | (Important) System keyboard support on the Virtual Device and a batched input command for automation. |
| Build again? | Yes. |

## Fire TV — Fire OS (Android) tooling

| Field | Feedback |
|---|---|
| Purpose | `apps/firetv-command-hud`: native Fire OS shell with leanback launcher and D-pad focus around the authenticated four-view HUD. |
| Zero-to-hello-world | APK builds in minutes with Gradle 8.13/AGP; validated on an Android TV API 30 emulator (33/33 scripted D-pad checks). |
| Best part | Standard Android TV focus APIs; the same APK sideloads onto Fire OS. |
| Friction | No Fire OS emulator image; the older system WebView lacked `crypto.randomUUID`, breaking sign-in until a fallback was added; web key handlers trapped D-pad focus. |
| Workaround | Fallback UUID, native/web focus hand-off and Back handling. |
| Requested improvement | (Important) An official Fire OS emulator image or cloud device for teams without hardware. |
| Build again? | Yes. |

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
| Bedrock (attempted) | Nova Converse returned `Operation not allowed` in three regions (friction A3); Muni ships a deterministic, tested compiler instead. |

What worked: Scheduler `at()` expressions with `ActionAfterCompletion=DELETE` are a clean fit for per-promise escalations; DynamoDB/S3/KMS wiring was straightforward. What needs work: CloudFront's account-verification block surfaced mid-stack (A4), and Bedrock's error gave no remedy (A3). Would build again: Yes.

## Other tools

| Tool | Purpose | Feedback |
|---|---|---|
| MediaPipe Pose / Object Detector | Rep counting and porch/threshold detection on decoded frames | Pinned models are easy to verify; native libs (`libGLESv2`, `libEGL`) must be installed separately on Linux; the larger pose model counted fewer reps on the generated fixture than lite. |
| GitHub Actions | Clean-checkout CI: backend/MCP, browser journeys, APK, container | Reliable; `setup-android` defaulted to a removed `tools` package. |

## Feature requests

| Request | Why it matters | Urgency |
|---|---|---|
| Published JSON schemas and samples for every Bee stream event | Integrators currently reverse-engineer payloads from bee-cli source (A1) | Critical |
| A sandbox Alexa+ client that can call a public MCP URL | Lets MCP builders test the real Alexa+ conversation loop before Preview access | Important |
| Actionable Bedrock access errors | `Operation not allowed` gives no remedy and blocks Nova adoption (A3) | Important |
| Longer-lived Ring Playground tokens | Judging and demos run for days; 30-minute tokens cannot serve a live view (A6) | Important |
| `is_wearer` / speaker identity on Bee utterances | Safely separates the wearer's promises from other people's speech (A2) | Important |
| System keyboard and batched input on the Vega Virtual Device | Unblocks sign-in flows and automated D-pad testing (A7, A8) | Important |
| Official Fire OS emulator image | Teams without hardware can validate Fire OS behaviour, not just Android TV (A9) | Important |
| CloudFormation pre-flight for account-level blocks | Avoids half-created stacks and manual cleanup (A4) | Nice-to-have |
| Public-deployment checklist in Alexa+ MCP docs | Host/Origin defaults silently reject public traffic (A5) | Nice-to-have |
