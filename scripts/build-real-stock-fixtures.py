"""Reproduce the REAL_RECORDED_STOCK fixture clips from their pinned public sources.

Downloads only from the official hosts recorded in scene-fixtures.json (videos.pexels.com,
upload.wikimedia.org), verifies each upstream SHA-256, then trims/downscales with ffmpeg.
x264 output can differ between ffmpeg builds, so a rebuilt fixture may hash differently from
the committed one; the committed fixture hashes live in packages/testing-fixtures/manifest.json.

Usage:
  uv run python scripts/build-real-stock-fixtures.py --sources /private/stock-sources [--download]
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlparse

import httpx

root = Path(__file__).resolve().parents[1]
fixture_dir = root / "packages/testing-fixtures/real-stock"
config = json.loads((fixture_dir / "scene-fixtures.json").read_text())
ALLOWED_HOSTS = {"videos.pexels.com", "upload.wikimedia.org"}
MAX_BYTES = 64 * 1024 * 1024


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url, path):
    if urlparse(url).hostname not in ALLOWED_HOSTS or not url.startswith("https://"):
        raise SystemExit(f"Refusing non-allowlisted source host: {url}")
    headers = {"User-Agent": "DONE-IRL-fixture-builder/1.0 (reproducible test fixtures)"}
    with httpx.stream("GET", url, timeout=120, follow_redirects=False, headers=headers) as response:
        response.raise_for_status()
        size = 0
        with path.open("wb") as target:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise SystemExit("Source exceeds the download limit.")
                target.write(chunk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", required=True, type=Path, help="Directory holding upstream source files")
    parser.add_argument("--download", action="store_true", help="Fetch missing sources from pinned URLs")
    parser.add_argument("--output", type=Path, default=fixture_dir)
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required")
    args.sources.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    for clip in config["clips"]:
        src = clip["source"]
        local = args.sources / (clip["id"] + Path(urlparse(src["download_url"]).path).suffix)
        if not local.is_file() or sha256(local) != src["source_sha256"]:
            if not args.download:
                raise SystemExit(f"{clip['id']}: source missing or hash mismatch ({local}); pass --download")
            fetch(src["download_url"], local)
            if sha256(local) != src["source_sha256"]:
                local.unlink()
                raise SystemExit(f"{clip['id']}: upstream SHA-256 mismatch; not using it")
        out = args.output / clip["file"]
        trim, enc = clip["trim"], clip["encode"]
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(trim["start"]), "-to", str(trim["end"]), "-i", str(local),
            "-an", "-map_metadata", "-1",
            "-vf", f"fps={enc['fps']},scale=-2:{enc['height']}",
            "-c:v", "libx264", "-preset", "slow", "-crf", "27", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-fflags", "+bitexact", "-flags:v", "+bitexact",
            str(out),
        ]  # fmt: skip
        subprocess.run(command, check=True)
        print(f"{clip['id']}: {out.stat().st_size} bytes sha256={sha256(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
