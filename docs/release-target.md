# Release target

Target: **FULL_ORIGINAL_VISION_COMPLETE** (not silently lowered).

## Primary track (one track prize per project)

**Recommended: Alexa+** — self-hosted MCP server (Streamable HTTP, protocol `2025-11-25`) running on the public HTTPS judge deployment, exercised by an external official-SDK client, the MCP Inspector CLI and a hosted `initialize` + `tools/call` ([evidence](evidence/aws-mcp-scheduler.json)); plus a clearly labelled simulated Alexa+ web experience whose source is in this repository. No real Alexa device connection is claimed.

**Eligible alternative: Fire TV** — the Vega OS app runs on the official Vega Virtual Device and the Fire OS APK on an Android TV emulator ([Vega report](../tests/firetv/vega-device-report.md)); the rules accept the Fire TV/Vega simulator in the demo video.

**Eligible alternative: Ring** — the official Ring Partner API runs live against the Ring Developer Playground device: discovery, capabilities, history and a WHEP live view decoded server-side and relayed into the Reality-Lock studio as LIVE RING ([probe](evidence/ring-live-probe.json), [studio](evidence/ring-live-studio.json)). The rules accept a Ring simulator.

**Bee:** the live integration was run by the owner with a borrowed Bee device ([attestation](evidence/bee-owner-attestation.md)). The Bee track is not recommended as primary because its demo video must show live Bee data and the device is no longer available.

## Mini challenges

- AWS Builder: live stack — see `docs/submission.md`.
- Open Source: Agent Skill ready in `packages/agent-skills/evidence-backed-commitments`; PR opened: https://github.com/AmazonAppDev/devices-agent-skills/pull/16.

The original-vision target still cannot pass while live Bee/Ring, physical device and submission media gates remain.
