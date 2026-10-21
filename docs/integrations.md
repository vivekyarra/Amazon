# Integrations

Every integration below runs through the same backend, reducers and evidence policy. Source labels travel with every observation, so the ledger always knows whether a fact came from a live device, a recording or a scripted replay.

## Amazon devices and services

| Surface | What runs | Proof |
|---|---|---|
| **Alexa+ (MCP)** | Self-hosted MCP server, Streamable HTTP, protocol `2025-11-25`, 11 tools (`compile_ambient_commitment`, `spawn_watchdog_subagent`, `evaluate_deadline_escalation`, `dispatch_police_evidence_dossier`, `bridge_ring_camera_to_firetv` + read-only state tools). Live on the public HTTPS deployment; the web Alexa+ experience calls it over real JSON-RPC. | [external SDK client](evidence/mcp-external-client.json) · [MCP Inspector](evidence/mcp-inspector-cli.json) · [hosted call + schedules](evidence/aws-mcp-scheduler.json) |
| **Ring Partner API** | Ring Developer Playground device: `GET /v1/devices`, capabilities, event history, WHEP receive-only live view (176 distinct 1280×720 H.264 frames decoded server-side), session cleanup; the same stream feeds the Reality-Lock studio as **LIVE RING** with MediaPipe pose on every frame. Signed webhooks (`X-Signature` HMAC) verified. | [probe](evidence/ring-live-probe.json) · [studio relay](evidence/ring-live-studio.json) · [frames](evidence/ring-live/) |
| **Bee** | Bee developer API on a real Bee device: `GET /v1/stream` SSE (`new-utterance`, `todo-created`) and `GET /v1/todos` backfill compiled into commitment contracts. | [verification](evidence/bee-live-verification.md) |
| **Fire TV — Vega OS** | React Native for Vega app (`apps/firetv-vega-hud`) built with the Vega SDK, installed and run on the Vega Virtual Device; all four views by D-pad against the live backend. | [device report](../tests/firetv/vega-device-report.md) · [recording](evidence/vega/vvd-session-4x.mp4) |
| **Fire TV — Fire OS** | Android TV / Fire OS APK (`apps/firetv-command-hud`); D-pad journey (33 checks) runs on an Android TV emulator in CI on every push. | [report](../tests/firetv/device-report.md) · [walkthrough](evidence/firetv/walkthrough.mp4) · [CI](evidence/ci-runs.md) |
| **AWS** | CloudFormation stack: EC2 reducer (SSM-managed), DynamoDB (KMS, PITR), S3 (SSE-KMS, versioned), EventBridge Scheduler → SQS (KMS, DLQ), Secrets Manager, CloudWatch. Real T-60 / T-25 / deadline escalations fired by EventBridge within a second of schedule. | [deployment](evidence/aws-deployment.json) · [live escalation](evidence/aws-live-escalation.json) |

## Perception

| Capability | What runs | Proof |
|---|---|---|
| Porch & doorway vision | MediaPipe EfficientDet + ROI change detection + IoU tracking on real licensed doorstep/CCTV footage: deposit vs courier fake-out, porch removal, inward pickup, passer-by, drinks visible / hands empty / bags. 10/10 clips correct. | [results](evidence/scene-vision.json) · [annotated frames](evidence/scene/) |
| Reality-Lock pose | MediaPipe Pose counts complete squat cycles from video; 14 stays locked, 15 unlocks; half squats, frozen frames and looped reps add nothing. | [fixture results](evidence/pose-15-fixture.json) · [annotated clip](evidence/pose-15-annotated.mp4) |

## Companion

Standard Web Push (VAPID, aes128gcm) to the owner's phone or browser, with generic lock-screen copy for incident alerts. The console works on desktop, TV and mobile.

## Safety by design

These are deliberate product decisions, not missing features:

- **No autonomous police reports.** Muni preserves a hash-chained evidence packet and asks the owner. A report requires an explicit, authenticated approval of the exact packet; the demo receiver records the dispatch and sends nothing to any police service.
- **"Not seen" is never "absent".** A camera that cannot see the drinks asks you to check; it never accuses.
- **A spoken "I did it" is a lead, not proof.** It moves a promise to *awaiting your confirmation*; owner confirmations are labelled separately from sensor proof.
- **In-app reward gate only.** Reality-Lock unlocks Muni's own entertainment action; it never controls other apps.
- **Nothing reaches a device unless that device's API confirms it.** Alerts go to the authenticated companion and Web Push; Muni does not pretend to whisper through earbuds or vibrate a wearable.
