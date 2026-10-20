# Continuation notes — 20 October 2026

Target remains **FULL_ORIGINAL_VISION_COMPLETE**; verdict **NOT COMPLETE** (34/55 verified). Read [acceptance-report.md](acceptance-report.md) for blockers and [progress.md](progress.md) for the area-by-area state.

## Workflow rules from the owner

- Work on feature branches (`feat/*`), get CI green, then merge to `main`. Keep the repo clean.
- Commits carry only the owner's identity (`vivekyarra`); no co-author or "generated with" trailers.
- Never mark a simulated, recorded or stock source as live. Functionality before UI polish.

## Environments

- Development happens on the owner's Windows 11 laptop (Git Bash, uv, Node 24, JDK 21, Android SDK with a `doneirl_tv30` Android TV AVD, Docker Desktop, WSL2 Ubuntu-22.04 with `/dev/kvm`). `scripts/setup-local.sh` / `start-local.sh` work there.
- AWS profile with admin rights (us-east-1). Stack `done-irl-judge` (template `infra/aws/judge-demo.yaml`) serves https://100-49-183-59.sslip.io. Redeploy a commit with `scripts/judge-redeploy.sh <sha>`; smoke with `scripts/aws-judge-smoke.py`. Secret `done-irl/judge-runtime` holds passwords and the ledger key. Bedrock invocation and CloudFront creation are blocked on this account.
- Judge passwords live only in `C:\Users\vivek\Downloads\Amazon\judge-credentials.txt` (outside the repo).

## Open work (in priority order)

1. Run `scripts/bee-live-probe.py` with the owner's `BEE_TOKEN`; if events normalize, set `BEE_SELF_SPEAKERS`, add `BEE_TOKEN` to the judge secret/owner household and record evidence (P0-008).
2. Run `scripts/ring-live-probe.py` with a fresh Playground token; bind the device in `RING_BINDINGS_FILE`; capture a short live Reality-Lock session (P0-018/019/038).
3. Finish the Vega OS app (`feat/vega`, `apps/firetv-vega-hud`) on the Vega Virtual Device; capture footage (P0-036).
4. Record the owner doing 15 squats (consented) and add it as a human fixture.
5. Produce the under-three-minute video from hosted/emulator/Vega footage; owner uploads it.
6. With owner approval: fork `AmazonAppDev/devices-agent-skills`, add `skills/evidence-backed-commitments` from `packages/agent-skills/`, open the PR, put the link in `docs/submission.md`.
7. After judging (Nov 20): delete the stack and retained table/bucket/key.

Keep `docs/acceptance-manifest.json` as the single source of truth; regenerate the traceability table with `python scripts/update-acceptance.py`.
