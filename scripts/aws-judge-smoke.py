"""End-to-end smoke test of a deployed judge stack, with AWS-side verification.

Usage:
  DONE_URL=https://<ip>.sslip.io DEMO_ADMIN_PASSWORD=... AWS_REGION=us-east-1 \
  uv run --extra aws python scripts/aws-judge-smoke.py --stack done-irl-judge [--out docs/evidence/aws-deployment.json]

Runs the six canonical stages through the public HTTPS API, then reads the stack's DynamoDB
projection, S3 evidence objects, SQS wake queue and EventBridge schedules to prove the cloud
coordination is real. Writes a report with identifiers and counts only (no secrets, no media).
"""

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", default="done-irl-judge")
    ap.add_argument("--out", default="docs/evidence/aws-deployment.json")
    args = ap.parse_args()
    url = os.environ["DONE_URL"].rstrip("/")
    region = os.getenv("AWS_REGION", "us-east-1")
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "url": url, "region": region, "stages": []}
    c = httpx.Client(base_url=url, timeout=60, headers={"Origin": url})

    def post(path, body=None):
        r = c.post("/api" + path, json=body or {}, headers={"Idempotency-Key": uuid.uuid4().hex})
        r.raise_for_status()
        return r.json()

    report["health_ready"] = c.get("/health/ready").json()
    post("/auth/login", {"username": "demo-admin", "password": os.environ["DEMO_ADMIN_PASSWORD"]})
    post("/admin/reset")
    for stage, branch in [(1, "deposit"), (2, "deposit"), (3, "disengaged"), (4, "unknown"), (5, "empty"), (6, "deposit")]:
        t0 = time.monotonic()
        s = post(f"/admin/scenarios/{stage}/run", {"branch": branch})["state"]
        report["stages"].append({"stage": stage, "branch": branch, "ms": round((time.monotonic() - t0) * 1000)})
    for _ in range(15):
        s = post("/admin/studio/rep")["state"]
    final = {c_["key"]: c_["status"] for c_ in s["contracts"]}
    report["final_contract_status"] = final
    report["studio"] = {k: (s.get("studio") or {}).get(k) for k in ("count", "status", "gate")}
    report["incidents"] = [{"status": i["status"], "quality": i.get("quality")} for i in s["incidents"]]
    report["evidence_items"] = len(s["evidence"])

    cf = boto3.client("cloudformation", region_name=region)
    out = {o["OutputKey"]: o["OutputValue"] for o in cf.describe_stacks(StackName=args.stack)["Stacks"][0]["Outputs"]}
    time.sleep(20)  # allow the cloud outbox worker to flush
    table = boto3.resource("dynamodb", region_name=region).Table(out["LedgerTable"])
    items = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq("HOUSE#demo"))["Items"]
    prefixes = {}
    for item in items:
        prefixes[item["sk"].split("#")[0]] = prefixes.get(item["sk"].split("#")[0], 0) + 1
    report["dynamodb"] = {"table": out["LedgerTable"], "items_for_demo_household": len(items), "by_sort_prefix": prefixes}
    s3 = boto3.client("s3", region_name=region)
    objs = s3.list_objects_v2(Bucket=out["EvidenceBucket"], Prefix="").get("KeyCount", 0)
    enc = None
    listing = s3.list_objects_v2(Bucket=out["EvidenceBucket"], MaxKeys=1).get("Contents", [])
    if listing:
        enc = s3.head_object(Bucket=out["EvidenceBucket"], Key=listing[0]["Key"]).get("ServerSideEncryption")
    report["s3"] = {"bucket": out["EvidenceBucket"], "object_count": objs, "server_side_encryption": enc}
    sched = boto3.client("scheduler", region_name=region)
    names = [x["Name"] for x in sched.list_schedules(NamePrefix="dirl-", MaxResults=100)["Schedules"]]
    report["eventbridge_scheduler"] = {"dirl_schedules": len(names)}
    sqs = boto3.client("sqs", region_name=region)
    attrs = sqs.get_queue_attributes(QueueUrl=out["WakeQueueUrl"], AttributeNames=["All"])["Attributes"]
    report["sqs_wake_queue"] = {k: attrs.get(k) for k in ("ApproximateNumberOfMessages", "KmsMasterKeyId", "RedrivePolicy")}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("final_contract_status", "studio", "dynamodb", "s3", "eventbridge_scheduler")},
                     default=str))


if __name__ == "__main__":
    main()
