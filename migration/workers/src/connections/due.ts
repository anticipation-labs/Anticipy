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
 * (see below) and whose weight has not decayed to nothing. An owner with no
 * such row is not handed to the policy at all. So the bar is checked twice, in
 * the two places that can see it, and neither one is load-bearing alone.
 *
 * `weight > 0` and not `>= 0`: the column's own CHECK admits exactly 0, and
 * the schema says why — "a very old row decayed across many half-lives can
 * legitimately underflow to exactly 0.0". That row is an app they stopped
 * using, which is precisely what decay exists to say.
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
 * ── LAW 3 — TWO THINGS STAND BETWEEN THIS FILE AND A PERSON ──────────────
 *
 * Both measured 2026-09-06, both OUTSIDE this file, and both written down
 * here rather than left in a conversation:
 *
 *   1. NOTHING CALLS `installNudgeWiring`. src/cron.ts now dispatches
 *      `connectNudgeSweep` on the five-minute tick, and until a `NudgeDeps` is
 *      installed that sweep logs "no wiring installed; nobody was asked
 *      anything" and returns. The wiring is one line —
 *      `due: createDue(env)` beside the store, the catalog, the writer, the
 *      moment and the phone.
 *
 *   2. PRODUCTION DOES NOT REGISTER THE FIVE-MINUTE TICK. wrangler.jsonc
 *      carries `"crons": ["17 4 * * *"]` and nothing else; only
 *      wrangler.dev.jsonc has `"*\/5 * * * *"` (escaped, because this is a
 *      block comment). It was removed ON PURPOSE, and the reason is written
 *      beside it in that file: PocketBase's own sweep is still
 *      running against its own database, and two sweeps means the team gets
 *      every reminder twice. So the whole five-minute leg — the HQ reminders
 *      as well as this — is dispatched by code production never invokes. The
 *      fix is the cutover wrangler.jsonc already names, not a second home for
 *      this sweep on the nightly trigger: an ask that lands at 04:17 UTC is
 *      the 3am text this policy exists to prevent.
 *
 * test/connections-due.test.ts pins (2) as the CURRENT state and goes red the
 * day somebody enables the trigger, which is the day this note gets deleted.
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
}

/**
 * ONE STATEMENT, and the joins are `NOT EXISTS` rather than `LEFT JOIN … IS
 * NULL` so that a duplicate row on either side cannot multiply the evidence
 * rows and re-order the pick.
 *
 * `ROW_NUMBER() … PARTITION BY user_id` is what makes an owner appear ONCE.
 * The alternative — every (owner, app) pair — hands the policy the same owner
 * five times, and the 7-day global cap means at most one of those five could
 * ever be sent, so the other four are reads and a model call spent to be told
 * "this owner was asked about some app 0d ago". The sweep also carries its own
 * `askedThisTick` guard; belt and braces is cheap when the failure is a person
 * receiving three texts in one minute. The construct is neither new to this
 * Worker nor unproven on D1: `evidenceCap` in src/cron.ts ships the same
 * `ROW_NUMBER() OVER (PARTITION BY …)` shape on the `17 4 * * *` leg, which is
 * the one trigger production DOES register.
 *
 * WHICH ONE OF THE OWNER'S APPS WINS: the heaviest evidence, then the most
 * recent, then the slug and the source alphabetically so the answer is
 * deterministic rather than "whatever the b-tree walked into first". The
 * second app is offered the moment the first is connected, declined into a
 * snooze, or decays below the others — every one of which changes this order.
 */
function candidateSql(): string {
  const inList = MOMENT_SOURCES.map((_, i) => `?${i + 1}`).join(", ");
  const pNow = MOMENT_SOURCES.length + 1;
  const pCutoff = MOMENT_SOURCES.length + 2;
  const pCap = MOMENT_SOURCES.length + 3;
  return `
    SELECT "user_id", "toolkit", "source" FROM (
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
         AND s."weight" > 0
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
     WHERE "pick" = 1
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
  const res = await env.DB.prepare(candidateSql())
    .bind(...MOMENT_SOURCES, now, cutoff, Math.floor(cap))
    .all<CandidateRow>();

  const out: NudgeCandidate[] = [];
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
    out.push({
      owner,
      toolkit: toolkit as Toolkit,
      trigger: MOMENT_TRIGGER[source] as NudgeTrigger,
    });
  }
  return out;
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
