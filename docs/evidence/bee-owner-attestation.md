# Bee live verification

- **Date:** 21–22 October 2026
- **Verified by:** vivekyarra
- **What was run:** DONE/IRL's live Bee integration (`apps/mcp-orchestrator/done_irl/adapters.py` — `BeeAdapter` SSE stream, todo backfill, `normalize_bee_event`) against the Bee developer API (`https://api.developer.bee.amazon.dev/v1/stream`) with a Bee device and a real `BEE_TOKEN`.
- **Result:** verified — live Bee data flowed into DONE/IRL and the integration worked as designed.
- **Reproduce:** `BEE_TOKEN=... uv run python scripts/bee-live-probe.py --seconds 120`.
