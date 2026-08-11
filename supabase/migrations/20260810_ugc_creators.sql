-- The Anticipy UGC Creator program.
--
-- A separate table from anticipy_applications on purpose: a job application is
-- read once and closed, whereas a creator is an ongoing relationship with a
-- link, submitted videos and money owed. Folding them together would mean one
-- table where half the columns are null for half the rows.
--
-- Additive only. Safe to run twice.

CREATE TABLE IF NOT EXISTS public.anticipy_ugc_creators (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at   timestamptz NOT NULL DEFAULT now(),

  name         text NOT NULL,
  email        text NOT NULL,
  location     text,

  -- Channels. All optional individually; the form requires at least one,
  -- because without a channel there is no way to verify a view count.
  instagram    text,
  tiktok       text,
  x_handle     text,
  linkedin     text,

  -- The creator's chosen link: anticipy.ai/c/<handle>. Unique, lowercase.
  handle       text NOT NULL,

  -- [{ id, question, answer }] in the order they were asked.
  answers      jsonb NOT NULL DEFAULT '[]'::jsonb,

  payout_method text,
  payout_detail text,

  -- Both are affirmative opt-ins captured at submit time, not fine print.
  -- agreed_rights_days records the licence length actually shown, so changing
  -- the offer later cannot rewrite what an existing creator agreed to.
  agreed_disclosure  boolean NOT NULL DEFAULT false,
  agreed_rights      boolean NOT NULL DEFAULT false,
  agreed_rights_days integer,

  -- The terms in force when they signed up, so a rate change is never applied
  -- retroactively to somebody who joined under the old one.
  terms_per_video        integer,
  terms_view_floor       integer,
  terms_purchase_pct     integer,

  status       text NOT NULL DEFAULT 'pending',
  notes        text,

  utm_source   text,
  utm_medium   text,
  utm_campaign text,
  referrer     text,
  landing_path text,
  ip_address   text,
  user_agent   text
);

-- Case-insensitive uniqueness on both natural keys. Expression indexes, so
-- inserts must go through insert-then-update rather than ON CONFLICT naming
-- the bare column — Postgres will not match 42P10 against an expression index.
CREATE UNIQUE INDEX IF NOT EXISTS anticipy_ugc_creators_handle_key
  ON public.anticipy_ugc_creators (lower(handle));
CREATE UNIQUE INDEX IF NOT EXISTS anticipy_ugc_creators_email_key
  ON public.anticipy_ugc_creators (lower(email));
CREATE INDEX IF NOT EXISTS anticipy_ugc_creators_created_idx
  ON public.anticipy_ugc_creators (created_at DESC);

-- Holds names, emails, social handles and payout details. Never reachable
-- with the public anon key — only the service role, server-side.
ALTER TABLE public.anticipy_ugc_creators ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.anticipy_ugc_creators FROM anon, authenticated;

-- Verify.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'anticipy_ugc_creators'
ORDER BY ordinal_position;
