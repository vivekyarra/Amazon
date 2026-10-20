"""Fetch the official MediaPipe pose model into ignored artifacts/vision/ and verify its pinned SHA-256."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/mcp-orchestrator"))
from done_irl.recorded import fetch_pose_model  # noqa: E402

print(fetch_pose_model())
