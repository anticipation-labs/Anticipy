-- engine_trajectories — persistent record of every browser-agent run
--
-- Every time the Chrome extension's BrowserAgent finishes a task (success
-- or failure), it POSTs a trajectory to `/api/engine/trajectory`. The
-- backend writes a row here. This is the foundation for any future
-- learning loop:
--   • Synthetic-data corpus for fine-tuning a smaller agent model
--   • Retrieval-augmented planning ("show me how this user's last 3 tasks
--     on amazon.com went before I plan this one")
--   • Per-domain failure-mode analytics (where does the agent stall most?)
--   • Self-reflection lessons (engine_lessons table, future migration)
--
-- The schema deliberately stores the full step trace as JSONB. The
-- consumer-side analytics build on top of (domain, outcome, step count,
-- duration), and the deeper RAG/training paths read the JSONB.
--
-- RLS: each user sees only their own trajectories. The API route writes
-- with the service-role key after verifying the wearer's access code; the
-- USING clause keeps direct REST reads scoped per-user.
--
-- This migration is ADDITIVE — it creates a new table and indexes, doesn't
-- touch existing data. Safe to apply during normal operation.

CREATE TABLE IF NOT EXISTS public.engine_trajectories (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         text        NOT NULL,
  intent_id       uuid,
  domain          text        NOT NULL,
  task_summary    text        NOT NULL,
  steps           jsonb       NOT NULL DEFAULT '[]'::jsonb,
  outcome         text        NOT NULL CHECK (outcome IN ('success','partial','fail','aborted')),
  outcome_message text,
  total_steps     int         NOT NULL DEFAULT 0,
  duration_ms     int,
  cost_usd        numeric(8,4),
  -- Reserved for future retrieval-augmented planning. Populating via Gemini
  -- text-embedding-004 (768-d) once the read-side RAG path is wired.
  task_embedding  vector(768),
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS engine_trajectories_user_idx
  ON public.engine_trajectories (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS engine_trajectories_user_domain_idx
  ON public.engine_trajectories (user_id, domain, created_at DESC);

CREATE INDEX IF NOT EXISTS engine_trajectories_outcome_idx
  ON public.engine_trajectories (outcome, created_at DESC);

-- ─── RLS: per-user isolation ────────────────────────────────────────────
ALTER TABLE public.engine_trajectories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "trajectories: users see only their own" ON public.engine_trajectories;
CREATE POLICY "trajectories: users see only their own"
  ON public.engine_trajectories
  FOR SELECT
  USING (auth.uid()::text = user_id);

-- Inserts come from the API route using the service role key. We do NOT
-- grant insert via RLS to anon/authenticated — the API enforces the
-- access-code → user_id mapping before writing.
DROP POLICY IF EXISTS "trajectories: deny direct inserts" ON public.engine_trajectories;
CREATE POLICY "trajectories: deny direct inserts"
  ON public.engine_trajectories
  FOR INSERT
  WITH CHECK (false);

COMMENT ON TABLE public.engine_trajectories IS
  'Persistent browser-agent run trace: one row per task attempt by the Chrome extension. Foundation for future learning loop (RAG, fine-tuning, per-domain lesson extraction). Writes service-role only via /api/engine/trajectory.';
