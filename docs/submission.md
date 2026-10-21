# Devpost submission draft — NOT SUBMITTED

Fill-in-ready text for the owner's Devpost form. Items marked **OWNER** need the owner's accounts or decisions.

## Basics

- **Name:** DONE/IRL
- **Tagline:** APIs lie. Reality doesn't.
- **Primary track:** Alexa+ (self-hosted MCP server, Streamable HTTP `2025-11-25`, plus a clearly labelled simulated Alexa+ experience in the web app).
- **Mini challenges:** AWS Builder (live AWS stack, below). Open Source — Agent Skill PR https://github.com/AmazonAppDev/devices-agent-skills/pull/16.
- **Repository:** https://github.com/vivekyarra/Amazon (public, MIT).
- **Live demo:** https://100-49-183-59.sslip.io — judge credentials go in the private testing-instructions field (**OWNER** pastes from `judge-credentials.txt`, never into the repo).
- **Video:** **OWNER** uploads the under-three-minute English video to YouTube/Vimeo (public).

## Description

Assistants remember what you said, then treat a reminder, a courier's "delivered" or a model's `completed=true` as if it were reality. DONE/IRL is a commitment daemon for the home that refuses to call anything done until evidence says so.

You never say "set a reminder". Spoken promises — "I'll call Mom tonight", "I'll pay the electricity bill by Friday", "I'll take out the bins every Monday", a family member's "can you pick up groceries?" — compile into durable *physical state contracts* with a counterparty, a deadline or trigger (arriving home, before TV), a recurrence and a verification method. A scheduler nudges quietly at T-60, escalates at T-25 only if you are not demonstrably on it, and records a miss honestly. Saying "I already called her" moves the promise to *evidence pending*, never to done.

Evidence comes from the physical world. A courier's claim triggers a porch check that distinguishes a real deposit from a fake-out; a deposited parcel spawns a persistent watchdog; a removal produces a hash-chained evidence packet and asks whether it was family — no report leaves without the owner approving the exact packet and destination. Arriving home without the promised drinks gets a private "check before you go in" instead of a false accusation. On the TV, the Reality-Lock studio counts fifteen real squats with MediaPipe before unlocking the in-app reward; fourteen stays locked.

Alexa+ is the control plane: every action is an MCP tool (`compile_ambient_commitment`, `spawn_watchdog_subagent`, `evaluate_deadline_escalation`, `dispatch_police_evidence_dossier`, `bridge_ring_camera_to_firetv`, plus read-only state tools), served over Streamable HTTP and usable from any MCP client or the simulated Alexa+ panel.

## How it works / tech stack

Python FastAPI orchestrator with the official MCP SDK; encrypted SQLite WAL ledger with an AWS outbox (DynamoDB, S3 SSE-KMS, EventBridge Scheduler, SQS, Secrets Manager, CloudWatch on EC2 via CloudFormation); deterministic commitment compiler and verifier policies; MediaPipe Pose and EfficientDet object detection with tracking on decoded video; Ring Partner API adapter (webhook HMAC, WHEP via aiortc); Bee SSE adapter; React/TypeScript judge console with Web Push companion alerts; Fire OS (Android TV) app with D-pad navigation. GitHub Actions CI: backend/MCP/security, Playwright journeys, APK build, container replay.

## What is real vs simulated (be explicit in the form)

- Live: AWS stack; hosted MCP server; Ring Partner API on the Ring Developer Playground device (WHEP live video decoded and relayed into Reality-Lock as LIVE RING); Bee developer API (verified live with a Bee device); real video inference on licensed recorded footage and a 15-squat workout video.
- Simulated and labelled: the canonical day's Bee utterances (fixtures), Ring-like synthetic scenes, the Alexa+ voice panel, the police receiver (`SIMULATED DISPATCH — NOT SENT`).
- Not available to the team: a physical Fire TV device (the Vega Virtual Device and an Android TV emulator are used), a real Alexa device (simulated experience over the real MCP server).

## AWS Builder mini challenge — services used

CloudFormation, EC2, Systems Manager, DynamoDB, S3, KMS, EventBridge Scheduler, SQS, Secrets Manager, CloudWatch. Per-promise T-60/T-25/deadline schedules are real EventBridge `at()` schedules targeting an encrypted SQS queue that wakes the reconciler; evidence and snapshots replicate to private SSE-KMS S3; contracts, agents, incidents and audit records project into DynamoDB. Bedrock Nova was attempted and returned "Operation not allowed" (see friction log). Evidence: `docs/evidence/aws-deployment.json`, `docs/evidence/aws-mcp-scheduler.json`.

## Open Source mini challenge

- Contribution URL: https://github.com/AmazonAppDev/devices-agent-skills/pull/16
- Fork: https://github.com/vivekyarra/devices-agent-skills/tree/add-evidence-backed-commitments
- Contribution: PR adding `skills/evidence-backed-commitments` to `AmazonAppDev/devices-agent-skills` (source: `packages/agent-skills/evidence-backed-commitments`, MIT).
- What it does: an Agent Skill that teaches coding agents to build assistants that never mark a task done without evidence — lifecycle state machines, a verification-policy matrix, MCP tool design for physical-world actions, Ring/Bee/Fire TV/Alexa+ constraints, plus a zero-dependency commitment compiler and a contract auditor.
- GitHub username: vivekyarra.

## Product feedback and friction log

Paste from [product-feedback.md](product-feedback.md) and [friction-log.md](friction-log.md) (Amazon-tool entries A1–A5 use the official format).

## Built during the hackathon window

The repository's first commit is dated 20 October 2026 and all code was written from then on. **OWNER:** confirm this falls inside the official submission window.

## Video storyboard (under 3:00)

| Time | Shot |
|---|---|
| 0:00–0:12 | Hook: "Today's assistants know what you said. DONE/IRL proves what happened." Live URL on screen. |
| 0:12–0:35 | Everyday promises spoken/typed → contracts appear with deadlines, triggers, recurrence; Alexa+ panel "what did I promise today?" with MCP log. |
| 0:35–0:58 | Courier claim → real-footage deposit vs fake-out; custody stays active; watchdog. |
| 0:58–1:15 | T-60 silent / T-25 active (phone push), meeting verified only by evidence. |
| 1:15–1:40 | Porch removal on real CCTV footage → evidence packet, family vs review report; nothing sent. |
| 1:40–1:55 | Arrival with drinks not visible → private check, no false accusation. |
| 1:55–2:35 | TV app (emulator/Vega) with D-pad → Reality-Lock: MediaPipe squats 14 locked → 15 unlocked. |
| 2:35–2:55 | AWS architecture + source labels + "never fake done" safeguards. |
| 2:55–3:00 | "DONE/IRL. APIs lie. Reality doesn't." |
