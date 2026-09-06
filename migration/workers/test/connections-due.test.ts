/**
 * test/connections-due.test.ts — WHO IS DUE, and the five-minute tick that
 * carries the question.
 *
 *   node --experimental-strip-types migration/workers/test/connections-due.test.ts
 *
 * WHAT IS REAL HERE. All of it except two other systems. The SQL is the
 * shipped statement, run by node:sqlite against the REAL migration/d1/
 * schema.sql — every CHECK, every PRIMARY KEY, the window function and the
 * three NOT EXISTS clauses are the database's own answers, not a fake that
 * records strings. `scheduled` out of src/cron.ts is the shipped dispatcher,
 * driven on the literal cron string wrangler.jsonc registers, so a leg that
 * exists but is never dispatched fails here. `connectNudgeSweep` out of
 * src/connections/nudge.ts is the shipped sweep. The catalog and the model
 * that writes the text never come into it: no candidate in this file is ever
 * asked anything, because this file is about WHO IS EVEN A CANDIDATE.
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH:
 *
 *   THE ADVERTISEMENT. An ask about an app on a hunch. The evidence bar is
 *   pinned from three directions — no signal row at all, a row decayed to
 *   weight 0, and a row whose source is not a moment anybody had.
 *
 *   ASKING SOMEBODY FOR SOMETHING THEY ALREADY GAVE. A connected app, and a
 *   nudge row that already says connected.
 *
 *   TALKING OVER A NO. A snooze, and the end of the ladder.
 *
 *   THREE TEXTS IN ONE MINUTE. The 7-day cap is GLOBAL — a nudge row for a
 *   DIFFERENT app closes the gate — and a clock that skewed into the future
 *   closes it too. A missing clock refuses outright, because a NaN cutoff
 *   compares as NULL and opens that gate for every owner in the table.
 *
 *   THE TICK THAT DIED OF THE OPTIONAL HALF. The connect ask is an
 *   interruption nobody asked for; the reminder sweep carries things somebody
 *   is waiting for. A throwing nudge sweep must cost nobody their reminder.
 *
 *   THE PART NOTHING CALLS. `installNudgeWiring` had zero callers on
 *   2026-09-06 and the whole /c/ feature answered 503 for the same reason a
 *   week earlier. The last section drives the real `scheduled` and asserts
 *   `due` was actually reached.
 *
 * MUTATIONS THIS FILE MUST GO RED ON: see the list at the bottom, each
 * anchored on a string that occurs EXACTLY ONCE in the file it mutates.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  DUE_CANDIDATES_PER_ASK,
  DUE_CANDIDATE_CAP,
  MOMENT_SOURCES,
  MOMENT_TRIGGER,
  createDue,
  dueCandidates,
} from "../src/connections/due.ts";
import {
  GLOBAL_ASK_INTERVAL_DAYS,
  MAX_ASKS_PER_SWEEP,
  connectNudgeSweep,
  installNudgeWiring,
  type NudgeDeps,
  type NudgeEnv,
} from "../src/connections/nudge.ts";
import {
  ConnectionsSchemaMissing,
  NUDGE_TRIGGERS,
  SIGNAL_SOURCES,
  type StoreEnv,
} from "../src/connections/store.ts";
import { scheduled, type CronEnv } from "../src/cron.ts";
import { FakeD1, asD1 } from "./fake-d1.ts";

const here = dirname(fileURLToPath(import.meta.url));
const DUE_SOURCE = readFileSync(join(here, "..", "src", "connections", "due.ts"), "utf8");
const CRON_SOURCE = readFileSync(join(here, "..", "src", "cron.ts"), "utf8");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

const logs: string[] = [];
const realLog = console.log;
console.log = (...a: unknown[]) => { logs.push(a.map(String).join(" ")); };

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const NOW = 1_757_000_000_000;
const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

const OWNER = "ownerdueaaaaa11";     // 15 lowercase alphanumerics, as D1 mints
const OTHER = "ownerduebbbbb22";

// TWO INVENTED SLUGS, in no catalog and named nowhere in src/connections/
// due.ts. "NO APP IS HARDCODED" made behavioural rather than promised.
const SLUG_A = "zzquixotic";
const SLUG_B = "wobblefish";

/** The five-minute schedule string wrangler.jsonc registers. */
const TICK_CRON = "*/5 * * * *";

/**
 * The two `app_usage_signals.source` values that ARE moments, and the
 * `NudgeTrigger` each one is — declared HERE and never read out of the file
 * under test, so that adding a third to due.ts goes red instead of quietly
 * moving this file's idea of what a moment is. See the check that names it.
 */
const MOMENTS_AS_DECLARED: Readonly<Record<string, string>> = Object.freeze({
  observer: "in_task",
  said: "user_named_it",
});

interface Rig {
  d1: FakeD1;
  env: StoreEnv & CronEnv;
}

function rig(opts: { schema?: boolean } = {}): Rig {
  const d1 = new FakeD1(opts);
  const env = {
    DB: asD1(d1),
    TWILIO_ACCOUNT_SID: "", TWILIO_AUTH_TOKEN: "", TWILIO_PHONE_NUMBER: "",
  } as unknown as StoreEnv & CronEnv;
  return { d1, env };
}

function signal(
  r: Rig,
  user: string,
  toolkit: string,
  source: string,
  weight = 3,
  lastSeen = NOW - HOUR,
): void {
  r.d1.db.prepare(
    `INSERT INTO "app_usage_signals" ("user_id","toolkit","source","alias","weight","last_seen_at")
     VALUES (?, ?, ?, '', ?, ?)`,
  ).run(user, toolkit, source, weight, lastSeen);
}

function connection(r: Rig, user: string, toolkit: string, status: string): void {
  r.d1.db.prepare(
    `INSERT INTO "connections"
       ("connected_account_id","user_id","toolkit","alias","status","writes_enabled","last_used_at")
     VALUES (?, ?, ?, '', ?, 0, NULL)`,
  ).run(`ca_${user}_${toolkit}`, user, toolkit, status);
}

function nudge(
  r: Rig,
  user: string,
  toolkit: string,
  row: { state?: string; level?: number; snooze_until?: number | null; sent_at?: number | null },
): void {
  r.d1.db.prepare(
    `INSERT INTO "connect_nudges"
       ("user_id","toolkit","state","level","snooze_until","trigger","sent_at","acted_at","channel")
     VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, NULL)`,
  ).run(
    user, toolkit, row.state ?? "never_asked", row.level ?? 0,
    row.snooze_until ?? null, row.sent_at ?? null,
  );
}

/** One owner, one app, one browser run's worth of evidence: the shape every
 *  exclusion below is measured against. */
function wellEvidenced(r: Rig, user = OWNER, toolkit = SLUG_A): void {
  signal(r, user, toolkit, "observer");
}

async function due(r: Rig, now = NOW) {
  return dueCandidates(r.env, now);
}

// ===========================================================================
// 1. THE CONTROL, AND THE EVIDENCE BAR
// ===========================================================================

await check("THE CONTROL: a well-evidenced owner is a candidate EXACTLY ONCE", async () => {
  const r = rig();
  wellEvidenced(r);
  const out = await due(r);
  assert.equal(out.length, 1, "expected exactly one candidate, got " + JSON.stringify(out));
  assert.deepEqual(out[0], { owner: OWNER, toolkit: SLUG_A, trigger: "in_task" });
  // "Exactly once" as a count over the whole answer, not just a length: a
  // candidate listed twice is an owner the sweep considers twice.
  assert.equal(out.filter((c) => c.owner === OWNER).length, 1);
});

await check("an owner with no evidence at all is not a candidate", async () => {
  const r = rig();
  // Everything else about this owner says yes: a nudge row that has never been
  // asked, no connection, no snooze. Only the evidence is missing.
  nudge(r, OWNER, SLUG_A, { state: "never_asked" });
  assert.deepEqual(await due(r), []);
});

await check("evidence decayed to weight 0 is not evidence", async () => {
  const r = rig();
  signal(r, OWNER, SLUG_A, "observer", 0);
  assert.deepEqual(await due(r), [],
    "a signal that decayed to exactly 0 is an app they stopped using");
  // THE CONTROL, same row, one number different.
  signal(r, OTHER, SLUG_A, "observer", 0.001);
  const out = await due(r);
  assert.equal(out.length, 1);
  assert.equal(out[0].owner, OTHER);
});

await check("a source that names no moment is weight, never a candidate", async () => {
  // mx and link are facts about an address or a message; connected and asked
  // are facts about our own records. None of them is a moment an ask can open
  // with, and an ask that names a moment nobody had is what the spec forbids.
  //
  // NOT DERIVED FROM `MOMENT_SOURCES`. A list read out of the file under test
  // moves when that file moves, and this check passed a mutation that added a
  // fourth source to the map precisely because it did that.
  const notMoments = SIGNAL_SOURCES.filter((s) => !Object.hasOwn(MOMENTS_AS_DECLARED, s));
  assert.equal(notMoments.length, 4, "the contract's source enum changed shape");
  for (const source of notMoments) {
    const r = rig();
    signal(r, OWNER, SLUG_A, source, 9);
    assert.deepEqual(await due(r), [], `source ${source} produced a candidate`);
  }
  // THE CONTROL: every source that IS a moment produces one, with its trigger.
  for (const source of Object.keys(MOMENTS_AS_DECLARED)) {
    const r = rig();
    signal(r, OWNER, SLUG_A, source, 9);
    const out = await due(r);
    assert.equal(out.length, 1, `source ${source} produced no candidate`);
    assert.equal(out[0].trigger, MOMENT_TRIGGER[source]);
  }
});

await check("the two moments are the two the contract describes, and no others", () => {
  // TYPED HERE, ON PURPOSE, rather than read out of due.ts. Each entry is a
  // contract.ts sentence:
  //   in_task       "a step routed to browser and the catalog has a match"
  //                 — which is what an `observer` signal IS (signals.ts: an
  //                 observed host after a browser run).
  //   user_named_it "they said 'my Notion'" — which is what `said` IS.
  // The other four sources are evidence about an address, a message, or our
  // own records. Adding one to the map is a claim that a moment happened, and
  // it needs a sentence like those two behind it, so this goes red and asks
  // for one.
  assert.deepEqual({ ...MOMENT_TRIGGER }, MOMENTS_AS_DECLARED,
    "due.ts now names a moment this test has no contract sentence for");
  for (const source of Object.keys(MOMENT_TRIGGER)) {
    assert.ok(SIGNAL_SOURCES.includes(source as never),
      `${source} is not a value app_usage_signals.source can hold`);
  }
  for (const trigger of Object.values(MOMENT_TRIGGER)) {
    assert.ok(NUDGE_TRIGGERS.includes(trigger),
      `${trigger} is not a NudgeTrigger the policy can score`);
  }
  assert.deepEqual([...MOMENT_SOURCES].sort(), Object.keys(MOMENT_TRIGGER).sort(),
    "MOMENT_SOURCES and MOMENT_TRIGGER disagree: a row would be selected with no trigger to "
      + "give it, or a trigger nothing ever selects");
});

// ===========================================================================
// 2. ALREADY CONNECTED
// ===========================================================================

await check("an owner who already connected that app is not a candidate", async () => {
  const r = rig();
  wellEvidenced(r);
  connection(r, OWNER, SLUG_A, "connected");
  assert.deepEqual(await due(r), []);
});

await check("a connection to a DIFFERENT app does not silence this one", async () => {
  const r = rig();
  wellEvidenced(r, OWNER, SLUG_A);
  connection(r, OWNER, SLUG_B, "connected");
  const out = await due(r);
  assert.equal(out.length, 1);
  assert.equal(out[0].toolkit, SLUG_A);
});

await check("a connection that is broken or gone is still worth asking about", async () => {
  // needs_reconnect is the repair of a thing this owner already chose, and the
  // policy has a whole branch for it. disconnected is an app they no longer
  // have. Excluding either here would make that branch unreachable.
  for (const status of ["needs_reconnect", "disconnected"]) {
    const r = rig();
    wellEvidenced(r);
    connection(r, OWNER, SLUG_A, status);
    const out = await due(r);
    assert.equal(out.length, 1, `status ${status} wrongly excluded the owner`);
  }
});

await check("a nudge row that says connected is not a candidate", async () => {
  const r = rig();
  wellEvidenced(r);
  nudge(r, OWNER, SLUG_A, { state: "connected" });
  assert.deepEqual(await due(r), []);
});

// ===========================================================================
// 3. THE SNOOZE AND THE LADDER
// ===========================================================================

await check("a snoozed owner is not a candidate", async () => {
  const r = rig();
  wellEvidenced(r);
  nudge(r, OWNER, SLUG_A, { state: "declined", level: 1, snooze_until: NOW + 14 * DAY });
  assert.deepEqual(await due(r), []);
});

await check("THE CONTROL: a snooze that has run out reopens the candidate", async () => {
  const r = rig();
  wellEvidenced(r);
  nudge(r, OWNER, SLUG_A, { state: "declined", level: 1, snooze_until: NOW - 1 });
  const out = await due(r);
  assert.equal(out.length, 1);
  assert.equal(out[0].owner, OWNER);
});

await check("a snooze on a DIFFERENT app does not silence this one", async () => {
  const r = rig();
  wellEvidenced(r, OWNER, SLUG_A);
  nudge(r, OWNER, SLUG_B, { state: "declined", level: 1, snooze_until: NOW + 45 * DAY });
  const out = await due(r);
  assert.equal(out.length, 1);
  assert.equal(out[0].toolkit, SLUG_A);
});

await check("three declines is the end: level 3 is not a candidate", async () => {
  const r = rig();
  wellEvidenced(r);
  nudge(r, OWNER, SLUG_A, { state: "declined", level: 3, snooze_until: NOW - 1 });
  assert.deepEqual(await due(r), [],
    "level 3 stops, and only the owner reopening it counts");
});

await check("level 2 is still a candidate: the ladder is the policy's, not this file's", async () => {
  // Deliberately NOT mirrored here. The level-2 allowlist depends on the
  // trigger, and a copy of it in this file would go stale the day a
  // laptop_closed moment becomes readable. Over-including costs a hold the
  // policy already owns; over-excluding costs somebody their ask forever.
  const r = rig();
  wellEvidenced(r);
  nudge(r, OWNER, SLUG_A, { state: "declined", level: 2, snooze_until: NOW - 1 });
  assert.equal((await due(r)).length, 1);
});

await check("a reconnect at level 3 is still a candidate", async () => {
  const r = rig();
  wellEvidenced(r);
  nudge(r, OWNER, SLUG_A, { state: "needs_reconnect", level: 3, snooze_until: NOW - 1 });
  assert.equal((await due(r)).length, 1,
    "the ladder governs 'will you connect an app you never connected'; a reconnect is the "
      + "repair of a thing this owner already chose");
});

// ===========================================================================
// 4. THE 7-DAY GLOBAL CAP
// ===========================================================================

await check("the 7-day cap holds ACROSS APPS", async () => {
  const r = rig();
  wellEvidenced(r, OWNER, SLUG_A);
  // The ask that was sent was about a DIFFERENT app. A per-app counter cannot
  // see it; this one has to.
  nudge(r, OWNER, SLUG_B, { state: "asked", sent_at: NOW - 1 * DAY });
  assert.deepEqual(await due(r), []);
});

await check("THE CONTROL: an ask older than the cap reopens the owner", async () => {
  const r = rig();
  wellEvidenced(r, OWNER, SLUG_A);
  nudge(r, OWNER, SLUG_B, {
    state: "asked", sent_at: NOW - (GLOBAL_ASK_INTERVAL_DAYS + 1) * DAY,
  });
  assert.equal((await due(r)).length, 1);
});

await check("the cap bites at every hour inside the window, and skew does not open it", async () => {
  for (const sentAt of [NOW - 1, NOW - HOUR, NOW - (GLOBAL_ASK_INTERVAL_DAYS * DAY) + 1, NOW + DAY]) {
    const r = rig();
    wellEvidenced(r);
    nudge(r, OWNER, SLUG_B, { state: "asked", sent_at: sentAt });
    assert.deepEqual(await due(r), [],
      `sent_at ${sentAt - NOW}ms from now did not close the gate`);
  }
});

await check("a nudge row nobody has ever been sent is not an ask at the epoch", async () => {
  const r = rig();
  wellEvidenced(r);
  nudge(r, OWNER, SLUG_B, { state: "never_asked", sent_at: null });
  assert.equal((await due(r)).length, 1,
    "a NULL sent_at is 'nobody has been asked', not 'asked in 1970'");
});

await check("another owner's ask does not close this owner's gate", async () => {
  const r = rig();
  wellEvidenced(r, OWNER, SLUG_A);
  nudge(r, OTHER, SLUG_A, { state: "asked", sent_at: NOW - HOUR });
  const out = await due(r);
  assert.equal(out.length, 1);
  assert.equal(out[0].owner, OWNER);
});

// ===========================================================================
// 5. ONE OWNER, ONE CANDIDATE — AND THE BOUND ON A TICK
// ===========================================================================

await check("an owner with two well-evidenced apps appears once, heaviest first", async () => {
  const r = rig();
  signal(r, OWNER, SLUG_A, "observer", 2);
  signal(r, OWNER, SLUG_B, "said", 7);
  const out = await due(r);
  assert.equal(out.length, 1, "one owner, one ask: the 7-day cap means the rest are reads "
    + "spent to be told 'asked 0d ago'");
  assert.equal(out[0].toolkit, SLUG_B);
  assert.equal(out[0].trigger, "user_named_it");
});

await check("two sources for one app are one candidate, not two", async () => {
  const r = rig();
  signal(r, OWNER, SLUG_A, "observer", 3);
  signal(r, OWNER, SLUG_A, "said", 3);
  assert.equal((await due(r)).length, 1);
});

await check("the per-tick cap is derived from what the sweep can actually send", () => {
  assert.equal(DUE_CANDIDATE_CAP, MAX_ASKS_PER_SWEEP * DUE_CANDIDATES_PER_ASK);
  assert.ok(DUE_CANDIDATE_CAP >= MAX_ASKS_PER_SWEEP,
    "a cap below the send budget would starve well-timed owners further down");
});

await check("a backlog is bounded at the cap and drains over ticks", async () => {
  const r = rig();
  const many = DUE_CANDIDATE_CAP + 7;
  for (let i = 0; i < many; i++) {
    // 15 lowercase alphanumerics, unique, as the schema's CHECK demands.
    signal(r, "dueowner" + String(i).padStart(7, "0"), SLUG_A, "observer", 1 + i);
  }
  const out = await due(r);
  assert.equal(out.length, DUE_CANDIDATE_CAP,
    "one tick must not try to consider an unbounded backlog");
  assert.equal(new Set(out.map((c) => c.owner)).size, DUE_CANDIDATE_CAP,
    "the cap must not be spent on one owner listed many times");
});

// ===========================================================================
// 6. WHEN IT CANNOT ANSWER, IT SAYS SO
// ===========================================================================

await check("a database that will not answer THROWS rather than saying nobody is due", async () => {
  const r = rig();
  wellEvidenced(r);
  r.d1.failOn = (sql) => /ROW_NUMBER/.test(sql);
  await assert.rejects(() => due(r), /D1_ERROR/,
    "'nobody is due' and 'we could not tell' are opposite facts; an empty list here is a "
      + "permanently quiet product with a green log line");
});

await check("a missing table refuses by name and points at the migration", async () => {
  const r = rig({ schema: false });
  await assert.rejects(
    () => due(r),
    (err: unknown) => {
      assert.ok(err instanceof ConnectionsSchemaMissing);
      assert.match(String((err as Error).message), /app_usage_signals/);
      assert.match(String((err as Error).message), /schema\.sql/);
      return true;
    },
  );
});

await check("a clock that is not a clock refuses, because a NaN cutoff opens the cap", async () => {
  const r = rig();
  wellEvidenced(r);
  nudge(r, OWNER, SLUG_B, { state: "asked", sent_at: NOW - HOUR });
  for (const bad of [NaN, Infinity, -Infinity, undefined, null, "now"]) {
    await assert.rejects(
      () => dueCandidates(r.env, bad as unknown as number),
      /the time|clock/,
      `due() accepted ${JSON.stringify(bad)} as the time`,
    );
  }
  // THE CONTROL: with a real clock the same rig answers — and answers "nobody",
  // because the 7-day cap is closed. The refusal above is about not being able
  // to ASK the question, never about the answer.
  assert.deepEqual(await due(r), []);
});

await check("a malformed owner id is dropped, not thrown on, and never asked", async () => {
  const r = rig({ schema: false });
  // The live table's CHECK refuses length != 15, so this row can only exist on
  // a database that predates it. Build that database on purpose.
  r.d1.db.exec(`CREATE TABLE "app_usage_signals" (
      "user_id" TEXT NOT NULL, "toolkit" TEXT NOT NULL, "source" TEXT NOT NULL,
      "alias" TEXT NOT NULL DEFAULT '', "weight" REAL NOT NULL DEFAULT 0,
      "last_seen_at" REAL NOT NULL DEFAULT 0,
      PRIMARY KEY ("user_id","toolkit","source","alias"))`);
  r.d1.db.exec(`CREATE TABLE "connections" ("connected_account_id" TEXT PRIMARY KEY,
      "user_id" TEXT, "toolkit" TEXT, "status" TEXT)`);
  r.d1.db.exec(`CREATE TABLE "connect_nudges" ("user_id" TEXT, "toolkit" TEXT,
      "state" TEXT, "level" INTEGER, "snooze_until" REAL, "sent_at" REAL,
      PRIMARY KEY ("user_id","toolkit"))`);
  signal(r, "omar", SLUG_A, "observer", 9);            // a display name
  signal(r, OWNER, SLUG_A, "observer", 1);             // and a real owner
  const out = await due(r);
  assert.equal(out.length, 1, "one bad row must not cost every other owner their ask");
  assert.equal(out[0].owner, OWNER);
  assert.ok(!JSON.stringify(out).includes("omar"),
    "a display name reached the sweep: this is the wrong-person failure");
});

// ===========================================================================
// 7. NO APP IS HARDCODED
// ===========================================================================

await check("due.ts names no app and holds no list of them", () => {
  // Every scenario above already ran on two slugs that exist in no catalog.
  // This is the source-level half: the file may know the CONTRACT's enums and
  // must know nothing about any particular app.
  assert.equal(DUE_SOURCE.includes(SLUG_A), false);
  // Comments stripped first: prose is where the reasons live and it is allowed
  // to quote a word. CODE is what must name no app.
  const code = DUE_SOURCE
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/(^|[^:])\/\/[^\n]*/g, "$1");
  const quoted = code.match(/"[a-z][a-z0-9]{2,}"/g) ?? [];
  const allowed = new Set([
    ...SIGNAL_SOURCES.map((s) => `"${s}"`),
    ...NUDGE_TRIGGERS.map((t) => `"${t}"`),
    '"app_usage_signals"', '"connections"', '"connect_nudges"',
    '"user_id"', '"toolkit"', '"source"', '"weight"', '"last_seen_at"',
    '"status"', '"state"', '"level"', '"snooze_until"', '"sent_at"',
    '"number"', '"string"', '"pick"',
  ]);
  const strays = quoted.filter((q) => !allowed.has(q));
  assert.deepEqual(strays, [],
    "an unexplained lowercase string literal in due.ts is where a per-app branch starts");
});

// ===========================================================================
// 8. THE FIVE-MINUTE TICK
//
// THESE RUN LAST ON PURPOSE: `installNudgeWiring` flips a module-level global
// that nothing turns back off, so every check above runs on a Worker with no
// wiring — which is also the state production is in until somebody installs
// one.
// ===========================================================================

/** The Worker's own dispatch, plus the waitUntil the runtime would have
 *  awaited. Rejections are captured rather than thrown, because "did the tick
 *  survive" is the thing under test. */
async function runCron(env: CronEnv, cron = TICK_CRON): Promise<PromiseSettledResult<unknown>[]> {
  const waited: Promise<unknown>[] = [];
  const ctx = { waitUntil: (p: Promise<unknown>) => { waited.push(p); }, passThroughOnException() {} };
  await scheduled(
    { cron, scheduledTime: NOW, noRetry() {} } as unknown as ScheduledController,
    env, ctx as unknown as ExecutionContext,
  );
  return Promise.allSettled(waited);
}

/** A todo whose reminder is due and whose recipients do not exist: the sweep
 *  claims it, fails to deliver, and stamps `remind_attempts`. That stamp is
 *  the proof the reminder leg ran to the end. */
function dueReminder(r: Rig, id = "tododuecheck01"): void {
  r.d1.db.prepare(
    `INSERT INTO "internal_todos" ("id","title","status","remind_at","remind_channel")
     VALUES (?, 'a reminder somebody is waiting for', 'open', ?, 'email')`,
  ).run(id, "2020-01-01T00:00:00.000Z");
}

function attemptsOf(r: Rig, id = "tododuecheck01"): number {
  const row = r.d1.rows<{ remind_attempts: number }>(
    `SELECT "remind_attempts" FROM "internal_todos" WHERE "id" = ?`, id)[0];
  return Number(row?.remind_attempts ?? -1);
}

await check("an unwired Worker asks nobody, and says so rather than throwing", async () => {
  const r = rig();
  wellEvidenced(r);
  const settled = await runCron(r.env);
  assert.deepEqual(settled.map((s) => s.status), ["fulfilled", "fulfilled"]);
  assert.ok(logs.some((l) => /no wiring installed/.test(l)),
    "an unwired sweep must name the missing wiring in the log");
});

await check("the five-minute tick carries the connect sweep AND the reminder sweep", async () => {
  const r = rig();
  dueReminder(r);
  const seen: number[] = [];
  const deps = { due: async (now: number) => { seen.push(now); return []; } } as unknown as NudgeDeps;
  installNudgeWiring((env) => (env === (r.env as unknown as NudgeEnv) ? deps : null));

  const settled = await runCron(r.env);
  assert.deepEqual(settled.map((s) => s.status), ["fulfilled", "fulfilled"]);
  assert.equal(seen.length, 1,
    "the tick never reached `due`: a sweep nothing dispatches is a part, not a feature");
  assert.ok(Number.isFinite(seen[0]), "`due` was handed something that is not a clock");
  assert.equal(attemptsOf(r), 1, "the reminder leg did not run");
});

await check("a throwing sweep loses the connect ask and NOT the tick", async () => {
  const r = rig();
  dueReminder(r);
  // The wiring itself throws — the one failure `connectNudgeSweep` does not
  // catch for itself, and therefore the one that reaches src/cron.ts.
  installNudgeWiring(() => { throw new Error("wiring blew up on purpose"); });

  const settled = await runCron(r.env);
  assert.deepEqual(settled.map((s) => s.status), ["fulfilled", "fulfilled"],
    "a rejected waitUntil marks the invocation failed, and a re-run of this tick re-sends "
      + "somebody's reminder");
  assert.equal(attemptsOf(r), 1,
    "the reminder leg must complete whatever the connect ask does");
  assert.ok(logs.some((l) => /connect nudge sweep: failed/.test(l)),
    "the failure must be swallowed LOUDLY");
});

await check("a throwing due loses the sweep and asks nobody", async () => {
  const r = rig();
  const deps = {
    due: async () => { throw new Error("the store could not answer"); },
  } as unknown as NudgeDeps;
  const report = await connectNudgeSweep(r.env as unknown as NudgeEnv, deps);
  assert.equal(report.wired, true);
  assert.equal(report.considered, 0);
  assert.equal(report.sent, 0);
  assert.ok(logs.some((l) => /could not read who is due/.test(l)));
});

await check("createDue is the shape NudgeDeps.due declares", async () => {
  const r = rig();
  wellEvidenced(r);
  const fn = createDue(r.env);
  const out = await fn(NOW);
  assert.equal(out.length, 1);
  assert.equal(out[0].owner, OWNER);
});

await check("src/cron.ts gives the connect ask its own waitUntil", () => {
  // The behavioural checks above prove both legs ran. This one pins WHY they
  // are independent: one chained promise would make either able to take the
  // other down, and the reminder leg is the one carrying things somebody is
  // waiting for.
  const tick = CRON_SOURCE.slice(CRON_SOURCE.indexOf('case "*/5 * * * *"'));
  const body = tick.slice(0, tick.indexOf("return;"));
  const calls = body.match(/ctx\.waitUntil\(/g) ?? [];
  assert.equal(calls.length, 2, "the five-minute tick must register two independent legs");
  assert.ok(body.indexOf("sweep(env)") < body.indexOf("connectAsks(env)"),
    "the reminder leg is registered first so it is already running whatever the second does");
});

await check("THE GAP: production does not register the tick this leg lives on", () => {
  // HARNESS-LAWS law 3, as a check rather than a promise. Everything above is
  // repo-green; NONE of it runs on api.anticipy.ai, and the reason is one line
  // in a config file this task does not own.
  //
  // `*/5 * * * *` was removed from wrangler.jsonc ON PURPOSE — PocketBase's
  // own sweep still runs against its own database and two sweeps would send
  // the team every reminder twice — so the whole five-minute case in
  // src/cron.ts, the HQ reminders included, is dispatched by code production
  // never invokes.
  //
  // THIS CHECK GOES RED THE DAY SOMEBODY ENABLES IT, which is the day the gap
  // closes: delete this check, and delete the LAW 3 note in
  // src/connections/due.ts with it.
  const prod = readFileSync(join(here, "..", "wrangler.jsonc"), "utf8");
  const dev = readFileSync(join(here, "..", "wrangler.dev.jsonc"), "utf8");
  assert.ok(/"crons"\s*:\s*\[[^\]]*"\*\/5 \* \* \* \*"/.test(dev),
    "wrangler.dev.jsonc no longer registers the five-minute tick, so not even a dev run "
      + "reaches connectAsks");
  assert.equal(/"crons"\s*:\s*\[[^\]]*"\*\/5 \* \* \* \*"/.test(prod), false,
    "wrangler.jsonc now registers \"*/5 * * * *\" — the connect ask is live, and this check "
      + "plus the LAW 3 note in src/connections/due.ts should be deleted in the same diff");
});

// ---------------------------------------------------------------------------
// MUTATIONS RUN AGAINST src/connections/due.ts AND src/cron.ts, 2026-09-06.
// Every one is anchored on a string that occurs EXACTLY ONCE in the file it
// mutates (the script refuses to run otherwise, because a regex that silently
// fails to match produces a false "it is tested" reading — that mistake was
// made twice on 2026-09-05). All fifteen went RED; the check each one killed
// is named.
//
// NUMBER 11 SURVIVED THE FIRST RUN, and the reason is worth keeping: the
// "not a moment" list was derived from `MOMENT_SOURCES`, so adding a source to
// due.ts moved the test's own idea of what a moment is and the loop skipped
// it. It is typed here now.
//
//   1  `AND s."weight" > 0` -> `AND s."weight" >= 0`
//      -> "evidence decayed to weight 0 is not evidence"
//   2  `AND c."status" = 'connected')` -> `AND c."status" = 'nothing')`
//      -> "an owner who already connected that app is not a candidate"
//   3  the `n."snooze_until" > ?` disjunct deleted
//      -> "a snoozed owner is not a candidate"
//   4  the whole `g."sent_at"` NOT EXISTS deleted
//      -> "the 7-day cap holds ACROSS APPS"
//   5  `AND g."sent_at" > ?${pCutoff})` -> `AND g."sent_at" < ?${pCutoff})`
//      -> "the cap bites at every hour inside the window, and skew does not open it"
//   6  `WHERE "pick" = 1` -> `WHERE "pick" >= 1`
//      -> "an owner with two well-evidenced apps appears once, heaviest first"
//   7  `LIMIT ?${pCap}` deleted
//      -> "a backlog is bounded at the cap and drains over ticks"
//   8  `if (typeof now !== "number" || !Number.isFinite(now)) {` -> `if (false) {`
//      -> "a clock that is not a clock refuses, because a NaN cutoff opens the cap"
//   9  `(n."level" >= 3 AND n."state" <> 'needs_reconnect')` -> `(0)`
//      -> "three declines is the end: level 3 is not a candidate"
//  10  `await requireTables(env);` deleted
//      -> "a missing table refuses by name and points at the migration"
//  11  `mx` added to MOMENT_TRIGGER
//      -> "the two moments are the two the contract describes, and no others"
//         and "a source that names no moment is weight, never a candidate"
//  12  src/cron.ts `ctx.waitUntil(connectAsks(env));` deleted
//      -> "the five-minute tick carries the connect sweep AND the reminder sweep"
//  13  src/cron.ts `connectAsks`'s try/catch removed
//      -> "a throwing sweep loses the connect ask and NOT the tick"
//  14  `ownerId(String(row?.user_id ?? ""))` -> the raw string
//      -> "a malformed owner id is dropped, not thrown on, and never asked"
//  15  `ORDER BY s."weight" DESC` -> `ASC`
//      -> "an owner with two well-evidenced apps appears once, heaviest first"
// ---------------------------------------------------------------------------

console.log = realLog;
console.log(`connections-due: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
