# PRECEDENT: the fellowship is already on Cloudflare D1

Discovered live on 2026-09-03 in Cloudflare account `114587b715e702461766369b01d42fc7`
(`omar@anticipy.ai`), database `anticipy-fellowship` (uuid 2f2abfae-9618-45f2-b53d-d302274bcb52,
created 2026-09-03T06:08Z).

WHY THIS MATTERS. The audit flagged `fellows` and `fellow_applications` as live PocketBase
collections with NO migration in any branch — schema unknowable from the repo. They are not
unknowable: somebody has already converted them to D1. This file is that schema, read back
from the live database, and it is the field-mapping convention the rest of the port should
follow.

STATE. Schema only. All nine tables are EMPTY (verified row counts, all 0), and
anticipyfellowship.com still answers from Vercel (`server: Vercel`) fronting the Railway
PocketBase. So this is a staged, not-yet-cut-over migration.

THE CONVENTION IT ESTABLISHES (PocketBase field type -> SQLite):
    text/select/relation/date/json  ->  TEXT    NOT NULL DEFAULT ''
    number                          ->  REAL    NOT NULL DEFAULT 0
    bool                            ->  INTEGER NOT NULL DEFAULT 0
    id                              ->  TEXT PRIMARY KEY
    created / updated               ->  TEXT    NOT NULL DEFAULT ''

  Partial-unique indexes are preserved correctly, which is the detail most conversions drop:
    CREATE UNIQUE INDEX idx_fpayout_idem ON fellow_payouts (idempotency_key)
      WHERE idempotency_key != ''

TWO CAVEATS BEFORE COPYING IT WHOLESALE:
  1. `NOT NULL DEFAULT ''` erases the difference between "empty" and "never set". PocketBase
     had the same weakness, so this is faithful, but any new code must not read '' as false.
  2. `REAL` is used for integer counters (attempts, clicks_total, payout_seq, oembed_status,
     http_status). Faithful to PocketBase's single number type; INTEGER would be truer to the
     data. Keep REAL for anything holding money (amount_usd, commission_usd).

22 explicit indexes + 9 automatic (PK/UNIQUE). DDL below is read verbatim from sqlite_master.

## Tables

```sql
CREATE TABLE fellow_applications (
  id TEXT PRIMARY KEY,
  fellow TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  fellowship TEXT NOT NULL DEFAULT '',
  answers TEXT NOT NULL DEFAULT '',
  ai_verdict TEXT NOT NULL DEFAULT '',
  ai_message TEXT NOT NULL DEFAULT '',
  ai_ok INTEGER NOT NULL DEFAULT 0,
  model TEXT NOT NULL DEFAULT '',
  terms_accepted_at TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT ''
);

CREATE TABLE fellow_clicks (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL DEFAULT '',
  ip_hash TEXT NOT NULL DEFAULT '',
  ua TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT ''
);

CREATE TABLE fellow_codes (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL DEFAULT '',
  code_hash TEXT NOT NULL DEFAULT '',
  expires TEXT NOT NULL DEFAULT '',
  attempts REAL NOT NULL DEFAULT 0,
  used INTEGER NOT NULL DEFAULT 0,
  ip TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT ''
);

CREATE TABLE fellow_conversions (
  id TEXT PRIMARY KEY,
  fellow TEXT NOT NULL DEFAULT '',
  code TEXT NOT NULL DEFAULT '',
  order_ref TEXT NOT NULL DEFAULT '',
  amount_usd REAL NOT NULL DEFAULT 0,
  commission_usd REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT '',
  flags TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  hold_until TEXT NOT NULL DEFAULT '',
  ship_confirmed_at TEXT NOT NULL DEFAULT '',
  paid_via TEXT NOT NULL DEFAULT '',
  entered_by TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT '',
  updated TEXT NOT NULL DEFAULT '',
  pay_after TEXT NOT NULL DEFAULT '',
  payout_key TEXT NOT NULL DEFAULT '',
  payout_attempts REAL NOT NULL DEFAULT 0,
  payout_claimed_at TEXT NOT NULL DEFAULT '',
  paid_at TEXT NOT NULL DEFAULT '',
  payout_ref TEXT NOT NULL DEFAULT '',
  review_reason TEXT NOT NULL DEFAULT '',
  payout_seq REAL NOT NULL DEFAULT 0,
  payout_blocked_on TEXT NOT NULL DEFAULT '',
  payout_checked_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE fellow_meter (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  hour TEXT NOT NULL DEFAULT '',
  calls REAL NOT NULL DEFAULT 0,
  created TEXT NOT NULL DEFAULT '',
  updated TEXT NOT NULL DEFAULT ''
);

CREATE TABLE fellow_payouts (
  id TEXT PRIMARY KEY,
  fellow TEXT NOT NULL DEFAULT '',
  batch TEXT NOT NULL DEFAULT '',
  total_usd REAL NOT NULL DEFAULT 0,
  method TEXT NOT NULL DEFAULT '',
  destination TEXT NOT NULL DEFAULT '',
  transfer_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  sent_at TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT '',
  conversion TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT NOT NULL DEFAULT '',
  attempt REAL NOT NULL DEFAULT 0,
  amount_usd REAL NOT NULL DEFAULT 0,
  vendor TEXT NOT NULL DEFAULT '',
  vendor_order_id TEXT NOT NULL DEFAULT '',
  vendor_reward_id TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT '',
  http_status REAL NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  product_id TEXT NOT NULL DEFAULT '',
  age_band_at_payment TEXT NOT NULL DEFAULT '',
  delivery TEXT NOT NULL DEFAULT '',
  finished_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE fellow_progress (
  id TEXT PRIMARY KEY,
  fellow TEXT NOT NULL DEFAULT '',
  lesson_id TEXT NOT NULL DEFAULT '',
  completed_at TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT ''
);

CREATE TABLE fellow_submissions (
  id TEXT PRIMARY KEY,
  fellow TEXT NOT NULL DEFAULT '',
  platform TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  url_key TEXT NOT NULL DEFAULT '',
  submitted_url TEXT NOT NULL DEFAULT '',
  native_id TEXT NOT NULL DEFAULT '',
  author_handle TEXT NOT NULL DEFAULT '',
  author_claimed TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  thumbnail_url TEXT NOT NULL DEFAULT '',
  verify_state TEXT NOT NULL DEFAULT '',
  verified_at TEXT NOT NULL DEFAULT '',
  oembed_status REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT '',
  removed_by TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  flags TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT '',
  updated TEXT NOT NULL DEFAULT ''
);

CREATE TABLE fellows (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT '',
  birth_month REAL NOT NULL DEFAULT 0,
  birth_year REAL NOT NULL DEFAULT 0,
  age_band TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  parent_email TEXT NOT NULL DEFAULT '',
  parental_consent TEXT NOT NULL DEFAULT '',
  consent_token_hash TEXT NOT NULL DEFAULT '',
  payout_identity_verified INTEGER NOT NULL DEFAULT 0,
  ad_usable INTEGER NOT NULL DEFAULT 0,
  instagram TEXT NOT NULL DEFAULT '',
  tiktok TEXT NOT NULL DEFAULT '',
  x_handle TEXT NOT NULL DEFAULT '',
  linkedin TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  sms_opt_in INTEGER NOT NULL DEFAULT 0,
  fellowship TEXT NOT NULL DEFAULT '',
  waitlist_tracks TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  referral_code TEXT NOT NULL DEFAULT '',
  code_active INTEGER NOT NULL DEFAULT 0,
  code_revoked INTEGER NOT NULL DEFAULT 0,
  clicks_total REAL NOT NULL DEFAULT 0,
  session_hash TEXT NOT NULL DEFAULT '',
  session_expires TEXT NOT NULL DEFAULT '',
  payout_method TEXT NOT NULL DEFAULT '',
  payout_handle TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL DEFAULT '',
  updated TEXT NOT NULL DEFAULT '',
  email_confirmed_at TEXT NOT NULL DEFAULT '',
  ip_address TEXT NOT NULL DEFAULT '',
  welcome_sent_at TEXT NOT NULL DEFAULT '',
  payout_method_set_at TEXT NOT NULL DEFAULT '',
  lifetime_paid_usd REAL NOT NULL DEFAULT 0,
  youtube TEXT NOT NULL DEFAULT '',
  applied_ack_sent_at TEXT NOT NULL DEFAULT '',
  guardian_name TEXT NOT NULL DEFAULT '',
  guardian_email TEXT NOT NULL DEFAULT '',
  guardian_consent_at TEXT NOT NULL DEFAULT '',
  guardian_consent_ip TEXT NOT NULL DEFAULT '',
  guardian_terms_version TEXT NOT NULL DEFAULT '',
  guardian_token_hash TEXT NOT NULL DEFAULT ''
);

```

## Indexes

```sql
CREATE INDEX idx_fapps_email ON fellow_applications (email, fellowship);
CREATE INDEX idx_fclicks ON fellow_clicks (code, created);
CREATE INDEX idx_fcodes_email ON fellow_codes (email, created);
CREATE INDEX idx_fcodes_ip ON fellow_codes (ip, created);
CREATE INDEX `idx_fconv_due` ON `fellow_conversions` (`status`, `pay_after`);
CREATE INDEX idx_fconv_fellow ON fellow_conversions (fellow, status);
CREATE UNIQUE INDEX idx_fconv_order ON fellow_conversions (order_ref);
CREATE INDEX `idx_fconv_parked` ON `fellow_conversions` (`status`, `payout_checked_at`);
CREATE INDEX idx_fellows_code ON fellows (referral_code);
CREATE UNIQUE INDEX idx_fellows_email ON fellows (email);
CREATE INDEX idx_fellows_session ON fellows (session_hash);
CREATE INDEX idx_fellows_status ON fellows (status);
CREATE UNIQUE INDEX idx_fmeter ON fellow_meter (name);
CREATE INDEX `idx_fpayout_conv` ON `fellow_payouts` (`conversion`, `created`);
CREATE UNIQUE INDEX `idx_fpayout_idem` ON `fellow_payouts` (`idempotency_key`) WHERE `idempotency_key` != '';
CREATE INDEX `idx_fpayout_state` ON `fellow_payouts` (`state`);
CREATE INDEX idx_fpayouts ON fellow_payouts (batch);
CREATE UNIQUE INDEX idx_fprog ON fellow_progress (fellow, lesson_id);
CREATE INDEX idx_fsub_author ON fellow_submissions (author_handle);
CREATE INDEX idx_fsub_fellow ON fellow_submissions (fellow, created);
CREATE UNIQUE INDEX idx_fsub_key ON fellow_submissions (url_key) WHERE url_key != '';
CREATE INDEX idx_fsub_platform ON fellow_submissions (platform, created);
```
