# Write-path and degraded-path evidence (P0-004, P0-007, P0-045)

Audited 2026-10-22 on `feat/audit`. Every row below is enforced by a test that runs in the CI backend
job.

## P0-004: every API write

`test_fixtures_matrix.py::test_P0_004_every_post_route_is_classified` enumerates every `POST` route of
the FastAPI app. The test fails if any route is not listed below, so a new route cannot skip this matrix.

For each of the 28 ledger-write routes, `::test_P0_004_write_is_authenticated_authorized_idempotent_validated_and_audited[<route>]`
checks the following, in order:

1. **Authenticated.** A request with no session returns `401 AUTH_REQUIRED`.
2. **Authorized.** On judge-only `/api/admin/*` and `/api/ingest/*` routes, an authenticated owner gets
   `403 ADMIN_REQUIRED` and that owner's ledger is unchanged. Household scoping is covered by F22 in the
   [fixture matrix](fixture-matrix.md).
3. **Idempotent.** A request without an `Idempotency-Key` returns `400 IDEMPOTENCY_KEY_REQUIRED` before
   any reducer runs, and the ledger is byte-identical afterwards.
4. **Validated.** Routes with a body reject an unknown field with `422 VALIDATION_FAILED`. The input is
   not echoed and the ledger is unchanged.
5. **Audited.** An accepted write appends at least one traced ledger event and a command row.
   - Reducers emit their own specific events.
   - If a reducer emits nothing, `api.py` `audited()` appends `command.audited`. That event records the
     channel, operation, principal, role and the SHA-256 of the key, never the key itself or the body.
6. **Idempotent replay.** Replaying the same key does not change the ledger. Pure command routes also
   return a byte-identical response.
7. **Key reuse.** Reusing the key for a different command returns `409 IDEMPOTENCY_CONFLICT`.

The ledger-write routes are:

- **Contracts:** `/api/contracts/{cid}/confirm`
- **Push:** `/api/push/subscribe`, `/api/push/unsubscribe`
- **Ingestion and owner input:** `/api/ingest/bee-simulated`, `/api/owner/promises`
- **Demo administration:** `/api/admin/scenarios/{stage}/run`, `/api/admin/reset`,
  `/api/admin/clock/advance`, `/api/admin/sister-proof`, `/api/admin/owner-pickup`
- **Consent and incidents:** `/api/consent`, `/api/incidents/{iid}/{action}`
- **Camera:** `/api/camera/start` (exercised against a live-mode app), `/api/camera/stop`
- **Studio:** `/api/studio/sessions`, `/api/studio/recorded/start`, `/api/studio/recorded/stop`,
  `/api/admin/studio/rep`, `/api/admin/studio/frame-step`, `/api/studio/control`,
  `/api/admin/studio/landmarks`
- **Failure injection and TV:** `/api/admin/failures/{kind}`, `/api/tv/sessions`
- **Privacy:** `/api/privacy/cameras/exclusion`, `/api/privacy/cameras/masks`,
  `/api/privacy/retention`, `/api/privacy/providers/{provider}/{action}`,
  `/api/privacy/household/delete`

The external effects of `camera/start` and `recorded/start` (Ring WHEP, MediaPipe streaming) are stubbed
in this test. Those paths are tested separately.

Exempt routes keep a replacement contract (`::test_P0_004_exempt_routes_keep_their_replacement_contract`):

| Route | Contract instead of session + Idempotency-Key |
|---|---|
| `/api/auth/login` | Credential exchange. It validates strictly without echoing input, is rate-limited (`test_rate_limited_login`) and writes no household ledger data. |
| `/api/auth/logout` | Needs the session it revokes; a repeat returns 401. Writes no household data. |
| `/api/webhooks/ring` | Raw-body HMAC plus account/device binding. It is idempotent by provider event id, and receipts go to the durable inbox (`test_forged_webhook_no_state_change`, `test_official_ring_raw_body_signature_and_delayed_retry`, `test_configured_live_webhook_persists_receipt_without_claiming_video`). |

MCP tool writes are covered by `::test_P0_004_mcp_tool_writes_are_authenticated_idempotent_and_audited`,
`test_security.py::test_no_anonymous_reads_writes_mcp` and
`test_mcp_compliance.py::test_dispatch_is_denied_audited_and_idempotent`. They share the same
`mutate`/`audited` path:

- anonymous calls return 401
- a deterministic key makes a repeated call return the stored result
- `command.audited` is written once
- an invalid argument type writes nothing

Two code changes in this audit closed real gaps, and the new tests failed before them:

- `/api/studio/recorded/stop` accepted writes without an Idempotency-Key and wrote no audit record.
- Push subscribe/unsubscribe, studio pause/resume, non-rep pose frames, clock advances with no due job,
  report cancellation and MCP deadline evaluation committed without any ledger event.

## P0-045: degraded paths

| Fault | Safe degradation | Tests |
|---|---|---|
| Ring failure / session expiry | WHEP DELETE and local cleanup run even when upstream cleanup fails. Source drops to `NOT_CONNECTED` with no silent replay. Studio pauses locked with a `watchdog.monitoring_gap`. | `test_fixtures_matrix.py::test_F19_ring_session_budget_expiry_records_gap_and_drops_live_label`, `test_camera.py::test_no_pose_or_duplicate_video_cannot_complete_cycle`, `test_adapters.py::test_ring_rejects_untrusted_session_url` |
| Ring/Bee expired tokens | Rejected and redacted; never shown as live or simulated. An expired owner session gets 401 `SESSION_EXPIRED`. | `test_adapters.py::test_ring_expired_token_does_not_become_live_or_simulated`, `::test_bee_401_redacted`, `test_fixtures_matrix.py::test_F19_ring_access_token_expiry_is_rejected_not_live`, `::test_F19_expired_owner_session_token_is_refused`, `::test_F19_token_expiry_shows_gap_fallback_label_and_recovers_without_reset` |
| Bee stream failure | Error recorded without the token, exponential backoff, nothing fabricated, reconnect resumes from the persisted `Last-Event-ID`. Owner revocation survives restart. | `test_fixtures_matrix.py::test_P0_007_P0_045_bee_stream_failure_backs_off_then_reconnects_with_cursor`, `test_privacy.py::test_provider_disconnect_cancels_work_and_never_auto_reconnects` |
| Worker crash | A claimed inbox lease is recovered after expiry and reduced exactly once. A crashing reconcile loop turns `/health/ready` to 503 and recovers. | `test_runtime.py::test_inbox_restart_lease_recovery_and_exactly_once_reducer`, `test_fixtures_matrix.py::test_P0_007_startup_failure_recovery_and_teardown`, `::test_F20_*` |
| Unauthorized webhook | A forged signature, wrong key or unknown device returns 401 or 403. No inbox row and no state change. | `test_security.py::test_forged_webhook_no_state_change`, `test_runtime.py::test_ring_signed_unknown_device_cannot_cross_households`, `test_fixtures_matrix.py::test_P0_045_unauthorized_and_cross_household_webhooks_change_nothing` |
| Storage failure | A failed save rolls back the whole command, including artifacts and the command row, and the same key succeeds later. A failed S3 upload keeps the outbox for retry. Tampered or expired artifacts are refused. | `test_fixtures_matrix.py::test_P0_045_storage_failure_mid_write_rolls_back_and_reports_retryable`, `test_scenarios.py::test_failed_transaction_rolls_back`, `test_aws_runtime.py::test_s3_failure_keeps_outbox_for_retry`, `::test_failed_cloud_erase_blocks_republish_and_retries`, `test_security.py::test_evidence_tampering_refuses_export_and_preview` |
| Replay duplication | Duplicate removal, duplicate provider event, duplicate Bee event and duplicate command each apply once. | `test_fixtures_matrix.py::test_F21_duplicate_removal_and_duplicate_provider_event_produce_one_of_each`, `test_scenarios.py::test_F01_four_promises_and_duplicate_reconnect`, `test_runtime.py::test_reused_provider_identity_with_changed_payload_rejected`, `test_security.py::test_idempotency_exact_response_and_conflict` |

These faults are injected through mocked HTTP transports, Moto, stubbed sessions and patched storage.
No real Ring, Bee or AWS outage was observed.

## P0-007: lifecycle

| Workflow | Documented | Tested |
|---|---|---|
| Startup | `docs/deployment.md`, `infra/aws/README.md` | `test_P0_007_startup_failure_recovery_and_teardown` (live, then ready), `test_security.py::test_production_mode_fails_closed`, CI container job (`scripts/smoke-container.py`) |
| Failure | `docs/deployment.md` (Runtime observability), `infra/aws/README.md` (Restart/OOM) | Worker crash makes readiness 503, then it recovers (`test_P0_007_*`); P0-045 table above |
| Reconnect | `infra/aws/README.md` step 5 (explicit camera reconnect), Bee adapter | `test_P0_007_P0_045_bee_stream_failure_backs_off_then_reconnects_with_cursor`, F19 resume test, Fire OS emulator offline/reconnect check |
| Resume after restart | `docs/deployment.md`, `infra/aws/README.md` | `test_F20_full_service_restart_mid_watchdog_and_scheduler_recovers_without_duplicates`, `test_F20_restart_during_open_camera_session_records_gap_and_keeps_count`, `scripts/smoke-container.py` (`docker restart`, durable state) |
| Teardown | `docs/deployment.md` (process, compose), `infra/aws/README.md` (stack deletion, retained resources) | Process: lifespan exit closes WHEP/peer/detector and stops Bee (`test_P0_007_*`). Container: `scripts/smoke-container.py` removes its own container and volume in CI. Household data: `test_household_deletion_requires_confirmation_and_is_household_scoped`. **AWS stack teardown has not been executed**, because the judge stack must stay up through judging. |
