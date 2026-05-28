-- Per-user "second brain" — distilled style profile that the first AI
-- (intent extractor + gate) reads on every analyze call. Updated
-- asynchronously by a meta-monitor that watches confirm / reject /
-- auto-proceed signals and re-summarizes patterns over time.
--
-- One row per user_id. ON CONFLICT updates in-place rather than
-- appending — the profile is a moving snapshot, not an event log.
-- The event log lives in anticipy_preferences and the training corpus.
CREATE TABLE IF NOT EXISTS public.anticipy_user_profile (
  user_id           text PRIMARY KEY,
  style_summary     text NOT NULL DEFAULT '',
  common_accepts    jsonb NOT NULL DEFAULT '[]'::jsonb,
  common_rejects    jsonb NOT NULL DEFAULT '[]'::jsonb,
  drift_alerts      jsonb NOT NULL DEFAULT '[]'::jsonb,
  signal_count      integer NOT NULL DEFAULT 0,
  updated_at        timestamptz NOT NULL DEFAULT now()
);

-- service-role-only: this is essentially a derived cache of the
-- user's preference history. Don't expose to anon/authenticated.
ALTER TABLE public.anticipy_user_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.anticipy_user_profile FORCE ROW LEVEL SECURITY;

COMMENT ON TABLE public.anticipy_user_profile IS
  'Meta-monitor distilled per-user style profile. service_role-only. Read by /api/engine/analyze, written by buildUserProfile() after each confirm/reject/auto-proceed.';
