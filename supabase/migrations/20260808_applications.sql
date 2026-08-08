-- Applications submitted from /build.
--
-- RLS is enabled and anon/authenticated are revoked in the same breath as the
-- table is created. The audit on 2026-08-07 found engine_users world-readable
-- through the public anon key, which ships inside the site's own JavaScript
-- bundle — this table holds names, email addresses, locations and résumé
-- pointers, so it is locked from the first second it exists rather than as a
-- follow-up step someone forgets.
--
-- Résumés themselves are NOT stored here. They live in the private
-- `applications` storage bucket (public = false) and this table holds only
-- the object path. Links are minted as short-lived signed URLs at email time,
-- so a leaked row still exposes no document.

CREATE TABLE IF NOT EXISTS public.anticipy_applications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  name text NOT NULL,
  email text NOT NULL,
  location text NOT NULL,

  -- The three things they built. This is the substance of the application.
  thing_1 text NOT NULL,
  thing_2 text NOT NULL,
  thing_3 text NOT NULL,

  work_authorized boolean NOT NULL,

  -- Object path inside the private `applications` bucket, never a URL.
  resume_path text,
  resume_filename text,
  resume_size_bytes integer,

  -- Attribution, captured as hidden fields on the form.
  utm_source text,
  utm_medium text,
  utm_campaign text,
  referrer text,
  landing_path text,

  ip_address text,
  user_agent text,

  -- Set once the applicant has been contacted, so the list stays workable.
  status text NOT NULL DEFAULT 'new',
  notes text,

  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS anticipy_applications_created_idx
  ON public.anticipy_applications (created_at DESC);
CREATE INDEX IF NOT EXISTS anticipy_applications_status_idx
  ON public.anticipy_applications (status, created_at DESC);

-- One application per email address. A refreshed submission should update the
-- existing record rather than quietly creating a duplicate that splits the
-- reviewer's attention across two half-applications.
CREATE UNIQUE INDEX IF NOT EXISTS anticipy_applications_email_uniq
  ON public.anticipy_applications (lower(email));

ALTER TABLE public.anticipy_applications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.anticipy_applications FROM anon, authenticated;
