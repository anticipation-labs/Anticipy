// ROUTER TESTS — the five rules as BEHAVIOUR, plus the one leg that behaviour
// cannot catch.
//
// Everything here runs with no network, no API key and no account: the
// Provider, Ledger and MatchJudge are local stubs implementing the contract's
// interfaces. They are stubs and not imports on purpose — the real
// provider_fake.ts and ledger.ts are being written in parallel, and a test that
// depends on another agent's file in flight tests two things and pins neither.
//
// THE LEG THAT IS NOT A BEHAVIOUR TEST is `router.ts names no app`. A hardcoded
// app name is invisible to every behaviour test in this file: the router would
// keep passing all of them and be wrong for exactly one owner, on exactly one
// app, in production. So this suite reads the router's own source back and
// fails on a known app name. HARNESS-LAWS law 1 permits pattern matching in
// "gates and evals — deterministic tests of outcomes", which is what that leg
// is. It is also the only place in this spike where a list of app names is
// allowed to exist.

import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

import {
  createRouter,
  fallbackAfterApiFailure,
  handScore,
  wilsonLowerBound,
  DEFAULT_COST_WEIGHT,
} from "../src/router.ts";
import type { ApiFailure, RouteDecision } from "../src/router.ts";
import { signatureHash } from "../src/signature.ts";
import type {
  CapabilitySignature,
  CapabilityStats,
  ConnectedApp,
  Ledger,
  MatchAnswer,
  MatchJudge,
  Provider,
  Rung,
  SideEffect,
  ToolCandidate,
  UserCtx,
  Verb,
} from "../src/contract.ts";

// ---------------------------------------------------------------------------
// Fixtures. Deliberately meaningless app strings.
// ---------------------------------------------------------------------------
// The apps here are called "app-alpha" and "app-beta" rather than anything real
// so that a router branch keyed on a real name could not be satisfied by these
// tests even by accident — and so that swapping the strings (see the
// app-blindness test) is a total substitution.
const APP_A = "app-alpha";
const APP_B = "app-beta";

// EVERY SIGNATURE IN THIS FILE CARRIES A HASH THIS PROCESS DERIVED.
//
// These fixtures used to carry hand-written keys — "sig-1", "sig-w", "sig-i".
// That made every routing test pass an object the router could not have
// trusted: `decide` verifies the hash before it reads a rung off it, because a
// signature that crossed a process boundary can carry a hash chosen by whoever
// last held it, and a swapped hash is how a delete inherits a read's rung.
//
// With fake keys the whole suite was testing a shape the router now refuses,
// so it would have gone green while proving nothing about production. The
// factory derives instead. `hashFor` is how a test that needs to PAIR a
// signature with a ledger row gets the same key both sides.
function sig(over: Partial<CapabilitySignature> = {}): CapabilitySignature {
  const { signature_hash: _ignored, ...rest } = over as Record<string, unknown>;
  const base = {
    app_hint: null,
    verb: "read" as Verb,
    object: "thing",
    inputs: { id: 1 },
    expected_effect: "the thing is known",
    side_effect: "read" as SideEffect,
    account_hint: null,
    signature_hash: "",
    ...rest,
  } as CapabilitySignature;
  return { ...base, signature_hash: signatureHash(base) };
}

/** The ledger key for a signature shaped like `over` — the same value `sig`
 *  will put on the object, so a fixture and its stats row agree. */
function hashFor(over: Partial<CapabilitySignature> = {}): string {
  return sig(over).signature_hash;
}

const H_READ = hashFor();
const H_WRITE = hashFor({ verb: "send", side_effect: "write" });
const H_IRREVERSIBLE = hashFor({ verb: "pay", side_effect: "irreversible" });

function candidate(over: Partial<ToolCandidate> = {}): ToolCandidate {
  return {
    toolSlug: "tool-1",
    app: APP_A,
    score: 0.9,
    schema: {},
    description: "does the thing",
    ...over,
  };
}

function connection(over: Partial<ConnectedApp> = {}): ConnectedApp {
  return {
    app: APP_A,
    accountId: "acct-1",
    label: "the account",
    scopes: [],
    status: "active",
    ...over,
  };
}

function stats(over: Partial<CapabilityStats> = {}): CapabilityStats {
  return {
    user_id: "u1",
    signature_hash: H_READ,
    app: APP_A,
    hand: "api",
    tool_slug: "tool-1",
    n: 0,
    successes: 0,
    p50_ms: 0,
    p95_ms: 0,
    cost_usd_total: 0,
    rung: 0 as Rung,
    last_fail_reason: "",
    last_run_at: 0,
    ...over,
  };
}

function ctx(over: Partial<UserCtx> = {}): UserCtx {
  return { userId: "u1", deviceOnline: true, now: 1_700_000_000_000, ...over };
}

// ---------------------------------------------------------------------------
// Stubs.
// ---------------------------------------------------------------------------
interface Rig {
  candidates?: ToolCandidate[];
  connections?: ConnectedApp[];
  verdicts?: Record<string, MatchAnswer["verdict"]>;
  judgeThrows?: boolean;
  searchThrows?: boolean;
  connectionsThrow?: boolean;
  rung?: Rung;
  optedIn?: boolean;
  prior?: CapabilityStats[];
  ledgerThrows?: boolean;
  /** The judge answers this many questions and then goes down. `judgeThrows`
   *  kills it before the first answer; this kills it after a verdict has
   *  already been given, which is a different state and the router has to tell
   *  them apart. */
  judgeThrowsAfter?: number;
}

interface Built {
  router: ReturnType<typeof createRouter>;
  asked: ToolCandidate[];
  searchOpts: { connectedOnly: boolean; limit: number }[];
}

function build(rig: Rig): Built {
  const asked: ToolCandidate[] = [];
  const searchOpts: { connectedOnly: boolean; limit: number }[] = [];
  const all = rig.candidates ?? [candidate()];
  const conns = rig.connections ?? [connection()];

  const provider: Provider = {
    name: "fake",
    async search(_s, _u, opts) {
      searchOpts.push(opts);
      if (rig.searchThrows) throw new Error("vendor down");
      const connectedApps = new Set(conns.filter((c) => c.status === "active").map((c) => c.app));
      const pool = opts.connectedOnly ? all.filter((c) => connectedApps.has(c.app)) : all;
      return pool.slice(0, opts.limit);
    },
    async connections() {
      if (rig.connectionsThrow) throw new Error("vendor down");
      return conns;
    },
    async connectLink() {
      return { url: "https://example.invalid/connect" };
    },
    async execute() {
      return { ok: true, ms: 1 };
    },
  };

  const judge: MatchJudge = {
    async matches(_s, c) {
      asked.push(c);
      if (rig.judgeThrows) throw new Error("judge unreachable");
      if (typeof rig.judgeThrowsAfter === "number" && asked.length > rig.judgeThrowsAfter) {
        throw new Error("judge unreachable");
      }
      return { verdict: rig.verdicts?.[c.toolSlug] ?? "yes", reason: "stub" };
    },
  };

  const ledger: Ledger = {
    async prior() {
      if (rig.ledgerThrows) throw new Error("ledger down");
      return rig.prior ?? [];
    },
    async record() {},
    async candidates() {
      return [];
    },
    async rung() {
      if (rig.ledgerThrows) throw new Error("ledger down");
      return rig.rung ?? (0 as Rung);
    },
    async setRung() {},
    async writesOptedIn() {
      if (rig.ledgerThrows) throw new Error("ledger down");
      return rig.optedIn === true;
    },
  };

  return { router: createRouter({ provider, judge, ledger }), asked, searchOpts };
}

async function decide(rig: Rig, s = sig(), c = ctx()): Promise<RouteDecision> {
  return await build(rig).router.decide(s, c);
}

// ===========================================================================
// RULE 5, part 1 — Wilson. Pinned against published values, not against itself.
// ===========================================================================
test("wilson: 1/1 is the textbook 0.2065, not 1.0", () => {
  assert.ok(Math.abs(wilsonLowerBound(1, 1) - 0.2065) < 0.0005, String(wilsonLowerBound(1, 1)));
});

test("wilson: 10/10 is the textbook 0.7225", () => {
  assert.ok(Math.abs(wilsonLowerBound(10, 10) - 0.7225) < 0.0005, String(wilsonLowerBound(10, 10)));
});

test("wilson: 2/2 is the textbook 0.3424", () => {
  assert.ok(Math.abs(wilsonLowerBound(2, 2) - 0.3424) < 0.0005, String(wilsonLowerBound(2, 2)));
});

test("wilson: 90/100 is the textbook 0.8256", () => {
  assert.ok(Math.abs(wilsonLowerBound(90, 100) - 0.8256) < 0.0005, String(wilsonLowerBound(90, 100)));
});

test("wilson: 0/10 is a positive-free bound, not NaN", () => {
  const lb = wilsonLowerBound(0, 10);
  assert.equal(Number.isFinite(lb), true);
  assert.equal(lb, 0);
});

test("wilson: n=0 is 0, never NaN — a NaN would silently decide every comparison", () => {
  assert.equal(wilsonLowerBound(0, 0), 0);
  assert.equal(wilsonLowerBound(3, 0), 0);
});

test("wilson: two lucky runs do not beat forty steady ones", () => {
  // The whole reason the raw rate is not used: 2/2 = 1.00 > 38/40 = 0.95.
  assert.ok(2 / 2 > 38 / 40);
  assert.ok(wilsonLowerBound(2, 2) < wilsonLowerBound(38, 40));
});

test("wilson: more evidence at the same rate raises the bound", () => {
  assert.ok(wilsonLowerBound(5, 5) < wilsonLowerBound(50, 50));
  assert.ok(wilsonLowerBound(9, 10) < wilsonLowerBound(90, 100));
});

// ===========================================================================
// RULE 5, part 2 — the hand score.
// ===========================================================================
test("handScore: latency and cost only ever subtract", () => {
  const clean = stats({ n: 40, successes: 40 });
  const slow = stats({ n: 40, successes: 40, p50_ms: 20_000 });
  const pricey = stats({ n: 40, successes: 40, cost_usd_total: 40 * 0.02 });
  assert.ok(handScore(slow) < handScore(clean));
  assert.ok(handScore(pricey) < handScore(clean));
});

test("handScore: cost is per RUN, so volume alone is not a penalty", () => {
  const few = stats({ n: 10, successes: 10, cost_usd_total: 10 * 0.01 });
  const many = stats({ n: 200, successes: 200, cost_usd_total: 200 * 0.01 });
  // Same price per call; the busier hand must not be punished for being busy.
  assert.ok(handScore(many) > handScore(few));
});

test("handScore: an unrun hand scores 0 rather than NaN or -Infinity", () => {
  assert.equal(handScore(null), 0);
  assert.equal(handScore(stats({ n: 0 })), 0);
});

test("handScore: cost weight is a dial, and 0 disables the cost term", () => {
  const pricey = stats({ n: 10, successes: 10, cost_usd_total: 10 });
  assert.ok(handScore(pricey, DEFAULT_COST_WEIGHT) < handScore(pricey, 0));
});

// ===========================================================================
// RULE 1 — the judge's "yes" is the only licence.
// ===========================================================================
test("rule 1: the same signature routes to the API on 'yes'", async () => {
  const d = await decide({ rung: 2 as Rung, prior: [stats({ n: 20, successes: 19 })] });
  assert.equal(d.hand, "api");
  assert.equal(d.tool?.toolSlug, "tool-1");
  assert.equal(d.accountId, "acct-1");
});

test("rule 1: the same signature routes to the browser on 'no'", async () => {
  const d = await decide({
    rung: 2 as Rung,
    prior: [stats({ n: 20, successes: 19 })],
    verdicts: { "tool-1": "no" },
  });
  assert.equal(d.hand, "browser");
  assert.equal(d.tool, undefined);
});

test("rule 1: 'unclear' is not a licence — the floor refuses without a verdict", async () => {
  const d = await decide({ rung: 4 as Rung, verdicts: { "tool-1": "unclear" } });
  assert.equal(d.hand, "browser");
});

test("rule 1: 'no-verdict' is not a licence", async () => {
  const d = await decide({ rung: 4 as Rung, verdicts: { "tool-1": "no-verdict" } });
  assert.equal(d.hand, "browser");
});

test("rule 1: an unreachable judge routes to the browser instead of throwing", async () => {
  const d = await decide({ rung: 4 as Rung, judgeThrows: true, prior: [stats({ n: 99, successes: 99 })] });
  assert.equal(d.hand, "browser");
  assert.equal(d.tool, undefined);
});

test("rule 1: an unreachable judge is asked once, not once per candidate", async () => {
  // Five timeouts inside a task the owner is watching is five times the wait
  // for the same answer.
  const rig = {
    rung: 4 as Rung,
    judgeThrows: true,
    candidates: [1, 2, 3, 4, 5].map((i) => candidate({ toolSlug: `tool-${i}` })),
  };
  const built = build(rig);
  await built.router.decide(sig(), ctx());
  assert.equal(built.asked.length, 1);
});

test("rule 1: an unreachable vendor routes to the browser, not to an exception", async () => {
  const d = await decide({ rung: 4 as Rung, searchThrows: true });
  assert.equal(d.hand, "browser");
});

test("rule 1: no candidates at all routes to the browser", async () => {
  const d = await decide({ rung: 4 as Rung, candidates: [] });
  assert.equal(d.hand, "browser");
});

test("rule 1: the FIRST 'yes' wins, and a 'no' above it does not stop the search", async () => {
  const d = await decide({
    rung: 2 as Rung,
    candidates: [
      candidate({ toolSlug: "tool-hi", score: 0.99 }),
      candidate({ toolSlug: "tool-lo", score: 0.10 }),
    ],
    verdicts: { "tool-hi": "no", "tool-lo": "yes" },
    prior: [stats({ n: 20, successes: 20, tool_slug: "tool-lo" })],
  });
  assert.equal(d.hand, "api");
  assert.equal(d.tool?.toolSlug, "tool-lo");
});

test("rule 1: the score orders the asking, it does not decide the match", async () => {
  const built = build({
    rung: 2 as Rung,
    candidates: [
      candidate({ toolSlug: "tool-lo", score: 0.10 }),
      candidate({ toolSlug: "tool-hi", score: 0.99 }),
    ],
    verdicts: { "tool-hi": "no", "tool-lo": "no" },
  });
  await built.router.decide(sig(), ctx());
  assert.deepEqual(built.asked.map((c) => c.toolSlug), ["tool-hi", "tool-lo"]);
});

test("rule 1: at most five candidates reach the judge", async () => {
  const built = build({
    rung: 2 as Rung,
    candidates: Array.from({ length: 8 }, (_, i) => candidate({ toolSlug: `tool-${i}`, score: 1 - i / 100 })),
    verdicts: Object.fromEntries(Array.from({ length: 8 }, (_, i) => [`tool-${i}`, "no" as const])),
  });
  await built.router.decide(sig(), ctx());
  assert.equal(built.asked.length, 5);
});

test("rule 1: the connected pass and the whole-catalog pass are both made", async () => {
  const built = build({ rung: 2 as Rung });
  await built.router.decide(sig(), ctx());
  assert.deepEqual(built.searchOpts.map((o) => o.connectedOnly).sort(), [false, true]);
});

test("rule 1: a connected tool outranks a higher-scored tool in an app nobody connected", async () => {
  // Sorting the merged list purely by score would turn a step that could run
  // right now into a connect nudge plus a browser run.
  const d = await decide({
    rung: 2 as Rung,
    candidates: [
      candidate({ toolSlug: "tool-unconnected", app: APP_B, score: 0.99 }),
      candidate({ toolSlug: "tool-connected", app: APP_A, score: 0.20 }),
    ],
    prior: [stats({ n: 20, successes: 20, tool_slug: "tool-connected" })],
  });
  assert.equal(d.hand, "api");
  assert.equal(d.tool?.toolSlug, "tool-connected");
  assert.equal(d.nudgeApp, undefined);
});

// --- which of SEVERAL licensed candidates actually runs --------------------
// contract.ts's LAW1 note lets the vendor's score ORDER the candidates and
// forbids it to DECIDE. Once more than one candidate is licensed, "which tool
// touches the owner's account" is a decision, and returning on the first "yes"
// handed it to the score.
test("rule 1: among licensed candidates the gentler declared effect wins, whichever way the scores run", async () => {
  // The judge's verdicts are held fixed — it licenses both — and only the
  // vendor's numbers are reversed. If the number were deciding, one of these
  // two runs would put a tool that declares itself irreversible against the
  // owner's real account for a step he planned as an ordinary write.
  const run = async (destructive: number, gentle: number) =>
    await decide(
      {
        rung: 3 as Rung,
        optedIn: true,
        candidates: [
          candidate({ toolSlug: "tool-destructive", score: destructive, sideEffectHint: "irreversible" }),
          candidate({ toolSlug: "tool-gentle", score: gentle }),
        ],
        prior: [stats({ n: 20, successes: 20, signature_hash: H_WRITE, tool_slug: "tool-gentle" })],
      },
      writeSig(),
    );

  const scoreFavoursDestruction = await run(0.99, 0.1);
  const scoreFavoursGentle = await run(0.1, 0.99);
  assert.equal(scoreFavoursDestruction.tool?.toolSlug, "tool-gentle");
  assert.equal(scoreFavoursGentle.tool?.toolSlug, "tool-gentle");
  assert.equal(scoreFavoursDestruction.hand, scoreFavoursGentle.hand);
});

test("rule 1: the gentler candidate is put TO the judge, not merely preferred if it happens to be asked", async () => {
  // The half of the defect a decision assertion cannot see: the safer tool was
  // never shown to the judge at all, because the top-scored one had already
  // said yes.
  const built = build({
    rung: 3 as Rung,
    optedIn: true,
    candidates: [
      candidate({ toolSlug: "tool-destructive", score: 0.99, sideEffectHint: "irreversible" }),
      candidate({ toolSlug: "tool-gentle", score: 0.1 }),
    ],
  });
  await built.router.decide(writeSig(), ctx());
  assert.deepEqual(built.asked.map((c) => c.toolSlug), ["tool-destructive", "tool-gentle"]);
});

test("rule 1: a licence at the step's own floor stops the asking — nothing can be gentler", async () => {
  // `tightenSideEffect` only ever ratchets UP, so no later candidate can
  // declare a gentler effect than the step as planned. Asking on would spend
  // another model call inside a task the owner is waiting on to answer a
  // question whose answer cannot change.
  const built = build({
    rung: 2 as Rung,
    candidates: [candidate({ toolSlug: "tool-1" }), candidate({ toolSlug: "tool-2" })],
  });
  await built.router.decide(sig(), ctx());
  assert.deepEqual(built.asked.map((c) => c.toolSlug), ["tool-1"]);
});

test("rule 1: a judge that dies mid-search does not withdraw the licence it already gave", async () => {
  // The search keeps going only while something gentler is still possible. A
  // judge that falls over during that hunt is a property of the judge, not of
  // the candidate it already vouched for — and four more timeouts would land
  // on the same floor.
  const d = await decide(
    {
      rung: 3 as Rung,
      optedIn: true,
      judgeThrowsAfter: 1,
      candidates: [
        candidate({ toolSlug: "tool-destructive", score: 0.99, sideEffectHint: "irreversible" }),
        candidate({ toolSlug: "tool-gentle", score: 0.1 }),
      ],
    },
    writeSig(),
  );
  assert.equal(d.hand, "api");
  assert.equal(d.tool?.toolSlug, "tool-destructive");
  assert.equal(d.requiresConfirmation, true);
});

test("rule 1: the destructive top hit is refused and the gentle one is ROUTED, not merely ranked", async () => {
  // The shipped fixture's dangerous ordering, driven through the router rather
  // than asserted of the vendor: a tool that would destroy the thing outranks
  // the tool that would put it away, and BOTH declare themselves a plain write,
  // so the seatbelt sees no difference between them. Everything that stands
  // between the owner's mail and permanent destruction here is the verdict.
  // Anything that took the top hit over a threshold destroys on this fixture.
  const built = build({
    rung: 3 as Rung,
    optedIn: true,
    candidates: [
      candidate({ toolSlug: "tool-destroys", score: 0.91, sideEffectHint: "write" }),
      candidate({ toolSlug: "tool-puts-away", score: 0.89, sideEffectHint: "write" }),
    ],
    verdicts: { "tool-destroys": "no", "tool-puts-away": "yes" },
    prior: [stats({ n: 30, successes: 30, signature_hash: H_WRITE, tool_slug: "tool-puts-away" })],
  });
  const d = await built.router.decide(writeSig(), ctx());
  assert.equal(d.tool?.toolSlug, "tool-puts-away");
  assert.notEqual(d.tool?.toolSlug, "tool-destroys");
  assert.ok(
    built.asked.map((c) => c.toolSlug).includes("tool-destroys"),
    "the top-scored candidate must be put to the judge before it is passed over",
  );
});

test("rule 1: two licensed candidates that declare the SAME effect are still ordered by the score", async () => {
  // Stated as behaviour so nobody discovers it later. The seatbelt sees no
  // difference between them, a model with the signature in front of it
  // licensed both, and ordering equally-licensed, equally-consequential
  // candidates is the one thing a retrieval score is for. The pair this spike
  // is actually afraid of — archive versus delete — is this shape, and what
  // saves it is the verdict, not this tie-break.
  const built = build({
    rung: 2 as Rung,
    candidates: [
      candidate({ toolSlug: "tool-hi", score: 0.99 }),
      candidate({ toolSlug: "tool-lo", score: 0.1 }),
    ],
    prior: [stats({ n: 20, successes: 20 })],
  });
  const d = await built.router.decide(sig(), ctx());
  assert.equal(d.tool?.toolSlug, "tool-hi");
  assert.deepEqual(built.asked.map((c) => c.toolSlug), ["tool-hi"]);
});

// ===========================================================================
// RULE 2 — connected?
// ===========================================================================
test("rule 2: a matched tool in an unconnected app goes to the browser with a nudge", async () => {
  const d = await decide({
    rung: 4 as Rung,
    candidates: [candidate({ app: APP_B })],
    connections: [],
  });
  assert.equal(d.hand, "browser");
  assert.equal(d.nudgeApp, APP_B);
  assert.equal(d.tool, undefined);
});

test("rule 2: an EXPIRED connection is not a connection", async () => {
  // Executing against a dead token buys a 401 the owner reads as a failed
  // errand; the nudge costs him one tap and no failed errand.
  const d = await decide({
    rung: 4 as Rung,
    connections: [connection({ status: "expired" })],
  });
  assert.equal(d.hand, "browser");
  assert.equal(d.nudgeApp, APP_A);
});

test("rule 2: a REVOKED connection is not a connection", async () => {
  const d = await decide({
    rung: 4 as Rung,
    connections: [connection({ status: "revoked" })],
  });
  assert.equal(d.hand, "browser");
  assert.equal(d.nudgeApp, APP_A);
});

test("rule 1: a malformed candidate is dropped, not carried into a nudge", async () => {
  // Rule 2 would otherwise text the owner asking him to connect "undefined".
  const d = await decide({
    rung: 4 as Rung,
    candidates: [{ toolSlug: "tool-x", score: 0.9, schema: {}, description: "d" } as ToolCandidate],
    connections: [],
  });
  assert.equal(d.hand, "browser");
  assert.equal(d.nudgeApp, undefined);
  assert.equal(Object.prototype.hasOwnProperty.call(d, "nudgeApp"), false);
});

test("rule 2: a vendor outage does not nudge the owner about an app he already connected", async () => {
  // An empty connection list and an unreachable connection list are the same
  // array. Treating them the same would text him "connect this to make me
  // faster" about an app he connected last month, once per task, for the whole
  // outage — and onboarding would count every one as evidence he wants it.
  const d = await decide({ rung: 4 as Rung, connectionsThrow: true });
  assert.equal(d.hand, "browser");
  assert.equal(d.nudgeApp, undefined);
});

test("rule 2: the nudge names the matched app, not the planner's hint", async () => {
  const d = await decide(
    { rung: 4 as Rung, candidates: [candidate({ app: APP_B })], connections: [] },
    sig({ app_hint: "a-planner-guess" }),
  );
  assert.equal(d.nudgeApp, APP_B);
});

// ===========================================================================
// RULE 3 — read steps and the ladder.
// ===========================================================================
test("rule 3: rung 1 read runs BOTH hands", async () => {
  const d = await decide({ rung: 1 as Rung });
  assert.equal(d.hand, "shadow");
  assert.equal(d.tool?.toolSlug, "tool-1");
});

test("rule 3: rung 0 read online stays on the browser", async () => {
  const d = await decide({ rung: 0 as Rung });
  assert.equal(d.hand, "browser");
  assert.equal(d.queued, undefined);
});

test("rule 3: rung 2 read goes API alone", async () => {
  const d = await decide({ rung: 2 as Rung, prior: [stats({ n: 27, successes: 26 })] });
  assert.equal(d.hand, "api");
});

test("rule 3: an OFFLINE read goes API at rung 0 — a read cannot hurt", async () => {
  const d = await decide({ rung: 0 as Rung }, sig(), ctx({ deviceOnline: false }));
  assert.equal(d.hand, "api");
  assert.equal(d.queued, undefined);
});

test("rule 3: an OFFLINE read at the shadow rung goes API, not shadow", async () => {
  // Shadow needs both hands. With one hand missing there is nothing to compare.
  const d = await decide({ rung: 1 as Rung }, sig(), ctx({ deviceOnline: false }));
  assert.equal(d.hand, "api");
});

test("rule 3: an OFFLINE read with no licensed tool is queued, not silently dropped", async () => {
  const d = await decide({ rung: 0 as Rung, verdicts: { "tool-1": "no" } }, sig(), ctx({ deviceOnline: false }));
  assert.equal(d.hand, "browser");
  assert.equal(d.queued, true);
});

// ===========================================================================
// RULE 4 — writes.
// ===========================================================================
const writeSig = () => sig({ verb: "send", side_effect: "write", signature_hash: H_WRITE });

test("rule 4: a write at rung 2 goes to the browser even with the opt-in", async () => {
  const d = await decide({ rung: 2 as Rung, optedIn: true }, writeSig());
  assert.equal(d.hand, "browser");
});

test("rule 4: a write at rung 3 WITHOUT the opt-in goes to the browser", async () => {
  const d = await decide({ rung: 3 as Rung, optedIn: false }, writeSig());
  assert.equal(d.hand, "browser");
});

test("rule 4: a write at rung 3 WITH the opt-in goes API", async () => {
  const d = await decide(
    { rung: 3 as Rung, optedIn: true, prior: [stats({ n: 30, successes: 29, signature_hash: H_WRITE })] },
    writeSig(),
  );
  assert.equal(d.hand, "api");
});

test("rule 4: a write is NEVER shadowed, at any rung", async () => {
  for (const rung of [0, 1, 2, 3, 4] as Rung[]) {
    for (const optedIn of [false, true]) {
      const d = await decide({ rung, optedIn }, writeSig());
      assert.notEqual(d.hand, "shadow", `rung ${rung} optedIn ${optedIn} shadowed a write`);
    }
  }
});

test("rule 4: an irreversible step is never shadowed either", async () => {
  for (const rung of [0, 1, 2, 3, 4] as Rung[]) {
    const d = await decide({ rung, optedIn: true }, sig({ verb: "delete", side_effect: "irreversible" }));
    assert.notEqual(d.hand, "shadow");
  }
});

test("rule 4: an irreversible step confirms at EVERY rung and on either hand", async () => {
  const irreversible = sig({ verb: "pay", side_effect: "irreversible", signature_hash: H_IRREVERSIBLE });
  for (const rung of [0, 1, 2, 3, 4] as Rung[]) {
    const d = await decide(
      { rung, optedIn: true, prior: [stats({ n: 50, successes: 50, signature_hash: H_IRREVERSIBLE })] },
      irreversible,
    );
    assert.equal(d.requiresConfirmation, true, `rung ${rung} skipped the confirmation`);
  }
});

test("rule 4: an irreversible step confirms even when no tool was licensed", async () => {
  const d = await decide(
    { rung: 4 as Rung, verdicts: { "tool-1": "no" } },
    sig({ verb: "delete", side_effect: "irreversible" }),
  );
  assert.equal(d.hand, "browser");
  assert.equal(d.requiresConfirmation, true);
});

test("rule 4: an OFFLINE write with no licence is queued, not dispatched into a sleeping browser", async () => {
  const d = await decide({ rung: 1 as Rung, optedIn: true }, writeSig(), ctx({ deviceOnline: false }));
  assert.equal(d.hand, "browser");
  assert.equal(d.queued, true);
});

test("rule 4: an OFFLINE write the owner opted into at rung 3 still goes API", async () => {
  // The API hand does not need his browser, and he already authorised this.
  const d = await decide(
    { rung: 3 as Rung, optedIn: true, prior: [stats({ n: 30, successes: 30, signature_hash: H_WRITE })] },
    writeSig(),
    ctx({ deviceOnline: false }),
  );
  assert.equal(d.hand, "api");
  assert.equal(d.queued, undefined);
});

test("rule 4: a tool's own hint may make a step stricter, never looser", async () => {
  // A planned READ that the tool declares irreversible must leave the read
  // ladder entirely: it now needs the write rung, the opt-in, and a
  // confirmation. Trusting the annotation the other way is how "archive" and
  // "delete" become the same call.
  const d = await decide(
    { rung: 2 as Rung, optedIn: false, candidates: [candidate({ sideEffectHint: "irreversible" })] },
    sig({ side_effect: "read" }),
  );
  assert.equal(d.hand, "browser");
  assert.equal(d.requiresConfirmation, true);
});

test("rule 4: a tool claiming read-only cannot downgrade a planned write", async () => {
  const d = await decide(
    { rung: 2 as Rung, optedIn: true, candidates: [candidate({ sideEffectHint: "read" })] },
    writeSig(),
  );
  // Still on the write ladder, so rung 2 is below the bar and the browser keeps
  // it — not the rung-2 API route a genuine read would have got.
  assert.equal(d.hand, "browser");
});

// ===========================================================================
// RULE 5 — score, then fall back.
// ===========================================================================
test("rule 5: a strictly better browser takes the step back from the API hand", async () => {
  const d = await decide({
    rung: 4 as Rung,
    prior: [
      stats({ hand: "api", n: 10, successes: 6 }),
      stats({ hand: "browser", tool_slug: "", n: 60, successes: 59 }),
    ],
  });
  assert.equal(d.hand, "browser");
});

test("rule 5: a tie is not a demotion — the ladder's licence stands", async () => {
  // A freshly promoted pair has no rows on either hand. If a tie went to the
  // browser, nothing would ever leave the ladder it just climbed.
  const d = await decide({ rung: 2 as Rung, prior: [] });
  assert.equal(d.hand, "api");
});

test("rule 5: latency alone can move the step to the browser", async () => {
  const d = await decide({
    rung: 4 as Rung,
    prior: [
      stats({ hand: "api", n: 50, successes: 50, p50_ms: 600_000 }),
      stats({ hand: "browser", tool_slug: "", n: 50, successes: 50, p50_ms: 1_000 }),
    ],
  });
  assert.equal(d.hand, "browser");
});

test("rule 5: the comparison also governs writes", async () => {
  const d = await decide(
    {
      rung: 4 as Rung,
      optedIn: true,
      prior: [
        stats({ hand: "api", signature_hash: H_WRITE, n: 8, successes: 4 }),
        stats({ hand: "browser", signature_hash: H_WRITE, tool_slug: "", n: 80, successes: 78 }),
      ],
    },
    writeSig(),
  );
  assert.equal(d.hand, "browser");
});

test("rule 5: the API row for the matched slug is preferred over other slugs in the app", async () => {
  const d = await decide({
    rung: 4 as Rung,
    prior: [
      stats({ hand: "api", tool_slug: "tool-1", n: 40, successes: 40 }),
      stats({ hand: "api", tool_slug: "tool-other", n: 40, successes: 0 }),
      stats({ hand: "browser", tool_slug: "", n: 40, successes: 30 }),
    ],
  });
  // Folding the sibling slug's 40 failures in would hand the step to the
  // browser for something a different endpoint did.
  assert.equal(d.hand, "api");
});

// --- fallbackAfterApiFailure -----------------------------------------------
const failCtx = (
  over: Partial<UserCtx & { consecutiveApiFailures: number; rung: Rung; sideEffect: SideEffect }> = {},
) => ({
  ...ctx(),
  ...over,
});

test("fallback: a rate limit spends its one retry before it counts as a failure", () => {
  const plan = fallbackAfterApiFailure({ kind: "rate" } as ApiFailure, failCtx({ rung: 3 as Rung }));
  assert.equal(plan.action, "retry-api");
  assert.equal(plan.demoteTo, null);
});

test("fallback: a rate limit AFTER its retry falls back like any other failure", () => {
  const plan = fallbackAfterApiFailure({ kind: "rate", retried: true } as ApiFailure, failCtx());
  assert.equal(plan.action, "browser");
});

test("fallback: an auth failure falls back in the same task and asks for a re-auth", () => {
  const plan = fallbackAfterApiFailure({ kind: "auth", message: "401" } as ApiFailure, failCtx());
  assert.equal(plan.action, "browser");
  assert.equal(plan.reauthNudge, true);
  assert.match(plan.failReason, /auth/);
});

test("fallback: a schema failure falls back and does not ask for a re-auth", () => {
  const plan = fallbackAfterApiFailure({ kind: "schema" } as ApiFailure, failCtx());
  assert.equal(plan.action, "browser");
  assert.equal(plan.reauthNudge, false);
});

test("fallback: a verifier mismatch falls back exactly like a transport failure", () => {
  // The API said it worked and the world disagreed. That is the most serious
  // of these, not an exception to them.
  //
  // The step is declared a read, which this test used to leave unsaid. On a
  // read the two failures really are the same; on a write they are not, and
  // the pair of tests below the ladder legs settles that half.
  const plan = fallbackAfterApiFailure(
    { kind: "verifier", message: "no such effect" } as ApiFailure,
    failCtx({ sideEffect: "read" as SideEffect }),
  );
  assert.equal(plan.action, "browser");
});

test("fallback: with the browser unreachable the step queues instead of failing", () => {
  // Also declared, for the same reason: parking a read for later costs the
  // owner a wait, and parking an unconfirmed write costs him a second one.
  const plan = fallbackAfterApiFailure(
    { kind: "other" } as ApiFailure,
    failCtx({ deviceOnline: false, sideEffect: "read" as SideEffect }),
  );
  assert.equal(plan.action, "queue");
});

test("fallback: two failures in a row drop the pair one rung", () => {
  const plan = fallbackAfterApiFailure(
    { kind: "schema" } as ApiFailure,
    failCtx({ consecutiveApiFailures: 2, rung: 3 as Rung }),
  );
  assert.equal(plan.demoteTo, 2);
});

test("fallback: one failure does not demote", () => {
  const plan = fallbackAfterApiFailure(
    { kind: "schema" } as ApiFailure,
    failCtx({ consecutiveApiFailures: 1, rung: 3 as Rung }),
  );
  assert.equal(plan.demoteTo, null);
});

test("fallback: a missing counter is read as one failure, never as two", () => {
  // Demoting on a caller's omission would quietly undo weeks of good runs.
  const plan = fallbackAfterApiFailure({ kind: "schema" } as ApiFailure, failCtx({ rung: 4 as Rung }));
  assert.equal(plan.demoteTo, null);
});

test("fallback: demotion stops at rung 0", () => {
  const plan = fallbackAfterApiFailure(
    { kind: "other" } as ApiFailure,
    failCtx({ consecutiveApiFailures: 5, rung: 0 as Rung }),
  );
  assert.equal(plan.demoteTo, null);
});

// --- an AMBIGUOUS failure on a step that changes the world ------------------
// The adapter one layer down retries a 429 exactly once and refuses to retry
// anything else, because the execute endpoint takes no idempotency key and a
// retried send is a second send. Falling back to the other hand is the same
// second attempt wearing a different hat.
test("fallback: an ambiguous failure on a WRITE is not silently re-run on the other hand", () => {
  const plan = fallbackAfterApiFailure(
    { kind: "other", message: "504 gateway timeout" } as ApiFailure,
    failCtx({ sideEffect: "write" as SideEffect, rung: 3 as Rung }),
  );
  assert.equal(plan.action, "ask-owner");
  assert.equal(plan.mayHaveLanded, true);
});

test("fallback: an ambiguous failure on an IRREVERSIBLE step is not re-run either", () => {
  const plan = fallbackAfterApiFailure(
    { kind: "other", message: "connection reset" } as ApiFailure,
    failCtx({ sideEffect: "irreversible" as SideEffect, rung: 4 as Rung }),
  );
  assert.equal(plan.action, "ask-owner");
});

test("fallback: a verifier mismatch on a write needs the owner — that call DID run", () => {
  // The API returned ok and the world disagreed. The one thing not in doubt is
  // that the request reached the vendor, so a browser re-run is the likeliest
  // duplicate of the lot: the verifier may simply be reading a mailbox that
  // has not caught up yet.
  const plan = fallbackAfterApiFailure(
    { kind: "verifier", message: "no such effect" } as ApiFailure,
    failCtx({ sideEffect: "write" as SideEffect, rung: 3 as Rung }),
  );
  assert.equal(plan.action, "ask-owner");
});

test("fallback: an ambiguous write still walks the ladder down after two in a row", () => {
  // Needing the owner is not the same as forgiving the hand.
  const plan = fallbackAfterApiFailure(
    { kind: "other" } as ApiFailure,
    failCtx({ sideEffect: "write" as SideEffect, consecutiveApiFailures: 2, rung: 3 as Rung }),
  );
  assert.equal(plan.action, "ask-owner");
  assert.equal(plan.demoteTo, 2);
});

test("fallback: an offline ambiguous write asks the owner rather than queueing a duplicate", () => {
  // "Queue" means run it when the browser comes back. On a step that may
  // already have happened that is a duplicate with a delay on it.
  const plan = fallbackAfterApiFailure(
    { kind: "other" } as ApiFailure,
    failCtx({ sideEffect: "write" as SideEffect, rung: 3 as Rung, deviceOnline: false }),
  );
  assert.equal(plan.action, "ask-owner");
});

test("fallback: a read falls back freely however ambiguous the failure was", () => {
  // A read changes nothing, so doing it twice costs the owner nothing and
  // refusing costs him the whole task.
  for (const kind of ["other", "verifier"] as const) {
    const plan = fallbackAfterApiFailure(
      { kind } as ApiFailure,
      failCtx({ sideEffect: "read" as SideEffect, rung: 4 as Rung }),
    );
    assert.equal(plan.action, "browser", kind);
    assert.equal(plan.mayHaveLanded, true, kind);
  }
});

// --- a failure that is KNOWN not to have landed -----------------------------
test("fallback: a write whose failure is known not to have landed falls back like a read", () => {
  // A credential rejected at the door and a schema the vendor refused are both
  // promises that nothing reached the owner's account; a 429 is the one status
  // the vendor documents as "not executed". Refusing these would strand every
  // expired token on the browser hand for no reason at all.
  for (const kind of ["auth", "schema"] as const) {
    const plan = fallbackAfterApiFailure(
      { kind } as ApiFailure,
      failCtx({ sideEffect: "write" as SideEffect, rung: 3 as Rung }),
    );
    assert.equal(plan.action, "browser", kind);
    assert.equal(plan.mayHaveLanded, false, kind);
  }
  const rated = fallbackAfterApiFailure(
    { kind: "rate", retried: true } as ApiFailure,
    failCtx({ sideEffect: "irreversible" as SideEffect, rung: 4 as Rung }),
  );
  assert.equal(rated.action, "browser");
  assert.equal(rated.mayHaveLanded, false);
});

test("fallback: a 401 on a write still asks for the re-auth on the way past", () => {
  const plan = fallbackAfterApiFailure(
    { kind: "auth", message: "401" } as ApiFailure,
    failCtx({ sideEffect: "write" as SideEffect, rung: 3 as Rung }),
  );
  assert.equal(plan.action, "browser");
  assert.equal(plan.reauthNudge, true);
});

// --- the caller who declares nothing ----------------------------------------
test("fallback: an UNDECLARED side effect at a rung a write could hold is not re-run", () => {
  // The floor points the same way as rule 1's here: no declaration is not a
  // declaration of "read". Rule 4 will not put a write on the API hand below
  // WRITE_MIN_RUNG, so at or above it the step could have been one — and a
  // caller that forgot the field must not buy a second send with the omission.
  const plan = fallbackAfterApiFailure({ kind: "other" } as ApiFailure, failCtx({ rung: 3 as Rung }));
  assert.equal(plan.action, "ask-owner");
});

test("fallback: an undeclared side effect BELOW the rung any write needs is provably a read", () => {
  // Rule 4 refuses the API hand to a write below WRITE_MIN_RUNG, so a failure
  // reported from a lower rung came from a read and falls back freely. This is
  // what keeps a caller that predates the field from stranding every read.
  for (const rung of [0, 1, 2] as Rung[]) {
    const plan = fallbackAfterApiFailure({ kind: "other" } as ApiFailure, failCtx({ rung }));
    assert.equal(plan.action, "browser", `rung ${rung}`);
  }
});

test("fallback: an undeclared side effect and an undeclared rung ask the owner", () => {
  // Nothing said what this step was and nothing said what it had earned. The
  // hazard is a duplicate the owner cannot undo; the cost of refusing is one
  // question. That trade is not close.
  const plan = fallbackAfterApiFailure({ kind: "other" } as ApiFailure, failCtx());
  assert.equal(plan.action, "ask-owner");
});

test("fallback: a rate limit still spends its retry before any of this applies", () => {
  // The one retry is cheaper than a browser run and safe by the vendor's own
  // documentation, on a write as much as on a read.
  const plan = fallbackAfterApiFailure(
    { kind: "rate" } as ApiFailure,
    failCtx({ sideEffect: "irreversible" as SideEffect, rung: 4 as Rung }),
  );
  assert.equal(plan.action, "retry-api");
  assert.equal(plan.mayHaveLanded, false);
});

// ===========================================================================
// LAW 1 — the router may not name an app, and may not read the planner's hint.
// ===========================================================================
const ROUTER_SRC = readFileSync(new URL("../src/router.ts", import.meta.url), "utf8");

/** Comments stripped so the load-bearing leg reads CODE. The whole-file leg
 *  below then catches the same names in prose, because a comment naming an app
 *  is where the next branch keyed on it gets its idea. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

// The only list of app names this spike is allowed to contain, and it lives in
// a test because HARNESS-LAWS law 1 permits pattern matching in gates.
const APP_NAMES = [
  "gmail", "googlecalendar", "google", "outlook", "slack", "notion", "github",
  "gitlab", "linear", "asana", "trello", "jira", "confluence", "salesforce",
  "hubspot", "stripe", "shopify", "twilio", "sendgrid", "airtable", "dropbox",
  "box", "zoom", "discord", "figma", "intercom", "zendesk", "quickbooks",
  "xero", "calendly", "docusign", "mailchimp", "clickup", "monday", "chrome",
  "whatsapp", "telegram", "instagram", "facebook", "twitter", "linkedin",
  "amazon", "uber", "doordash", "opentable", "spotify", "apple", "microsoft",
];

test("law 1: router.ts contains no app name in its code", () => {
  const code = stripComments(ROUTER_SRC).toLowerCase();
  const hits = APP_NAMES.filter((n) => new RegExp(`\\b${n}\\b`).test(code));
  assert.deepEqual(hits, [], `router.ts names apps in code: ${hits.join(", ")}`);
  // The leg has to be able to go red. Stripping comments is the step most
  // likely to quietly eat the whole file and turn this green over nothing, so
  // the same scan is run over a source that definitely violates it.
  const planted = stripComments('// a comment\nif (c.app === "slack") return 1;').toLowerCase();
  assert.ok(APP_NAMES.some((n) => new RegExp(`\\b${n}\\b`).test(planted)));
});

test("law 1: router.ts does not name an app in its prose either", () => {
  // A comment naming one app is where the next agent's branch on that app
  // starts. There is no legitimate reason for this file to know one exists.
  const hits = APP_NAMES.filter((n) => new RegExp(`\\b${n}\\b`).test(ROUTER_SRC.toLowerCase()));
  assert.deepEqual(hits, [], `router.ts names apps: ${hits.join(", ")}`);
});

test("law 1: no string literal is compared against an app or a tool slug", () => {
  const code = stripComments(ROUTER_SRC);
  // `typeof c.toolSlug !== "string"` is exempt, and only that shape. It is a
  // runtime guard on a value the vendor supplied, which law 1 counts as
  // plumbing; it cannot express "this app in particular" because the only
  // strings it can compare against are JavaScript's seven type names.
  const literalComparisons = [
    /(?<!typeof\s)\b[A-Za-z_$][\w$]*\.(app|toolSlug)\s*[=!]==?\s*["'`]/,
    /["'`]\s*[=!]==?\s*[A-Za-z_$][\w$.]*\.(app|toolSlug)/,
    /\.(app|toolSlug)\s*\.\s*(includes|startsWith|endsWith|match|search|indexOf)\s*\(/,
  ];
  for (const re of literalComparisons) {
    assert.equal(re.test(code), false, `router.ts branches on an app string: ${re}`);
  }
  // A gate that cannot go red is a decoration. These are the three shapes the
  // leg exists to catch, and it has to catch them.
  const violations = [
    'if (matched.app === "some-vendor") return browserHand;',
    'if ("some-vendor" === matched.app) return browserHand;',
    'if (matched.toolSlug.startsWith("SOMEVENDOR_")) return browserHand;',
  ];
  for (const v of violations) {
    assert.ok(literalComparisons.some((re) => re.test(v)), `the leg would have missed: ${v}`);
  }
});

test("law 1: the router never reads the planner's app_hint", () => {
  // app_hint is a guess made before anyone looked at a catalog. Routing on it
  // would let the planner's wording decide which of the owner's accounts gets
  // touched — the contract calls it advisory for exactly that reason.
  assert.equal(stripComments(ROUTER_SRC).includes("app_hint"), false);
});

test("law 1: renaming every app string changes nothing about the decision", async () => {
  // The behavioural half of the source scan. If any branch were keyed on an
  // app string, one of these two runs would differ.
  const run = async (app: string) =>
    await decide({
      rung: 3 as Rung,
      optedIn: true,
      candidates: [candidate({ app })],
      connections: [connection({ app })],
      prior: [stats({ app, hand: "api", n: 20, successes: 19, signature_hash: H_WRITE })],
    }, writeSig());

  const a = await run("aaaaaaaa");
  const z = await run("zzzzzzzz");
  assert.equal(a.hand, z.hand);
  assert.equal(a.rung, z.rung);
  assert.equal(a.score, z.score);
  assert.equal(a.requiresConfirmation, z.requiresConfirmation);
});

test("law 1: an unavailable ledger lands on the browser, never on an assumed rung", async () => {
  // "We could not read the rung, so assume it is high" is the shape that turns
  // an outage into an unlicensed write.
  const d = await decide({ ledgerThrows: true, optedIn: true }, writeSig());
  assert.equal(d.hand, "browser");
  assert.equal(d.rung, 0);
});

// ===========================================================================
// The audit sentence.
// ===========================================================================
test("reason: every decision carries a sentence a person can read", async () => {
  const cases: RouteDecision[] = [
    await decide({ rung: 2 as Rung, prior: [stats({ n: 27, successes: 26 })] }),
    await decide({ rung: 1 as Rung }),
    await decide({ rung: 0 as Rung }),
    await decide({ rung: 4 as Rung, connections: [] }),
    await decide({ rung: 4 as Rung, verdicts: { "tool-1": "no" } }),
  ];
  for (const d of cases) {
    assert.equal(typeof d.reason, "string");
    assert.ok(d.reason.length > 10, d.reason);
  }
});

test("reason: an API decision names the rung and the evidence behind it", async () => {
  const d = await decide({ rung: 2 as Rung, prior: [stats({ n: 27, successes: 26 })] });
  assert.match(d.reason, /rung 2/);
  assert.match(d.reason, /LB95 0\.\d\d over 27 runs/);
});

test("reason: a browser decision reports the browser hand's real score, not 0", async () => {
  // The audit line is the only account anyone gets of why a step went the way
  // it did. Printing 0 for a hand with forty good runs says the opposite of
  // the truth to the person reading it at 2am.
  const d = await decide({
    rung: 4 as Rung,
    connections: [],
    prior: [stats({ hand: "browser", tool_slug: "", n: 40, successes: 39 })],
  });
  assert.equal(d.hand, "browser");
  assert.ok(d.score > 0.7, String(d.score));
});

test("reason: the structured fields carry every fact the sentence does", async () => {
  // Nothing may branch on the sentence, so anything a caller needs has to exist
  // as a field. This is the leg that notices if a fact goes prose-only.
  const d = await decide({ rung: 4 as Rung, candidates: [candidate({ app: APP_B })], connections: [] });
  assert.equal(d.hand, "browser");
  assert.equal(d.nudgeApp, APP_B);
  assert.equal(typeof d.rung, "number");
  assert.equal(typeof d.score, "number");
});
