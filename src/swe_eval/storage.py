from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from .schema import ACTIVE, TERMINAL, TRANSITIONS, Metrics, RunState
from .security import Redactor


class Conflict(Exception):
    pass


class RunRepository(Protocol):
    """Persistence boundary; worker and engine do not issue backend-specific SQL."""

    def create(self, task: dict, model: dict, *, mode: str = "agent", parent_id: str | None = None) -> dict: ...
    def get(self, run_id: str) -> dict | None: ...
    def list(self, limit: int = 50, offset: int = 0) -> list[dict]: ...
    def claim(self, owner: str, run_id: str | None = None) -> dict | None: ...
    def transition(self, run_id: str, state: RunState, error: str | None = None) -> None: ...
    def save_metrics(self, run_id: str, metrics: Metrics) -> None: ...
    def log(self, run_id: str, event: str, message: str) -> None: ...
    def save_patch(self, run_id: str, patch: str) -> None: ...
    def logs(self, run_id: str, after: int = 0, limit: int = 200) -> list[dict]: ...
    def patch(self, run_id: str) -> str: ...
    def cancel(self, run_id: str) -> dict: ...
    def acquire(self, owner: str, lease_seconds: int) -> bool: ...
    def heartbeat(self, owner: str, lease_seconds: int) -> bool: ...
    def release(self, owner: str) -> None: ...
    def recover(self, owner: str) -> list[str]: ...
    @property
    def service_id(self) -> str: ...


class SQLiteRepository:
    def __init__(self, path: Path, redactor: Redactor | None = None):
        self.path = path
        self.redact = redactor or Redactor()

    @contextmanager
    def connect(self, *, write=False):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except BaseException:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("unsupported database schema version")
            db.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, state TEXT NOT NULL,
                    task_json TEXT NOT NULL, model_json TEXT NOT NULL,
                    mode TEXT NOT NULL, parent_id TEXT,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    started_at REAL, finished_at REAL,
                    metrics_json TEXT NOT NULL, patch TEXT NOT NULL DEFAULT '',
                    error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
                    worker_id TEXT
                );
                CREATE INDEX IF NOT EXISTS runs_queue ON runs(state, created_at);
                CREATE TABLE IF NOT EXISTS logs (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id),
                    at REAL NOT NULL, event TEXT NOT NULL, message TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS logs_run ON logs(run_id, seq);
                CREATE TABLE IF NOT EXISTS worker_lock (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    owner TEXT NOT NULL, expires_at REAL NOT NULL
                );
                PRAGMA user_version=1;
                COMMIT;
            """)
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('service_id', ?)", (uuid.uuid4().hex,))
        self.path.chmod(0o600)

    @property
    def service_id(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM metadata WHERE key='service_id'").fetchone()[0]

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        record = dict(row)
        record["task"] = json.loads(record.pop("task_json"))
        record["model"] = json.loads(record.pop("model_json"))
        record["metrics"] = json.loads(record.pop("metrics_json"))
        record.pop("patch", None)
        return record

    def create(self, task, model, *, mode="agent", parent_id=None):
        run_id, now = uuid.uuid4().hex, time.time()
        # Caller supplies a public model snapshot, never the credential object.
        metrics = Metrics(model_id=model.get("model_id"), model_profile_id=model.get("id"),
                          upstream_id=model.get("upstream_id"),
                          requested_reasoning_effort=model.get("reasoning_effort"),
                          benchmark_version=task["dataset_version"])
        with self.connect(write=True) as db:
            db.execute("""INSERT INTO runs
                (id,state,task_json,model_json,mode,parent_id,created_at,updated_at,metrics_json)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                       (run_id, "queued", json.dumps(task), json.dumps(model), mode, parent_id,
                        now, now, metrics.model_dump_json()))
            self._log(db, run_id, "queued", "Evaluation queued")
        return self.get(run_id)

    def get(self, run_id):
        with self.connect() as db:
            return self._decode(db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())

    def list(self, limit=50, offset=0):
        with self.connect() as db:
            return [self._decode(row) for row in db.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, id LIMIT ? OFFSET ?", (limit, offset))]

    def claim(self, owner, run_id=None):
        with self.connect(write=True) as db:
            self._check_owner(db, owner)
            # One active run per service, including a directly launched CLI run.
            if db.execute("SELECT 1 FROM runs WHERE state IN ('preparing','running','evaluating')").fetchone():
                return None
            row = (db.execute("SELECT id FROM runs WHERE state='queued' AND id=?", (run_id,)).fetchone()
                   if run_id else db.execute("SELECT id FROM runs WHERE state='queued' ORDER BY created_at, id LIMIT 1").fetchone())
            if not row:
                return None
            now = time.time()
            db.execute("UPDATE runs SET state='preparing',started_at=?,updated_at=?,worker_id=? WHERE id=?",
                       (now, now, owner, row[0]))
            self._log(db, row[0], "preparing", "Worker claimed evaluation")
            run_id = row[0]
        return self.get(run_id)

    def transition(self, run_id, state, error=None):
        state = RunState(state)
        with self.connect(write=True) as db:
            row = db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            old = RunState(row[0])
            if state not in TRANSITIONS.get(old, set()):
                raise Conflict(f"invalid state transition: {old} -> {state}")
            now = time.time()
            db.execute("UPDATE runs SET state=?,error=?,updated_at=?,finished_at=? WHERE id=?",
                       (state, self.redact(error) if error else None, now,
                        now if state in TERMINAL else None, run_id))
            self._log(db, run_id, str(state), error or f"Evaluation {state}")

    def save_metrics(self, run_id, metrics):
        safe = json.dumps(self.redact.data(metrics.model_dump(mode="json")))
        with self.connect(write=True) as db:
            db.execute("UPDATE runs SET metrics_json=?,updated_at=? WHERE id=?", (safe, time.time(), run_id))

    def save_patch(self, run_id, patch):
        if len(patch.encode()) > 512 * 1024:
            raise ValueError("patch exceeds 512 KiB")
        # Redacting would silently change the submitted repair. Reject instead.
        if self.redact.contains_secret(patch):
            raise ValueError("patch contains credential-like material; artifact rejected")
        with self.connect(write=True) as db:
            db.execute("UPDATE runs SET patch=? WHERE id=?", (patch, run_id))

    def patch(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT patch FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return row[0]

    def _log(self, db, run_id, event, message):
        message = self.redact(message)[:32768]
        db.execute("INSERT INTO logs (run_id,at,event,message) VALUES (?,?,?,?)",
                   (run_id, time.time(), event[:80], message))
        logging.getLogger("swe_eval.runs").info(message[:4096], extra={"run_id": run_id, "event": event[:80]})

    def log(self, run_id, event, message):
        with self.connect(write=True) as db:
            self._log(db, run_id, event, message)

    def logs(self, run_id, after=0, limit=200):
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT seq,at,event,message FROM logs WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
                (run_id, after, limit))]

    def cancel(self, run_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row[0] in TERMINAL:
                raise Conflict("run is already terminal")
            if row[0] == "queued":
                db.execute("UPDATE runs SET state='cancelled',finished_at=?,updated_at=? WHERE id=?",
                           (time.time(), time.time(), run_id))
                self._log(db, run_id, "cancelled", "Queued run cancelled")
            else:
                db.execute("UPDATE runs SET cancel_requested=1,updated_at=? WHERE id=?", (time.time(), run_id))
                self._log(db, run_id, "cancel_requested", "Cancellation requested")
        return self.get(run_id)

    @staticmethod
    def _check_owner(db, owner):
        row = db.execute("SELECT owner,expires_at FROM worker_lock WHERE singleton=1").fetchone()
        if not row or row[0] != owner or row[1] <= time.time():
            raise Conflict("worker lease is not held")

    def acquire(self, owner, lease_seconds):
        with self.connect(write=True) as db:
            row = db.execute("SELECT owner,expires_at FROM worker_lock WHERE singleton=1").fetchone()
            if row and row[1] > time.time() and row[0] != owner:
                return False
            db.execute("INSERT OR REPLACE INTO worker_lock VALUES (1,?,?)", (owner, time.time() + lease_seconds))
        return True

    def heartbeat(self, owner, lease_seconds):
        with self.connect(write=True) as db:
            cursor = db.execute("UPDATE worker_lock SET expires_at=? WHERE owner=? AND expires_at>?",
                                (time.time() + lease_seconds, owner, time.time()))
            return cursor.rowcount == 1

    def release(self, owner):
        with self.connect(write=True) as db:
            db.execute("DELETE FROM worker_lock WHERE owner=?", (owner,))

    def recover(self, owner):
        with self.connect(write=True) as db:
            self._check_owner(db, owner)
            ids = [row[0] for row in db.execute(
                "SELECT id FROM runs WHERE state IN ('preparing','running','evaluating')")]
            for run_id in ids:
                db.execute("UPDATE runs SET state='failed',error='worker_interrupted',finished_at=?,updated_at=? WHERE id=?",
                           (time.time(), time.time(), run_id))
                self._log(db, run_id, "failed", "worker_interrupted: previous worker stopped; explicit retry required")
        return ids
