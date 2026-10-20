# Engineering friction log

## Amazon developer tools (official friction-log format)

Each entry below was actually encountered on 20 October 2026 while building DONE/IRL. Format: task · steps · expected vs actual · severity · workaround · request.

A1. **Bee API stream event shapes are undocumented.** *Task:* ingest live Bee utterances and todos. *Steps:* read https://docs.bee.computer/docs/api; it lists `GET /v1/stream` event types (`new-utterance`, `todo-created`, ...) but no payload schema. *Expected:* a JSON schema/sample per event type. *Actual:* the original adapter guessed a flat `{"utterance": "..."}` shape and would have rejected every real event; the real shape (`{utterance:{id,text,speaker,spoken_at}, conversation_uuid}`, `{todo:{id,text,completed,alarmAt}}`) had to be read from the official `bee-cli` source (`sources/commands/stream/index.ts`). *Severity:* High for integrators. *Workaround:* normalizer mirroring bee-cli plus tests; unknown shapes are ignored, never guessed. *Request:* publish per-event JSON schemas, sample payloads and timestamp units.

A2. **No wearer attribution on Bee utterances.** *Task:* only treat promises spoken by the wearer as commitments. *Expected:* a documented field identifying the device owner. *Actual:* only a free-form `speaker` label. *Severity:* Medium (privacy/safety: someone else's sentence can look like the wearer's promise). *Workaround:* unattributed speech becomes `NEEDS_CONFIRMATION`; an optional `BEE_SELF_SPEAKERS` mapping. *Request:* an explicit `is_wearer`/speaker-identity field.

A3. **Amazon Bedrock Converse returns an unexplained "Operation not allowed".** *Task:* use Nova for ambiguous-utterance parsing. *Steps:* `aws bedrock-runtime converse` with `us.amazon.nova-2-lite-v1:0`, `amazon.nova-lite-v1:0`, `amazon.nova-pro-v1:0` in us-east-1, us-west-2 and ap-south-1 as an IAM user with AdministratorAccess; `list-foundation-models` succeeds. *Expected:* a response, or an actionable access error. *Actual:* `ValidationException: Operation not allowed` with no reason or remedy. *Severity:* High (blocked the planned Nova integration). *Workaround:* deterministic, tested commitment compiler; no LLM dependency. *Request:* say which account state, quota or model-access step is missing.

A4. **CloudFront account verification surfaces only mid-deployment.** *Task:* HTTPS for the judge deployment via a CloudFront distribution. *Actual:* `AWS::CloudFront::Distribution` failed with "Your account must be verified before you can add new CloudFront resources" after other resources were created; the rollback left retained KMS key, DynamoDB table and S3 bucket to clean up manually. *Severity:* Medium. *Workaround:* Elastic IP + Caddy with automatic Let's Encrypt on `<ip>.sslip.io`. *Request:* CloudFormation pre-flight validation (or console banner) for account-level service blocks.

A5. **MCP Python SDK rejects public deployments by default (Alexa+ MCP route).** *Task:* expose the Streamable HTTP MCP server on the public judge URL. *Actual:* `initialize` returned `421 Invalid Host header` because FastMCP's DNS-rebinding protection defaults to localhost hosts only. *Severity:* Medium (silent until tested from outside). *Workaround:* explicit allowed hosts/origins from deployment config, with a regression test. *Request:* Alexa+ MCP onboarding docs should include a public-deployment checklist (Host/Origin, auth, protocol version).

## Other engineering notes (cloud workspace and CI)


These are actual observations, not ten fabricated entries. The source spec’s ten-entry goal is internal. The official bonus/rule claim still needs owner verification against the current competition site.

1. **Cloud package cache location:** `uv sync` first failed because `/home/agent/.cache/uv` was read-only. Set UV_CACHE_DIR to a writable workspace cache. Request: expose writable cache defaults in cloud setup.
2. **GitHub API reachability:** native Git read/push worked while `gh api` returned Forbidden. Adding `api.github.com` to environment domains restored API access after propagation. Request: separate Git versus API capability indicators.
3. **Documentation reachability:** Amazon/MCP official documentation initially returned proxy 403; the public Amazon GitHub sample README was reachable. Added the actual required documentation hosts, preserved presets. Request: show the denied hostname/action in onboarding.
4. **Origin policy and test port:** module assets on the browser test port 8091 were rejected by a fixed-port origin allowlist. Accept the service’s same origin while retaining explicit external-origin rejection. Request: mount/examples should cover production built assets as well as API CSRF.
5. **MCP subprocess import path:** external-client test could not start the child server because pytest's pythonpath option does not automatically set child PYTHONPATH. Set an explicit source directory. Request: subprocess integration examples should state this distinction.
6. **JRE versus JDK:** `java` existed but Android compilation failed because the installation lacked JAVA_COMPILER. Installed an official checksum-verified full JDK. Request: preflight build tools should check javac rather than java alone.
7. **Gradle proxy:** Gradle did not automatically use the shell’s HTTPS proxy and could not resolve the Android plugin. Supplied supported JVM proxy properties and the system trust store, preserving TLS verification. Request: make proxy diagnostics explicit.
8. **Overlapping browser runs:** older test processes continued after their web server was stopped and interfered with a subsequent suite’s shared demo namespace. Stopped owned test processes and ran the suite in isolation; reset setup now waits for its actual response. Request: clearly report orphaned webServer/test ownership on cancellation.

Do not pad this list to ten. Runtime/device observations should be added only when actually encountered.

9. **Retired Android SDK package in CI:** `android-actions/setup-android@v3` defaulted to `tools`, which the SDK repository no longer provides. Set `packages: platform-tools` and install explicit platform/build tools. Request: update action defaults and report removed-package migrations.
10. **MediaPipe native dependency:** Python import succeeded, but creating PoseLandmarker failed because `libGLESv2.so.2` was absent. Resolved using Debian’s signed repository metadata and checksum-verified `libgles2` package, extracted into the writable cloud tools directory; inference then decoded 20 frames with zero false reps. Request: document native runtime prerequisites independently from Python import checks.
