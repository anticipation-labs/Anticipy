// AN EVICTED STEP MUST NOT VOTE ON WHICH HAND IS FASTER.
//
// The Observer's store is capped, so a step whose trace was thrown away
// summarizes to `duration_ms: 0` — byte-identical to a step where nothing ever
// happened. `browserOutcome` files that as the browser hand's row, and rule 5
// prefers the faster hand. So a silent eviction does not merely lose a row: it
// files "the browser finished instantly" on evidence nobody collected, and the
// ladder then campaigns for the API hand on the strength of it.
//
// THIS FILE EXISTS BECAUSE THE FIX SHIPPED WITHOUT IT. `browserOutcome` was
// wired to ask `wasEvicted` and to set `unmeasured`, and the ledger was taught
// to skip unmeasured latency samples — and an adversarial pass then pointed out
// that `grep -rn unmeasured test/` returned nothing at all. The leg that was
// supposed to certify the wiring is a substring scan of shipped source, which a
// mention satisfies. A guard with no behavioural test is one careless edit from
// being decoration, so here is the behaviour.
//
// Run: node --experimental-strip-types --test test/unmeasured.test.ts
import test from "node:test";
import assert from "node:assert/strict";

import { createObserver, MAX_RETAINED_STEPS } from "../src/observer.ts";
import type { RequestEvent } from "../src/observer.ts";
import { browserOutcome } from "../src/index.ts";
import { InMemoryLedger } from "../src/ledger.ts";
import { makeSignature } from "../src/signature.ts";
import type { CapabilitySignature, UserCtx } from "../src/contract.ts";

const OWNER = "unmeasured-owner";
const APP = "gmail";

function req(runId: string, stepId: string, at: number, url: string): RequestEvent {
  return {
    kind: "request",
    run_id: runId,
    step_id: stepId,
    method: "GET",
    url,
    status: 200,
    at,
    duration_ms: 10,
  };
}

const SIG: CapabilitySignature = makeSignature({
  verb: "read",
  object: "email",
  inputs: { query: "from:alex" },
  expected_effect: "the last email from Alex is known",
  side_effect: "read",
});

const ctx = (now: number): UserCtx => ({ userId: OWNER, deviceOnline: true, now });

/** Observe one step, then bury it under the cap so its trace is gone. */
function buriedObserver() {
  const observer = createObserver();
  observer.observe(req("run-1", "buried", 1_000, "https://google.com/x"));
  observer.observe(req("run-1", "buried", 13_000, "https://google.com/y"));
  for (let i = 1; i <= MAX_RETAINED_STEPS; i += 1) {
    observer.observe(req("run-1", `filler-${i}`, 20_000 + i, "https://stripe.com/x"));
  }
  return observer;
}

// ---------------------------------------------------------------------------
// (a) THE ROW. An evicted step says so; a measured one does not.
// ---------------------------------------------------------------------------

test("an evicted browser step files no duration and says it was unmeasured", () => {
  const observer = buriedObserver();
  assert.equal(observer.wasEvicted("run-1", "buried"), true, "precondition: the trace is gone");

  const outcome = browserOutcome({
    sig: SIG, ctx: ctx(30_000), app: APP, observer,
    runId: "run-1", stepId: "buried", ok: true, verifierResult: "verified", at: 30_000,
  });

  assert.equal(outcome.unmeasured, true,
    "the row must say the duration is missing, not present-and-zero");
  assert.equal(outcome.ms, 0);
  assert.equal(outcome.ok, true, "the step still HAPPENED — only its clock was lost");
  assert.equal(outcome.hand, "browser");
});

test("a measured browser step carries its real duration and is NOT flagged — the control", () => {
  // Without this, setting `unmeasured` unconditionally would satisfy the leg
  // above while destroying every latency number in the system.
  const observer = createObserver();
  observer.observe(req("run-2", "live", 1_000, "https://google.com/x"));
  observer.observe(req("run-2", "live", 13_000, "https://google.com/y"));

  const outcome = browserOutcome({
    sig: SIG, ctx: ctx(20_000), app: APP, observer,
    runId: "run-2", stepId: "live", ok: true, verifierResult: "verified", at: 20_000,
  });

  assert.equal(outcome.unmeasured, undefined, "a step we timed is not unmeasured");
  assert.ok(outcome.ms > 0, `a real duration survives, got ${outcome.ms}`);
});

// ---------------------------------------------------------------------------
// (b) THE LEDGER. The lost clock changes no percentile; the run still counts.
// ---------------------------------------------------------------------------

test("an unmeasured run contributes no latency sample, so it cannot make a hand look fast", async () => {
  const ledger = new InMemoryLedger();
  const base = {
    user_id: OWNER, signature_hash: SIG.signature_hash, app: APP,
    hand: "browser" as const, tool_slug: "browser",
    ok: true, verifierResult: "verified" as const, cost: 0,
    side_effect: "read" as const,
  };

  // EXACTLY ONE honest sample, and that is deliberate. An earlier version of
  // this test used two, and it proved nothing: percentile is nearest-rank, so
  // with [0, 12000, 12000] the median is still 12000 and deleting the ledger's
  // exclusion left the test green. Mutation testing caught it. With one honest
  // sample the bug is visible — [0, 12000] has rank-1 median 0 — so the
  // assertion below can only pass if the zero really was excluded.
  await ledger.record({ ...base, ms: 12_000, at: 1 });

  const before = (await ledger.prior(OWNER, SIG.signature_hash, APP))
    .find((r) => r.hand === "browser");
  assert.equal(before?.p50_ms, 12_000, "precondition: p50 is the real number");

  // Now an evicted one. Its 0 is a lost measurement, and if it lands in the
  // sample the browser hand's p50 collapses on evidence nobody gathered.
  await ledger.record({ ...base, ms: 0, unmeasured: true, at: 2 });

  const after = (await ledger.prior(OWNER, SIG.signature_hash, APP))
    .find((r) => r.hand === "browser");
  assert.equal(after?.p50_ms, 12_000, "the lost clock must not move p50");
  assert.equal(after?.p95_ms, 12_000, "nor p95");
  assert.equal(after?.n, 2, "but the run still happened and still counts toward n");
  assert.equal(after?.successes, 2, "and toward successes — it succeeded");
});

test("a measured 0 is still a sample — only the UNMEASURED flag excludes one", async () => {
  // The exclusion keys off the flag, never off the value. A step that genuinely
  // took under a millisecond is real data, and dropping every zero would let a
  // fast hand be silently under-counted.
  const ledger = new InMemoryLedger();
  const base = {
    user_id: OWNER, signature_hash: SIG.signature_hash, app: "notion",
    hand: "api" as const, tool_slug: "NOTION_FETCH",
    ok: true, verifierResult: "verified" as const, cost: 0,
    side_effect: "read" as const,
  };
  await ledger.record({ ...base, ms: 400, at: 1 });
  await ledger.record({ ...base, ms: 0, at: 2 });

  const row = (await ledger.prior(OWNER, SIG.signature_hash, "notion"))
    .find((r) => r.hand === "api");
  assert.equal(row?.n, 2);
  assert.equal(row?.p50_ms, 0, "an honest zero IS in the sample and drags p50 down");
});

// ---------------------------------------------------------------------------
// (c) THE WIRING, as behaviour rather than as a substring.
// ---------------------------------------------------------------------------

test("browserOutcome releases the step it just read", () => {
  // The other half of the same edit: browserOutcome is the one caller that
  // KNOWS a browser step is over, so it summarizes-and-forgets. Without this
  // every finished step's trace stays in the service worker for the session.
  const observer = createObserver();
  observer.observe(req("run-3", "done", 1_000, "https://notion.so/x"));
  assert.deepEqual(observer.summarize("run-3", "done").hosts, ["notion.so"],
    "precondition: the trace is there");

  browserOutcome({
    sig: SIG, ctx: ctx(9_000), app: "notion", observer,
    runId: "run-3", stepId: "done", ok: true, verifierResult: "verified", at: 9_000,
  });

  assert.deepEqual(observer.summarize("run-3", "done").hosts, [],
    "the trace is released once the row is filed");
  assert.equal(observer.wasEvicted("run-3", "done"), false,
    "and released is not the same fact as evicted — a healthy release is not a lost clock");
});
