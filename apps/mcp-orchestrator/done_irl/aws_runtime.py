"""Optional AWS durable projection, private evidence replica and scheduled wakeups.

The single active SQLite reducer remains authoritative. Its transactional outbox makes
AWS delivery retryable; DynamoDB conditional writes fence stale snapshots. This is not
a multi-writer database replacement. Deploy one active reducer per ledger volume.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone


def schedule_name(household, contract_id, kind):
    return "dirl-" + hashlib.sha256(f"{household}:{contract_id}:{kind}".encode()).hexdigest()[:48]


class AWSRuntime:
    def __init__(
        self,
        store,
        region=None,
        table=None,
        bucket=None,
        queue_url=None,
        scheduler_role=None,
        queue_arn=None,
        session=None,
    ):
        import boto3

        self.store = store
        self.session = session or boto3.Session(region_name=region or os.getenv("AWS_REGION"))
        self.table = self.session.resource("dynamodb").Table(table or os.environ["AWS_LEDGER_TABLE"])
        self.s3 = self.session.client("s3")
        self.sqs = self.session.client("sqs")
        self.scheduler = self.session.client("scheduler")
        self.bucket = bucket or os.environ["S3_EVIDENCE_BUCKET"]
        self.queue_url = queue_url or os.environ["AWS_WAKE_QUEUE_URL"]
        self.queue_arn = queue_arn or os.environ["AWS_WAKE_QUEUE_ARN"]
        self.scheduler_role = scheduler_role or os.environ["AWS_SCHEDULER_ROLE_ARN"]

    def put_blob(self, key, data):
        # SSE-KMS is configured by bucket policy/default encryption, in addition to local AES-GCM.
        sha = hashlib.sha256(data).hexdigest()
        from botocore.exceptions import ClientError

        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                Metadata={"sha256": sha},
                ContentType="application/octet-stream",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"PreconditionFailed", "412"}:
                raise
            existing = self.s3.head_object(Bucket=self.bucket, Key=key)
            if existing.get("Metadata", {}).get("sha256") != sha:
                raise RuntimeError("Immutable cloud object hash differs.") from None
        return sha

    def publish(self, row):
        from botocore.exceptions import ClientError

        household, revision = row["household"], int(row["id"])
        state = self.store.decode(row["state"], f"state:{household}")
        pk = "HOUSE#" + household
        key = f"{household}/snapshots/{revision}.enc"
        sha = self.put_blob(key, row["state"].encode())
        for item in state["evidence"]:
            with self.store.lock:
                artifact = self.store.db.execute(
                    "SELECT * FROM artifacts WHERE id=? AND household=?", (item["evidence_id"], household)
                ).fetchone()
            if artifact and datetime.fromisoformat(item["retention_expires_at"]).timestamp() > time.time():
                self.put_blob(f"{household}/evidence/{item['evidence_id']}.enc", bytes(artifact["data"]))
        # A snapshot pointer is published only after all available artifacts have reached S3.
        # Retries can rewrite identical bytes; stale revisions cannot replace a newer pointer.
        try:
            self.table.put_item(
                Item={
                    "pk": pk,
                    "sk": "SNAPSHOT",
                    "revision": revision,
                    "object_key": key,
                    "sha256": sha,
                    "updated_at": int(time.time()),
                },
                ConditionExpression="attribute_not_exists(revision) OR revision <= :revision",
                ExpressionAttributeValues={":revision": revision},
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return
            raise
        # Explicit single-table access patterns: query HOUSE#id with CONTRACT#, AGENT#,
        # INCIDENT#, EVIDENCE# or AUDIT# prefix. No transcript/PII is indexed in plaintext.
        records = [
            ("CONTRACT#", state["contracts"], "contract_id"),
            ("AGENT#", state["subagents"], "subagent_id"),
            ("INCIDENT#", state["incidents"], "incident_id"),
            ("EVIDENCE#", state["evidence"], "evidence_id"),
            ("AUDIT#", state["events"], "event_id"),
        ]
        for prefix, items, identity in records:
            for item in items:
                projected = {"pk": pk, "sk": prefix + item[identity], "revision": revision}
                for field in ("status", "source_mode", "due_at", "event_type", "sha256_original"):
                    if item.get(field) is not None:
                        projected[field] = item[field]
                try:
                    self.table.put_item(
                        Item=projected,
                        ConditionExpression="attribute_not_exists(revision) OR revision <= :revision",
                        ExpressionAttributeValues={":revision": revision},
                    )
                except ClientError as error:
                    if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                        raise
        for contract in state["contracts"]:
            self.schedules(household, contract)

    def schedules(self, household, contract):
        from botocore.exceptions import ClientError

        for job in contract["scheduled_jobs"]:
            name = schedule_name(household, contract["contract_id"], job["kind"])
            future = datetime.fromisoformat(job["at"]).timestamp() > time.time()
            active = job["status"] == "PENDING" and contract["status"] not in {
                "VERIFIED",
                "CANCELLED",
                "REJECTED",
            }
            if not future or not active:
                try:
                    self.scheduler.delete_schedule(Name=name)
                except ClientError as error:
                    if error.response["Error"]["Code"] != "ResourceNotFoundException":
                        raise
                continue
            when = (
                datetime.fromisoformat(job["at"])
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
                .isoformat(timespec="seconds")
            )
            params = dict(
                Name=name,
                ScheduleExpression=f"at({when})",
                ScheduleExpressionTimezone="UTC",
                FlexibleTimeWindow={"Mode": "OFF"},
                ActionAfterCompletion="DELETE",
                Target={
                    "Arn": self.queue_arn,
                    "RoleArn": self.scheduler_role,
                    "Input": json.dumps(
                        {
                            "schema_version": "1.0",
                            "household": household,
                            "contract_id": contract["contract_id"],
                            "kind": job["kind"],
                        }
                    ),
                    "RetryPolicy": {"MaximumEventAgeInSeconds": 3600, "MaximumRetryAttempts": 3},
                },
            )
            try:
                self.scheduler.create_schedule(**params)
            except ClientError as error:
                if error.response["Error"]["Code"] != "ConflictException":
                    raise
                self.scheduler.update_schedule(**params)

    def purge(self):
        # Remove all versions of expired media; S3 lifecycle is an additional backstop.
        with self.store.lock:
            households = [row["id"] for row in self.store.db.execute("SELECT id FROM households").fetchall()]
        for household in households:
            state = self.store.read(household)
            for item in state["evidence"]:
                if datetime.fromisoformat(item["retention_expires_at"]).timestamp() > time.time():
                    continue
                key = f"{household}/evidence/{item['evidence_id']}.enc"
                paginator = self.s3.get_paginator("list_object_versions")
                for page in paginator.paginate(Bucket=self.bucket, Prefix=key):
                    objects = [
                        {"Key": obj["Key"], "VersionId": obj["VersionId"]}
                        for obj in [*page.get("Versions", []), *page.get("DeleteMarkers", [])]
                        if obj["Key"] == key
                    ]
                    if objects:
                        self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})
        with self.store.transaction() as db:
            db.execute(
                "DELETE FROM cloud_outbox WHERE status='DONE' AND completed<?", (time.time() - 7 * 86400,)
            )

    def erase(self):
        """Process owner household-deletion requests before any newer snapshot is republished."""
        from boto3.dynamodb.conditions import Key
        from botocore.exceptions import ClientError

        with self.store.lock:
            rows = [
                dict(row)
                for row in self.store.db.execute(
                    "SELECT * FROM cloud_deletions WHERE status='PENDING' ORDER BY id"
                ).fetchall()
            ]
        erased = 0
        for row in rows:
            household = row["household"]
            try:
                # Trailing slash: house_a/ never matches house_ab/. All versions and delete markers go.
                paginator = self.s3.get_paginator("list_object_versions")
                for page in paginator.paginate(Bucket=self.bucket, Prefix=household + "/"):
                    objects = [
                        {"Key": obj["Key"], "VersionId": obj["VersionId"]}
                        for obj in [*page.get("Versions", []), *page.get("DeleteMarkers", [])]
                        if obj["Key"].startswith(household + "/")
                    ]
                    for start in range(0, len(objects), 1000):
                        self.s3.delete_objects(
                            Bucket=self.bucket, Delete={"Objects": objects[start : start + 1000]}
                        )
                query = {"KeyConditionExpression": Key("pk").eq("HOUSE#" + household), "ConsistentRead": True}
                while True:
                    page = self.table.query(**query)
                    # Single-item deletes: the service role is scoped to DeleteItem, not BatchWriteItem.
                    for item in page.get("Items", []):
                        self.table.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                    if "LastEvaluatedKey" not in page:
                        break
                    query["ExclusiveStartKey"] = page["LastEvaluatedKey"]
                for name in json.loads(row["schedules"]):
                    try:
                        self.scheduler.delete_schedule(Name=name)
                    except ClientError as error:
                        if error.response["Error"]["Code"] != "ResourceNotFoundException":
                            raise
            except Exception as error:
                with self.store.transaction() as db:
                    db.execute(
                        "UPDATE cloud_deletions SET attempts=attempts+1,error_code=? WHERE id=?",
                        (type(error).__name__, row["id"]),
                    )
                raise
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE cloud_deletions SET status='DONE',completed=?,error_code=NULL WHERE id=?",
                    (time.time(), row["id"]),
                )
            erased += 1
        return erased

    def flush(self, limit=10):
        # Deletion first: a failed erase blocks republishing the household's post-deletion receipt.
        self.erase()
        self.purge()
        # Refresh snapshots daily so the seven-day bucket lifecycle preserves a current backup.
        with self.store.transaction() as db:
            for household in db.execute("SELECT id FROM households").fetchall():
                latest = db.execute(
                    "SELECT MAX(completed) AS completed FROM cloud_outbox WHERE household=?",
                    (household["id"],),
                ).fetchone()["completed"]
                pending = db.execute(
                    "SELECT id FROM cloud_outbox WHERE household=? AND status='PENDING' LIMIT 1",
                    (household["id"],),
                ).fetchone()
                if not pending and (latest is None or latest < time.time() - 86400):
                    self.store.save(db, household["id"], self.store.read(household["id"]))
        sent = 0
        for _ in range(limit):
            with self.store.lock:
                row = self.store.db.execute(
                    "SELECT * FROM cloud_outbox WHERE id IN (SELECT MAX(id) FROM cloud_outbox "
                    "WHERE status='PENDING' GROUP BY household) ORDER BY id LIMIT 1"
                ).fetchone()
            if not row:
                break
            try:
                self.publish(row)
            except Exception as error:
                # Keep durable work for retry. No payload/credential content in operational diagnostics.
                with self.store.transaction() as db:
                    db.execute(
                        "UPDATE cloud_outbox SET attempts=attempts+1,error_code=? WHERE id=?",
                        (type(error).__name__, row["id"]),
                    )
                raise
            with self.store.transaction() as db:
                db.execute(
                    "UPDATE cloud_outbox SET status='DONE',completed=?,error_code=NULL WHERE household=? AND id<=?",
                    (time.time(), row["household"], row["id"]),
                )
            sent += 1
        return sent

    def wake(self, runtime):
        messages = self.sqs.receive_message(
            QueueUrl=self.queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=1, VisibilityTimeout=60
        ).get("Messages", [])
        for message in messages:
            try:
                payload = json.loads(message["Body"])
                if payload["schema_version"] != "1.0" or not isinstance(payload["household"], str):
                    continue  # Invalid messages exhaust their receive budget and enter the configured DLQ.
                # A scheduler hint cannot supply observations, client time or verifier state.
                runtime.step()
                self.sqs.delete_message(QueueUrl=self.queue_url, ReceiptHandle=message["ReceiptHandle"])
            except (ValueError, TypeError, KeyError):
                continue
        return len(messages)

    def restore(self, household):
        """Restore an absent household from its encrypted, hash-checked snapshot; never overwrite local state."""
        pointer = self.table.get_item(
            Key={"pk": "HOUSE#" + household, "sk": "SNAPSHOT"}, ConsistentRead=True
        ).get("Item")
        if not pointer:
            raise RuntimeError("No cloud snapshot exists for this household.")
        data = self.s3.get_object(Bucket=self.bucket, Key=pointer["object_key"])["Body"].read()
        if hashlib.sha256(data).hexdigest() != pointer["sha256"]:
            raise RuntimeError("Cloud snapshot integrity check failed.")
        state = self.store.decode(data.decode(), f"state:{household}")
        if state["household_id"] != household:
            raise RuntimeError("Cloud snapshot belongs to another household.")
        artifacts = []
        for item in state["evidence"]:
            if datetime.fromisoformat(item["retention_expires_at"]).timestamp() <= time.time():
                continue
            data = self.s3.get_object(
                Bucket=self.bucket, Key=f"{household}/evidence/{item['evidence_id']}.enc"
            )["Body"].read()
            plain = self.store.open(data, f"artifact:{household}:{item['evidence_id']}")
            if hashlib.sha256(plain).hexdigest() != item["sha256_original"]:
                raise RuntimeError("Cloud evidence integrity check failed.")
            artifacts.append((item["evidence_id"], household, item["mime"], data, item["sha256_original"]))
        with self.store.transaction() as db:
            if self.store.read(household):
                raise RuntimeError("Restore refuses to replace an existing household.")
            for artifact in artifacts:
                db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?)", artifact)
            for item in state["evidence"]:
                if datetime.fromisoformat(item["retention_expires_at"]).timestamp() <= time.time():
                    db.execute(
                        "INSERT OR IGNORE INTO retention_tombstones VALUES (?,?,?,?)",
                        (item["evidence_id"], household, item["sha256_original"], time.time()),
                    )
            # Preserve global outbox revision monotonicity after disaster recovery.
            db.execute(
                "INSERT INTO cloud_outbox(id,household,state,status,completed) VALUES (?,?,?,'DONE',?)",
                (
                    int(pointer["revision"]),
                    household,
                    self.store.encode(state, f"state:{household}"),
                    time.time(),
                ),
            )
            db.execute(
                "INSERT INTO households VALUES (?,?)",
                (household, self.store.encode(state, f"state:{household}")),
            )
        return state
