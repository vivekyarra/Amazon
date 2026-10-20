# Fire OS command HUD

Target: Android-based Fire OS / Android TV, API 26+. This is an original native Android shell containing the authenticated shared web HUD. It is not a Vega build and does not imply the official Vega simulator has been tested.

Requires JDK 17+, Gradle 8.13, Android platform 35/build tools 35.0.0. CI builds a debug APK and uploads it as an artifact.

```bash
gradle -p apps/firetv-command-hud assembleDebug --no-daemon --max-workers=2
adb connect YOUR_FIRE_TV_ADDRESS:5555
adb install -r apps/firetv-command-hud/app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n dev.doneirl.tv.debug/dev.doneirl.tv.MainActivity
```

Enable ADB debugging only on a trusted development network. Use **Connection** to enter the backend origin. Debug permits local HTTP; release requires HTTPS. Use the generated private judge/owner login at the service. Do not embed API credentials in the app. Remote top-bar buttons open Ledger, Incident review, Evidence packet and Reality-Lock views. Remote model: the web HUD owns the arrow keys (focus moves between its controls, and Up/Down scroll text-only areas into view). **Back** (or Menu) always returns focus to the native view bar, DPAD_DOWN goes back into the content, Back on the bar opens Ledger, and Back on Ledger's bar exits. A network loss shows an offline message, and the view reloads on reconnect. App suspension preserves server state and cookies; private media stays behind server authentication.

## Android TV emulator check (not a Fire TV device)

`scripts/firetv-emulator-check.py` installs the debug APK on an Android TV AVD, connects it to a local demo backend through `adb reverse`, and signs in. It then drives all four views with D-pad keyevents only, exercises Reality-Lock 14/15 (locked) vs 15/15 (unlocked), network loss, force-stop/relaunch and Back-to-exit. It saves screenshots, `run-results.json` and, with `--record`, a screenrecord.

```bash
# one-time: official cmdline-tools, then
android sdk install "platforms;android-35" "system-images;android-30;android-tv;x86"   # Android CLI in cmdline-tools/latest/bin
avdmanager create avd -n doneirl_tv30 -k "system-images;android-30;android-tv;x86" -d tv_1080p
./scripts/start-local.sh                                  # demo backend on :8080 (writes .local/access.json)
gradle -p apps/firetv-command-hud assembleDebug --no-daemon --max-workers=2
python scripts/firetv-emulator-check.py --boot --serial emulator-5560 --record --out /tmp/firetv-run
```

Latest results: [tests/firetv/device-report.md](../../tests/firetv/device-report.md), with evidence in [docs/evidence/firetv](../../docs/evidence/firetv). That run used an Android TV API 30 emulator with a Fire OS-compatible APK. It is **not** a physical Fire TV and **not** Vega OS.

## Device validation still required

Run the actual APK on a supported Fire OS device/Android TV emulator, record install/launch, navigate all four views with D-pad/Back, exercise lifecycle/network loss, check WebView support and video decoding. Preserve the recording, device model, OS version, build hash and results. A browser screenshot and an APK build alone do not pass P0-036–040.

Public reference consulted: [Amazon multi-TV sample](https://github.com/AmazonAppDev/react-native-multi-tv-app-sample). Its separate Vega/native targets informed the decision to explicitly select Fire OS; no source or media was copied.
