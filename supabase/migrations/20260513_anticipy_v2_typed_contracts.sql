-- anticipy_intents_v2 + anticipy_tasks_v2 + anticipy_results_v2 — v-final-prototype typed contracts
--
-- The three typed contracts spelled out in the v-final-prototype master prompt:
--
--   Intent (proactive engine emits)  →  Task (middle layer dispatches)  →  Result (executor writes back)
--
-- Each contract gets its own table with the EXACT schema fields from the prompt.
-- Existing tables (anticipy_intents, anticipy_actions) are kept untouched — the
-- v1 surface is still wired to the legacy /api/engine/analyze + /api/engine/confirm
-- paths, and the v2 architecture runs in parallel via Supabase Realtime channels:
--
--   intent.detected.{user_id}   → anticipy_intents_v2
--   task.dispatched.{user_id}   → anticipy_tasks_v2
--   task.completed.{user_id}    → anticipy_results_v2
--
-- This migration is ADDITIVE — creates new tables only. Does NOT touch v1
-- tables. Once the v2 cascade is stable in production, a separate migration
-- can deprecate v1.
--
-- RLS posture
--   All three tables: service_role only for writes. Reads via per-user policy
--   keyed on user_id = auth.uid()::text (text column to match the rest of the
--   v1 anticipy_* family that already uses auth.uid()::text). Service-role
--   bypasses RLS as usual.
--
-- Realtime
--   All three tables are added to the `supabase_realtime` publication so the
--   middle layer (subscribed to intent.detected.{user_id}) and the executor
--   (subscribed to task.dispatched.{user_id}) get pushes on insert.

-- ─── anticipy_intents_v2 ────────────────────────────────────────────────
--
-- The proactive engine writes one row per typed Intent that passes Stage 1
-- demand detection AND Stage 1.5 hedge filter (COMMIT or STORE_AS_LATENT).
-- REFUSE decisions do NOT write to this table — they go directly to memory
-- as aversion/sentiment facts.
--
-- The schema mirrors the master prompt's Intent contract verbatim:
--
--   Intent {
--     intent_id, user_id, utterance_window, action_category,
--     proposed_skill_hint, slots, detection_confidence,
--     hedge_filter_decision, hedge_filter_reason, proactivity_score,
--     source, timestamp
--   }
CREATE TABLE IF NOT EXISTS public.anticipy_intents_v2 (
  intent_id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                text        NOT NULL,
  utterance_window       jsonb       NOT NULL,
  action_category        text,
  proposed_skill_hint    text,
  slots                  jsonb       NOT NULL DEFAULT '{
    "filled": {},
    "needs_memory": [],
    "needs_inference": [],
    "ambiguous": []
  }'::jsonb,
  detection_confidence   double precision,
  hedge_filter_decision  text        NOT NULL
                                     CHECK (hedge_filter_decision IN ('COMMIT','STORE_AS_LATENT','REFUSE')),
  hedge_filter_reason    text,
  proactivity_score      double precision,
  source                 text        NOT NULL
                                     CHECK (source IN ('pendant','mac_mic','typed')),
  created_at             timestamptz NOT NULL DEFAULT now()
);

-- Channel-scoped lookup: "give me this user's recent intents."
CREATE INDEX IF NOT EXISTS anticipy_intents_v2_user_recent_idx
  ON public.anticipy_intents_v2 (user_id, created_at DESC);

-- Skill-router lookup: "who's matched this skill recently?"
CREATE INDEX IF NOT EXISTS anticipy_intents_v2_skill_hint_idx
  ON public.anticipy_intents_v2 (proposed_skill_hint)
  WHERE proposed_skill_hint IS NOT NULL;

ALTER TABLE public.anticipy_intents_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.anticipy_intents_v2 FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "intents_v2: users see their own" ON public.anticipy_intents_v2;
CREATE POLICY "intents_v2: users see their own"
  ON public.anticipy_intents_v2
  FOR SELECT
  USING (user_id = auth.uid()::text);

DROP POLICY IF EXISTS "intents_v2: deny direct writes" ON public.anticipy_intents_v2;
CREATE POLICY "intents_v2: deny direct writes"
  ON public.anticipy_intents_v2
  FOR INSERT
  WITH CHECK (false);

DROP POLICY IF EXISTS "intents_v2: deny direct updates" ON public.anticipy_intents_v2;
CREATE POLICY "intents_v2: deny direct updates"
  ON public.anticipy_intents_v2
  FOR UPDATE
  USING (false)
  WITH CHECK (false);

DROP POLICY IF EXISTS "intents_v2: deny direct deletes" ON public.anticipy_intents_v2;
CREATE POLICY "intents_v2: deny direct deletes"
  ON public.anticipy_intents_v2
  FOR DELETE
  USING (false);

REVOKE ALL ON public.anticipy_intents_v2 FROM PUBLIC;
REVOKE ALL ON public.anticipy_intents_v2 FROM anon;
REVOKE ALL ON public.anticipy_intents_v2 FROM authenticated;
GRANT SELECT ON public.anticipy_intents_v2 TO authenticated;
GRANT ALL ON public.anticipy_intents_v2 TO service_role;

COMMENT ON TABLE public.anticipy_intents_v2 IS
  'v-final-prototype typed-Intent contract. One row per Intent that passes Stage 1 demand detection AND Stage 1.5 hedge filter (COMMIT or STORE_AS_LATENT). REFUSE goes to memory instead. Inserted by the proactive engine; subscribers (middle layer) receive on Realtime channel intent.detected.{user_id}.';


-- ─── anticipy_tasks_v2 ──────────────────────────────────────────────────
--
-- The middle layer (slot_resolver → skill_router → policy → dispatcher)
-- writes one row per Intent it has decided to dispatch. The executor (Mac
-- app subscribed to task.dispatched.{user_id}) pulls these and runs them.
--
-- Schema mirrors the prompt verbatim:
--
--   Task {
--     task_id, intent_id, user_id, skill_id, parameters, recipe_steps,
--     global_postcondition, rollback_spec, rehearsal_required,
--     irreversible, aevoy_confirmation_required, created_at
--   }
CREATE TABLE IF NOT EXISTS public.anticipy_tasks_v2 (
  task_id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  intent_id                     uuid        NOT NULL REFERENCES public.anticipy_intents_v2(intent_id) ON DELETE CASCADE,
  user_id                       text        NOT NULL,
  skill_id                      text,
  parameters                    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  recipe_steps                  jsonb       NOT NULL DEFAULT '[]'::jsonb,
  global_postcondition          jsonb,
  rollback_spec                 jsonb,
  rehearsal_required            boolean     NOT NULL DEFAULT false,
  irreversible                  boolean     NOT NULL DEFAULT false,
  aevoy_confirmation_required   boolean     NOT NULL DEFAULT false,
  created_at                    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS anticipy_tasks_v2_user_recent_idx
  ON public.anticipy_tasks_v2 (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS anticipy_tasks_v2_intent_id_idx
  ON public.anticipy_tasks_v2 (intent_id);

CREATE INDEX IF NOT EXISTS anticipy_tasks_v2_skill_id_idx
  ON public.anticipy_tasks_v2 (skill_id)
  WHERE skill_id IS NOT NULL;

ALTER TABLE public.anticipy_tasks_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.anticipy_tasks_v2 FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tasks_v2: users see their own" ON public.anticipy_tasks_v2;
CREATE POLICY "tasks_v2: users see their own"
  ON public.anticipy_tasks_v2
  FOR SELECT
  USING (user_id = auth.uid()::text);

DROP POLICY IF EXISTS "tasks_v2: deny direct writes" ON public.anticipy_tasks_v2;
CREATE POLICY "tasks_v2: deny direct writes"
  ON public.anticipy_tasks_v2
  FOR INSERT
  WITH CHECK (false);

DROP POLICY IF EXISTS "tasks_v2: deny direct updates" ON public.anticipy_tasks_v2;
CREATE POLICY "tasks_v2: deny direct updates"
  ON public.anticipy_tasks_v2
  FOR UPDATE
  USING (false)
  WITH CHECK (false);

DROP POLICY IF EXISTS "tasks_v2: deny direct deletes" ON public.anticipy_tasks_v2;
CREATE POLICY "tasks_v2: deny direct deletes"
  ON public.anticipy_tasks_v2
  FOR DELETE
  USING (false);

REVOKE ALL ON public.anticipy_tasks_v2 FROM PUBLIC;
REVOKE ALL ON public.anticipy_tasks_v2 FROM anon;
REVOKE ALL ON public.anticipy_tasks_v2 FROM authenticated;
GRANT SELECT ON public.anticipy_tasks_v2 TO authenticated;
GRANT ALL ON public.anticipy_tasks_v2 TO service_role;

COMMENT ON TABLE public.anticipy_tasks_v2 IS
  'v-final-prototype typed-Task contract. One row per Intent the middle layer has decided to dispatch. The Mac executor app subscribes to Realtime channel task.dispatched.{user_id} to pick these up. CASCADE on intent_id so a rolled-back intent removes its task.';


-- ─── anticipy_results_v2 ────────────────────────────────────────────────
--
-- The executor writes one row per Task it has attempted. Captures evidence
-- (screenshots, DOM snapshots, parsed confirmation emails), the symbolic
-- verifier's CERTIFIED/NOT_CERTIFIED, and the saga rollback status if
-- compensate.py was invoked.
--
-- Schema mirrors the prompt verbatim:
--
--   Result {
--     task_id, status, executed_at, evidence, verifier_output,
--     steps_completed, steps_failed, total_cost_usd, total_latency_ms,
--     aevoy_email_sent, aevoy_email_id
--   }
CREATE TABLE IF NOT EXISTS public.anticipy_results_v2 (
  task_id              uuid        PRIMARY KEY REFERENCES public.anticipy_tasks_v2(task_id) ON DELETE CASCADE,
  status               text        NOT NULL
                                   CHECK (status IN ('executed','failed','rolled_back','refused')),
  executed_at          timestamptz,
  evidence             jsonb       NOT NULL DEFAULT '{
    "screenshots": [],
    "dom_snapshots": [],
    "parsed_confirmations": []
  }'::jsonb,
  verifier_output      text        NOT NULL
                                   CHECK (verifier_output IN ('CERTIFIED','NOT_CERTIFIED')),
  steps_completed      integer     NOT NULL DEFAULT 0 CHECK (steps_completed >= 0),
  steps_failed         integer     NOT NULL DEFAULT 0 CHECK (steps_failed >= 0),
  total_cost_usd       numeric(10, 6),
  total_latency_ms     integer     CHECK (total_latency_ms IS NULL OR total_latency_ms >= 0),
  aevoy_email_sent     boolean     NOT NULL DEFAULT false,
  aevoy_email_id       text,
  created_at           timestamptz NOT NULL DEFAULT now()
);

-- "What did this user finish recently?" — drives the /engine page status
-- view and the watchdog canary.
CREATE INDEX IF NOT EXISTS anticipy_results_v2_status_idx
  ON public.anticipy_results_v2 (status, created_at DESC);

-- "Find verified successes for the fleet learning flywheel" — drives the
-- Phase 9 skill_library promotion query.
CREATE INDEX IF NOT EXISTS anticipy_results_v2_verifier_idx
  ON public.anticipy_results_v2 (verifier_output, status, created_at DESC);

ALTER TABLE public.anticipy_results_v2 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.anticipy_results_v2 FORCE ROW LEVEL SECURITY;

-- Read policy joins through tasks_v2 to recover user_id (results don't
-- store it directly to keep the row small).
DROP POLICY IF EXISTS "results_v2: users see their own via task join" ON public.anticipy_results_v2;
CREATE POLICY "results_v2: users see their own via task join"
  ON public.anticipy_results_v2
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1
      FROM public.anticipy_tasks_v2 t
      WHERE t.task_id = anticipy_results_v2.task_id
        AND t.user_id = auth.uid()::text
    )
  );

DROP POLICY IF EXISTS "results_v2: deny direct writes" ON public.anticipy_results_v2;
CREATE POLICY "results_v2: deny direct writes"
  ON public.anticipy_results_v2
  FOR INSERT
  WITH CHECK (false);

DROP POLICY IF EXISTS "results_v2: deny direct updates" ON public.anticipy_results_v2;
CREATE POLICY "results_v2: deny direct updates"
  ON public.anticipy_results_v2
  FOR UPDATE
  USING (false)
  WITH CHECK (false);

DROP POLICY IF EXISTS "results_v2: deny direct deletes" ON public.anticipy_results_v2;
CREATE POLICY "results_v2: deny direct deletes"
  ON public.anticipy_results_v2
  FOR DELETE
  USING (false);

REVOKE ALL ON public.anticipy_results_v2 FROM PUBLIC;
REVOKE ALL ON public.anticipy_results_v2 FROM anon;
REVOKE ALL ON public.anticipy_results_v2 FROM authenticated;
GRANT SELECT ON public.anticipy_results_v2 TO authenticated;
GRANT ALL ON public.anticipy_results_v2 TO service_role;

COMMENT ON TABLE public.anticipy_results_v2 IS
  'v-final-prototype typed-Result contract. One row per Task the executor has attempted. Contains evidence, symbolic verifier output, and saga rollback status. CASCADE on task_id. Read by the watchdog (Phase 9) and the fleet-learning skill promotion (Phase 9).';


-- ─── Realtime publication ──────────────────────────────────────────────
-- Add the three v2 tables to the supabase_realtime publication so
-- subscribers on the three channels get push notifications on INSERT.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime'
  ) THEN
    BEGIN
      ALTER PUBLICATION supabase_realtime ADD TABLE public.anticipy_intents_v2;
    EXCEPTION WHEN duplicate_object THEN
      NULL;  -- already in publication; idempotent
    END;
    BEGIN
      ALTER PUBLICATION supabase_realtime ADD TABLE public.anticipy_tasks_v2;
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;
    BEGIN
      ALTER PUBLICATION supabase_realtime ADD TABLE public.anticipy_results_v2;
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;
  END IF;
END $$;
