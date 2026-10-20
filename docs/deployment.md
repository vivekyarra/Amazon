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

Docker is optional. The image was built and tested with all six scenarios, fifteen distinct pose cycles, evidence export, service restart, persisted contracts and teardown. See `docs/evidence/container.json`. In the supplied cloud proxy environment, use `python scripts/build-container-cloud.py` to preserve the proxy route and public CA trust; then `.venv/bin/python scripts/smoke-container.py` validates an isolated container and removes only its own container/volume. Standard Compose can be used on a normal network. The image exposes only the synthetic mode; it is not an AWS deployment. Put an owner-controlled TLS reverse proxy in front of any remote demo, restrict access, set ALLOWED_ORIGINS to the actual origin, and protect passwords. Do not expose the judge workspace anonymously.

## Fire OS client

See `apps/firetv-command-hud/README.md`. APK compilation, install/launch, D-pad behavior, lifecycle and video playback are separate evidence gates. Device runtime proof is still needed.

## Runtime observability

Health responses disclose storage/mode without secrets. The judge event inspector correlates intake, contract revisions, schedule decisions, evidence, consent and incidents with trace IDs. Do not use access logs to store transcript content. The UI lists source failures and logical observation gaps. Inspect persisted `scheduled_jobs` and `subagents` after a restart; a WATCHING watchdog means a logical job, not continuously observed pixels. The synthetic workflow requires explicit clock advances; it does not claim wall-clock live scheduling.

For rollback, stop the server, take a consistent SQLite backup (SQLite backup API, not an arbitrary copy during writes), preserve the encrypted volume and deploy the previous source commit. No migrations beyond CREATE TABLE IF NOT EXISTS exist yet. Restore into a separate protected DATA_DIR and validate health/ledger before routing users.

## Before real AWS/live deployment

Provisioning DynamoDB/SQS/EventBridge/S3/IAM, encrypted media retention, signed user-scoped media URLs, backup deletion, real-time scheduler workers, token rotation/account linking, webhook signature contracts, Ring WHEP decoding/relay, camera calibration, consent revocation propagation, retry/DLQ and resource limits remain open. No cloud deployment or official report receiver has been created. Do not add AWS mini-challenge claims until actual AWS usage is demonstrated.


## Updated live/AWS pilot

The original synthetic deployment remains the default. A guarded live pilot, WHEP/MediaPipe relay and optional AWS runtime are now implemented; use [infra/aws/README.md](../infra/aws/README.md) for the current template, security configuration, backup/restore, retention, teardown and limitations. No actual AWS deployment is claimed. New encrypted storage is not compatible with rolling back to the old plaintext implementation without an explicit migration plan. Keep the original key and consistent backups; never replace a missing encryption key with a new random key.
