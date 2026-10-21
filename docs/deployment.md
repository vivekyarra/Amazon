# Operations and deployment

## Local

Run `scripts/setup-local.sh`, then `scripts/start-local.sh`. `/health/live` checks process liveness; `/health/ready` checks ledger access and reports the running mode. Run `scripts/access.sh` only in a private terminal to read the generated credentials. Sessions and state live in the git-ignored `.local` directory; keep it on an encrypted volume if it holds anything sensitive. Stop with Ctrl-C and restart with the same `DATA_DIR` to resume the persisted ledger. Run exactly one worker per database.

## Container

```bash
docker compose -f infra/local/compose.yml up --build -d
docker compose -f infra/local/compose.yml exec done-irl cat /data/access.json   # private terminal only
docker compose -f infra/local/compose.yml down
# Add --volumes only when deliberately deleting ALL local demo data.
```

The image is tested end to end with all six scenarios, fifteen distinct pose cycles, evidence export, service restart, persisted contracts and teardown ([evidence](evidence/container.json)). Build with `docker build -f infra/local/Dockerfile -t done-irl:validation .`; `uv run python scripts/smoke-container.py` validates an isolated container and removes only its own container and volume. The local image starts in demo mode.

For any remote deployment, put an owner-controlled TLS reverse proxy in front, restrict access, set `ALLOWED_ORIGINS` to the real origin and keep passwords private.

## AWS

The hosted judge deployment is CloudFormation stack `done-irl-judge` from `infra/aws/judge-demo.yaml`, deployed and smoke-tested over HTTPS ([evidence](evidence/aws-deployment.json), [MCP + EventBridge](evidence/aws-mcp-scheduler.json)). The template, security configuration, backup/restore, retention and teardown are documented in [infra/aws/README.md](../infra/aws/README.md).

## Fire TV clients

- **Vega OS** — `apps/firetv-vega-hud`, run on the Vega Virtual Device against the hosted backend ([report](../tests/firetv/vega-device-report.md)).
- **Fire OS** — `apps/firetv-command-hud`, an APK built in CI and exercised on an Android TV API 30 emulator with `scripts/firetv-emulator-check.py` ([report](../tests/firetv/device-report.md)).

## Observability

Health responses report storage and mode without secrets. The judge event inspector correlates intake, contract revisions, schedule decisions, evidence, consent and incidents by trace ID. The UI lists source failures and logical observation gaps. After a restart, inspect persisted `scheduled_jobs` and `subagents`; a WATCHING watchdog is persisted event-driven work, not continuous observation. Access logs never store transcript content.

## Rollback

Stop the server, take a consistent SQLite backup (use the SQLite backup API, not a file copy during writes), preserve the encrypted volume and deploy the previous commit. Schema changes are additive (`CREATE TABLE IF NOT EXISTS`). Restore into a separate protected `DATA_DIR` and validate health and ledger before routing users. Keep the original encryption key with every backup: never replace a missing key with a new random one, and encrypted ledgers cannot roll back to older plaintext builds without an explicit migration.

## Lifecycle

Startup, failure, reconnect, resume and teardown are mapped to their documentation and tests in [write-and-degradation-matrix.md](evidence/write-and-degradation-matrix.md#p0-007-lifecycle).
