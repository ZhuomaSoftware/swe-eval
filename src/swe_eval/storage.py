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
from .diagnostics import log_message, public_log


class Conflict(Exception):
    pass


class RunRepository(Protocol):
    """Persistence boundary; worker and engine do not issue backend-specific SQL."""

    def create(self, task: dict, model: dict, *, mode: str = "agent", parent_id: str | None = None) -> dict: ...
    def get(self, run_id: str) -> dict | None: ...
    def list(self, limit: int = 50, offset: int = 0) -> list[dict]: ...
    def claim(self, owner: str, run_id: str | None = None) -> dict | None: ...
    def transition(self, run_id: str, state: RunState, error: str | None = None, *, metrics: Metrics | None = None) -> None: ...
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
            if version not in (0, 1, 2, 3):
                raise RuntimeError("unsupported database schema version")
            if version < 2:
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
            from .migrations import migrate
            migrate(db)
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

    def create(self, task, model, *, mode="agent", parent_id=None, snapshot=None, max_pending=None):
        with self.connect(write=True) as db:
            if max_pending is not None and self._pending(db) >= max_pending:
                raise Conflict("pending queue limit reached")
            run_id = self._insert_run(db, task, model, mode, parent_id, snapshot)
        return self.get(run_id)

    def _insert_run(self, db, task, model, mode="agent", parent_id=None, snapshot=None):
        run_id, now = uuid.uuid4().hex, time.time()
        metrics = Metrics(model_id=model.get("model_id"), model_profile_id=model.get("id"),
                          upstream_id=model.get("upstream_id"), requested_reasoning_effort=model.get("reasoning_effort"),
                          benchmark_version=task["dataset_version"])
        db.execute("""INSERT INTO runs
            (id,state,task_json,model_json,mode,parent_id,created_at,updated_at,metrics_json)
            VALUES (?,?,?,?,?,?,?,?,?)""", (run_id,"queued",json.dumps(task),json.dumps(model),mode,parent_id,
                                           now,now,metrics.model_dump_json()))
        if snapshot:
            db.execute("INSERT INTO evaluation_snapshots VALUES (?,?)", (run_id,json.dumps(snapshot)))
        self._log(db,run_id,"queued","Evaluation queued")
        return run_id

    @staticmethod
    def _pending(db):
        return db.execute("SELECT count(*) FROM runs WHERE state IN ('queued','preparing','running','evaluating')").fetchone()[0]

    def get(self, run_id):
        with self.connect() as db:
            record = self._decode(db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())
            if record:
                attempt = db.execute("SELECT * FROM batch_attempts WHERE run_id=?", (run_id,)).fetchone()
                record['batch'] = dict(attempt) if attempt else None
                snap = db.execute("SELECT snapshot_json FROM evaluation_snapshots WHERE run_id=?", (run_id,)).fetchone()
                record['snapshot'] = json.loads(snap[0]) if snap else None
            return record

    def list(self, limit=50, offset=0):
        with self.connect() as db:
            return [self._decode(row) for row in db.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, id LIMIT ? OFFSET ?", (limit, offset))]

    def claim(self, owner, run_id=None):
        with self.connect(write=True) as db:
            self._check_owner(db, owner)
            self._reconcile_batches(db)
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

    def _writable(self, db, run_id):
        row = db.execute("SELECT state,worker_id,metrics_json FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        if row["state"] in TERMINAL:
            raise Conflict("terminal run is immutable; create an explicit retry")
        if row["state"] in ACTIVE:
            self._check_owner(db, row["worker_id"])
        return row

    def _metrics_json(self, metrics, state):
        value = metrics.model_copy(deep=True)
        if state in TERMINAL - {RunState.COMPLETED}:
            value.resolved = None
        elif state == RunState.COMPLETED:
            if value.test_result == "passed" and value.patch_applied is True:
                value.resolved = True
            elif value.test_result == "failed" or value.patch_applied is False:
                value.resolved = False
            elif (value.execution_metadata.get("grading_protocol")=="swebench-official-v5"
                  and value.execution_metadata.get("harness_version")=="5.0.2"
                  and value.execution_metadata.get("failure_classification")=="empty_patch_skipped"
                  and value.execution_metadata.get("patch_sha256")==__import__("hashlib").sha256(b"").hexdigest()
                  and value.execution_metadata.get("harness_run_id")
                  and value.execution_metadata.get("evaluation_config_fingerprint")
                  and value.test_result=="not_run" and value.patch_applied is None
                  and value.resolved is False):
                # Successful processing of an upstream-skipped prediction is
                # not an executed test and never a valid evaluation/repair.
                value.resolved=False
            else:
                raise Conflict("completed evaluation requires an authoritative test or patch verdict")
        return json.dumps(self.redact.data(value.model_dump(mode="json")))

    def transition(self, run_id, state, error=None, *, metrics=None):
        state = RunState(state)
        with self.connect(write=True) as db:
            row = self._writable(db, run_id)
            old = RunState(row["state"])
            if state not in TRANSITIONS.get(old, set()):
                raise Conflict(f"invalid state transition: {old} -> {state}")
            now = time.time()
            normalized = self._metrics_json(metrics or Metrics.model_validate_json(row["metrics_json"]), state)
            db.execute("UPDATE runs SET state=?,error=?,updated_at=?,finished_at=?,metrics_json=? WHERE id=?",
                       (state, self.redact(error) if error else None, now,
                        now if state in TERMINAL else None, normalized, run_id))
            self._log(db, run_id, str(state), error or f"Evaluation {state}")

    def save_metrics(self, run_id, metrics):
        safe = json.dumps(self.redact.data(metrics.model_dump(mode="json")))
        with self.connect(write=True) as db:
            self._writable(db, run_id)
            db.execute("UPDATE runs SET metrics_json=?,updated_at=? WHERE id=?", (safe, time.time(), run_id))

    def save_patch(self, run_id, patch):
        if len(patch.encode()) > 512 * 1024:
            raise ValueError("patch exceeds 512 KiB")
        # Redacting would silently change the submitted repair. Reject instead.
        if self.redact.contains_secret(patch):
            raise ValueError("patch contains credential-like material; artifact rejected")
        with self.connect(write=True) as db:
            self._writable(db, run_id)
            db.execute("UPDATE runs SET patch=? WHERE id=?", (patch, run_id))

    def patch(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT patch FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(run_id)
            return row[0]

    def _log(self, db, run_id, event, message):
        message = self.redact(log_message(event, message))[:32768]
        db.execute("INSERT INTO logs (run_id,at,event,message) VALUES (?,?,?,?)",
                   (run_id, time.time(), event[:80], message))
        logging.getLogger("swe_eval.runs").info(message[:4096], extra={"run_id": run_id, "event": event[:80]})

    def log(self, run_id, event, message):
        with self.connect(write=True) as db:
            self._log(db, run_id, event, message)

    def logs(self, run_id, after=0, limit=200):
        with self.connect() as db:
            return [public_log(dict(row)) for row in db.execute(
                "SELECT seq,at,event,message FROM logs WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
                (run_id, after, limit))]

    def cancel(self, run_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT state,metrics_json FROM runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            if row[0] in TERMINAL:
                raise Conflict("run is already terminal")
            if row[0] == "queued":
                normalized = self._metrics_json(Metrics.model_validate_json(row["metrics_json"]), RunState.CANCELLED)
                db.execute("UPDATE runs SET state='cancelled',finished_at=?,updated_at=?,metrics_json=? WHERE id=?",
                           (time.time(), time.time(), normalized, run_id))
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
            self._record_heartbeat(db)
        return True

    @staticmethod
    def _record_heartbeat(db):
        db.execute("INSERT OR REPLACE INTO metadata VALUES ('worker_heartbeat_at', ?)", (str(time.time()),))

    def heartbeat(self, owner, lease_seconds):
        with self.connect(write=True) as db:
            cursor = db.execute("UPDATE worker_lock SET expires_at=? WHERE owner=? AND expires_at>?",
                                (time.time() + lease_seconds, owner, time.time()))
            if cursor.rowcount == 1:
                self._record_heartbeat(db)
            return cursor.rowcount == 1

    def release(self, owner):
        with self.connect(write=True) as db:
            db.execute("DELETE FROM worker_lock WHERE owner=?", (owner,))

    def recover(self, owner):
        with self.connect(write=True) as db:
            self._check_owner(db, owner)
            rows = db.execute("SELECT id,metrics_json FROM runs WHERE state IN ('preparing','running','evaluating')").fetchall()
            ids = [row["id"] for row in rows]
            for row in rows:
                run_id = row["id"]
                normalized = self._metrics_json(Metrics.model_validate_json(row["metrics_json"]), RunState.FAILED)
                db.execute("UPDATE runs SET state='failed',error='worker_interrupted',finished_at=?,updated_at=?,metrics_json=? WHERE id=?",
                           (time.time(), time.time(), normalized, run_id))
                self._log(db, run_id, "failed", "worker_interrupted: previous worker stopped; explicit retry required")
        return ids

    def create_batch(self, config, specs, max_pending, reserved):
        from .center import digest
        request_hash = digest(config)
        with self.connect(write=True) as db:
            prior = db.execute('SELECT id,request_hash FROM evaluation_batches WHERE idempotency_key=?',
                               (config['idempotency_key'],)).fetchone()
            if prior:
                if prior['request_hash'] != request_hash:
                    raise Conflict('idempotency key already used for different configuration')
                batch_id = prior['id']
            else:
                if self._pending(db) + len(specs) > max_pending:
                    raise Conflict('pending queue limit reached')
                batch_id, now = uuid.uuid4().hex, time.time()
                stored = dict(config, reserved_requests=reserved, monetary_enforcement='unavailable')
                db.execute('INSERT INTO evaluation_batches (id,name,idempotency_key,request_hash,configuration_json,created_at,deadline) VALUES (?,?,?,?,?,?,?)',
                           (batch_id,config['name'],config['idempotency_key'],request_hash,json.dumps(stored),now,now+config['max_duration']))
                for task, model, snapshot, attempt in specs:
                    run_id = self._insert_run(db,task,model,snapshot=snapshot)
                    db.execute('INSERT INTO batch_attempts VALUES (?,?,?,?,?)',
                               (batch_id,run_id,task['id'],model['id'],attempt))
        return self.batch(batch_id)

    def batch(self, batch_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM evaluation_batches WHERE id=?',(batch_id,)).fetchone()
            if not row:
                return None
            value = dict(row)
            value['configuration'] = json.loads(value.pop('configuration_json'))
            attempts = [dict(x) for x in db.execute('SELECT a.*,r.state,r.error,r.metrics_json FROM batch_attempts a JOIN runs r ON r.id=a.run_id WHERE batch_id=? ORDER BY task_id,profile_id,attempt',(batch_id,))]
            for item in attempts:
                item['metrics'] = json.loads(item.pop('metrics_json'))
            value['attempts'] = attempts
            value['progress'] = {state: sum(x['state']==state for x in attempts) for state in RunState}
            value['total'] = len(attempts)
            value['terminal'] = sum(x['state'] in TERMINAL for x in attempts)
            if value['terminal'] == value['total']:
                # Terminal attempts are immutable. A late stop signal cannot
                # relabel completed work, even if final completion won a race.
                value['state'] = ('completed' if all(x['state']=='completed' for x in attempts)
                                  else 'cancelled' if value['cancel_requested'] or any(x['state']=='cancelled' for x in attempts)
                                  else 'failed')
            else:
                value['state'] = 'stopping' if value['cancel_requested'] else 'running' if any(x['state']!='queued' for x in attempts) else 'queued'
            return value

    def batches(self, limit=50, offset=0):
        with self.connect() as db:
            ids = [x[0] for x in db.execute('SELECT id FROM evaluation_batches ORDER BY created_at DESC LIMIT ? OFFSET ?',(limit,offset))]
        return [self.batch(x) for x in ids]

    def _reconcile_batches(self, db):
        now = time.time()
        db.execute("UPDATE evaluation_batches SET cancel_requested=1,stop_reason='batch_deadline_exceeded' WHERE deadline<=? AND cancel_requested=0 AND EXISTS (SELECT 1 FROM batch_attempts a JOIN runs r ON r.id=a.run_id WHERE a.batch_id=evaluation_batches.id AND r.state IN ('queued','preparing','running','evaluating'))",(now,))
        rows = db.execute("SELECT r.id,r.state,r.metrics_json FROM runs r JOIN batch_attempts a ON a.run_id=r.id JOIN evaluation_batches b ON b.id=a.batch_id WHERE b.cancel_requested=1 AND r.state IN ('queued','preparing','running','evaluating')").fetchall()
        for row in rows:
            if row['state']=='queued':
                normalized = self._metrics_json(Metrics.model_validate_json(row['metrics_json']),RunState.CANCELLED)
                db.execute("UPDATE runs SET state='cancelled',cancel_requested=1,finished_at=?,updated_at=?,metrics_json=? WHERE id=?",(now,now,normalized,row['id']))
                self._log(db,row['id'],'cancelled','Batch stopped before execution')
            else:
                db.execute('UPDATE runs SET cancel_requested=1 WHERE id=?',(row['id'],))

    def reconcile_batches(self):
        with self.connect(write=True) as db:
            self._reconcile_batches(db)

    def cancel_batch(self, batch_id):
        with self.connect(write=True) as db:
            if not db.execute('SELECT 1 FROM evaluation_batches WHERE id=?',(batch_id,)).fetchone():
                raise KeyError(batch_id)
            db.execute("UPDATE evaluation_batches SET cancel_requested=1,stop_reason=coalesce(stop_reason,'administrator_cancelled') WHERE id=? AND EXISTS (SELECT 1 FROM batch_attempts a JOIN runs r ON r.id=a.run_id WHERE a.batch_id=evaluation_batches.id AND r.state IN ('queued','preparing','running','evaluating'))",(batch_id,))
            self._reconcile_batches(db)
        return self.batch(batch_id)

    def query_runs(self, *, limit=50, offset=0, **filters):
        clauses, values = [], []
        expressions = {'model_profile_id':"json_extract(r.model_json,'$.id')", 'upstream_id':"json_extract(r.model_json,'$.upstream_id')",
            'benchmark':"json_extract(r.task_json,'$.benchmark')", 'state':'r.state', 'batch_id':'a.batch_id',
            'grading_protocol':"coalesce(json_extract(r.metrics_json,'$.execution_metadata.grading_protocol'),json_extract(s.snapshot_json,'$.grading_protocol'),'legacy/unknown')"}
        for key, expression in expressions.items():
            if filters.get(key) is not None:
                clauses.append(expression+'=?'); values.append(filters[key])
        for key, operator in [('created_after','>='),('created_before','<=')]:
            if filters.get(key) is not None:
                clauses.append('r.created_at'+operator+'?'); values.append(filters[key])
        where = ' WHERE '+' AND '.join(clauses) if clauses else ''
        join = ' FROM runs r LEFT JOIN batch_attempts a ON a.run_id=r.id LEFT JOIN evaluation_snapshots s ON s.run_id=r.id'
        with self.connect() as db:
            total = db.execute('SELECT count(*)'+join+where,values).fetchone()[0]
            rows = db.execute('SELECT r.*,a.batch_id,a.attempt,s.snapshot_json'+join+where+' ORDER BY r.created_at DESC,r.id LIMIT ? OFFSET ?',values+[limit,offset]).fetchall()
            items = []
            for row in rows:
                value = self._decode(row)
                value['snapshot'] = json.loads(value.pop('snapshot_json')) if value.get('snapshot_json') else None
                value.pop('snapshot_json',None)
                items.append(value)
        return {'items':items,'total':total,'limit':limit,'offset':offset}

    def event(self, kind, detail=''):
        with self.connect(write=True) as db:
            db.execute('INSERT INTO operational_events(at,kind,detail) VALUES (?,?,?)',(time.time(),kind,self.redact(detail)[:1000]))
            db.execute('DELETE FROM operational_events WHERE id < (SELECT coalesce(max(id),0)-10000 FROM operational_events)')

    def operations(self):
        with self.connect() as db:
            lease = db.execute('SELECT expires_at FROM worker_lock WHERE singleton=1').fetchone()
            active = db.execute("SELECT id,state,started_at FROM runs WHERE state IN ('preparing','running','evaluating')").fetchone()
            oldest = db.execute("SELECT min(created_at),count(*) FROM runs WHERE state='queued'").fetchone()
            events = [dict(x) for x in db.execute('SELECT at,kind,detail FROM operational_events ORDER BY id DESC LIMIT 30')]
            heartbeat = db.execute("SELECT value FROM metadata WHERE key='worker_heartbeat_at'").fetchone()
            completed = db.execute("SELECT id,finished_at FROM runs WHERE state='completed' ORDER BY finished_at DESC,id LIMIT 1").fetchone()
            errors = [dict(x) for x in db.execute("SELECT id,state,error,finished_at FROM runs WHERE state IN ('failed','timeout') ORDER BY finished_at DESC,id LIMIT 10")]
            cleanup = db.execute("SELECT at,kind,detail FROM operational_events WHERE kind IN ('cleanup_started','cleanup_complete','cleanup_failed') ORDER BY id DESC LIMIT 1").fetchone()
            readiness_row = db.execute("SELECT at,kind,detail FROM operational_events WHERE kind IN ('worker_ready','cleanup_failed','worker_starting') ORDER BY id DESC LIMIT 1").fetchone()
            starts = db.execute("SELECT count(*),max(at) FROM operational_events WHERE kind='worker_starting'").fetchone()
            failed_api = db.execute("SELECT count(*) FROM operational_events WHERE kind='http_error'").fetchone()[0]
        from .analytics import records, trusted_success
        latest = max((r['finished_at'] for r in records(self) if trusted_success(r) and r['finished_at'] is not None), default=None)
        ready = bool(lease and lease[0]>time.time())
        readiness = dict(readiness_row) if readiness_row else None
        return {'api':'ready','database':'ready',
                'last_worker_heartbeat_at':float(heartbeat[0]) if heartbeat else None,
                'worker_lease_status':'active' if ready else 'expired' if lease else 'absent',
                'last_completed_evaluation':dict(completed) if completed else None,
                'recent_infrastructure_errors':errors,
                'orphan_cleanup':dict(status={'cleanup_started':'in_progress','cleanup_complete':'complete','cleanup_failed':'failed'}[cleanup['kind']],observed_at=cleanup['at'],detail=cleanup['detail']) if cleanup else {'status':'unknown','observed_at':None},
                'worker_ready':ready and bool(readiness and readiness['kind']=='worker_ready'),
                'worker_start_observations_retained':starts[0], 'last_worker_start_at':starts[1],
                'readiness_observation':readiness, 'lease_valid':ready,'lease_expires_at':lease[0] if lease else None,
                'docker': 'last_probe_ok' if ready and readiness and readiness['kind']=='worker_ready' else 'unknown',
                'upstream':'not_probed','active_run':dict(active) if active else None,
                'queue_depth':oldest[1],'oldest_pending_at':oldest[0],'last_success_at':latest,
                'failed_http_requests_retained':failed_api,'events':events}
