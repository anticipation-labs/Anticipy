-- Applications submitted from /build.
--
-- Replaces the earlier draft of this file. That version was never run, so
-- this is a straight rewrite rather than an ALTER: the flow changed from
-- three "things" plus a work-authorisation question to two things, each with
-- an optional follow-up, and attachments became a list rather than a single
-- résumé.
--
-- RLS is enabled and anon/authenticated revoked in the same breath as the
-- table is created. A prior audit found another table world-readable through
-- the public anon key — which ships inside the site's own JavaScript — and
-- this one holds names, emails, locations and pointers to private files.
--
-- Files are NOT stored here. They live in the private `applications` bucket
-- (public = false) and this table holds only object paths. Links are minted
-- as short-lived signed URLs at email time, so a leaked row exposes no file.

DROP TABLE IF EXISTS public.anticipy_applications;

CREATE TABLE public.anticipy_applications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  name text NOT NULL,
  email text NOT NULL,
  location text NOT NULL,

  -- Two things they built. The first of each pair is required; the "_extra"
  -- is the optional "anything else?" screen that follows it.
  thing_1 text NOT NULL,
  thing_1_extra text,
  thing_2 text NOT NULL,
  thing_2_extra text,

  -- Which answers were spoken rather than typed. Useful for reading the
  -- transcript charitably — dictated prose has different texture.
  spoken_fields text[] NOT NULL DEFAULT '{}',

  -- [{ path, filename, size, type }] inside the private bucket.
  attachments jsonb NOT NULL DEFAULT '[]'::jsonb,
  resume_link text,

  -- What the domain check said at submit time. Advisory only: it is recorded
  -- so a bounce can be correlated later, never used to reject an applicant.
  email_domain_ok boolean,
  email_domain_reason text,
  -- Set by the Resend bounce webhook. This is the only real proof the address
  -- exists, and it arrives after the fact.
  email_bounced boolean NOT NULL DEFAULT false,

  utm_source text,
  utm_medium text,
  utm_campaign text,
  referrer text,
  landing_path text,

  ip_address text,
  user_agent text,

  status text NOT NULL DEFAULT 'new',
  notes text,

  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX anticipy_applications_created_idx
  ON public.anticipy_applications (created_at DESC);
CREATE INDEX anticipy_applications_status_idx
  ON public.anticipy_applications (status, created_at DESC);

-- One application per address: a resubmission updates the existing record
-- rather than splitting a reviewer's attention across two half-applications.
CREATE UNIQUE INDEX anticipy_applications_email_uniq
  ON public.anticipy_applications (lower(email));

ALTER TABLE public.anticipy_applications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.anticipy_applications FROM anon, authenticated;

-- Verify: rls_enabled true, anon_can_select false.
SELECT
  c.relname        AS table_name,
  c.relrowsecurity AS rls_enabled,
  has_table_privilege('anon', c.oid, 'SELECT') AS anon_can_select
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = 'anticipy_applications';
