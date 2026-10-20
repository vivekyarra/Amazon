"""Create an isolated validation container/volume, prove restart durability, remove only those resources."""

import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import httpx

suffix = uuid.uuid4().hex[:10]
name = "done-irl-check-" + suffix
volume = name + "-data"
environment = {**os.environ, "DOCKER_CONFIG": os.environ.get("DOCKER_CONFIG", "/workspace/.cache/docker")}


def docker(*args):
    return subprocess.check_output(["docker", *args], env=environment, text=True).strip()


def ready(client):
    for _ in range(100):
        try:
            if client.get("/health/ready").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Container readiness timed out")


created = False
try:
    docker("volume", "create", volume)
    docker(
        "run",
        "--detach",
        "--name",
        name,
        "--publish",
        "127.0.0.1::8080",
        "--mount",
        f"type=volume,source={volume},target=/data",
        "done-irl:validation",
    )
    created = True
    port = int(docker("port", name, "8080/tcp").rsplit(":", 1)[1])
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60) as client:
        ready(client)
        credentials = json.loads(docker("exec", name, "cat", "/data/access.json"))

        def login():
            response = client.post(
                "/api/auth/login", json={"username": "demo-admin", "password": credentials["demo-admin"]}
            )
            response.raise_for_status()

        login()

        def command(path, body=None):
            response = client.post(
                "/api" + path, json=body or {}, headers={"Idempotency-Key": uuid.uuid4().hex}
            )
            response.raise_for_status()
            return response.json()["state"]

        for i in range(1, 7):
            command(f"/admin/scenarios/{i}/run", {"branch": "unknown" if i == 4 else "deposit"})
        for _ in range(15):
            state = command("/admin/studio/rep")
        contracts = {c["key"]: c["status"] for c in state["contracts"]}
        assert contracts == {
            "drinks": "ACTIVE",
            "sister": "MISSED",
            "teacher": "VERIFIED",
            "squats": "VERIFIED",
            "parcel": "DISPUTED",
        }, contracts
        assert state["studio"]["count"] == 15
        assert state["incidents"][0]["clip_actual_duration_seconds"] == 15
        assert client.get("/api/export").status_code == 200
        docker("restart", name)
        # Docker may allocate a new port for an ephemeral host binding on restart.
        restarted_port = int(docker("port", name, "8080/tcp").rsplit(":", 1)[1])
        client.base_url = f"http://127.0.0.1:{restarted_port}"
        ready(client)
        login()
        restored = client.get("/api/state").json()["state"]
        assert restored["contracts"] == state["contracts"]
        assert restored["studio"]["gate"] == "UNLOCKED"
        report = {
            "result": "PASS",
            "image": docker("image", "inspect", "done-irl:validation", "--format", "{{.Id}}"),
            "contracts": contracts,
            "rep_count": 15,
            "restart_durable": True,
            "source": "SYNTHETIC",
            "official_dispatches": 0,
        }
        Path("artifacts/container").mkdir(parents=True, exist_ok=True)
        Path("artifacts/container/result.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
except Exception:
    if created:
        logs = docker("logs", name)
        Path("artifacts/container").mkdir(parents=True, exist_ok=True)
        Path("artifacts/container/error.log").write_text(logs)
        print(logs[-4000:])
    raise
finally:
    if created:
        docker("rm", "--force", name)
    docker("volume", "rm", volume)
