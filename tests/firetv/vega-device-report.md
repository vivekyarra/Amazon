# Vega OS device test report: Muni Fire TV HUD

**Runtime label: Vega Virtual Device (Amazon's official emulator). This was not a physical Fire TV
device.**

Status, mode and account names below use the project's current vocabulary; the API
behaviour they describe is unchanged.

- **Date:** 2026-10-20
- **Tester:** automated agent session on the developer workstation
- **App:** `apps/firetv-vega-hud`, package `com.doneirl.hud`, component `com.doneirl.hud.main`
- **Backend:** `https://100-49-183-59.sslip.io`, the public judge deployment in GUIDED mode
  (`REPLAY_VERIFIED`, scripted clock). It was signed in as `judge`. During the
  session the backend was running a newer commit, but the API was the same.

## Environment

| Item | Value |
| --- | --- |
| Host | Windows 11 Home, WSL2 `Ubuntu-22.04` (kernel 6.18.33.2-microsoft-standard-WSL2), `/dev/kvm` present, 12 cores, 7 GB RAM |
| Display | WSLg (VVD window titled "Vega Virtual Device") |
| Vega SDK | `0.24.12112` (Active SDK Version), Vega CLI `1.4.5`, installed by the official `get_vvm.sh` installer, `NONINTERACTIVE=true`, default `~/vega/sdk` |
| Vega Virtual Device | `virtualdevice` 1.0.6500.0, bundled with SDK 0.24.12112. `vega device info`: product `vvrp-tv-x64`, profile `tv`, `buildDescription` "OS 1.2 (TV Ship/102401320)", flagged as an emulated (non-physical) device, `inDeveloperMode: true` |
| Dependencies | Node v20.20.2 (nvm), watchman 4.9.0, lz4, libpython3.8-dev (deadsnakes), qemu-kvm/libvirt (`kvm-ok`: KVM acceleration can be used) |
| Template | `vega project generate --template helloWorld` (RN 0.83, `@amazon-devices/react-native-kepler` ~4.0.0) |
| Account | No Amazon login or developer account was needed to install, build or run on the VVD |

## Builds

`npm run build:app` (Release) produced three `.vpkg` files per build.

**Build 1:** source commit `bd633cd`. This build was used for the full four-view session and
the recording.

- `x86_64` SHA-256: `544049f9ed2365dcdf25e823479196312583d6737700881e3b6a2ea4419ac580`

**Build 2:** source commit after the UI fixes below. Screenshots 24 and 25 come from this
build.

| Arch | SHA-256 |
| --- | --- |
| x86_64 | `6ab7a13577622221a39afa3a8974344d6acf59d2df9155a5e331aaeb4b5a1086` |
| aarch64 | `6e570c44fcf73e3409c6953cc4161a71de5d14ae5cf81db20b4b4266e7d78514` |
| armv7 | `ea144494ae17b612badd3835d2f5972fc385e689e22b2a7f8b4365960a867db7` |

The builds are not checked for byte-reproducibility, so a rebuild will produce different
hashes. `.vpkg` files are not committed. Rebuild from source.

Before each build, these checks passed: `npx tsc --noEmit` clean, `npx eslint src test`
clean, and `npx jest` 7/7.

## Exact commands

```bash
source ~/vega/env
cd apps/firetv-vega-hud && npm install && npm run build:app
vega virtual-device start                       # reports the device ready  (keep the launching WSL shell alive)
vega device list                                # VirtualDevice : tv - x86_64 - OS - amazon-885fce6776255e1e
vega run-app build/x86_64-release/done-irl-firetv-vega-hud_x86_64.vpkg com.doneirl.hud.main -d VirtualDevice
#   -> "Installed ... on VirtualDevice" / "Successfully launched the app"
vega device running-apps -d VirtualDevice       # lists com.doneirl.hud.main

# D-pad input: official inputd-cli on the device (developer mode was already enabled)
VDA=~/vega/sdk/vega-sdk/main/0.24.12112/bin/tools/vda
$VDA shell 'inputd-cli button_press KEY_DOWN'   # also KEY_UP/LEFT/RIGHT/ENTER/BACK
# helpers: tests/firetv/vega/tv.sh key KEY_X [n] | tv.sh shot NAME ; tests/firetv/vega/tvtype.py

# Screenshots / recording: the VVD's bundled emulator console on 127.0.0.1:5554
#   screenrecord screenshot /tmp/vshots
#   screenrecord start --size 1280x720 --time-limit 600 /tmp/vega-hud-session.webm   (and: screenrecord stop)
# (QEMU QMP "screendump" returned a blank frame because the display is GPU-composited.)

# Backend scenarios as judge (tests/firetv/vega/scen.sh -> api.py, password from an uncommitted local file)
POST /api/admin/reset
POST /api/admin/scenarios/1/run {"branch":"deposit"}
POST /api/admin/scenarios/2/run {"branch":"deposit"}
POST /api/admin/scenarios/3/run {"branch":"engaged"}
POST /api/admin/scenarios/4/run {"branch":"deposit"}     # removal -> inc_parcel AWAITING_HUMAN_DECISION
POST /api/admin/scenarios/5/run {"branch":"visible"}
POST /api/admin/studio/rep  x14, then x1               # 14/15 LOCKED, then 15/15 UNLOCKED
POST /api/admin/scenarios/6/run {"branch":"deposit"}
```

## Observations (in order)

All screenshots are 1280x720 JPEG downscales of the 1920x1080 VVD framebuffer.

1. **Launch and sign-in (`01-login.jpg`, `02-login-filled.jpg`).**
   - The app installs and launches on the VVD.
   - Focusing a `TextInput` and pressing OK did not bring up a system keyboard on the VVD.
     `inputd-cli send_text` did not reach the field either.
   - The app therefore uses an in-app D-pad keyboard. The password was entered with D-pad
     presses only, and the field shows it masked.
2. **Live data over HTTPS from the VVD.**
   - The first wrong password got the backend's real 401 message ("Username or password is
     incorrect."), which proves the VVD reached the backend.
   - After sign-in, `POST /api/tv/sessions` registered the TV session. The header shows the
     `tv_...` session ID and the live integration statuses.
3. **View A (`03`, `04`, `05`, `06`, `07`, `22`, `23`).**
   - The matrix updates within one poll after each backend scenario run.
   - **Countdowns** (for example "Due in 1h 55m") run on the server's scripted clock.
   - **Stages:** T-60/T-25/DUE show as pending or sent.
   - **Evidence and watchers:** evidence counts with the last decision, SocialGraphAuditor
     and PorchWatchdog `WATCHING`, and scripted-replay source labels.
   - **Detail:** OK opens it, showing utterance, actor, counterparty, method, last evidence
     hash and outstanding action. The audit timeline scrolls with the D-pad, and Back
     returns to the matrix.
4. **View B (`08` to `13`).**
   - After scenario 4 the incident shows `AWAITING_HUMAN_DECISION`.
   - Confirm Authorized Pickup opens a dialog with focus on Cancel. Back cancelled it, and
     no backend call was made.
   - Review / Prepare Report produced `EVIDENCE_PREPARED`, labeled DRAFT (not sent).
   - Approve opened a second dialog with focus on Cancel. Approval needed an explicit move
     to the approve button, then OK, which produced `REPORT_APPROVED`.
   - Dispatch needed a third dialog and produced `LOCAL_DISPATCH`, a local-receiver receipt
     marked "NOT SENT TO POLICE", official case ID none.
5. **View C (`14`, `15`).**
   - Packet state marks the local-receiver state `(*)` against DRAFT, DISPATCHED and ACKNOWLEDGED.
   - Also shown: the manifest SHA-256, the approval record, and the evidence chain (deposit,
     participation, removal frame, person crop, original and derived clips) with SHA-256,
     chain hash, source and provenance.
6. **View D (`16` to `21`).**
   - No session: 0/15 and LOCKED. "Start studio session" was pressed on the TV.
   - At 14/15 the gate showed `[LOCKED]`, and pressing "Continue to entertainment (locked)"
     did nothing (`19` is identical to `18`).
   - After the 15th backend rep the screen showed 15/15, `[OPEN] UNLOCKED` and status
     COMPLETED, and Continue opened the in-app entertainment gate.
   - The annotated frame from `/api/studio/frame` (Bearer-authenticated `Image`) is
     labeled as a scripted marker source and "NOT LIVE RING", plus the app's scripted-source
     banner.
7. **Recording (`vvd-session-4x.mp4`).** It runs 150 s at 4x speed. It covers about 10
   minutes of real time, from the live matrix through the detail, incident review, evidence
   packet and studio unlock to the final matrix. The source was the VVD console
   `screenrecord` at 1280x720, transcoded with ffmpeg (h264, CRF 30, 960x540, 12 fps).
8. **Restart persistence (`24`, `25`, build 2).**
   - The app was reinstalled, which terminated it and cleared the in-memory session.
   - After signing in again, the matrix and Reality-Lock show the same backend state:
     15/15 UNLOCKED, and the squat contract is VERIFIED.
   - Build 2 fixes:
     - Closed contracts read "Closed (VERIFIED/MISSED)" instead of "Overdue".
     - The ONLINE / "updated n s ago" indicator is no longer clipped.
     - The studio frame reloads only when new pose data arrives. In build 1 it went briefly
       black on every 3 s poll; `20` caught one of those black frames.

## Limitations and honest gaps

- **Emulator only.** No physical Vega or Fire OS device was used.
- **Typing automation.** One `vda shell inputd-cli button_press` per key was reliable but
  slow: about 13 minutes for a 24-character password. Batched `inputd-cli series` and piped
  console mode dropped or misplaced presses. That is a limit of the test harness, not of the
  app.
- **Password exposure during testing.** One automated run started from an unexpected focus
  state and typed the judge password into the visible Username field.
  - The screenshot that captured it was deleted before any commit, and git history was
    checked: only the masked image is committed.
  - The recording started after sign-in, so it does not include the password.
  - The driver now requires a screenshot check that the Password keyboard is open first.
  - The judge password **should still be rotated**, because it was rendered in
    plaintext on the emulator screen.
- **Sessions are in memory only.** Restarting the app means signing in again, by design,
  since nothing is persisted on the device.
- **Backend is GUIDED only.** All sources are SCRIPTED / `REPLAY_VERIFIED`. LIVE RING was
  not exercised: the backend refuses camera start in GUIDED mode.
- **Not exercised:**
  - Video playback of the 15 s clip; the app shows a reference to it.
  - Network-loss recovery on the VVD; the code shows OFFLINE and retries every 3 s, but this
    was not tested.
  - Suspend/resume via the home button.
  - The accessible-override path (it is implemented).
