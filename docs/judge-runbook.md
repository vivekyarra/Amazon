# Judge runbook — Muni in five minutes

**Live:** https://100-49-183-59.sslip.io · press **Try Muni live**. No account or password needed.
Each visitor gets a private copy of the **Guided day** household with full judge controls; your clicks run the same backend, reducers and evidence policy as a live household.

| # | Do this | What to notice |
|---|---|---|
| 1 | **Mission control → Run the full day** | Six scenes play in order (08:15 → 20:30). Promises appear as contracts; none start verified. |
| 2 | Open **Commitment ledger**, click *Call your sister* | "Why not done yet": it needs conversation evidence. The 17:00 / 17:35 nudges fired, then the deadline passed → **Missed**, never auto-verified. |
| 3 | Open the teacher meeting | **Verified by evidence** — closed only after a participation record arrived at 16:05. |
| 4 | **Evidence & incidents** | Real CCTV of a parcel leaving the porch, tracked with detection boxes, a hash-chained packet and one question: was this authorized? Try *Confirm authorized pickup* or *Review evidence / Prepare report* → approve → the local receiver records it and **nothing is sent to police**. |
| 5 | Back on Mission control, read **Right now** | The 19:45 arrival check: drinks weren't visible, so Muni asks you to check — no accusation. |
| 6 | **Reality-Lock studio → Play recorded workout** | MediaPipe counts each full squat from the video. 14/15 stays locked; the 15th unlocks the in-app reward. |
| 7 | **Alexa+** → "what did I promise today?" | Each answer cites the MCP tools it called; the tool cards show name, arguments, result and latency. |
| 8 | Type a promise of your own: *"I'll pay the electricity bill by Friday"* | Parsed into a contract with a deadline, T-60/T-25 jobs and the right verification method. |
| 9 | **Judge replay** | The six spec buttons with branches: false delivery claim, family pickup, visible/empty/ambiguous drinks, real-footage branches; the MCP JSON-RPC log streams on the right. |

**MCP from your own client:** `https://100-49-183-59.sslip.io/mcp/` — Streamable HTTP, protocol `2025-11-25`, Bearer = the `done_session` cookie value after pressing *Try Muni live*.

**Fire TV:** the Vega OS app (`apps/firetv-vega-hud`) runs on the Vega Virtual Device; the Fire OS APK (`apps/firetv-command-hud`) sideloads on Fire TV / Android TV and is D-pad tested in CI.

**Run it yourself:** `./scripts/setup-local.sh && ./scripts/start-local.sh`, then `./scripts/access.sh` for local passwords. Tests: `uv run --extra ring-video --extra aws pytest -q` and `npm run test:e2e`.

**Reset:** *Reset day* on Mission control restores a clean guided day at any time.
