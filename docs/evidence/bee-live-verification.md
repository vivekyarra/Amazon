# Bee live verification

- **Date:** 21–22 October 2026
- **Verified by:** vivekyarra
- **What was run:** Muni's live Bee integration (`apps/mcp-orchestrator/done_irl/adapters.py` — `BeeAdapter` SSE stream, todo backfill, `normalize_bee_event`) against the Bee developer API (`https://api.developer.bee.amazon.dev/v1/stream`) with a Bee device and a real `BEE_TOKEN`.
- **Result:** verified. `GET /v1/stream` live SSE events (`new-utterance`, `todo-created`) and `GET /v1/todos` backfill were parsed by the adapter and compiled into Muni commitment contracts in the owner household on wall-clock time.
- **Reproduce:** `BEE_TOKEN=... uv run python scripts/bee-live-probe.py --seconds 120`.

## Integration parameters (from `apps/mcp-orchestrator/done_irl/adapters.py`)

| Parameter | Value in Muni |
|---|---|
| Transport | Live SSE stream `GET /v1/stream?types=new-utterance,todo-created,todo-updated,new-conversation,update-conversation` |
| Backfill | `GET /v1/todos` once on connect |
| Reconnect | Exponential backoff 1 s → 60 s, resumes with `Last-Event-ID` |
| Timeouts | 60 s connect, 90 s read |
| Event size cap | 64 KB per event; larger events are rejected |
| Dedupe | Utterance ID / todo ID plus a version hash, so re-delivery creates nothing new |
| Wearer attribution | Unattributed speakers held for owner confirmation (`BEE_SELF_SPEAKERS`) |
| Offline behaviour | Status shows the disconnect; no invented events; last cursor kept for resume |
