/**
 * src/connections/due.ts — WHO IS DUE TO BE ASKED, and nothing else.
 *
 * `NudgeDeps.due(now)` is the one dependency src/connections/nudge.ts declares
 * and deliberately refuses to implement, in its own words: "a question about
 * `app_usage_signals`, about which steps just fell back to the browser, and
 * about whether a laptop is shut — three things this file does not and must
 * not read." This file reads the first of those three. The other two are not
 * readable from D1 today and this file does not pretend otherwise; see THE
 * TRIGGER below.
 *
 * THE DIVISION OF LABOUR, because getting it wrong is how a policy gets
 * duplicated in two places and drifts:
 *
 *   nudge.ts `shouldAsk`   decides WHETHER this owner may be interrupted.
 *                          Quiet hours, mid-step, before-the-result, the
 *                          decline ladder, the level-2 allowlist, the
 *                          right-time score, the four-state verdict.
 *   this file              decides WHO IS EVEN WORTH ASKING THAT ABOUT.
 *
 * So the predicates below are the ones whose answer can never change the
 * verdict from `hold` to `ask` — an owner with no evidence, an owner who
 * already connected this app, an owner mid-snooze, an owner asked about
 * something in the last week, an owner at the end of the ladder. Every one of
 * them is ALSO checked by `shouldAsk`, which is the point: this file is an
 * index, not a second policy. If it is wrong it can only be wrong by handing
 * the policy somebody the policy then refuses — never by asking somebody the
 * policy would have protected.
 *
 * THE ONE EXCEPTION TO THAT, STATED SO IT IS NOT A SURPRISE: a candidate this
 * file omits is a person nobody asks. Every filter here is therefore written
 * to over-include rather than over-exclude where the two differ, and the SQL
 * makes no attempt to mirror the level-2 allowlist or the score thresholds —
 * those depend on the trigger, and the day a `laptop_closed` moment becomes
 * readable, a mirrored copy of them here would be silently stale.
 *
 * ── THE EVIDENCE BAR ─────────────────────────────────────────────────────
 *
 * The spec's bar is `tasks_that_would_have_used_it > 0`: "we do not ask about
 * an app on a hunch". That count is a fact about the MOMENT and it arrives
 * through `NudgeDeps.moment`; `shouldAsk` holds on a zero and always will, and
 * this file neither reads it nor could — no table records it.
 *
 * What this file enforces is the same bar over the only evidence it may read:
 * AT LEAST ONE `app_usage_signals` row for this (owner, app) that is a moment
 * (see below) and that is still ALIVE. An owner with no such row is not handed
 * to the policy at all. So the bar is checked twice, in the two places that can
 * see it, and neither one is load-bearing alone.
 *
 * ── ALIVE, AND WHY THE QUERY NO LONGER DECIDES IT ────────────────────────
 *
 * This file used to write `AND s."weight" > 0` and call that the aliveness
 * test, quoting the schema's own sentence about a row "decayed across many
 * half-lives" underflowing to zero. IT WAS NEVER TRUE, and it was driven on
 * 2026-09-06: signals.ts decays on READ (`decayedWeight`, thirty-day
 * half-life) and the STORED column only ever moves when a NEW signal arrives
 * for that (owner, app, source, alias) — which raises it. So the stored number
 * never falls, `weight > 0` never became false for anybody, and a signal
 * nobody had refreshed in four hundred days produced a real text through the
 * shipped cron.
 *
 * The decay is signals.ts's and it stays there: `decayedWeight` is an
 * exponential and SQLite has no exponential, so a copy of it in SQL would be a
 * SECOND definition of alive, in a language that cannot express the first.
 * THE QUERY SELECTS AND THIS FILE FILTERS. The statement below carries no
 * weight predicate of any kind — deliberately, because the one boundary is
 * `ALIVE_WEIGHT_FLOOR` and it is stated exactly once, in TypeScript, next to
 * the `decayedWeight` call that uses it.
 *
 * WHAT THAT COSTS AND WHY IT IS PAID: the query has to hand back more rows
 * than it used to (`SIGNAL_ROWS_PER_OWNER` per owner, not one), because the
 * heaviest STORED row can be the deadest one and dropping an owner on account
 * of it would be this file over-excluding — a person nobody asks.
 *
 * ── THE TRIGGER, AND WHY ONLY TWO OF THE FIVE ────────────────────────────
 *
 * `NudgeCandidate` carries a `NudgeTrigger`: which real moment produced the
 * ask, "never out of nowhere". `app_usage_signals` records evidence keyed by
 * `source`, and two of its six sources ARE moments this file can name:
 *
 *   observer -> in_task        a browser run ended on that app's own site.
 *                              contract.ts: "a step routed to browser and the
 *                              catalog has a match".
 *   said     -> user_named_it  the owner named the app. contract.ts: "they
 *                              said 'my Notion'".
 *
 * The other four are not moments. `mx` and `link` are facts about an address
 * or a message, `connected` and `asked` are facts about our own records —
 * signals.ts says so where it weights them. They still add weight, and weight
 * is what ORDERS candidates below; they just cannot name the moment an ask
 * would open with, and an ask that names a moment nobody had is the thing the
 * spec forbids.
 *
 * `laptop_closed`, `repeated_use` and `onboarding` are not derivable here at
 * all: nothing in D1 records that a Mac is shut, `app_usage_signals` merges
 * every browser run into ONE row with a weight rather than counting them, and
 * onboarding is a screen, not a sweep. A caller that KNOWS one of those
 * happened calls `sendConnectAsk` directly with it. This file never guesses at
 * one, because the trigger is what the policy scores.
 *
 * ── HARNESS-LAWS LAW 1 ───────────────────────────────────────────────────
 *
 * Nothing here decides what anybody MEANT. `MOMENT_TRIGGER` maps one closed
 * enum the database CHECKs (`source`) onto another closed enum the contract
 * declares (`NudgeTrigger`). It is not a word list and it never sees prose:
 * the meaning question — "when they said that, did they mean an app, and
 * which one?" — was asked of a model before a `said` row was ever written
 * (signals.ts takes a `ToolkitVerdict` and adds weight only for
 * `{kind:"toolkit"}`; `unclear`, `none` and no-verdict add nothing). By the
 * time a row reaches this file the understanding has already happened and
 * been recorded. What is left is a join.
 *
 * NO APP IS NAMED IN THIS FILE. There is no slug, no domain and no per-app
 * anything; `toolkit` is a column that is read and passed on. The test runs
 * the whole path on two slugs that exist in no catalog.
 *
 * ── LAW 3 — WHAT STANDS BETWEEN THIS FILE AND A PERSON ───────────────────
 *
 * Both of the two things this note used to name are CLOSED, on 2026-09-06 and
 * in the same diff as this sentence:
 *
 *   `installNudgeWiring` has a caller — src/cron.ts installs
 *   src/connections/wiring.ts's `nudgeWiring` at module load, so the sweep has
 *   a `NudgeDeps` and this file's `createDue` is the `due` port in it.
 *
 *   wrangler.jsonc registers `"*\/5 * * * *"` beside the nightly trigger
 *   (escaped, because this is a block comment), so the five-minute case in
 *   src/cron.ts is dispatched by code production actually invokes. The
 *   PocketBase sweep that made two schedules unsafe was stopped on 2026-09-05.
 *
 * WHAT IS STILL NOT DONE, so nobody reads the above as the feature working:
 *
 *   1. NO DEPLOY HAS BEEN VERIFIED. Everything here is repo-green. The leg goes
 *      green when a tick is observed on api.anticipy.ai — overnight/
 *      is_connect_live.py leg 11 reads it from the rows the sweep leaves, which
 *      is the only half of it a gate can see without a `wrangler tail`.
 *
 *   2. THE TWO MOMENT SOURCES HAVE NO PRODUCTION WRITER. `observer` needs the
 *      browser hand to report the host a run ended on, and `said` needs a
 *      `ToolkitVerdict` from wherever the owner's words are read
 *      (src/connections/text_commands.ts is one such reader, wired into the
 *      inbound SMS path on 2026-09-06). Until one of them writes rows, this
 *      query correctly returns nobody and NOBODY IS ASKED ANYTHING — which
 *      reads exactly like a working quiet night, and is why leg 11 reports it
 *      as UNPROVEN rather than green.
 */

/// <reference types="@cloudflare/workers-types" />

import type {
  NudgeTrigger,
  OwnerId,
  Toolkit,
} from "../../../../spike/two-hands/src/connections/contract.ts";
import { GLOBAL_ASK_INTERVAL_DAYS, MAX_ASKS_PER_SWEEP } from "./nudge.ts";
import type { NudgeCandidate } from "./nudge.ts";
import {
  ConnectionsSchemaMissing,
  liveColumns,
  ownerId,
  type SignalSource,
  type StoreEnv,
} from "./store.ts";
import {
  DEFAULT_HALF_LIFE_MS,
  SOURCE_DECAYS,
  WEIGHT_MEDIUM,
  decayedWeight,
} from "./signals.ts";

const DAY_MS = 24 * 60 * 60 * 1000;

// ---------------------------------------------------------------------------
// THE MOMENTS THIS FILE CAN NAME
// ---------------------------------------------------------------------------

/**
 * `app_usage_signals.source` -> the `NudgeTrigger` it IS. Enum to enum; see
 * THE TRIGGER in the header for why the other four sources appear nowhere.
 *
 * Frozen because it is read at run time by `MOMENT_SOURCES`, which becomes the
 * `IN (…)` list of the query below: a mutated entry here is an app_usage row
 * that would be asked about under a moment that never happened.
 */
export const MOMENT_TRIGGER: Readonly<Record<string, NudgeTrigger>> = Object.freeze({
  observer: "in_task",
  said: "user_named_it",
});

/** The sources of `MOMENT_TRIGGER`, in a stable order, as the query's IN list.
 *  Derived rather than typed twice: a source in one and not the other is a row
 *  selected with no trigger to give it, or a trigger nothing ever selects. */
export const MOMENT_SOURCES: readonly SignalSource[] =
  Object.freeze(Object.keys(MOMENT_TRIGGER) as SignalSource[]);

// ---------------------------------------------------------------------------
// THE CAP
// ---------------------------------------------------------------------------

/**
 * How many candidates one tick may consider per ask it could possibly send.
 *
 * Not 1. Most candidates hold for a reason that has nothing to do with them —
 * quiet hours alone cover ten hours of every day, and "the result has not been
 * delivered yet" covers most of the rest — so a cap of exactly
 * `MAX_ASKS_PER_SWEEP` would mean a tick where the top twenty owners are all
 * asleep sends nothing while a well-timed owner one row further down waits
 * another five minutes.
 */
export const DUE_CANDIDATES_PER_ASK = 5;

/**
 * THE BOUND ON ONE TICK'S WORK: 100 candidates, and the reason is the prune's
 * own (src/cron.ts): it bounds the work one tick does so a backlog drains over
 * several ticks instead of timing out forever on the first.
 *
 * Two things make 100 the number rather than 200. The sweep can send at most
 * `MAX_ASKS_PER_SWEEP` texts, so candidates beyond a small multiple of that
 * are reads with no reachable outcome. And each candidate costs the sweep
 * several D1 reads (`readNudge`, `nudgesForOwner`, whatever `moment` needs)
 * inside the SAME Worker invocation as the reminder sweep, which spends one
 * subrequest per reminder it sends (cron.ts header, item 3). The two legs
 * share one budget, and the leg that carries somebody's reminders is the one
 * that must not run out.
 *
 * Derived from `MAX_ASKS_PER_SWEEP` rather than typed, so retuning that number
 * moves this one with it instead of quietly changing the ratio.
 */
export const DUE_CANDIDATE_CAP = MAX_ASKS_PER_SWEEP * DUE_CANDIDATES_PER_ASK;

// ---------------------------------------------------------------------------
// ALIVE — the one boundary, stated once
// ---------------------------------------------------------------------------

/**
 * How long a signal may go unrefreshed before it stops being evidence, in
 * signals.ts's own unit: half-lives. Six of them is a hundred and eighty days.
 *
 * WHY IT IS A NUMBER HERE AT ALL. signals.ts decays and RANKS; it never has to
 * say where the bottom is, because a caller taking the top of a sorted list
 * does not care what the last entry is worth. This file does have to say,
 * because there is nothing below it: the answer is "text this person" or
 * "text nobody", and `decayedWeight` reaches exactly zero only through float
 * underflow, which takes about a thousand half-lives — eighty-eight years. A
 * floor of "greater than zero" would therefore be the old bug with extra
 * arithmetic.
 *
 * SIX, and the spec's own sentence is the argument: "Signals decay so an app
 * you stopped using stops coming up." Six months of not once opening an app,
 * not once naming it, and not once having a browser run end on it is the
 * plainest reading of "stopped using it" this table can express. The cost is
 * stated in signals.ts and is the same trade: the payroll thing used once a
 * quarter falls off, and the `repeated_use` trigger is what catches it, at the
 * moment it is actually used.
 */
export const DEAD_AFTER_HALF_LIVES = 6;

/**
 * THE BOUNDARY. Below this a signal is an app they stopped using, and this
 * file hands nobody to the policy on account of it.
 *
 * DERIVED, NEVER TYPED: it is what the WEAKEST thing `app_usage_signals` can
 * hold — one Medium signal — is worth after `DEAD_AFTER_HALF_LIVES` of
 * silence, computed by signals.ts's own `decayedWeight`. Retune the half-life
 * there and this moves with it; there is no second copy of the arithmetic and
 * no second copy of the number. The SQL below states no weight bound at all,
 * which is what makes "stated once" true rather than claimed.
 */
export const ALIVE_WEIGHT_FLOOR =
  decayedWeight(WEIGHT_MEDIUM, 0, DEAD_AFTER_HALF_LIVES * DEFAULT_HALF_LIFE_MS);

/**
 * How many of ONE owner's signal rows the statement hands back so that the
 * decay can be applied to them out here.
 *
 * NOT ONE. The row with the heaviest STORED weight can be the deadest row an
 * owner has — that is the whole shape of the defect this section exists to
 * close — so a query that returned only the top row per owner would hand back
 * a corpse and this file would drop an owner whose second row is alive and
 * fresh. Five is `DUE_CANDIDATES_PER_ASK` and the same reasoning: enough that
 * the common case has somewhere to fall back to, small enough that one owner
 * cannot fill a tick.
 */
export const SIGNAL_ROWS_PER_OWNER = DUE_CANDIDATES_PER_ASK;

/**
 * A row's weight AS OF `now`, which is the only weight that means anything.
 *
 * Both halves are signals.ts's and neither is re-derived: which sources go
 * stale at all (`SOURCE_DECAYS` — a connection that exists and an ask that was
 * answered are as true a year later) and what staleness costs
 * (`decayedWeight`). This function is the seam, not a second opinion.
 */
function weightNow(weight: unknown, lastSeenAt: unknown, source: string, now: number): number {
  const stored = Number(weight);
  if (!Number.isFinite(stored)) return 0;
  if (!SOURCE_DECAYS[source as SignalSource]) return stored;
  return decayedWeight(stored, Number(lastSeenAt), now, DEFAULT_HALF_LIFE_MS);
}

// ---------------------------------------------------------------------------
// THE SCHEMA GUARD
// ---------------------------------------------------------------------------

/**
 * What each table must actually have live for this query to mean anything.
 *
 * The same discipline as store.ts's `REQUIRED`, and for the same measured
 * reason: on 2026-09-05 the live `events` table was missing two columns
 * schema.sql declared and every write turned into a D1 1101. A read is worse
 * than a write here, because a missing table does not throw in every SQLite —
 * it throws in one and returns nothing in another, and "nothing" is
 * indistinguishable from "nobody is due". A named refusal that says which
 * migration to run is the only honest answer.
 */
const REQUIRED: Readonly<Record<string, readonly string[]>> = Object.freeze({
  app_usage_signals: ["user_id", "toolkit", "source", "weight", "last_seen_at"],
  connections: ["user_id", "toolkit", "status"],
  connect_nudges: ["user_id", "toolkit", "state", "level", "snooze_until", "sent_at"],
});

async function requireTables(env: StoreEnv): Promise<void> {
  for (const table of Object.keys(REQUIRED)) {
    const live = await liveColumns(env, table);
    const missing = (REQUIRED[table] ?? []).filter((c) => !live.has(c));
    // An EMPTY set is the table not existing at all, which `filter` reports as
    // every column missing — the same error, naming the same migration.
    if (missing.length > 0) throw new ConnectionsSchemaMissing(table, missing);
  }
}

// ---------------------------------------------------------------------------
// THE QUERY
// ---------------------------------------------------------------------------

interface CandidateRow {
  user_id: unknown;
  toolkit: unknown;
  source: unknown;
  /** As STORED — the weight as of this row's own `last_seen_at`, which is not
   *  the weight now. `weightNow` is what turns it into an answer. */
  weight: unknown;
  last_seen_at: unknown;
}

/**
 * ONE STATEMENT, and the joins are `NOT EXISTS` rather than `LEFT JOIN … IS
 * NULL` so that a duplicate row on either side cannot multiply the evidence
 * rows and re-order the pick.
 *
 * `ROW_NUMBER() … PARTITION BY user_id` is what bounds an owner to
 * `SIGNAL_ROWS_PER_OWNER` rows. Without it, every (owner, app, source) pair
 * comes back and one busy owner fills the whole tick; with `pick = 1` — which
 * is what this said until 2026-09-06 — a single dead row at the top of an
 * owner's list silences an owner whose next row is alive. `dueCandidates`
 * decays what comes back and keeps ONE candidate per owner, so the guarantee
 * the sweep depends on is unchanged: the 7-day global cap means at most one
 * ask per owner could ever be sent, so a second candidate for the same owner
 * is a read and a model call spent to be told "asked 0d ago". The sweep also
 * carries its own `askedThisTick` guard; belt and braces is cheap when the
 * failure is a person receiving three texts in one minute. The construct is
 * neither new to this Worker nor unproven on D1: `evidenceCap` in src/cron.ts
 * ships the same `ROW_NUMBER() OVER (PARTITION BY …)` shape on the
 * `17 4 * * *` leg, which is the one trigger production DOES register.
 *
 * NO WEIGHT PREDICATE, AND THAT IS THE POINT. Which of an owner's apps wins,
 * and whether any of them is alive at all, are both decided out in
 * `dueCandidates` from the DECAYED weight — see ALIVE above. The ordering in
 * here is the STORED weight, and it does one job only: deciding which rows a
 * bounded read brings back when the table is bigger than one tick.
 */
function candidateSql(): string {
  const inList = MOMENT_SOURCES.map((_, i) => `?${i + 1}`).join(", ");
  const pNow = MOMENT_SOURCES.length + 1;
  const pCutoff = MOMENT_SOURCES.length + 2;
  const pRows = MOMENT_SOURCES.length + 3;
  const pCap = MOMENT_SOURCES.length + 4;
  return `
    SELECT "user_id", "toolkit", "source", "weight", "last_seen_at" FROM (
      SELECT s."user_id"      AS "user_id",
             s."toolkit"      AS "toolkit",
             s."source"       AS "source",
             s."weight"       AS "weight",
             s."last_seen_at" AS "last_seen_at",
             ROW_NUMBER() OVER (
               PARTITION BY s."user_id"
               ORDER BY s."weight" DESC, s."last_seen_at" DESC,
                        s."toolkit" ASC, s."source" ASC
             ) AS "pick"
        FROM "app_usage_signals" s
       WHERE s."source" IN (${inList})
         AND NOT EXISTS (
               SELECT 1 FROM "connections" c
                WHERE c."user_id" = s."user_id"
                  AND c."toolkit" = s."toolkit"
                  AND c."status" = 'connected')
         AND NOT EXISTS (
               SELECT 1 FROM "connect_nudges" n
                WHERE n."user_id" = s."user_id"
                  AND n."toolkit" = s."toolkit"
                  AND ( n."state" = 'connected'
                     OR (n."snooze_until" IS NOT NULL AND n."snooze_until" > ?${pNow})
                     OR (n."level" >= 3 AND n."state" <> 'needs_reconnect') ))
         AND NOT EXISTS (
               SELECT 1 FROM "connect_nudges" g
                WHERE g."user_id" = s."user_id"
                  AND g."sent_at" IS NOT NULL
                  AND g."sent_at" > ?${pCutoff})
    )
     WHERE "pick" <= ?${pRows}
     ORDER BY "weight" DESC, "last_seen_at" DESC, "user_id" ASC
     LIMIT ?${pCap}`;
}

/**
 * The candidates, newest evidence first, one per owner, at most `cap` of them.
 *
 * IT THROWS RATHER THAN RETURNING AN EMPTY LIST when it cannot answer. Those
 * two are opposite facts — "nobody is due" and "we could not tell" — and
 * `connectNudgeSweep` already keeps them apart: it catches, logs "could not
 * read who is due", and asks nobody. Collapsing them here would turn a missing
 * table into a permanently quiet product with a green log line, which is the
 * shape of the failure that left the ears deaf for 30 hours.
 */
export async function dueCandidates(
  env: StoreEnv,
  now: number,
  cap: number = DUE_CANDIDATE_CAP,
): Promise<NudgeCandidate[]> {
  // THE CLOCK IS A FLOOR INPUT. A NaN or an Infinity binds to SQLite as a
  // value every comparison against is NULL, so `sent_at > <cutoff>` is never
  // true, the NOT EXISTS holds for everybody, AND THE 7-DAY CAP OPENS FOR THE
  // WHOLE TABLE. The direction of that failure is a hundred people texted at
  // once, so it refuses instead.
  if (typeof now !== "number" || !Number.isFinite(now)) {
    throw new TypeError(
      `due() was given ${JSON.stringify(now)} as the time. Without a clock the 7-day cap `
        + "compares against NULL, which is true for every owner who has ever been asked.",
    );
  }
  if (typeof cap !== "number" || !Number.isFinite(cap) || cap < 0) {
    throw new TypeError(`due() was given ${JSON.stringify(cap)} as its per-tick cap`);
  }

  await requireTables(env);

  const cutoff = now - GLOBAL_ASK_INTERVAL_DAYS * DAY_MS;
  // `cap` counts OWNERS, as it always has; the row budget is that many owners'
  // worth of rows, because the decay that decides which of an owner's rows is
  // alive cannot be run inside the statement.
  const owners = Math.floor(cap);
  const res = await env.DB.prepare(candidateSql())
    .bind(...MOMENT_SOURCES, now, cutoff, SIGNAL_ROWS_PER_OWNER, owners * SIGNAL_ROWS_PER_OWNER)
    .all<CandidateRow>();

  /** One readable row, with the only weight that means anything attached. */
  interface Live { candidate: NudgeCandidate; weight: number; seen: number }
  const live: Live[] = [];
  for (const row of res.results ?? []) {
    // Re-checked on the way out, not trusted on the way in. The database's own
    // CHECK already refuses a `user_id` that is not 15 characters, but this is
    // the value that becomes the owner a connection is BOUND to, and the one
    // failure this whole feature is shaped around is a connection bound to a
    // name instead of a person. A row that cannot be read is DROPPED, not
    // thrown on: one malformed row must not cost every other owner their ask,
    // and dropping is the direction that asks fewer people.
    let owner: OwnerId;
    try {
      owner = ownerId(String(row?.user_id ?? ""));
    } catch {
      console.log("connect nudge due: dropped a signal row whose user_id is not an owner id");
      continue;
    }
    const toolkit = typeof row?.toolkit === "string" ? row.toolkit.trim() : "";
    if (toolkit === "") {
      console.log("connect nudge due: dropped a signal row with no toolkit");
      continue;
    }
    // `Object.hasOwn`, not `MOMENT_TRIGGER[source]`: a source of "constructor"
    // reaches the prototype and comes back truthy, and the ask would carry a
    // function where the policy expects a moment.
    const source = String(row?.source ?? "");
    if (!Object.hasOwn(MOMENT_TRIGGER, source)) {
      console.log(`connect nudge due: dropped a row whose source names no moment: ${source}`);
      continue;
    }
    // THE ALIVENESS TEST, and the only one there is. `>` and not `>=`, matching
    // the direction the old SQL predicate pointed: a row sitting exactly on the
    // floor has run out its silence.
    const seen = Number(row?.last_seen_at);
    const weight = weightNow(row?.weight, seen, source, now);
    if (!(weight > ALIVE_WEIGHT_FLOOR)) continue;

    live.push({
      candidate: {
        owner,
        toolkit: toolkit as Toolkit,
        trigger: MOMENT_TRIGGER[source] as NudgeTrigger,
      },
      weight,
      seen: Number.isFinite(seen) ? seen : 0,
    });
  }

  // ONE TOTAL ORDER, then one pass. Sorting by the decayed weight and walking
  // it taking the first row for each owner gives both answers at once: which
  // of an owner's apps is offered (their heaviest LIVE evidence) and which
  // owners a bounded tick spends itself on. The tail of the comparator is the
  // slug and the source so the answer is deterministic rather than "whatever
  // the b-tree walked into first", and the owner id last so that two owners
  // whose evidence is identical still come back in a stable order.
  live.sort((a, b) =>
    b.weight - a.weight
    || b.seen - a.seen
    || cmp(a.candidate.toolkit, b.candidate.toolkit)
    || cmp(a.candidate.trigger, b.candidate.trigger)
    || cmp(String(a.candidate.owner), String(b.candidate.owner)));

  const out: NudgeCandidate[] = [];
  const taken = new Set<string>();
  for (const entry of live) {
    // Checked BEFORE the push, not after, so a cap of zero returns nobody
    // rather than one. The statement's own LIMIT already makes that
    // unreachable today; a bound that depends on another bound to be correct
    // is the kind that stops being correct when somebody tunes the other one.
    if (out.length >= owners) break;
    const who = String(entry.candidate.owner);
    if (taken.has(who)) continue;
    taken.add(who);
    out.push(entry.candidate);
  }
  return out;
}

/** Code-unit order, never `localeCompare`: collation depends on the ICU data
 *  the runtime was built with, so two deploys of the same code could order the
 *  same owners differently. signals.ts `rankRows` draws the same line. */
function cmp(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

/**
 * `NudgeDeps.due` for a live D1, ready to hand to `installNudgeWiring`.
 *
 *     installNudgeWiring((env) => ({ store, catalog, write, moment, phone,
 *                                    due: createDue(env) }));
 */
export function createDue(env: StoreEnv): (now: number) => Promise<NudgeCandidate[]> {
  return (now: number) => dueCandidates(env, now);
}
