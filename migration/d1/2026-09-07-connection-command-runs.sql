-- One invocation across incoming text and brain polls. An expired planning
-- lease can be retried; an uncertain external effect must never be replayed.
CREATE TABLE IF NOT EXISTS connection_command_runs (
  event_id TEXT PRIMARY KEY NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  owner_ref TEXT NOT NULL REFERENCES owners(id) ON DELETE CASCADE,
  state TEXT NOT NULL CHECK(state IN ('planning','executing','completed')),
  lease_token TEXT NOT NULL,
  lease_until INTEGER NOT NULL,
  outcome TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_connection_command_owner ON connection_command_runs(owner_ref);
CREATE TRIGGER IF NOT EXISTS erasure_fence_connection_command_runs_insert
BEFORE INSERT ON connection_command_runs
WHEN EXISTS(SELECT 1 FROM purges WHERE owner_ref = NEW.owner_ref)
BEGIN SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS'); END;
CREATE TRIGGER IF NOT EXISTS erasure_fence_connection_command_runs_update
BEFORE UPDATE ON connection_command_runs
WHEN EXISTS(SELECT 1 FROM purges WHERE owner_ref = NEW.owner_ref OR owner_ref = OLD.owner_ref)
BEGIN SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS'); END;
