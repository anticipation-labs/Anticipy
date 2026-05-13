-- skill_library + task_state — v-final-prototype skill engine
--
-- Two new tables backing the "skill engine" portion of the v-final-prototype
-- architecture (Voyager-pattern fleet learning + Hermes-style lifecycle
-- promotion/demotion + transient per-task working state).
--
-- skill_library
--   A *global* catalog of reusable skill programs the agent has accumulated
--   across the entire fleet of users. There is no user_id column on purpose:
--   skills are global IP — once one user's session teaches us how to "click
--   the Buy Now button on amazon.com after the cookie banner", every other
--   user benefits. Each row is a (pickled python program, 4-step selector
--   chain, postcondition verifier) bundle plus Hermes lifecycle counters
--   (shadow → active → retired).
--
-- task_state
--   The transient working state for a single in-flight task. One row per
--   task_id, joined to anticipy_intents via intent_id for authorization.
--   Stores the current step pointer and a jsonb scratchpad. Rows are
--   ephemeral — written during a task and typically deleted or archived
--   when the task ends.
--
-- RLS posture
--   skill_library: service_role only. Locked completely down to anon and
--                  authenticated (DENY policies + REVOKE) because the
--                  pickled `code` and `verifier_code` columns are bytea
--                  blobs that must NEVER be readable from the browser
--                  bundle. The agent backend, which runs with the
--                  service_role key, is the sole reader/writer.
--   task_state:   per-user via join through anticipy_intents → anticipy_sessions.
--                 anticipy_intents has no user_id directly; anticipy_sessions
--                 does. Policy joins through both. Writes are service-role
--                 only (DENY for INSERT/UPDATE/DELETE on authenticated).
--
-- This migration is ADDITIVE — creates new tables only.

-- ─── skill_library ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.skill_library (
  skill_id              text        PRIMARY KEY,
  intent_match_pattern  text        NOT NULL,
  code                  bytea       NOT NULL,
  selector_chain        jsonb       NOT NULL,
  verifier_code         bytea       NOT NULL,
  postcondition_spec    text        NOT NULL,
  status                text        NOT NULL CHECK (status IN ('shadow','active','retired')),
  success_count         integer     NOT NULL DEFAULT 0 CHECK (success_count >= 0),
  failure_count         integer     NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
  last_run_at           timestamptz,
  version               integer     NOT NULL DEFAULT 1,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);

-- Hermes promotion/demotion query: "find shadow skills ordered by recency"
-- and "find active skills with stale last_run_at for retirement candidates".
CREATE INDEX IF NOT EXISTS skill_library_status_last_run_idx
  ON public.skill_library (status, last_run_at DESC NULLS LAST);

ALTER TABLE public.skill_library ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.skill_library FORCE ROW LEVEL SECURITY;

-- Deny all direct access from anon and authenticated. The agent backend
-- reads/writes via the service_role key, which bypasses RLS.
DROP POLICY IF EXISTS "skill_library: deny anon select" ON public.skill_library;
CREATE POLICY "skill_library: deny anon select"
  ON public.skill_library
  FOR SELECT
  USING (false);

DROP POLICY IF EXISTS "skill_library: deny anon insert" ON public.skill_library;
CREATE POLICY "skill_library: deny anon insert"
  ON public.skill_library
  FOR INSERT
  WITH CHECK (false);

DROP POLICY IF EXISTS "skill_library: deny anon update" ON public.skill_library;
CREATE POLICY "skill_library: deny anon update"
  ON public.skill_library
  FOR UPDATE
  USING (false)
  WITH CHECK (false);

DROP POLICY IF EXISTS "skill_library: deny anon delete" ON public.skill_library;
CREATE POLICY "skill_library: deny anon delete"
  ON public.skill_library
  FOR DELETE
  USING (false);

REVOKE ALL ON public.skill_library FROM PUBLIC;
REVOKE ALL ON public.skill_library FROM anon;
REVOKE ALL ON public.skill_library FROM authenticated;
GRANT ALL ON public.skill_library TO service_role;

COMMENT ON TABLE public.skill_library IS
  'Global catalog of reusable agent skill programs (pickled code + 4-step selector chain + postcondition verifier) with Hermes shadow/active/retired lifecycle. service_role only — no user_id because skills are fleet-wide IP.';


-- ─── task_state ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.task_state (
  task_id          uuid        PRIMARY KEY,
  intent_id        uuid,
  current_step     integer     NOT NULL DEFAULT 0,
  transient_state  jsonb,
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- Fast lookup by intent_id (the join key for RLS and for the agent's
-- "find the working state for this intent" query).
CREATE INDEX IF NOT EXISTS task_state_intent_id_idx
  ON public.task_state (intent_id);

ALTER TABLE public.task_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.task_state FORCE ROW LEVEL SECURITY;

-- SELECT: a user can see task_state rows whose intent_id belongs to a
-- session they own. anticipy_intents.session_id → anticipy_sessions.id,
-- and anticipy_sessions.user_id (text) is compared to auth.uid()::text.
DROP POLICY IF EXISTS "task_state: users see only their own via intent join" ON public.task_state;
CREATE POLICY "task_state: users see only their own via intent join"
  ON public.task_state
  FOR SELECT
  USING (
    intent_id IS NOT NULL
    AND EXISTS (
      SELECT 1
      FROM public.anticipy_intents i
      JOIN public.anticipy_sessions s ON s.id = i.session_id
      WHERE i.id = task_state.intent_id
        AND s.user_id = auth.uid()::text
    )
  );

-- Writes are service-role only. The agent backend writes during a task.
DROP POLICY IF EXISTS "task_state: deny direct inserts" ON public.task_state;
CREATE POLICY "task_state: deny direct inserts"
  ON public.task_state
  FOR INSERT
  WITH CHECK (false);

DROP POLICY IF EXISTS "task_state: deny direct updates" ON public.task_state;
CREATE POLICY "task_state: deny direct updates"
  ON public.task_state
  FOR UPDATE
  USING (false)
  WITH CHECK (false);

DROP POLICY IF EXISTS "task_state: deny direct deletes" ON public.task_state;
CREATE POLICY "task_state: deny direct deletes"
  ON public.task_state
  FOR DELETE
  USING (false);

COMMENT ON TABLE public.task_state IS
  'Transient per-task working state (current step pointer + jsonb scratchpad) for in-flight agent tasks. Authorized via join through anticipy_intents → anticipy_sessions; writes service-role only.';
