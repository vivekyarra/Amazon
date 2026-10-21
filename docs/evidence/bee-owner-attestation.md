# Bee live test — owner attestation

- **Date:** 21–22 October 2026
- **Tester:** project owner (vivekyarra)
- **What was run:** DONE/IRL's live Bee integration (`apps/mcp-orchestrator/done_irl/adapters.py` — `BeeAdapter` SSE stream + todo backfill, `normalize_bee_event`) against the Bee developer API (`https://api.developer.bee.amazon.dev/v1/stream`) with a real `BEE_TOKEN`.
- **Hardware:** a Bee device borrowed from a friend for a single test session, then returned.
- **Owner-reported result:** the integration worked with the real token and real Bee data.
- **Artifacts:** none retained. The token belongs to a third party and was not shared with the repository or its tooling, so `scripts/bee-live-probe.py` output is not available here. Re-run that script with a token to produce a redacted structural report (`docs/evidence/bee-live-probe.json`).
