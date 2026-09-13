-- Additive, once-only migration. Apply before enabling durable OAuth recovery.
-- No credentials, raw links, OAuth tokens, or account content are stored here.
--
-- NOT RERUNNABLE ON ITS OWN: the five ALTERs fail with "duplicate column name"
-- on a second pass and the index and triggers below then never get created,
-- which is the worst state available because readiness would still pass. Apply
-- it through `python3 -m proof.audit.d1_additive`, which skips the columns that
-- are already there and runs the rest, and whose tests are tests/test_d1_additive.py.
ALTER TABLE connect_links ADD COLUMN recovery_account_id TEXT NULL;
ALTER TABLE connect_links ADD COLUMN recovery_deadline REAL NULL;
ALTER TABLE connect_links ADD COLUMN recovery_next_check REAL NULL;
ALTER TABLE connect_links ADD COLUMN recovery_attempts INTEGER NOT NULL DEFAULT 0 CHECK(recovery_attempts BETWEEN 0 AND 16);
ALTER TABLE connect_links ADD COLUMN recovery_lease TEXT NULL;
CREATE INDEX IF NOT EXISTS idx_connect_links_recovery
  ON connect_links(recovery_next_check) WHERE recovery_account_id IS NOT NULL AND completed_at IS NULL;

-- A LATER EXPLICIT DISCONNECT/DECLINE WINS OVER AN IN-FLIGHT VENDOR READ.
--
-- `arm()` writes recovery_account_id only AFTER provider.authorize returns, so
-- between the redeem and the arm there is a live attempt whose account id is
-- still NULL. An account-only predicate cannot see it, and a disconnect landing
-- in that window would be overtaken a moment later by a recovery that
-- reconnected the very account the owner just removed. `used_at IS NOT NULL` is
-- what says "this link was actually redeemed", and `toolkit` keeps that branch
-- from reaching a pending connect for a DIFFERENT app of the same owner.
--
-- KNOWN AND ACCEPTED COST: the owner who is adding a SECOND account of the same
-- app, and removes the first while the new one is mid-authorize, has the new
-- attempt cancelled too. That costs one "send me a new link" tap. The other
-- direction re-creates a connection somebody explicitly removed, so this is the
-- side to be wrong on. Do not try to narrow it with a clock in SQL.
--
-- THE PURGES CLAUSE IS NOT DECORATION. These bodies UPDATE connect_links, and
-- 2026-09-07-account-erasure-fence.sql installs a BEFORE UPDATE RAISE(ABORT) on
-- that table for any owner holding a purges row. Without the NOT EXISTS, a
-- DELETE on connections for such an owner aborts with ACCOUNT_ERASURE_IN_PROGRESS
-- — measured, not theorised — which is reachable whenever accountDelete files
-- the purge row and then returns 503 before running its delete batch. Skipping
-- a fenced owner costs nothing: recovery.ts already refuses to arm, list or
-- claim anything for one, so there is never a live attempt left to cancel.
CREATE TRIGGER IF NOT EXISTS cancel_oauth_recovery_deleted_connection
AFTER DELETE ON connections
BEGIN
  UPDATE connect_links SET recovery_deadline=0, recovery_lease=NULL
  WHERE user_id=OLD.user_id AND toolkit=OLD.toolkit AND completed_at IS NULL
    AND (recovery_account_id=OLD.connected_account_id OR (recovery_account_id IS NULL AND used_at IS NOT NULL))
    AND NOT EXISTS (SELECT 1 FROM purges WHERE owner_ref=connect_links.user_id);
END;
CREATE TRIGGER IF NOT EXISTS cancel_oauth_recovery_disconnected_connection
AFTER UPDATE OF status ON connections WHEN NEW.status='disconnected'
BEGIN
  UPDATE connect_links SET recovery_deadline=0, recovery_lease=NULL
  WHERE user_id=NEW.user_id AND toolkit=NEW.toolkit AND completed_at IS NULL
    AND (recovery_account_id=NEW.connected_account_id OR (recovery_account_id IS NULL AND used_at IS NOT NULL))
    AND NOT EXISTS (SELECT 1 FROM purges WHERE owner_ref=connect_links.user_id);
END;
CREATE TRIGGER IF NOT EXISTS cancel_oauth_recovery_decline_insert
AFTER INSERT ON connect_nudges WHEN NEW.state IN ('declined_soft','declined')
BEGIN
  UPDATE connect_links SET recovery_deadline=0, recovery_lease=NULL
  WHERE user_id=NEW.user_id AND toolkit=NEW.toolkit AND completed_at IS NULL
    AND used_at IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM purges WHERE owner_ref=connect_links.user_id);
END;
CREATE TRIGGER IF NOT EXISTS cancel_oauth_recovery_decline_update
AFTER UPDATE OF state ON connect_nudges WHEN NEW.state IN ('declined_soft','declined')
BEGIN
  UPDATE connect_links SET recovery_deadline=0, recovery_lease=NULL
  WHERE user_id=NEW.user_id AND toolkit=NEW.toolkit AND completed_at IS NULL
    AND used_at IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM purges WHERE owner_ref=connect_links.user_id);
END;
