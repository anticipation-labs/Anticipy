-- =====================================================================
-- Anticipy — Cloudflare D1 schema
-- Generated from the FINAL STATE of backend/pb_migrations/*.js (58 files,
-- 1700000000_anticipy.js .. 1700000055_active_commitment_identity.js),
-- PocketBase 0.30.4 (backend/Dockerfile:3).
--
-- 26 collections: 12 PRODUCT + 14 INTERNAL HQ.
-- Every column below carries the migration file:line that introduced it.
--
-- ***** THIS FILE IS NOT THE WHOLE PRODUCTION DATABASE. *****
-- The live PocketBase instance serves NINE fellowship collections that no
-- migration in this repo creates -- fellows, fellow_applications,
-- fellow_submissions, fellow_payouts, fellow_conversions, fellow_codes,
-- fellow_clicks, fellow_progress, fellow_meter. Their schema is unknowable
-- from this repo; it is recorded in migration/d1/FELLOWSHIP-PRECEDENT.md,
-- read back from an already-staged (and still empty) D1 database.
-- `internal_people` may also carry columns no migration declares (a password
-- and a face), because /internal/me/password and /internal/people/faces are
-- forwarded by next.config.mjs and answered by nothing in this tree.
-- Read migration/d1/GAPS.md and run the superuser listing it specifies BEFORE
-- writing the importer. One of the routes with no handler here is the route
-- that pays a fellow.
--
-- Independent corroboration of the type mapping below: the staged
-- anticipy-fellowship D1 database reached the same conventions from the same
-- PocketBase source -- text -> TEXT NOT NULL DEFAULT '', number -> REAL,
-- bool -> INTEGER, and partial-unique indexes kept with their WHERE
-- predicate. Two conversions, done separately, agree.
--
-- Apply:
--   wrangler d1 execute anticipy --remote --file=migration/d1/schema.sql
--   wrangler d1 execute anticipy --local  --file=migration/d1/schema.sql
--
-- ---------------------------------------------------------------------
-- HOW POCKETBASE TYPES WERE MAPPED, AND WHERE THE MAPPING IS LOSSY
-- ---------------------------------------------------------------------
-- PocketBase's own DDL is `<col> TEXT DEFAULT '' NOT NULL` for essentially
-- every non-system column; `required` is an APPLICATION-LAYER validator run
-- inside `app.save()`, not a database constraint. Two consequences that this
-- file is built around:
--
--   1. PocketBase NEVER writes SQL NULL into a user field. An unset text /
--      date / relation / file column holds '' and an unset number holds 0.
--      So every column here is `NOT NULL DEFAULT ''` (or `DEFAULT 0`) and the
--      import is a byte-for-byte copy. Do NOT "improve" '' into NULL during
--      import: guard.pb.js:49 and every client filter compares against ''
--      (e.g. `owner_ref=""`, `stage = ''`), and brain/ + the extension do the
--      same. A NULL would silently drop rows out of every one of those filters.
--
--   2. `required` is therefore expressed here as a CHECK. Every `required`
--      field in this tree was declared required AT COLLECTION-CREATION TIME
--      (verified across all 58 migrations — no migration ever promotes an
--      existing optional field to required), so PocketBase validated every
--      row that has ever been written and no legacy row can violate these.
--      If the import rejects a row on one of these CHECKs, that row is
--      already invalid by PocketBase's own rules — fix or drop the row, do
--      not weaken the CHECK. The one exception is called out at
--      agent_audit_sessions.active below.
--
-- Type mapping:
--   text      -> TEXT    NOT NULL DEFAULT ''       (PB `max` is a validator,
--                                                   not a column width; SQLite
--                                                   has no VARCHAR(n) anyway.
--                                                   `max` is carried as a
--                                                   comment for the Worker's
--                                                   validator to re-implement.)
--   editor    -> TEXT    (HTML string) — NOT USED in this tree.
--   email     -> TEXT    NOT NULL DEFAULT ''       (owners.email only)
--   number    -> REAL    NOT NULL DEFAULT 0        LOSSY: PocketBase does not
--                        distinguish int from float; it stores Go float64 in a
--                        NUMERIC column. REAL is chosen over INTEGER because
--                        internal_todos.position is deliberately fractional
--                        (1700000049_todo_position.js:9-16 — midpoint inserts).
--                        Counters (attempts, calls, seq, fetches) round-trip
--                        exactly as REAL up to 2^53; read them with
--                        Math.trunc() in the Worker.
--                        DIVERGENCE, RECONCILE BEFORE CUTOVER:
--                        migration/runbooks/import_d1.py:79 maps number ->
--                        NUMERIC. Both work -- SQLite affinities, not types --
--                        but NUMERIC silently narrows a lossless float to
--                        INTEGER on write, so a `position` midpoint that lands
--                        on 2.0 is stored as 2. That reads back identically in
--                        JS, so nothing breaks; it is recorded because two
--                        artifacts in this directory disagree and the next
--                        person should not have to rediscover which. Pick one.
--   bool      -> INTEGER NOT NULL DEFAULT 0        0/1. SQLite has no boolean.
--   date      -> TEXT    NOT NULL DEFAULT ''       LOSSY-BY-FORMAT: PocketBase
--                        serialises to "2026-08-31 09:00:00.000Z" — a SPACE,
--                        not a 'T', and always UTC with 3-digit millis. That is
--                        NOT ISO-8601 and `new Date(x)` parses it inconsistently
--                        across engines. See the DATE FORMAT note below.
--   autodate  -> TEXT    same wire format as `date`; PB fills it on
--                        create/update. In D1 the Worker must fill it — there
--                        is no autodate; see the DEFAULT note per column.
--   json      -> TEXT    — NOT USED as a PB field type anywhere in this tree.
--                        Every JSON payload here (params, trace, facts,
--                        entities, members, assignees, watchers, subtasks,
--                        attachments, receipt, approval, ...) is a PB `text`
--                        field holding a JSON string. Kept as TEXT so the
--                        import is lossless; use json_extract() where useful.
--   relation  -> TEXT    holding the related record id (maxSelect:1 in every
--                        case here). LOSSY: PocketBase's `cascadeDelete: true`
--                        is Go code in the record deleter, NOT an SQL foreign
--                        key — PB creates no FKs. See the CASCADE DELETE
--                        section at the end of this file for the exact
--                        statements the Worker must now run itself.
--   file      -> TEXT    holding the stored FILENAME (evidence.image). The
--                        BYTES lived under `--dir /pb_data` (backend/start.sh:33)
--                        and must move to R2; the column is only a key.
--   select    -> TEXT    — NOT USED. Fields that read like enums
--                        (jobs.status, events.kind, internal_todos.stage,
--                        internal_people.remind_pref, ...) are plain `text`
--                        with the allowed values only in a comment. There is
--                        no database-level constraint on any of them today and
--                        none is added here; adding one would reject rows the
--                        live system writes.
--
-- ---------------------------------------------------------------------
-- DATE FORMAT — READ THIS BEFORE WRITING THE IMPORTER
-- ---------------------------------------------------------------------
-- PocketBase stores `date` and `autodate` as "YYYY-MM-DD HH:MM:SS.sssZ".
-- Several *text* columns in this schema hold real ISO-8601 instead, because
-- the client wrote them: events.spoken_at / capture_started_at /
-- capture_ended_at, segments.started_at / last_speech_at / ended_at,
-- password_resets.expires, purges.requested_at / purged_at, and every
-- internal_* timestamp-ish text column (remind_at, fire_at, sent_at,
-- expires, last_in, code_set_at, done_at, edited_at, emailed_at, smsed_at).
-- The two formats sort differently and are NOT interchangeable. Keep each
-- column's existing format on import. Do not normalise.
--
-- ---------------------------------------------------------------------
-- INDEXES
-- ---------------------------------------------------------------------
-- 32 index definitions are reconstructed below from the migrations (16 on the
-- product collections, 16 on internal HQ), of which 11 are UNIQUE and 5 of
-- those are PARTIAL-UNIQUE (`WHERE col != ''`). One more UNIQUE index
-- (owners.tokenKey) is PocketBase-implicit for auth collections and is made
-- explicit. A further 13 indexes are ADDED by this file and are each marked
-- `-- ADDED`: they cover reads that PocketBase ran as table scans and that a
-- Worker on D1 must not. Nothing marked ADDED is required for correctness;
-- every one can be dropped without changing a result.
--
-- The partial predicate is load-bearing, not decoration: because PocketBase
-- writes '' rather than NULL (note 1 above), a plain UNIQUE index would let
-- exactly ONE row hold the empty value and reject every other unset row.
-- Every partial-unique index here exists precisely so that "unset" can repeat.
--
-- CORRECTION TO THE BRIEF: there is no phone-uniqueness index on
-- `owner_profile`. Phone uniqueness lived on `owners.phone` as
-- `CREATE UNIQUE INDEX idx_owners_phone ... WHERE phone != ''`
-- (1700000008_owners.js:37) and was DELIBERATELY DEMOTED to a non-unique index
-- by 1700000016_share_phone_across_accounts.js:16 — "the number is a routing
-- address, not an identity", after it refused every second account a person
-- tried to make. Carrying it across as unique would reintroduce that bug.
-- owner_profile's partial-unique index is on `owner_ref`
-- (1700000054_owner_profile_canonical.js:44-45), one profile row per account.
--
-- Not reproduced here: PocketBase's internal `_collections`, `_params`,
-- `_migrations`, `_mfas`, `_otps`, `_authOrigins`, `_externalAuths` and
-- `_superusers` tables. `_superusers` in particular is the PocketBase admin
-- account store and has no D1 equivalent — HQ identity is internal_sessions
-- + internal_people.code_hash, and the product identity is `owners`.
-- =====================================================================

PRAGMA foreign_keys = OFF;   -- no FKs are declared; see CASCADE DELETE below

-- =====================================================================
-- SECTION 1 — PRODUCT COLLECTIONS (12)
--
-- pendants, events, jobs, agents, owner_profile, segments, owners,
-- password_resets, agent_llm_audit, agent_audit_sessions, purges, evidence
--
-- Reached today through PocketBase's generic REST API
-- /api/collections/<name>/records by iOS, macOS, the Chrome extension,
-- brain/pb.py and ~30 proof harnesses. Their API rules are almost all "",
-- which in PocketBase means PUBLIC — the real gate is guard.pb.js:24-38,
-- a routerUse that demands the X-Anticipy-Token header on every
-- /api/collections/* request. See RULES.md before exposing any of these.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1.1  pendants   (base)   1700000000_anticipy.js:7-25
--      One row per physical device: a short pair_code + an owner link.
--
--      NOTE — NO TIMESTAMPS. `pendants` was created without autodate fields
--      and never gained them. There is no `created`/`updated` to copy. The
--      columns are declared here (default '') so every table has the same
--      shape, but they will be EMPTY for every imported pendant row. Compare:
--      1700000003_events_timestamps.js exists solely because `events` had the
--      same omission and it broke chronological sort in the app.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "pendants" (
  "id"         TEXT PRIMARY KEY NOT NULL,                 -- PB id: 15 chars, [a-z0-9]
  "created"    TEXT    NOT NULL DEFAULT '',               -- ABSENT in PocketBase; always ''
  "updated"    TEXT    NOT NULL DEFAULT '',               -- ABSENT in PocketBase; always ''
  "device_id"  TEXT    NOT NULL DEFAULT '' CHECK (length("device_id") > 0),  -- :11 required, presentable
  "name"       TEXT    NOT NULL DEFAULT '',               -- :12
  "pair_code"  TEXT    NOT NULL DEFAULT '' CHECK (length("pair_code") > 0),  -- :13 required; 6 digits, guessable — see guard.pb.js:117-165
  "owner"      TEXT    NOT NULL DEFAULT '',               -- :14 pre-accounts UUID the phone invented for itself
  "paired"     INTEGER NOT NULL DEFAULT 0,                -- :15 bool
  "battery"    REAL    NOT NULL DEFAULT 0,                -- :16 number
  "owner_ref"  TEXT    NOT NULL DEFAULT ''                -- 1700000027_pendants_owner_ref.js:9-11 relation->owners, cascadeDelete
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_device" ON "pendants" ("device_id");
-- 1700000000_anticipy.js:18. NOT partial: device_id is required, so '' cannot
-- legitimately repeat.
CREATE INDEX IF NOT EXISTS "idx_pendants_owner_ref" ON "pendants" ("owner_ref");
-- ADDED, not from a migration. PocketBase had no index here and the cascade
-- delete was a Go table-scan; the Worker now runs that delete as SQL (see the
-- CASCADE DELETE section) and must not scan.

-- ---------------------------------------------------------------------
-- 1.2  events   (base)   1700000000_anticipy.js:27-44
--      Transcript lines + brain decisions, streamed app <-> extension.
--      The single largest table in the product.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "events" (
  "id"                  TEXT PRIMARY KEY NOT NULL,
  "created"             TEXT    NOT NULL DEFAULT '',      -- 1700000003_events_timestamps.js:7  autodate onCreate
  "updated"             TEXT    NOT NULL DEFAULT '',      -- 1700000003_events_timestamps.js:8  autodate onCreate+onUpdate
  "device_id"           TEXT    NOT NULL DEFAULT '' CHECK (length("device_id") > 0),  -- :31 required
  "kind"                TEXT    NOT NULL DEFAULT '' CHECK (length("kind") > 0),       -- :32 required; transcript|decision|action|confirm
  "text"                TEXT    NOT NULL DEFAULT '',      -- :33  ("text" is not reserved in SQLite but is quoted throughout)
  "decision"            TEXT    NOT NULL DEFAULT '',      -- :34  ignore|act|ask
  "goal"                TEXT    NOT NULL DEFAULT '',      -- :35
  "needs_confirmation"  INTEGER NOT NULL DEFAULT 0,       -- :36 bool
  "capture_started_at"  TEXT    NOT NULL DEFAULT '',      -- 1700000004_segments.js:46  ISO8601 capture clock, NOT arrival time
  "capture_ended_at"    TEXT    NOT NULL DEFAULT '',      -- 1700000004_segments.js:47
  "gap_before_ms"       REAL    NOT NULL DEFAULT 0,       -- 1700000004_segments.js:48 number
  "seq"                 REAL    NOT NULL DEFAULT 0,       -- 1700000004_segments.js:49 number
  "boot_id"             TEXT    NOT NULL DEFAULT '',      -- 1700000004_segments.js:50
  "source"              TEXT    NOT NULL DEFAULT '',      -- 1700000004_segments.js:51  phone|pendant
  "backfill"            INTEGER NOT NULL DEFAULT 0,       -- 1700000004_segments.js:52 bool
  "segment"             TEXT    NOT NULL DEFAULT '',      -- 1700000004_segments.js:53  owning segments.id (text, not a relation)
  "speaker"             TEXT    NOT NULL DEFAULT '',      -- 1700000007_event_speaker.js:15  owner|other|'' — local voice verdict
  "owner_ref"           TEXT    NOT NULL DEFAULT '',      -- 1700000009_owner_ref.js:25-32 relation->owners, cascadeDelete
  "addressee"           TEXT    NOT NULL DEFAULT '',      -- 1700000019_events_addressee.js:11  assistant|person|dictation|self|''
  "spoken_at"           TEXT    NOT NULL DEFAULT '',      -- 1700000020_events_capture_and_link.js:35  ISO8601 UTC
  "parent_line"         TEXT    NOT NULL DEFAULT '',      -- 1700000020_events_capture_and_link.js:38  self-id = "new thread"
  "external_event_id"   TEXT    NOT NULL DEFAULT '',      -- 1700000028_event_sources.js:9-11  Twilio idempotency key
  "explicit"            INTEGER NOT NULL DEFAULT 0,       -- 1700000029_event_intent.js:9 bool — typed vs ambient
  "importance"          REAL    NOT NULL DEFAULT 0,       -- 1700000040_event_importance.js:23-28 number, PB min 1 max 5; 0 = unset, worker reads missing as 4,
  "heard_ms"            REAL    NOT NULL DEFAULT 0,       -- 1700000056_events_heard.js  Omi port 06: wall-clock the decision spent
  "heard_calls"         REAL    NOT NULL DEFAULT 0        -- 1700000056_events_heard.js  Omi port 06: model calls the decision spent
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_events_external_event"
  ON "events" ("external_event_id") WHERE "external_event_id" != '';
-- PARTIAL-UNIQUE 1/5. 1700000028_event_sources.js:16. Without the predicate,
-- the second event with no provider id (i.e. every microphone line) collides.
CREATE INDEX IF NOT EXISTS "idx_events_owner_ref_created" ON "events" ("owner_ref", "created");
-- ADDED. Not in any migration — PocketBase had NO index on events at all
-- beyond the external-id one, and the phone's feed is
-- `owner_ref="X"` sorted `-created` on the largest table in the product.
-- guard.pb.js:45-50 requires that exact filter shape, so this index matches
-- the only query the door allows.
CREATE INDEX IF NOT EXISTS "idx_events_segment" ON "events" ("segment");
-- ADDED. Segment fan-out (1700000004_segments.js:53) was an unindexed scan.

-- ---------------------------------------------------------------------
-- 1.3  jobs   (base)   1700000001_jobs.js:5-23
--      The action queue: brain -> extension, and the durable workflow
--      envelope enforced by pb_hooks/workflow_guard.pb.js.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "jobs" (
  "id"                 TEXT PRIMARY KEY NOT NULL,
  "created"            TEXT    NOT NULL DEFAULT '',       -- :14 autodate onCreate
  "updated"            TEXT    NOT NULL DEFAULT '',       -- :15 autodate onCreate+onUpdate
  "goal"               TEXT    NOT NULL DEFAULT '' CHECK (length("goal") > 0),    -- :9 required
  "params"             TEXT    NOT NULL DEFAULT '',       -- :10 JSON string; PB max raised 5000 -> 100000 in 1700000033_job_params_large.js:10
  "status"             TEXT    NOT NULL DEFAULT '' CHECK (length("status") > 0),  -- :11 required; queued|running|awaiting_confirm|done|failed
  "result"             TEXT    NOT NULL DEFAULT '',       -- :12
  "device_id"          TEXT    NOT NULL DEFAULT '',       -- :13
  "owner"              TEXT    NOT NULL DEFAULT '',       -- 1700000002_agents.js:33  pre-accounts UUID
  "claimed_by"         TEXT    NOT NULL DEFAULT '',       -- 1700000002_agents.js:34
  "claimed_at"         TEXT    NOT NULL DEFAULT '',       -- 1700000002_agents.js:35 date
  "owner_ref"          TEXT    NOT NULL DEFAULT '',       -- 1700000009_owner_ref.js:25-32 relation->owners, cascadeDelete
  "lane"               TEXT    NOT NULL DEFAULT '',       -- 1700000019_job_lane.js:10  '' = browser lane, 'research' = worker; see research_lane.pb.js:441-442
  "attempts"           REAL    NOT NULL DEFAULT 0,        -- 1700000021_jobs_attempts.js:26 number — bounds the retry loop
  "trace"              TEXT    NOT NULL DEFAULT '',       -- 1700000024_jobs_trace.js:9; PB max raised to 100000 in 1700000034_jobs_trace_large.js:10
  "workflow_id"        TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:13
  "workflow_version"   REAL    NOT NULL DEFAULT 0,        -- 1700000025_job_workflows.js:14 number
  "workflow_state"     TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:15
  "consequence"        TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:16
  "lineage_key"        TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:17
  "effect_key"         TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:18
  "scope_digest"       TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:19
  "approval"           TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:20 JSON string
  "receipt"            TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:21 JSON string; workflow_guard.pb.js:202-211 refuses `done` without verified+evidence
  "reconciliation"     TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:22
  "lease_token"        TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:23
  "lease_until"        TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:24 date — the EXECUTOR's lease
  "source_event_ids"   TEXT    NOT NULL DEFAULT '',       -- 1700000025_job_workflows.js:25 JSON string
  "effect_uncertain"   INTEGER NOT NULL DEFAULT 0,        -- 1700000025_job_workflows.js:26 bool
  "watching_until"     TEXT    NOT NULL DEFAULT '',       -- 1700000041_watch_lease.js:37-39 date — the OWNER's presence lease (30s half-life). Deliberately NOT lease_until; see :25-29.
  "commitment_key"     TEXT    NOT NULL DEFAULT ''        -- 1700000055_active_commitment_identity.js:16-18 text max 64, sha256(tenant+node)
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_jobs_workflow"
  ON "jobs" ("workflow_id") WHERE "workflow_id" != '';
-- PARTIAL-UNIQUE 2/5. 1700000025_job_workflows.js:35.
CREATE UNIQUE INDEX IF NOT EXISTS "idx_jobs_active_commitment"
  ON "jobs" ("commitment_key") WHERE "commitment_key" != '';
-- PARTIAL-UNIQUE 3/5. 1700000055_active_commitment_identity.js:23-24.
-- This is the ONLY thing that stops two processes both reading "no active
-- promise" and both creating one. job_commitment_identity.pb.js clears the key
-- when a row goes terminal, because PocketBase's index validator accepts a
-- nonempty partial predicate but not `status IN (...)` (:9-12).
CREATE INDEX IF NOT EXISTS "idx_jobs_owner_ref_status" ON "jobs" ("owner_ref", "status", "created");
-- ADDED. The extension polls `owner_ref="X" && status="queued"` on every
-- sweep (guard.pb.js:240 allows exactly this list shape); PocketBase ran it
-- as a scan.
CREATE INDEX IF NOT EXISTS "idx_jobs_lane_status" ON "jobs" ("lane", "status");
-- ADDED. research_lane.pb.js:441-442 rewrites every extension list filter to
-- append `&& lane != "research" && lane != "<supervised>" && lane != "<device>"`.

-- ---------------------------------------------------------------------
-- 1.4  agents   (base)   1700000002_agents.js:10-30
--      One row per browser-extension install. `last_seen` is the heartbeat
--      the phone derives "last seen 4s ago" from.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "agents" (
  "id"           TEXT PRIMARY KEY NOT NULL,
  "created"      TEXT    NOT NULL DEFAULT '',             -- :20 autodate onCreate
  "updated"      TEXT    NOT NULL DEFAULT '',             -- :21 autodate onCreate+onUpdate
  "agent_id"     TEXT    NOT NULL DEFAULT '' CHECK (length("agent_id") > 0),   -- :14 required, presentable
  "pair_code"    TEXT    NOT NULL DEFAULT '' CHECK (length("pair_code") > 0),  -- :15 required; 6 digits, permanent once minted (agent_auth.pb.js:19-25)
  "owner"        TEXT    NOT NULL DEFAULT '',             -- :16 written ONCE at pairing; rotates on Settings reset / reinstall
  "paired"       INTEGER NOT NULL DEFAULT 0,              -- :17 bool
  "last_seen"    TEXT    NOT NULL DEFAULT '',             -- :18 date
  "browser"      TEXT    NOT NULL DEFAULT '',             -- :19
  "owner_ref"    TEXT    NOT NULL DEFAULT '',             -- 1700000022_agents_owner_ref.js:33-40 relation->owners, cascadeDelete
  "agent_token"  TEXT    NOT NULL DEFAULT '',             -- 1700000026_agent_tokens.js:11-12  256 bits of client-generated material.
                                                          -- PB field is hidden:true (min 40, max 200) — NEVER returned by the API.
                                                          -- The Worker MUST reproduce that: it is a bearer credential, and D1 has
                                                          -- no equivalent of `hidden`. Never SELECT * this table into a response.
  "llm_calls"    REAL    NOT NULL DEFAULT 0,              -- 1700000035_agent_llm_meter.js:17 NumberField min 0 — spend meter, on the row on purpose (:11-13)
  "llm_hour"     TEXT    NOT NULL DEFAULT '',             -- 1700000035_agent_llm_meter.js:20 TextField max 20 — "YYYY-MM-DDTHH"
  "solve_calls"  REAL    NOT NULL DEFAULT 0,              -- 1700000036_agent_solve_meter.js:10 NumberField min 0
  "solve_hour"   TEXT    NOT NULL DEFAULT ''              -- 1700000036_agent_solve_meter.js:13 TextField max 20
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_agent" ON "agents" ("agent_id");
-- 1700000002_agents.js:23.
CREATE INDEX IF NOT EXISTS "idx_agents_pair_code" ON "agents" ("pair_code");
-- ADDED. The tokenless pairing bootstrap looks a row up BY pair_code
-- (guard.pb.js:117-165). That lookup is rate-limited but not indexed today.
CREATE INDEX IF NOT EXISTS "idx_agents_owner_ref" ON "agents" ("owner_ref");
-- ADDED. Cascade-delete target; see the CASCADE DELETE section.

-- ---------------------------------------------------------------------
-- 1.5  owner_profile   (base)   1700000003_owner_profile.js:8-24
--      The owner's own details, so nobody hand-edits a server env var to
--      make texting work. Payment details are deliberately absent and
--      always will be (1700000005_owner_identity.js:10-11).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "owner_profile" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT    NOT NULL DEFAULT '',              -- :15 autodate onCreate
  "updated"     TEXT    NOT NULL DEFAULT '',              -- :16 autodate onCreate+onUpdate
  "owner_id"    TEXT    NOT NULL DEFAULT '' CHECK (length("owner_id") > 0),  -- :12 required; the pre-accounts UUID
  "phone"       TEXT    NOT NULL DEFAULT '',              -- :13 E.164
  "name"        TEXT    NOT NULL DEFAULT '',              -- :14
  "first_name"  TEXT    NOT NULL DEFAULT '',              -- 1700000005_owner_identity.js:15
  "last_name"   TEXT    NOT NULL DEFAULT '',              -- 1700000005_owner_identity.js:16
  "email"       TEXT    NOT NULL DEFAULT '',              -- 1700000005_owner_identity.js:17
  "birthday"    TEXT    NOT NULL DEFAULT '',              -- 1700000006_owner_birthday.js:11  YYYY-MM-DD
  "facts"       TEXT    NOT NULL DEFAULT '',              -- 1700000007_owner_facts.js:15  JSON object — free-form key/value, so no column-per-form-field treadmill
  "owner_ref"   TEXT    NOT NULL DEFAULT '',              -- 1700000009_owner_ref.js:25-32 relation->owners, cascadeDelete
  "timezone"    TEXT    NOT NULL DEFAULT ''               -- 1700000023_owner_timezone.js:34-38  IANA id; the clock AND the city
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_owner_profile_owner_ref"
  ON "owner_profile" ("owner_ref") WHERE "owner_ref" != '';
-- PARTIAL-UNIQUE 4/5. 1700000054_owner_profile_canonical.js:44-45. ONE PROFILE
-- ROW PER ACCOUNT, enforced by SQLite rather than by hope: two concurrent
-- first-saves used to make two rows and every reader took `-updated`, which
-- made whichever request finished last the whole truth (:5-9).
-- The predicate is why the three documented owner_ref='' orphan rows
-- (1700000043_owner_profile_needs_owner.js:6-8) can still coexist. A plain
-- UNIQUE index would reject the import of the second one.
CREATE INDEX IF NOT EXISTS "idx_owner_profile_phone" ON "owner_profile" ("phone");
-- ADDED. sms.pb.js:166 routes an inbound text by number through this column.
-- NOT unique — see the CORRECTION note in the header.

-- ---------------------------------------------------------------------
-- 1.6  segments   (base)   1700000004_segments.js:13-39
--      A conversation as a ROW that stays open with a rolling
--      last_speech_at, so a dropped Bluetooth link cannot end one.
--      All timestamp columns here are TEXT ISO8601, not PB `date`.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "segments" (
  "id"                    TEXT PRIMARY KEY NOT NULL,
  "created"               TEXT    NOT NULL DEFAULT '',    -- :30 autodate onCreate
  "updated"               TEXT    NOT NULL DEFAULT '',    -- :31 autodate onCreate+onUpdate
  "owner"                 TEXT    NOT NULL DEFAULT '',    -- :17
  "status"                TEXT    NOT NULL DEFAULT '' CHECK (length("status") > 0),  -- :18 required; open|closed
  "started_at"            TEXT    NOT NULL DEFAULT '',    -- :19 ISO8601 CAPTURE time (text, not date)
  "last_speech_at"        TEXT    NOT NULL DEFAULT '',    -- :20
  "ended_at"              TEXT    NOT NULL DEFAULT '',    -- :21
  "turn_count"            REAL    NOT NULL DEFAULT 0,     -- :22 number
  "word_count"            REAL    NOT NULL DEFAULT 0,     -- :23 number
  "summary"               TEXT    NOT NULL DEFAULT '',    -- :24
  "entities"              TEXT    NOT NULL DEFAULT '',    -- :25 JSON array string
  "parent_segment"        TEXT    NOT NULL DEFAULT '',    -- :26
  "triaged_through_seq"   REAL    NOT NULL DEFAULT 0,     -- :27 number
  "dirty"                 INTEGER NOT NULL DEFAULT 0,     -- :28 bool
  "supersedes"            TEXT    NOT NULL DEFAULT '',    -- :29
  "owner_ref"             TEXT    NOT NULL DEFAULT ''     -- 1700000009_owner_ref.js:25-32 relation->owners, cascadeDelete
);
CREATE INDEX IF NOT EXISTS "idx_segments_owner_ref_status" ON "segments" ("owner_ref", "status");
-- ADDED. PocketBase declared NO index on segments. "find my open segment" is
-- the hottest read in the capture path (CAPTURE-ARCHITECTURE.md).

-- ---------------------------------------------------------------------
-- 1.7  owners   (AUTH)   1700000008_owners.js:18-56
--      A person. The only auth-type collection in the tree.
--
--      PocketBase auto-injects the auth system fields; they are made
--      explicit below (:22-23 says so in the migration itself). On
--      Cloudflare there is no PocketBase auth machinery, so the Worker
--      owns password verification, token minting and the tokenKey
--      invalidation semantics. See RULES.md.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "owners" (
  "id"               TEXT PRIMARY KEY NOT NULL,
  "created"          TEXT    NOT NULL DEFAULT '',         -- :33 autodate onCreate
  "updated"          TEXT    NOT NULL DEFAULT '',         -- :34 autodate onCreate+onUpdate

  -- --- auth system fields (PocketBase-implicit, made explicit here) ---
  "email"            TEXT    NOT NULL DEFAULT '' CHECK (length("email") > 0),
                                                          -- :24 declared required; re-asserted 1700000013_owners_allow_signup.js:26-27.
                                                          -- PB type `email` = TEXT + an email-shape validator.
  "emailVisibility"  INTEGER NOT NULL DEFAULT 0,          -- auth-implicit, bool. camelCase on purpose: this is the exact
                                                          -- PocketBase column name and every client reads it by that name.
  "verified"         INTEGER NOT NULL DEFAULT 0,          -- auth-implicit, bool
  "password"         TEXT    NOT NULL DEFAULT '',         -- auth-implicit. BCRYPT HASH ONLY. PB never stores plaintext.
                                                          -- LOSSY-BY-PLATFORM: Workers have no native bcrypt. See
                                                          -- RULES.md "owners" row — the hashes import fine, the
                                                          -- VERIFIER is the thing that must be rebuilt.
                                                          -- NOT EXPORTABLE OVER REST. This column, `tokenKey` below and
                                                          -- `agents.agent_token` are PocketBase-hidden and never appear in
                                                          -- /api/collections/*/records output — corroborated independently
                                                          -- at migration/runbooks/import_d1.py:214-216. They exist only
                                                          -- inside /pb_data/data.db, so the cutover needs a NATIVE
                                                          -- PocketBase archive as well as a REST export. An export without
                                                          -- one locks every existing customer out of their account and
                                                          -- unpairs every browser, and it will look like a clean run.
  "tokenKey"         TEXT    NOT NULL DEFAULT '',         -- auth-implicit. Random per-record salt mixed into every issued
                                                          -- JWT. Rotating it invalidates that person's live sessions —
                                                          -- which is what "log out everywhere" and a password change do.
                                                          -- Carry it across or every existing phone/Mac session dies.

  -- --- fields declared by the migration ---
  "phone"            TEXT    NOT NULL DEFAULT '',         -- :28 E.164. A ROUTING ADDRESS, NEVER A CREDENTIAL — US carriers
                                                          -- reassign disconnected numbers after ~45 days (:25-27).
  "legacy_uuid"      TEXT    NOT NULL DEFAULT ''          -- :32 the UUID the phone generated before accounts existed;
                                                          -- what makes /auth/claim able to adopt rather than orphan
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_owners_email" ON "owners" ("email");
-- 1700000008_owners.js:39, re-declared 1700000013_owners_allow_signup.js:30.
-- NOT partial, and correctly so: email is required, so '' cannot repeat.
CREATE UNIQUE INDEX IF NOT EXISTS "idx_owners_legacy"
  ON "owners" ("legacy_uuid") WHERE "legacy_uuid" != '';
-- PARTIAL-UNIQUE 5/5. 1700000008_owners.js:38.
CREATE INDEX IF NOT EXISTS "idx_owners_phone" ON "owners" ("phone");
-- 1700000016_share_phone_across_accounts.js:16. NON-UNIQUE, DELIBERATELY.
-- It was `UNIQUE ... WHERE phone != ''` at 1700000008_owners.js:37 and was
-- demoted because it refused every second account a person tried to make,
-- with the app blaming the email for it. DO NOT RESTORE THE UNIQUE FORM.
CREATE UNIQUE INDEX IF NOT EXISTS "idx_owners_tokenKey" ON "owners" ("tokenKey");
-- PocketBase-implicit for auth collections. Reproduced explicitly. The real
-- production index name embeds the collection id (see Unverified in RULES.md).

-- ---------------------------------------------------------------------
-- 1.8  password_resets   (base)   1700000012_password_resets.js:15-40
--      The code itself is NEVER stored — only SHA-256 of it (:5-8).
--      EVERY API RULE IS null. There is no client-facing path to this
--      table at all; the reset hook reaches it through the DAO.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "password_resets" (
  "id"         TEXT PRIMARY KEY NOT NULL,
  "created"    TEXT    NOT NULL DEFAULT '',               -- :28 autodate onCreate
  "updated"    TEXT    NOT NULL DEFAULT '',               -- :29 autodate onCreate+onUpdate
  "owner"      TEXT    NOT NULL DEFAULT '' CHECK (length("owner") > 0),      -- :19-20 required relation->owners, cascadeDelete
  "code_hash"  TEXT    NOT NULL DEFAULT '' CHECK (length("code_hash") > 0),  -- :21 required; SHA-256, never the code
  "expires"    TEXT    NOT NULL DEFAULT '' CHECK (length("expires") > 0),    -- :23 required; ISO8601 UTC *text*, not a PB date
  "attempts"   REAL    NOT NULL DEFAULT 0,                -- :26 number — 1-in-a-million is only true if the tries are counted
  "used"       INTEGER NOT NULL DEFAULT 0                 -- :27 bool
);
CREATE INDEX IF NOT EXISTS "idx_resets_owner" ON "password_resets" ("owner");
-- 1700000012_password_resets.js:32.

-- ---------------------------------------------------------------------
-- 1.9  agent_llm_audit   (base)   1700000030_agent_llm_audit.js:7-42
--      Append-only evidence for EXPLICITLY TAGGED certification runs only.
--      Normal customer model calls are not retained (:4-5).
--
--      THIS TABLE FILLED THE 5GB VOLUME AND TOOK PRODUCTION DOWN
--      (1700000037_backup_footprint.js:13-14, audit_retention.pb.js).
--      D1 has its own size ceiling — keep audit_retention's sweep.
--
--      NOTE: owner_ref here is a plain required TEXT field (:13), NOT a
--      relation like everywhere else. So it is NOT cascade-deleted by
--      account deletion; account_delete.pb.js:69 lists it explicitly.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "agent_llm_audit" (
  "id"                      TEXT PRIMARY KEY NOT NULL,
  "created"                 TEXT    NOT NULL DEFAULT '',  -- :27 autodate onCreate
  "updated"                 TEXT    NOT NULL DEFAULT '',  -- :28 autodate onCreate+onUpdate
  "task_tag"                TEXT    NOT NULL DEFAULT '' CHECK (length("task_tag") > 0),   -- :11 required, presentable; [AUDIT:<run>:<task>]
  "agent_id"                TEXT    NOT NULL DEFAULT '' CHECK (length("agent_id") > 0),   -- :12 required
  "owner_ref"               TEXT    NOT NULL DEFAULT '' CHECK (length("owner_ref") > 0),  -- :13 required TEXT (not a relation)
  "model"                   TEXT    NOT NULL DEFAULT '' CHECK (length("model") > 0),      -- :14 required
  "provider"                TEXT    NOT NULL DEFAULT '',  -- :15
  "status"                  TEXT    NOT NULL DEFAULT '' CHECK (length("status") > 0),     -- :16 required
  "http_status"             REAL    NOT NULL DEFAULT 0,   -- :17 number
  "duration_ms"             REAL    NOT NULL DEFAULT 0,   -- :18 number
  "request_sha256"          TEXT    NOT NULL DEFAULT '',  -- :19
  "response_sha256"         TEXT    NOT NULL DEFAULT '',  -- :20
  "client_request_json"     TEXT    NOT NULL DEFAULT '' CHECK (length("client_request_json") > 0),
                                                          -- :21 required; PB max 1000000 (1700000032:11) to match the proxy's 900KB ceiling
  "provider_request_json"   TEXT    NOT NULL DEFAULT '',  -- :22 PB max 1000000
  "provider_response_json"  TEXT    NOT NULL DEFAULT '',  -- :23 PB max 1000000
  "client_response_json"    TEXT    NOT NULL DEFAULT '',  -- :24 PB max 1000000
  "error"                   TEXT    NOT NULL DEFAULT '',  -- :25 PB max 10000 (1700000032:14)
  "proxy_version"           TEXT    NOT NULL DEFAULT '' CHECK (length("proxy_version") > 0),  -- :26 required
  "provider_model"          TEXT    NOT NULL DEFAULT ''   -- 1700000031_agent_audit_sessions.js:9
);
CREATE INDEX IF NOT EXISTS "idx_agent_llm_audit_task_created"  ON "agent_llm_audit" ("task_tag", "created");
CREATE INDEX IF NOT EXISTS "idx_agent_llm_audit_agent_created" ON "agent_llm_audit" ("agent_id", "created");
-- 1700000030_agent_llm_audit.js:31-32.
CREATE INDEX IF NOT EXISTS "idx_agent_llm_audit_created" ON "agent_llm_audit" ("created");
-- ADDED. audit_retention.pb.js sweeps by age alone; without this the sweep
-- that exists to stop this table filling the disk is itself a full scan.

-- ---------------------------------------------------------------------
-- 1.10  agent_audit_sessions   (base)   1700000031_agent_audit_sessions.js:12-33
--       A short-lived correlation window so planner/verifier/recovery calls
--       are retained even when their prompt does not repeat the tagged goal.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "agent_audit_sessions" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT    NOT NULL DEFAULT '',              -- :21 autodate onCreate
  "updated"     TEXT    NOT NULL DEFAULT '',              -- :22 autodate onCreate+onUpdate
  "task_tag"    TEXT    NOT NULL DEFAULT '' CHECK (length("task_tag") > 0),   -- :16 required, presentable
  "agent_id"    TEXT    NOT NULL DEFAULT '' CHECK (length("agent_id") > 0),   -- :17 required
  "owner_ref"   TEXT    NOT NULL DEFAULT '' CHECK (length("owner_ref") > 0),  -- :18 required TEXT (not a relation)
  "active"      INTEGER NOT NULL DEFAULT 0,               -- :19 bool, declared required:true — NO CHECK IS EMITTED HERE ON PURPOSE.
                                                          -- PocketBase's `required` validator on a bool means "must be truthy",
                                                          -- so `active = false` is arguably unwritable through the record API
                                                          -- while the collection's updateRule is "". agent_key.pb.js:255-258
                                                          -- reads `active = true` and the migration header (:4-5) says the proxy
                                                          -- "ignores expired/inactive sessions" — a state the schema may never
                                                          -- have allowed to be reached. Flagged in Unverified; do NOT encode
                                                          -- CHECK("active" = 1), it would make deactivation impossible in D1 too.
  "expires_at"  TEXT    NOT NULL DEFAULT '' CHECK (length("expires_at") > 0)  -- :20 required date
);
CREATE INDEX IF NOT EXISTS "idx_agent_audit_session_active"
  ON "agent_audit_sessions" ("agent_id", "active", "created");
-- 1700000031_agent_audit_sessions.js:25.

-- ---------------------------------------------------------------------
-- 1.11  purges   (base)   1700000039_purges.js:22-49
--       "This person asked to be forgotten", surviving being forgotten.
--       Deliberately NOT owner-scoped by relation: the owner is gone by
--       the time the worker reads it, and a dangling relation would either
--       block the delete or be nulled out and lose the only thing the row
--       is for (:14-16).
--
--       NO TIMESTAMPS. Like `pendants`, this collection declares no
--       autodate fields; requested_at / purged_at are plain ISO text the
--       writer fills in.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "purges" (
  "id"             TEXT PRIMARY KEY NOT NULL,
  "created"        TEXT    NOT NULL DEFAULT '',           -- ABSENT in PocketBase; always ''
  "updated"        TEXT    NOT NULL DEFAULT '',           -- ABSENT in PocketBase; always ''
  "owner_ref"      TEXT    NOT NULL DEFAULT '' CHECK (length("owner_ref") > 0),  -- :34 required TEXT (not a relation, on purpose)
  "legacy_uuid"    TEXT    NOT NULL DEFAULT '',           -- :37 pre-accounts uuid, for state dirs under the older naming
  "memory_purged"  INTEGER NOT NULL DEFAULT 0,            -- :41 bool — set by the worker once the per-owner memory.db is really gone
  "requested_at"   TEXT    NOT NULL DEFAULT '',           -- :42 ISO text
  "purged_at"      TEXT    NOT NULL DEFAULT ''            -- :43 ISO text
);
CREATE INDEX IF NOT EXISTS "idx_purges_pending" ON "purges" ("memory_purged");
-- 1700000039_purges.js:46.

-- ---------------------------------------------------------------------
-- 1.12  evidence   (base)   1700000045_evidence.js:50-95
--       Somewhere for a picture to live. The ONLY `type: "file"` field in
--       all 58 migrations (:16-18).
--
--       On PocketBase the bytes landed under `--dir /pb_data` (the Railway
--       volume). On Cloudflare they belong in R2 and this column becomes
--       the object key. `share_expires` is what makes a public URL live or
--       dead — a caller who can PATCH it mints itself a permanent public
--       link to somebody's booking confirmation (:42-45), which is why
--       update and delete are superuser-only. Preserve that in the Worker.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "evidence" (
  "id"             TEXT PRIMARY KEY NOT NULL,
  "created"        TEXT    NOT NULL DEFAULT '',           -- :82 autodate onCreate
  "updated"        TEXT    NOT NULL DEFAULT '',           -- :83 autodate onCreate+onUpdate
  "owner_ref"      TEXT    NOT NULL DEFAULT '' CHECK (length("owner_ref") > 0),  -- :58 required TEXT — "an unowned one is a picture nobody can see and nobody can erase"
  "job"            TEXT    NOT NULL DEFAULT '' CHECK (length("job") > 0),        -- :60 required TEXT (jobs.id; not a PB relation)
  "effect_key"     TEXT    NOT NULL DEFAULT '',           -- :65 keeps the picture on the same leash as the receipt
  "image"          TEXT    NOT NULL DEFAULT '',           -- :67-75 PB file field: maxSelect 1, maxSize 400000 (the extension's own
                                                          -- screenshot ceiling, agent_loop.js:129), mimeTypes image/jpeg + image/png.
                                                          -- Column holds the FILENAME only. Enforce size and MIME in the Worker —
                                                          -- "an evidence host that accepts arbitrary files is a file host" (:73).
  "share_expires"  TEXT    NOT NULL DEFAULT '',           -- :78 date. '' MEANS NO PUBLIC URL EXISTS.
  "fetches"        REAL    NOT NULL DEFAULT 0             -- :81 number — expiry alone leaves a leaked URL an unlimited download
);
CREATE INDEX IF NOT EXISTS "idx_evidence_owner" ON "evidence" ("owner_ref");
CREATE INDEX IF NOT EXISTS "idx_evidence_job"   ON "evidence" ("job");
-- 1700000045_evidence.js:92-93.

-- =====================================================================
-- SECTION 2 — INTERNAL HQ (14)
--
-- internal_people, internal_tracks, internal_todos, internal_events,
-- internal_activity, internal_meter, internal_comments, internal_notifs,
-- internal_reminders, internal_sessions, internal_config,
-- internal_expenses, internal_passwords, internal_notes
--
-- EVERY ONE OF THESE HAS ALL FIVE API RULES = null.
-- 1700000038_internal_hq.js:5-8: "these rows are reachable ONLY through the
-- /internal/* hook routes in internal_hq.pb.js — never through
-- /api/collections/, not even with the service token."
-- That is the strongest posture in the tree and it must survive the move:
-- the D1 binding is reachable only from the HQ Worker's own routes.
--
-- Identifier quoting is NOT optional in this section. `desc`, `key`,
-- `date`, `action`, `read`, `value`, `position`, `notes` and `text` all
-- appear as column names; `desc` is a SQLite keyword and an unquoted one in
-- a column list is a syntax error, not a warning
-- (1700000048_hq_v2.js:170-171, 224-226).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 2.1  internal_people   1700000038_internal_hq.js:34-42  +  1700000048_hq_v2.js:204-218
--      Seeded with NAMES ONLY (Omar, Jose, Arav) — contact details for real
--      humans do not belong in git (1700000038:10-11).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_people" (
  "id"           TEXT PRIMARY KEY NOT NULL,
  "created"      TEXT    NOT NULL DEFAULT '',             -- 38:40 autodate onCreate
  "updated"      TEXT    NOT NULL DEFAULT '',             -- 38:41 autodate onCreate+onUpdate
  "name"         TEXT    NOT NULL DEFAULT '' CHECK (length("name") > 0),  -- 38:35 required, PB max 120, presentable
  "email"        TEXT    NOT NULL DEFAULT '',             -- 38:36 PB max 254
  "phone"        TEXT    NOT NULL DEFAULT '',             -- 38:37 PB max 32
  "is_admin"     INTEGER NOT NULL DEFAULT 0,              -- 38:38 bool
  "active"       INTEGER NOT NULL DEFAULT 0,              -- 38:39 bool
  "role"         TEXT    NOT NULL DEFAULT '',             -- 48:205 PB max 80
  "focus"        TEXT    NOT NULL DEFAULT '',             -- 48:206 PB max 140
  "tz"           TEXT    NOT NULL DEFAULT '',             -- 48:207 PB max 60. IANA ONLY ('America/Toronto'), never a friendly label —
                                                          -- "Pacific (PT)" cannot be computed with and fires reminders in the wrong
                                                          -- hour (48:38-41). '' is the signal onboarding reads; NOT backfilled (48:146-148).
  "remind_pref"  TEXT    NOT NULL DEFAULT '',             -- 48:208 PB max 20; inapp|email|sms|both. Backfilled to 'both' (48:403-409).
  "email_on"     INTEGER NOT NULL DEFAULT 0,              -- 48:209 bool. One-shot backfill to true (48:417-424) — a bool backfill is
                                                          -- NOT idempotent, false is indistinguishable from "turned off on purpose" (48:369-373).
  "sms_on"       INTEGER NOT NULL DEFAULT 0,              -- 48:210 bool, same one-shot backfill
  "code_hash"    TEXT    NOT NULL DEFAULT '',             -- 48:211 PB max 80. SHA-256 OF THE LOGIN CODE, NEVER THE CODE (48:50-54).
  "code_set_at"  TEXT    NOT NULL DEFAULT '',             -- 48:212 PB max 40
  "last_in"      TEXT    NOT NULL DEFAULT ''              -- 48:213 PB max 40
);
CREATE INDEX IF NOT EXISTS "idx_hq_people_name" ON "internal_people" ("name");
-- 1700000038_internal_hq.js:42.
CREATE INDEX IF NOT EXISTS "idx_hq_people_code" ON "internal_people" ("code_hash");
-- 1700000048_hq_v2.js:216-217. The login route looks a person up BY the hash
-- of the code they typed; unindexed, every sign-in is a full table scan.

-- ---------------------------------------------------------------------
-- 2.2  internal_tracks   1700000038_internal_hq.js:44-51  +  1700000048_hq_v2.js:223-233
--      These ARE the design's Projects. No parallel internal_projects
--      collection: internal_todos.track already carries the id (48:61-63).
--      Seeds: Company, Fellowship Growth, Fellowship Software (38:126-130)
--      and Ideas (48:356-358).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_tracks" (
  "id"        TEXT PRIMARY KEY NOT NULL,
  "created"   TEXT    NOT NULL DEFAULT '',                -- 38:49 autodate onCreate
  "updated"   TEXT    NOT NULL DEFAULT '',                -- 38:50 autodate onCreate+onUpdate
  "name"      TEXT    NOT NULL DEFAULT '' CHECK (length("name") > 0),  -- 38:45 required, PB max 120, presentable
  "kind"      TEXT    NOT NULL DEFAULT '',                -- 38:46 PB max 20; company|fellowship
  "members"   TEXT    NOT NULL DEFAULT '',                -- 38:47 PB max 2000; JSON array of internal_people ids
  "active"    INTEGER NOT NULL DEFAULT 0,                 -- 38:48 bool — hides a track from the New Task picker
  "desc"      TEXT    NOT NULL DEFAULT '',                -- 48:227 PB max 300. SQLITE KEYWORD — always quote it (48:224-226).
  "owner"     TEXT    NOT NULL DEFAULT '',                -- 48:228 PB max 40; internal_people id
  "archived"  INTEGER NOT NULL DEFAULT 0,                 -- 48:229 bool. DISTINCT FROM `active` on purpose and both are kept:
                                                          -- collapsing them means archiving a finished project also makes its
                                                          -- still-open tasks unfilable (48:65-69).
  "notes"     TEXT    NOT NULL DEFAULT ''                 -- 48:232 PB max 20000, not the 5KB default — that default has silently
                                                          -- truncated on save twice in this codebase (48:230-231)
);
-- No indexes declared for internal_tracks in any migration.
CREATE INDEX IF NOT EXISTS "idx_hq_tracks_name" ON "internal_tracks" ("name");
-- ADDED. Every seed probe and the /internal/tracks upsert look a track up by
-- name (1700000038:130, 1700000048:356, internal_hq.pb.js:1313).

-- ---------------------------------------------------------------------
-- 2.3  internal_todos   1700000038_internal_hq.js:53-75
--                       + 1700000040_remind_attempts.js:18
--                       + 1700000048_hq_v2.js:238-252
--                       + 1700000049_todo_position.js:25
--
--      `status` IS NOT WIDENED and must never be. It stays
--      {open, done, cancelled}. The board vocabulary (todo/doing/waiting/
--      blocked) is the SEPARATE `stage` column, because four live queries
--      key off the exact string 'open' (internal_hq.pb.js:71, 716, 1235,
--      1286) and widening status would make a dragged task vanish from the
--      payload, vanish from the assistant's context, and STOP BEING
--      REMINDED, with nothing red anywhere (48:12-28).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_todos" (
  "id"                TEXT PRIMARY KEY NOT NULL,
  "created"           TEXT    NOT NULL DEFAULT '',        -- 38:69 autodate onCreate
  "updated"           TEXT    NOT NULL DEFAULT '',        -- 38:70 autodate onCreate+onUpdate
  "title"             TEXT    NOT NULL DEFAULT '' CHECK (length("title") > 0),  -- 38:54 required, PB max 500, presentable
  "notes"             TEXT    NOT NULL DEFAULT '',        -- 38:56 PB max 20000 on purpose — "the 5KB text default has broken this codebase twice"
  "track"             TEXT    NOT NULL DEFAULT '',        -- 38:57 PB max 40; internal_tracks id
  "assignees"         TEXT    NOT NULL DEFAULT '',        -- 38:58 PB max 2000; JSON array of person ids
  "due"               TEXT    NOT NULL DEFAULT '',        -- 38:59 PB max 40; ISO YYYY-MM-DD
  "status"            TEXT    NOT NULL DEFAULT '',        -- 38:60 PB max 20; open|done|cancelled — DO NOT WIDEN
  "done_at"           TEXT    NOT NULL DEFAULT '',        -- 38:61 PB max 40
  "done_by"           TEXT    NOT NULL DEFAULT '',        -- 38:62 PB max 40
  "created_by"        TEXT    NOT NULL DEFAULT '',        -- 38:63 PB max 40
  "remind_at"         TEXT    NOT NULL DEFAULT '',        -- 38:64 PB max 40; UTC ISO datetime
  "remind_channel"    TEXT    NOT NULL DEFAULT '',        -- 38:65 PB max 10; email|sms|both|''
  "remind_sent_at"    TEXT    NOT NULL DEFAULT '',        -- 38:66 PB max 40 — the cron's IDEMPOTENCY CLAIM, stamped BEFORE the send
  "followup_sent_at"  TEXT    NOT NULL DEFAULT '',        -- 38:67 PB max 40 — one nudge, ever
  "research_job_id"   TEXT    NOT NULL DEFAULT '',        -- 38:68 PB max 40; jobs id
  "remind_attempts"   REAL    NOT NULL DEFAULT 0,         -- 1700000040_remind_attempts.js:18 NumberField min 0.
                                                          -- Bounds an otherwise infinite retry: 288 Twilio/Resend calls a day per stuck todo (:8-14).
  "stage"             TEXT    NOT NULL DEFAULT '',        -- 48:239 PB max 12; todo|doing|waiting|blocked. Backfilled to 'todo' (48:389).
  "priority"          TEXT    NOT NULL DEFAULT '',        -- 48:240 PB max 12; urgent|important|normal|later. Backfilled to 'normal' (48:390).
  "due_time"          TEXT    NOT NULL DEFAULT '',        -- 48:241 PB max 5; "HH:mm", local to the assignee
  "repeat_rule"       TEXT    NOT NULL DEFAULT '',        -- 48:242 PB max 40
  "hold_reason"       TEXT    NOT NULL DEFAULT '',        -- 48:243 PB max 200
  "watchers"          TEXT    NOT NULL DEFAULT '',        -- 48:244 PB max 2000; JSON id array
  "subtasks"          TEXT    NOT NULL DEFAULT '',        -- 48:245 PB max 4000; JSON [{t, done}] — on the row, not a table (48:90-92)
  "attachments"       TEXT    NOT NULL DEFAULT '',        -- 48:246 PB max 4000; JSON [{n, url, by, at}] — LINKS AND NAMES, NEVER UPLOADS (48:93-96)
  "cmt_count"         REAL    NOT NULL DEFAULT 0,         -- 48:247 NumberField min 0; denormalized. Maintained by the comment routes ONLY.
  "position"          REAL    NOT NULL DEFAULT 0          -- 1700000049_todo_position.js:25 NumberField, NO min — FLOAT ON PURPOSE.
                                                          -- A drop between two rows takes the midpoint, so a reorder is ONE write
                                                          -- instead of N (:9-16). 0 means "never hand-ordered". REAL is required here;
                                                          -- INTEGER would silently destroy every midpoint.
);
CREATE INDEX IF NOT EXISTS "idx_hq_todos_track"  ON "internal_todos" ("track", "status");
CREATE INDEX IF NOT EXISTS "idx_hq_todos_remind" ON "internal_todos" ("status", "remind_at");
CREATE INDEX IF NOT EXISTS "idx_hq_todos_due"    ON "internal_todos" ("status", "due");
-- 1700000038_internal_hq.js:72-74.
CREATE INDEX IF NOT EXISTS "idx_hq_todos_stage"  ON "internal_todos" ("status", "stage");
-- 1700000048_hq_v2.js:250-251 — serves the board's per-stage columns.

-- ---------------------------------------------------------------------
-- 2.4  internal_events   1700000038_internal_hq.js:77-85
--      Team calendar / countdowns. Unrelated to the product `events` table.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_events" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT    NOT NULL DEFAULT '',              -- 38:83 autodate onCreate
  "updated"     TEXT    NOT NULL DEFAULT '',              -- 38:84 autodate onCreate+onUpdate
  "title"       TEXT    NOT NULL DEFAULT '' CHECK (length("title") > 0),  -- 38:78 required, PB max 300, presentable
  "date"        TEXT    NOT NULL DEFAULT '',              -- 38:79 PB max 40; ISO date, optional THH:mm. SQLite function name — keep it quoted.
  "notes"       TEXT    NOT NULL DEFAULT '',              -- 38:80 PB max 5000
  "countdown"   INTEGER NOT NULL DEFAULT 0,               -- 38:81 bool
  "created_by"  TEXT    NOT NULL DEFAULT ''               -- 38:82 PB max 40
);
CREATE INDEX IF NOT EXISTS "idx_hq_events_date" ON "internal_events" ("date");
-- 1700000038_internal_hq.js:85.

-- ---------------------------------------------------------------------
-- 2.5  internal_activity   1700000038_internal_hq.js:87-95  +  1700000048_hq_v2.js:257-261
--      CREATED ONLY — no `updated` autodate. An append-only ledger.
--      THIS LEDGER FILLED THE RAILWAY VOLUME ONCE (48:94-96); the
--      internal_hq_prune cron (internal_hq.pb.js:2642) exists because of it
--      and must be ported.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_activity" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT    NOT NULL DEFAULT '',              -- 38:94 autodate onCreate
  "updated"     TEXT    NOT NULL DEFAULT '',              -- ABSENT in PocketBase; always ''
  "actor"       TEXT    NOT NULL DEFAULT '',              -- 38:88 PB max 40
  "actor_name"  TEXT    NOT NULL DEFAULT '',              -- 38:90 PB max 120. DENORMALIZED so the feed still reads right after
                                                          -- someone is deactivated (38:89).
  "action"      TEXT    NOT NULL DEFAULT '',              -- 38:91 PB max 40
  "subject"     TEXT    NOT NULL DEFAULT '',              -- 38:92 PB max 500
  "ref"         TEXT    NOT NULL DEFAULT '',              -- 38:93 PB max 40; the todo id on every task event
  "verb"        TEXT    NOT NULL DEFAULT ''               -- 48:258 PB max 120. Without it the Task panel has to string-parse
                                                          -- `subject` back apart, which breaks the first time somebody's name
                                                          -- contains a word the parser looks for (48:137-141).
);
CREATE INDEX IF NOT EXISTS "idx_hq_activity_created" ON "internal_activity" ("created");
-- 1700000038_internal_hq.js:95.
CREATE INDEX IF NOT EXISTS "idx_hq_activity_ref" ON "internal_activity" ("ref", "created");
-- 1700000048_hq_v2.js:259-260 — without it, per-task activity is a filter
-- over the whole ledger.

-- ---------------------------------------------------------------------
-- 2.6  internal_meter   1700000038_internal_hq.js:97-104
--      Bounded call counters. Rows: llm, research (38:132-135) and login
--      (48:349-350) — "a brute-force guard with no counter row is a
--      brute-force guard that fails open on the first attempt".
--      A COUNTER ROW, NEVER A ROW PER CALL: the audit ledger already filled
--      the 5GB volume once (1700000035:11-13).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_meter" (
  "id"           TEXT PRIMARY KEY NOT NULL,
  "created"      TEXT    NOT NULL DEFAULT '',             -- 38:102 autodate onCreate
  "updated"      TEXT    NOT NULL DEFAULT '',             -- 38:103 autodate onCreate+onUpdate
  "name"         TEXT    NOT NULL DEFAULT '' CHECK (length("name") > 0),  -- 38:98 required, PB max 60
  "hour"         TEXT    NOT NULL DEFAULT '',             -- 38:99 PB max 20; YYYY-MM-DDTHH
  "calls"        REAL    NOT NULL DEFAULT 0,              -- 38:100 number, min 0
  "live_job_id"  TEXT    NOT NULL DEFAULT ''              -- 38:101 PB max 40
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_hq_meter_name" ON "internal_meter" ("name");
-- 1700000038_internal_hq.js:104. UNIQUE and NOT partial — name is required.
-- This uniqueness is what makes the meter an atomic upsert target rather than
-- a read-modify-write race.

-- ---------------------------------------------------------------------
-- 2.7  internal_comments   1700000048_hq_v2.js:266-276
--      The one new thing that earns its own collection: comments have
--      identity, edits, deletes, replies and drive mentions, and two people
--      commenting at once must not clobber each other the way a JSON blob
--      read-modify-write does (48:101-104).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_comments" (
  "id"           TEXT PRIMARY KEY NOT NULL,
  "created"      TEXT    NOT NULL DEFAULT '',             -- 48:274 autodate onCreate
  "updated"      TEXT    NOT NULL DEFAULT '',             -- 48:275 autodate onCreate+onUpdate
  "todo"         TEXT    NOT NULL DEFAULT '' CHECK (length("todo") > 0),  -- 48:267 required, PB max 40
  "author"       TEXT    NOT NULL DEFAULT '',             -- 48:268 PB max 40
  "author_name"  TEXT    NOT NULL DEFAULT '',             -- 48:269 PB max 120, denormalized like internal_activity
  "text"         TEXT    NOT NULL DEFAULT '',             -- 48:270 PB max 4000, presentable
  "parent"       TEXT    NOT NULL DEFAULT '',             -- 48:271 PB max 40; '' = top level, else a comment id
  "edited_at"    TEXT    NOT NULL DEFAULT '',             -- 48:272 PB max 40; '' or ISO -> renders "· edited"
  "deleted"      INTEGER NOT NULL DEFAULT 0               -- 48:273 bool. A TOMBSTONE, NOT A DELETE — hard-deleting a comment
                                                          -- that has replies orphans them (48:109-110).
);
CREATE INDEX IF NOT EXISTS "idx_hq_cmt_todo" ON "internal_comments" ("todo", "created");
-- 1700000048_hq_v2.js:276.

-- ---------------------------------------------------------------------
-- 2.8  internal_notifs   1700000048_hq_v2.js:278-291
--      CREATED ONLY — no `updated` autodate.
--      emailed_at / smsed_at are the digest's CLAIM stamps, written BEFORE
--      the send, in the same shape as remind_sent_at, for the same reason:
--      send-first means unbounded duplicate texts every five minutes,
--      forever (48:114-117).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_notifs" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT    NOT NULL DEFAULT '',              -- 48:290 autodate onCreate
  "updated"     TEXT    NOT NULL DEFAULT '',              -- ABSENT in PocketBase; always ''
  "person"      TEXT    NOT NULL DEFAULT '' CHECK (length("person") > 0),  -- 48:279 required, PB max 40
  "kind"        TEXT    NOT NULL DEFAULT '',              -- 48:281 PB max 20; assign|mention|comment|deadline|done|file|overdue
  "text"        TEXT    NOT NULL DEFAULT '',              -- 48:282 PB max 200, presentable
  "sub"         TEXT    NOT NULL DEFAULT '',              -- 48:283 PB max 300
  "todo"        TEXT    NOT NULL DEFAULT '',              -- 48:284 PB max 40; '' or the click target
  "actor"       TEXT    NOT NULL DEFAULT '',              -- 48:285 PB max 40
  "read"        INTEGER NOT NULL DEFAULT 0,               -- 48:286 bool. Quote it — `read` is fine in SQLite but reserved elsewhere.
  "emailed_at"  TEXT    NOT NULL DEFAULT '',              -- 48:288 PB max 40; claim stamp
  "smsed_at"    TEXT    NOT NULL DEFAULT ''               -- 48:289 PB max 40; claim stamp
);
CREATE INDEX IF NOT EXISTS "idx_hq_notif_person" ON "internal_notifs" ("person", "read", "created");
-- 1700000048_hq_v2.js:291.

-- ---------------------------------------------------------------------
-- 2.9  internal_reminders   1700000048_hq_v2.js:293-307
--      internal_todos.remind_at STAYS and keeps working — it is the
--      one-shot bell. This exists because "one hour before" and "daily
--      until done" cannot be expressed in one column, and bolting a second
--      meaning onto remind_at would break the bell that already works
--      (48:119-124). fire_at is precomputed on write so the cron's due
--      query stays a plain indexed comparison.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_reminders" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT    NOT NULL DEFAULT '',              -- 48:305 autodate onCreate
  "updated"     TEXT    NOT NULL DEFAULT '',              -- 48:306 autodate onCreate+onUpdate
  "todo"        TEXT    NOT NULL DEFAULT '' CHECK (length("todo") > 0),  -- 48:294 required, PB max 40
  "person"      TEXT    NOT NULL DEFAULT '',              -- 48:295 PB max 40; '' = every recipient of the todo
  "rule"        TEXT    NOT NULL DEFAULT '',              -- 48:297 PB max 24; at|one_hour_before|one_day_before|when_overdue|daily_until_done
  "fire_at"     TEXT    NOT NULL DEFAULT '',              -- 48:299 PB max 40; UTC ISO, computed on write
  "channel"     TEXT    NOT NULL DEFAULT '',              -- 48:300 PB max 20
  "label"       TEXT    NOT NULL DEFAULT '',              -- 48:301 PB max 60, presentable
  "sent_at"     TEXT    NOT NULL DEFAULT '',              -- 48:302 PB max 40; the cron's claim
  "attempts"    REAL    NOT NULL DEFAULT 0,               -- 48:303 number min 0; bounded retry, same as remind_attempts
  "created_by"  TEXT    NOT NULL DEFAULT ''               -- 48:304 PB max 40
);
CREATE INDEX IF NOT EXISTS "idx_hq_rem_fire" ON "internal_reminders" ("sent_at", "fire_at");
-- 1700000048_hq_v2.js:307. Column order matters: the cron's query is
-- "unsent AND due", so sent_at leads.

-- ---------------------------------------------------------------------
-- 2.10  internal_sessions   1700000048_hq_v2.js:309-321
--       CREATED ONLY — no `updated` autodate.
--       token_hash only. A stealable plaintext session table is worse than
--       the shared key it replaces (48:126-129).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_sessions" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT NOT NULL DEFAULT '',                 -- 48:315 autodate onCreate
  "updated"     TEXT NOT NULL DEFAULT '',                 -- ABSENT in PocketBase; always ''
  "person"      TEXT NOT NULL DEFAULT '' CHECK (length("person") > 0),      -- 48:310 required, PB max 40
  "token_hash"  TEXT NOT NULL DEFAULT '' CHECK (length("token_hash") > 0),  -- 48:311 required, PB max 80; SHA-256 ONLY
  "expires"     TEXT NOT NULL DEFAULT '',                 -- 48:312 PB max 40
  "ip"          TEXT NOT NULL DEFAULT '',                 -- 48:313 PB max 60
  "ua"          TEXT NOT NULL DEFAULT ''                  -- 48:314 PB max 200
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_hq_sess_token" ON "internal_sessions" ("token_hash");
-- 1700000048_hq_v2.js:319. UNIQUE: one row per token. Two rows sharing a hash
-- would make "sign out" ambiguous and leave a live session behind after a code
-- reset (48:317-318). NOT partial — token_hash is required, '' cannot repeat.
CREATE INDEX IF NOT EXISTS "idx_hq_sess_person" ON "internal_sessions" ("person", "created");
-- 1700000048_hq_v2.js:320.

-- ---------------------------------------------------------------------
-- 2.11  internal_config   1700000048_hq_v2.js:323-328
--       Two or three rows, ever. Seeded: team_name=Anticipy,
--       perm_assign=everyone, perm_delete=creator (48:343-345), plus the
--       hq_v2_backfill marker row (48:428-429) that gates the one-shot
--       boolean backfill — DO NOT DROP THAT ROW during import, or a
--       re-run would silently switch everyone's email back on (48:369-373).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_config" (
  "id"       TEXT PRIMARY KEY NOT NULL,
  "created"  TEXT NOT NULL DEFAULT '',                    -- 48:326 autodate onCreate
  "updated"  TEXT NOT NULL DEFAULT '',                    -- 48:327 autodate onCreate+onUpdate
  "key"      TEXT NOT NULL DEFAULT '' CHECK (length("key") > 0),  -- 48:324 required, PB max 60, presentable. QUOTE IT — `key` is
                                                          -- reserved in several dialects and is a keyword in SQLite's INDEXED BY grammar.
  "value"    TEXT NOT NULL DEFAULT ''                     -- 48:325 PB max 2000
);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_hq_config_key" ON "internal_config" ("key");
-- 1700000048_hq_v2.js:328.

-- ---------------------------------------------------------------------
-- 2.12  internal_expenses   1700000050_expenses_vault.js:28-38
--       One table serves both lenses: rows carry the person, the page shows
--       "Mine" and "Company" as two views of the same data (:6-9).
--       `currency` is explicit because the team sits in Vancouver and buys
--       from the US, and a log that guesses the currency is a log nobody
--       trusts at tax time (:9-11).
--
--       NOTE: this collection was created by an `mk()` (:25) that passes NO
--       rule properties at all. PocketBase's zero value for a rule pointer
--       is nil = null = SUPERUSER ONLY, which is what the migration's own
--       header asserts (:20-21). All five rules are null.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_expenses" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT NOT NULL DEFAULT '',                 -- :36 autodate onCreate
  "updated"     TEXT NOT NULL DEFAULT '',                 -- :37 autodate onCreate+onUpdate
  "title"       TEXT NOT NULL DEFAULT '',                 -- :29 PB max 200 (NOT required)
  "amount"      REAL NOT NULL DEFAULT 0,                  -- :30 number, plain dollars. REAL, not INTEGER cents — that is what
                                                          -- PocketBase stores today; changing the unit during a migration would
                                                          -- silently multiply or divide every historical expense by 100.
  "currency"    TEXT NOT NULL DEFAULT '',                 -- :31 PB max 8; CAD|USD
  "date"        TEXT NOT NULL DEFAULT '',                 -- :32 PB max 10; YYYY-MM-DD
  "track"       TEXT NOT NULL DEFAULT '',                 -- :33 PB max 32
  "person"      TEXT NOT NULL DEFAULT '',                 -- :34 PB max 32
  "created_by"  TEXT NOT NULL DEFAULT ''                  -- :35 PB max 32
);
-- No indexes declared (:25 passes indexes: []).
CREATE INDEX IF NOT EXISTS "idx_hq_expenses_person_date" ON "internal_expenses" ("person", "date");
-- ADDED. The "Mine" lens is exactly this filter.

-- ---------------------------------------------------------------------
-- 2.13  internal_passwords   1700000050_expenses_vault.js:39-48
--       The company vault for tool logins.
--
--       secret_enc NEVER HOLDS PLAINTEXT. It is `$security.encrypt` output
--       keyed by ANTICIPY_VAULT_KEY from the environment, so a copied
--       database file exposes nothing without the env (:13-17).
--
--       MIGRATION HAZARD — READ THIS. `$security.encrypt` is PocketBase's
--       own Go AES-GCM helper. A Worker cannot decrypt those blobs with
--       WebCrypto unless it reimplements PocketBase's exact scheme
--       (nonce placement and encoding included). Either re-encrypt every
--       row through a one-time script that still has both PocketBase and
--       the key, or have the team re-enter the secrets. Do NOT copy the
--       ciphertext across and discover at reveal-time that nothing can read
--       it. The key name is ANTICIPY_VAULT_KEY; its VALUE appears nowhere
--       in this repo and must not.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_passwords" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT NOT NULL DEFAULT '',                 -- :46 autodate onCreate
  "updated"     TEXT NOT NULL DEFAULT '',                 -- :47 autodate onCreate+onUpdate
  "service"     TEXT NOT NULL DEFAULT '',                 -- :40 PB max 120
  "username"    TEXT NOT NULL DEFAULT '',                 -- :41 PB max 200
  "secret_enc"  TEXT NOT NULL DEFAULT '',                 -- :42 PB max 2000; ciphertext ONLY
  "url"         TEXT NOT NULL DEFAULT '',                 -- :43 PB max 500
  "notes"       TEXT NOT NULL DEFAULT '',                 -- :44 PB max 2000
  "updated_by"  TEXT NOT NULL DEFAULT ''                  -- :45 PB max 32
);
-- No indexes declared.

-- ---------------------------------------------------------------------
-- 2.14  internal_notes   1700000052_notes.js:13-22
--       A plain notes page, shared by the whole team ON PURPOSE: three
--       people don't need private notebooks inside their own dashboard,
--       they need one place where "the wifi password at the studio" stops
--       living in chat scrollback (:3-8).
--       All-null API rules (:10).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS "internal_notes" (
  "id"          TEXT PRIMARY KEY NOT NULL,
  "created"     TEXT NOT NULL DEFAULT '',                 -- :19 autodate onCreate
  "updated"     TEXT NOT NULL DEFAULT '',                 -- :20 autodate onCreate+onUpdate
  "title"       TEXT NOT NULL DEFAULT '',                 -- :14 PB max 200
  "body"        TEXT NOT NULL DEFAULT '',                 -- :15 PB max 50000
  "track"       TEXT NOT NULL DEFAULT '',                 -- :16 PB max 32
  "created_by"  TEXT NOT NULL DEFAULT '',                 -- :17 PB max 32
  "updated_by"  TEXT NOT NULL DEFAULT ''                  -- :18 PB max 32
);
-- No indexes declared.
CREATE INDEX IF NOT EXISTS "idx_hq_notes_track" ON "internal_notes" ("track");
-- ADDED. The notes page filters by track.

-- =====================================================================
-- SECTION 3 — CASCADE DELETE
--
-- PocketBase's `cascadeDelete: true` on six relation fields is Go code in
-- the record deleter, NOT an SQL foreign key — PocketBase creates no FKs at
-- all. Deleting an owner in D1 therefore deletes NOTHING unless the Worker
-- runs these statements itself. 1700000009_owner_ref.js:11-13 is explicit
-- that cascade was chosen so "delete everything about me" is a property of
-- the schema rather than a script somebody has to remember to run — so in
-- D1 it must be a single reviewed function, not scattered deletes.
--
-- Real FOREIGN KEY constraints are deliberately NOT declared above:
-- documented orphan rows exist (owner_profile with owner_ref = '' —
-- 1700000043_owner_profile_needs_owner.js:6-8) and '' is not NULL, so an
-- enforced FK would reject their import outright.
--
-- The six cascadeDelete relations, all -> owners.id:
--   jobs.owner_ref           1700000009_owner_ref.js:21,25-32
--   events.owner_ref         1700000009_owner_ref.js:21,25-32
--   owner_profile.owner_ref  1700000009_owner_ref.js:21,25-32
--   segments.owner_ref       1700000009_owner_ref.js:21,25-32
--   agents.owner_ref         1700000022_agents_owner_ref.js:33-40
--   pendants.owner_ref       1700000027_pendants_owner_ref.js:8-11
--   password_resets.owner    1700000012_password_resets.js:19-20
--
-- NOT cascade-deleted (plain TEXT, deleted explicitly by
-- account_delete.pb.js:69 and its neighbours — port that list, do not
-- assume this block covers them):
--   evidence.owner_ref, purges.owner_ref (deliberately NOT — the row must
--   outlive the account), agent_llm_audit.owner_ref,
--   agent_audit_sessions.owner_ref
--
-- Run as one batch (D1 batch() is atomic) with :owner bound once:
--
--   DELETE FROM "password_resets" WHERE "owner"     = ?1;
--   DELETE FROM "jobs"            WHERE "owner_ref" = ?1;
--   DELETE FROM "events"          WHERE "owner_ref" = ?1;
--   DELETE FROM "owner_profile"   WHERE "owner_ref" = ?1;
--   DELETE FROM "segments"        WHERE "owner_ref" = ?1;
--   DELETE FROM "agents"          WHERE "owner_ref" = ?1;
--   DELETE FROM "pendants"        WHERE "owner_ref" = ?1;
--   DELETE FROM "owners"          WHERE "id"        = ?1;
--
-- and then, separately and NOT as a cascade, whatever
-- account_delete.pb.js enumerates for the non-relation tables, plus the
-- INSERT into "purges" that records the request so it survives the
-- deletion (1700000039_purges.js:3-20). The per-owner memory.db on the
-- brain's own volume is a second system and is what `purges` exists for.
-- =====================================================================

-- =====================================================================
-- SECTION 4 — POST-IMPORT ASSERTIONS
--
-- Run these after the import. Each must return 0. They restate, as
-- queries, the invariants the CHECKs and partial-unique indexes above
-- encode, so a bulk load done with the constraints deferred is still
-- verified rather than assumed.
--
--   SELECT count(*) FROM "owner_profile" a JOIN "owner_profile" b
--     ON a."owner_ref" = b."owner_ref" AND a."id" <> b."id"
--     WHERE a."owner_ref" != '';                        -- one profile per account
--   SELECT count(*) FROM "owners" WHERE "email" = '';   -- email is the identity
--   SELECT count(*) FROM "owners" WHERE "tokenKey" = '';-- every live session dies without it
--   SELECT count(*) FROM "owners" WHERE "password" = '';-- an account nobody can log into
--   SELECT count(*) FROM "jobs"   WHERE "goal" = '' OR "status" = '';
--   SELECT count(*) FROM "events" WHERE "device_id" = '' OR "kind" = '';
--   SELECT count(*) FROM "evidence" WHERE "owner_ref" = '' OR "job" = '';
--   SELECT count(*) FROM "internal_sessions" WHERE "token_hash" = '';
--   SELECT count(*) FROM "internal_todos" WHERE "status" NOT IN ('open','done','cancelled');
--                                                       -- status must not have been widened
--
-- And these three, which should each return a NON-zero, expected number —
-- they are the rows a careless importer silently drops:
--
--   SELECT count(*) FROM "owner_profile" WHERE "owner_ref" = '';
--       -- the documented orphans (1700000043:6-8). Expected > 0 today.
--   SELECT count(*) FROM "internal_config" WHERE "key" = 'hq_v2_backfill';
--       -- expected exactly 1; losing it re-runs the one-shot bool backfill
--   SELECT count(*) FROM "internal_meter";
--       -- expected >= 3: llm, research, login
-- =====================================================================
