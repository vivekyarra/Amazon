# Acceptance report

Dated 20 October 2026. Produced from `scripts/verify-release.py`, the [acceptance manifest](acceptance-manifest.json) and the evidence linked below. This is an engineering self-assessment; the spec's independent release review (P0-055) has **not** happened.

```text
DONE/IRL Release Report
-----------------------
Target: FULL_ORIGINAL_VISION_COMPLETE (unchanged; see release-target.md)
Verdict: NOT_COMPLETE
Commit: feat/completion head at time of writing (see git log); CI run 39425459386 green on f7d996c
Primary track: Alexa+ — self-hosted MCP Streamable HTTP (2025-11-25) live on hosted HTTPS + labelled simulated Alexa+ web experience
P0 verified: 34/55 (9 BLOCKED, 12 IMPLEMENTED_UNVERIFIED) — requirements-traceability.md
Automated tests: backend pytest 176 passed (full suite incl. real-video scene/pose, Windows 11); CI 4/4 jobs green; Playwright journeys in CI
Fire TV device/simulator: Android TV API 30 emulator, Fire OS APK, 33/33 D-pad checks (tests/firetv/device-report.md); physical Fire TV untested; Vega Virtual Device in progress
Bee: BLOCKED (adapter + redacted probe ready; no BEE_TOKEN run yet); canonical day uses SIMULATED_VERIFIED fixtures
Alexa+/MCP: LIVE_VERIFIED MCP server (hosted initialize + tool call); Alexa+ device NOT_CONNECTED; simulated experience SIMULATED_VERIFIED
Ring: BLOCKED live (adapter, webhook HMAC, WHEP decode, redacted probe ready); recorded real-scene vision verified on licensed footage
AWS: LIVE_VERIFIED (DynamoDB, S3 SSE-KMS, EventBridge Scheduler, SQS, Secrets Manager, CloudWatch, EC2/SSM)
Incident reporting: DEMO_MOCK (SIMULATED DISPATCH — NOT SENT TO POLICE); export available
6-scenario full replay: PASS (local, CI and hosted AWS)
Adversarial branches: PASS (fake deposit, removal, family pickup, report review, visible/empty/occluded, real_* footage branches)
Security/consent: PASS (household isolation, forged webhook, tampering, consent revocation, privacy controls, MCP host/origin/auth)
Submission: NOT_READY (public video and Devpost entry need the owner's accounts)
```

## Remaining known blockers (literal)

1. Live Bee data through a real device/account (P0-008) — needs the owner's `BEE_TOKEN`.
2. Live Ring camera / simulator API run, WHEP video into the TV (P0-018, P0-019, P0-038) — needs a Playground token and an authorized device.
3. Fire OS **device** or **Vega Virtual Device** run (P0-036, P0-047 device test in CI).
4. Recorded-Ring threshold path (P0-032) and Ring-backed watchdog reconciliation (P0-022) beyond recorded stock footage.
5. Public under-three-minute video and Devpost submission (P0-048, P0-050, P0-051), Open Source PR link (P0-052).
6. Remaining engineering hardening rows (P0-004, P0-006, P0-007, P0-027, P0-029, P0-044, P0-045, P0-054) need live-provider faults or device views to be exercised.
7. Independent release review (P0-055).

## Proof

- Hosted: https://100-49-183-59.sslip.io · [AWS smoke](evidence/aws-deployment.json) · [MCP + EventBridge](evidence/aws-mcp-scheduler.json)
- Vision: [scene-vision.json](evidence/scene-vision.json), [annotated frames](evidence/scene/)
- Pose: [pose-15-fixture.json](evidence/pose-15-fixture.json), [annotated clip](evidence/pose-15-annotated.mp4)
- TV: [device report](../tests/firetv/device-report.md), [walkthrough](evidence/firetv/walkthrough.mp4)
- MCP: [external client](evidence/mcp-external-client.json), [Inspector CLI](evidence/mcp-inspector-cli.json)
- CI: [ci-runs.md](evidence/ci-runs.md)

The product never marks a contract VERIFIED without policy-matching evidence; the golden end state deliberately leaves the sister call, drinks and parcel custody unresolved.
