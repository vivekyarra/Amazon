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
