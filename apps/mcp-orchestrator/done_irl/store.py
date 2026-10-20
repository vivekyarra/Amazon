"""Transactional SQLite local deployment. State, audit, dedupe and artifacts commit together."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS households (id TEXT PRIMARY KEY, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS commands (household TEXT, key TEXT, fingerprint TEXT, response TEXT,
            PRIMARY KEY(household,key));
        CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, household TEXT NOT NULL,
            mime TEXT NOT NULL, data BLOB NOT NULL, sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT, household TEXT,
            role TEXT, expires REAL);
        """)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def read(self, household):
        with self.lock:
            row = self.db.execute("SELECT state FROM households WHERE id=?", (household,)).fetchone()
            return json.loads(row["state"]) if row else None

    def save(self, db, household, state):
        db.execute(
            "INSERT INTO households VALUES (?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
            (household, json.dumps(state, separators=(",", ":"), allow_nan=False)),
        )
