// THE LADDER, TESTED AS A STATE MACHINE.
//
// Every gate, every demotion trigger, and — the half that actually protects the
// owner — every thing that must NOT promote. A ladder that only has tests for
// climbing is a ladder that climbs on anything.
//
// No network, no key, no account: the clock is injected and every table is in
// memory, so these run on a laptop with the wifi off.

import test from "node:test";
import assert from "node:assert/strict";

import type {
  ApiCandidate,
  MatchVerdict,
  Outcome,
  Rung,
  ShadowRun,
} from "../src/contract.ts";
import {
  InMemoryLedger,
  LADDER,
  MemoryTable,
  type LedgerOutcome,
  type LedgerStore,
  asErrorKind,
  memoryStore,
  percentile,
} from "../src/ledger.ts";

const SIG = "sig_email_send";
const APP = "gmail";
const TOOL = "GMAIL_SEND_EMAIL";
const T0 = 1_756_000_000_000;

function ledger(now: number = T0): InMemoryLedger {
  // A fixed clock, so `last_run_at` and `last_change_at` are assertable and a
  // test never fails at midnight.
  return new InMemoryLedger({ now: () => now });
}

function outcome(over: Partial<LedgerOutcome> = {}): Outcome {
  const base: LedgerOutcome = {
    user_id: "owner",
    signature_hash: SIG,
    app: APP,
    hand: "api",
    tool_slug: TOOL,
    ok: true,
    ms: 100,
    cost: 0,
    verifierResult: "unknown",
  };
  return { ...base, ...over } as Outcome;
}

/**
 * The read the 2 -> 3 gate is paid in: it succeeded AND the verifier watched
 * the effect land.
 *
 * Named rather than inlined because the fixture default is `"unknown"` on
 * purpose — "nobody looked" is the honest default for a run, and every leg that
 * expects a promotion has to say out loud that somebody did look. When these
 * tests said `{ ok: true }` and still promoted, that was the defect.
 */
const READ_THE_VERIFIER_SAW: Partial<LedgerOutcome> = { ok: true, verifierResult: "verified" };

function candidate(over: Partial<ApiCandidate> = {}): ApiCandidate {
  const base: ApiCandidate = {
    user_id: "owner",
    signature_hash: SIG,
    app: APP,
    tool_slug: TOOL,
    match_score: 0.42,
    match_verdict: "yes",
    connected: false,
    first_seen_at: T0,
    source: "composio",
  };
  return { ...base, ...over };
}

/** Put a pair on a rung without walking the gates, for tests about a HIGHER
 *  gate. The gates below it have their own tests. */
async function standingOn(led: InMemoryLedger, rung: Rung, user = "owner"): Promise<void> {
  await led.setRung(user, SIG, APP, rung);
}

// ---------------------------------------------------------------------------
// PERCENTILES — hand-computed, because "roughly right" latency is how a p95
// regression hides for a month.
// ---------------------------------------------------------------------------

test("percentile: n=1 — the single sample is both p50 and p95", () => {
  assert.equal(percentile([42], 50), 42);
  assert.equal(percentile([42], 95), 42);
});

test("percentile: n=2 — nearest rank, never interpolated", () => {
  // ranks: ceil(2*50/100)=1 -> sorted[0]; ceil(2*95/100)=2 -> sorted[1].
  // p95 of two runs is the SLOWER run, not their average, which is a number
  // neither call ever took.
  assert.equal(percentile([10, 20], 50), 10);
  assert.equal(percentile([10, 20], 95), 20);
  assert.equal(percentile([20, 10], 50), 10, "unsorted input must sort first");
});

test("percentile: n=3", () => {
  // ceil(3*50/100)=2 -> sorted[1]=20; ceil(3*95/100)=3 -> sorted[2]=30.
  assert.equal(percentile([30, 10, 20], 50), 20);
  assert.equal(percentile([30, 10, 20], 95), 30);
});

test("percentile: n=10", () => {
  const s = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
  // ceil(10*50/100)=5 -> sorted[4]=50; ceil(10*95/100)=10 -> sorted[9]=100.
  assert.equal(percentile(s, 50), 50);
  assert.equal(percentile(s, 95), 100);
});

test("percentile: the rank is integer-first, so 7% of 100 is sample 7 not 8", () => {
  // (7/100)*100 is 7.000000000000001 in IEEE754 and ceils to 8. The ledger
  // computes (n*pct)/100 for exactly this reason.
  const s = Array.from({ length: 100 }, (_, i) => i + 1);
  assert.equal(percentile(s, 7), 7);
});

test("percentile: an empty sample is 0, not NaN", () => {
  assert.equal(percentile([], 50), 0);
  assert.equal(percentile([], 95), 0);
});

// ---------------------------------------------------------------------------
// capability_stats
// ---------------------------------------------------------------------------

test("record maintains n, successes, cost and last_run_at", async () => {
  const led = ledger();
  await led.record(outcome({ ms: 100, cost: 0.001 }));
  await led.record(outcome({ ms: 300, cost: 0.001, ok: false, verifierResult: "unknown" }));
  await led.record(outcome({ ms: 200, cost: 0.001 }));

  const [row] = await led.stats("owner", SIG, APP, "api", TOOL);
  assert.equal(row.n, 3);
  assert.equal(row.successes, 2);
  assert.equal(row.p50_ms, 200);
  assert.equal(row.p95_ms, 300);
  assert.equal(row.last_run_at, T0);
  assert.equal(row.cost_usd_total, 0.003, "0.001 three times must be 0.003, not 0.0030000000000000005");
});

test("cost survives a hundred small calls without floating-point lint", async () => {
  const led = ledger();
  for (let i = 0; i < 100; i++) await led.record(outcome({ cost: 0.0001 }));
  const [row] = await led.stats("owner", SIG, APP, "api", TOOL);
  assert.equal(row.cost_usd_total, 0.01);
});

test("p50/p95 on the stats row are exact for n = 1, 2, 3 and 10", async () => {
  const led = ledger();
  const expected: Array<[number, number, number]> = [
    // [samples so far, p50, p95]
    [1, 10, 10],
    [2, 10, 20],
    [3, 20, 30],
  ];
  const ms = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100];
  for (let i = 0; i < 3; i++) {
    await led.record(outcome({ ms: ms[i] }));
    const [row] = await led.stats("owner", SIG, APP, "api", TOOL);
    assert.equal(row.n, expected[i][0]);
    assert.equal(row.p50_ms, expected[i][1], `p50 at n=${expected[i][0]}`);
    assert.equal(row.p95_ms, expected[i][2], `p95 at n=${expected[i][0]}`);
  }
  for (let i = 3; i < 10; i++) await led.record(outcome({ ms: ms[i] }));
  const [row] = await led.stats("owner", SIG, APP, "api", TOOL);
  assert.equal(row.n, 10);
  assert.equal(row.p50_ms, 50);
  assert.equal(row.p95_ms, 100);
});

test("stats rows are per hand and per tool; prior returns all of them", async () => {
  const led = ledger();
  await led.record(outcome({ hand: "api", tool_slug: TOOL }));
  await led.record(outcome({ hand: "browser", tool_slug: "chrome" }));
  const rows = await led.prior("owner", SIG, APP);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((r) => r.hand).sort(), ["api", "browser"]);
});

test("last_fail_reason keeps the auth failure a later success does not undo", async () => {
  const led = ledger();
  await led.record(outcome({ ok: false, failKind: "auth", failReason: "auth" }));
  let [row] = await led.stats("owner", SIG, APP, "api", TOOL);
  assert.equal(row.last_fail_reason, "auth");

  await led.record(outcome({ ok: true }));
  [row] = await led.stats("owner", SIG, APP, "api", TOOL);
  assert.equal(
    row.last_fail_reason,
    "auth",
    "clearing it on success erases the only record of why the owner was nudged to reconnect",
  );
});

test("rows handed back are copies — editing one does not edit the ledger", async () => {
  const led = ledger();
  await led.record(outcome());
  const [row] = await led.stats("owner", SIG, APP, "api", TOOL);
  row.n = 999;
  row.rung = 4;
  const [again] = await led.stats("owner", SIG, APP, "api", TOOL);
  assert.equal(again.n, 1);
  assert.equal(again.rung, 0);
});

// ---------------------------------------------------------------------------
// RUNG 0 -> 1: a candidate the judge vouched for AND the app connected
// ---------------------------------------------------------------------------

test("an unseen pair starts at rung 0", async () => {
  const led = ledger();
  assert.equal(await led.rung("owner", SIG, APP), 0);
  assert.equal(await led.writesOptedIn("owner", APP), false);
});

test("a vouched-for candidate on an UNCONNECTED app does not leave rung 0", async () => {
  const led = ledger();
  await led.noteCandidate(candidate({ match_verdict: "yes", connected: false }));
  assert.equal(await led.rung("owner", SIG, APP), 0);
});

test("a connected app with no vouched-for candidate does not leave rung 0", async () => {
  const led = ledger();
  await led.setConnection("owner", APP, true);
  for (const verdict of ["no", "unclear", "no-verdict"] as MatchVerdict[]) {
    await led.noteCandidate(candidate({ tool_slug: `T_${verdict}`, match_verdict: verdict }));
    assert.equal(
      await led.rung("owner", SIG, APP),
      0,
      `verdict "${verdict}" is not a licence — only an explicit "yes" is`,
    );
  }
});

test("judge yes + connected promotes to shadow, in either arrival order", async () => {
  const a = ledger();
  await a.noteCandidate(candidate({ match_verdict: "yes" }));
  await a.setConnection("owner", APP, true);
  assert.equal(await a.rung("owner", SIG, APP), 1, "connection landing second must notice");

  const b = ledger();
  await b.setConnection("owner", APP, true);
  await b.noteCandidate(candidate({ match_verdict: "yes" }));
  assert.equal(await b.rung("owner", SIG, APP), 1, "candidate landing second must notice");

  const c = ledger();
  await c.noteCandidate(candidate({ match_verdict: "yes", connected: true }));
  assert.equal(await c.rung("owner", SIG, APP), 1, "a candidate may assert its own connection");
});

test("a vouched candidate for a DIFFERENT app does not promote this pair", async () => {
  const led = ledger();
  await led.setConnection("owner", APP, true);
  await led.noteCandidate(candidate({ app: "slack", tool_slug: "SLACK_SEND", match_verdict: "yes" }));
  assert.equal(await led.rung("owner", SIG, APP), 0);
});

// ---------------------------------------------------------------------------
// RUNG 1 -> 2: three CONSECUTIVE parity matches
// ---------------------------------------------------------------------------

test("three consecutive parity matches promote shadow reads to API reads", async () => {
  const led = ledger();
  await standingOn(led, 1);
  // "verified" is spelled out on every match rather than left to the fixture
  // default, because it is the load-bearing half: parity is agreement with the
  // VERIFIER's ground truth, and a match nobody verified is a claim, not a
  // match. The leg two tests down pins that.
  await led.record(outcome({ parity: true, verifierResult: "verified" }));
  await led.record(outcome({ parity: true, verifierResult: "verified" }));
  assert.equal(await led.rung("owner", SIG, APP), 1, "two is not three");
  await led.record(outcome({ parity: true, verifierResult: "verified" }));
  assert.equal(await led.rung("owner", SIG, APP), 2);
});

test("two matches then a MISMATCH resets the streak", async () => {
  const led = ledger();
  await standingOn(led, 1);
  const match = { parity: true, verifierResult: "verified" } as Partial<LedgerOutcome>;
  await led.record(outcome(match));
  await led.record(outcome(match));
  await led.record(outcome({ parity: false }));
  assert.equal(await led.rung("owner", SIG, APP), 1);

  await led.record(outcome(match));
  await led.record(outcome(match));
  assert.equal(await led.rung("owner", SIG, APP), 1, "the streak restarted at the mismatch");
  await led.record(outcome(match));
  assert.equal(await led.rung("owner", SIG, APP), 2);
});

test("a parity mismatch on a READ resets the streak but is not a demotion", async () => {
  const led = ledger();
  await standingOn(led, 1);
  await led.record(outcome({ parity: false }));
  const pair = await led.ladderState("owner", SIG, APP);
  assert.equal(pair?.rung, 1, "a shadow read that disagreed is why shadow mode exists");
  assert.equal(pair?.parity_mismatches, 1);
  assert.equal(pair?.shadow_required, false);
});

test("a browser-hand parity match does not also count — three matches need three runs", async () => {
  const led = ledger();
  await standingOn(led, 1);
  for (let i = 0; i < 3; i++) {
    await led.record(outcome({ hand: "browser", tool_slug: "chrome", parity: true }));
  }
  assert.equal(
    await led.rung("owner", SIG, APP),
    1,
    "counting both sides of a shadow pair promotes after a run and a half",
  );
});

test("a failed API call cannot contribute a parity match", async () => {
  const led = ledger();
  await standingOn(led, 1);
  for (let i = 0; i < 3; i++) {
    await led.record(outcome({ ok: false, parity: true, failKind: "auth" }));
  }
  assert.equal(await led.rung("owner", SIG, APP), 1);
});

test("a parity claim the verifier never made cannot buy the API read hand", async () => {
  // Parity is DEFINED in contract.ts as agreement with the verifier's ground
  // truth — "did the expected effect happen" — never as the two hands matching
  // each other. So `parity: true` beside `verifierResult: "unknown"` is a
  // caller asserting a comparison nobody performed, and beside "unverified" it
  // is a caller asserting one the verifier refused.
  //
  // THE FAILURE THIS PREVENTS: three shadow runs where the verifier was down
  // hand the pair the API hand for reads, and the browser — the supervisor that
  // was the whole point of rung 1 — stops running. The floor polarity from
  // LAW1 applies: a privilege needs something to license it, not merely the
  // absence of an objection.
  for (const claimed of ["unknown", "unverified"] as const) {
    const led = ledger();
    await standingOn(led, 1);
    for (let i = 0; i < 3; i++) {
      await led.record(outcome({ ok: true, parity: true, verifierResult: claimed }));
    }
    assert.equal(
      await led.rung("owner", SIG, APP),
      1,
      `"${claimed}" is not the verifier vouching for a match`,
    );
  }

  const good = ledger();
  await standingOn(good, 1);
  for (let i = 0; i < 3; i++) {
    await good.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  }
  assert.equal(await good.rung("owner", SIG, APP), 2, "a verified match still counts");
});

test("a run the verifier refused empties the streak even though it is not a mismatch", async () => {
  // `parity === false` and `verifierResult === "unverified"` are the same
  // event told two ways, and #applyDemotion already treats them as one. If only
  // the first emptied the streak, an API read the verifier said did NOT happen
  // would sit inside a window of "three consecutive matches" without breaking
  // it — the streak surviving the exact evidence it exists to be broken by.
  const led = ledger();
  await standingOn(led, 1);
  await led.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  await led.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  await led.record(outcome({ ok: true, verifierResult: "unverified" }));
  await led.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  assert.equal(
    await led.rung("owner", SIG, APP),
    1,
    "the run the verifier refused restarted the window",
  );
  const pair = await led.ladderState("owner", SIG, APP);
  assert.equal(pair?.parity_streak, 1);
});

test("a real API failure breaks the streak; an excused one is invisible to it", async () => {
  // "Three CONSECUTIVE parity matches" cannot be true of a window with a broken
  // API call in the middle of it. Letting the streak step over one promotes a
  // pair that errors one shadow run in three to reading the owner's mail
  // unsupervised.
  const broken = ledger();
  await standingOn(broken, 1);
  await broken.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  await broken.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  await broken.record(outcome({ ok: false, failKind: "schema" }));
  await broken.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  assert.equal(await broken.rung("owner", SIG, APP), 1, "the tool broke inside the window");

  // A 401 is not the tool being wrong (see isExcusedFailure), so it stays
  // invisible to this counter for the same reason it is invisible to the
  // demotion counter: a refresh token ageing out must not cost earned ground.
  const excused = ledger();
  await standingOn(excused, 1);
  await excused.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  await excused.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  await excused.record(outcome({ ok: false, failKind: "auth" }));
  await excused.record(outcome({ ok: true, parity: true, verifierResult: "verified" }));
  assert.equal(await excused.rung("owner", SIG, APP), 2, "a token expiry is not the tool erring");
});

// ---------------------------------------------------------------------------
// RUNG 2 -> 3: the owner's write opt-in AND ten clean reads
// ---------------------------------------------------------------------------

test("ten reads NOBODY VERIFIED do not unlock the write path", async () => {
  // THE DEFECT THIS PINS. The 3 -> 4 gate already refuses "unknown" — its own
  // comment says "nobody looked, and three writes nobody looked at are not
  // evidence" — while the 2 -> 3 gate, the one that UNLOCKS WRITES, took the
  // identical evidence. The strict gate guarded the smaller privilege.
  //
  // THE FAILURE THIS PREVENTS: ten API reads run with the verifier down or not
  // wired, nobody ever checks that a single answer was right or complete, and
  // the pair is handed the rung at which the agent starts sending the owner's
  // mail. An unverified read is not a read that worked; it is a read nobody
  // looked at, and the floor polarity from LAW1 says a privilege needs
  // something to license it.
  for (const seen of ["unknown", "unverified"] as const) {
    const led = ledger();
    await standingOn(led, 2);
    await led.setWritesOptIn("owner", APP, true);
    for (let i = 0; i < 10; i++) await led.record(outcome({ ok: true, verifierResult: seen }));
    assert.equal(
      await led.rung("owner", SIG, APP),
      2,
      `ten "${seen}" reads are ten runs nobody vouched for`,
    );
    const pair = await led.ladderState("owner", SIG, APP);
    assert.equal(pair?.clean_reads, 0, "and none of them was banked for later, either");
  }
});

test("the same ten reads, verified, do unlock it", async () => {
  // The other half of the gate: made strict, it must still be reachable. A
  // guard that can never be satisfied takes the API hand out entirely, which
  // is a guard that guards nothing by being infinitely strict.
  const led = ledger();
  await standingOn(led, 2);
  await led.setWritesOptIn("owner", APP, true);
  for (let i = 0; i < 10; i++) {
    await led.record(outcome({ ok: true, verifierResult: "verified" }));
  }
  assert.equal(await led.rung("owner", SIG, APP), 3);
});

test("nine clean reads is not ten", async () => {
  const led = ledger();
  await standingOn(led, 2);
  await led.setWritesOptIn("owner", APP, true);
  for (let i = 0; i < 9; i++) await led.record(outcome(READ_THE_VERIFIER_SAW));
  assert.equal(await led.rung("owner", SIG, APP), 2);
  await led.record(outcome(READ_THE_VERIFIER_SAW));
  assert.equal(await led.rung("owner", SIG, APP), 3);
});

test("ten clean reads without the opt-in stay at rung 2 forever", async () => {
  const led = ledger();
  await standingOn(led, 2);
  for (let i = 0; i < 25; i++) await led.record(outcome(READ_THE_VERIFIER_SAW));
  assert.equal(
    await led.rung("owner", SIG, APP),
    2,
    "no amount of successful reading is consent to write",
  );
});

test("the opt-in itself completes the gate, without waiting for one more run", async () => {
  const led = ledger();
  await standingOn(led, 2);
  for (let i = 0; i < 10; i++) await led.record(outcome(READ_THE_VERIFIER_SAW));
  assert.equal(await led.rung("owner", SIG, APP), 2);
  await led.setWritesOptIn("owner", APP, true);
  assert.equal(await led.rung("owner", SIG, APP), 3);
});

test("a failed read is not a clean read", async () => {
  const led = ledger();
  await standingOn(led, 2);
  await led.setWritesOptIn("owner", APP, true);
  for (let i = 0; i < 5; i++) await led.record(outcome(READ_THE_VERIFIER_SAW));
  await led.record(outcome({ ok: false, failKind: "auth" }));
  for (let i = 0; i < 4; i++) await led.record(outcome(READ_THE_VERIFIER_SAW));
  assert.equal(await led.rung("owner", SIG, APP), 2, "nine clean reads and one failure");
  await led.record(outcome(READ_THE_VERIFIER_SAW));
  assert.equal(await led.rung("owner", SIG, APP), 3);
});

test("shadow reads at rung 1 are not banked toward the write gate", async () => {
  const led = ledger();
  await standingOn(led, 1);
  for (let i = 0; i < 10; i++) {
    await led.record(outcome({ ...READ_THE_VERIFIER_SAW, parity: true }));
  }
  await led.setWritesOptIn("owner", APP, true);
  // Runs 1-3 were shadow and bought rung 2. Only runs 4-10 were reads taken on
  // rung 2, so seven are banked and the write gate is three short — even though
  // ten successful reads happened.
  assert.equal(await led.rung("owner", SIG, APP), 2);
  const pair = await led.ladderState("owner", SIG, APP);
  assert.equal(pair?.clean_reads, 7);
});

// ---------------------------------------------------------------------------
// RUNG 3 -> 4: three confirmed writes with a verified effect
// ---------------------------------------------------------------------------

test("three verified writes promote assisted writes to auto writes", async () => {
  const led = ledger();
  await standingOn(led, 3);
  await led.record(outcome({ verifierResult: "verified" }));
  await led.record(outcome({ verifierResult: "verified" }));
  assert.equal(await led.rung("owner", SIG, APP), 3, "two is not three");
  await led.record(outcome({ verifierResult: "verified" }));
  assert.equal(await led.rung("owner", SIG, APP), 4);
});

test("a write nobody verified does not count toward auto writes", async () => {
  const led = ledger();
  await standingOn(led, 3);
  for (let i = 0; i < 5; i++) await led.record(outcome({ verifierResult: "unknown" }));
  assert.equal(
    await led.rung("owner", SIG, APP),
    3,
    "'unknown' means nobody looked; five writes nobody looked at are not evidence",
  );
});

test("a pair climbs at most one rung on one outcome", async () => {
  const led = ledger();
  await standingOn(led, 1);
  // Everything the 1->2 and the 2->3 gate could want, delivered at once.
  await led.setWritesOptIn("owner", APP, true);
  for (let i = 0; i < 12; i++) {
    await led.record(outcome({ ...READ_THE_VERIFIER_SAW, parity: true }));
  }
  // Runs 1-3 buy rung 2. Runs 4-12 are nine reads on rung 2 — one short of the
  // write gate. A pair that took two rungs on one outcome would be on 3 here
  // with a gate whose evidence was never collected.
  const pair = await led.ladderState("owner", SIG, APP);
  assert.equal(pair?.rung, 2);
  assert.equal(pair?.clean_reads, 9);
});

// ---------------------------------------------------------------------------
// DEMOTION
// ---------------------------------------------------------------------------

test("two consecutive API failures drop one rung and re-open shadow", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: false, failKind: "other", verifierResult: "unknown" }));
  assert.equal(await led.rung("owner", SIG, APP), 4, "one failure is not a pattern");
  await led.record(outcome({ ok: false, failKind: "other", verifierResult: "unknown" }));

  assert.equal(await led.earnedRung("owner", SIG, APP), 3, "dropped exactly one rung");
  assert.equal(
    await led.rung("owner", SIG, APP),
    1,
    "and routes as shadow until parity is proved again",
  );
  const pair = await led.ladderState("owner", SIG, APP);
  assert.equal(pair?.shadow_required, true);
});

test("a success between two failures means they are not consecutive", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: false, failKind: "other", verifierResult: "unknown" }));
  await led.record(outcome({ ok: true, verifierResult: "unknown" }));
  await led.record(outcome({ ok: false, failKind: "other", verifierResult: "unknown" }));
  assert.equal(await led.rung("owner", SIG, APP), 4);
});

test("a run the verifier refused does not LAUNDER two real failures", async () => {
  // The mirror of the auth-laundering leg below. A 200 whose effect the
  // verifier says did not happen — the tool answered, with the wrong answer —
  // is not evidence the tool works, so it may not hand the pair a clean slate
  // between two genuine failures. It is not a transport failure either, so it
  // does not ADD to the counter; invisible, exactly like an excused 401.
  //
  // Rung 2 rather than 4 on purpose: at rung 3+ an undeclared run is scored as
  // a write and one refusal demotes on its own, which would hide what this
  // leg is measuring.
  const led = ledger();
  await standingOn(led, 2);
  await led.record(outcome({ ok: false, failKind: "other" }));
  await led.record(outcome({ ok: true, verifierResult: "unverified" }));
  await led.record(outcome({ ok: false, failKind: "other" }));
  assert.equal(
    await led.earnedRung("owner", SIG, APP),
    1,
    "the two failures were consecutive; a wrong answer between them is not a success",
  );
});

test("a 401 is never a demotion, however many times it happens", async () => {
  const led = ledger();
  await standingOn(led, 4);
  for (let i = 0; i < 6; i++) {
    await led.record(outcome({ ok: false, failKind: "auth", failReason: "auth", verifierResult: "unknown" }));
  }
  assert.equal(
    await led.rung("owner", SIG, APP),
    4,
    "a token expiring is not the tool being wrong",
  );
  const [row] = await led.stats("owner", SIG, APP, "api", TOOL);
  assert.equal(row.last_fail_reason, "auth", "it is recorded, so the reconnect nudge can fire");
});

test("a 429 is never a demotion either", async () => {
  const led = ledger();
  await standingOn(led, 4);
  for (let i = 0; i < 6; i++) {
    await led.record(outcome({ ok: false, failKind: "rate", verifierResult: "unknown" }));
  }
  assert.equal(await led.rung("owner", SIG, APP), 4);
});

test("an auth failure does not LAUNDER two real failures into non-consecutive ones", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: false, failKind: "other", verifierResult: "unknown" }));
  await led.record(outcome({ ok: false, failKind: "auth", verifierResult: "unknown" }));
  await led.record(outcome({ ok: false, failKind: "other", verifierResult: "unknown" }));
  assert.equal(
    await led.earnedRung("owner", SIG, APP),
    3,
    "an excused failure is invisible to the counter, it does not reset it",
  );
});

test("one verifier mismatch on a write demotes immediately", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: true, verifierResult: "unverified" }));
  assert.equal(await led.earnedRung("owner", SIG, APP), 3);
  assert.equal(await led.rung("owner", SIG, APP), 1);
});

test("a write whose parity is false demotes even though the call succeeded", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: true, parity: false, verifierResult: "unknown" }));
  assert.equal(await led.earnedRung("owner", SIG, APP), 3);
});

test("a write the verifier could not check is not a mismatch", async () => {
  const led = ledger();
  await standingOn(led, 4);
  for (let i = 0; i < 3; i++) await led.record(outcome({ ok: true, verifierResult: "unknown" }));
  assert.equal(
    await led.rung("owner", SIG, APP),
    4,
    "demoting on a no-verdict punishes the capability for the verifier being down",
  );
});

test("browser-hand failures never demote the API hand", async () => {
  const led = ledger();
  await standingOn(led, 4);
  for (let i = 0; i < 5; i++) {
    await led.record(outcome({
      hand: "browser",
      tool_slug: "chrome",
      ok: false,
      failKind: "other",
      verifierResult: "unverified",
    }));
  }
  assert.equal(
    await led.rung("owner", SIG, APP),
    4,
    "a flaky website must not take the API hand away",
  );
});

test("a demotion at rung 0 floors there instead of going negative", async () => {
  const led = ledger();
  await standingOn(led, 0);
  await led.record(outcome({ ok: false, failKind: "other" }));
  await led.record(outcome({ ok: false, failKind: "other" }));
  assert.equal(await led.rung("owner", SIG, APP), 0);
  assert.equal(await led.earnedRung("owner", SIG, APP), 0);
});

test("a pair demoted to browser-only is not trapped there", async () => {
  const led = ledger();
  await led.setConnection("owner", APP, true);
  await led.noteCandidate(candidate({ match_verdict: "yes" }));
  assert.equal(await led.rung("owner", SIG, APP), 1);

  await led.record(outcome({ ok: true, parity: true }));
  await led.record(outcome({ ok: false, failKind: "other" }));
  await led.record(outcome({ ok: false, failKind: "other" }));
  assert.equal(await led.earnedRung("owner", SIG, APP), 0, "demoted out of shadow");

  // The next run of this capability goes through the browser, and the rung-0
  // gate is still satisfied — the judge vouched and the app is connected — so
  // the pair re-enters shadow instead of being stranded on the browser forever.
  await led.record(outcome({ hand: "browser", tool_slug: "chrome", ok: true }));
  assert.equal(await led.rung("owner", SIG, APP), 1);
  const pair = await led.ladderState("owner", SIG, APP);
  assert.equal(pair?.parity_streak, 0, "the demotion still cost it the streak");
});

test("while shadow is re-opened, a disagreeing run is a read, not a failed write", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: true, verifierResult: "unverified" }));
  assert.equal(await led.earnedRung("owner", SIG, APP), 3);
  assert.equal(await led.rung("owner", SIG, APP), 1, "the router is being told to shadow");

  // Scored against the earned rung this would read as a second failed write and
  // demote the pair again for doing exactly what it was told to do.
  await led.record(outcome({ ok: true, parity: false }));
  assert.equal(await led.earnedRung("owner", SIG, APP), 3);
  const pair = await led.ladderState("owner", SIG, APP);
  assert.equal(pair?.parity_streak, 0);
  assert.equal(pair?.parity_mismatches, 1);
});

test("re-opened shadow closes on three fresh parity matches, not on time", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: true, verifierResult: "unverified" }));
  assert.equal(await led.rung("owner", SIG, APP), 1);

  const match = { ok: true, parity: true, verifierResult: "verified" } as Partial<LedgerOutcome>;
  await led.record(outcome(match));
  await led.record(outcome(match));
  assert.equal(await led.rung("owner", SIG, APP), 1, "two matches do not re-open the API hand");

  await led.record(outcome(match));
  assert.equal(await led.rung("owner", SIG, APP), 3, "the earned rung is handed back, not rung 4");
  assert.equal(await led.earnedRung("owner", SIG, APP), 3);
});

test("a demotion clears the counters it fell with", async () => {
  const led = ledger();
  await standingOn(led, 2);
  await led.setWritesOptIn("owner", APP, true);
  for (let i = 0; i < 9; i++) await led.record(outcome(READ_THE_VERIFIER_SAW));
  await led.record(outcome({ ok: false, failKind: "other" }));
  await led.record(outcome({ ok: false, failKind: "other" }));
  const pair = await led.ladderState("owner", SIG, APP);
  assert.equal(pair?.rung, 1);
  assert.equal(pair?.clean_reads, 0, "nine reads gathered on rung 2 do not survive the fall");
});

// ---------------------------------------------------------------------------
// THE GLOBAL PRIOR — a rung travels, a permission does not
// ---------------------------------------------------------------------------

/** A veteran who earned rung 2 the long way, so the global prior has something
 *  real behind it rather than a hand-set number. */
async function veteranAtRungTwo(led: InMemoryLedger, user = "veteran"): Promise<void> {
  await led.setConnection(user, APP, true);
  await led.noteCandidate(candidate({ user_id: user, match_verdict: "yes" }));
  for (let i = 0; i < 3; i++) {
    await led.record(outcome({
      user_id: user,
      ok: true,
      parity: true,
      verifierResult: "verified",
      ms: 250,
      cost: 0.002,
    }));
  }
  assert.equal(await led.rung(user, SIG, APP), 2);
}

/** The same veteran, all the way up, every rung paid for at its own gate. It is
 *  written the long way because a hand-set rung is the one thing that must NOT
 *  travel to strangers, so a test about what travels cannot start with one. */
async function veteranAtRungFour(led: InMemoryLedger, user = "veteran"): Promise<void> {
  await veteranAtRungTwo(led, user);
  await led.setWritesOptIn(user, APP, true);
  for (let i = 0; i < LADDER.CLEAN_READS_FOR_ASSISTED_WRITES; i++) {
    await led.record(outcome({ user_id: user, ok: true, verifierResult: "verified", side_effect: "read" }));
  }
  assert.equal(await led.rung(user, SIG, APP), 3, "ten verified reads plus the opt-in");
  for (let i = 0; i < LADDER.CONFIRMED_WRITES_FOR_AUTO_WRITES; i++) {
    await led.record(outcome({ user_id: user, ok: true, verifierResult: "verified", side_effect: "write" }));
  }
  assert.equal(await led.rung(user, SIG, APP), 4, "three writes the verifier watched land");
}

test("an operator's hand-set rung is not exported to strangers as evidence", async () => {
  // globalRung's own comment says it reports "the highest rung anyone has
  // EARNED", and setRung is documented as an operator override or a test. An
  // override is the absence of evidence, not evidence.
  //
  // THE FAILURE THIS PREVENTS: somebody stands a pair up by hand to get past
  // the write-ladder gap RESULTS.md FINDING 1 describes, and every other user
  // who has connected that app and opted into writes silently starts at
  // assisted writes on a capability nobody ever proved once.
  const led = ledger();
  await veteranAtRungTwo(led);
  await led.setRung("veteran", SIG, APP, 4);

  await led.setConnection("newbie", APP, true);
  await led.setWritesOptIn("newbie", APP, true);
  assert.equal(
    await led.rung("newbie", SIG, APP),
    2,
    "the newbie may inherit the rung the veteran EARNED, and not the one typed in",
  );
  assert.equal(await led.globalRung(SIG, APP), 2);
  assert.equal(
    await led.rung("veteran", SIG, APP),
    4,
    "the override still stands for the pair it was applied to",
  );
});

test("a new user inherits the global rung once they connect the app themselves", async () => {
  const led = ledger();
  await veteranAtRungTwo(led);

  assert.equal(await led.rung("newbie", SIG, APP), 0, "no connection of their own, no inheritance");
  await led.setConnection("newbie", APP, true);
  assert.equal(await led.rung("newbie", SIG, APP), 2);
});

test("inheriting a rung never inherits somebody else's write consent", async () => {
  const led = ledger();
  // The veteran earns rung 4 the long way, so the thing on offer really is the
  // top of the ladder. Standing them up with setRung would prove nothing now
  // that an override is not exportable evidence.
  await veteranAtRungFour(led);

  await led.setConnection("newbie", APP, true);
  assert.equal(
    await led.writesOptedIn("newbie", APP),
    false,
    "consent is per person and is never aggregated",
  );
  assert.equal(
    await led.rung("newbie", SIG, APP),
    2,
    "the read half of the ladder is all an unconsenting user may inherit",
  );
});

test("a new user's writes start at ASSISTED, never at auto, however global rung 4 is", async () => {
  const led = ledger();
  await veteranAtRungFour(led);
  assert.equal(await led.globalRung(SIG, APP), 4, "there really is a rung 4 on offer");

  await led.setConnection("newbie", APP, true);
  await led.setWritesOptIn("newbie", APP, true);
  assert.equal(
    await led.rung("newbie", SIG, APP),
    3,
    "auto writes are earned on your own account or not at all",
  );
});

test("an inherited rung is not re-exported as if it were evidence", async () => {
  const led = ledger();
  await veteranAtRungTwo(led);
  await led.setConnection("newbie", APP, true);
  await led.record(outcome({ user_id: "newbie", hand: "browser", tool_slug: "chrome", ok: true }));

  assert.equal(await led.rung("newbie", SIG, APP), 2, "newbie is standing on a prior");
  assert.equal(
    await led.globalRung(SIG, APP, "veteran"),
    0,
    "without the veteran there is no evidence — a prior must not become one",
  );
});

test("a user's own ladder event outranks the global prior from then on", async () => {
  const led = ledger();
  await veteranAtRungTwo(led);
  await led.setConnection("newbie", APP, true);
  assert.equal(await led.rung("newbie", SIG, APP), 2);

  await led.record(outcome({ user_id: "newbie", ok: false, failKind: "other" }));
  await led.record(outcome({ user_id: "newbie", ok: false, failKind: "other" }));
  assert.equal(await led.earnedRung("newbie", SIG, APP), 1, "their own failures moved them");

  await led.setRung("veteran", SIG, APP, 4);
  assert.equal(
    await led.earnedRung("newbie", SIG, APP),
    1,
    "somebody else's rung 4 must not undo this user's demotion",
  );
});

test("losing the connection takes the inherited rung with it", async () => {
  const led = ledger();
  await veteranAtRungTwo(led);
  await led.setConnection("newbie", APP, true);
  assert.equal(await led.rung("newbie", SIG, APP), 2);
  await led.setConnection("newbie", APP, false);
  assert.equal(await led.rung("newbie", SIG, APP), 0);
});

test("prior() hands back the global aggregate, marked, when the user has no history", async () => {
  const led = ledger();
  await veteranAtRungTwo(led);
  await led.setConnection("newbie", APP, true);

  const rows = await led.prior("newbie", SIG, APP);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].user_id, "*", "nothing may mistake other people's runs for the owner's");
  assert.equal(rows[0].n, 3);
  assert.equal(rows[0].successes, 3);
  assert.equal(rows[0].rung, 2, "already capped by this user's own connection and consent");
  assert.equal(rows[0].cost_usd_total, 0.006);
});

test("prior() stops handing back the global row the moment the user has their own", async () => {
  const led = ledger();
  await veteranAtRungTwo(led);
  await led.setConnection("newbie", APP, true);
  await led.record(outcome({ user_id: "newbie", ok: true, ms: 10 }));
  const rows = await led.prior("newbie", SIG, APP);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].user_id, "newbie");
});

test("prior() is empty when nobody anywhere has ever run this capability", async () => {
  const led = ledger();
  assert.deepEqual(await led.prior("owner", SIG, APP), []);
});

// ---------------------------------------------------------------------------
// THE OTHER THREE TABLES
// ---------------------------------------------------------------------------

test("api_candidates are ordered by the vendor score and keep their first sighting", async () => {
  const led = ledger();
  await led.noteCandidate(candidate({ tool_slug: "LOW", match_score: 0.2, first_seen_at: T0 }));
  await led.noteCandidate(candidate({ tool_slug: "HIGH", match_score: 0.9, first_seen_at: T0 }));
  await led.noteCandidate(candidate({ tool_slug: "LOW", match_score: 0.25, first_seen_at: T0 + 9999 }));

  const rows = await led.candidates("owner", SIG);
  assert.deepEqual(rows.map((r) => r.tool_slug), ["HIGH", "LOW"]);
  assert.equal(rows[1].match_score, 0.25, "the newest score wins");
  assert.equal(rows[1].first_seen_at, T0, "re-searching must not reset the clock the nudge reads");
});

test("api_candidates keep the verdict, so 'no tool' and 'no vouch' stay distinguishable", async () => {
  const led = ledger();
  await led.noteCandidate(candidate({ tool_slug: "MAYBE", match_verdict: "unclear" }));
  const rows = await led.candidates("owner", SIG);
  assert.equal(rows[0].match_verdict, "unclear");
  assert.equal(await led.rung("owner", SIG, APP), 0);
});

test("candidates for one signature never leak into another's list", async () => {
  const led = ledger();
  await led.noteCandidate(candidate({ signature_hash: "sig_a", tool_slug: "A" }));
  await led.noteCandidate(candidate({ signature_hash: "sig_ab", tool_slug: "B" }));
  const rows = await led.candidates("owner", "sig_a");
  assert.deepEqual(rows.map((r) => r.tool_slug), ["A"], "a prefix scan must match whole segments");
});

test("connect_nudges counts the tasks that would have used the app", async () => {
  const led = ledger();
  await led.countMissedTask("owner", APP);
  await led.countMissedTask("owner", APP);
  const row = await led.noteNudge("owner", APP, { state: "sent", channel: "sms", sent_at: T0 });
  assert.equal(row.tasks_that_would_have_used_it, 2);
  assert.equal(row.state, "sent");
  assert.equal(row.channel, "sms");
  assert.equal(row.sent_at, T0);
  assert.equal((await led.nudges("owner")).length, 1);
});

test("recording a shadow run stores the row and moves nothing", async () => {
  const led = ledger();
  await standingOn(led, 1);
  const run: ShadowRun = {
    run_id: "r1",
    step_id: "s1",
    api_result_hash: "a",
    browser_result_hash: "b",
    parity: true,
    verifier_notes: "the draft exists in Sent",
    api_ms: 300,
    browser_ms: 5200,
    api_cost: 0.001,
    browser_cost: 0.02,
  };
  for (const i of [1, 2, 3]) {
    await led.recordShadowRun({ ...run, run_id: `r${i}` }, {
      user_id: "owner",
      signature_hash: SIG,
      app: APP,
    });
  }
  assert.equal((await led.shadowRuns()).length, 3);
  assert.equal(
    await led.rung("owner", SIG, APP),
    1,
    "if the row moved the streak too, a router that logs both promotes on two runs",
  );
});

test("the rung column on capability_stats is the same number rung() returns", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: true, verifierResult: "verified" }));
  let rows = await led.stats("owner", SIG, APP);
  assert.equal(rows[0].rung, 4);

  await led.record(outcome({ ok: true, verifierResult: "unverified" }));
  rows = await led.stats("owner", SIG, APP);
  assert.equal(await led.rung("owner", SIG, APP), 1);
  assert.equal(rows[0].rung, 1, "the table and the method must never tell a router two stories");
});

// ---------------------------------------------------------------------------
// THE STORAGE SEAM AND LAW 1
// ---------------------------------------------------------------------------

test("every table goes through LedgerStore, so week 2 can swap in D1", async () => {
  const puts: string[] = [];
  class CountingTable<Row> extends MemoryTable<Row> {
    #name: string;
    constructor(name: string) {
      super();
      this.#name = name;
    }
    async put(key: string, row: Row): Promise<void> {
      puts.push(this.#name);
      await super.put(key, row);
    }
  }
  const store: LedgerStore = {
    capability_stats: new CountingTable("capability_stats"),
    api_candidates: new CountingTable("api_candidates"),
    connect_nudges: new CountingTable("connect_nudges"),
    shadow_runs: new CountingTable("shadow_runs"),
    ladder_state: new CountingTable("ladder_state"),
    app_consent: new CountingTable("app_consent"),
    latency_samples: new CountingTable("latency_samples"),
  };
  const led = new InMemoryLedger({ store, now: () => T0 });

  await led.setConnection("owner", APP, true);
  await led.noteCandidate(candidate({ match_verdict: "yes" }));
  await led.record(outcome({ parity: true }));
  await led.countMissedTask("owner", "slack");

  for (const table of [
    "capability_stats",
    "api_candidates",
    "connect_nudges",
    "ladder_state",
    "app_consent",
    "latency_samples",
  ]) {
    assert.ok(puts.includes(table), `${table} was written outside the store seam`);
  }
  assert.equal(await led.rung("owner", SIG, APP), 1);
});

test("memoryStore() gives a working default store", async () => {
  const led = new InMemoryLedger({ store: memoryStore(), now: () => T0 });
  await led.record(outcome());
  assert.equal((await led.stats("owner", SIG, APP)).length, 1);
});

test("asErrorKind matches the closed set exactly and never searches prose", () => {
  assert.equal(asErrorKind("auth"), "auth");
  assert.equal(asErrorKind("rate"), "rate");
  assert.equal(asErrorKind("schema"), "schema");
  assert.equal(asErrorKind(undefined), "other");
  // Every one of these CONTAINS a word a substring rule would fire on. None of
  // them is the provider declaring a kind, so none of them is excused.
  assert.equal(asErrorKind("401 Unauthorized"), "other");
  assert.equal(asErrorKind("auth failed"), "other");
  assert.equal(asErrorKind("not authorized to exceed your rate limit"), "other");
});

test("prose in failReason is never laundered into an excuse", async () => {
  const led = ledger();
  await standingOn(led, 4);
  await led.record(outcome({ ok: false, failReason: "401 Unauthorized: token expired" }));
  await led.record(outcome({ ok: false, failReason: "401 Unauthorized: token expired" }));
  assert.equal(
    await led.earnedRung("owner", SIG, APP),
    3,
    "the carve-out is claimed with failKind, not guessed at from a sentence",
  );

  const led2 = ledger();
  await standingOn(led2, 4);
  const declared = { ok: false, failKind: "auth", failReason: "401 Unauthorized: token expired" };
  await led2.record(outcome(declared as Partial<LedgerOutcome>));
  await led2.record(outcome(declared as Partial<LedgerOutcome>));
  assert.equal(await led2.earnedRung("owner", SIG, APP), 4, "declared, it is excused");
});

test("no app name or verb decides anything: the same ladder runs for any app", async () => {
  // The point of the spike. Two capabilities with nothing in common but their
  // outcomes reach rung 2 by the identical path, and an app nobody has heard of
  // is not disadvantaged by not being on a list.
  for (const [sig, app, tool] of [
    ["sig_email_send", "gmail", "GMAIL_SEND_EMAIL"],
    ["sig_wibble", "some-app-nobody-hardcoded", "WIBBLE_DO_THING"],
  ]) {
    const led = ledger();
    await led.setConnection("owner", app, true);
    await led.noteCandidate(candidate({
      signature_hash: sig,
      app,
      tool_slug: tool,
      match_verdict: "yes",
    }));
    assert.equal(await led.rung("owner", sig, app), 1);
    for (let i = 0; i < 3; i++) {
      await led.record(outcome({
        signature_hash: sig,
        app,
        tool_slug: tool,
        parity: true,
        verifierResult: "verified",
      }));
    }
    assert.equal(await led.rung("owner", sig, app), 2, `${app} climbed on outcomes alone`);
  }
});

test("the ladder constants are the ones the spec asked for", () => {
  assert.equal(LADDER.PARITY_MATCHES_FOR_API_READS, 3);
  assert.equal(LADDER.CLEAN_READS_FOR_ASSISTED_WRITES, 10);
  assert.equal(LADDER.CONFIRMED_WRITES_FOR_AUTO_WRITES, 3);
  assert.equal(LADDER.CONSECUTIVE_API_FAILURES_TO_DEMOTE, 2);
});
