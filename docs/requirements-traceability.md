# Requirements traceability

All 55 original P0 gates are retained. VERIFIED rows refer only to reproducible synthetic/local behaviors; they do not imply live-device completion. Full original-vision release and independent review remain blocked. `artifacts/` outputs are generated locally or retained by CI, never fabricated source files.

| ID | Result | Evidence / remaining work |
|---|---|---|
| [P0-001](product-spec.md) | IMPLEMENTED_UNVERIFIED | Four modules and schemas exist; clean checkout and full native runtime are separate proof. |
| [P0-002](product-spec.md) | VERIFIED | `test_F20_restart_recovers_watchdog_and_jobs` — Synthetic local development workflow; no live/device inference |
| [P0-003](product-spec.md) | VERIFIED | `test_F01_four_promises_and_duplicate_reconnect` — Synthetic local development workflow; no live/device inference |
| [P0-004](product-spec.md) | IMPLEMENTED_UNVERIFIED | Authenticated live pilot writes now have guarded configuration and provenance; live provider/account runtime and independent review remain unverified. |
| [P0-005](product-spec.md) | VERIFIED | `test_mcp_streamable_http_handshake_discovery_and_shared_state` — Synthetic local development workflow; no live/device inference |
| [P0-006](product-spec.md) | IMPLEMENTED_UNVERIFIED | Status endpoints expose processed provider receipts and current decoded-frame status; actual authorized device probes remain unavailable. |
| [P0-007](product-spec.md) | IMPLEMENTED_UNVERIFIED | Local restart verified; container/full platform lifecycle teardown still needs execution. |
| [P0-008](product-spec.md) | BLOCKED | Bee token/device unavailable; adapter unit tests do not provide live proof. |
| [P0-009](product-spec.md) | VERIFIED | `test_compiler_intent` — Synthetic local development workflow; no live/device inference |
| [P0-010](product-spec.md) | VERIFIED | `test_F01_four_promises_and_duplicate_reconnect` — Synthetic local development workflow; no live/device inference |
| [P0-011](product-spec.md) | VERIFIED | `test_compiler_intent` — Synthetic local development workflow; no live/device inference |
| [P0-012](product-spec.md) | VERIFIED | `test_contract_verification_cannot_bypass_evidence` — Synthetic local development workflow; no live/device inference |
| [P0-013](product-spec.md) | VERIFIED | `test_F04_F06_teacher_exact_schedules_and_proof` — Synthetic local development workflow; no live/device inference |
| [P0-014](product-spec.md) | VERIFIED | `test_F07_F08_independent_sister_schedule_and_evidence` — Synthetic local development workflow; no live/device inference |
| [P0-015](product-spec.md) | VERIFIED | `test_F05_engaged_quiet_without_premature_verification` — Synthetic local development workflow; no live/device inference |
| [P0-016](product-spec.md) | VERIFIED | `test_F04_F06_teacher_exact_schedules_and_proof` — Synthetic local development workflow; no live/device inference |
| [P0-017](product-spec.md) | VERIFIED | `test_late_scheduler_does_not_send_stale_twenty_five_minute_alert` — Synthetic local development workflow; no live/device inference |
| [P0-018](product-spec.md) | BLOCKED | Documented raw-body webhook HMAC, account/device binding, capabilities and bounded aiortc WHEP decoder implemented; real Ring account/runtime proof missing. |
| [P0-019](product-spec.md) | IMPLEMENTED_UNVERIFIED | Sources labeled; actual Ring simulator and live switching not connected. |
| [P0-020](product-spec.md) | IMPLEMENTED_UNVERIFIED | Real-frame pipeline (`done_irl/scene.py`: pinned MediaPipe EfficientDet-Lite0, ROI change detection, IoU tracker) decodes actual recorded video: `test_real_clip_verdicts[RS01/RS02]` → DEPOSIT_CONFIRMED, `[RS03]` (courier leaves without a drop) → MISMATCH; `test_real_deposit_stage_uses_shared_reducers_and_labels_source`. Source is REAL_RECORDED_STOCK (Pexels / CC BY Commons), not Ring or this household; COCO has no parcel class, so parcels are inferred from persistent ROI change. Ring-sourced proof still missing. Synthetic marker path unchanged for deterministic replay. |
| [P0-021](product-spec.md) | VERIFIED | `test_F02_deposit_starts_one_watchdog_without_completion` — Synthetic local development workflow; no live/device inference |
| [P0-022](product-spec.md) | IMPLEMENTED_UNVERIFIED | Leased durable provider worker and Ring notification handling/recovery implemented; actual Ring observation/history-based watchdog reconciliation still missing. |
| [P0-023](product-spec.md) | IMPLEMENTED_UNVERIFIED | Synthetic 15-second path unchanged. Real path: two public CC BY porch-camera clips → REMOVAL_UNDER_REVIEW (`test_real_clip_verdicts[RS04/RS05]`); `test_real_removal_creates_one_incident_with_truthful_clip_labels` shows one incident, original MP4 + parent-linked annotated WebM/frame, person crop, pixel trajectory ("world-space trajectory unavailable"), and the 14.1 s clip labeled EVIDENCE_INCOMPLETE. Not Ring footage; live Ring detection remains blocked. |
| [P0-024](product-spec.md) | IMPLEMENTED_UNVERIFIED | Private AES-GCM local artifacts and optional SSE-KMS S3 replica/restore implemented and tested locally; actual cloud/live media proof pending. |
| [P0-025](product-spec.md) | VERIFIED | `test_F16_retained_parcel_owner_pickup` — Synthetic local development workflow; no live/device inference |
| [P0-026](product-spec.md) | VERIFIED | `test_pixel_detector_negative_cases` — Synthetic local development workflow; no live/device inference. Additional real-frame negatives on REAL_RECORDED_STOCK: passerby → NO_REMOVAL / no courier → UNKNOWN, interrupted clips → UNKNOWN, dark/empty → CAMERA_UNAVAILABLE, painted occluder over real frames → UNKNOWN, static lamp false-positive ignored, duplicate removal → one incident (`test_scene.py`). |
| [P0-027](product-spec.md) | IMPLEMENTED_UNVERIFIED | Working authenticated web incident view; actual TV device/runtime proof missing. |
| [P0-028](product-spec.md) | VERIFIED | `test_F10_family_authorization_is_human_provenance` — Synthetic local development workflow; no live/device inference |
| [P0-029](product-spec.md) | IMPLEMENTED_UNVERIFIED | Preview shows available synthetic evidence; live images/clip/address unavailable. |
| [P0-030](product-spec.md) | VERIFIED | `test_F11_F12_report_prepare_approve_simulated_dispatch` — Synthetic local development workflow; no live/device inference |
| [P0-031](product-spec.md) | VERIFIED | `test_F23_official_dispatch_boolean_and_unauthorized` — Synthetic local development workflow; no live/device inference |
| [P0-032](product-spec.md) | IMPLEMENTED_UNVERIFIED | Stage 5 can now consume a recorded real clip (`real_visible`/`real_empty`/`real_bags`) through the same reducers and cross-reference the drinks contract (`test_real_threshold_branches`). Clips are public stock scenes (RS08/RS10 have no real doorway), not a Ring recording or live trigger. |
| [P0-033](product-spec.md) | VERIFIED | `test_F13_F14_F15_threshold_uncertainty` — Synthetic local development workflow; no live/device inference. Real-frame check on REAL_RECORDED_STOCK: bottle carrier → VISIBLE_MATCH, empty-handed → NOT_VISIBLE, paper bags → AMBIGUOUS (`test_real_clip_verdicts[RS08–RS10]`); not Ring footage. |
| [P0-034](product-spec.md) | VERIFIED | `test_F13_F14_F15_threshold_uncertainty` — Synthetic local development workflow; no live/device inference |
| [P0-035](product-spec.md) | VERIFIED | `test_stolen_branch_cannot_also_claim_owner_pickup` — Synthetic local development workflow; no live/device inference |
| [P0-036](product-spec.md) | BLOCKED | Native APK builds; no supported Fire OS/Vega device launch recording. |
| [P0-037](product-spec.md) | IMPLEMENTED_UNVERIFIED | Four web HUD views and native navigation supplied; actual D-pad device proof pending. |
| [P0-038](product-spec.md) | BLOCKED | Backend WHEP decoder, MediaPipe/JPEG relay and real-codec synthetic loopback implemented; actual Ring-to-Fire-TV runtime proof pending. |
| [P0-039](product-spec.md) | BLOCKED | Actual MediaPipe processed a licensed public video and counted one rep; canonical fifteen distinct human-rep acceptance remains unmet. |
| [P0-040](product-spec.md) | IMPLEMENTED_UNVERIFIED | Synthetic 14/15 versus 15/15 passes; actual TV restart and human-video proof pending. |
| [P0-041](product-spec.md) | VERIFIED | `test_accessible_override_does_not_falsely_verify` — Synthetic local development workflow; no live/device inference |
| [P0-042](product-spec.md) | VERIFIED | `canonical full day updates shared ledger, keeps uncertainty and verifies 15 cycles` — Synthetic local development workflow; no live/device inference. Also exercised by `simulated Alexa+ answers from real MCP tool calls over the shared ledger` (buttons 1, 2, 3 and 5 mutate state that the simulated Alexa+ panel then reads back through `/mcp/`). |
| [P0-043](product-spec.md) | VERIFIED | `test_three_replays_semantically_deterministic` — Synthetic local development workflow; no live/device inference |
| [P0-044](product-spec.md) | IMPLEMENTED_UNVERIFIED | F01–F24 mapped; F17 human-video and F24 native runtime remain incomplete. |
| [P0-045](product-spec.md) | IMPLEMENTED_UNVERIFIED | Durable queue lease/crash, consent, provider duplicate, encrypted retention, AWS emulation and real codec tests pass; actual provider/cloud faults still unverified. |
| [P0-046](product-spec.md) | IMPLEMENTED_UNVERIFIED | Encrypted storage, retention byte deletion and consent propagation, plus owner per-camera exclusion, PRIVATE_MASKS (derived evidence zeroed before hashing; source clip kept unmasked under encryption), 1–30 day retention, Bee/Ring disconnect without auto-reconnect and household-scoped deletion with queued AWS erase. Local/Moto tests: `test_privacy_controls_require_authenticated_owner_and_idempotency`, `test_camera_exclusion_blocks_synthetic_collection_and_is_audited`, `test_live_excluded_camera_cannot_start_and_webhook_is_acknowledged_not_processed`, `test_frame_callback_refuses_excluded_camera_without_evidence`, `test_apply_masks_zeroes_exact_normalized_region`, `test_private_masks_zero_pixels_in_derived_evidence_before_hashing`, `test_retention_setting_updates_existing_and_new_artifacts_without_breaking_chain`, `test_shortened_retention_deletes_due_bytes_immediately_and_never_resurrects`, `test_provider_disconnect_cancels_work_and_never_auto_reconnects`, `test_household_deletion_requires_confirmation_and_is_household_scoped`, `test_household_deletion_erases_only_that_households_cloud_objects`, `test_failed_cloud_erase_blocks_republish_and_retries`. Unverified: real Ring/Bee/AWS runtime, upstream token revocation, operator backup deletion, independent security review. |
| [P0-047](product-spec.md) | BLOCKED | Engineering CI supplied; required Fire TV device/simulator tests absent. |
| [P0-048](product-spec.md) | BLOCKED | Runbook/screenshots supplied; real track footage and submission artifacts incomplete. |
| [P0-049](product-spec.md) | IMPLEMENTED_UNVERIFIED | AWS runtime/projection/schedules/restore and validated CloudFormation supplied alongside local deployment; actual AWS provisioning/runtime remains unverified. |
| [P0-050](product-spec.md) | BLOCKED | Candidate Alexa+ route recorded via the rules' simulated-Alexa+ alternative: MCP 2025-11-25 server (`test_mcp_compliance.py`, `test_mcp.py`), external SDK client transcript `docs/evidence/mcp-external-client.json`, MCP Inspector CLI `docs/evidence/mcp-inspector-cli.json`, and the labeled simulated Alexa+ console panel (`tests/e2e/alexa-sim.spec.ts`). Still pending: final track-eligibility decision, recorded submission demo, hosted HTTPS MCP endpoint; no Alexa device/account integration is claimed. |
| [P0-051](product-spec.md) | BLOCKED | No public under-three-minute video URL or required device footage. |
| [P0-052](product-spec.md) | IMPLEMENTED_UNVERIFIED | Actual tools have feedback; Amazon live tool feedback and mini-challenge links pending. |
| [P0-053](product-spec.md) | IMPLEMENTED_UNVERIFIED | Actual friction recorded; no fabricated ten-entry or bonus claim. |
| [P0-054](product-spec.md) | IMPLEMENTED_UNVERIFIED | Traceability/progress/report maintained; independent dated release review still needed. |
| [P0-055](product-spec.md) | BLOCKED | Release gate intentionally reports NOT_COMPLETE; no independent platform review. |

Machine-readable definitions, exact requirement text and code/test references: [acceptance manifest](acceptance-manifest.json). Domain tests live in `apps/mcp-orchestrator/tests`; browser tests in `tests/e2e/journeys.spec.ts`. Device acceptance is deliberately separate from the engineering build.
