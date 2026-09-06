-- migration/d1/2026-09-06-connect-nudges-declined-soft.sql
-- Widen connect_nudges.state to carry 'declined_soft' (spec pages 21 and 25:
-- a skipped setup card is a 7-day soft snooze, NOT a real decline).
-- SQLite cannot alter a CHECK constraint, so the table is rebuilt.
-- connect_nudges held ZERO rows when this was run; the INSERT..SELECT is kept
-- anyway so the script is correct if it is ever replayed against a live table.
ALTER TABLE "connect_nudges" RENAME TO "connect_nudges_pre_soft";
CREATE TABLE "connect_nudges" (
  "user_id"      TEXT NOT NULL CHECK (length("user_id") = 15),
  "toolkit"      TEXT NOT NULL CHECK (length("toolkit") > 0),
  "state"        TEXT NOT NULL CHECK ("state" IN ('never_asked','asked','declined_soft','declined','connected','needs_reconnect')),
      -- contract.ts:81-87.
      -- 'declined_soft' added 2026-09-06. It is the setup card's Skip: page 21
      -- says that skip "records declined_soft with a 7-day snooze, not a real
      -- decline", and until that date the code recorded a real decline with a
      -- shorter clock — which raised the ask threshold from 0.50 to 0.80 and
      -- permanently silenced in_task, onboarding and repeated_use for that app.
      -- It is the ONE state that legitimately carries level 0 alongside a
      -- snooze; nudge.ts whatIsMissing enforces that pairing in both
      -- directions. The live table was rebuilt to widen this CHECK while
      -- connect_nudges held ZERO rows (measured immediately before).
  "level"        INTEGER NOT NULL DEFAULT 0 CHECK ("level" BETWEEN 0 AND 3),
      -- 0 while never declined; 1, 2, 3 as declines accumulate. LEVEL 3
      -- STOPS — LEVEL_THRESHOLD[3] is +Infinity and only the user may
      -- reopen it. A level of 4 would index that table as `undefined`, every
      -- comparison against it is false, and the owner who said no three
      -- times starts being asked again.
  "snooze_until" REAL NULL,
      -- epoch ms; NULL = not snoozed.
  "trigger"      TEXT NULL CHECK ("trigger" IS NULL OR "trigger" IN ('in_task','repeated_use','laptop_closed','user_named_it','onboarding')),
      -- contract.ts:91-96 — which real moment produced the ask, never "out
      -- of nowhere". Quoted because TRIGGER is a SQL keyword. The value is
      -- read by the snooze arithmetic (an onboarding skip snoozes 7 days,
      -- not 14 — policy.ts recordDecline), so a junk value here does not
      -- just spoil a log line, it changes when somebody is asked again.
  "sent_at"      REAL NULL,
  "acted_at"     REAL NULL,
      -- NULL when the decline was SILENCE rather than a "no". The spec's
      -- timers get tuned from this column, and a silent decline that stamps
      -- acted_at claims an action nobody took.
  "channel"      TEXT NULL CHECK ("channel" IS NULL OR "channel" IN ('sms','ios')),
  PRIMARY KEY ("user_id", "toolkit")
);
INSERT INTO "connect_nudges" SELECT * FROM "connect_nudges_pre_soft";
DROP TABLE "connect_nudges_pre_soft";
