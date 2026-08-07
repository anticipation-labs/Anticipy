-- Offer engine: behavioural visitor profiles, configurable discount tiers,
-- and an event log for measuring whether any of it is actually incremental.
--
-- Three design rules encoded here, each of which is expensive to retrofit:
--
--  1. The tier is DERIVED AND STORED SERVER-SIDE, keyed to an httpOnly
--     first-party cookie. The client is never asked what tier it is and its
--     answer is never trusted — otherwise the discount ladder is a DevTools
--     exercise and everyone pays the floor price.
--
--  2. Tier config lives in the database, not in code, so changing an offer is
--     an admin action rather than a deploy. `stripe_coupon_id` is the join to
--     Stripe; the amount is mirrored here so the popup endpoint never has to
--     call the Stripe API on a page view.
--
--  3. Every impression, dismissal and redemption is logged with the holdout
--     arm attached. Without the arm on the row you can measure that discounted
--     orders converted, but never that the discount CAUSED them — which is the
--     only question that decides whether this engine makes or loses money.

-- ── Visitor behavioural profile ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.anticipy_visitor_profiles (
  visitor_id text PRIMARY KEY,

  -- Behaviour accumulated across sessions. Engaged time only, never wall
  -- clock; see src/lib/analytics.ts for why a backgrounded tab counts zero.
  session_count integer NOT NULL DEFAULT 1,
  engaged_seconds integer NOT NULL DEFAULT 0,
  max_scroll_pct integer NOT NULL DEFAULT 0,
  price_dwell_seconds integer NOT NULL DEFAULT 0,
  pages_seen text[] NOT NULL DEFAULT '{}',
  sections_seen text[] NOT NULL DEFAULT '{}',

  -- Friction signals. These push a visitor UP the discount ladder, because
  -- they mark a persuadable rather than a sure-thing.
  friction_flags text[] NOT NULL DEFAULT '{}',
  checkout_started_count integer NOT NULL DEFAULT 0,
  checkout_abandoned_count integer NOT NULL DEFAULT 0,
  email_field_completed boolean NOT NULL DEFAULT false,
  email_captured boolean NOT NULL DEFAULT false,

  -- Acquisition context, captured once on first touch.
  referrer_class text,
  utm_source text,
  utm_medium text,
  utm_campaign text,
  landing_path text,

  -- Two scores, not one. A single propensity score systematically
  -- mis-targets: the highest-propensity visitors are exactly the ones who
  -- would have converted anyway, so discounting them is pure margin loss.
  intent_score integer NOT NULL DEFAULT 0,
  friction_score integer NOT NULL DEFAULT 0,

  assigned_tier text,
  tier_assigned_at timestamptz,
  tier_expires_at timestamptz,
  offer_shown_count integer NOT NULL DEFAULT 0,
  offer_dismissed_count integer NOT NULL DEFAULT 0,
  offer_redeemed boolean NOT NULL DEFAULT false,

  -- Randomised at first touch and never recomputed. Reassigning a returning
  -- visitor to a different arm silently destroys the experiment.
  holdout_arm text NOT NULL DEFAULT 'ladder',

  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS anticipy_visitor_profiles_last_seen_idx
  ON public.anticipy_visitor_profiles (last_seen_at DESC);
CREATE INDEX IF NOT EXISTS anticipy_visitor_profiles_tier_idx
  ON public.anticipy_visitor_profiles (assigned_tier, holdout_arm);

-- ── Discount tiers ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.anticipy_offer_tiers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tier_key text UNIQUE NOT NULL,
  label text NOT NULL,
  sort_order integer NOT NULL DEFAULT 0,

  -- amount_off in cents, never percent_off. None of the target prices on
  -- this ladder is exactly expressible as a percentage of the list price,
  -- and Stripe does not document how it rounds percentage discounts — so a
  -- percentage coupon would land at $119.99 or $120.01 unpredictably.
  -- amount_off is exact, and it is also the only form Stripe allows
  -- currency_options on, which the CAD price will need.
  amount_off_cents integer NOT NULL DEFAULT 0,
  stripe_coupon_id text,

  headline text NOT NULL,
  subhead text,

  -- Entry rules, evaluated server-side against the visitor profile.
  min_intent_score integer NOT NULL DEFAULT 0,
  max_intent_score integer,
  min_friction_score integer NOT NULL DEFAULT 0,
  min_sessions integer NOT NULL DEFAULT 1,

  active boolean NOT NULL DEFAULT true,
  max_redemptions integer,
  redemption_count integer NOT NULL DEFAULT 0,
  expires_at timestamptz,

  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS anticipy_offer_tiers_active_idx
  ON public.anticipy_offer_tiers (active, sort_order);

-- ── Offer event log ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.anticipy_offer_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  visitor_id text NOT NULL,
  tier_key text,
  event text NOT NULL,          -- shown | accepted | dismissed | suppressed | redeemed
  trigger_type text,            -- scroll | dwell | repeat_visit | checkout_abandon | exit_intent
  price_before_cents integer,
  price_after_cents integer,
  holdout_arm text,
  meta jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS anticipy_offer_events_visitor_idx
  ON public.anticipy_offer_events (visitor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS anticipy_offer_events_arm_idx
  ON public.anticipy_offer_events (holdout_arm, event, created_at DESC);

-- ── Seed ladder ──────────────────────────────────────────────────────
-- List price $149.99. Target median realized price $120.00.
--
-- The share-of-orders mix below is a CONSTRUCTION, not measured data. Before
-- trusting it, backfit these rules over the existing PostHog history: every
-- past buyer already carries a full pre-purchase behavioural trail, because
-- Stripe checkout identified them and PostHog merged their anonymous events.
-- If the real distribution differs, the realized median moves with it.
--
--  tier  price    off      target share   cumulative
--  T0    149.99   $0       10%            10%
--  T1    139.00   $10.99   10%            20%
--  T2    134.00   $15.99   10%            30%
--  T3    129.00   $20.99   10%            40%
--  T4    124.00   $25.99    8%            48%
--  T5    120.00   $29.99   20%            68%   <- median lands here
--  T6    115.00   $34.99   17%            85%
--  T7    110.00   $39.99   15%           100%
--                          mean $125.17 / median $120.00

INSERT INTO public.anticipy_offer_tiers
  (tier_key, label, sort_order, amount_off_cents, headline, subhead,
   min_intent_score, max_intent_score, min_friction_score, min_sessions)
VALUES
  ('T0', 'Full price — high intent',        0,    0,
   'You are in Batch 1',                'Reserved at $149.99, free shipping to the US and Canada.',
   60, NULL, 0, 1),
  ('T1', 'Engaged, low friction',           1, 1099,
   'Your price: $139',                  'Because you have spent real time with this.',
   45, 59, 0, 1),
  ('T2', 'Returning visitor',               2, 1599,
   'Your price: $134',                  'You came back. That earns something.',
   35, 44, 0, 2),
  ('T3', 'Deep reader',                     3, 2099,
   'Your price: $129',                  'You read the whole thing.',
   28, 34, 0, 1),
  ('T4', 'Considering',                     4, 2599,
   'Your price: $124',                  'Still deciding? This might help.',
   20, 27, 0, 1),
  ('T5', 'Hesitant — friction seen',        5, 2999,
   'Your price: $120',                  'The best price we offer before launch.',
   14, 19, 1, 1),
  ('T6', 'Abandoned checkout',              6, 3499,
   'Your price: $115',                  'You got as far as checkout. Let us close the gap.',
   10, 13, 2, 1),
  ('T7', 'Deep abandon — floor',            7, 3999,
   'Your price: $110',                  'This is the floor. It does not go lower.',
   0,  9,  2, 2)
ON CONFLICT (tier_key) DO NOTHING;
