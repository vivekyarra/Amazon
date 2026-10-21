# Muni Fire TV HUD (Fire OS)

Native Android shell for Fire OS / Android TV (API 26+) that hosts Muni's authenticated four-view HUD. For Vega OS, see [`apps/firetv-vega-hud`](../firetv-vega-hud/README.md).

Requires JDK 17+, Gradle 8.13 and Android platform 35 / build tools 35.0.0. CI builds a debug APK and uploads it as an artifact.

```bash
gradle -p apps/firetv-command-hud assembleDebug --no-daemon --max-workers=2
adb connect YOUR_FIRE_TV_ADDRESS:5555
adb install -r apps/firetv-command-hud/app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n dev.doneirl.tv.debug/dev.doneirl.tv.MainActivity
```

Enable ADB debugging only on a trusted network. Use **Connection** to enter the backend origin (debug builds allow local HTTP; release builds require HTTPS), then sign in with your owner or judge credentials. No API credentials are embedded in the app.

## Navigation

- The top bar opens Ledger, Incident review, Evidence packet and Reality-Lock.
- Inside a view, the arrow keys move focus between controls; Up/Down scroll text-only areas into view.
- **Back** (or Menu) returns focus to the view bar and DPAD_DOWN re-enters the content. Back on the bar opens Ledger; Back on Ledger's bar exits.
- Network loss shows an offline message and the view reloads on reconnect. Suspension preserves server state and cookies; private media stays behind server authentication.

## Emulator check

`scripts/firetv-emulator-check.py` installs the debug APK on an Android TV AVD, connects it to a local backend through `adb reverse` and signs in. It drives all four views with D-pad key events only, exercises Reality-Lock 14/15 (locked) vs 15/15 (unlocked), network loss, force-stop/relaunch and Back-to-exit, and saves screenshots, `run-results.json` and, with `--record`, a screen recording.

```bash
# one-time: official cmdline-tools, then
android sdk install "platforms;android-35" "system-images;android-30;android-tv;x86"   # Android CLI in cmdline-tools/latest/bin
avdmanager create avd -n doneirl_tv30 -k "system-images;android-30;android-tv;x86" -d tv_1080p
./scripts/start-local.sh                                  # demo backend on :8080 (writes .local/access.json)
gradle -p apps/firetv-command-hud assembleDebug --no-daemon --max-workers=2
python scripts/firetv-emulator-check.py --boot --serial emulator-5560 --record --out /tmp/firetv-run
```

Latest run: 33/33 checks on an Android TV API 30 emulator — [report](../../tests/firetv/device-report.md), [evidence](../../docs/evidence/firetv).

Public reference consulted: [Amazon multi-TV sample](https://github.com/AmazonAppDev/react-native-multi-tv-app-sample). Its separate Vega and native targets informed the choice of a dedicated Fire OS target; no source or media was copied.
