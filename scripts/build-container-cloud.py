"""Build using the configured cloud proxy and public system CA bundle, preserving TLS.

No credentials or CA material are copied into the repository or final image.
The optional BuildKit mount contains public trust certificates, not secret values.
"""

import argparse
import os
from pathlib import Path
import socket
import ssl
import subprocess
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument("--tag", default="done-irl:validation")
parser.add_argument("--live-runtime", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
environment = {**os.environ, "DOCKER_CONFIG": os.environ.get("DOCKER_CONFIG", "/workspace/.cache/docker")}
command = ["docker", "build"]
if args.live_runtime:
    command += ["--build-arg", "ENABLE_LIVE_RUNTIME=true"]
proxy = urlsplit(os.environ.get("HTTPS_PROXY", ""))
if proxy.hostname:
    command += [
        "--network",
        "host",
        "--add-host",
        proxy.hostname + ":" + socket.gethostbyname(proxy.hostname),
    ]
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        command += ["--build-arg", name]
    bundle = ssl.get_default_verify_paths().cafile
    if bundle:
        command += ["--secret", "id=proxy_ca,src=" + bundle]
command += ["-f", "infra/local/Dockerfile", "-t", args.tag, "."]
raise SystemExit(subprocess.call(command, cwd=root, env=environment))
