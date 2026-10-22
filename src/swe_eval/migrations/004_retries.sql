-- Explicit additive feature migration. Core/management schema remains 3.
BEGIN IMMEDIATE;
CREATE TABLE provider_cooldowns(provider_key TEXT PRIMARY KEY, until_at REAL NOT NULL, reason TEXT NOT NULL);
CREATE TABLE recovery_decisions(parent_id TEXT PRIMARY KEY REFERENCES runs(id), reason TEXT NOT NULL, decided_at REAL NOT NULL);
CREATE TABLE run_recoveries(
 parent_id TEXT PRIMARY KEY REFERENCES runs(id),
 child_id TEXT NOT NULL UNIQUE REFERENCES runs(id),
 batch_id TEXT NOT NULL REFERENCES evaluation_batches(id),
 sequence INTEGER NOT NULL CHECK(sequence=1),
 reason TEXT NOT NULL, next_eligible_at REAL NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX recoveries_batch ON run_recoveries(batch_id);
INSERT INTO metadata VALUES('api_retry_schema','1');
COMMIT;
