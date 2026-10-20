# DONE/IRL

**APIs lie. Reality doesn’t.** A durable reality ledger that turns consented commitments into evidence-backed outcomes.

DONE/IRL connects the morning promise, the parcel on the porch, the meeting you need to attend, and the movement before your evening TV. It keeps reminders separate from completion, custody separate from delivery, and observation separate from accusation.

> **Current release: working synthetic development demo; original vision NOT COMPLETE.** Bee/Ring/Fire TV live verification and official hackathon submission evidence remain external gates. See [acceptance report](docs/acceptance-report.md) and [integration status](docs/integration-status.md). An Android build is not proof of a Fire TV device run.

![Mission control — actual synthetic web workspace](docs/images/mission-control.png)

[Watch the actual 40-second synthetic browser demo](docs/demo/browser-demo.mp4) · [Validation evidence](docs/evidence/engineering.json)

## Run locally

Requires Linux/macOS, Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 22.12+ (24 recommended), and npm. Linux OpenCV requires the standard GL/glib runtime (`libgl1`, `libglib2.0-0` on Debian/Ubuntu); the optional MediaPipe worker also needs `libgles2`. No personal camera, cloud account, Docker, or device token is required for the synthetic workflow.

```bash
./scripts/setup-local.sh
./scripts/start-local.sh
```

The service listens on port 8080 by default and serves the built frontend and API together. In a private terminal, run `./scripts/access.sh` to read the generated `demo-admin` and `owner` passwords. Never include that output in a public issue, video, or CI log. Passwords and local state are ignored by Git. The administrator uses the isolated synthetic household; ordinary owners cannot invoke replay controls.

For frontend development, run the backend and `npm run dev` separately. Vite proxies `/api` to the backend.

## Try the connected day

1. Sign in as `demo-admin`. Choose **Run the full day** in Mission control.
2. Four morning utterances compile into four durable contracts. Nothing starts verified.
3. The synthetic camera sees the parcel deposited; one persistent PorchWatchdog starts. Custody stays pending.
4. Teacher T−60/T−25 jobs execute; a separate authorized synthetic meeting transcript verifies attendance.
5. A removal opens a human-review incident with real generated snapshots and SHA-256 hashes. It sends no police report.
6. Arrival with drinks not visible requests a user check. It never proves the drinks are absent.
7. Studio processes generated marker pixels into landmarks and 15 complete movement cycles. The in-app gate opens. This is synthetic geometry, not a certified human fitness detector.

Use **Judge replay** to choose fake delivery, engaged meeting preparation, authorized family pickup, a parcel that remains, visible drinks, or occluded hands. Reset before rewinding or changing an already played branch. Inspect contract provenance, event JSON, schedules, and evidence. The sister call stays unresolved until independently supplied proof. Browser tabs and the TV preview read the same database.

## Verification

```bash
uv run ruff check apps/mcp-orchestrator
uv run pytest -q --junitxml=artifacts/backend-results.xml
npm run build
# Uses /usr/bin/chromium when present, otherwise Playwright's Chromium. E2E_PORT overrides port 8091.
npm run test:e2e
./scripts/verify-release.sh  # expected nonzero while original-vision gates are unresolved
```

Tests exercise exact scheduling, durable restart, evidence tampering, household isolation, owner approval, compiler ambiguity, source failures, pixel-based synthetic vision, fourteen-versus-fifteen reps, browser journeys, and an external MCP SDK client over TCP. A green engineering CI is distinct from a complete product release. Generated logs, screenshots, databases, caches and APKs stay out of the source tree history; CI publishes test artifacts separately.

## Surfaces and modules

| Module | Implementation |
|---|---|
| `apps/mcp-orchestrator` | FastAPI, official MCP SDK Streamable HTTP, SQLite WAL, deterministic domain policies, backend adapters |
| `apps/vision-webrtc-engine` | Vision worker and source documentation; shared pixel/pose engine in orchestrator package |
| `apps/firetv-command-hud` | Native Fire OS Android TV shell; shared authenticated four-view web HUD |
| `apps/judge-godmode-console` | React + TypeScript judge console, companion inbox, keyboard TV preview |
| `packages/physical-contract-schema` | Shared TypeScript contracts and generated JSON schemas |
| `packages/testing-fixtures` | Synthetic source manifest and reproducible geometric fixtures |

Fire OS build/install and runtime validation are described in [TV instructions](apps/firetv-command-hud/README.md). Web TV mode is explicitly a preview. The primary candidate track is Alexa+ via compliant MCP/simulated orchestration, pending actual eligibility review and recorded proof; other track claims require their device evidence.

## Simulated Alexa+ experience

There is **no real Alexa device or Alexa+ account connection**. Under the hackathon's simulated-Alexa+ entry route, the **Judge replay** page includes a panel labeled **SIMULATED ALEXA+ — not an Alexa device**:

- Speak (browser Web Speech API, where available) or type, e.g. "Alexa, what did I promise today?", "Alexa, is my parcel safe?", "Alexa, start Reality-Lock", "Alexa, did I call my sister?", "Alexa, report it to the police", "Alexa, are my devices connected?", "Alexa, remember I'll call my sister before 6 PM".
- A deterministic router (fixed rules, no LLM) maps each request to MCP tool calls made from the browser as real JSON-RPC to the same-origin, authenticated `/mcp/` endpoint (`initialize` → `tools/call`). The panel's right rail shows every request/response.
- Answers are built only from tool results and are read aloud with `speechSynthesis`; each carries the simulation badge. T-25 escalation and arrival-check alerts from the shared ledger appear as a **SIMULATED WHISPER — not delivered to any device**, using the spec 5.4 copy.
- Voice cannot verify a promise or file a report: `dispatch_police_evidence_dossier` always returns `DENIED` (audited) and the live Ring→Fire TV bridge reports `BLOCKED` in demo mode.

External MCP proof (official Python SDK client over real HTTP, plus the MCP Inspector CLI):

```bash
uv run --extra ring-video --extra aws python scripts/mcp-external-client.py --inspector
# -> docs/evidence/mcp-external-client.json, docs/evidence/mcp-inspector-cli.json (credentials redacted)
```

## Safety and privacy

No browser receives a Bee/Ring/AWS credential. All state and evidence routes require household-scoped authentication. API writes require an idempotency key. Cookies are HttpOnly/SameSite; HTTPS enables Secure cookies. The server validates origins and rate-limits commands. Live pilot startup requires an explicitly provisioned encryption key, HTTPS origins and strong owner-only credentials; actual integration/runtime certification remains pending. Simulated incident approval is bound to the exact manifest and destination; a tool’s `human_confirmed_boolean` cannot authorize dispatch. There is no official police adapter or cross-app TV lock.

See [architecture](docs/architecture.md), [privacy](docs/privacy-security.md), [deployment](docs/deployment.md), [judge runbook](docs/judge-runbook.md), and the [original product specification](docs/product-spec.md).

## Repository workflow

Work is developed on feature branches (`feat/done-irl`, then `feat/live-runtime`). CI must pass on the exact release commit before promotion to `main`. Credentials, local outputs, vendor directories, APKs and generated build bundles are ignored. Publication, third-party device registration, and submission video uploads need owner-controlled accounts and are not inferred from a passing local test.


## Live runtime and AWS pilot

The optional runtime includes an encrypted durable provider inbox, wall-clock deadline worker, documented Ring webhook signatures, a backend WHEP decoder/MediaPipe/JPEG relay, and optional AWS outbox replication, DynamoDB projections, private S3 evidence, EventBridge Scheduler/SQS and hash-checked snapshot recovery. New live households require explicit consent; no demo administrator exists in this mode. Actual Bee/Ring/Alexa/Fire TV account and device acceptance is still outstanding.

See [AWS provisioning and operations](infra/aws/README.md), [current architecture](docs/architecture.md), [integration proof](docs/integration-status.md) and [public reference attribution](docs/public-references.md). Install optional runtime dependencies with `uv sync --frozen --extra ring-video --extra aws`; run backend checks with the same extras to exercise real WebRTC codec loopback. Build the live container with `--build-arg ENABLE_LIVE_RUNTIME=true`. Local AWS emulation and template lint are not evidence of an actual deployment.
