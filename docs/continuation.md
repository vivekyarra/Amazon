# Continuation checkpoint — 20 October 2026

The owner requested a checkpoint and push to main before continuing in another session. **Original target remains FULL_ORIGINAL_VISION_COMPLETE; current verdict is NOT COMPLETE.** Do not replace it with demo completion or tick unverified device criteria. This document is implementation context, not permission to override the owner's later instructions.

## Repository and delivery

- Repository: `vivekyarra/Amazon`, working directory `/workspace/Amazon`.
- Previous green main: `752d01d3850eb0e7f5c1f352c7f177996c318f28`, CI https://github.com/vivekyarra/Amazon/actions/runs/39395072078.
- This work is on `feat/live-runtime`; the owner subsequently requested an immediate checkpoint push without waiting for checks. Save the feature branch and main now; inspect the new commit’s hosted CI first when resuming. Keep generated outputs, dependencies, databases, private credentials and downloaded reference videos ignored.
- GitHub currently has `feat/done-irl` as its default branch. Updating repository settings returned 403 for this integration; pushing main works. Owner/admin must change the GitHub default branch later.
- User authorizes autonomous implementation, branch pushes and main promotion after green checks, and will supply device credentials/testing later. Actual laptop-control tools are unavailable. Do not claim a task will run overnight after this session closes.

## Implemented in this checkpoint

1. AES-256-GCM encryption for household aggregates, command responses, provider inbox payloads and artifacts; identity/household-associated data; private key permissions; legacy plaintext upgrade guarded by explicit opt-in; missing keys fail closed.
2. Durable provider inbox with identity/payload-conflict detection, recoverable leases, atomic reducer/ack commits, retries/dead events, cursor persistence and consent cancellation. Wall-clock worker operates separately from the deterministic virtual demo clock. Physical local artifact retention deletes bytes and keeps manifest tombstones.
3. Ring webhook verification corrected against current official docs: `X-Signature: sha256=<HMAC_SHA256(raw_body)>`, JSON:API v1.1, account/device bindings, durable request IDs, no false physical conclusion from motion. Provider notification history prevents duplicate observations after snapshot restore.
4. Ring WHEP receive-only negotiation, capability check, gathered ICE/STUN, actual aiortc decode, SHA-pinned MediaPipe inference, authenticated annotated JPEG relay, server-only credentials/SDP, 30/60-second cleanup, consent stop, reconnect preserving rep count and rejecting duplicate video/pose frames. Real WebRTC codec loopback test passes using explicitly generated video, not actual Ring.
5. Guarded live pilot mode requires HTTPS origins, a separately provisioned 32-byte key, strong owner-only passwords and opt-in collection. New pilot accounts start with consent disabled. It is not production-certified. Synthetic admin routes remain isolated.
6. Optional AWS transactional outbox, conditional DynamoDB projections, encrypted private S3 media/snapshots, EventBridge/SQS wakeups, expiry deletion of all media versions, immutable retries, daily backup refresh, error retries/readiness and hash-checked restore. Eight Moto tests cover these paths. S3 restore recovers state/media, not sessions, command cache or inbox leases. Complete local recovery still uses EBS/SQLite backups.
7. CloudFormation template provisions one EC2 reducer behind HTTPS, encrypted EBS, DynamoDB/PITR, S3/KMS, Scheduler/SQS/DLQ, scoped IAM, secret bootstrap, logs and alarms. `cfn-lint==1.57.2` passes. Actual AWS deployment has not run. Guide: `infra/aws/README.md`.
8. Native Fire OS shell now has distinct evidence-packet navigation. TV session registration is household-scoped/bounded and explicitly does not attest device runtime. MCP owner-input compilation is available with honest provenance; the camera tool can open a relay for an authorized registered TV session. Live UI offers configured cameras and source labels.
9. Actual MediaPipe inference processed a pinned public MIT-licensed 14.52-second reference video: 363 frames, **one accepted rep**, about 47 CPU FPS in this environment. It does not satisfy fifteen-rep acceptance. Attribution: `docs/public-references.md`; summary: `docs/evidence/mediapipe-public-reference.json`; reproduction: `scripts/check-public-pose.py`.

## Verified and pending validation

The backend suite reached **91 passing tests** before the final checkpoint run. The TypeScript/Vite build and updated native Gradle APK build passed. Final backend/browser/container results and hosted CI are recorded by the checkpoint delivery. Existing `.local/e2e` had a legacy plaintext database, so its first new E2E run needs explicit `ALLOW_LEGACY_LEDGER_MIGRATION=true`; do not use that option to bypass a missing key for encrypted data. Fresh CI uses a new database/key.

The engineering CI has backend/MCP/security/real-codec/Moto checks, browser journeys, native APK build, and container replay/restart smoke tests. A green CI is not full product acceptance. `scripts/verify-release.py` must continue returning NOT_COMPLETE while live/track/independent gates remain unresolved.

## Resume priorities — actual remaining work

- Implement per-camera privacy exclusions, adjustable retention, provider disconnect and household deletion workflows; these are still explicitly absent. Review encryption migration/backups/key rotation and production security independently.
- Implement a real-scene parcel/deposit/removal/drinks detector/tracker with permitted positive/negative video fixtures. Current scene vision uses calibrated colored shapes only. Motion notifications cannot substitute for visual proof. Record evidence gaps truthfully.
- Verify/normalize actual Bee event envelopes and add relevant conversation evidence auditing. The current normalizer accepts typed BeeInput envelopes and refuses to guess undocumented shapes. Implement authorized OAuth/account linking/token refresh and camera history reconciliation where supported.
- Obtain a genuine non-repeated fifteen-human-squat fixture; validate full/partial/occluded/replayed variants through actual MediaPipe. Do not loop the public one-rep reference to manufacture acceptance. Confirm source labels/proof and camera-model quality on real equipment.
- Test actual Ring credentials/camera through the new WHEP path, including NAT/ICE, capabilities, expiry, cleanup, loss, reconnect and real client playback. No actual Ring connection has been observed.
- Install/launch the APK on a supported Fire OS device/eligible simulator; exercise all four views with D-pad, lifecycle, video and durable 14/15 vs15/15. Browser TV preview and APK build are not device-runtime proof.
- Deploy/test AWS with an owner-controlled identity, network, ACM/DNS, ECR image and private secret. One active reducer only. Validate restore, IAM, queue redrive, schedules, retention and operational alarms. The template has no automatic failover.
- Verify Alexa+ primary-track eligibility/account runtime, capture actual device footage, produce/upload a public under-three-minute video through owner-controlled accounts, complete truthful tool feedback/submission and independent review. No public submission video exists.
- Review all 55 criteria and keep `docs/requirements-traceability.md`, `docs/acceptance-manifest.json`, `docs/progress.md`, `docs/integration-status.md` and `docs/acceptance-report.md` synchronized. Do not mark original-device requirements verified from mocks.

## Cloud environment notes

- Node24, Python3.12, uv0.11, `/usr/bin/chromium`, ffmpeg, Docker and gh are available. Set `UV_CACHE_DIR=/workspace/.cache/uv`, `npm_config_cache=/workspace/.cache/npm`; root home is read-only. For uvx also set `UV_TOOL_DIR=/workspace/.tools/uv`, `UV_TOOL_BIN_DIR=/workspace/.tools/bin`.
- `.venv` supports optional extras via `uv sync --frozen --extra ring-video --extra aws`. Always use those extras when running codec tests; plain uv run can remove optional packages. Avoid dependency mutations during running tests. `UV_NO_SYNC=1` can preserve the prepared environment for Playwright's backend.
- Full Android/JDK/Gradle setup is preserved in `/workspace/.tools`; `scripts/build-tv-cloud.sh` uses it and preserves proxy/TLS trust.
- Local MediaPipe needs extracted Debian GLES libraries: `LD_LIBRARY_PATH=/workspace/.tools/vision-libs/usr/lib/x86_64-linux-gnu`, `MPLCONFIGDIR=/workspace/.cache/matplotlib`, `XDG_CACHE_HOME=/workspace/.cache`. Official lite model: `/workspace/.tools/pose_landmarker_lite.task`, SHA-256 in docs/env examples.
- Cloud Docker build helper preserves proxy DNS/public CA trust: `python scripts/build-container-cloud.py --live-runtime --tag done-irl:live-validation`. Standard builds use `infra/local/Dockerfile`; optional runtime flag includes aws/ring-video extras. Test via `scripts/smoke-container.py` (see its image argument). No credentials or proxy CA are copied into the repo/image.
- Original master spec is preserved as `docs/product-spec.md`; uploaded original remains in `/workspace/attachments/a1b43a24-fdfb-46c5-a0c6-d497c24d26bc/`.
- Earlier onboarding saved a reviewable cloud config draft pinned to the previous commit; if config tools remain available, update its repository pin to the new final main SHA. No draft publication was claimed. Setup skill was read earlier; later platform update says no cloud skills currently available.
- No AWS/Bee/Ring/YouTube/Devpost credentials were supplied. Never print secret values, bootstrap passwords or entire environment contents. GitHub push/API integration works; repository admin settings are restricted.
