# Public references and attribution

Implementation follows the [official Ring developer documentation](https://developer.amazon.com/docs/ring/overview.html), [Bee developer API](https://api.developer.bee.amazon.dev), [MCP specification](https://modelcontextprotocol.io/specification/2025-11-25) and SDK APIs. Current Ring webhook verification uses the documented `X-Signature` raw-body HMAC contract; account-linking nonce encodings are not interchangeable with webhook signatures. Ring's documented example STUN server is used for the WHEP receiver, which gathers ICE before posting a receive-only SDP offer. These code paths still need authorized account/runtime verification.

The public repository [Srustika-18/squat-counter](https://github.com/Srustika-18/squat-counter/tree/9b64cbf1c1f6bfdbfd87a158911dc624d5573c14) was inspected as a reference and provides the **14.52-second video.mp4** used for a limited positive human-pose model check. No counter implementation was copied. The sample is labeled `PUBLIC_LICENSED_RECORDED`, never consented household footage or a live Ring source. Its SHA-256 and actual result are in [the model-check evidence](evidence/mediapipe-public-reference.json). `scripts/check-public-pose.py` downloads only the pinned reference/model, checks both hashes, runs actual MediaPipe and requires a limited positive result. The footage does not meet the fifteen-rep acceptance fixture.

The repository's MIT license is reproduced below for attribution. The original media remains in ignored local artifacts rather than being republished as an original DONE/IRL asset.

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

## Fifteen-rep pose fixture (P0-039, F17/F18)

The canonical fifteen-rep fixture is **SYNTHETIC / GENERATED**, not human footage and not a Ring recording. `scripts/generate-synthetic-squats.py` ray-traces a humanoid figure (shaded capsules/ellipsoids with skin, clothing and face features) and poses it by forward kinematics. Each of the 15 reps has its own seeded depth (128–140° knee flexion), tempo, sway and arm raise, and every frame carries fresh sensor noise; no footage is looped or copied between reps. The generator is byte-reproducible (seed `20261020`), and the outputs are MIT-licensed project assets:

| Fixture | File | SHA-256 |
|---|---|---|
| `squats-15` (15 full reps, 769 frames, 640×480 @ 15 fps) | `packages/testing-fixtures/pose/squats-15-synthetic.mp4` | `2a35a46dd85d419bc38fdbcf2baa7a22272fbee8b9ab74e9e7c012e101e19162` |
| `squats-half-15` (15 half-squats, 746 frames) | `packages/testing-fixtures/pose/squats-half-15-synthetic.mp4` | `cdb46543128196ace704df0d7706e921cb256ff9edf8a74a1f31fd823d97c47a` |

The official [MediaPipe Pose Landmarker lite model](https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task) (SHA-256 `59929e1d…690d574a`) is fetched by `scripts/fetch-pose-model.py` into ignored `artifacts/vision/` and is never committed. `scripts/evaluate-pose-fixtures.py` decodes the fixtures, runs that model and feeds the same reducer as live Ring frames. Its observed results are in [pose-15-fixture.json](evidence/pose-15-fixture.json), with a derived overlay clip in [pose-15-annotated.mp4](evidence/pose-15-annotated.mp4): 15 reps for `squats-15`, 14 when truncated before the 15th rep, 0 for half-squats, 0 for frozen frames, and 1 when a single rep is looped 15 times. The studio streams the same fixture as **RECORDED DEMO** through `POST /api/studio/recorded/start`, and it is never labelled LIVE RING.

Observed limits: with the larger `pose_landmarker_full` model (SHA-256 `5134a3aa…27a839011b1`, used only for local comparison), the same fixture produced 13 of 15 reps. Reps 6 and 7 were not counted, and 6 frames were flagged as left/right asymmetric. The fixture shows that the pipeline counts complete movements from pixels. It is not a measure of real-world accuracy. Inference is also not bit-identical across platforms. A bare rep-1 clip with no standing lead-in counted 1 rep on Windows and 0 on the Ubuntu CI runner, so the loop negative starts from the fixture's own standing lead-in.

### Real human footage investigated (not committed)

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

Pexels and Pixabay search pages returned HTTP 403 to non-browser clients, so no footage from those sites was assessed. Human-video confirmation of fifteen reps remains pending.
