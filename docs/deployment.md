# Operations and deployment

## Verified local pathway

Run `scripts/setup-local.sh`, then `scripts/start-local.sh` from the repository. `/health/live` checks process liveness; `/health/ready` checks SQLite access. Both responses identify the synthetic development mode. Run `scripts/access.sh` only in a private terminal. Sessions and state live in the ignored `.local` directory; keep it on a protected encrypted volume if storing anything sensitive. Stop the server with Ctrl-C, restart with the same DATA_DIR and verify the persisted ledger. Never start a second worker against a different database and call that synchronized state.

Each cloud task is already isolated: use the existing checkout; no extra Git worktree is required. Live processes do not survive environment publication/restoration, so restart the service in each task. Dependency caches and the built frontend may survive; validate them before reuse.

## Container pathway (build, full replay and restart verified)

```bash
docker compose -f infra/local/compose.yml up --build -d
docker compose -f infra/local/compose.yml exec done-irl cat /data/access.json
# The previous command is for a private terminal only. Do not record its output.
docker compose -f infra/local/compose.yml down
# Add --volumes only when deliberately deleting ALL local demo data.
```

Docker is optional. The image was built and tested with all six scenarios, fifteen distinct pose cycles, evidence export, service restart, persisted contracts and teardown. See `docs/evidence/container.json`. Build with `docker build -f infra/local/Dockerfile -t done-irl:validation .`; then `uv run python scripts/smoke-container.py` validates an isolated container and removes only its own container/volume. Standard Compose can be used on a normal network. The local image defaults to synthetic mode. The public judge deployment on AWS is described in `infra/aws/README.md` (`judge-demo.yaml`). Put an owner-controlled TLS reverse proxy in front of any remote demo, restrict access, set ALLOWED_ORIGINS to the actual origin, and protect passwords. Do not expose the judge workspace anonymously.

## Fire OS client

See `apps/firetv-command-hud/README.md`. The APK builds in CI and runs on an Android TV API 30 emulator in CI (`scripts/firetv-emulator-check.py`, [report](../tests/firetv/device-report.md)); the Vega OS app ran on the Vega Virtual Device ([report](../tests/firetv/vega-device-report.md)). A physical Fire TV run and in-app video playback are still unverified.

## Runtime observability

Health responses disclose storage/mode without secrets. The judge event inspector correlates intake, contract revisions, schedule decisions, evidence, consent and incidents with trace IDs. Do not use access logs to store transcript content. The UI lists source failures and logical observation gaps. Inspect persisted `scheduled_jobs` and `subagents` after a restart; a WATCHING watchdog means a logical job, not continuously observed pixels. The synthetic workflow requires explicit clock advances; it does not claim wall-clock live scheduling.

For rollback, stop the server, take a consistent SQLite backup (SQLite backup API, not an arbitrary copy during writes), preserve the encrypted volume and deploy the previous source commit. No migrations beyond CREATE TABLE IF NOT EXISTS exist yet. Restore into a separate protected DATA_DIR and validate health/ledger before routing users.

## Lifecycle workflows

Startup, failure, reconnect, resume and teardown are mapped to their documentation and tests in [write-and-degradation-matrix.md](evidence/write-and-degradation-matrix.md#p0-007-lifecycle).

## Before real AWS/live deployment

Provisioning DynamoDB/SQS/EventBridge/S3/IAM, encrypted media retention, signed user-scoped media URLs, backup deletion, real-time scheduler workers, token rotation/account linking, webhook signature contracts, Ring WHEP decoding/relay, camera calibration, consent revocation propagation, retry/DLQ and resource limits remain open. The judge stack `done-irl-judge` is deployed ([evidence](evidence/aws-deployment.json)); no official report receiver exists. The items above remain open for a production household deployment.


## Updated live/AWS pilot

The original synthetic deployment remains the default. A guarded live pilot, WHEP/MediaPipe relay and optional AWS runtime are now implemented; use [infra/aws/README.md](../infra/aws/README.md) for the current template, security configuration, backup/restore, retention, teardown and limitations. The judge stack was deployed and smoke-tested ([evidence](evidence/aws-deployment.json)); its teardown is documented but has not been executed because it must stay up through judging. New encrypted storage is not compatible with rolling back to the old plaintext implementation without an explicit migration plan. Keep the original key and consistent backups; never replace a missing encryption key with a new random key.
