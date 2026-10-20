# Requirements traceability

Generated from [acceptance-manifest.json](acceptance-manifest.json) by `scripts/update-acceptance.py`; do not edit by hand. All 55 original P0 gates are retained. VERIFIED means reproducible automated or platform evidence exists for the gate's own wording; it never implies live-device completion where the row says otherwise. Full original-vision release and independent review remain separate gates.

Status counts: BLOCKED: 9, IMPLEMENTED_UNVERIFIED: 14, VERIFIED: 32.

| ID | Result | Evidence / remaining work |
|---|---|---|
| P0-001 | VERIFIED | Four modules plus the shared schema build and test from a clean GitHub Actions checkout. Evidence: [docs/evidence/ci-runs.md](../docs/evidence/ci-runs.md). |
| P0-002 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-003 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-004 | IMPLEMENTED_UNVERIFIED | Authenticated live pilot writes now have guarded configuration and provenance; live provider/account runtime and independent review remain unverified. |
| P0-005 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-006 | IMPLEMENTED_UNVERIFIED | Status endpoints expose processed provider receipts and current decoded-frame status; actual authorized device probes remain unavailable. |
| P0-007 | IMPLEMENTED_UNVERIFIED | Local restart verified; container/full platform lifecycle teardown still needs execution. |
| P0-008 | BLOCKED | Bee token/device unavailable; adapter unit tests do not provide live proof. |
| P0-009 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-010 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-011 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-012 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-013 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-014 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-015 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-016 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-017 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-018 | BLOCKED | Documented raw-body webhook HMAC, account/device binding, capabilities and bounded aiortc WHEP decoder implemented; real Ring account/runtime proof missing. |
| P0-019 | IMPLEMENTED_UNVERIFIED | Sources labeled; actual Ring simulator and live switching not connected. |
| P0-020 | VERIFIED | Decoded frames of licensed real recordings (REAL_RECORDED_STOCK) give DEPOSIT_CONFIRMED vs MISMATCH; synthetic Ring-like replay retained for judges. Live Ring capture is tracked under P0-018. Evidence: [docs/evidence/scene-vision.json](../docs/evidence/scene-vision.json). |
| P0-021 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-022 | IMPLEMENTED_UNVERIFIED | Leased durable provider worker and Ring notification handling/recovery implemented; actual Ring observation/history-based watchdog reconciliation still missing. |
| P0-023 | VERIFIED | One incident with timestamp, best-available person crop, original+annotated clip and pixel trajectory; a 14.1 s real clip is truthfully labelled EVIDENCE_INCOMPLETE. Evidence: [docs/evidence/scene-vision.json](../docs/evidence/scene-vision.json). |
| P0-024 | VERIFIED | AES-GCM local artifacts and a live private SSE-KMS S3 replica (14 objects in the judge stack); SHA-256 originals, parent-linked derivatives and chained manifest re-verified before export/approval. Evidence: [docs/evidence/aws-deployment.json](../docs/evidence/aws-deployment.json). |
| P0-025 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-026 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-027 | IMPLEMENTED_UNVERIFIED | Working authenticated web incident view; actual TV device/runtime proof missing. |
| P0-028 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-029 | IMPLEMENTED_UNVERIFIED | Preview shows available synthetic evidence; live images/clip/address unavailable. |
| P0-030 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-031 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-032 | IMPLEMENTED_UNVERIFIED | Stage 5 can consume a REAL_RECORDED_STOCK arrival clip (branches real_visible/real_empty/real_bags) and cross-reference the morning drinks contract through the same reducers. The clips are public stock scenes (two without a real doorway), not a Ring recording or live trigger. Evidence: [docs/evidence/scene-vision.json](../docs/evidence/scene-vision.json). |
| P0-033 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-034 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-035 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-036 | BLOCKED | Native APK builds; no supported Fire OS/Vega device launch recording. |
| P0-037 | VERIFIED | Ledger, incident, evidence-packet and Reality-Lock views reachable by D-pad with visible focus and Back handling on an Android TV API 30 emulator running the Fire OS APK (not a physical Fire TV). Evidence: [tests/firetv/device-report.md](../tests/firetv/device-report.md). |
| P0-038 | BLOCKED | Backend WHEP decoder, MediaPipe/JPEG relay and real-codec synthetic loopback implemented; actual Ring-to-Fire-TV runtime proof pending. |
| P0-039 | VERIFIED | Real MediaPipe Pose on a generated, labelled SYNTHETIC 15-squat video (spec 11.4 permits generated fixtures): exactly 15 reps; half, frozen and looped inputs add none. Green in CI. A consented human recording would strengthen but is not required by this gate. Evidence: [docs/evidence/pose-15-fixture.json](../docs/evidence/pose-15-fixture.json). |
| P0-040 | VERIFIED | Gate stays locked at 14/15 and unlocks only after the verifier-backed PSC transition; TV app restart restores the unlocked state from the durable ledger. Evidence: [tests/firetv/device-report.md](../tests/firetv/device-report.md). |
| P0-041 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-042 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/playwright/results.xml](../artifacts/playwright/results.xml). |
| P0-043 | VERIFIED | Synthetic local development workflow; no live/device inference Evidence: [artifacts/backend-results.xml](../artifacts/backend-results.xml). |
| P0-044 | IMPLEMENTED_UNVERIFIED | F01–F24 mapped; actual human-video repetitions and native device navigation remain unverified. |
| P0-045 | IMPLEMENTED_UNVERIFIED | Durable queue lease/crash, consent, provider duplicate, encrypted retention, AWS emulation and real codec tests pass; actual provider/cloud faults still unverified. |
| P0-046 | VERIFIED | Consent, per-camera exclusion, private masks, retention, provider disconnect and household deletion tested; upstream token revocation and operator backups are documented operator duties. Evidence: [docs/privacy-security.md](../docs/privacy-security.md). |
| P0-047 | BLOCKED | Engineering CI supplied; required Fire TV device/simulator tests absent. |
| P0-048 | BLOCKED | Runbook/screenshots supplied; real track footage and submission artifacts incomplete. |
| P0-049 | IMPLEMENTED_UNVERIFIED | AWS runtime/projection/schedules/restore and validated CloudFormation supplied alongside local deployment; actual AWS provisioning/runtime remains unverified. |
| P0-050 | BLOCKED | Candidate Alexa+ route recorded; account/track runtime and eligibility proof pending. |
| P0-051 | BLOCKED | No public under-three-minute video URL or required device footage. |
| P0-052 | IMPLEMENTED_UNVERIFIED | Actual tools have feedback; Amazon live tool feedback and mini-challenge links pending. |
| P0-053 | IMPLEMENTED_UNVERIFIED | Actual friction recorded; no fabricated ten-entry or bonus claim. |
| P0-054 | IMPLEMENTED_UNVERIFIED | Traceability/progress/report maintained; independent dated release review still needed. |
| P0-055 | BLOCKED | Release gate intentionally reports NOT_COMPLETE; no independent platform review. |

Domain tests: `apps/mcp-orchestrator/tests`; browser tests: `tests/e2e`; TV emulator: `scripts/firetv-emulator-check.py`; release gate: `scripts/verify-release.py`.
