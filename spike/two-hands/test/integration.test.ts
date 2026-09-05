// THE WHOLE STORY, ON THE FAKE PROVIDER, WITH NO NETWORK AND NO KEY.
//
// Every other suite in this directory tests one part against the contract.
// This one is the only place where the parts have to be true at the same time,
// and it is written as a narrative on purpose: a person should be able to read
// it top to bottom and recognise the product.
//
//   1. A read step on an app the owner has not connected goes to the browser,
//      and raises a nudge with the evidence to earn the ask.
//   2. He connects it. The ladder hears about it — that is the wire this spike
//      did not have until src/index.ts was written.
//   3. Three shadow reads with parity promote the pair to rung 2.
//   4. The fourth read goes API-only, because the API hand's own measured runs
//      beat the browser's own measured runs.
//   5. A write is refused until he opts in.
//   6. An API failure falls back to the browser inside the same task.
//   7. Two failures in a row demote the pair and re-open shadow.
//
// TWO THINGS IN THIS FILE ARE PINNED DEFECTS, NOT DESIRED BEHAVIOUR. They are
// marked `FINDING` and they assert what the assembled system does TODAY, with
// a comment saying what it ought to do instead. Writing them as skipped tests
// or leaving them out would be the same as not knowing; RESULTS.md carries
// both, and this is where they will fail loudly if anybody fixes them.
//
// The judge is a stub. It has to be: a judge is a model call, and this suite
// runs with no key. The stub answers from a TABLE keyed by signature hash and
// tool slug — it never reads a description. A stub that decided "yes" by
// looking for a word in `candidate.description` would make every assertion
// below a test of my substring rule rather than of the router, and the fixture
// is built to punish exactly that: retrieval ranks GMAIL_ARCHIVE_THREAD above
// GMAIL_DELETE_THREAD for a delete step, so anything that follows the score
// archives when it was asked to delete.

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { apiOutcome, browserOutcome, fallbackAfterApiFailure, makeTwoHands } from "../src/index.ts";
import type { TwoHands } from "../src/index.ts";
import { makeSignature } from "../src/signature.ts";
import { FIXTURE, FakeProvider, withConnections, withExec, withRetrieval } from "../src/provider_fake.ts";
import type { FakeFixture } from "../src/provider_fake.ts";
import type {
  CapabilitySignature,
  ConnectedApp,
  ExecResult,
  MatchAnswer,
  MatchJudge,
  Provider,
  ToolCandidate,
  UserCtx,
} from "../src/contract.ts";
import type { ObservedEvent } from "../src/observer.ts";

const OWNER = "owner-integration";
const GMAIL_WORK: ConnectedApp = {
  app: "gmail",
  accountId: "conn-gmail-work-0001",
  label: "work@example.invalid",
  scopes: ["gmail.readonly", "gmail.send"],
  status: "active",
};

// A fixed clock. Every timestamp in the story is derived from it, so a run at
// midnight and a run at noon produce the same rows — and the quiet-hours rule
// in onboarding is exercised at a stated hour rather than at whatever hour the
// suite happens to run.
const T0 = Date.UTC(2026, 8, 5, 15, 0, 0); // 15:00 UTC, inside waking hours

// ---------------------------------------------------------------------------
// The three steps this story is about.
// ---------------------------------------------------------------------------
// Built with the real `makeSignature`, so the hashes are the ones production
// would compute rather than literals that agree with nothing.
const READ = makeSignature({
  app_hint: "gmail",
  verb: "read",
  object: "unread messages in the primary inbox",
  inputs: { max_results: 20 },
  expected_effect: "the last 20 unread messages are listed and none is marked read",
  side_effect: "read",
  account_hint: "work",
});

const WRITE = makeSignature({
  app_hint: "gmail",
  verb: "send",
  object: "an email to one recipient",
  inputs: { to: "", subject: "", body: "" },
  expected_effect: "a message from the owner to that recipient appears in Sent",
  side_effect: "write",
  account_hint: "work",
});

const DELETE = makeSignature({
  app_hint: "gmail",
  verb: "delete",
  object: "one mail thread",
  inputs: { thread_id: "" },
  expected_effect: "the thread is gone from All Mail",
  side_effect: "irreversible",
  account_hint: "work",
});

/** What retrieval returns for each of the three, on top of the shipped fixture.
 *  The delete step's ordering is the dangerous one from provider_fake: the
 *  ARCHIVE tool outranks the DELETE tool, so a router that trusted the score
 *  would archive a thread it was told to destroy. */
function withStorySteps(base: FakeFixture): FakeFixture {
  let f = withRetrieval(base, READ.signature_hash, [
    { toolSlug: "GMAIL_FETCH_EMAILS", score: 0.93 },
    { toolSlug: "NOTION_SEARCH", score: 0.41 },
  ]);
  f = withRetrieval(f, WRITE.signature_hash, [
    { toolSlug: "GMAIL_SEND_EMAIL", score: 0.88 },
    { toolSlug: "SLACK_SEND_MESSAGE", score: 0.72 },
  ]);
  f = withRetrieval(f, DELETE.signature_hash, [
    { toolSlug: "GMAIL_ARCHIVE_THREAD", score: 0.9 },
    { toolSlug: "GMAIL_DELETE_THREAD", score: 0.87 },
  ]);
  return f;
}

/** GMAIL_FETCH_EMAILS answers four times and then breaks, twice. The script is
 *  the whole of the failure half of the story and it needs no clock. */
const READ_SCRIPT = [
  { ok: true, ms: 340, costUsd: 0.0004, data: { messages: [{ id: "msg-1" }] } },
  { ok: true, ms: 355, costUsd: 0.0004, data: { messages: [{ id: "msg-2" }] } },
  { ok: true, ms: 330, costUsd: 0.0004, data: { messages: [{ id: "msg-3" }] } },
  { ok: true, ms: 360, costUsd: 0.0004, data: { messages: [{ id: "msg-4" }] } },
  { ok: false, ms: 900, error: { kind: "other" as const, message: "500 upstream error" } },
  { ok: false, ms: 880, error: { kind: "other" as const, message: "500 upstream error" } },
];

// ---------------------------------------------------------------------------
// The judge stub.
// ---------------------------------------------------------------------------
/** A table, not a reader. `matches` looks up (signature hash, tool slug) and
 *  answers in the contract's four states; the description is never read. Every
 *  candidate that is not in the table gets an explicit "no", so an unasked
 *  question and a refused one are still different things. */
function tableJudge(table: Record<string, string>): MatchJudge & { asked: string[] } {
  const asked: string[] = [];
  return {
    asked,
    async matches(sig: CapabilitySignature, candidate: ToolCandidate): Promise<MatchAnswer> {
      asked.push(`${sig.verb}:${candidate.toolSlug}`);
      const wanted = table[sig.signature_hash];
      return wanted === candidate.toolSlug
        ? { verdict: "yes", reason: "this tool does this step" }
        : { verdict: "no", reason: "this tool does something else" };
    },
  };
}

const STORY_JUDGE = {
  [READ.signature_hash]: "GMAIL_FETCH_EMAILS",
  [WRITE.signature_hash]: "GMAIL_SEND_EMAIL",
  [DELETE.signature_hash]: "GMAIL_DELETE_THREAD",
};

// ---------------------------------------------------------------------------
// A provider the owner can connect an app to, mid-story.
// ---------------------------------------------------------------------------
/** `FakeProvider` is built from an immutable fixture, which is right for a unit
 *  test and wrong for a story in which the owner taps a connect link halfway
 *  through. This delegates to whichever fake is current, so "he connected it"
 *  is one line and the facade keeps the same provider object it was built
 *  with — exactly as it would in a Worker, where the vendor's answer changes
 *  and our object does not. */
class ConnectableProvider implements Provider {
  readonly name = "fake" as const;
  #fixture: FakeFixture;
  #current: FakeProvider;

  constructor(fixture: FakeFixture) {
    this.#fixture = fixture;
    this.#current = new FakeProvider(fixture);
  }

  get inner(): FakeProvider {
    return this.#current;
  }

  connect(rows: ConnectedApp[]): void {
    this.#fixture = withConnections(this.#fixture, OWNER, rows);
    this.#current = new FakeProvider(this.#fixture);
  }

  search(sig: CapabilitySignature, userId: string, opts: { connectedOnly: boolean; limit: number }) {
    return this.#current.search(sig, userId, opts);
  }
  connections(userId: string) {
    return this.#current.connections(userId);
  }
  connectLink(userId: string, app: string, scopes?: string[]) {
    return this.#current.connectLink(userId, app, scopes);
  }
  execute(userId: string, toolSlug: string, args: Record<string, unknown>, accountId?: string) {
    return this.#current.execute(userId, toolSlug, args, accountId);
  }
}

// ---------------------------------------------------------------------------
// The browser hand, as the Observer sees it.
// ---------------------------------------------------------------------------
/** One browser step: a navigation and two requests, twelve seconds wall clock.
 *  Twelve seconds is not decoration — rule 5 compares the two hands on their
 *  own measured p50s, and a browser hand that were as fast as the API hand
 *  would make the comparison in scene 4 prove nothing. */
function browserStepEvents(runId: string, stepId: string, startedAt: number): ObservedEvent[] {
  return [
    { kind: "navigation", run_id: runId, step_id: stepId, url: "https://mail.google.com/mail/u/0/", at: startedAt },
    {
      kind: "request",
      run_id: runId,
      step_id: stepId,
      method: "GET",
      url: "https://mail.google.com/sync/u/0/i/fd",
      status: 200,
      at: startedAt + 400,
      ms: 900,
    },
    {
      kind: "request",
      run_id: runId,
      step_id: stepId,
      method: "POST",
      url: "https://mail.google.com/sync/u/0/i/s",
      status: 200,
      at: startedAt + 4000,
      ms: 8000,
    },
  ];
}

/** Run the browser hand for one step and file the row. Returns the summary so
 *  the story can assert what the extension would have sent. */
function runBrowserStep(
  hands: TwoHands,
  sig: CapabilitySignature,
  ctx: UserCtx,
  runId: string,
  stepId: string,
  startedAt: number,
) {
  hands.observer.observeAll(browserStepEvents(runId, stepId, startedAt));
  // READ THE SUMMARY FIRST. `browserOutcome` is the last reader of a finished
  // step: it calls `summarizeAndForget`, so the trace is released the moment
  // the ledger row is built. Reading afterwards returns an empty summary — not
  // a bug, the lifecycle working. Anything that wants the duration for its own
  // purposes (the nudge copy quotes it: "that took 3 minutes") takes it here,
  // before the step is filed.
  const summary = hands.observer.summarize(runId, stepId);
  const outcome = browserOutcome({
    sig,
    ctx,
    // Supplied, never derived from the summary's hosts: mail.google.com,
    // calendar.google.com and drive.google.com all reduce to google.com, so a
    // host -> app table would be a guess wearing a lookup's clothes.
    app: "gmail",
    observer: hands.observer,
    runId,
    stepId,
    ok: true,
    verifierResult: "verified",
    at: startedAt,
  });
  return { outcome, summary };
}

function ctxAt(at: number, deviceOnline = true): UserCtx {
  return { userId: OWNER, deviceOnline, now: at };
}

function buildWorld(): { hands: TwoHands; provider: ConnectableProvider; judge: { asked: string[] } } {
  // The owner starts having connected NOTHING. Every "route to browser because
  // there is no connection" rule in the spike is measured from here.
  const fixture = withExec(
    withStorySteps(withConnections(FIXTURE, OWNER, [])),
    "GMAIL_FETCH_EMAILS",
    READ_SCRIPT,
  );
  const provider = new ConnectableProvider(fixture);
  const judge = tableJudge(STORY_JUDGE);
  const hands = makeTwoHands({ provider, judge, now: () => T0 });
  return { hands, provider, judge };
}

// ---------------------------------------------------------------------------
// THE STORY.
// ---------------------------------------------------------------------------
test("the whole second hand, from a cold owner to a demotion", async () => {
  const { hands, provider, judge } = buildWorld();
  const readHash = READ.signature_hash;

  // -- SCENE 1 --------------------------------------------------------------
  // "What did Alex say?" He has never connected Gmail. There IS a tool and the
  // judge vouches for it, and none of that matters yet: the API hand needs a
  // token, so the step goes to the browser and the owner gets told there is a
  // faster way.
  const d1 = await hands.router.decide(READ, ctxAt(T0));
  assert.equal(d1.hand, "browser");
  assert.equal(d1.rung, 0);
  assert.equal(d1.nudgeApp, "gmail", "rule 2 must surface WHICH app is worth connecting");
  assert.equal(d1.tool, undefined, "a browser decision carries no tool to execute");

  // The verdict was written down even though we did not use it. That row is
  // the ladder's rung-0 gate, the nudge's evidence, and the measurement
  // contract.ts LAW1 promises — how often the vendor's score agreed with the
  // judge — which cannot be collected after the fact.
  const candidates = await hands.ledger.candidates(OWNER, readHash);
  const fetchRow = candidates.find((c) => c.tool_slug === "GMAIL_FETCH_EMAILS");
  assert.ok(fetchRow, "the judged candidate was never recorded");
  assert.equal(fetchRow!.match_verdict, "yes");
  assert.equal(fetchRow!.connected, false);
  assert.equal(fetchRow!.source, "fake", "the row says which vendor answered, not which one we wished had");

  // The browser does the work. Twelve seconds of it, which is the number the
  // nudge is allowed to quote and the number rule 5 will compare against.
  const step1 = runBrowserStep(hands, READ, ctxAt(T0), "run-1", "step-1", T0);
  assert.deepEqual(step1.summary.hosts, ["google.com"], "eTLD+1 only, never a path and never a full URL");
  assert.equal(step1.summary.duration_ms, 12000);
  await hands.ledger.record(step1.outcome);

  // Evidence for the ask accrued by itself, because the facade counts a
  // `nudgeApp` decision as one more task that would have used the connection.
  const evidenceRow = await hands.onboarding.row(OWNER, "gmail");
  assert.equal(evidenceRow?.tasks_that_would_have_used_it, 1);

  // Now onboarding decides whether to interrupt him. Nothing above this line
  // asked that question, and nothing below re-answers it.
  const ask = await hands.onboarding.shouldNudge("gmail", {
    userId: OWNER,
    now: T0,
    ownerTimeZone: "America/Los_Angeles",
    taskRunning: false,
    lastNudgeAnyAppAt: null,
  });
  assert.equal(ask.verdict, "ask");

  const link = await hands.onboarding.connectLink(OWNER, "gmail");
  const scopes = hands.onboarding.scopesFor(
    await provider.search(READ, OWNER, { connectedOnly: false, limit: 5 }),
  );
  const text = hands.onboarding.text("gmail", {
    what_it_would_do: READ.expected_effect,
    browser_ms: step1.summary.duration_ms,
    api_ms_estimate: null,
    tasks_that_would_have_used_it: 1,
    connectUrl: link.url,
    scopes,
  });
  assert.ok(text.includes(link.url), "the one thing the message exists to get tapped must be in it");
  assert.ok(text.length <= 320, `the nudge is ${text.length} characters; two SMS segments is the budget`);
  assert.ok(
    !text.includes("nothing else"),
    "no tool in this fixture declared its scopes, so the message may not promise a narrow one",
  );
  await hands.onboarding.markSent(OWNER, "gmail", T0 + 1000, "sms");

  // -- SCENE 2 --------------------------------------------------------------
  // He taps it. Two things have to happen and only one of them is the vendor's:
  // the token exists, AND the ladder is told, or the pair sits at rung 0 for
  // ever and the tap buys him nothing.
  provider.connect([GMAIL_WORK]);
  await hands.onboarding.markConnected(OWNER, "gmail", T0 + 60_000);

  assert.equal((await hands.onboarding.row(OWNER, "gmail"))?.state, "connected");
  assert.equal(
    await hands.ledger.rung(OWNER, readHash, "gmail"),
    1,
    "a vouched candidate plus a connection IS the rung 0 -> 1 gate; the pair should be at shadow now",
  );

  // -- SCENE 3 --------------------------------------------------------------
  // Rung 1 is shadow: both hands run and the verifier compares each against the
  // expected effect — never against each other's output, or a wrong browser run
  // would certify a wrong API run for matching it.
  for (let i = 0; i < 3; i++) {
    const at = T0 + 120_000 + i * 60_000;
    const ctx = ctxAt(at);
    const decision = await hands.router.decide(READ, ctx);
    assert.equal(decision.hand, "shadow", `shadow run ${i + 1} did not go to both hands`);
    assert.equal(decision.rung, 1);
    assert.equal(decision.tool?.toolSlug, "GMAIL_FETCH_EMAILS");
    assert.equal(decision.accountId, GMAIL_WORK.accountId, "the API hand must name the account it will use");

    // The API hand. Arguments are hand-written here because NOTHING IN THIS
    // SPIKE FILLS A TOOL SCHEMA FROM A SIGNATURE — that is the executor's job
    // and week 1 has no executor (see RESULTS.md). tasks/run_ten.ts asks the
    // model to do it, which is where that decision belongs.
    const result: ExecResult = await provider.execute(
      OWNER,
      decision.tool!.toolSlug,
      { query: "is:unread", max_results: 20 },
      decision.accountId,
    );
    assert.equal(result.ok, true);

    // The browser hand runs the same step, and the verifier says the two agree.
    const step = runBrowserStep(hands, READ, ctx, `run-${i + 2}`, "step-1", at);
    await hands.ledger.record(step.outcome);
    await hands.ledger.record(
      apiOutcome({
        sig: READ,
        ctx,
        app: "gmail",
        toolSlug: decision.tool!.toolSlug,
        result,
        verifierResult: "verified",
        parity: true,
        at,
      }),
    );
  }

  assert.equal(
    await hands.ledger.rung(OWNER, readHash, "gmail"),
    2,
    "three consecutive parity matches is the rung 1 -> 2 gate",
  );

  // -- SCENE 4 --------------------------------------------------------------
  // From rung 2 the API hand runs alone — but only because its own measured
  // runs beat the browser's own measured runs. 340ms against 12 seconds, on
  // identical success rates.
  const at4 = T0 + 600_000;
  const d4 = await hands.router.decide(READ, ctxAt(at4));
  assert.equal(d4.hand, "api");
  assert.equal(d4.rung, 2);
  assert.ok(
    d4.reason.includes("LB95"),
    `the audit line must carry the numbers the decision was made on: ${d4.reason}`,
  );

  const fourth = await provider.execute(OWNER, d4.tool!.toolSlug, { query: "is:unread", max_results: 20 }, d4.accountId);
  assert.equal(fourth.ok, true);
  await hands.ledger.record(
    apiOutcome({ sig: READ, ctx: ctxAt(at4), app: "gmail", toolSlug: d4.tool!.toolSlug, result: fourth, verifierResult: "verified", at: at4 }),
  );

  // -- SCENE 5 --------------------------------------------------------------
  // A write is a different capability with its own ladder. It has a connection
  // and a licensed tool, so it climbs to rung 1 the moment the judge is asked —
  // and rung 1 is nowhere near enough to send an email.
  const at5 = T0 + 700_000;
  const w1 = await hands.router.decide(WRITE, ctxAt(at5));
  assert.equal(w1.hand, "browser");
  assert.equal(w1.rung, 1);
  assert.match(w1.reason, /below the rung writes need/);

  // The opt-in alone does not buy it either. Consent and evidence are two
  // separate gates and the owner saying yes does not conjure a track record.
  await hands.ledger.setWritesOptIn(OWNER, "gmail", true);
  const w2 = await hands.router.decide(WRITE, ctxAt(at5 + 1000));
  assert.equal(w2.hand, "browser", "an opt-in is consent, not evidence");

  // FINDING 1 (RESULTS.md): the pair is stood up by hand here because the
  // ladder cannot get a WRITE pair to rung 3 on its own. Rung 1 -> 2 is paid
  // for in shadow parity matches, rule 4 forbids ever shadowing a write, and
  // `clean_reads` only counts read-classified runs on this same pair — so the
  // gate that unlocks writes can never be satisfied by a write capability.
  // This line is the workaround, and it is a workaround, not the design.
  await hands.ledger.setRung(OWNER, WRITE.signature_hash, "gmail", 3);

  const w3 = await hands.router.decide(WRITE, ctxAt(at5 + 2000));
  assert.equal(w3.hand, "api", "rung 3 plus the owner's opt-in is what a write needs");
  assert.equal(w3.rung, 3);
  assert.equal(w3.tool?.toolSlug, "GMAIL_SEND_EMAIL");

  // FINDING 2 (RESULTS.md), NOW CLOSED — and this leg going red is how we found
  // out. Rung 3 is ASSISTED writes; the ledger's own constant says "every one
  // confirmed". The decision had no way to say so: `requiresConfirmation` was
  // set for irreversible steps only, so an executor reading a rung-3 decision
  // sent the email without asking, at the exact rung the ladder invented to
  // make it ask. It was PINNED to today's wrong answer rather than fixed,
  // because the fix is a routing rule and router.ts belonged to another agent.
  //
  // The router now sets it, this assertion went red on the next full run, and
  // it is flipped to the right answer. That is the whole point of pinning a
  // defect instead of leaving a TODO: the pin is what notices.
  assert.equal(
    w3.requiresConfirmation,
    true,
    "rung 3 is assisted writes — every one of them waits for his word",
  );

  // The irreversible step DOES carry it, on whichever hand runs — and the judge
  // licensed the second-ranked candidate, so nothing here followed the score.
  const del = await hands.router.decide(DELETE, ctxAt(at5 + 3000));
  assert.equal(del.requiresConfirmation, true, "a thing that cannot be taken back always waits for his word");
  assert.ok(
    judge.asked.includes("delete:GMAIL_ARCHIVE_THREAD"),
    "the judge must be asked about the top-scored candidate before it is passed over",
  );
  assert.ok(
    !(del.hand === "api" && del.tool?.toolSlug === "GMAIL_ARCHIVE_THREAD"),
    "the retrieval score ranked ARCHIVE first for a DELETE step; only a verdict may license a tool",
  );

  // -- SCENE 6 --------------------------------------------------------------
  // Back on the read pair, at rung 2, the vendor's upstream breaks. The owner
  // must not experience that as a failed errand: the same task changes hands.
  const at6 = T0 + 800_000;
  const d6 = await hands.router.decide(READ, ctxAt(at6));
  assert.equal(d6.hand, "api");
  const failed = await provider.execute(OWNER, d6.tool!.toolSlug, { query: "is:unread", max_results: 20 }, d6.accountId);
  assert.equal(failed.ok, false);
  assert.equal(failed.error?.kind, "other");

  const plan6 = fallbackAfterApiFailure(
    { kind: failed.error!.kind, message: failed.error!.message },
    { ...ctxAt(at6), consecutiveApiFailures: 1, rung: 2 },
  );
  assert.equal(plan6.action, "browser", "one failure changes hands inside the same task");
  assert.equal(plan6.demoteTo, null, "one failure is not a demotion");

  await hands.ledger.record(
    apiOutcome({ sig: READ, ctx: ctxAt(at6), app: "gmail", toolSlug: d6.tool!.toolSlug, result: failed, verifierResult: "unknown", at: at6 }),
  );
  const rescue = runBrowserStep(hands, READ, ctxAt(at6), "run-6", "step-1", at6);
  await hands.ledger.record(rescue.outcome);
  assert.equal(await hands.ledger.rung(OWNER, readHash, "gmail"), 2, "the pair keeps its rung after one failure");

  // -- SCENE 7 --------------------------------------------------------------
  // It breaks again. Two in a row is the ledger's demotion rule and the
  // router's; they must agree on the number, or the audit log says one thing
  // and the stored rung says another.
  const at7 = T0 + 900_000;
  const d7 = await hands.router.decide(READ, ctxAt(at7));
  assert.equal(d7.hand, "api");
  const failedAgain = await provider.execute(OWNER, d7.tool!.toolSlug, { query: "is:unread", max_results: 20 }, d7.accountId);
  assert.equal(failedAgain.ok, false);

  const plan7 = fallbackAfterApiFailure(
    { kind: failedAgain.error!.kind },
    { ...ctxAt(at7), consecutiveApiFailures: 2, rung: 2 },
  );
  assert.equal(plan7.action, "browser");
  assert.equal(plan7.demoteTo, 1);

  await hands.ledger.record(
    apiOutcome({ sig: READ, ctx: ctxAt(at7), app: "gmail", toolSlug: d7.tool!.toolSlug, result: failedAgain, verifierResult: "unknown", at: at7 }),
  );

  assert.equal(
    await hands.ledger.rung(OWNER, readHash, "gmail"),
    plan7.demoteTo,
    "the ledger's own demotion and the router's plan must land on the same rung",
  );

  // A demotion is two things, and the second one is the one that bites: shadow
  // re-opens, so the next read is supervised again and the pair pays the full
  // three parity matches to come back.
  const d8 = await hands.router.decide(READ, ctxAt(T0 + 1_000_000));
  assert.equal(d8.hand, "shadow", "a demotion re-opens shadow, it does not merely decrement a number");

  const stats = await hands.ledger.stats(OWNER, readHash, "gmail", "api");
  assert.equal(stats.length, 1);
  assert.equal(stats[0].n, 6, "four successes and two failures on the API hand");
  assert.equal(stats[0].successes, 4);
  assert.equal(stats[0].last_fail_reason, "other", "a machine kind, never the vendor's prose");
});

// ---------------------------------------------------------------------------
// The seams, each on its own leg.
// ---------------------------------------------------------------------------
// The story above would still pass if one of these regressed in a way that only
// showed up two scenes later. These fail at the seam itself.

test("an expired token does not demote a working capability", async () => {
  // THE FAILURE THIS PREVENTS, IN FULL: a refresh token ages out overnight, the
  // vendor 401s twice, the ledger reads two failures in a row, the pair falls a
  // rung, shadow re-opens, and the agent drives the browser for a week
  // re-earning ground it never lost — because one field was dropped between
  // `ExecResult.error.kind` and `Outcome.failKind`.
  const { hands, provider } = buildWorld();
  provider.connect([GMAIL_WORK]);
  await hands.onboarding.markConnected(OWNER, "gmail", T0);
  await hands.ledger.setRung(OWNER, READ.signature_hash, "gmail", 2);

  const authFailure: ExecResult = {
    ok: false,
    ms: 120,
    error: { kind: "auth", message: "401 invalid_grant: token expired" },
  };
  for (let i = 0; i < 2; i++) {
    const outcome = apiOutcome({
      sig: READ,
      ctx: ctxAt(T0 + i * 1000),
      app: "gmail",
      toolSlug: "GMAIL_FETCH_EMAILS",
      result: authFailure,
      verifierResult: "unknown",
      at: T0 + i * 1000,
    });
    assert.equal(outcome.failKind, "auth", "the provider's own kind must survive the trip to the ledger");
    assert.ok(
      !outcome.failReason?.includes("invalid_grant"),
      "the vendor's prose quotes our request back at us and must not reach the ledger",
    );
    await hands.ledger.record(outcome);
  }

  assert.equal(await hands.ledger.rung(OWNER, READ.signature_hash, "gmail"), 2);
});

test("the nudge counters survive a round trip through the ledger", async () => {
  // `asks` and `declines` are not columns of the contract's `ConnectNudge`, and
  // without them "a second decline is never-again" and "re-ask once" both
  // silently become "ask every fortnight for ever". They survive today only
  // because the in-memory table stores whole objects; on D1 they are two
  // columns somebody has to add, and this leg is the reminder.
  const { hands } = buildWorld();
  await hands.onboarding.wouldHaveUsed(OWNER, "notion");
  await hands.onboarding.markSent(OWNER, "notion", T0, "sms");
  await hands.onboarding.markDeclined(OWNER, "notion", T0 + 1000);
  await hands.onboarding.markSent(OWNER, "notion", T0 + 20 * 24 * 3600_000, "sms");
  await hands.onboarding.markDeclined(OWNER, "notion", T0 + 20 * 24 * 3600_000 + 1000);

  const row = await hands.onboarding.row(OWNER, "notion");
  assert.equal(row?.asks, 2, "the ask counter did not survive storage");
  assert.equal(row?.declines, 2, "the decline counter did not survive storage");

  const verdict = await hands.onboarding.shouldNudge("notion", {
    userId: OWNER,
    now: T0 + 40 * 24 * 3600_000,
    ownerTimeZone: "America/Los_Angeles",
    taskRunning: false,
    lastNudgeAnyAppAt: T0 + 20 * 24 * 3600_000,
  });
  assert.equal(verdict.verdict, "never-again");
  assert.equal(verdict.cause, "declined-twice", "two noes is a terminal state, not a longer wait");
});

test("a vendor that is down costs the API hand, never the task", async () => {
  // Pipedream was acquired, Klavis pivoted, Browser Use retired Skills with a
  // 410 inside a year. Every one of those is this test: the browser hand still
  // works, and nothing tells the owner to reconnect an app he connected last
  // month just because the vendor stopped answering.
  const hands = makeTwoHands({ provider: FakeProvider.down("vendor unreachable"), judge: tableJudge(STORY_JUDGE), now: () => T0 });
  const decision = await hands.router.decide(READ, ctxAt(T0));
  assert.equal(decision.hand, "browser");
  assert.equal(decision.rung, 0);
  assert.equal(decision.nudgeApp, undefined, "an unreachable vendor is not evidence about the owner's accounts");
  assert.equal(await hands.onboarding.row(OWNER, "gmail"), undefined, "and it accrues no nudge evidence either");
});

test("one decision costs one connections() call, not one per candidate", async () => {
  // The recording judge and the router both need to know what is connected. On
  // Composio that is an HTTP round trip inside a task the owner is watching,
  // and the naive wiring makes one per judged candidate.
  const { hands, provider } = buildWorld();
  provider.connect([GMAIL_WORK]);
  await hands.router.decide(READ, ctxAt(T0));
  const calls = provider.inner.calls.filter((c) => c.method === "connections");
  assert.equal(calls.length, 1, `one decision made ${calls.length} connection lookups`);
});

// ---------------------------------------------------------------------------
// THE ACCOUNT THE STEP RUNS AGAINST.
// ---------------------------------------------------------------------------
test("FINDING 3: account_hint is carried, asked about, and then ignored", async () => {
  // `CapabilitySignature.account_hint` is "work" | "personal" | null, and
  // `onboarding.accountChoice` exists, is tested, and correctly refuses to
  // guess from a label. NOTHING CALLS IT. The router takes the first ACTIVE
  // connection for the matched app, so with two mailboxes connected the hint is
  // decoration.
  //
  // The failure that is: moment 1 is "send Sam the deck", and the deck is on
  // the personal account. Today the step runs against whichever connection the
  // vendor happens to list first — which for a read is a wrong answer, and on
  // the write path is the dinner invitation going out from the work address.
  //
  // Why it is PINNED and not FIXED here: `accountChoice` returns "must-ask"
  // whenever the accounts are untagged, and `ConnectedApp` has no `kind`
  // column and there is no screen that would ever ask. Wiring it today would
  // turn every step into must-ask and take the API hand out entirely — a guard
  // that guards nothing by being infinitely strict. The fix is a column plus a
  // one-time question, in that order. This leg goes red the day somebody adds
  // them, which is when it should.
  const { hands, provider } = buildWorld();
  const GMAIL_PERSONAL: ConnectedApp = {
    app: "gmail",
    accountId: "conn-gmail-personal-0002",
    label: "personal@example.invalid",
    scopes: ["gmail.readonly"],
    status: "active",
  };
  provider.connect([GMAIL_WORK, GMAIL_PERSONAL]);
  await hands.onboarding.markConnected(OWNER, "gmail", T0);

  // account_hint is not in the hash, so this is the same capability as READ and
  // needs no new retrieval fixture. That is itself the contract working: "read
  // my work inbox" and "read my personal inbox" are one capability with two
  // accounts, not two capabilities.
  const personal = makeSignature({
    app_hint: READ.app_hint,
    verb: READ.verb,
    object: READ.object,
    inputs: READ.inputs,
    expected_effect: READ.expected_effect,
    side_effect: READ.side_effect,
    account_hint: "personal",
  });
  assert.equal(personal.signature_hash, READ.signature_hash);

  // deviceOnline:false so rule 3 puts the read on the API hand at any rung and
  // the decision actually names an account.
  const decision = await hands.router.decide(personal, ctxAt(T0 + 5000, false));
  assert.equal(decision.hand, "api");
  assert.equal(
    decision.accountId,
    GMAIL_WORK.accountId,
    "PINNED DEFECT: the step asked for the personal mailbox and got the first one listed",
  );

  // And the module that would have answered correctly is right there, unasked.
  const choice = hands.onboarding.accountChoice([decision.tool!], "personal", [GMAIL_WORK, GMAIL_PERSONAL]);
  assert.equal(
    choice.kind,
    "must-ask",
    "untagged accounts cannot be told apart, and a label is not evidence — so the honest answer is a question",
  );
});

// ---------------------------------------------------------------------------
// THE TEN-TASK GATE INPUT.
// ---------------------------------------------------------------------------
test("the ten read tasks are ten distinct read capabilities, hashed by the real function", () => {
  // The gate's input, checked by the same function the router keys on. A task
  // file whose hashes have drifted files every run under a hash nothing else
  // computes: ten rungs earned, none ever read, and every row still green.
  // run_ten.ts re-derives these at startup too; this leg is here so the check
  // runs in a suite with no key, on every commit.
  const doc = JSON.parse(readFileSync(new URL("../tasks/ten_read_tasks.json", import.meta.url), "utf8"));
  assert.equal(doc.gate.min_correct, 9);
  assert.equal(doc.gate.of, 10);
  assert.equal(doc.gate.p50_ms_max, 3000);
  assert.equal(doc.tasks.length, 10);

  const hashes = new Set<string>();
  for (const task of doc.tasks) {
    const rebuilt = makeSignature({
      app_hint: task.signature.app_hint,
      verb: task.signature.verb,
      object: task.signature.object,
      inputs: task.signature.inputs,
      expected_effect: task.signature.expected_effect,
      side_effect: task.signature.side_effect,
      account_hint: task.signature.account_hint,
    });
    assert.equal(rebuilt.signature_hash, task.signature.signature_hash, `${task.id}: stored hash disagrees with makeSignature`);
    // The seatbelt on the gate's own input. This harness runs against a real
    // mailbox with no confirmation step and no undo, so a write reaching this
    // file must fail here rather than at 3am against his Sent folder.
    assert.equal(rebuilt.side_effect, "read", `${task.id} is not a read`);
    assert.ok(!hashes.has(rebuilt.signature_hash), `${task.id} duplicates another task's capability`);
    hashes.add(rebuilt.signature_hash);
    // Grading must not be vibes: every task says what right looks like, what
    // the response can settle, and what only the owner can.
    assert.ok(task.how_to_grade.right_is.length > 20, `${task.id}: how_to_grade.right_is is too thin to grade against`);
    assert.ok(task.how_to_grade.checkable_from_the_response.length >= 2, `${task.id}: nothing checkable`);
    assert.ok(task.how_to_grade.only_the_owner_can_confirm.length >= 1, `${task.id}: no completeness question`);
  }

  // Four apps, so the gate is not ten variations of one connector working.
  const apps = new Set(doc.tasks.map((t: { signature: { app_hint: string } }) => t.signature.app_hint));
  assert.ok(apps.size >= 4, `the ten tasks cover only ${apps.size} app(s)`);
});

// ---------------------------------------------------------------------------
// THE HARNESS'S THIRD STATE — HARNESS-LAWS law 3, on a leg.
// ---------------------------------------------------------------------------
test("with no key the live harness prints UNPROVEN, exits 2, and prints no table", () => {
  // The single most important promise in this spike, and the one that is
  // easiest to lose in a refactor: a run that could not happen must never be
  // reported as one that did. A table is what gets screenshotted, and an empty
  // table is indistinguishable from a full one at a glance a week later.
  //
  // The keys are cleared explicitly rather than assumed absent. On the day the
  // owner sets them, a test that merely inherited the environment would start
  // making live calls to Composio from `node --test` — billing him for a unit
  // test and, worse, quietly turning this leg into a live run whose failure
  // would read as a bug in the fence.
  const run = spawnSync(
    process.execPath,
    ["--experimental-strip-types", fileURLToPath(new URL("../tasks/run_ten.ts", import.meta.url))],
    {
      encoding: "utf8",
      env: { ...process.env, COMPOSIO_API_KEY: "", OPENROUTER_API_KEY: "" },
      timeout: 60_000,
    },
  );

  assert.equal(run.status, 2, `the gate exited ${run.status}; 2 is UNPROVEN, 0 is a pass and 1 is a measured failure`);
  const out = `${run.stdout}${run.stderr}`;
  assert.match(out, /UNPROVEN/);
  assert.match(out, /COMPOSIO_API_KEY is not set/);
  // No table: not a header, not a separator row, not one formatted number.
  assert.ok(!out.includes("| task | tool |"), "a run that could not happen printed a table");
  assert.ok(!/\|\s*-+\s*\|/.test(out), "a run that could not happen printed a table separator");
  assert.ok(!/\$\d/.test(out), "a run that could not happen printed a cost");
});
