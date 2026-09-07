-- Erasure fence: a purge request is permanent identity state.
-- Apply before deploying the corresponding account deletion handler.
-- The handler refuses cleanup if these triggers are absent. No rows are
-- erased by this migration. Existing purge rows block subsequent writes.
-- Owner presence keeps the brain's memory purge consumer waiting while the
-- API retries provider/picture cleanup. DELETE remains available for cleanup.
CREATE INDEX IF NOT EXISTS idx_purges_owner_ref ON purges(owner_ref);

CREATE TRIGGER IF NOT EXISTS erasure_fence_jobs_insert
BEFORE INSERT ON "jobs"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_jobs_update
BEFORE UPDATE ON "jobs"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner") OR p.owner_ref = OLD."owner_ref" OR (OLD.owner_ref = '' AND p.owner_ref = OLD."owner"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_segments_insert
BEFORE INSERT ON "segments"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_segments_update
BEFORE UPDATE ON "segments"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner") OR p.owner_ref = OLD."owner_ref" OR (OLD.owner_ref = '' AND p.owner_ref = OLD."owner"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_agents_insert
BEFORE INSERT ON "agents"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_agents_update
BEFORE UPDATE ON "agents"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner") OR p.owner_ref = OLD."owner_ref" OR (OLD.owner_ref = '' AND p.owner_ref = OLD."owner"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_owner_profile_insert
BEFORE INSERT ON "owner_profile"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner_id"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_owner_profile_update
BEFORE UPDATE ON "owner_profile"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner_id") OR p.owner_ref = OLD."owner_ref" OR (OLD.owner_ref = '' AND p.owner_ref = OLD."owner_id"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_pendants_insert
BEFORE INSERT ON "pendants"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_pendants_update
BEFORE UPDATE ON "pendants"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR (NEW.owner_ref = '' AND p.owner_ref = NEW."owner") OR p.owner_ref = OLD."owner_ref" OR (OLD.owner_ref = '' AND p.owner_ref = OLD."owner"))
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_agent_llm_audit_insert
BEFORE INSERT ON "agent_llm_audit"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_agent_llm_audit_update
BEFORE UPDATE ON "agent_llm_audit"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR p.owner_ref = OLD."owner_ref")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_agent_audit_sessions_insert
BEFORE INSERT ON "agent_audit_sessions"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_agent_audit_sessions_update
BEFORE UPDATE ON "agent_audit_sessions"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR p.owner_ref = OLD."owner_ref")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_evidence_insert
BEFORE INSERT ON "evidence"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_evidence_update
BEFORE UPDATE ON "evidence"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR p.owner_ref = OLD."owner_ref")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_events_insert
BEFORE INSERT ON "events"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_events_update
BEFORE UPDATE ON "events"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner_ref" OR p.owner_ref = OLD."owner_ref")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_password_resets_insert
BEFORE INSERT ON "password_resets"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_password_resets_update
BEFORE UPDATE ON "password_resets"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."owner" OR p.owner_ref = OLD."owner")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_connect_codes_insert
BEFORE INSERT ON "connect_codes"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_connect_codes_update
BEFORE UPDATE ON "connect_codes"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id" OR p.owner_ref = OLD."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_connect_links_insert
BEFORE INSERT ON "connect_links"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_connect_links_update
BEFORE UPDATE ON "connect_links"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id" OR p.owner_ref = OLD."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_connect_nudges_insert
BEFORE INSERT ON "connect_nudges"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_connect_nudges_update
BEFORE UPDATE ON "connect_nudges"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id" OR p.owner_ref = OLD."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_app_usage_signals_insert
BEFORE INSERT ON "app_usage_signals"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_app_usage_signals_update
BEFORE UPDATE ON "app_usage_signals"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id" OR p.owner_ref = OLD."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_connections_insert
BEFORE INSERT ON "connections"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_connections_update
BEFORE UPDATE ON "connections"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."user_id" OR p.owner_ref = OLD."user_id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_owners_insert
BEFORE INSERT ON "owners"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;

CREATE TRIGGER IF NOT EXISTS erasure_fence_owners_update
BEFORE UPDATE ON "owners"
WHEN EXISTS (SELECT 1 FROM purges p WHERE p.owner_ref = NEW."id" OR p.owner_ref = OLD."id")
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;
