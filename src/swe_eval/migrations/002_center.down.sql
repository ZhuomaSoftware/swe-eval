-- Offline rollback on a disposable/restored copy only. Retains runs/logs/patches.
-- Removes Phase 2 provenance/batch/session metadata. Prefer restoring a v1 backup.
BEGIN IMMEDIATE;
DROP TABLE IF EXISTS admin_sessions;
DROP TABLE IF EXISTS integration_metadata;
DROP TABLE IF EXISTS operational_events;
DROP TABLE IF EXISTS batch_attempts;
DROP TABLE IF EXISTS evaluation_snapshots;
DROP TABLE IF EXISTS evaluation_batches;
PRAGMA user_version=1;
COMMIT;
