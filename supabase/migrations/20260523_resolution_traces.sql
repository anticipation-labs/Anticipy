-- Resolution traces emitted by the local engine for each judged post-ASR
-- transcript window. These rows are evidence that input reached the real
-- resolution/compose boundary; they are not success flags for actions.

CREATE TABLE IF NOT EXISTS public.resolution_traces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL,
  ingest_id text NOT NULL,
  source text NOT NULL,
  transcript text NOT NULL DEFAULT '',
  reference text NOT NULL DEFAULT '',
  resolved_to text,
  layer_used integer NOT NULL DEFAULT 0,
  confidence numeric NOT NULL DEFAULT 0,
  confirm_card_surfaced boolean NOT NULL DEFAULT false,
  candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
  plan jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS resolution_traces_user_created_idx
  ON public.resolution_traces (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS resolution_traces_ingest_idx
  ON public.resolution_traces (ingest_id);

ALTER TABLE public.resolution_traces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resolution_traces FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "resolution_traces_select_own" ON public.resolution_traces;
DROP POLICY IF EXISTS "resolution_traces_insert_own" ON public.resolution_traces;

CREATE POLICY "resolution_traces_select_own"
  ON public.resolution_traces
  FOR SELECT
  TO authenticated
  USING ((select auth.uid())::text = user_id);

CREATE POLICY "resolution_traces_insert_own"
  ON public.resolution_traces
  FOR INSERT
  TO authenticated
  WITH CHECK ((select auth.uid())::text = user_id);

GRANT SELECT, INSERT ON TABLE public.resolution_traces TO authenticated;
GRANT SELECT, INSERT ON TABLE public.resolution_traces TO service_role;

COMMENT ON TABLE public.resolution_traces IS
  'Per-window local-engine reference-resolution trace, inserted through the authenticated cloud trace route.';
