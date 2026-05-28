-- Onboarding dossier snapshots written by the local Mac engine after a
-- signed-in user provisions it from anticipy.ai/app. The local JSON remains
-- the engine's source of truth; this table gives the hosted app and verifier a
-- per-user cloud artifact to inspect.

CREATE TABLE IF NOT EXISTS public.dossiers (
  user_id text PRIMARY KEY,
  profile jsonb NOT NULL DEFAULT '{}'::jsonb,
  pronoun_map jsonb NOT NULL DEFAULT '{}'::jsonb,
  people jsonb NOT NULL DEFAULT '{}'::jsonb,
  do_not_touch jsonb NOT NULL DEFAULT '[]'::jsonb,
  source text NOT NULL DEFAULT 'local_engine',
  field_count integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.dossiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dossiers FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "dossiers_select_own" ON public.dossiers;
DROP POLICY IF EXISTS "dossiers_insert_own" ON public.dossiers;
DROP POLICY IF EXISTS "dossiers_update_own" ON public.dossiers;

CREATE POLICY "dossiers_select_own"
  ON public.dossiers
  FOR SELECT
  TO authenticated
  USING ((select auth.uid())::text = user_id);

CREATE POLICY "dossiers_insert_own"
  ON public.dossiers
  FOR INSERT
  TO authenticated
  WITH CHECK ((select auth.uid())::text = user_id);

CREATE POLICY "dossiers_update_own"
  ON public.dossiers
  FOR UPDATE
  TO authenticated
  USING ((select auth.uid())::text = user_id)
  WITH CHECK ((select auth.uid())::text = user_id);

GRANT SELECT, INSERT, UPDATE ON TABLE public.dossiers TO authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.dossiers TO service_role;

COMMENT ON TABLE public.dossiers IS
  'Anticipy local-engine onboarding dossier snapshot. Written by authenticated sync and read by the journey verifier.';
