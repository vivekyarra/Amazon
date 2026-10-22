# CI evidence

GitHub Actions workflow `.github/workflows/ci.yml` runs from a clean checkout on every push to `main`, `feat/**` and `fix/**`.

| Date | Commit | Run | Jobs |
|---|---|---|---|
| 2026-10-20 | d9b0f3e6fbe06751ec844e886393ad12c2388dca | https://github.com/vivekyarra/Muni/actions/runs/39460611952 | Domain, security and MCP ✅ · Browser journeys ✅ · Fire OS APK build ✅ · **Fire OS APK on Android TV API 30 emulator: 33/33 D-pad checks** ✅ · Container ✅ |
| 2026-10-20 | f7d996c44c1254a2ea5364bac08c22227f97e4cf | https://github.com/vivekyarra/Muni/actions/runs/39425459386 | Domain, security and MCP ✅ · Build and browser journeys ✅ · Fire OS APK build ✅ · Container build and durable replay ✅ |

The backend job downloads the pinned MediaPipe models (official URLs, SHA-256 checked) and runs the full pytest suite, including real-video scene and pose tests.
