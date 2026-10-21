# Acceptance report

Dated 20 October 2026. Produced from `scripts/verify-release.py`, the [acceptance manifest](acceptance-manifest.json) and the evidence linked below. This is an engineering self-assessment; the spec's independent release review (P0-055) has **not** happened.

```text
DONE/IRL Release Report
-----------------------
Target: FULL_ORIGINAL_VISION_COMPLETE (unchanged; see release-target.md)
Verdict: NOT_COMPLETE
Commit: feat/completion head at time of writing (see git log); CI run 39425459386 green on f7d996c
Primary track: Alexa+ — self-hosted MCP Streamable HTTP (2025-11-25) live on hosted HTTPS + labelled simulated Alexa+ web experience
P0 verified: 41/55 (3 BLOCKED, 11 IMPLEMENTED_UNVERIFIED) — requirements-traceability.md
Automated tests: backend pytest 211 passed (incl. real-video scene/pose and 27 QA regressions); Playwright 5/5; CI 5/5 jobs green incl. Android TV emulator D-pad journey
Fire TV device/simulator: Vega OS app on the official Vega Virtual Device (tests/firetv/vega-device-report.md) and Fire OS APK on an Android TV API 30 emulator (33/33, in CI); physical Fire TV untested
Bee: LIVE_VERIFIED (owner-attested run with a borrowed Bee device; no artifact retained); canonical judge day uses scripted Bee fixtures
Alexa+/MCP: LIVE_VERIFIED MCP server (hosted initialize + tool call); Alexa+ device NOT_CONNECTED; simulated experience SIMULATED_VERIFIED
Ring: LIVE_VERIFIED on the Ring Developer Playground device (discovery, capabilities, history, WHEP 720p decode, live Reality-Lock relay); real-scene vision verified on licensed footage
AWS: LIVE_VERIFIED (DynamoDB, S3 SSE-KMS, EventBridge Scheduler, SQS, Secrets Manager, CloudWatch, EC2/SSM)
Incident reporting: DEMO_MOCK (SIMULATED DISPATCH — NOT SENT TO POLICE); export available
6-scenario full replay: PASS (local, CI and hosted AWS)
Adversarial branches: PASS (fake deposit, removal, family pickup, report review, visible/empty/occluded, real_* footage branches)
Security/consent: PASS (household isolation, forged webhook, tampering, consent revocation, privacy controls, MCP host/origin/auth)
Submission: NOT_READY (public video and Devpost entry need the owner's accounts)
```

## Remaining known blockers (literal)

1. Bee: owner-attested only (no retained artifact); re-run `scripts/bee-live-probe.py` with a token to add one.
2. Ring: live source switching under token expiry (P0-019) and history-based watchdog reconciliation (P0-022) not exercised live; Playground tokens last ~30 minutes.
3. Physical Fire TV device run (simulator/emulator runs done: P0-036, P0-047).
4. Recorded-Ring threshold path (P0-032) and Ring-backed watchdog reconciliation (P0-022) beyond recorded stock footage.
5. Public under-three-minute video upload and Devpost submission (P0-048, P0-051). Open Source PR: https://github.com/AmazonAppDev/devices-agent-skills/pull/16.
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
