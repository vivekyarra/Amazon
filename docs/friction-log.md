# Engineering friction log

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
10. **MediaPipe native dependency:** Python import succeeded, but creating PoseLandmarker failed because `libGLESv2.so.2` was absent. Investigating supported system libraries with package signature/checksum verification intact. Request: document native runtime prerequisites independently from Python import checks.
