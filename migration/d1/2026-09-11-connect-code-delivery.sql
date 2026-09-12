-- Additive migration: apply once, before the connector reliability Worker.
-- Check PRAGMA table_info(connect_codes) first; do not rerun if present.
-- Existing rows were created after provider acceptance and retain that meaning.
-- New pending/failed rows have non-null used_at, so an older Worker cannot
-- redeem them during rollout or rollback. No rows are deleted or invalidated.
ALTER TABLE connect_codes ADD COLUMN delivery_state TEXT NOT NULL DEFAULT 'accepted'
  CHECK (delivery_state IN ('pending', 'accepted', 'failed'));
