# AWS deployment

## Judge deployment (`judge-demo.yaml`)

`infra/aws/judge-demo.yaml` is the stack running for the hackathon (`done-irl-judge`, us-east-1, since 20 October 2026): one EC2 reducer in DEMO_MODE that builds an exact public commit, Caddy terminating HTTPS with an automatic Let's Encrypt certificate on `<elastic-ip>.sslip.io`, and the same DynamoDB (KMS, PITR), versioned SSE-KMS S3, EventBridge Scheduler → SQS (KMS, DLQ), CloudWatch logs and alarms as the owner template below. No SSH; operations use SSM.

```bash
# one-time: a Secrets Manager secret with OWNER_PASSWORD, DEMO_ADMIN_PASSWORD (>=16 chars) and LEDGER_KEY_BASE64 (32 random bytes)
aws cloudformation create-stack --stack-name done-irl-judge --template-body file://infra/aws/judge-demo.yaml   --capabilities CAPABILITY_IAM --parameters ParameterKey=SubnetId,ParameterValue=<public-subnet>   ParameterKey=VpcId,ParameterValue=<vpc> ParameterKey=RuntimeSecretArn,ParameterValue=<secret-arn>   ParameterKey=GitCommit,ParameterValue=<40-char sha>
scripts/judge-redeploy.sh <40-char sha>          # rebuild/restart a newer commit via SSM
DONE_URL=https://<ip>.sslip.io DEMO_ADMIN_PASSWORD=... uv run --extra aws python scripts/aws-judge-smoke.py
aws cloudformation delete-stack --stack-name done-irl-judge   # after judging; then remove retained table/bucket/key
```

CloudFront was the first choice, but the account returned "must be verified before you can add new CloudFront resources" (friction A4), so the stack terminates TLS on the instance. Results: [deployment](../../docs/evidence/aws-deployment.json), [MCP + EventBridge](../../docs/evidence/aws-mcp-scheduler.json).

## Owner deployment template (`template.yaml`)

A production-shaped **single active reducer** variant for owner households. The stack provisions an HTTPS ALB, one EC2 host with encrypted persistent EBS, private SSE-KMS S3 evidence, DynamoDB projections/PITR, EventBridge Scheduler, SQS/DLQ, least-scope service roles, seven-day logs and queue alarms. It shares the runtime, outbox and schedule code of the deployed judge stack; the template itself is validated with `cfn-lint` and Moto-backed tests.

The runtime uses the existing transactional ledger as its authority. Every committed state update also writes an encrypted cloud outbox row. The cloud worker coalesces pending full snapshots, uploads available encrypted artifacts, writes a hash-checked S3 snapshot, conditionally advances the DynamoDB revision, projects queryable records, and creates/updates/cancels deadline schedules. Scheduler messages only wake the trusted reconciler; they cannot provide evidence or mark a contract verified. A one-second durable local reconciliation loop recovers missed scheduler deliveries. Exactly one active reducer owns a ledger volume; never start two restored copies against one table.

## Provisioning inputs

Use an AWS account/region you control. Supply an existing VPC, two public ALB subnets in different AZs, an outbound-enabled service subnet, an ACM certificate and matching DNS name, and a private ECR image pinned by digest. Network/IAM changes and EC2, ALB, KMS and storage incur AWS charges. This template deliberately has no SSH ingress. Use SSM Session Manager for operations.

Create a **Secrets Manager JSON secret** through your private AWS console or secure provisioning tool. Never put values in git, shell history, stack parameters or chat. Fields:

- `OWNER_PASSWORD`: at least 16 characters; the only initial account is `owner`.
- `LEDGER_KEY_BASE64`: a base64-encoded **32-byte cryptographically random** AES key; retain a recoverable copy separately from the ledger. Losing it makes local and cloud ciphertext unreadable.
- Optional `BEE_TOKEN`, `RING_ACCESS_TOKEN`, `RING_HMAC_KEY`, `BEE_HOUSEHOLD` (defaults to `house_owner`). No credentials means an explicitly blocked integration.
- `RING_BINDINGS`: object mapping an authorized Ring account ID to `{"household":"house_owner","devices":["authorized-device-id"],"mains_powered_devices":[]}`. Only independently confirmed line-powered devices belong in the optional mains list; all others have a 30-second budget.

A secret encrypted with a customer-managed key needs an additional, explicit decrypt grant for the instance role. The template's data key does not grant access to unrelated secret keys.

Build the optional native runtime and publish it to your private ECR repository using your own authenticated AWS tooling:

```sh
docker build --build-arg ENABLE_LIVE_RUNTIME=true -f infra/local/Dockerfile -t done-irl:live .
# Authenticate/push with ECR; use the resulting repository@sha256:digest as ImageUri.
uvx --from cfn-lint==1.57.2 cfn-lint infra/aws/template.yaml
aws cloudformation deploy --stack-name done-irl --template-file infra/aws/template.yaml \
  --capabilities CAPABILITY_IAM --parameter-overrides file:///your/private/stack-parameters.json
```

The parameter file contains **identifiers only**: `VpcId`, `PublicSubnets` (comma-separated IDs), `ServiceSubnet`, `CertificateArn`, `PublicHostname`, `RuntimeSecretArn`, and `ImageUri`. Follow your AWS CLI's documented `--parameter-overrides` JSON format. Point your DNS name to the `LoadBalancerDNS` output after provisioning. The host fetches secrets without logging values, downloads and verifies the pinned official pose model, and runs the image as uid 10001 with a read-only root filesystem, dropped capabilities, bounded CPU/RAM, persistent private data, and a read-only config mount. HTTPS forwarded headers are trusted only behind the security group that accepts backend traffic from the ALB.

## Post-deployment verification

1. `/health/ready` must return ready after both the ledger and AWS worker succeed. `/health/live` only proves the process is alive. Missing required AWS configuration fails startup; synchronization failures degrade readiness rather than silently becoming a local-only success.
2. Sign in over the configured HTTPS origin. New live households start with **consent disabled**; enable collection explicitly. Demo administrator routes are unavailable.
3. Register the HTTPS Ring webhook endpoint `/api/webhooks/ring` with the authorized partner account. Signatures use **`X-Signature: sha256=HMAC_SHA256(raw_body)`**. Account and device allowlists are server-side; duplicate `meta.request_id` receipts do not reapply state. By design, motion is never treated as physical proof.
4. Confirm Bee ingestion with `scripts/bee-live-probe.py`. The normalizer mirrors the official bee-cli event shapes (verified live on a Bee device, [evidence](../../docs/evidence/bee-live-verification.md)); unknown envelopes are ignored, never relabelled as successful ingestion.
5. In Reality-Lock choose a linked Ring camera. Capability discovery must advertise video. WHEP uses a receive-only video offer, gathered ICE and the documented STUN server. SDP and session URLs stay on the backend. The server decodes changing frames, runs the SHA-pinned MediaPipe model, relays an authenticated JPEG with skeleton, and verifies reps from those decoded observations. Sessions expire at 30/60 seconds; reconnect explicitly to preserve count. Camera loss resets an incomplete phase and pauses verification.
6. Verify DynamoDB prefix queries (`CONTRACT#`, `AGENT#`, `INCIDENT#`, `EVIDENCE#`, `AUDIT#` under `HOUSE#<household>`), S3 ciphertext and hashes, scheduler T60/T25/deadline creation, queue consumption, and a stopped/restarted service.

Scope: one active writer per ledger volume, an aggregate event history that grows with use, and no automatic failover. High availability and paginated history retention are outside the current scope.

## Operations and recovery

- **Worker/storage failure:** inspect CloudWatch service logs (exception class only), `/health/ready`, pending `cloud_outbox` attempts, `inbox` leases/dead letters, queue-age and DLQ alarms. Outbox storage failures remain durable for retry; a failed upload cannot advance the snapshot pointer. Alarm actions (for example SNS) are left to the account owner; the template sends no messages.
- **SQS/DLQ:** malformed messages exhaust six receives and enter DLQ. Inspect and fix their cause before using AWS's explicit redrive operation. Scheduler hints contain no authentication secrets or physical evidence. Replay does not bypass domain idempotency.
- **Instance updates/replacement:** stop the original reducer before updating instance/AMI properties; restore or reattach the original ledger before starting a replacement. The single-host design has no automatic failover. The live initializer refuses to silently create an empty local household when its cloud snapshot already exists.
- **Restart/OOM:** systemd restarts the one container; Docker has CPU/RAM limits. SQLite state, provider receipts, leases, cursors and rep count survive on EBS. Camera sockets do not survive; a restart records a gap and requires reconnecting. Do not run another active writer during recovery.
- **Retention:** local expired artifact bytes are deleted and manifest tombstones retained. The cloud worker deletes **all S3 versions** of expired evidence and never resurrects expired media during restore. S3's seven-day lifecycle and noncurrent-version expiration are additional eventual backstops; AWS lifecycle execution is not instantaneous. Immutable retries do not refresh an evidence object's age. Daily state snapshot refresh preserves a current backup while older snapshots expire. Ledger and audit metadata remain until the household is deleted.
- **Backup/key recovery:** stop the old reducer, mount a recovered EBS volume or start a fresh volume, provision the exact original ledger key from its separately controlled secret, and run `scripts/restore-aws-household.py --household house_owner` with the stack's non-secret AWS environment configuration. It authenticates/decrypts snapshot and artifact hashes, rejects cross-household context, refuses to overwrite an existing household, and preserves outbox revision order. S3 snapshot recovery restores household state and media, but does not restore sessions, the command-response cache or inbox leases; use EBS/SQLite backups for full local recovery. Restored source-event history prevents reapplying known Bee and Ring observations. Test recovery before relying on it. A copied volume must include its SQLite WAL or use the SQLite backup API; never copy a live database file alone.
- **Clock skew:** keep host time synchronized. Persisted future local time is not rewound; investigate NTP before proceeding. Provider webhook timestamps far in the future are rejected; legitimate delayed retries are deduplicated rather than discarded after an arbitrary five-minute window.
- **Token/password rotation:** stop camera/ingestion, replace the secret through your secure AWS workflow, refresh the host's private config using the bootstrap's retrieval procedure, and restart. Persisted `access.json` must be replaced securely to rotate bootstrap passwords. Do not rotate the AES ledger key by replacing bytes: existing data would require an authenticated re-encryption migration, which is outside the current scope.
- **Teardown:** stop the container and verify WHEP sessions close; delete pending `dirl-*` schedules for this stack's ledger; delete the stack. The instance is terminated; its encrypted EBS volume, the data key, DynamoDB and S3 are **retained** to prevent accidental evidence/data loss. Retire retained volumes, all S3 versions, table protection/backups, logs and KMS key only after the owner applies their retention policy. Deleting a stack is not full data erasure.
