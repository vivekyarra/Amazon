# Bee live verification

- **Date:** 21–22 October 2026
- **Verified by:** vivekyarra
- **What was run:** DONE/IRL's live Bee integration (`apps/mcp-orchestrator/done_irl/adapters.py` — `BeeAdapter` SSE stream, todo backfill, `normalize_bee_event`) against the Bee developer API (`https://api.developer.bee.amazon.dev/v1/stream`) with a Bee device and a real `BEE_TOKEN`.
- **Result:** verified. `GET /v1/stream` live SSE events (`new-utterance`, `todo-created`) and `GET /v1/todos` backfill were parsed by the adapter and compiled into DONE/IRL commitment contracts in the owner household on wall-clock time.
- **Reproduce:** `BEE_TOKEN=... uv run python scripts/bee-live-probe.py --seconds 120`.
