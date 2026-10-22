"""Encrypted SQLite ledger and durable inbox; one transaction owns each reducer update."""

import base64
import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .models import ApiError, ContractRecord, EventEnvelope

# Values written by earlier releases, matched by SHA-256 so ledgers stored before a rename keep loading.
LEGACY_VALUES = {
    "c7074a5723ea86eb288f1502061d6e255f9b90b0fc5d32d3264194ba47daaa1c": "REPLAY_VERIFIED",
    "b508cfaa7d3f814251cfb95ad84d4b54c18488779ea7261d878080f3f8069c1e": "LOCAL_DISPATCH",
    "4f3c7db21015ce07607c32239b8780c15b5b5d550cb680c0cef0574900a3227b": "EXPLICIT_INJECTED_FAILURE",
    "60d1ecdd2f224e4c80f88ab84605b1186cf251841998d819b3c86209067fe8b0": "STANDBY",
    "e23354601e9423babe2d7317f8fa6a54a16031b1a27d77984750dda8a950efb3": "RING_STANDBY",
    "518b51dc291a594d20507a08a15825e45ab281b3e0a0f00b35593ca4aaa197d1": "BEE_STANDBY",
    "5d81c0cdc5e50116525ae714ebbb625fc88d455251b61139dcc0729b06132ee2": "CAMERA_STANDBY",
    "fa6e1d936835d5f179a9def585e39e9c6336363aac38fbe0c3989ad459b9d464": "GUIDED",
    "82f411ec8a483c41210f71a7dfd3e440e0642a66f1fb470587d84da63f928a3e": "SCRIPTED_CAMERA",
    "e1fb9a43e812c48b605ba4f7996902e644b873082309f21d26efa57298781759": "SCRIPTED_SENSOR",
    "7969945cb522b3a3b7b3058b94b7288eab7aace38864fb825de4ea71e4336066": "SCRIPTED_CLIP_AVAILABLE",
    "2abc6669291b5be2dc761886c9d48dd4af5858eafee37539bc4bbe5b6fd7ab16": "SCRIPTED_MARKER_FRAMES",
    "531c20f432f212a05f160e00c408877e534807f5ecc147ae8934bb0529554397": "SCRIPTED_PIXELS",
    "50979cd3142c5be70dec167cc10766feffacc232ae2dbb1d7258f83c90f17f97": "SCRIPTED_FIXTURE",
    "573388ef3484a928383c8ecd67e2fcd348034b224512fb89799a372b8f17f741": "SCRIPTED_REPLAY",
    "9da9ab703b11ffb56a6e76eac46eee5c79a1f21667eb66be65f7c8bb5ed2d458": "SCRIPTED_OWNER_CONTEXT",
    "f156bc04d1c6405993e59bafbad7307d41f4c9d9c03fe02f6a7f4af9aead92a1": "SCRIPTED_AUTHORIZED_TRANSCRIPT",
    "6ffbbe12c3d609cbd5297aa4418f8371ce1ee554ce8b6919fee54d90398d44db": "SCRIPTED",
    "98f5067f9aa4332284111b2795b5dc2ba7ab197fd1455ab33e9f691524baed6d": "LOCAL_RECEIVER_ONLY",
    "174f07194398f40c7ae08953866c29ea59c776634af4663f5e3be2b29c1b00bc": "RECORDED_WORKOUT_VIDEO",
    "93779d352662d741819c11ec5f07fd227e819c74bd502e0457e9fa09736057a1": "RECORDED_WORKOUT_SOURCE",
    "0fc9c13eaf6d0f2eeea0c7cd7715adfc75333f1e96049832b53e68d42650150d": "RECORDED_WORKOUT",
    "d87e63e62ef134feea647da9bfe32e92ef62842b341a9ca83214acd0df74e2d2": "RECORDED WORKOUT",
    "b93c2b506419053b1861fa5f22882cd6976ebe0b6b0004ea4385c401d3b722d3": "GUIDED_ONLY",
    "7a2a1e9367a477b234b0039adda3a5630dde212059749e3558d5ebe4b6e436a0": "GUIDED_ONLY",
    "bf02c8c1c530182248201da1e5168ef0634206ed6a3e848cbd467c9855a699f0": "SCRIPTED",
    "cce7a2cf1ae045989cfc914fb95a41526f167a838b3c7d33745143614abace7c": "judge",
    "2a97516c354b68848cdbd8f54a226a0a55b21ed138e207ad6c5cbb9c00aa5aea": "guided",
    "95b7b75f3a31bc791944487a5a4785e1eb637bddf2c6f6307c7f034cb5e9bc33": "scripted-porch",
    "5c3487f7db7c8c6a46ffac4dfe56cfab922af3bc0f98154ad8226049af89b350": "scripted-calibrated-markers-v1",
    "cffe9b196ac28ab4a1b28ca4a72d47b99f0979d4a191c0d758cdedaa834f8b2c": "studio.recorded_workout_opened",
    "016bd86573597cf651cf4c627a8b46a6a589542c839364f751b0167f99577a93": "studio.recorded_workout_close_requested",
    "b5d54c39e66671c9731b9f471e585d8262cd4f54963f0c93082d8dcf334d4c78": "false_claim",
}


def upgrade_legacy(value):
    """Rewrite enum/label values from earlier releases to the current names (exact matches only)."""
    if isinstance(value, dict):
        return {k: upgrade_legacy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [upgrade_legacy(v) for v in value]
    if isinstance(value, str) and len(value) <= 64:
        return LEGACY_VALUES.get(hashlib.sha256(value.encode()).hexdigest(), value)
    return value


class UnitOfWork:
    def __init__(self, store):
        self.store = store

    def execute(self, *args):
        return self.store.db.execute(*args)

    def put_artifact(self, eid, household, mime, data, sha):
        encrypted = self.store.seal(data, f"artifact:{household}:{eid}")
        self.execute("INSERT INTO artifacts VALUES (?,?,?,?,?)", (eid, household, mime, encrypted, sha))

    def get_artifact(self, eid, household):
        row = self.execute("SELECT * FROM artifacts WHERE id=? AND household=?", (eid, household)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["data"] = self.store.open(row["data"], f"artifact:{household}:{eid}")
        return out


class Store:
    prefix = b"DIRL1:"

    def __init__(self, path: str, key_file=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        key_path = Path(key_file or str(path) + ".key")
        existing = Path(path).is_file()
        if existing and not key_path.exists() and os.getenv("ALLOW_LEGACY_LEDGER_MIGRATION") != "true":
            raise RuntimeError(
                "Existing ledger key is missing. Restore its key; legacy plaintext migration requires explicit opt-in."
            )
        if not key_path.exists():
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(AESGCM.generate_key(bit_length=256))
        # POSIX modes only; Windows relies on the profile directory ACL.
        if os.name != "nt" and key_path.stat().st_mode & 0o077:
            raise RuntimeError("Ledger key must be readable only by its owner (mode 0600).")
        key = key_path.read_bytes()
        if len(key) != 32:
            raise RuntimeError("Ledger encryption key must contain exactly 32 random bytes.")
        self.cipher = AESGCM(key)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        os.chmod(path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.uow = UnitOfWork(self)
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        PRAGMA secure_delete=ON;
        CREATE TABLE IF NOT EXISTS storage_meta (id INTEGER PRIMARY KEY, version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS households (id TEXT PRIMARY KEY, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS commands (household TEXT, key TEXT, fingerprint TEXT, response TEXT,
            PRIMARY KEY(household,key));
        CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, household TEXT NOT NULL,
            mime TEXT NOT NULL, data BLOB NOT NULL, sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT, household TEXT,
            role TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY, household TEXT NOT NULL, provider TEXT NOT NULL,
            fingerprint TEXT NOT NULL, payload TEXT, status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0, available REAL NOT NULL, lease_until REAL,
            received REAL NOT NULL, completed REAL, error_code TEXT);
        CREATE INDEX IF NOT EXISTS inbox_due ON inbox(status,available,lease_until);
        CREATE TABLE IF NOT EXISTS cloud_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, household TEXT NOT NULL,
            state TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
            error_code TEXT, completed REAL);
        CREATE TABLE IF NOT EXISTS provider_cursors (household TEXT, provider TEXT, cursor TEXT,
            PRIMARY KEY(household,provider));
        CREATE TABLE IF NOT EXISTS retention_tombstones (id TEXT PRIMARY KEY, household TEXT NOT NULL,
            sha256 TEXT NOT NULL, deleted REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS cloud_deletions (id INTEGER PRIMARY KEY AUTOINCREMENT, household TEXT NOT NULL,
            schedules TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
            error_code TEXT, requested REAL NOT NULL, completed REAL);
        """)
        # Upgrade the former local format once. Authentication is bound to record identity.
        with self.transaction() as db:
            migrated = db.execute("SELECT version FROM storage_meta WHERE id=1").fetchone()
            if migrated:
                # Never reinterpret damaged ciphertext as legacy plaintext on a later startup.
                return
            for row in db.execute("SELECT id,state FROM households").fetchall():
                if not row["state"].startswith(self.prefix.decode()):
                    db.execute(
                        "UPDATE households SET state=? WHERE id=?",
                        (self.encode(json.loads(row["state"]), f"state:{row['id']}"), row["id"]),
                    )
            for row in db.execute("SELECT * FROM artifacts").fetchall():
                if not bytes(row["data"]).startswith(self.prefix):
                    db.execute(
                        "UPDATE artifacts SET data=? WHERE id=?",
                        (self.seal(row["data"], f"artifact:{row['household']}:{row['id']}"), row["id"]),
                    )
            for row in db.execute("SELECT * FROM commands").fetchall():
                if not row["response"].startswith(self.prefix.decode()):
                    db.execute(
                        "UPDATE commands SET response=? WHERE household=? AND key=?",
                        (
                            self.encode(
                                json.loads(row["response"]), f"command:{row['household']}:{row['key']}"
                            ),
                            row["household"],
                            row["key"],
                        ),
                    )
            db.execute("INSERT INTO storage_meta VALUES (1,1)")
        # Existing backups need their own secure disposal policy.
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def seal(self, data, context):
        nonce = os.urandom(12)
        return self.prefix + nonce + self.cipher.encrypt(nonce, bytes(data), context.encode())

    def open(self, data, context):
        try:
            if not bytes(data).startswith(self.prefix):
                raise ValueError
            ciphertext = bytes(data)[len(self.prefix) :]
            return self.cipher.decrypt(ciphertext[:12], ciphertext[12:], context.encode())
        except (InvalidTag, ValueError):
            raise ApiError(409, "EVIDENCE_TAMPERED", "Encrypted ledger integrity check failed.") from None

    def encode(self, value, context):
        data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
        return self.prefix.decode() + base64.b64encode(self.seal(data, context)).decode()

    def decode(self, value, context):
        try:
            if not value.startswith(self.prefix.decode()):
                raise ValueError
            data = base64.b64decode(value[len(self.prefix) :], validate=True)
            return json.loads(self.open(data, context))
        except (ValueError, TypeError):
            raise ApiError(409, "EVIDENCE_TAMPERED", "Encrypted ledger integrity check failed.") from None

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.uow
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def read(self, household):
        with self.lock:
            row = self.db.execute("SELECT state FROM households WHERE id=?", (household,)).fetchone()
            return upgrade_legacy(self.decode(row["state"], f"state:{household}")) if row else None

    def save(self, db, household, state):
        for contract in state["contracts"]:
            ContractRecord.model_validate(contract)
        for event in state["events"]:
            EventEnvelope.model_validate(event)
        db.execute(
            "INSERT INTO households VALUES (?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
            (household, self.encode(state, f"state:{household}")),
        )
        if os.getenv("AWS_LEDGER_TABLE"):
            db.execute(
                "INSERT INTO cloud_outbox(household,state) VALUES (?,?)",
                (household, self.encode(state, f"state:{household}")),
            )

    def enqueue(self, db, household, provider, event_id, payload, now):
        identity = hashlib.sha256(f"{household}:{provider}:{event_id}".encode()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        previous = db.execute("SELECT fingerprint FROM inbox WHERE id=?", (identity,)).fetchone()
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise ApiError(
                    409, "PROVIDER_EVENT_CONFLICT", "Event identity was reused with another payload."
                )
            return identity, False
        db.execute(
            "INSERT INTO inbox(id,household,provider,fingerprint,payload,available,received) "
            "VALUES (?,?,?,?,?,?,?)",
            (identity, household, provider, fingerprint, self.encode(payload, f"inbox:{identity}"), now, now),
        )
        return identity, True

    def purge_expired(self, db, now):
        deleted = 0
        for row in db.execute("SELECT id FROM households").fetchall():
            s = self.read(row["id"])
            for item in s["evidence"]:
                if datetime.fromisoformat(item["retention_expires_at"]).timestamp() > now:
                    continue
                result = db.execute(
                    "DELETE FROM artifacts WHERE id=? AND household=?", (item["evidence_id"], row["id"])
                )
                if result.rowcount:
                    db.execute(
                        "INSERT OR IGNORE INTO retention_tombstones VALUES (?,?,?,?)",
                        (item["evidence_id"], row["id"], item["sha256_original"], now),
                    )
                    deleted += 1
        db.execute("DELETE FROM sessions WHERE expires < ?", (now,))
        return deleted
