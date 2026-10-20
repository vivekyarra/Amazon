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
        if key_path.stat().st_mode & 0o077:
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
            return self.decode(row["state"], f"state:{household}") if row else None

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
