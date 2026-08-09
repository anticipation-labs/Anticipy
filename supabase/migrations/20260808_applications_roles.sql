-- Extends the existing applications table for the shared /apply funnel.
--
-- Additive only: nothing is dropped and no existing column changes type, so
-- the /build funnel keeps working exactly as it does now. Safe to run twice.
--
-- Two shapes now share one table:
--   /build  writes thing_1 / thing_2  (the original hardware funnel)
--   /apply  writes roles + answers    (role-specific Q&A as structured JSON)
-- Storing the role answers as JSON rather than as fixed columns means adding a
-- fifth role later is a code change, not another migration.

ALTER TABLE public.anticipy_applications
  -- Everything the candidate selected. An array because somebody can say they
  -- fit both software and hardware.
  ADD COLUMN IF NOT EXISTS roles text[] NOT NULL DEFAULT '{}',
  -- Which question set those selections resolved to (software + hardware
  -- resolves to hardware_software).
  ADD COLUMN IF NOT EXISTS question_set text,
  -- [{ id, question, answer }] in the order they were asked.
  ADD COLUMN IF NOT EXISTS answers jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS links text,
  ADD COLUMN IF NOT EXISTS availability text,
  ADD COLUMN IF NOT EXISTS start_date text,
  ADD COLUMN IF NOT EXISTS vancouver text,
  -- Legal right to work, and meeting the applicable minimum working age.
  -- Deliberately a boolean answer to a yes/no question — no date of birth and
  -- no exact age is collected anywhere in this funnel.
  ADD COLUMN IF NOT EXISTS work_authorized boolean,
  -- Which page the application came from, so /build and /apply are separable.
  ADD COLUMN IF NOT EXISTS source_form text NOT NULL DEFAULT 'build';

-- /apply stores its answers in `answers`, so the two /build-specific columns
-- must stop being mandatory. Existing rows are untouched.
ALTER TABLE public.anticipy_applications ALTER COLUMN thing_1 DROP NOT NULL;
ALTER TABLE public.anticipy_applications ALTER COLUMN thing_2 DROP NOT NULL;

CREATE INDEX IF NOT EXISTS anticipy_applications_role_idx
  ON public.anticipy_applications (question_set, created_at DESC);
CREATE INDEX IF NOT EXISTS anticipy_applications_source_idx
  ON public.anticipy_applications (source_form, created_at DESC);

-- RLS is already enabled on this table; re-asserted so running this file on a
-- fresh database cannot leave it open.
ALTER TABLE public.anticipy_applications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.anticipy_applications FROM anon, authenticated;

-- Verify.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'anticipy_applications'
  AND column_name IN ('roles','question_set','answers','links','availability',
                      'start_date','vancouver','work_authorized','source_form',
                      'thing_1','thing_2')
ORDER BY column_name;
