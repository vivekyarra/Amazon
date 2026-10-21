# Public references and attribution

Implementation follows the [official Ring developer documentation](https://developer.amazon.com/docs/ring/overview.html), [Bee developer API](https://api.developer.bee.amazon.dev), [MCP specification](https://modelcontextprotocol.io/specification/2025-11-25) and SDK APIs. Ring webhook verification uses the documented `X-Signature` raw-body HMAC contract (account-linking nonce encodings are a separate scheme). The WHEP receiver uses Ring's documented example STUN server and gathers ICE before posting a receive-only SDP offer; it is verified live against the Ring Developer Playground device ([evidence](evidence/ring-live-studio.json)).

The public repository [Srustika-18/squat-counter](https://github.com/Srustika-18/squat-counter/tree/9b64cbf1c1f6bfdbfd87a158911dc624d5573c14) was inspected as a reference, and its **14.52-second video.mp4** was used locally for a positive human-pose model check. No counter implementation was copied. The sample is labelled `PUBLIC_LICENSED_RECORDED`, never household footage or a live Ring source.

The repository's MIT license is reproduced below for attribution. The original media remains in ignored local artifacts rather than being republished as an original Muni asset.

> MIT License
>
> Copyright (c) 2024 Srustika Mohapatra
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

A separate public squat dataset repository was also inspected, but its `license` file was empty. Its footage was not used. Merely finding a public repository is not permission to silently republish someone else's work or assert a separate open-source mini-challenge contribution.

## Fifteen-rep pose fixture

The canonical fifteen-rep fixture is **generated**, not human footage and not a Ring recording. `scripts/generate-synthetic-squats.py` ray-traces a humanoid figure (shaded capsules/ellipsoids with skin, clothing and face features) and poses it by forward kinematics. Each of the 15 reps has its own seeded depth (128–140° knee flexion), tempo, sway and arm raise, and every frame carries fresh sensor noise; no footage is looped or copied between reps. The generator is byte-reproducible (seed `20261020`), and the outputs are MIT-licensed project assets:

| Fixture | File | SHA-256 |
|---|---|---|
| `squats-15` (15 full reps, 769 frames, 640×480 @ 15 fps) | `packages/testing-fixtures/pose/squats-15-synthetic.mp4` | `2a35a46dd85d419bc38fdbcf2baa7a22272fbee8b9ab74e9e7c012e101e19162` |
| `squats-half-15` (15 half-squats, 746 frames) | `packages/testing-fixtures/pose/squats-half-15-synthetic.mp4` | `cdb46543128196ace704df0d7706e921cb256ff9edf8a74a1f31fd823d97c47a` |

The official [MediaPipe Pose Landmarker lite model](https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task) (SHA-256 `59929e1d…690d574a`) is fetched by `scripts/fetch-pose-model.py` into ignored `artifacts/vision/` and is never committed. `scripts/evaluate-pose-fixtures.py` decodes the fixtures, runs that model and feeds the same reducer as live Ring frames. Its observed results are in [pose-15-fixture.json](evidence/pose-15-fixture.json), with a derived overlay clip in [pose-15-annotated.mp4](evidence/pose-15-annotated.mp4): 15 reps for `squats-15`, 14 when truncated before the 15th rep, 0 for half-squats, 0 for frozen frames, and 1 when a single rep is looped 15 times. The studio streams the same fixture as **RECORDED DEMO** through `POST /api/studio/recorded/start`, and it is never labelled LIVE RING.

Observed limits: with the larger `pose_landmarker_full` model (SHA-256 `5134a3aa…27a839011b1`, used only for local comparison), the same fixture produced 13 of 15 reps. Reps 6 and 7 were not counted, and 6 frames were flagged as left/right asymmetric. The fixture shows that the pipeline counts complete movements from pixels. It is not a measure of real-world accuracy. Inference is also not bit-identical across platforms. A bare rep-1 clip with no standing lead-in counted 1 rep on Windows and 0 on the Ubuntu CI runner, so the loop negative starts from the fixture's own standing lead-in.

### Real human footage evaluated (not committed)

These freely licensed Wikimedia Commons clips were downloaded only to scratch storage with `curl` and run through the same pinned lite model and verifier. All of them were **0 reps**, mostly because of low hip/knee/ankle visibility (backlit or side views where one leg is occluded), left/right asymmetry, or close-up framing. The verifier was not loosened to make them pass, and none of these clips is redistributed here.

| Commons file | Author | License | Observed |
|---|---|---|---|
| Kettlebell Racked Squats (side view).webm | Taco fleur | CC BY-SA 4.0 | 0 reps (visibility below 0.7 on every frame; about 6 deep reps visible) |
| Double Kettlebell Racked Squat (up view).webm | Taco fleur | CC BY-SA 4.0 | 0 reps (low visibility / asymmetric) |
| Kettlebell Goblet Squat.webm | Taco fleur | CC BY-SA 4.0 | 0 reps (asymmetric) |
| Kettlebell racked squat.webm | Taco fleur | CC BY-SA 4.0 | 0 reps |
| Squat - exercise demonstration video.webm | FitnessScape | CC BY 3.0 | 0 reps |
| Squats Wikipedia.webm | CRiles23 | CC BY-SA 3.0 | 0 reps (mostly close-ups) |
| Sentadillas.ogv | PaolaAltamirano | CC BY-SA 4.0 | 0 reps |
| Muscle Strengthening at Home - Half squat.webm | CDC | Public domain | 0 reps (half-squats; a real-world negative) |

Pexels and Pixabay search pages returned HTTP 403 to non-browser clients, so no footage from those sites was assessed.

## REAL_RECORDED_STOCK scene-vision fixtures

The real-scene porch/threshold pipeline (`apps/mcp-orchestrator/done_irl/scene.py`) is exercised on ten freely licensed public recordings. They are labeled `REAL_RECORDED_STOCK`: **not Ring footage, not the user's home, not consented household footage, and not one continuous scene**. Each clip was downloaded only from the platform's official file host (videos.pexels.com or upload.wikimedia.org), its upstream SHA-256 recorded, then trimmed and downscaled (<=480p, 5-10 fps, no audio) into `packages/testing-fixtures/real-stock/` (3.6 MB total). `scripts/build-real-stock-fixtures.py` reproduces them from the pinned sources; committed fixture hashes are in `packages/testing-fixtures/manifest.json`. No face recognition or identity inference is performed. Pexels clips are used only in neutral roles (deposit, owner pickup, arrival); every removal/theft-shaped clip is publicly released CC BY security-camera footage (the Vancouver Police clip is face-pixelated at source).

Pexels clips are used under the [Pexels License](https://www.pexels.com/license/) (free use and modification; no redistribution on other stock platforms; identifiable people not shown in a bad light). Wikimedia Commons clips are [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/); attribution is given below, and the clips were trimmed and downscaled (modified).

| Fixture | Use | Source | Author | License | Upstream SHA-256 | Fixture SHA-256 |
|---|---|---|---|---|---|---|
| `RS01_DEPOSIT_DOORSTEP_STACK` | porch_deposit -> expected `DEPOSIT_CONFIRMED` | [Putting the Boxes On a Doorstep](https://www.pexels.com/video/putting-the-boxes-on-a-doorstep-8926524/) | [Kampus Production](https://www.pexels.com/@kampus/) | [Pexels License](https://www.pexels.com/license/) | `9d1b2760b739b4d9…` | `f35684161ca3d80b…` |
| `RS02_DEPOSIT_MAILER_DOORMAT` | porch_deposit -> expected `DEPOSIT_CONFIRMED` | [A Person Leaving a Parcel at the Door](https://www.pexels.com/video/a-person-leaving-a-parcel-at-the-door-6667230/) | [Kampus Production](https://www.pexels.com/@kampus/) | [Pexels License](https://www.pexels.com/license/) | `64453a78a3be90c6…` | `9ace09661d6ac353…` |
| `RS03_COURIER_NO_DEPOSIT` | porch_deposit -> expected `MISMATCH` | [File:FedEx fails delivery without knocking.ogv](https://commons.wikimedia.org/wiki/File:FedEx_fails_delivery_without_knocking.ogv) | [Mac Manson (YouTube: stabaho1)](https://www.youtube.com/user/stabaho1) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | `0d80bb4f8bb1d658…` | `409c2c8133050ec8…` |
| `RS04_PORCH_REMOVAL_CCTV` | porch_watchdog -> expected `REMOVAL_UNDER_REVIEW` | [File:Front Porch Theft 2012 11 17 101117.ogv](https://commons.wikimedia.org/wiki/File:Front_Porch_Theft_2012_11_17_101117.ogv) | [Trevor Fiatal (YouTube: tafiatal)](https://www.youtube.com/user/tafiatal) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | `2c095254dbe09401…` | `ef7a0993402058b3…` |
| `RS05_PORCH_REMOVAL_DOORBELL` | porch_watchdog -> expected `REMOVAL_UNDER_REVIEW` | [File:Don't Tempt a Thief with Unattended Parcels.ogv](https://commons.wikimedia.org/wiki/File:Don%27t_Tempt_a_Thief_with_Unattended_Parcels.ogv) | [Vancouver Police Department (YouTube: vpdonline)](https://www.youtube.com/user/vpdonline) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | `74a2d03b2be828a1…` | `c63063656b97ff71…` |
| `RS06_PICKUP_INWARD` | porch_watchdog -> expected `TRANSFER_OBSERVED` | [A Woman Taking Her Packages Inside](https://www.pexels.com/video/a-woman-taking-her-packages-inside-8927178/) | [Kampus Production](https://www.pexels.com/@kampus/) | [Pexels License](https://www.pexels.com/license/) | `794df13a46fd07fe…` | `af8d915f60a3163b…` |
| `RS07_PASSERBY_DRIVEWAY` | porch_watchdog -> expected `NO_REMOVAL` | [File:Package Theft from home.ogv](https://commons.wikimedia.org/wiki/File:Package_Theft_from_home.ogv) | [DonGar37 (YouTube)](https://www.youtube.com/user/DonGar37) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | `567cb7e75ea31282…` | `8791284c5a12c76c…` |
| `RS08_ARRIVAL_BOTTLE_VISIBLE` | threshold -> expected `VISIBLE_MATCH` | [A Woman Drinking on a Bottled Water While Walking](https://www.pexels.com/video/a-woman-drinking-on-a-bottled-water-while-walking-8865610/) | [MART PRODUCTION](https://www.pexels.com/@mart-production/) | [Pexels License](https://www.pexels.com/license/) | `b2747409d5024644…` | `82833bb9806712ff…` |
| `RS09_ARRIVAL_HANDS_EMPTY` | threshold -> expected `NOT_VISIBLE` | [Man Knocking Door](https://www.pexels.com/video/man-knocking-door-11680516/) | [Andrew Kota](https://www.pexels.com/@andrew-kota-1968573/) | [Pexels License](https://www.pexels.com/license/) | `8a88545a17d5ffc7…` | `5af18cd58032e88c…` |
| `RS10_ARRIVAL_PAPER_BAGS` | threshold -> expected `AMBIGUOUS` | [Woman Walking on the Sidewalk Carrying Paper Bags](https://www.pexels.com/video/woman-walking-on-the-sidewalk-carrying-paper-bags-7234080/) | [Blue Bird](https://www.pexels.com/@blue-bird/) | [Pexels License](https://www.pexels.com/license/) | `0dab25bcf1f81ff8…` | `80742e82ad81ad3f…` |

Object detection uses the official MediaPipe [EfficientDet-Lite0 float32 COCO model](https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float32/1/efficientdet_lite0.tflite) (Apache-2.0 per the MediaPipe model card), fetched from storage.googleapis.com into ignored `artifacts/vision/` and checked against SHA-256 `40338edf5ec70d43e318b0a716a84d4564cd1802759a7a07170c7e43796dbf58`. No AGPL detector (e.g. Ultralytics YOLO) is used. Actual per-clip results: [scene-vision evidence](evidence/scene-vision.json).

Clips considered and rejected: several Pexels porch clips with a moving/zooming camera (zones cannot stay calibrated), and Mixkit clips (license outside the allowed set).
