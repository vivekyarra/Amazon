# Fire OS command HUD: Android TV emulator runtime report

> **Honest label:** these results come from an **Android TV emulator** (Google AOSP TV image, API 30 / Android 11, x86) running the **Fire OS-compatible debug APK**. This is **not a physical Fire TV device**, **not Fire OS itself**, and **not Vega OS**. Nothing here certifies Fire TV device validation, Amazon Appstore review, or Vega Virtual Device behaviour. P0-036–040 still need a run on real Fire TV hardware (see `apps/firetv-command-hud/README.md`).

Date: 2026-10-20 · Host: Windows 11 (WHPX acceleration) · Branch: `feat/tv`

## Environment

| Item | Value |
|---|---|
| Emulator | Android emulator 37.1.11.0 (build 15917651), `-gpu swiftshader_indirect -no-snapshot -no-audio` |
| System image | `system-images;android-30;android-tv;x86` rev 4 (Android TV, API 30). Fire OS 8 is based on API 30 and Fire OS 7 on API 28 |
| Build fingerprint | `google/sdk_google_atv_x86/generic_x86:11/RTU1.221129.002/9351025:user/dev-keys` |
| Model / characteristics | `AOSP TV on x86` / `emulator` |
| AVD | `doneirl_tv30`, device profile `tv_1080p` (1920×1080, 320 dpi), 2 GB RAM, `hw.keyboard=yes` |
| System WebView | `com.google.android.webview` 90.0.4430.91 |
| Build | Gradle 8.13, AGP 8.9.1, JDK 21 (Temurin 21.0.12), `platforms;android-35`, build-tools 35.0.0 |
| APK | `app-debug.apk`, 21 836 bytes, **SHA-256 `5ebe657fba4824c444854388b37009103a3714aff740ed1ffcf714b1299f035d`** (package `dev.doneirl.tv.debug`). Debug builds are not reproducible across machines; recompute the hash for your own build |
| Backend | local demo mode (`DEMO_MODE=true`), `uvicorn done_irl.api:app` on 127.0.0.1:8080, frontend built with `npm run build`; emulator reaches it through `adb reverse tcp:8080 tcp:8080` as `http://127.0.0.1:8080` |

## Commands run

```bash
# SDK (official dl.google.com cmdline-tools 16111833, unpacked to $ANDROID_HOME/cmdline-tools/latest)
# The deprecated sdkmanager.bat wrapper split "pkg;ver" arguments on ';', so the bundled Android CLI was used:
"$ANDROID_HOME/cmdline-tools/latest/bin/android.exe" sdk install "platforms;android-35"
"$ANDROID_HOME/cmdline-tools/latest/bin/android.exe" sdk install "system-images;android-30;android-tv;x86"
echo no | "$ANDROID_HOME/cmdline-tools/latest/bin/avdmanager.bat" create avd -n doneirl_tv30 \
  -k "system-images;android-30;android-tv;x86" -d tv_1080p      # then hw.keyboard=yes, hw.ramSize=2048
"$ANDROID_HOME/emulator/emulator" -accel-check                   # WHPX(10.0.26300) is installed and usable
"$ANDROID_HOME/emulator/emulator" -avd doneirl_tv30 -no-snapshot -no-audio -no-boot-anim \
  -gpu swiftshader_indirect -port 5560                           # boot completed in 145 s

# APK
gradle -p apps/firetv-command-hud assembleDebug --no-daemon --max-workers=2   # Gradle 8.13

# Backend (demo mode)
uv sync --frozen --extra ring-video --extra aws && npm ci && npm run build
PYTHONPATH=apps/mcp-orchestrator DEMO_MODE=true uv run --frozen uvicorn done_irl.api:app --host 127.0.0.1 --port 8080

# Runtime check (install, launch, connect, sign in, D-pad walkthrough, Reality-Lock, network, restart, exit)
python scripts/firetv-emulator-check.py --serial emulator-5560 --record --out <dir>
ffmpeg -i walkthrough-raw.mp4 -vf "setpts=PTS/2.1,scale=1280:720,drawtext=..." -an -c:v libx264 -crf 30 walkthrough.mp4
```

The script uses only `adb shell input keyevent KEYCODE_DPAD_*/ENTER/BACK` for navigation. Text is typed with `adb shell input text`, standing in for the remote's on-screen keyboard, for the backend URL and the locally generated demo password; the password is read from the ignored `.local/access.json` and is never printed or recorded. Focus is checked with `uiautomator dump` for native views. For the web content it is checked by reading `document.activeElement` (tag, label, computed outline, in-viewport) through the debug-only WebView DevTools socket. That inspection is read-only.

## Observed results (final run, 33/33 checks passed)

The machine-readable log is `docs/evidence/firetv/run-results.json`.

| Check | Observed |
|---|---|
| Install / cold launch | `Success`; `am start -W` `Status: ok`, TotalTime 7944 ms in the final run (3.8–8.9 s across runs; software GPU) |
| Leanback registration | `cmd package query-activities -c LEANBACK_LAUNCHER` lists `dev.doneirl.tv.debug/.MainActivity` with label Muni and banner. Home screenshot not kept because it shows third-party content |
| Connection | dialog opens on first run; URL typed, Enter/Go on the remote keyboard connects (debug build permits local HTTP) |
| Sign-in | D-pad to username → Back closes IME → Down to password → typed (length verified) → Down → Enter: signed in as the demo household |
| Live backend state | after `/api/admin/reset` and scenarios 1–6: 5 contracts, 1 incident; TV views show the same state (Incident review shows “A package moved. Was it authorized?”, awaiting human decision) |
| View bar | Back from web content moves focus to the current view's button; DPAD_RIGHT moves Ledger → Incident review → Evidence packet → Reality-Lock; ENTER opens each view and hands focus to the web HUD |
| Focus visibility | in all four views DPAD_DOWN moves web focus between controls with a `solid 4px` outline, in viewport; native buttons show a filled mint focus state, and the current view gets an outline |
| Unreachable content | before the fix, the Reality-Lock counter sat below the fold with no focusable control near it, so the D-pad could never reveal it. After the fix, 5 × DPAD_DOWN scrolls it into view |
| Reality-Lock 14/15 | backend `count=14 gate=LOCKED`; TV shows “14 / 15 verified cycles”, no “gate unlocked” |
| Reality-Lock 15/15 | backend `count=15 gate=UNLOCKED`; TV shows “15 / 15” and “15 synthetic cycles verified. In-app gate unlocked.” (synthetic marker frames, not a live camera) |
| Network loss | airplane mode on: status bar reads “Network lost. Showing last loaded state; nothing new is verified until reconnect.” Airplane mode off: message cleared and HUD reloaded |
| Restart | `am force-stop` + relaunch: backend URL, session cookie, last view (`page=studio`) and server state preserved, with no re-login |
| Back / no trap | Back on a view's bar returns to Ledger; Back on Ledger's bar exits to the TV launcher (`com.google.android.tvlauncher`) |

## Defects found on the TV runtime and fixed in this branch

1. **Sign-in impossible on older WebViews.** `crypto.randomUUID` is undefined in WebView 90, and every API write threw “crypto.randomUUID is not a function”. Fire TV WebViews can be similarly old. The fix is a `getRandomValues` UUIDv4 fallback in `apps/judge-godmode-console/src/main.tsx`.
2. **Clipped native buttons.** The view-bar height was 60 *px*, which is 30 dp at 320 dpi, so labels were cut off. Sizing now uses dp: 56 dp targets, a single line, 18 sp text and overscan-safe margins.
3. **Focus trap.** The web HUD consumes every arrow key, so once focus entered it the native view bar was unreachable. Back only reloaded Ledger and never exited. Now Back or Menu parks focus on the view bar. The WebView is made unfocusable while parked, so page scripts can't steal focus back. DPAD_DOWN returns to the content. Back on the bar goes to Ledger, then exits.
4. **Content unreachable by D-pad.** Text-only regions, such as the Reality-Lock counter and evidence text, could not be scrolled into view. In TV mode, Up/Down now scroll by 60% of the viewport while the next control is off-screen.
5. **Backspace in a TV text field navigated away.** The TV Backspace shortcut is now ignored while typing in inputs.
6. Lifecycle and network handling. A `ConnectivityManager` callback shows an honest offline message and reloads on reconnect. A failed load is retried on resume, and the last view is persisted. `configChanges` prevents activity recreation when a remote or keyboard connects.

## Not covered / still required

- No physical Fire TV (Fire OS 7/8) device was used. Amazon WebView, a real remote, Fire OS launcher integration, HDMI overscan and hardware video decoding remain untested.
- Not run on the Vega SDK or Vega Virtual Device. Vega is a separate platform, and this APK does not target it.
- Private media/video playback inside the WebView was not exercised (the synthetic studio frames are JPEG stills).
- The emulator uses software rendering, so its timings are not representative of device performance.
- The repository's Playwright suite was not re-run locally on Windows, because its config targets Linux Chromium. CI runs it.
