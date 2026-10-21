# Muni Fire TV HUD (Vega OS)

React Native for Vega app for Fire TV on Vega OS. It was generated from the official
Vega SDK `helloWorld` template (React Native 0.83, `@amazon-devices/react-native-kepler` 4.x),
package id `com.doneirl.hud`, interactive component `com.doneirl.hud.main`.

It reads live state from the Muni backend over HTTPS. The default backend is
`https://100-49-183-59.sslip.io`, the judge deployment running in DEMO mode. You can
change the backend on the sign-in screen.

Runs on the **Vega Virtual Device**, navigated end to end by D-pad against the hosted backend
([report](../../tests/firetv/vega-device-report.md), [recording](../../docs/evidence/vega/vvd-session-4x.mp4)).

## Views (D-pad)

The top row holds four tabs. Left/Right picks a tab and OK opens it. Down moves into the
content.

| View | What it shows |
| --- | --- |
| A Commitments | One card per contract. Each card has a status word and a glyph (`[OK]`, `[!!]`, `[..]`), the countdown on the server clock, the T-60/T-25/DUE stage, the evidence status, any active PorchWatchdog/SocialGraphAuditor, and a source label. OK opens the detail view: utterance, actor, counterparty, verification method, last evidence and its hash, outstanding action, and a scrollable audit timeline. |
| B Incident | The removal intercept: source, 15 s clip reference, movement, capture gaps and destination. **Confirm Authorized Pickup** opens a confirmation dialog. **Review / Prepare Report** creates a DRAFT only. Approving needs a second dialog. Dispatch to `DEMO_RECEIVER_ONLY` (which records the packet and sends nothing) needs a third. Each dialog opens with focus on **Cancel**, and Back also cancels, so one accidental press can never dispatch. |
| C Evidence | Packet state (DRAFT / APPROVED / DEMO RECEIVER / DISPATCHED / ACKNOWLEDGED, with the current one marked `(*)`), manifest SHA-256, approval record, and the official case ID (shown as none unless an external receipt exists). Below that is the evidence chain: kind, time, original SHA-256, chain hash, source platform and provenance. |
| D Reality-Lock | The annotated frame from `GET /api/studio/frame`, labeled with its source (`LIVE RING`, `Recorded workout` or `Camera frames`). Also the backend rep count `n/15`, `[LOCKED]` / `[OPEN] UNLOCKED`, status and quality. **Continue to entertainment** stays disabled until the backend reports `gate == UNLOCKED`. The accessible override needs a confirmation and is labeled `USER_OVERRIDE`. |

**Back behavior:**

- Back closes a dialog, the keyboard or the detail view.
- On any other tab, Back returns to tab A.
- On tab A, Back exits the app.

**Lifecycle:**

- Polling stops while the app is in the background.
- On resume, the app refreshes at once.
- A network failure shows `OFFLINE - retrying every 3 s`.

**Auth:**

- You type the username and password with the on-screen D-pad keyboard. The keyboard is a
  5 x 10 grid, so Up/Down keeps the column. The VVD did not raise a system IME for
  `TextInput`.
- Nothing is stored in the bundle or on disk. The session lives in memory only.
- The client uses the `done_session` cookie, or `Authorization: Bearer` when the platform
  exposes `Set-Cookie`.
- After sign-in the app registers itself with `POST /api/tv/sessions`.
- Every POST sends a fresh `Idempotency-Key`.

## Build and run (Ubuntu 22.04 / WSL2 with KVM)

```bash
# Official SDK install: https://developer.amazon.com/docs/vega/0.24/install-vega-sdk.html
curl -fsSL https://sdk-installer.vega.labcollab.net/get_vvm.sh | NONINTERACTIVE=true bash   # interactive: drop NONINTERACTIVE
source ~/vega/env
vega --version              # Active SDK Version: 0.24.12112, Vega CLI Version: 1.4.5

cd apps/firetv-vega-hud
npm install
npx tsc --noEmit && npx jest && npx eslint src test --ext .ts,.tsx
npm run build:app           # -> build/x86_64-release/done-irl-firetv-vega-hud_x86_64.vpkg (also armv7/aarch64)

vega virtual-device start   # keep the launching shell alive under WSL
vega run-app build/x86_64-release/done-irl-firetv-vega-hud_x86_64.vpkg com.doneirl.hud.main -d VirtualDevice
```

On a physical Vega Fire TV, use the device's DSN with `-d` and the `aarch64` or `armv7`
`.vpkg`.

## Remote input on the Vega Virtual Device

`vda` ships with the SDK at `~/vega/sdk/vega-sdk/main/<ver>/bin/tools/vda`. Send keys with
the official `inputd-cli`:

```bash
vda shell 'inputd-cli button_press KEY_DOWN'
```

The keys used are `KEY_UP`, `KEY_DOWN`, `KEY_LEFT`, `KEY_RIGHT`, `KEY_ENTER` and
`KEY_BACK`. Developer mode was already enabled on the VVD. Test helpers live in
`tests/firetv/vega/`.
