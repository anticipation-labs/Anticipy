// WHAT THIS SUITE IS FOR.
//
// The Observer's whole value is a promise about what it does NOT keep, and a
// promise is worth exactly the test that would fail if it were broken. So the
// privacy half of this file is written as an adversary: it feeds the Observer a
// password-reset link, a presigned URL with a signature in the query, a
// credential in the authority, and event objects carrying page text and
// response bodies as extra fields — and then searches the ENTIRE serialized
// summary for each secret. A test that only checked `hosts` would pass while a
// new field leaked the lot.
//
// No network, no key, no account, no chrome. Every event is a plain object.

import test from "node:test";
import assert from "node:assert/strict";

import {
  createObserver,
  disclosureCopy,
  MAX_RETAINED_STEPS,
  readHost,
  registrableDomain,
} from "../src/observer.ts";
import type { NavigationEvent, ObservedEvent, RequestEvent } from "../src/observer.ts";
import type { Observer, TraceSummary } from "../src/contract.ts";

const RUN = "run-1";
const STEP = "step-1";

function req(over: Partial<RequestEvent> = {}): RequestEvent {
  return {
    kind: "request",
    run_id: RUN,
    step_id: STEP,
    method: "GET",
    url: "https://example.com/",
    status: 200,
    at: 1_000,
    ms: 10,
    ...over,
  } as RequestEvent;
}

function nav(over: Partial<NavigationEvent> = {}): NavigationEvent {
  return {
    kind: "navigation",
    run_id: RUN,
    step_id: STEP,
    url: "https://example.com/",
    at: 1_000,
    ...over,
  } as NavigationEvent;
}

function summarize(events: readonly ObservedEvent[]): TraceSummary {
  const observer = createObserver();
  observer.observeAll(events);
  return observer.summarize(RUN, STEP);
}

// ---------------------------------------------------------------------------
// THE SHAPE — exactly the contract's TraceSummary, no more.
// ---------------------------------------------------------------------------

test("the summary carries exactly the contract's fields and nothing else", () => {
  // This is the privacy test that keeps working after someone adds a field. If
  // a future edit puts `urls`, `titles` or `sample` on the summary, this fails
  // before it can reach a server.
  const summary = summarize([req()]);
  assert.deepEqual(
    Object.keys(summary).sort(),
    ["duration_ms", "hosts", "reads", "run_id", "status", "step_id", "writes"],
  );
});

test("it satisfies the contract's Observer at runtime, not only in the types", () => {
  // Types are stripped, not checked, under --experimental-strip-types. A
  // structural claim nobody executes is a comment.
  const observer: Observer = createObserver();
  assert.equal(typeof observer.summarize, "function");
  const summary = observer.summarize(RUN, STEP);
  assert.equal(summary.run_id, RUN);
  assert.equal(summary.step_id, STEP);
});

test("a step nobody observed summarizes as empty rather than throwing", () => {
  // The router asks after EVERY browser step, including ones where the page
  // only moved the DOM. A throw here surfaces to the owner as a failed task.
  const summary = createObserver().summarize("run-none", "step-none");
  assert.deepEqual(summary, {
    run_id: "run-none",
    step_id: "step-none",
    hosts: [],
    writes: 0,
    reads: 0,
    status: {},
    duration_ms: 0,
  });
});

// ---------------------------------------------------------------------------
// WAS IT A WRITE — the effect channel, and only the effect channel.
// ---------------------------------------------------------------------------

test("a mutating method that came back 2xx is a write", () => {
  for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
    const summary = summarize([req({ method, status: 200 })]);
    assert.equal(summary.writes, 1, `${method} 200 should be a write`);
    assert.equal(summary.reads, 0, `${method} 200 should not also be a read`);
  }
});

test("204 counts as a write - the 2xx family, not the literal 200", () => {
  // DELETE almost always answers 204. A check for `status === 200` would score
  // every successful delete as a read and the router would never learn that the
  // step mutated anything.
  assert.equal(summarize([req({ method: "DELETE", status: 204 })]).writes, 1);
  assert.equal(summarize([req({ method: "POST", status: 201 })]).writes, 1);
});

test("a mutating method that did NOT come back 2xx is a read, not a write", () => {
  // Nothing was written. Scoring a 403 POST as a write would teach the router
  // that an app the owner cannot reach is an app it is succeeding at, and the
  // first API suggestion he ever saw would be for a login he does not have.
  for (const status of [302, 401, 403, 429, 500]) {
    const summary = summarize([req({ method: "POST", status })]);
    assert.equal(summary.writes, 0, `POST ${status} must not be a write`);
    assert.equal(summary.reads, 1, `POST ${status} must be a read`);
  }
});

test("GET, HEAD and an unknown method are reads at any status", () => {
  // An unrecognised verb landing in `reads` under-claims writes, which is the
  // safe direction: these counts feed learning, never licensing.
  for (const method of ["GET", "HEAD", "OPTIONS", "MKCOL", ""]) {
    const summary = summarize([req({ method, status: 200 })]);
    assert.equal(summary.writes, 0, `${method || "(blank)"} must not be a write`);
    assert.equal(summary.reads, 1);
  }
});

test("the method is read case-insensitively and untrimmed", () => {
  // chrome.webRequest is consistent about case; a replayed or hand-built event
  // is not, and a lowercase "post" silently scoring as a read is the kind of
  // miscount nobody would ever look for.
  assert.equal(summarize([req({ method: "post", status: 200 })]).writes, 1);
  assert.equal(summarize([req({ method: " Delete ", status: 200 })]).writes, 1);
});

test("a navigation contributes a host and a clock but never a read or a write", () => {
  // The page load a navigation starts arrives separately as a request event.
  // Counting both would double every top-level GET.
  const summary = summarize([nav({ url: "https://news.bbc.co.uk/politics" })]);
  assert.deepEqual(summary.hosts, ["bbc.co.uk"]);
  assert.equal(summary.reads, 0);
  assert.equal(summary.writes, 0);
  assert.deepEqual(summary.status, {});
});

// ---------------------------------------------------------------------------
// STATUS — buckets, never codes.
// ---------------------------------------------------------------------------

test("statuses are bucketed and the individual codes never appear", () => {
  const summary = summarize([
    req({ status: 200 }), req({ status: 201 }),
    req({ status: 301 }),
    req({ status: 404 }),
    req({ status: 503 }),
  ]);
  assert.deepEqual(summary.status, { "2xx": 2, "3xx": 1, "4xx": 1, "5xx": 1 });
  // "404 on accounts.google.com" is a fact about the owner's account. "one 4xx
  // on google.com" is not. The difference is this assertion.
  const serialized = JSON.stringify(summary);
  for (const code of ["200", "201", "301", "404", "503"]) {
    assert.ok(!serialized.includes(`"${code}"`), `status code ${code} leaked as a key`);
  }
});

test("a request with no status at all is counted in an 'other' bucket, not dropped", () => {
  // A DNS failure or an aborted fetch arrives as status 0. Dropping it would
  // make a step that died on the network look like a step where nothing
  // happened — a silence that reads as calm, which is how the ears once stayed
  // deaf for thirty hours.
  const summary = summarize([
    req({ status: 0 }),
    req({ status: Number.NaN as unknown as number }),
    req({ status: 999 }),
  ]);
  assert.deepEqual(summary.status, { other: 3 });
  assert.equal(summary.reads, 3);
});

test("status buckets come out in a stable order for identical traces", () => {
  // The ledger hashes what it is given; two identical traces must serialize to
  // identical bytes or one capability's evidence splits across two rows.
  const events = [req({ status: 500 }), req({ status: 200 }), req({ status: 404 })];
  const forward = JSON.stringify(summarize(events));
  const backward = JSON.stringify(summarize([...events].reverse()));
  assert.equal(forward, backward);
});

// ---------------------------------------------------------------------------
// WHICH APP — eTLD+1, and only eTLD+1.
// ---------------------------------------------------------------------------

test("registrableDomain reduces a hostname to the registrable domain", () => {
  const cases: Array<[string, string | null]> = [
    ["https://example.com/", "example.com"],
    ["https://mail.google.com/mail/u/0/#inbox", "google.com"],
    ["https://a.b.c.google.com/x", "google.com"],
    // multi-part public suffixes: the whole reason a list exists here
    ["https://news.bbc.co.uk/politics", "bbc.co.uk"],
    ["https://example.co.uk/", "example.co.uk"],
    ["https://shop.example.com.au/cart", "example.com.au"],
    ["https://www.company.co.nz/", "company.co.nz"],
    ["https://a.b.example.co.jp/", "example.co.jp"],
    // a tenant subdomain is NOT a private suffix here, on purpose: the tenant
    // label is the owner's employer's name and the app is the same app.
    ["https://acme.atlassian.net/browse/ENG-1", "atlassian.net"],
    ["https://acme.myshopify.com/admin", "myshopify.com"],
    // plumbing edges
    ["https://GOOGLE.COM/", "google.com"],
    ["https://google.com./", "google.com"],
    ["http://localhost:3000/x", "localhost"],
    ["http://192.168.1.10:8080/x", "192.168.1.10"],
    ["http://[::1]:8080/x", "[::1]"],
    // no app to name
    ["chrome-extension://abcdefg/background.html", null],
    ["data:text/html,<h1>hi</h1>", null],
    ["blob:https://example.com/9a7f", null],
    ["file:///Users/owner/Documents/tax.pdf", null],
    ["not a url at all", null],
    ["", null],
  ];
  for (const [input, expected] of cases) {
    assert.equal(registrableDomain(input), expected, `registrableDomain(${input})`);
  }
});

test("registrableDomain survives a caller passing something that is not a string", () => {
  // Types are stripped. A chrome.webRequest payload that changed shape between
  // Chrome versions must not throw inside a listener — a thrown error there
  // kills the listener and the Observer goes silently deaf for the session.
  for (const bad of [null, undefined, 42, {}, []]) {
    assert.equal(registrableDomain(bad as unknown as string), null);
  }
});

test("subdomains of one app collapse into one host, and the step still names only one app", () => {
  // mail/calendar/drive share one Google connection. Three hosts would mean the
  // ledger never accumulates enough runs on any one of them to leave rung 0.
  // Stripe is here to prove the second half: the summary answers "which app was
  // this step in" with ONE app, and three Google requests beat one Stripe one.
  const summary = summarize([
    req({ url: "https://mail.google.com/a" }),
    req({ url: "https://calendar.google.com/b" }),
    req({ url: "https://drive.google.com/c" }),
    req({ url: "https://api.stripe.com/v1/charges" }),
  ]);
  assert.deepEqual(summary.hosts, ["google.com"]);
  assert.equal(summary.reads, 4, "the Stripe request is unnamed, not uncounted");
});

test("a request the Observer cannot name a site for is dropped whole, counts included", () => {
  // An invented host is worse than a missing one: the router would go shopping
  // for an API for an app that was never touched.
  const summary = summarize([
    req({ url: "chrome-extension://abc/sw.js", method: "POST", status: 200 }),
    req({ url: "blob:https://example.com/9a7f", status: 200 }),
    req({ url: "://////", status: 200 }),
    req({ url: undefined as unknown as string, status: 200 }),
  ]);
  assert.deepEqual(summary, {
    run_id: RUN,
    step_id: STEP,
    hosts: [],
    writes: 0,
    reads: 0,
    status: {},
    duration_ms: 0,
  });
});

// ---------------------------------------------------------------------------
// THE PROMISE — what must never survive.
// ---------------------------------------------------------------------------

/** Search the WHOLE serialized summary, not one field. A leak that a future
 *  edit introduces will land in a field this test does not know the name of. */
function assertAbsent(summary: TraceSummary, secrets: readonly string[]): void {
  const serialized = JSON.stringify(summary);
  for (const secret of secrets) {
    assert.ok(
      !serialized.toLowerCase().includes(secret.toLowerCase()),
      `"${secret}" survived into the summary: ${serialized}`,
    );
  }
}

test("a password-reset link does not survive, not even as a host and path", () => {
  const summary = summarize([
    nav({ url: "https://accounts.example.co.uk/password/reset?token=SEKRIT-9f2a&email=owner%40home.test" }),
    req({
      url: "https://accounts.example.co.uk/password/reset/confirm?token=SEKRIT-9f2a",
      method: "POST",
      status: 200,
    }),
  ]);
  assert.deepEqual(summary.hosts, ["example.co.uk"]);
  assert.equal(summary.writes, 1);
  assertAbsent(summary, [
    "SEKRIT-9f2a", "token", "reset", "password", "confirm", "owner", "home.test",
    "accounts.", "?", "=", "/password",
  ]);
});

test("a presigned URL's signature never appears", () => {
  const summary = summarize([
    req({
      url: "https://files.example.com/private/2026/payslip.pdf"
        + "?X-Amz-Credential=AKIAEXAMPLE&X-Amz-Signature=deadbeefcafe&X-Amz-Expires=900",
      status: 200,
    }),
  ]);
  assert.deepEqual(summary.hosts, ["example.com"]);
  assertAbsent(summary, [
    "X-Amz", "AKIAEXAMPLE", "deadbeefcafe", "payslip", "private", ".pdf",
  ]);
});

test("a credential in the URL authority never appears", () => {
  // https://user:token@host/ is a real shape, and reading `href` or `host`
  // instead of `hostname` would carry it straight through.
  const summary = summarize([req({ url: "https://owner:hunter2@intranet.example.com/x" })]);
  assert.deepEqual(summary.hosts, ["example.com"]);
  assertAbsent(summary, ["hunter2", "owner", "@", "intranet"]);
});

test("a search query never appears", () => {
  const summary = summarize([
    nav({ url: "https://www.google.com/search?q=am+i+being+laid+off&hl=en" }),
  ]);
  assert.deepEqual(summary.hosts, ["google.com"]);
  assertAbsent(summary, ["laid+off", "laid", "search", "q=", "hl="]);
});

test("bodies, titles, page text and cookies handed to it on the event are never stored", () => {
  // Nothing reads these keys, so this cannot regress by accident — but the
  // whole disclosure rests on it, and a promise with no failing test is a
  // comment. `path_shape` is in the list on purpose: the Observer accepts it
  // from the webRequest listener and throws it away, because even
  // "/password/reset/{token}" tells a later reader which flow the owner was in.
  const noisy = {
    ...req({ method: "POST", status: 200 }),
    path_shape: "/password/reset/{token}",
    requestBody: "{\"card\":\"4111111111111111\"}",
    responseBody: "{\"balance\":\"93.20\"}",
    cookies: "session=abc123",
    title: "Your account - Example Bank",
    pageText: "Balance ninety three pounds twenty",
    referrer: "https://mail.google.com/mail/u/0/#inbox",
  } as unknown as ObservedEvent;

  const summary = summarize([noisy]);
  assert.deepEqual(summary.hosts, ["example.com"]);
  assert.equal(summary.writes, 1);
  assertAbsent(summary, [
    "4111111111111111", "93.20", "session=abc123", "Example Bank", "ninety three",
    "requestBody", "responseBody", "cookies", "title", "pageText", "referrer",
    "path_shape", "{token}", "mail.google.com",
  ]);
});

test("no path, no query and no fragment survives from any ordinary URL either", () => {
  const summary = summarize([
    req({ url: "https://example.com/orders/7781/items?ref=email#line-3" }),
  ]);
  assert.deepEqual(summary.hosts, ["example.com"]);
  assertAbsent(summary, ["/orders", "7781", "items", "ref=email", "#line-3", "/"]);
});

// ---------------------------------------------------------------------------
// SCOPE — one step's trace is one step's trace.
// ---------------------------------------------------------------------------

test("another step's events never bleed into this step's summary", () => {
  const observer = createObserver();
  observer.observeAll([
    req({ step_id: "step-1", url: "https://google.com/a", method: "POST", status: 200 }),
    req({ step_id: "step-2", url: "https://stripe.com/b", method: "POST", status: 200 }),
  ]);
  const first = observer.summarize(RUN, "step-1");
  assert.deepEqual(first.hosts, ["google.com"]);
  assert.equal(first.writes, 1);
  const second = observer.summarize(RUN, "step-2");
  assert.deepEqual(second.hosts, ["stripe.com"]);
  assert.equal(second.writes, 1);
});

test("the same step id under a different run is a different trace", () => {
  // Step ids restart per run in the agent loop. Keying on step alone would fold
  // yesterday's run into today's.
  const observer = createObserver();
  observer.observeAll([
    req({ run_id: "run-a", step_id: "s1", url: "https://google.com/a" }),
    req({ run_id: "run-b", step_id: "s1", url: "https://stripe.com/b" }),
  ]);
  assert.deepEqual(observer.summarize("run-a", "s1").hosts, ["google.com"]);
  assert.deepEqual(observer.summarize("run-b", "s1").hosts, ["stripe.com"]);
});

test("ids containing spaces, colons or dashes cannot collide into one trace", () => {
  // The store is a Map keyed by run and step joined together, so the joiner has
  // to be a character the ids cannot contain. A space or a ":" is not: run
  // "a b" step "c" and run "a" step "b c" are two different steps, and folding
  // them into one row would credit one step's writes to another.
  const observer = createObserver();
  observer.observeAll([
    req({ run_id: "a b", step_id: "c", url: "https://google.com/x" }),
    req({ run_id: "a", step_id: "b c", url: "https://stripe.com/x" }),
    req({ run_id: "x:y", step_id: "z", url: "https://plaid.com/x" }),
    req({ run_id: "x", step_id: "y:z", url: "https://ramp.com/x" }),
  ]);
  assert.deepEqual(observer.summarize("a b", "c").hosts, ["google.com"]);
  assert.deepEqual(observer.summarize("a", "b c").hosts, ["stripe.com"]);
  assert.deepEqual(observer.summarize("x:y", "z").hosts, ["plaid.com"]);
  assert.deepEqual(observer.summarize("x", "y:z").hosts, ["ramp.com"]);
});

test("summarize is a read: calling it twice, or mutating what it returned, changes nothing", () => {
  // The router summarizes, hands the summary on, and may summarize the same
  // step again when a retry lands. If `hosts` were the Set's own backing array,
  // a caller sorting or splicing it in place would silently rewrite the trace
  // the ledger is about to key on.
  const observer = createObserver();
  observer.observe(req({ url: "https://google.com/a", method: "POST", status: 200 }));
  const first = observer.summarize(RUN, STEP);
  first.hosts.push("evil.example.com");
  first.hosts.sort();
  first.status["2xx"] = 99;
  const second = observer.summarize(RUN, STEP);
  assert.deepEqual(second.hosts, ["google.com"]);
  assert.deepEqual(second.status, { "2xx": 1 });
  assert.equal(second.writes, 1);
});

test("an event with no run or no step id is dropped, not attributed to a neighbour", () => {
  // A request seen outside an agent run is the owner's own browsing. Filing it
  // under "the last step we saw" would break the sentence the disclosure makes.
  const observer = createObserver();
  observer.observeAll([
    req({ url: "https://google.com/a" }),
    req({ run_id: "", url: "https://stripe.com/b" }),
    req({ step_id: "", url: "https://plaid.com/c" }),
    req({ run_id: undefined as unknown as string, url: "https://ramp.com/d" }),
    null as unknown as ObservedEvent,
    "oops" as unknown as ObservedEvent,
  ]);
  const summary = observer.summarize(RUN, STEP);
  assert.deepEqual(summary.hosts, ["google.com"]);
  assert.equal(summary.reads, 1);
  assert.deepEqual(observer.steps(), [{ run_id: RUN, step_id: STEP }]);
});

// ---------------------------------------------------------------------------
// THE CLOCK.
// ---------------------------------------------------------------------------

test("duration spans the first thing seen to the last thing that finished", () => {
  const summary = summarize([
    req({ at: 1_000, ms: 50 }),
    req({ at: 1_200, ms: 800 }),   // started later, finished last: 2000
    req({ at: 1_500, ms: 10 }),
  ]);
  assert.equal(summary.duration_ms, 1_000);
});

test("out-of-order arrivals still produce the true span", () => {
  // chrome.webRequest fires onCompleted in completion order, not start order,
  // so "first event seen" is not "earliest event".
  const summary = summarize([
    req({ at: 5_000, ms: 10 }),
    req({ at: 1_000, ms: 10 }),
  ]);
  assert.equal(summary.duration_ms, 4_010);
});

test("a missing or nonsense timestamp cannot make the duration NaN or negative", () => {
  const summary = summarize([
    req({ at: undefined as unknown as number, ms: undefined }),
    req({ at: 2_000, ms: -5 }),
    req({ at: "later" as unknown as number }),
  ]);
  assert.equal(Number.isFinite(summary.duration_ms), true);
  assert.ok(summary.duration_ms >= 0);
  assert.equal(summary.reads, 3, "an untimed request is still a request");
});

// ---------------------------------------------------------------------------
// THE PAUSE SWITCH — the disclosure promises it, so it has to be real.
// ---------------------------------------------------------------------------

test("pause drops events at ingest, and resume starts recording again", () => {
  // A pause that keeps recording and hides the result at read time is not a
  // pause, it is a lie with a checkbox — and the whole Limited Use disclosure
  // rests on this one being true.
  const observer = createObserver();
  observer.observe(req({ url: "https://google.com/a" }));
  observer.pause();
  assert.equal(observer.paused, true);
  observer.observe(req({ url: "https://stripe.com/b", method: "POST", status: 200 }));
  observer.observe(nav({ url: "https://plaid.com/c" }));

  const whilePaused = observer.summarize(RUN, STEP);
  assert.deepEqual(whilePaused.hosts, ["google.com"]);
  assert.equal(whilePaused.writes, 0);
  assert.equal(whilePaused.reads, 1);

  observer.resume();
  assert.equal(observer.paused, false);
  // A write, so the resumed event takes the one host slot outright rather than
  // tying with the pre-pause read and being settled alphabetically. The point
  // under test is that recording restarted, and it should not rest on a
  // tiebreak.
  observer.observe(req({ url: "https://ramp.com/d", method: "POST", status: 200 }));
  const afterResume = observer.summarize(RUN, STEP);
  assert.deepEqual(afterResume.hosts, ["ramp.com"]);
  assert.equal(afterResume.writes, 1, "the write made after resume was recorded");
  assert.equal(afterResume.reads, 1, "and the paused ones still were not");
});

test("a step observed entirely while paused summarizes as empty", () => {
  const observer = createObserver();
  observer.pause();
  observer.observe(req({ url: "https://google.com/a" }));
  assert.deepEqual(observer.summarize(RUN, STEP).hosts, []);
  assert.deepEqual(observer.steps(), []);
});

test("forget drops a finished run and leaves other runs alone", () => {
  // The service worker lives for hours across dozens of runs. Without this the
  // Map is a leak that also happens to be a growing record of where the owner
  // has been.
  const observer = createObserver();
  observer.observeAll([
    req({ run_id: "run-a", step_id: "s1", url: "https://google.com/x" }),
    req({ run_id: "run-a", step_id: "s2", url: "https://google.com/y" }),
    req({ run_id: "run-b", step_id: "s1", url: "https://stripe.com/z" }),
  ]);
  observer.forget("run-a");
  assert.deepEqual(observer.steps(), [{ run_id: "run-b", step_id: "s1" }]);
  assert.deepEqual(observer.summarize("run-a", "s1").hosts, []);
  assert.deepEqual(observer.summarize("run-b", "s1").hosts, ["stripe.com"]);
});

test("forget matches on the whole run id, not a prefix of one", () => {
  const observer = createObserver();
  observer.observeAll([
    req({ run_id: "run-1", step_id: "s", url: "https://google.com/x" }),
    req({ run_id: "run-10", step_id: "s", url: "https://stripe.com/y" }),
  ]);
  observer.forget("run-1");
  assert.deepEqual(observer.steps(), [{ run_id: "run-10", step_id: "s" }]);
});

// ---------------------------------------------------------------------------
// WHICH APP WAS THIS STEP IN — ONE ANSWER, NOT A PAGE FINGERPRINT.
// ---------------------------------------------------------------------------
// `hosts` used to be every registrable domain the step touched. On a modern
// page that is the app plus its CDN, its fonts, its analytics, its error
// reporter and whoever bought the ad slot — a list that describes the PAGE, and
// through it the person, far past the one question the router asked. These
// tests hold the summary to a single answer and pin the precedence that picks
// it, because a rule nobody can predict is a rule nobody can audit.

test("the summary names ONE host, not every domain the page happened to touch", () => {
  const summary = summarize([
    nav({ url: "https://mail.google.com/mail/u/0/" }),
    req({ url: "https://mail.google.com/sync/i/fd" }),
    req({ url: "https://fonts.gstatic.com/s/roboto.woff2" }),
    req({ url: "https://www.google-analytics.com/collect" }),
    req({ url: "https://cdn.doubleclick.net/px" }),
    req({ url: "https://o1.ingest.sentry.io/api/1/envelope" }),
    req({ url: "https://ads.adnxs.com/ttj" }),
  ]);
  assert.deepEqual(summary.hosts, ["google.com"]);
  // The third parties are not hidden, they are just not NAMED: every request is
  // still counted, so a step is never made to look quieter than it was.
  assert.equal(summary.reads, 6);
});

test("a third party cannot outvote the document the step was actually in", () => {
  // Forty CDN requests against one navigation and one XHR. Ranking by volume
  // alone would file this Notion step under Segment's name.
  const events: ObservedEvent[] = [nav({ url: "https://www.notion.so/workspace" })];
  for (let i = 0; i < 40; i += 1) events.push(req({ url: `https://cdn.segment.com/a/${i}` }));
  events.push(req({ url: "https://www.notion.so/api/v3/loadPage", method: "POST", status: 200 }));
  assert.deepEqual(summarize(events).hosts, ["notion.so"]);
});

test("with no navigation, the host that carried the writes takes the slot", () => {
  // An SPA step that only fires XHRs has no navigation to go on. The write is
  // the effect the router is asking about, so it outranks any amount of
  // read-only chatter from an asset host.
  const events: ObservedEvent[] = [];
  for (let i = 0; i < 30; i += 1) events.push(req({ url: `https://cdn.cloudfront.net/a/${i}` }));
  events.push(req({ url: "https://api.stripe.com/v1/charges", method: "POST", status: 200 }));
  assert.deepEqual(summarize(events).hosts, ["stripe.com"]);
});

test("with no navigation and no write the busiest host wins, and a tie breaks identically every time", () => {
  const busier = summarize([
    req({ url: "https://stripe.com/a" }),
    req({ url: "https://stripe.com/b" }),
    req({ url: "https://google.com/c" }),
  ]);
  assert.deepEqual(busier.hosts, ["stripe.com"]);

  // The ledger hashes what it is given. A tie broken by "whichever XHR finished
  // first" would make two identical traces two different rows.
  const tied = [req({ url: "https://ramp.com/a" }), req({ url: "https://google.com/b" })];
  assert.deepEqual(summarize(tied).hosts, ["google.com"]);
  assert.equal(JSON.stringify(summarize(tied)), JSON.stringify(summarize([...tied].reverse())));
});

test("however many domains one step touches, the summary carries at most one", () => {
  // The bound is the point. Two hundred distinct domains in one step is an ad
  // page, and the old summary would have shipped all two hundred.
  const events: ObservedEvent[] = [];
  for (let i = 0; i < 200; i += 1) events.push(req({ url: `https://s${i}.example-${i}.com/x` }));
  const summary = summarize(events);
  assert.equal(summary.hosts.length, 1, "hosts is an answer, not a page fingerprint");
  assert.equal(summary.reads, 200, "and every request still counts");
});

// ---------------------------------------------------------------------------
// THE SUFFIX LIST IS A COPY, AND A COPY IS BEHIND. SAY SO OUT LOUD.
// ---------------------------------------------------------------------------
// MULTI_LABEL_SUFFIXES is a hand-cut copy of the ICANN half of the public
// suffix list. For every suffix it does not carry, taking the last two labels
// returns the SUFFIX ITSELF as if it were a site — and every unrelated site
// under it merges into one bucket, which is verbatim the failure the list
// exists to prevent. These are real, current omissions, written down so the
// gap is a documented state rather than a silent wrong answer.
const UNKNOWN_SUFFIX_EXAMPLES: ReadonlyArray<readonly [string, string]> = [
  ["https://www.example.com.gr/politics", "com.gr"],   // Greece
  ["https://shop.example.com.vn/x", "com.vn"],         // Vietnam
  ["https://mail.example.com.pk/x", "com.pk"],         // Pakistan
  ["https://portal.example.com.bd/x", "com.bd"],       // Bangladesh
  ["https://www.example.nhs.uk/x", "nhs.uk"],          // the NHS
  ["https://www.example.ac.at/x", "ac.at"],            // Austria
  ["https://www.example.co.ug/x", "co.ug"],            // Uganda
];

test("a host under a public suffix the list does not carry is reported as unknown, never as the suffix", () => {
  for (const [url, suffix] of UNKNOWN_SUFFIX_EXAMPLES) {
    assert.equal(registrableDomain(url), null, `${url}: an unknown suffix must not be guessed at`);
    assert.notEqual(registrableDomain(url), suffix, `${url} collapsed into the bare suffix ${suffix}`);
  }
});

test("two unrelated sites under an unknown suffix do not become one app, and their requests still count", () => {
  // The old behaviour filed a bank and a clinic under one host called
  // "com.gr". Reporting no host at all is the honest answer; dropping the
  // requests as well would be a second wrong answer on top of it.
  const summary = summarize([
    req({ url: "https://www.a-bank.com.gr/login", method: "POST", status: 200 }),
    req({ url: "https://www.a-clinic.com.gr/records" }),
  ]);
  assert.deepEqual(summary.hosts, [], "unknown is reported as unknown");
  assert.equal(summary.writes, 1, "the effect still counts even when the app cannot be named");
  assert.equal(summary.reads, 1);
  assert.deepEqual(summary.status, { "2xx": 2 });
});

test("the unknown-suffix rule fires only where a boundary is actually being drawn", () => {
  for (const [url, expected] of [
    // ordinary subdomains: nothing registrar-shaped, nothing changes
    ["https://acme.atlassian.net/browse/ENG-1", "atlassian.net"],
    ["https://a.b.c.google.com/x", "google.com"],
    ["https://mail.example.io/x", "example.io"],
    ["https://x.company.de/x", "company.de"],
    // a suffix the list DOES carry still resolves through it
    ["https://news.bbc.co.uk/politics", "bbc.co.uk"],
    ["https://a.b.example.co.jp/", "example.co.jp"],
    // two labels is the whole name the browser was given; no boundary is being
    // chosen, so there is nothing to be unsure about
    ["http://com.gr/", "com.gr"],
    ["http://localhost:3000/x", "localhost"],
  ] as ReadonlyArray<readonly [string, string]>) {
    assert.equal(registrableDomain(url), expected, `registrableDomain(${url})`);
  }
});

test("a site we cannot name still beats a third party we can, so the app is never a bystander", () => {
  // The step ran in a Greek bank whose suffix this file's copy does not carry.
  // Every OTHER host on the page is nameable — the CDN, the fonts — and if the
  // unnameable document simply sat out the contest, the summary would confidently
  // report the step as having happened in Cloudflare. Reporting a bystander as
  // the app is the same failure as inventing one: the router goes shopping for
  // an API for something the owner never used. "Unknown" competes, and wins.
  const events: ObservedEvent[] = [nav({ url: "https://www.a-bank.com.gr/accounts" })];
  for (let i = 0; i < 20; i += 1) events.push(req({ url: `https://cdn.cloudflare.com/a/${i}` }));
  const summary = summarize(events);
  assert.deepEqual(summary.hosts, [], "the document could not be named, so nothing is named");
  assert.equal(summary.reads, 20);
});

test("a tie between a nameable bystander and an unnameable one resolves to unknown", () => {
  // Same reasoning one rung down: with nothing to separate them, the honest
  // answer is that we do not know which app this was.
  const summary = summarize([
    req({ url: "https://cdn.cloudflare.com/a" }),
    req({ url: "https://www.a-bank.com.gr/b" }),
  ]);
  assert.deepEqual(summary.hosts, []);
});

test("the rule's own cost, written down rather than discovered", () => {
  // `.it` has no `co.it` public suffix, so `co.it` IS the registrable domain of
  // www.example.co.it and the old code got it right. The new rule refuses to
  // name it, because it cannot tell that case from `com.gr`. The trade: one
  // host lost on an unusual name, against every site under an unknown ccTLD
  // suffix silently merging into one. It is a test so the trade stays visible.
  assert.equal(registrableDomain("https://www.example.co.it/x"), null);
});

// ---------------------------------------------------------------------------
// RELEASE — the promise not to accumulate, kept by the code rather than by a
// caller who might never come.
// ---------------------------------------------------------------------------
// `forget()` on its own is a request. Until something calls it, the service
// worker holds every step of every run it has ever seen — the slowly growing
// record of where the owner has been that this module exists to not keep. Two
// things close that: a consuming read for the caller that knows a step is
// finished, and a hard cap for the times nobody tells us.

test("summarizeAndForget hands back the trace and releases it in the same breath", () => {
  const observer = createObserver();
  observer.observe(req({ url: "https://google.com/a", method: "POST", status: 200 }));
  const summary = observer.summarizeAndForget(RUN, STEP);
  assert.deepEqual(summary.hosts, ["google.com"]);
  assert.equal(summary.writes, 1);
  assert.deepEqual(observer.steps(), [], "a finished step's events must not survive the read that consumed them");
  assert.deepEqual(observer.summarize(RUN, STEP), {
    run_id: RUN,
    step_id: STEP,
    hosts: [],
    writes: 0,
    reads: 0,
    status: {},
    duration_ms: 0,
  });
});

test("summarizeAndForget releases only its own step", () => {
  const observer = createObserver();
  observer.observeAll([
    req({ run_id: "run-a", step_id: "s1", url: "https://google.com/x" }),
    req({ run_id: "run-a", step_id: "s2", url: "https://stripe.com/y" }),
  ]);
  observer.summarizeAndForget("run-a", "s1");
  assert.deepEqual(observer.steps(), [{ run_id: "run-a", step_id: "s2" }]);
});

test("summarizeAndForget on a step nobody observed is an empty summary, not a throw", () => {
  // Same reason `summarize` does not throw: the router asks after every browser
  // step, including the ones where the page only moved the DOM.
  const observer = createObserver();
  assert.deepEqual(observer.summarizeAndForget("run-none", "step-none").hosts, []);
});

test("the store is capped: an unclaimed step does not survive MAX_RETAINED_STEPS later ones", () => {
  // Nothing in the extension is obliged to call forget. This is what stops a
  // week-long service worker from becoming a browsing history.
  const observer = createObserver();
  observer.observe(req({ run_id: "run-a", step_id: "s0", url: "https://google.com/x" }));
  for (let i = 1; i <= MAX_RETAINED_STEPS; i += 1) {
    observer.observe(req({ run_id: "run-a", step_id: `s${i}`, url: "https://stripe.com/x" }));
  }
  assert.equal(observer.steps().length, MAX_RETAINED_STEPS);
  assert.deepEqual(observer.summarize("run-a", "s0").hosts, [], "the oldest step was released");
  assert.deepEqual(observer.summarize("run-a", `s${MAX_RETAINED_STEPS}`).hosts, ["stripe.com"]);
});

test("the step still receiving events is never the one the cap evicts", () => {
  // The cap's whole cost is a summary that comes back empty for a step that
  // really happened, and the one step that must never suffer it is the live
  // one — the router is about to read it. Eviction is by least-recently-seen,
  // and a step receiving events is by definition not that.
  const observer = createObserver();
  for (let i = 0; i < MAX_RETAINED_STEPS * 2; i += 1) {
    observer.observe(req({ run_id: "run-a", step_id: "live", url: "https://google.com/x" }));
    observer.observe(req({ run_id: "run-a", step_id: `s${i}`, url: "https://stripe.com/x" }));
  }
  assert.deepEqual(observer.summarize("run-a", "live").hosts, ["google.com"]);
  assert.equal(observer.steps().length, MAX_RETAINED_STEPS);
});

test("readHost tells 'no site here' apart from 'a site we cannot name'", () => {
  // The two are different facts and they get different treatment at ingest: a
  // chrome-extension:// request is not a site and its counts are meaningless,
  // while a request to an unknown ccTLD suffix really happened and must still
  // be counted. Collapsing them into one null is how the second one silently
  // became the first.
  assert.deepEqual(readHost("https://mail.google.com/x"), { kind: "named", host: "google.com" });
  assert.deepEqual(readHost("https://www.example.com.gr/x"), { kind: "unnamed" });
  assert.deepEqual(readHost("chrome-extension://abc/sw.js"), { kind: "none" });
  assert.deepEqual(readHost("not a url at all"), { kind: "none" });
});

// ---------------------------------------------------------------------------
// THE DISCLOSURE COPY.
// ---------------------------------------------------------------------------
// The checklist lives HERE, not in observer.ts, on purpose: copy that declares
// its own requirements and then checks itself against them proves nothing. Each
// row is one element Chrome Web Store's Limited Use policy requires a prominent
// in-UI disclosure to carry, written the way the owner would say it.

const DISCLOSURE_REQUIREMENTS: ReadonlyArray<{ element: string; mustSay: readonly string[] }> = [
  { element: "what is collected: the host", mustSay: ["the site name"] },
  { element: "what is collected: counts", mustSay: ["a count of how many requests"] },
  // Added 2026-09-05 with the one-host summary. The copy used to imply every
  // site a page touched, which is what the code actually did; both changed.
  { element: "what is NOT collected: the page's third parties",
    mustSay: ["only the one site it was working in"] },
  { element: "never collected: request and response bodies",
    mustSay: ["what you typed", "what was sent", "what came back"] },
  { element: "never collected: page titles", mustSay: ["the page title"] },
  { element: "never collected: page text", mustSay: ["the text on it"] },
  { element: "never collected: cookies", mustSay: ["your cookies"] },
  { element: "never collected: full URLs, paths, query strings",
    mustSay: ["everything in the address bar after the site name", "no full links"] },
  { element: "runs during agent runs only",
    mustSay: ["only while anticipy is running a task you asked for"] },
  { element: "there is a pause switch", mustSay: ["you can pause this"] },
];

function normalized(): string {
  // The copy is hard-wrapped for a settings pane, so a required sentence can
  // straddle a newline. Normalising whitespace lets the checklist assert the
  // SENTENCE rather than the line breaks, which are a layout decision.
  return disclosureCopy().replace(/\s+/g, " ").toLowerCase();
}

test("the disclosure copy names every element the Limited Use policy requires", () => {
  const copy = normalized();
  for (const requirement of DISCLOSURE_REQUIREMENTS) {
    for (const phrase of requirement.mustSay) {
      assert.ok(
        copy.includes(phrase.toLowerCase()),
        `disclosure is missing "${phrase}" (${requirement.element})`,
      );
    }
  }
});

test("the disclosure copy is in the owner's register, not a lawyer's", () => {
  // "Request body" means nothing to him; "what you typed, what was sent" means
  // the same thing and he can check it against what he sees. A disclosure he
  // cannot read is not a disclosure.
  const copy = normalized();
  for (const jargon of [
    "telemetry", "pii", "personally identifiable", "request body", "payload",
    "metadata", "data subject", "anonymized", "anonymised", "third party",
  ]) {
    assert.ok(!copy.includes(jargon), `disclosure uses jargon: "${jargon}"`);
  }
});

test("the disclosure copy is one stable string, not rebuilt differently each call", () => {
  // It is shown in a settings pane and quoted in the store listing; the two must
  // be the same words.
  assert.equal(disclosureCopy(), disclosureCopy());
  assert.ok(disclosureCopy().length > 200);
});
