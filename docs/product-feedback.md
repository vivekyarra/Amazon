# Product feedback — observed use only

| Tool | Purpose / evidence | What worked | Actual friction / improvement request | Build again? |
|---|---|---|---|---|
| Official MCP Python SDK | `api.py`, external TCP client in `test_mcp.py` | Initialize/discovery/tools share durable REST state | Request context ownership and mounted lifespan need careful wiring; provide a mounted authenticated FastAPI sample | Yes |
| Amazon multi-TV sample docs | Public README consulted for platform boundaries; source link in Fire OS README | Clear separate Vega/Android/web targets | Device runtime must be proven separately; a consolidated CI emulator example would help | Conditional; no sample code was run/copied |
| Android SDK / AGP | Native Fire OS APK compilation | Minimal dependency-free shell builds | Latest command-line tooling requires full modern JDK; error messages should identify JRE-only installs and proxy configuration sooner | Yes |
| GitHub Actions | Domain/MCP, browser, APK validation | Independent hosted checks and retained artifacts | Initial setup-android tried to install the removed `tools` package; explicit toolchain pinning helps reproducibility | Yes |

Bee, Ring, Alexa+ account connection, Vega, Strands/Bedrock and AWS services have not been live-tested. Do not fabricate developer feedback or claim APIs were used in production. Update this sheet after device/token validation with actual errors and successes.
