# Release target

Target: **FULL_ORIGINAL_VISION_COMPLETE** (not silently lowered).

## Primary track (one track prize per project)

**Recommended: Alexa+** — self-hosted MCP server (Streamable HTTP, protocol `2025-11-25`) running on the public HTTPS judge deployment, exercised by an external official-SDK client, the MCP Inspector CLI and a hosted `initialize` + `tools/call` ([evidence](evidence/aws-mcp-scheduler.json)); plus a clearly labelled simulated Alexa+ web experience whose source is in this repository. No real Alexa device connection is claimed.

**Eligible alternative: Fire TV** — the Vega OS app runs on the official Vega Virtual Device and the Fire OS APK on an Android TV emulator ([Vega report](../tests/firetv/vega-device-report.md)); the rules accept the Fire TV/Vega simulator in the demo video.

Bee and Ring tracks are **not** claimed: the team has no Bee wearable or Apple Watch running Bee (the Bee track requires one), and no live Ring Developer Playground run has been performed.

## Mini challenges

- AWS Builder: live stack — see `docs/submission.md`.
- Open Source: Agent Skill ready in `packages/agent-skills/evidence-backed-commitments`; PR opened: https://github.com/AmazonAppDev/devices-agent-skills/pull/16.

The original-vision target still cannot pass while live Bee/Ring, physical device and submission media gates remain.
