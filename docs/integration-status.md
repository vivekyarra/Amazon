# Integration status

Checked 2026-10-20. These labels describe observed capabilities, never adapter filenames.

| Surface / capability | Status | Actual proof / gap |
|---|---|---|
| Bee canonical ingestion | SIMULATED_VERIFIED | Protected fixtures create four persisted contracts; duplicate/ambiguity tests pass |
| Bee live SSE | BLOCKED | Durable SSE/cursor/inbox wiring and parser/backoff tests exist; actual event-envelope/device verification and authorized token are unavailable |
| MCP Streamable HTTP | SIMULATED_VERIFIED | Official SDK; external TCP client initializes, discovers five tools, compiles and reads shared state |
| Alexa+ account/device | NOT_CONNECTED | No actual Alexa+ connection/voice delivery verified |
| Ring camera/API account | BLOCKED | Documented webhook, account/device binding and WHEP/MediaPipe relay implemented; no linked camera/token or actual runtime proof |
| Ring-like porch/threshold replay | SIMULATED_VERIFIED | Actual generated marker pixels segmented/tracked by OpenCV; not an official Ring simulator |
| Vision human pose | BLOCKED | Optional MediaPipe worker supplied; model fetched from official host; native runtime libraries resolved through authenticated Debian package metadata; actual CPU inference counted zero on 20 nonhuman frames and one on a licensed public 363-frame human sample; fifteen-rep acceptance is still outstanding |
| Fire OS client build | SIMULATED_VERIFIED | Native debug APK compiled; CI build evidence tracked separately |
| Actual Fire TV runtime | BLOCKED | No install/launch/device recording; web preview is not a Fire OS/Vega runtime |
| Web TV/companion | SIMULATED_VERIFIED | Shared authenticated ledger, inbox, D-pad web preview and mobile browser tests |
| Official incident filing | BLOCKED | No authorized official receiver; export and isolated labeled demo receiver only |
| Bee haptics / earbud whisper | BLOCKED | No supported, authorized delivery API verified; no fake-success adapter |
| Cross-app entertainment lock | BLOCKED | Only voluntary DONE/IRL in-app gate; no third-party app control |
| AWS runtime | NOT_CONNECTED | AWS outbox/S3/DynamoDB/Scheduler/SQS/restore and validated infrastructure implemented; eight Moto tests pass, actual credentials/deployment unavailable |

A logical WATCHING subagent is persisted event-driven work. It never promises uninterrupted camera observation. Live source failures do not silently become live-looking replay. Last successful live probe is **none** for the blocked connections.
