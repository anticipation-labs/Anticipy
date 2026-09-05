// WHAT THIS SUITE IS FOR.
//
// Every other test in this spike stands on the fake. If the fake lies - hands
// back a candidate the fixture never listed, mutates its own catalog because a
// caller mutated a result, reads a clock, orders ties by insertion - then the
// router suite, the ledger suite and the judge suite all pass or fail for
// reasons that have nothing to do with the code under test. So this file checks
// the fake against the contract the same way the gates check production: shape,
// every failure mode reachable, and the same answer twice.
//
// No network, no key, no account. `node --experimental-strip-types --test`.

import test from "node:test";
import assert from "node:assert/strict";

import {
  FIXTURE,
  FIXTURE_HASHES,
  FIXTURE_SIGNATURES,
  FIXTURE_USER,
  FIXTURE_USER_COLD,
  FakeProvider,
  FakeProviderDown,
  withConnections,
  withExec,
  withRetrieval,
} from "../src/provider_fake.ts";
import type { CapabilitySignature, ExecErrorKind } from "../src/contract.ts";

// A signature the fixture knows nothing about, built by hand so this file does
// not depend on `signature.ts`, which another part owns and which does not exist
// while this is being written.
function sigWithHash(hash: string): CapabilitySignature {
  return {
    app_hint: null,
    verb: "read",
    object: "something",
    inputs: {},
    expected_effect: "nothing observable changes",
    side_effect: "read",
    account_hint: null,
    signature_hash: hash,
  };
}

const READ_INBOX = FIXTURE_SIGNATURES.read_inbox;
const ARCHIVE = FIXTURE_SIGNATURES.archive_thread;
const CREATE_EVENT = FIXTURE_SIGNATURES.create_event;

// ---------------------------------------------------------------------------
// SHAPE: the four methods of `Provider`
// ---------------------------------------------------------------------------

test("declares itself as the fake provider", () => {
  assert.equal(new FakeProvider(FIXTURE).name, "fake");
});

test("search returns candidates in the ToolCandidate shape", async () => {
  const p = new FakeProvider(FIXTURE);
  const [top] = await p.search(READ_INBOX, FIXTURE_USER, { connectedOnly: true, limit: 5 });
  assert.equal(top.toolSlug, "GMAIL_FETCH_EMAILS");
  assert.equal(top.app, "gmail");
  assert.equal(top.score, 0.93);
  assert.equal(top.sideEffectHint, "read");
  assert.deepEqual(top.schema, { query: "string", max_results: "number" });
  assert.equal(typeof top.description, "string");
});

test("a tool with no sideEffectHint omits the key rather than setting it undefined", async () => {
  // A `sideEffectHint: undefined` key serializes differently from a missing one,
  // and the shadow-run parity hashes in this spike are built from serialized
  // objects - two runs that agree would hash apart.
  const fixture = withRetrieval(
    { tools: [{ toolSlug: "T_NO_HINT", app: "gmail", description: "d", schema: {} }] },
    "h",
    [{ toolSlug: "T_NO_HINT", score: 0.5 }],
  );
  const [only] = await new FakeProvider(fixture).search(sigWithHash("h"), FIXTURE_USER, {
    connectedOnly: false,
    limit: 5,
  });
  assert.equal("sideEffectHint" in only, false);
});

test("connections lists every state the owner is actually in", async () => {
  const rows = await new FakeProvider(FIXTURE).connections(FIXTURE_USER);
  const byApp = new Map(rows.map((r) => [`${r.app}:${r.accountId}`, r.status]));
  assert.equal(byApp.get("gmail:conn-gmail-work-0001"), "active");
  assert.equal(byApp.get("gmail:conn-gmail-personal-0002"), "active");
  assert.equal(byApp.get("googlecalendar:conn-gcal-0003"), "active");
  assert.equal(byApp.get("notion:conn-notion-0004"), "expired");
  assert.equal(byApp.get("slack:conn-slack-0005"), "revoked");
});

test("an owner who has connected nothing gets an empty list, not a throw", async () => {
  const p = new FakeProvider(FIXTURE);
  assert.deepEqual(await p.connections(FIXTURE_USER_COLD), []);
  // An owner the fixture never mentions is the same fresh-install case, and a
  // throw here would make "the router asked about a new owner" indistinguishable
  // from "the vendor is down".
  assert.deepEqual(await p.connections("owner-nobody-has-heard-of"), []);
});

test("connectLink returns a URL naming the app and the owner", async () => {
  const { url } = await new FakeProvider(FIXTURE).connectLink(FIXTURE_USER, "slack", [
    "chat:write",
  ]);
  const parsed = new URL(url);
  assert.equal(parsed.protocol, "https:");
  assert.equal(parsed.hostname, "connect.example.invalid");
  assert.equal(parsed.pathname, "/start/slack");
  assert.equal(parsed.searchParams.get("user"), FIXTURE_USER);
  assert.equal(parsed.searchParams.get("scopes"), "chat:write");
});

test("connectLink is stable across calls, instances and scope order", async () => {
  // A nonce or a timestamp here would be more realistic and would make every
  // onboarding assertion a regex, and a snapshot of the nudge copy impossible.
  const a = await new FakeProvider(FIXTURE).connectLink(FIXTURE_USER, "notion", ["b", "a"]);
  const b = await new FakeProvider(FIXTURE).connectLink(FIXTURE_USER, "notion", ["a", "b"]);
  assert.equal(a.url, b.url);
});

// ---------------------------------------------------------------------------
// SEARCH: ordering, limit, connectedOnly, and the empty answer
// ---------------------------------------------------------------------------

test("search returns nothing for a capability the vendor has no tool for", async () => {
  const p = new FakeProvider(FIXTURE);
  assert.deepEqual(
    await p.search(sigWithHash(FIXTURE_HASHES.no_tool_exists), FIXTURE_USER, {
      connectedOnly: false,
      limit: 10,
    }),
    [],
  );
  // The same answer for a hash nobody scripted at all. "No tool exists" is the
  // most common real reply and must never need fixture work to reach.
  assert.deepEqual(
    await p.search(sigWithHash("a-hash-this-fixture-never-heard-of"), FIXTURE_USER, {
      connectedOnly: false,
      limit: 10,
    }),
    [],
  );
});

test("search orders by score, highest first", async () => {
  const got = await new FakeProvider(FIXTURE).search(READ_INBOX, FIXTURE_USER, {
    connectedOnly: false,
    limit: 10,
  });
  assert.deepEqual(
    got.map((c) => c.toolSlug),
    ["GMAIL_FETCH_EMAILS", "NOTION_SEARCH", "SLACK_FETCH_HISTORY"],
  );
  assert.deepEqual(
    got.map((c) => c.score),
    [0.93, 0.41, 0.38],
  );
});

test("search breaks score ties on slug so first place never depends on fixture order", async () => {
  const got = await new FakeProvider(FIXTURE).search(CREATE_EVENT, FIXTURE_USER, {
    connectedOnly: false,
    limit: 10,
  });
  // GOOGLECALENDAR_FIND_EVENT and NOTION_CREATE_PAGE both score 0.6; the fixture
  // lists the calendar one first, and so does the sort - but by name, not by
  // luck. Reversing the fixture rows must not move them.
  assert.deepEqual(
    got.map((c) => c.toolSlug),
    ["GOOGLECALENDAR_CREATE_EVENT", "GOOGLECALENDAR_FIND_EVENT", "NOTION_CREATE_PAGE"],
  );

  const reversed = withRetrieval(FIXTURE, FIXTURE_HASHES.create_event, [
    { toolSlug: "NOTION_CREATE_PAGE", score: 0.6 },
    { toolSlug: "GOOGLECALENDAR_FIND_EVENT", score: 0.6 },
    { toolSlug: "GOOGLECALENDAR_CREATE_EVENT", score: 0.95 },
  ]);
  const again = await new FakeProvider(reversed).search(CREATE_EVENT, FIXTURE_USER, {
    connectedOnly: false,
    limit: 10,
  });
  assert.deepEqual(
    again.map((c) => c.toolSlug),
    got.map((c) => c.toolSlug),
  );
});

test("the archive/delete pair comes back ranked the dangerous way round", async () => {
  // This is the fixture's reason for existing. Asked to ARCHIVE a thread, the
  // vendor's own score puts the IRREVERSIBLE delete tool first. Any "take the
  // top hit over 0.75" rule destroys the owner's mail here; only a per-candidate
  // judge verdict of exactly "yes" can catch it. If this assertion ever flips,
  // the fixture stopped testing the thing it was built for.
  const got = await new FakeProvider(FIXTURE).search(ARCHIVE, FIXTURE_USER, {
    connectedOnly: true,
    limit: 10,
  });
  assert.deepEqual(
    got.map((c) => c.toolSlug),
    ["GMAIL_DELETE_THREAD", "GMAIL_ARCHIVE_THREAD"],
  );
  assert.ok(got[0].score > 0.75);
});

test("search honours limit", async () => {
  const p = new FakeProvider(FIXTURE);
  const opts = { connectedOnly: false, limit: 2 };
  const got = await p.search(READ_INBOX, FIXTURE_USER, opts);
  assert.equal(got.length, 2);
  assert.deepEqual(
    got.map((c) => c.toolSlug),
    ["GMAIL_FETCH_EMAILS", "NOTION_SEARCH"],
  );
  assert.deepEqual(await p.search(READ_INBOX, FIXTURE_USER, { connectedOnly: false, limit: 0 }), []);
});

test("connectedOnly means usable: an expired or revoked connection is not connected", async () => {
  // Notion is expired and Slack is revoked in the fixture. A fake that returned
  // them under connectedOnly is how a router picks the API hand and then spends
  // an owner-visible failure discovering the token is dead.
  const got = await new FakeProvider(FIXTURE).search(READ_INBOX, FIXTURE_USER, {
    connectedOnly: true,
    limit: 10,
  });
  assert.deepEqual(
    got.map((c) => c.toolSlug),
    ["GMAIL_FETCH_EMAILS"],
  );
});

test("connectedOnly returns nothing for an owner who has connected nothing", async () => {
  const got = await new FakeProvider(FIXTURE).search(READ_INBOX, FIXTURE_USER_COLD, {
    connectedOnly: true,
    limit: 10,
  });
  assert.deepEqual(got, []);
});

test("connectedOnly false hands back unconnected tools, exactly as the vendor would", async () => {
  // The fake must never be safer than Composio. A router that forgets the flag
  // has to fail here, in a test, rather than in production against a dead token.
  const got = await new FakeProvider(FIXTURE).search(READ_INBOX, FIXTURE_USER_COLD, {
    connectedOnly: false,
    limit: 10,
  });
  assert.equal(got.length, 3);
});

test("search survives a caller that omits opts entirely", async () => {
  // Annotations are stripped, not checked: `opts` is typed as required and will
  // still arrive undefined one day. The unhelpful default (connectedOnly false)
  // is deliberate - see the note in provider_fake.ts.
  const p = new FakeProvider(FIXTURE);
  const got = await p.search(READ_INBOX, FIXTURE_USER, undefined as never);
  assert.equal(got.length, 3);
  assert.equal((p.calls[0] as { connectedOnly: boolean }).connectedOnly, false);
});

// ---------------------------------------------------------------------------
// EXECUTE: every failure mode the router has to survive
// ---------------------------------------------------------------------------

test("execute reports success with the fixture's ms and cost", async () => {
  const r = await new FakeProvider(FIXTURE).execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {
    to: "sam@example.invalid",
  });
  assert.equal(r.ok, true);
  assert.equal(r.ms, 612);
  assert.equal(r.costUsd, 0.0006);
  assert.equal(r.error, undefined);
  assert.deepEqual(r.data, { id: "msg-fake-sent-1" });
});

test("a slow success reports its ms as data and does not actually take that long", async () => {
  // 8.24 seconds of reported latency in under a tick. A fake that really slept
  // would add eight seconds per latency assertion and CI would end up measuring
  // the sleep instead of the router's timeout rule.
  const started = Date.now();
  const r = await new FakeProvider(FIXTURE).execute(FIXTURE_USER, "GOOGLECALENDAR_FIND_EVENT", {});
  const wall = Date.now() - started;
  assert.equal(r.ok, true);
  assert.equal(r.ms, 8240);
  assert.ok(wall < 1000, `the fake slept for ${wall}ms; ms is data, not a delay`);
});

test("all four ExecErrorKinds are reachable from the shipped fixture", async () => {
  const p = new FakeProvider(FIXTURE);
  const seen = new Set<ExecErrorKind>();
  for (const slug of [
    "NOTION_SEARCH", // auth, derived from the expired connection
    "GOOGLECALENDAR_QUICK_ADD", // rate
    "GMAIL_ADD_LABEL", // schema
    "GOOGLECALENDAR_CREATE_EVENT", // other
  ]) {
    const r = await p.execute(FIXTURE_USER, slug, {});
    assert.equal(r.ok, false);
    assert.ok(r.error, `${slug} failed with no error object`);
    assert.equal(typeof r.error!.message, "string");
    assert.ok(Number.isFinite(r.ms));
    seen.add(r.error!.kind);
  }
  // Equality, not superset: a fixture that quietly lost its 429 leaves the
  // router's rate-limit path untested and nothing else would say so.
  assert.deepEqual([...seen].sort(), ["auth", "other", "rate", "schema"]);
});

test("a tool whose app the owner never connected fails as auth, not as a task failure", async () => {
  // The tool exists in the catalog; the owner simply has no Gmail. A 401 here
  // looks like a failed errand to the owner, so the router must record it as a
  // re-auth nudge and a browser fallback - never as evidence that the API hand
  // is worse at the task.
  const r = await new FakeProvider(FIXTURE).execute(FIXTURE_USER_COLD, "GMAIL_FETCH_EMAILS", {});
  assert.equal(r.ok, false);
  assert.equal(r.error?.kind, "auth");
  assert.match(r.error!.message, /not connected/);
});

test("an expired connection executes as auth, derived from the connection state", async () => {
  // Nothing is scripted for Notion. The 401 comes from the fact that the token
  // is expired, which is where it comes from in production too.
  const r = await new FakeProvider(FIXTURE).execute(FIXTURE_USER, "NOTION_SEARCH", {});
  assert.equal(r.ok, false);
  assert.equal(r.error?.kind, "auth");
  assert.match(r.error!.message, /no active connection for notion/);
});

test("a revoked connection executes as auth", async () => {
  const r = await new FakeProvider(FIXTURE).execute(FIXTURE_USER, "SLACK_SEND_MESSAGE", {});
  assert.equal(r.ok, false);
  assert.equal(r.error?.kind, "auth");
});

test("an accountId this owner does not hold fails as auth", async () => {
  // The shape of a stale ledger row: `capability_stats` remembers the account
  // that worked last month and the owner has since disconnected it.
  const p = new FakeProvider(FIXTURE);
  const good = await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {}, "conn-gmail-work-0001");
  assert.equal(good.ok, true);
  const stale = await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {}, "conn-gmail-deleted-9999");
  assert.equal(stale.ok, false);
  assert.equal(stale.error?.kind, "auth");
});

test("a scripted success cannot outrank a missing connection", async () => {
  // THE REGRESSION PIN for the ordering inside `execute`. The first draft of the
  // fake let a scripted outcome win, and this owner - who has connected nothing
  // - got the fixture's Gmail success back. A router test built on that would
  // have concluded the API hand works for an owner with no accounts, and the
  // fake would have certified the bug it exists to expose.
  const p = new FakeProvider(FIXTURE);
  const r = await p.execute(FIXTURE_USER_COLD, "GMAIL_SEND_EMAIL", {});
  assert.equal(r.ok, false);
  assert.equal(r.error?.kind, "auth");
});

test("a call that never reached the tool does not consume the script", async () => {
  // Three attempts against a dead accountId, then one against a live one. If the
  // 401s ate script entries, a demotion test would be counting failures the tool
  // never saw, and the fixture's own sequence would depend on how many times the
  // router guessed the account wrong.
  const fixture = withExec(FIXTURE, "GMAIL_SEND_EMAIL", [
    { ok: true, ms: 500 },
    { ok: false, ms: 60, error: { kind: "rate", message: "429 slow down" } },
  ]);
  const p = new FakeProvider(fixture);
  for (let i = 0; i < 3; i++) {
    const bad = await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {}, "conn-gmail-deleted-9999");
    assert.equal(bad.error?.kind, "auth");
  }
  const first = await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {}, "conn-gmail-work-0001");
  assert.equal(first.ok, true);
  assert.equal(first.ms, 500);
});

test("an unknown tool slug is an error result, not a throw", async () => {
  // The vendor renamed the tool and the ledger still points at the old slug.
  // Composio answers with an error; so does this, or the router learns to treat
  // a rename as a crash.
  const r = await new FakeProvider(FIXTURE).execute(FIXTURE_USER, "GMAIL_SEND_EMAIL_V1", {});
  assert.equal(r.ok, false);
  assert.equal(r.error?.kind, "other");
  assert.match(r.error!.message, /unknown tool/);
});

test("a scripted sequence is consumed in order and its last entry repeats", async () => {
  // The shape a demotion test needs: worked, worked, then started rate-limiting,
  // with no clock involved.
  const fixture = withExec(FIXTURE, "GMAIL_SEND_EMAIL", [
    { ok: true, ms: 500 },
    { ok: true, ms: 520 },
    { ok: false, ms: 60, error: { kind: "rate", message: "429 slow down" } },
  ]);
  const p = new FakeProvider(fixture);
  const kinds: string[] = [];
  for (let i = 0; i < 5; i++) {
    const r = await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {});
    kinds.push(r.ok ? "ok" : r.error!.kind);
  }
  assert.deepEqual(kinds, ["ok", "ok", "rate", "rate", "rate"]);
});

test("two owners each get the whole script from the start", async () => {
  // Keyed per (owner, tool). Shared cursors would hand owner B the second entry
  // of owner A's script during a shadow run, which reads exactly like a routing
  // bug in the part under test.
  const fixture = withExec(withConnections(FIXTURE, "owner-two", FIXTURE.connections![FIXTURE_USER]),
    "GMAIL_SEND_EMAIL", [
      { ok: true, ms: 1 },
      { ok: false, ms: 2, error: { kind: "rate", message: "429" } },
    ]);
  const p = new FakeProvider(fixture);
  assert.equal((await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {})).ok, true);
  assert.equal((await p.execute("owner-two", "GMAIL_SEND_EMAIL", {})).ok, true);
  assert.equal((await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {})).ok, false);
  assert.equal((await p.execute("owner-two", "GMAIL_SEND_EMAIL", {})).ok, false);
});

test("reset replays the script from the beginning", async () => {
  const fixture = withExec(FIXTURE, "GMAIL_SEND_EMAIL", [
    { ok: true, ms: 1 },
    { ok: false, ms: 2, error: { kind: "other", message: "500" } },
  ]);
  const p = new FakeProvider(fixture);
  await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {});
  await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {});
  p.reset();
  assert.equal((await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {})).ok, true);
  assert.equal(p.calls.length, 1);
});

// ---------------------------------------------------------------------------
// THE VENDOR BEING DOWN
// ---------------------------------------------------------------------------

test("a provider that is down rejects on every method", async () => {
  const p = FakeProvider.down("composio unreachable");
  const sig = sigWithHash("anything");
  await assert.rejects(
    () => p.search(sig, FIXTURE_USER, { connectedOnly: true, limit: 5 }),
    FakeProviderDown,
  );
  await assert.rejects(() => p.connections(FIXTURE_USER), FakeProviderDown);
  await assert.rejects(() => p.connectLink(FIXTURE_USER, "gmail"), FakeProviderDown);
  await assert.rejects(() => p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", {}), FakeProviderDown);
});

test("one method can be down while the rest work", async () => {
  // The real outage shape: retrieval answers, execution 502s. A router that only
  // survives a wholly-dead vendor still strands the owner here.
  const p = new FakeProvider({ ...FIXTURE, throws: { execute: "502 from the tool runner" } });
  const got = await p.search(READ_INBOX, FIXTURE_USER, { connectedOnly: true, limit: 5 });
  assert.equal(got.length, 1);
  await assert.rejects(
    () => p.execute(FIXTURE_USER, "GMAIL_FETCH_EMAILS", {}),
    (err: FakeProviderDown) => {
      assert.equal(err.name, "FakeProviderDown");
      assert.equal(err.method, "execute");
      assert.equal(err.message, "502 from the tool runner");
      return true;
    },
  );
});

// ---------------------------------------------------------------------------
// DETERMINISM AND ISOLATION - a flaky fake makes every downstream test lie
// ---------------------------------------------------------------------------

test("two providers built from one fixture answer identically", async () => {
  const a = new FakeProvider(FIXTURE);
  const b = new FakeProvider(FIXTURE);
  const opts = { connectedOnly: true, limit: 10 };
  assert.deepEqual(
    await a.search(READ_INBOX, FIXTURE_USER, opts),
    await b.search(READ_INBOX, FIXTURE_USER, opts),
  );
  assert.deepEqual(
    await a.execute(FIXTURE_USER, "GMAIL_FETCH_EMAILS", { query: "is:unread" }),
    await b.execute(FIXTURE_USER, "GMAIL_FETCH_EMAILS", { query: "is:unread" }),
  );
  assert.deepEqual(await a.connections(FIXTURE_USER), await b.connections(FIXTURE_USER));
});

test("no method reads a clock or a random number", async () => {
  // Proved rather than asserted: break both sources for the duration of the
  // calls. A fake that stamps `Date.now()` into a result makes every deepEqual
  // in every downstream suite a rewrite-the-expectation exercise.
  const realNow = Date.now;
  const realRandom = Math.random;
  const realPerf = performance.now;
  Date.now = () => {
    throw new Error("the fake read a clock");
  };
  Math.random = () => {
    throw new Error("the fake rolled a die");
  };
  performance.now = () => {
    throw new Error("the fake read a clock");
  };
  try {
    const p = new FakeProvider(FIXTURE);
    await p.search(READ_INBOX, FIXTURE_USER, { connectedOnly: true, limit: 3 });
    await p.connections(FIXTURE_USER);
    await p.connectLink(FIXTURE_USER, "notion", ["read_content"]);
    await p.execute(FIXTURE_USER, "GMAIL_FETCH_EMAILS", {});
    await p.execute(FIXTURE_USER_COLD, "GMAIL_FETCH_EMAILS", {});
  } finally {
    Date.now = realNow;
    Math.random = realRandom;
    performance.now = realPerf;
  }
});

test("mutating a result cannot rewrite the fixture", async () => {
  // Without the copies, a router that stuffs a normalized schema back into the
  // candidate it was handed corrupts every later test in the same file, and the
  // failure surfaces three tests away from its cause.
  const p = new FakeProvider(FIXTURE);
  const first = await p.search(READ_INBOX, FIXTURE_USER, { connectedOnly: false, limit: 10 });
  first[0].score = 0.01;
  first[0].schema.injected = true;
  const rows = await p.connections(FIXTURE_USER);
  rows[0].status = "revoked";
  rows.length = 0;
  const exec = await p.execute(FIXTURE_USER, "GMAIL_FETCH_EMAILS", {});
  (exec.data as { messages: unknown[] }).messages.push({ id: "injected" });

  const second = await p.search(READ_INBOX, FIXTURE_USER, { connectedOnly: false, limit: 10 });
  assert.equal(second[0].score, 0.93);
  assert.equal("injected" in second[0].schema, false);
  assert.equal((await p.connections(FIXTURE_USER)).length, 5);
  assert.equal((await p.connections(FIXTURE_USER))[0].status, "active");
  const execAgain = await p.execute(FIXTURE_USER, "GMAIL_FETCH_EMAILS", {});
  assert.equal((execAgain.data as { messages: unknown[] }).messages.length, 1);
});

test("the with* helpers do not mutate the fixture they were given", async () => {
  const before = structuredClone(FIXTURE);
  withRetrieval(FIXTURE, "new-hash", [{ toolSlug: "NOTION_SEARCH", score: 0.5 }]);
  withConnections(FIXTURE, "someone-else", []);
  withExec(FIXTURE, "NOTION_SEARCH", { ok: true, ms: 1 });
  assert.deepEqual(FIXTURE, before);
});

// ---------------------------------------------------------------------------
// THE CALL LOG
// ---------------------------------------------------------------------------

test("the call log records what was asked, and a caller cannot rewrite it", async () => {
  const p = new FakeProvider(FIXTURE);
  const args: Record<string, unknown> = { to: "sam@example.invalid" };
  await p.search(READ_INBOX, FIXTURE_USER, { connectedOnly: true, limit: 3 });
  await p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", args, "conn-gmail-work-0001");
  // The router legitimately reuses and mutates its own args object between
  // steps; the log has to be a copy or an assertion about what was SENT quietly
  // becomes an assertion about what the object looks like now.
  args.to = "someone-else@example.invalid";

  assert.deepEqual(p.calls[0], {
    method: "search",
    userId: FIXTURE_USER,
    sigHash: FIXTURE_HASHES.read_inbox,
    connectedOnly: true,
    limit: 3,
  });
  assert.deepEqual(p.calls[1], {
    method: "execute",
    userId: FIXTURE_USER,
    toolSlug: "GMAIL_SEND_EMAIL",
    args: { to: "sam@example.invalid" },
    accountId: "conn-gmail-work-0001",
  });
});

// ---------------------------------------------------------------------------
// FIXTURE VALIDATION - a fixture bug must never look like a routing decision
// ---------------------------------------------------------------------------

test("a retrieval hit naming a tool that does not exist is rejected at construction", () => {
  // Left unchecked, this returns zero candidates, the router falls back to the
  // browser, and the test asserting "browser" passes for the wrong reason.
  assert.throws(
    () =>
      new FakeProvider(
        withRetrieval(FIXTURE, "h", [{ toolSlug: "GMAIL_SEND_EMAILS", score: 0.9 }]),
      ),
    /unknown tool GMAIL_SEND_EMAILS/,
  );
});

test("the same tool listed twice in one retrieval result is rejected", () => {
  assert.throws(
    () =>
      new FakeProvider(
        withRetrieval(FIXTURE, "h", [
          { toolSlug: "NOTION_SEARCH", score: 0.9 },
          { toolSlug: "NOTION_SEARCH", score: 0.4 },
        ]),
      ),
    /lists NOTION_SEARCH twice/,
  );
});

test("a value that cannot cross the wire is refused with a sentence, not a DataCloneError", async () => {
  const p = new FakeProvider(FIXTURE);
  await assert.rejects(
    () => p.execute(FIXTURE_USER, "GMAIL_SEND_EMAIL", { onDone: () => {} }),
    /must be JSON-shaped/,
  );
});

test("a duplicate tool slug is rejected", () => {
  assert.throws(
    () =>
      new FakeProvider({
        tools: [
          { toolSlug: "DUP", app: "gmail", description: "", schema: {} },
          { toolSlug: "DUP", app: "slack", description: "", schema: {} },
        ],
      }),
    /duplicate toolSlug DUP/,
  );
});

test("an exec entry for a tool that does not exist is rejected", () => {
  assert.throws(
    () => new FakeProvider(withExec(FIXTURE, "NO_SUCH_TOOL", { ok: true, ms: 1 })),
    /exec names unknown tool NO_SUCH_TOOL/,
  );
});

test("an outcome that is both ok and an error is rejected", () => {
  assert.throws(
    () =>
      new FakeProvider(
        withExec(FIXTURE, "NOTION_SEARCH", {
          ok: true,
          ms: 1,
          error: { kind: "auth", message: "401" },
        }),
      ),
    /ok:true must not carry an error/,
  );
});

test("a failure with no recognised error kind is rejected", () => {
  assert.throws(
    () =>
      new FakeProvider(
        withExec(FIXTURE, "NOTION_SEARCH", {
          ok: false,
          ms: 1,
          error: { kind: "timeout" as ExecErrorKind, message: "" },
        }),
      ),
    /error\.kind of auth\|rate\|schema\|other/,
  );
});

test("a non-numeric or negative ms is rejected", () => {
  // ms feeds p50/p95. A NaN there does not throw - it makes a latency comparison
  // quietly false and the router promotes or demotes a hand for a reason nobody
  // can reconstruct.
  assert.throws(
    () => new FakeProvider(withExec(FIXTURE, "NOTION_SEARCH", { ok: true, ms: NaN })),
    /ms must be a non-negative number/,
  );
  assert.throws(
    () => new FakeProvider(withExec(FIXTURE, "NOTION_SEARCH", { ok: true, ms: -1 })),
    /ms must be a non-negative number/,
  );
});

test("a connection row with an invented status is rejected", () => {
  assert.throws(
    () =>
      new FakeProvider(
        withConnections(FIXTURE, "owner-bad", [
          {
            app: "gmail",
            accountId: "x",
            label: "x",
            scopes: [],
            status: "pending" as never,
          },
        ]),
      ),
    /has status pending/,
  );
});

// ---------------------------------------------------------------------------
// THE FIXTURE ITSELF
// ---------------------------------------------------------------------------

test("every fixture endpoint and address is unreachable on purpose", async () => {
  // A fixture that names a real host is one copy-paste away from a suite that
  // opens somebody's real OAuth consent screen, or emails a real person.
  const text = JSON.stringify({ FIXTURE, FIXTURE_SIGNATURES });
  const hosts = text.match(/[a-z0-9.-]+\.(com|org|net|io|ai|dev|co)\b/g) ?? [];
  assert.deepEqual(hosts, [], `fixture names real-looking hosts: ${hosts.join(", ")}`);
  const { url } = await new FakeProvider(FIXTURE).connectLink(FIXTURE_USER, "gmail");
  assert.match(url, /example\.invalid/);
});

test("the shipped fixture covers the four connection states the router must survive", async () => {
  const p = new FakeProvider(FIXTURE);
  const statuses = new Set((await p.connections(FIXTURE_USER)).map((c) => c.status));
  assert.deepEqual([...statuses].sort(), ["active", "expired", "revoked"]);
  // The fourth state is ABSENT, and it is a different owner rather than a
  // missing row, so a test for the fresh-install path does not have to edit the
  // fixture to reach it.
  assert.deepEqual(await p.connections(FIXTURE_USER_COLD), []);
});

test("the fixture holds two accounts for one app", async () => {
  // account_hint is work-or-personal in the contract, and a fixture with one
  // Gmail can never show a router picking the wrong mailbox.
  const gmail = (await new FakeProvider(FIXTURE).connections(FIXTURE_USER)).filter(
    (c) => c.app === "gmail",
  );
  assert.equal(gmail.length, 2);
  assert.notEqual(gmail[0].accountId, gmail[1].accountId);
});

test("every fixture signature's hash is listed in FIXTURE_HASHES", () => {
  const known = new Set(Object.values(FIXTURE_HASHES) as string[]);
  for (const [name, sig] of Object.entries(FIXTURE_SIGNATURES)) {
    assert.ok(known.has(sig.signature_hash), `${name} carries a hash nothing else knows`);
  }
});
