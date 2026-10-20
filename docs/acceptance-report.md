# DONE/IRL acceptance report

Date: **20 October 2026**. Target: **FULL_ORIGINAL_VISION_COMPLETE**. Verdict: **NOT COMPLETE**.

The implemented synthetic workflow runs end-to-end through a real shared transactional ledger. It is not a complete live-device product or a submission-ready hackathon entry. The engineering checks and the full product release gate are deliberately separate.

## Executed evidence

- Python domain/API/security suite: **65 passing tests**, including the regression rejecting one looped rep with renamed frame IDs. The generated JUnit file and hosted CI retain the actual counts. Tests cover four promises, ambiguity/negation, DST, teacher/sister schedules, restart, idempotency, pixel-derived deposit/removal, human-reviewed incidents, private media, tampering, consent, and fourteen-versus-fifteen cycles.
- External official MCP SDK client: initializes over TCP Streamable HTTP, discovers all five original tools, compiles a contract through the shared engine, reads the same REST state, and observes rejection of model-provided dispatch approval.
- React/TypeScript production build: passed. Browser suite: **4 passed**, including full canonical replay, adverse delivery, mobile/consent/D-pad preview, and a second authenticated TV tab reading shared state.
- Fire OS native APK: compiled successfully with Gradle 8.13/full JDK 21/Android 35; repeat build succeeded with outputs up to date. An APK build is not install/launch or device-runtime proof.
- Native MediaPipe CPU inference: official lite model SHA-256 recorded in `docs/evidence/mediapipe-negative.json`; a twenty-frame generated no-human video decoded successfully with zero counted reps. This is a negative model check, not human exercise accuracy or fifteen real squats.
- Real generated fifteen-second WebM removal video: 150 decoded frames at 10 FPS; original and annotated artifacts have distinct SHA-256 digests and parent-child provenance. This content is synthetic, never a live Ring recording.
- Hosted engineering CI on development commit `d7e55395ff9cbe489889f752b27e1f9c294c9356`: backend/MCP/security, browser and native APK jobs all passed ([run](https://github.com/vivekyarra/Amazon/actions/runs/39391975642)). Later commits must pass their own checks before promotion.

Generated artifacts: `artifacts/backend-results.xml`, `artifacts/playwright/results.xml`, `artifacts/screenshots/`, `artifacts/vision/mediapipe-negative-result.json`, native `app/build/outputs/apk/debug/`, and `artifacts/release/release-result.json`. Source-controlled screenshots under `docs/images` show the actual synthetic web UI. Build artifacts, credentials and databases stay ignored.

- Container: full image build, authenticated six-stage replay, evidence export, fifteen reps, restart durability and teardown passed; image digest is in `docs/evidence/container.json`. The cloud build preserves TLS/package signatures using the existing public CA bundle.
- Actual browser recording: `docs/demo/browser-demo.mp4`, **40.2 seconds**, captured from a real running synthetic session after login. It is not Fire TV runtime footage or an uploaded public submission video.

## Requirement determination

The [traceability map](requirements-traceability.md) and [machine manifest](acceptance-manifest.json) retain all 55 P0 criteria. **24 narrow local/synthetic behaviors have reproducible test references. 31 full criteria are blocked or require further proof.** Scoped test success does not establish original-device completion or independent release approval.

`./scripts/verify-release.sh` intentionally returns nonzero with `NOT_COMPLETE`. It requires all 55 criteria, actual primary-track runtime evidence and independent review. No report overrides the checker to manufacture completion.

## Remaining work

1. Authorized Bee device/SSE ingestion and real data provenance; documented account linking, access revocation and live ingestion wiring.
2. Ring device permissions, checked provider webhook/auth contract, actual WHEP decoder/secure video relay, bounded renewal/history reconciliation, real scene calibration and a general object detector/tracker validated on permitted footage. Calibrated colored-marker fixtures are not a general real-world vision model.
3. Positive human exercise video through MediaPipe, camera/body calibration, real fourteen-versus-fifteen evidence and synchronized TV playback. Generated marker cycles alone do not meet the human-video gate.
4. Actual Fire OS device/eligible simulator install, launch, four-view D-pad/lifecycle/video tests and recorded runtime proof. No Vega runtime has been tested.
5. Full AWS durable worker/queue/scheduler/object-store implementation and deployment, encrypted media, bounded history, backup-retention deletion and production operational/security review. The supported current deployment is a local single-service SQLite demo and explicitly refuses live mode.
6. Genuine Alexa+ account integration or independently eligible simulated-route proof, primary-track rules review, public under-three-minute video, owner submission, real tool feedback and independent release review. No official police receiver or cross-app TV locking API is available or claimed.

The original release target remains unchanged. The owner deferred device credentials/testing until later; independent implementation and engineering validation proceed without inventing live results.


## Live-runtime checkpoint, 20 October 2026

The backend suite now reaches **91 passing tests**, including encrypted retention, durable inbox/lease recovery, official Ring signatures/bindings, actual WebRTC codec loopback and eight Moto AWS-runtime tests. Updated APK and web builds pass. Actual public-reference MediaPipe inference counted one accepted rep in 363 frames; no fifteen-rep or genuine device acceptance is claimed. The WHEP relay and AWS implementation listed as absent above have now been implemented and locally tested, but actual provider/cloud/TV runtime proof remains unavailable. Current remaining work and exact handoff context supersede the earlier implementation list: see [continuation.md](continuation.md), [architecture.md](architecture.md), and [AWS guide](../infra/aws/README.md). Per-camera exclusions, adjustable retention and disconnect/delete workflows remain unimplemented. The full release gate still intentionally fails.
