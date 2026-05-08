-- proactive_training_corpus view
--
-- Joins anticipy_intents + anticipy_sessions + anticipy_transcripts +
-- anticipy_preferences + anticipy_actions into one row per completed intent
-- so an offline distillation / few-shot pipeline can pull a clean training
-- corpus from real production signal.
--
-- Privacy + access:
--   - The view itself is created in the public schema (Supabase REST does not
--     expose views in other schemas easily) but has REVOKE ALL FROM anon and
--     authenticated. Only the service_role can SELECT from it.
--   - Test users (e2e-test-* and *@anticipy-test.local) are filtered out of
--     the JOIN so synthetic benchmark data never poisons the corpus.
--   - Only intents older than 48h are included so in-flight items never leak.
--   - Only intents that reached a TERMINAL state are emitted: confirmed,
--     rejected, executed, failed, auto_proceeded. "pending" and
--     "awaiting_user" are dropped (no signal yet).
--
-- One row per intent. Output columns:
--   intent_id              : uuid
--   created_at             : timestamptz of intent creation
--   user_id                : session.user_id (text — engine_user.id or supabase auth uid)
--   user_email             : session.user_email (already filtered for tests, but caller may use it for further filtering)
--   transcript_window      : the conversation window that produced the intent.
--                            Concatenates anticipy_transcripts rows for the
--                            session (newline separated) when present;
--                            falls back to the intent's evidence_quote when
--                            no transcript rows are stored.
--   extracted_intent_json  : the intent itself, jsonb — action_type, summary,
--                            evidence_quote, parameters, importance, confidence
--   gate_verdict           : terminal status (confirmed / rejected / executed / failed / auto_proceeded)
--   signal_kind            : preference signal recorded against this intent
--                            (accept / reject / edit / auto_proceed) when present.
--                            NULL when no preference row was ever written.
--   signal_reasoning       : the short LLM-summarized reason for the signal
--                            (e.g., "user dislikes morning meetings").
--   executed_outcome       : jsonb with {executed: bool, action_status: text, action_result: jsonb}
--                            describing whether anticipy_actions ran for this
--                            intent and what came back.

CREATE OR REPLACE VIEW public.proactive_training_corpus
WITH (security_invoker = true) AS
WITH terminal_intents AS (
  SELECT
    i.id                  AS intent_id,
    i.session_id,
    i.action_type,
    i.summary_for_user,
    i.evidence_quote,
    i.parameters,
    i.importance,
    i.confidence,
    i.status              AS gate_verdict,
    i.execution_result,
    i.created_at,
    i.executed_at
  FROM public.anticipy_intents i
  WHERE i.status IN ('confirmed', 'rejected', 'executed', 'failed', 'auto_proceeded')
    AND i.created_at < (NOW() - INTERVAL '48 hours')
),
session_filtered AS (
  -- Drop test/synthetic users so the corpus only contains real production signal.
  -- Match the e2e-test-* and *@anticipy-test.local conventions used by the test harness.
  SELECT
    ti.*,
    s.user_id,
    s.user_email
  FROM terminal_intents ti
  JOIN public.anticipy_sessions s ON s.id = ti.session_id
  WHERE COALESCE(s.user_email, '') NOT LIKE 'e2e-test-%'
    AND COALESCE(s.user_email, '') NOT LIKE '%@anticipy-test.local'
    AND COALESCE(ti.summary_for_user, '') NOT LIKE 'Test race intent%'
    AND COALESCE(ti.summary_for_user, '') NOT LIKE 'Test concurrent confirm%'
),
transcript_windows AS (
  -- Build the transcript window per session. When anticipy_transcripts has
  -- rows for the session, concatenate them in order. When it does not (most
  -- sessions store transcripts on-device only), fall back to the intent's
  -- evidence_quote so every row in the view has SOMETHING to learn from.
  SELECT
    sf.intent_id,
    COALESCE(
      (
        SELECT string_agg(t.text, E'\n' ORDER BY t.start_time)
        FROM public.anticipy_transcripts t
        WHERE t.session_id = sf.session_id
          AND COALESCE(t.is_final, true) = true
      ),
      sf.evidence_quote,
      ''
    ) AS transcript_window
  FROM session_filtered sf
),
prefs AS (
  -- Match preferences to intents on (action_type, summary head). preferences
  -- table doesn't carry intent_id directly today.
  SELECT DISTINCT ON (sf.intent_id)
    sf.intent_id,
    p.signal       AS signal_kind,
    p.reasoning    AS signal_reasoning
  FROM session_filtered sf
  LEFT JOIN public.anticipy_preferences p
    ON p.action_type = sf.action_type
   AND LEFT(LOWER(COALESCE(p.intent_summary, '')), 80) = LEFT(LOWER(COALESCE(sf.summary_for_user, '')), 80)
   AND p.created_at >= sf.created_at - INTERVAL '5 minutes'
   AND p.created_at <= sf.created_at + INTERVAL '24 hours'
  ORDER BY sf.intent_id, p.created_at DESC
),
actions AS (
  -- Most-recent action row per intent (intents normally execute zero or one time).
  SELECT DISTINCT ON (a.intent_id)
    a.intent_id,
    a.status   AS action_status,
    a.result   AS action_result
  FROM public.anticipy_actions a
  ORDER BY a.intent_id, a.executed_at DESC NULLS LAST
)
SELECT
  sf.intent_id,
  sf.created_at,
  sf.user_id,
  sf.user_email,
  tw.transcript_window,
  jsonb_build_object(
    'action_type',     sf.action_type,
    'summary',         sf.summary_for_user,
    'evidence_quote',  sf.evidence_quote,
    'parameters',      sf.parameters,
    'importance',      sf.importance,
    'confidence',      sf.confidence
  )                                     AS extracted_intent_json,
  sf.gate_verdict,
  pr.signal_kind,
  pr.signal_reasoning,
  jsonb_build_object(
    'executed',       (sf.gate_verdict IN ('executed', 'auto_proceeded')) OR (ac.action_status = 'success'),
    'action_status',  ac.action_status,
    'action_result',  ac.action_result,
    'execution_result_text', sf.execution_result
  )                                     AS executed_outcome
FROM session_filtered sf
LEFT JOIN transcript_windows tw ON tw.intent_id = sf.intent_id
LEFT JOIN prefs              pr ON pr.intent_id = sf.intent_id
LEFT JOIN actions            ac ON ac.intent_id = sf.intent_id;

-- Service-role-only access. Anon and authenticated MUST NOT see real-user
-- transcripts. The export script reads with SUPABASE_SERVICE_ROLE_KEY.
REVOKE ALL ON public.proactive_training_corpus FROM PUBLIC;
REVOKE ALL ON public.proactive_training_corpus FROM anon;
REVOKE ALL ON public.proactive_training_corpus FROM authenticated;
GRANT SELECT ON public.proactive_training_corpus TO service_role;

COMMENT ON VIEW public.proactive_training_corpus IS
  'Training corpus for distillation / few-shot calibration. service_role only. Filters: test users, < 48h age, non-terminal status. See engine/data/CORPUS.md.';
