import hashlib
import time
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

from done_irl import engine as e
from done_irl.aws_runtime import AWSRuntime
from done_irl.store import Store


@pytest.fixture
def aws(tmp_path, monkeypatch):
    monkeypatch.delenv("AWS_PROFILE", raising=False)  # Moto only; no network or cloud identity.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_LEDGER_TABLE", "ledger-test")
    with mock_aws():
        session = boto3.Session(region_name="us-east-1")
        session.client("dynamodb").create_table(
            TableName="ledger-test",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )
        session.client("s3").create_bucket(Bucket="done-irl-evidence-test")
        queue = session.client("sqs").create_queue(QueueName="wake-test")["QueueUrl"]
        store = Store(str(tmp_path / "source.db"))
        cloud = AWSRuntime(
            store,
            table="ledger-test",
            bucket="done-irl-evidence-test",
            queue_url=queue,
            scheduler_role="arn:aws:iam::123456789012:role/scheduler",
            queue_arn="arn:aws:sqs:us-east-1:123456789012:wake-test",
            session=session,
        )
        yield store, cloud


def snapshot(store):
    state = e.fresh()
    state["household_id"] = "house_owner"
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    c = e.create_contract(
        state, "teacher", "Meeting", "I'll attend", "Teacher", "BEE_CONVERSATION_AUDIT", due=future
    )
    with store.transaction() as db:
        e.add_evidence(state, db, "house_owner", c, "TEST_SNAPSHOT", b"private-media")
        store.save(db, "house_owner", state)
    return state


def test_cloud_outbox_private_encrypted_media_and_explicit_query_patterns(aws):
    store, cloud = aws
    state = snapshot(store)
    assert cloud.flush() == 1
    assert cloud.flush() == 0
    from boto3.dynamodb.conditions import Key

    for prefix in ["CONTRACT#", "AGENT#", "EVIDENCE#", "AUDIT#"]:
        rows = cloud.table.query(
            KeyConditionExpression=Key("pk").eq("HOUSE#house_owner") & Key("sk").begins_with(prefix)
        )["Items"]
        assert rows
        assert all("utterance" not in item and "data" not in item for item in rows)
    item = state["evidence"][0]
    raw = cloud.s3.get_object(Bucket=cloud.bucket, Key=f"house_owner/evidence/{item['evidence_id']}.enc")[
        "Body"
    ].read()
    assert b"private-media" not in raw
    assert (
        hashlib.sha256(store.open(raw, f"artifact:house_owner:{item['evidence_id']}")).hexdigest()
        == item["sha256_original"]
    )
    assert len(cloud.scheduler.list_schedules()["Schedules"]) == 3


def test_stale_cloud_snapshot_cannot_regress_newer_revision(aws):
    store, cloud = aws
    state = snapshot(store)
    old = dict(store.db.execute("SELECT * FROM cloud_outbox LIMIT 1").fetchone())
    state["contracts"][0]["status"] = "ENGAGED"
    with store.transaction() as db:
        store.save(db, "house_owner", state)
    assert cloud.flush() == 1  # The latest complete snapshot safely subsumes pending older ones.
    cloud.publish(old)
    pointer = cloud.table.get_item(Key={"pk": "HOUSE#house_owner", "sk": "SNAPSHOT"})["Item"]
    assert pointer["revision"] == 2
    contract = cloud.table.get_item(Key={"pk": "HOUSE#house_owner", "sk": "CONTRACT#psc_teacher"})["Item"]
    assert contract["status"] == "ENGAGED"


def test_s3_failure_keeps_outbox_for_retry(aws, monkeypatch):
    store, cloud = aws
    snapshot(store)
    real = cloud.put_blob

    def failed(*args):
        raise OSError("injected private storage failure")

    monkeypatch.setattr(cloud, "put_blob", failed)
    with pytest.raises(OSError):
        cloud.flush()
    row = store.db.execute("SELECT * FROM cloud_outbox").fetchone()
    assert row["status"] == "PENDING" and row["attempts"] == 1
    assert row["error_code"] == "OSError"
    assert "Item" not in cloud.table.get_item(Key={"pk": "HOUSE#house_owner", "sk": "SNAPSHOT"})
    monkeypatch.setattr(cloud, "put_blob", real)
    assert cloud.flush() == 1


def test_disaster_restore_checks_hash_key_and_refuses_overwrite(aws, tmp_path):
    store, cloud = aws
    expected = snapshot(store)
    cloud.flush()
    key = tmp_path / "recovery.key"
    key.write_bytes((tmp_path / "source.db.key").read_bytes())
    key.chmod(0o600)
    recovered = Store(str(tmp_path / "recovered.db"), key_file=str(key))
    cloud.store = recovered
    assert cloud.restore("house_owner") == expected
    assert e.verify_artifacts(recovered.read("house_owner"), recovered.uow, "house_owner")
    with pytest.raises(RuntimeError, match="existing household"):
        cloud.restore("house_owner")
    with recovered.transaction() as db:
        recovered.save(db, "house_owner", expected)
    assert recovered.db.execute("SELECT MAX(id) AS id FROM cloud_outbox").fetchone()["id"] == 2


def test_scheduler_wakeup_cannot_supply_verifier_state(aws):
    _, cloud = aws

    class Worker:
        calls = 0

        def step(self):
            self.calls += 1

    worker = Worker()
    cloud.sqs.send_message(
        QueueUrl=cloud.queue_url,
        MessageBody='{"schema_version":"1.0","household":"house_owner","status":"VERIFIED"}',
    )
    assert cloud.wake(worker) == 1
    assert worker.calls == 1
    assert not cloud.sqs.receive_message(QueueUrl=cloud.queue_url).get("Messages")


def test_cancelled_contract_removes_all_durable_schedules(aws):
    store, cloud = aws
    state = snapshot(store)
    cloud.flush()
    state["contracts"][0]["status"] = "CANCELLED"
    with store.transaction() as db:
        store.save(db, "house_owner", state)
    cloud.flush()
    assert cloud.scheduler.list_schedules()["Schedules"] == []


def test_expired_evidence_is_not_restored_from_cloud(aws, tmp_path):
    store, cloud = aws
    state = snapshot(store)
    cloud.flush()
    # A future recovery must not resurrect media past its original retention cutoff.
    future = time.time() + 8 * 86400
    from unittest.mock import patch

    restored = Store(str(tmp_path / "after-retention.db"), key_file=str(tmp_path / "source.db.key"))
    cloud.store = restored
    with patch("done_irl.aws_runtime.time.time", return_value=future):
        cloud.restore("house_owner")
    assert not restored.db.execute("SELECT id FROM artifacts").fetchone()
    assert restored.read("house_owner")["evidence"] == state["evidence"]


def test_cloud_purge_deletes_all_expired_media_versions_without_refreshing_age(aws):
    store, cloud = aws
    state = snapshot(store)
    cloud.flush()
    key = "house_owner/evidence/" + state["evidence"][0]["evidence_id"] + ".enc"
    # A retry keeps the immutable object, rather than extending its lifetime with a new version.
    row = store.db.execute("SELECT * FROM cloud_outbox LIMIT 1").fetchone()
    cloud.publish(row)
    state["evidence"][0]["retention_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    with store.transaction() as db:
        store.save(db, "house_owner", state)
    cloud.purge()
    assert not cloud.s3.list_objects_v2(Bucket=cloud.bucket, Prefix=key).get("Contents")
    cloud.flush()  # Expired local data cannot be uploaded again.
    assert not cloud.s3.list_objects_v2(Bucket=cloud.bucket, Prefix=key).get("Contents")


def house_snapshot(store, household):
    state = e.fresh()
    state["household_id"] = household
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    c = e.create_contract(
        state, "teacher", "Meeting", "I'll attend", "Teacher", "BEE_CONVERSATION_AUDIT", due=future
    )
    with store.transaction() as db:
        e.add_evidence(state, db, household, c, "TEST_SNAPSHOT", b"private-media-" + household.encode())
        store.save(db, household, state)
    return state


def test_household_deletion_erases_only_that_households_cloud_objects(aws):
    from boto3.dynamodb.conditions import Key

    from done_irl import privacy
    from done_irl.aws_runtime import schedule_name

    store, cloud = aws
    house_snapshot(store, "house_owner")
    # A prefix-sharing household id must survive: "house_owner/" never matches "house_owner2/".
    other = house_snapshot(store, "house_owner2")
    assert cloud.flush() == 2
    assert len(cloud.scheduler.list_schedules()["Schedules"]) == 6

    def objects(prefix):
        page = cloud.s3.list_object_versions(Bucket=cloud.bucket, Prefix=prefix)
        return [o["Key"] for o in [*page.get("Versions", []), *page.get("DeleteMarkers", [])]]

    def items(household):
        return cloud.table.query(KeyConditionExpression=Key("pk").eq("HOUSE#" + household))["Items"]

    other_objects, other_items = objects("house_owner2/"), items("house_owner2")
    assert any("/evidence/" in key for key in objects("house_owner/"))
    with store.transaction() as db:
        state = store.read("house_owner")
        receipt = privacy.delete_household(state, db, "house_owner", e.fresh())
        store.save(db, "house_owner", state)
    assert receipt["cloud_deletion"] == "QUEUED"
    assert cloud.flush() == 1  # Erase first, then publish only the minimal receipt snapshot.
    remaining = objects("house_owner/")
    assert remaining and all(key.startswith("house_owner/snapshots/") for key in remaining)
    assert {item["sk"] for item in items("house_owner")} == {"SNAPSHOT", "AUDIT#evt_000001"}
    restored = cloud.store.decode(
        cloud.s3.get_object(Bucket=cloud.bucket, Key=remaining[0])["Body"].read().decode(),
        "state:house_owner",
    )
    assert restored["contracts"] == [] and restored["deletion_receipts"] == [receipt]
    names = {s["Name"] for s in cloud.scheduler.list_schedules()["Schedules"]}
    assert names == {
        schedule_name("house_owner2", c["contract_id"], job["kind"])
        for c in other["contracts"]
        for job in c["scheduled_jobs"]
    }
    assert objects("house_owner2/") == other_objects and items("house_owner2") == other_items
    row = store.db.execute("SELECT status,attempts FROM cloud_deletions").fetchone()
    assert tuple(row) == ("DONE", 0)


def test_failed_cloud_erase_blocks_republish_and_retries(aws, monkeypatch):
    from done_irl import privacy

    store, cloud = aws
    house_snapshot(store, "house_owner")
    cloud.flush()
    with store.transaction() as db:
        state = store.read("house_owner")
        privacy.delete_household(state, db, "house_owner", e.fresh())
        store.save(db, "house_owner", state)
    real = cloud.s3.delete_objects

    def failed(**kwargs):
        raise OSError("injected deletion failure")

    monkeypatch.setattr(cloud.s3, "delete_objects", failed)
    with pytest.raises(OSError):
        cloud.flush()
    row = store.db.execute("SELECT status,attempts,error_code FROM cloud_deletions").fetchone()
    assert tuple(row) == ("PENDING", 1, "OSError")
    assert store.db.execute("SELECT status FROM cloud_outbox").fetchone()["status"] == "PENDING"
    monkeypatch.setattr(cloud.s3, "delete_objects", real)
    assert cloud.flush() == 1
    assert store.db.execute("SELECT status FROM cloud_deletions").fetchone()["status"] == "DONE"
