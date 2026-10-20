# Fire OS command HUD

Target: Android-based Fire OS / Android TV, API 26+. This is an original native Android shell containing the authenticated shared web HUD. It is not a Vega build and does not imply the official Vega simulator has been tested.

Requires JDK 17+, Gradle 8.13, Android platform 35/build tools 35.0.0. CI builds a debug APK and uploads it as an artifact.

```bash
gradle -p apps/firetv-command-hud assembleDebug --no-daemon --max-workers=2
adb connect YOUR_FIRE_TV_ADDRESS:5555
adb install -r apps/firetv-command-hud/app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n dev.doneirl.tv.debug/dev.doneirl.tv.MainActivity
```

Enable ADB debugging only on a trusted development network. Use **Connection** to enter the backend origin. Debug permits local HTTP; release requires HTTPS. Use the generated private judge/owner login at the service. Do not embed API credentials in the app. Remote top-bar buttons open Ledger, Incident review, Evidence packet and Reality-Lock views. The web HUD supports arrow-key focus navigation and Back. App suspension preserves server state and cookies; private media stays behind server authentication.

## Device validation still required

Run the actual APK on a supported Fire OS device/Android TV emulator, record install/launch, navigate all four views with D-pad/Back, exercise lifecycle/network loss, check WebView support and video decoding. Preserve the recording, device model, OS version, build hash and results. A browser screenshot and an APK build alone do not pass P0-036–040.

Public reference consulted: [Amazon multi-TV sample](https://github.com/AmazonAppDev/react-native-multi-tv-app-sample). Its separate Vega/native targets informed the decision to explicitly select Fire OS; no source or media was copied.
