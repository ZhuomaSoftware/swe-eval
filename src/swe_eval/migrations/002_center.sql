BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS evaluation_batches (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
 request_hash TEXT NOT NULL, configuration_json TEXT NOT NULL,
 created_at REAL NOT NULL, deadline REAL NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0,
 stop_reason TEXT
);
CREATE TABLE IF NOT EXISTS batch_attempts (
 batch_id TEXT NOT NULL REFERENCES evaluation_batches(id),
 run_id TEXT NOT NULL UNIQUE REFERENCES runs(id),
 task_id TEXT NOT NULL, profile_id TEXT NOT NULL, attempt INTEGER NOT NULL CHECK(attempt>0),
 PRIMARY KEY(batch_id,task_id,profile_id,attempt)
);
CREATE TABLE IF NOT EXISTS evaluation_snapshots (
 run_id TEXT PRIMARY KEY REFERENCES runs(id), snapshot_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admin_sessions (
 token_hash TEXT PRIMARY KEY, csrf_hash TEXT NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS integration_metadata (
 source_id TEXT PRIMARY KEY, observed_at REAL NOT NULL, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operational_events (
 id INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS operational_kind ON operational_events(kind,at);
PRAGMA user_version=2;
COMMIT;
