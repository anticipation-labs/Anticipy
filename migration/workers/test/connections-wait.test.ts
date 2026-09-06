/**
 * test/connections-wait.test.ts — the background poll that stops a connection
 * existing at the vendor and nowhere here.
 *
 *   node --experimental-strip-types migration/workers/test/connections-wait.test.ts
 *
 * WHAT IS REAL HERE AND WHAT IS NOT. `waitForConnection`, the whole of
 * routes/connect.ts (routing, session check, redeem, the callback, the HTML)
 * and — in the race section — the REAL D1 store over the REAL schema.sql are
 * the shipped code. The clock and the sleep are injected so five minutes of
 * backoff costs no wall-clock time, and the vendor is a script because the
 * whole question is what happens when a remote list changes underneath us.
 *
 * THE FAILURE THIS FILE EXISTS TO CATCH, in one sentence: the person's browser
 * dies between the vendor's consent screen and `/c/{token}/done`, the account
 * is bound AT THE VENDOR, there is no row here, no nudge flip, and — because
 * the vendor publishes no success webhook, only `expired` — nothing that will
 * ever mention it again. Before this poll, `/done` was the only way a
 * connection was ever learned about.
 *
 * MUTATIONS THIS FILE MUST GO RED ON (run, not asserted — see the report):
 *   the lease dropped from the poll (both paths write);
 *   `release` dropped when `onConnected` throws (the link is dead forever);
 *   the baseline dropped (an account that was already connected is recorded as
 *     this attempt's, flipping the nudge on a connect that never finished);
 *   the deadline ignored;
 *   `status !== "connected"` dropped (an EXPIRED credential recorded as live);
 *   the owner check on a vendor row dropped (a stranger's account bound);
 *   the owner/toolkit check against the STORED ROW dropped;
 *   `startWaiting` removed from /go;
 *   `writes_enabled` defaulting true.
 *
 * ANCHORS. Every source scan below asserts its anchor appears EXACTLY ONCE. A
 * regex that silently matched nothing is a test that passes for the wrong
 * reason, and this repo has been given three false "it is tested" readings that
 * way in one day.
 */
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import {
  connectRoute, connectPageDone, tokenHandle, LINK_TTL_MS, SESSION_COOKIE,
  type ClaimOutcome, type ConnectDeps, type ConnectEnv, type ConnectLinkStore,
  type Connection, type StoredLink, type ToolkitMeta,
} from "../src/routes/connect.ts";
import {
  waitForConnection, waitBudgetMs, linkFingerprint,
  MAX_VENDOR_CALLS, POLL_FIRST_DELAY_MS, WAIT_BUDGET_MS, WAIT_CEILING_MS,
  type WaitOptions, type WaitOutcome,
} from "../src/connections/wait.ts";
import { createD1Store, type StoredConnection } from "../src/connections/store.ts";

const here = dirname(fileURLToPath(import.meta.url));
const WAIT_SRC = readFileSync(join(here, "..", "src", "connections", "wait.ts"), "utf8");
const CONNECT_SRC = readFileSync(join(here, "..", "src", "routes", "connect.ts"), "utf8");
const INDEX_SRC = readFileSync(join(here, "..", "src", "index.ts"), "utf8");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

/** An anchor that matched nothing is the bug this helper exists for. */
function occurrences(haystack: string, needle: string): number {
  let n = 0;
  let i = haystack.indexOf(needle);
  while (i !== -1) { n++; i = haystack.indexOf(needle, i + needle.length); }
  return n;
}
function anchoredOnce(src: string, needle: string, where: string): void {
  assert.equal(occurrences(src, needle), 1,
    `the anchor ${JSON.stringify(needle)} appears ${occurrences(src, needle)} times in `
    + `${where} — a scan whose anchor moved proves nothing about the code it names`);
}

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const NOW = 1_757_000_000_000;
const PB_NOW = "2026-09-05 12:00:00.000Z";
const OWNER = "ownerrefaaaaaa1";
const STRANGER = "strangerowner12";
const TOOLKIT = "zellibrix";          // an app nobody has ever heard of
const ACCOUNT_NEW = "ca_THIS_ATTEMPT";
const ACCOUNT_OLD = "ca_ALREADY_THEIRS";

/**
 * The link store, written to the interface's OWN rule: `claim`, `complete` and
 * `release` are compare-and-sets with NO await between the read and the write.
 * An async function body runs synchronously to its first await, so on one event
 * loop the check and the set cannot interleave — which is the property D1's
 * single-statement UPDATE gives for real. A fake that read, awaited, then wrote
 * would let both the callback and the poll win and this suite would call the
 * double-write bug a pass.
 */
class MemoryStore implements ConnectLinkStore {
  rows = new Map<string, StoredLink>();
  reads = 0;
  failReads = 0;

  put(row: StoredLink): void { this.rows.set(row.token_handle, { ...row }); }
  get(handle: string): StoredLink | undefined {
    const r = this.rows.get(handle);
    return r ? { ...r } : undefined;
  }

  async read(handle: string): Promise<StoredLink | null> {
    this.reads++;
    if (this.failReads > 0) { this.failReads--; throw new Error("D1_ERROR: no"); }
    const row = this.rows.get(handle);
    return row ? { ...row } : null;
  }

  async claim(handle: string, usedAt: number): Promise<ClaimOutcome> {
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.used_at !== null) return { won: false, row: { ...row } };
    const next: StoredLink = { ...row, used_at: usedAt };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }

  async complete(handle: string, completedAt: number): Promise<ClaimOutcome> {
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.completed_at !== null) return { won: false, row: { ...row } };
    const next: StoredLink = { ...row, completed_at: completedAt };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }

  async release(handle: string, completedAt: number): Promise<ClaimOutcome> {
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.completed_at !== completedAt) return { won: false, row: { ...row } };
    const next: StoredLink = { ...row, completed_at: null };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }
}

/** A clock a test owns. `sleep` advances it, so five minutes of backoff costs
 *  nothing and every deadline check below is deterministic. */
function clock(start: number, opts: { frozen?: boolean } = {}) {
  let t = start;
  const slept: number[] = [];
  return {
    slept,
    now: (): number => t,
    at: (): number => t,
    sleep: async (ms: number): Promise<void> => {
      slept.push(ms);
      if (!opts.frozen) t += ms;
    },
  };
}

/** One vendor account, the shape `provider.connections` returns. */
function acct(
  id: string, over: Partial<Connection> = {},
): Connection {
  return {
    user_id: OWNER, toolkit: TOOLKIT, connected_account_id: id, alias: null,
    status: "connected", writes_enabled: false, last_used_at: null, ...over,
  };
}

/** The vendor, as a script over call number (1-based). Returning an Error
 *  throws it; returning anything at all is handed through unread, so a
 *  non-array answer can be tested against an empty one. */
function vendor(script: (call: number) => unknown) {
  const asked: string[] = [];
  return {
    asked,
    provider: {
      async connections(user: string): Promise<Connection[]> {
        asked.push(user);
        const v = script(asked.length);
        if (v instanceof Error) throw v;
        return v as Connection[];
      },
    } as unknown as WaitOptions["provider"],
  };
}

async function handleOf(token: string): Promise<string> { return await tokenHandle(token); }
function newToken(): string { return randomBytes(32).toString("base64url"); }

interface Bench {
  store: MemoryStore;
  handle: string;
  token: string;
  written: Connection[];
  onConnected: (c: Connection) => Promise<void>;
}

async function bench(over: Partial<StoredLink> = {}, throwOnWrite = false): Promise<Bench> {
  const token = newToken();
  const handle = await handleOf(token);
  const store = new MemoryStore();
  store.put({
    token_handle: handle, user_id: OWNER, toolkit: TOOLKIT, alias: null,
    expires_at: NOW + LINK_TTL_MS, used_at: NOW, completed_at: null, ...over,
  });
  const written: Connection[] = [];
  return {
    store, handle, token, written,
    onConnected: async (c: Connection): Promise<void> => {
      if (throwOnWrite) throw new Error("D1_ERROR: the batch failed");
      written.push(c);
    },
  };
}

function waitOpts(
  b: Bench, v: ReturnType<typeof vendor>, c: ReturnType<typeof clock>,
  over: Partial<WaitOptions> = {},
): WaitOptions {
  return {
    owner: OWNER, toolkit: TOOLKIT, handle: b.handle,
    deadline: c.now() + WAIT_BUDGET_MS,
    store: b.store, provider: v.provider, onConnected: b.onConnected,
    now: c.now, sleep: c.sleep, ...over,
  };
}

// ===========================================================================
// 1. THE POLL WINS WHEN THE CALLBACK NEVER COMES
// ===========================================================================

await check("the poll wins when the callback never comes, and writes the connection", async () => {
  const b = await bench();
  const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW)]));
  const c = clock(NOW);

  const out = await waitForConnection(null, waitOpts(b, v, c));

  assert.equal(out.state, "recorded", "the poll must record what the callback never reported");
  assert.equal(b.written.length, 1, "exactly one connection is written");
  assert.equal(b.written[0]?.connected_account_id, ACCOUNT_NEW);
  assert.equal(b.store.get(b.handle)?.completed_at, c.at(),
    "the poll must burn the same exactly-once lease the callback burns");
});

await check("the row the poll writes is IDENTICAL to the row the callback writes", async () => {
  // Two identical links, two paths, one comparison. If these ever differ, one
  // of the two ways a connection is learned about writes a different fact
  // about the same event.
  const viaPoll = await bench();
  const p = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW)]));
  await waitForConnection(null, waitOpts(viaPoll, p, clock(NOW)));

  const viaCallback = await bench();
  const done = await connectPageDone(
    viaCallback.token,
    { status: "success", connectedAccountId: ACCOUNT_NEW },
    {
      signedInAs: OWNER, store: viaCallback.store,
      provider: { async connections(): Promise<Connection[]> { return [acct(ACCOUNT_NEW)]; } },
      onConnected: viaCallback.onConnected, now: NOW,
    },
  );

  assert.equal(done.state, "connected");
  assert.equal(viaPoll.written.length, 1);
  assert.equal(viaCallback.written.length, 1);
  assert.deepEqual(viaPoll.written[0], viaCallback.written[0],
    "the backup must land the same row as the primary — including writes_enabled false, "
    + "the alias off the stored row and a null last_used_at");
  assert.equal(viaPoll.written[0]?.writes_enabled, false,
    "a new connection is never write-enabled: that is the Settings toggle, off by default");
});

await check("the alias on the stored link rides onto the connection the poll writes", async () => {
  const b = await bench({ alias: "work" });
  const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW)]));
  await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(b.written[0]?.alias, "work",
    "the alias comes off the stored row, which is the only thing that knows which "
    + "of two accounts this link was minted for");
});

// ===========================================================================
// 2. THE CALLBACK WINS AND THE POLL FINDS THE LEASE TAKEN
// ===========================================================================

await check("the callback wins: the poll finds the lease taken and writes nothing", async () => {
  const b = await bench();
  const done = await connectPageDone(
    b.token, { status: "success", connectedAccountId: ACCOUNT_NEW },
    {
      signedInAs: OWNER, store: b.store,
      provider: { async connections(): Promise<Connection[]> { return [acct(ACCOUNT_NEW)]; } },
      onConnected: b.onConnected, now: NOW,
    },
  );
  assert.equal(done.state, "connected");
  assert.equal(b.written.length, 1);

  const v = vendor(() => [acct(ACCOUNT_NEW)]);
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));

  assert.equal(out.state, "already-recorded");
  assert.equal(b.written.length, 1, "the poll must not write a second connection");
  assert.equal(v.asked.length, 0,
    "and it must not spend a single vendor call: the lease is checked before the "
    + "vendor is asked, so the ordinary case costs nothing");
});

await check("a callback that lands MID-POLL stops the poll before it writes", async () => {
  const b = await bench();
  const v = vendor((n) => {
    // The account appears at the vendor on call 3 — but the callback lands
    // first, between polls.
    if (n === 2) b.store.rows.set(b.handle, { ...b.store.rows.get(b.handle)!, completed_at: NOW + 1 });
    return n >= 3 ? [acct(ACCOUNT_NEW)] : [];
  });
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(out.state, "already-recorded");
  assert.equal(b.written.length, 0, "the poll wrote nothing after the lease was taken");
  // AND IT STOPPED ASKING. The lease alone keeps the WRITE correct, so this
  // assertion is about cost rather than correctness — and the cost is real: on
  // every ordinary connect, where the callback lands in seconds, a poll that
  // did not notice would go on spending the owner's vendor quota for the rest
  // of the five-minute budget. Two calls: the baseline, and the one poll during
  // which the callback landed.
  assert.equal(v.asked.length, 2,
    `the poll asked the vendor ${v.asked.length} times after the lease was gone`);
});

// ===========================================================================
// 3. BOTH RACING — ONE CONNECTION ROW, ONE NUDGE FLIP, ON THE REAL D1 STORE
// ===========================================================================

await check("callback and poll racing produce exactly ONE connection row and ONE nudge flip",
  async () => {
    // The real store, the real schema, the real one-batch write. The lease is
    // the only thing standing between two writers and two rows.
    const db = new FakeD1();
    const env = { DB: asD1(db) } as unknown as { DB: D1Database };
    const store = createD1Store(env);
    const token = newToken();
    const handle = await handleOf(token);
    await store.put({
      token_handle: handle, user_id: OWNER, toolkit: TOOLKIT, alias: null,
      expires_at: NOW + LINK_TTL_MS, used_at: NOW, completed_at: null,
    });

    let writes = 0;
    const onConnected = async (c: Connection): Promise<void> => {
      writes++;
      await store.recordConnection(c as StoredConnection, NOW);
    };
    const holds = async (): Promise<Connection[]> => [acct(ACCOUNT_NEW)];

    const callback = connectPageDone(
      token, { status: "success", connectedAccountId: ACCOUNT_NEW },
      { signedInAs: OWNER, store, provider: { connections: holds }, onConnected, now: NOW },
    );
    const poll = waitForConnection(null, {
      owner: OWNER, toolkit: TOOLKIT, handle, deadline: NOW + WAIT_BUDGET_MS,
      store, provider: { connections: holds }, onConnected,
      now: () => NOW, sleep: async () => {},
    });
    const [doneOut, pollOut] = await Promise.all([callback, poll]);

    // Exactly one of the two did the writing. Which one is a race and is not
    // asserted; that both did NOT is the whole property.
    const wroteIt = [
      doneOut.state === "connected" && doneOut.recorded === true,
      pollOut.state === "recorded",
    ].filter(Boolean).length;
    assert.equal(wroteIt, 1,
      `exactly one writer may take the lease — callback=${JSON.stringify(doneOut.state)} `
      + `poll=${JSON.stringify(pollOut.state)}`);
    assert.equal(writes, 1, "onConnected ran exactly once");

    const conns = db.db.prepare(`SELECT * FROM "connections"`).all() as Record<string, unknown>[];
    assert.equal(conns.length, 1, "ONE connection row");
    assert.equal(conns[0]?.user_id, OWNER);
    assert.equal(conns[0]?.writes_enabled, 0, "writes stay off");

    const nudges = db.db.prepare(`SELECT * FROM "connect_nudges"`).all() as Record<string, unknown>[];
    assert.equal(nudges.length, 1, "ONE nudge row");
    assert.equal(nudges[0]?.state, "connected", "and it is flipped to connected");
    assert.equal(nudges[0]?.toolkit, TOOLKIT);
  });

await check("two polls racing each other also produce exactly one write", async () => {
  const b = await bench();
  // ONE vendor for both polls: each takes its own baseline off the first two
  // calls, and the account then appears to both at once.
  let opened = 0;
  const shared = vendor(() => (++opened <= 2 ? [] : [acct(ACCOUNT_NEW)]));
  const c1 = clock(NOW);
  const c2 = clock(NOW);
  const [a, z] = await Promise.all([
    waitForConnection(null, waitOpts(b, shared, c1)),
    waitForConnection(null, waitOpts(b, shared, c2)),
  ]);
  const recorded = [a.state, z.state].filter((s) => s === "recorded").length;
  assert.equal(recorded, 1, `exactly one poll may win — got ${a.state} and ${z.state}`);
  assert.equal(b.written.length, 1);
});

// ===========================================================================
// 4. THE DEADLINE, THE BOUND AND THE BACKOFF
// ===========================================================================

await check("the deadline is honoured: a vendor that never shows the account writes nothing",
  async () => {
    const b = await bench();
    const v = vendor(() => []);
    const c = clock(NOW);
    const out = await waitForConnection(null, waitOpts(b, v, c));

    assert.equal(out.state, "never-appeared");
    assert.equal(b.written.length, 0, "nothing written");
    assert.equal(b.store.get(b.handle)?.completed_at, null,
      "and the lease is untouched, so a late callback can still record it");
    assert.ok(c.at() <= NOW + WAIT_BUDGET_MS,
      `the poll ran past its deadline: stopped at +${c.at() - NOW}ms of a `
      + `${WAIT_BUDGET_MS}ms budget`);
    assert.ok(v.asked.length > 1, "it did actually poll rather than give up at once");
    assert.ok(v.asked.length <= MAX_VENDOR_CALLS,
      `it spent ${v.asked.length} vendor calls, over the ${MAX_VENDOR_CALLS} ceiling`);
    // THE INVARIANT THAT MAKES THE DEADLINE LOAD-BEARING, and it is here
    // because without it a loop with no deadline test still passed everything
    // above: once the deadline is behind us the gap clamps to zero, so the
    // clock stops moving and every wall-clock assertion stays true while the
    // poll spins on the vendor until the call ceiling. Every poll after the
    // baseline is preceded by exactly one gap; a poll with no gap in front of
    // it is a spin, not a poll.
    assert.equal(v.asked.length, 1 + c.slept.length,
      `${v.asked.length} vendor calls behind ${c.slept.length} gaps — a poll that is not `
      + "waiting between calls is not backing off, whatever its total says");
    assert.ok(c.slept.length >= 5,
      `only ${c.slept.length} gaps in a ${WAIT_BUDGET_MS}ms budget; the backoff has `
      + "swallowed the window the person is actually in");
  });

await check("the gaps back off, and the first one is not immediate", async () => {
  const b = await bench();
  const v = vendor(() => []);
  const c = clock(NOW);
  await waitForConnection(null, waitOpts(b, v, c));
  assert.equal(c.slept[0], POLL_FIRST_DELAY_MS,
    "the first gap is the configured one: nobody finishes a consent screen in under it");
  const growing = c.slept.slice(0, 4);
  for (let i = 1; i < growing.length; i++) {
    assert.ok((growing[i] as number) > (growing[i - 1] as number),
      `gap ${i} did not grow: ${JSON.stringify(c.slept)}`);
  }
  assert.equal(c.slept.reduce((a, x) => a + x, 0), WAIT_BUDGET_MS,
    "the gaps add up to exactly the budget — the last one is clipped to the deadline "
    + "rather than overshooting it");
});

await check("a caller asking for an hour is clamped to the ceiling", async () => {
  const b = await bench();
  const v = vendor(() => []);
  const c = clock(NOW);
  const out = await waitForConnection(null,
    waitOpts(b, v, c, { deadline: NOW + 60 * 60 * 1000 }));
  assert.equal(out.state, "never-appeared");
  assert.ok(c.at() <= NOW + WAIT_CEILING_MS,
    `an hour-long deadline was honoured (+${c.at() - NOW}ms); past the vendor link's own `
    + "ten minutes this attempt cannot produce an account at all");
});

await check("a clock that never moves is still bounded — MAX_VENDOR_CALLS is the second exit",
  async () => {
    const b = await bench();
    const v = vendor(() => []);
    const frozen = clock(NOW, { frozen: true });
    const out = await waitForConnection(null, waitOpts(b, v, frozen));
    assert.equal(out.state, "never-appeared");
    assert.equal(v.asked.length, MAX_VENDOR_CALLS,
      "a loop whose only exit is a clock is a loop with no exit");
  });

await check("a store that fails EVERY tick is bounded too, under a clock that never moves",
  async () => {
    // The turn of the loop that never reaches the vendor. Bounding on vendor
    // calls alone leaves this iteration costing nothing and therefore never
    // counted: a frozen clock plus a dead store is an infinite loop inside a
    // promise nobody awaits. If this check hangs, that is the bug.
    const b = await bench();
    const v = vendor(() => []);
    const frozen = clock(NOW, { frozen: true });
    const realRead = b.store.read.bind(b.store);
    let n = 0;
    b.store.read = async (h: string): Promise<StoredLink | null> => {
      n++;
      if (n === 1) return await realRead(h);     // the pre-flight read succeeds
      throw new Error("D1_ERROR: the store is gone");
    };
    const out = await waitForConnection(null, waitOpts(b, v, frozen));
    assert.equal(out.state, "never-appeared");
    assert.ok(frozen.slept.length <= MAX_VENDOR_CALLS,
      `the loop turned ${frozen.slept.length} times with a dead store and a stopped clock`);
    assert.equal(v.asked.length, 1, "only the baseline ever reached the vendor");
  });

await check("a deadline already in the past starts nothing", async () => {
  const b = await bench();
  const v = vendor(() => [acct(ACCOUNT_NEW)]);
  const out = await waitForConnection(null,
    waitOpts(b, v, clock(NOW), { deadline: NOW - 1 }));
  assert.equal(out.state, "not-started");
  assert.equal(v.asked.length, 0, "not one vendor call");
  assert.equal(b.store.reads, 0, "and the store was never even read");
});

// ===========================================================================
// 5. WHAT IS NOT EVIDENCE
// ===========================================================================

await check("an account that was already connected before the tap is NOT this attempt's",
  async () => {
    // The owner's personal mailbox is already ACTIVE. They tap a link for the
    // same toolkit and abandon it. Recording the old account would bind the
    // wrong one under this link's alias and flip the nudge to connected on a
    // connect that never finished.
    const b = await bench({ alias: "work" });
    const v = vendor(() => [acct(ACCOUNT_OLD, { alias: "personal" })]);
    const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
    assert.equal(out.state, "never-appeared");
    assert.equal(b.written.length, 0,
      "an account that pre-dates the attempt is not evidence the attempt landed");
  });

await check("a SECOND account appearing beside the old one is recorded, and it is the new one",
  async () => {
    const b = await bench({ alias: "work" });
    const v = vendor((n) => (n === 1
      ? [acct(ACCOUNT_OLD, { alias: "personal" })]
      : [acct(ACCOUNT_OLD, { alias: "personal" }), acct(ACCOUNT_NEW, { alias: "work" })]));
    const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
    assert.equal(out.state, "recorded");
    assert.equal(b.written[0]?.connected_account_id, ACCOUNT_NEW,
      "the account the baseline did not hold is the one this attempt produced");
  });

await check("two new accounts at once are ambiguous, and nothing is written", async () => {
  const b = await bench();
  const v = vendor((n) => (n === 1 ? [] : [acct("ca_A"), acct("ca_B")]));
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(out.state, "ambiguous");
  assert.equal(b.written.length, 0, "which one this link's alias belongs to is not a guess");
  assert.equal(b.store.get(b.handle)?.completed_at, null, "the lease is left for the callback");
});

await check("an EXPIRED credential is not a connection", async () => {
  const b = await bench();
  const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW, { status: "needs_reconnect" })]));
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(out.state, "never-appeared");
  assert.equal(b.written.length, 0,
    "recording a dead credential as live routes the owner's next task to a hand "
    + "with no key and they watch it fail");
});

await check("an account on ANOTHER toolkit is not this link's", async () => {
  const b = await bench();
  const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW, { toolkit: "quandle_mail" })]));
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(out.state, "never-appeared");
  assert.equal(b.written.length, 0, "a calendar credential must not be filed under the mail row");
});

await check("an account the vendor binds to a STRANGER is never adopted", async () => {
  const b = await bench();
  const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW, { user_id: STRANGER })]));
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(out.state, "never-appeared");
  assert.equal(b.written.length, 0,
    "the list was asked for BY OWNER, so a row bound to anybody else means the scoping "
    + "did not hold — one operator's mailbox serving everybody, arrived at from the poll");
});

await check("a vendor answer that is not a list is UNREADABLE, never 'they have nothing'",
  async () => {
    // THE DISTINCTION THAT MATTERS: `[]` is a claim; a 500 body is not. If an
    // unreadable answer were read as an empty list it would become an EMPTY
    // baseline, and the account this owner had connected last year would look
    // brand new — recorded as this attempt's, nudge flipped, on a connect that
    // never happened. So the unreadable answer is retried and the baseline is
    // whatever the first READABLE answer says.
    const b = await bench();
    const v = vendor((n) => (n === 1 ? { error: "gateway" } : [acct(ACCOUNT_OLD)]));
    const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
    assert.equal(out.state, "never-appeared",
      "an unreadable answer read as an empty list would make a pre-existing account "
      + "look like this attempt's");
    assert.equal(b.written.length, 0);
  });

await check("a blip before the baseline costs the poll its chance, and that is the safe way "
  + "to be wrong", async () => {
    // Written down rather than left to be discovered. Until a readable answer
    // arrives there is nothing to compare against, so the first readable one
    // becomes the baseline however late it is — and an account that appeared
    // while the vendor was unreachable is inside it. The poll then records
    // nothing, which loses a backup; the alternative loses a mailbox.
    const b = await bench();
    const v = vendor((n) => (n <= 2 ? new Error("502") : [acct(ACCOUNT_NEW)]));
    const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
    assert.equal(out.state, "never-appeared");
    assert.equal(b.written.length, 0);
  });

await check("a vendor blip AFTER the baseline is not a verdict — the poll keeps going",
  async () => {
    const b = await bench();
    const v = vendor((n) => {
      if (n === 1) return [];
      if (n <= 4) return new Error("502");
      return [acct(ACCOUNT_NEW)];
    });
    const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
    assert.equal(out.state, "recorded",
      "three bad gateways in a row must not decide a connection does not exist");
  });

await check("a store blip mid-poll is not a verdict either", async () => {
  const b = await bench();
  const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW)]));
  b.store.failReads = 0;
  const c = clock(NOW);
  // Fail the first in-loop read only; the pre-flight read has already happened.
  const realRead = b.store.read.bind(b.store);
  let seen = 0;
  b.store.read = async (h: string): Promise<StoredLink | null> => {
    seen++;
    if (seen === 2) throw new Error("D1_ERROR: no");
    return await realRead(h);
  };
  const out = await waitForConnection(null, waitOpts(b, v, c));
  assert.equal(out.state, "recorded", "a D1 blip must not decide a connection does not exist");
});

// ===========================================================================
// 6. THE OWNER COMES FROM THE STORED ROW
// ===========================================================================

await check("an owner the stored row disagrees with is refused before any vendor call",
  async () => {
    const b = await bench();
    const v = vendor(() => [acct(ACCOUNT_NEW, { user_id: STRANGER })]);
    const out = await waitForConnection(null,
      waitOpts(b, v, clock(NOW), { owner: STRANGER }));
    assert.equal(out.state, "not-started");
    assert.equal(v.asked.length, 0, "a confused caller never reaches the vendor");
    assert.equal(b.written.length, 0);
  });

await check("a toolkit the stored row disagrees with is refused too", async () => {
  const b = await bench();
  const v = vendor(() => [acct(ACCOUNT_NEW, { toolkit: "quandle_mail" })]);
  const out = await waitForConnection(null,
    waitOpts(b, v, clock(NOW), { toolkit: "quandle_mail" }));
  assert.equal(out.state, "not-started");
  assert.equal(v.asked.length, 0);
});

await check("the vendor is asked about the STORED row's owner and nobody else", async () => {
  const b = await bench();
  const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW)]));
  await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.ok(v.asked.length > 0);
  for (const who of v.asked) {
    assert.equal(who, OWNER, "every vendor read is scoped to the owner on the link row");
  }
});

await check("a link that never went through /go starts nothing", async () => {
  const b = await bench({ used_at: null });
  const v = vendor(() => [acct(ACCOUNT_NEW)]);
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(out.state, "not-started");
  assert.equal(v.asked.length, 0, "there is no round trip for this poll to be the backup for");
});

await check("a link already completed starts nothing and costs nothing", async () => {
  const b = await bench({ completed_at: NOW - 5 });
  const v = vendor(() => [acct(ACCOUNT_NEW)]);
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(out.state, "already-recorded");
  assert.equal(v.asked.length, 0);
});

await check("a malformed handle never reaches the store", async () => {
  const b = await bench();
  const v = vendor(() => [acct(ACCOUNT_NEW)]);
  for (const bad of ["", "not-hex", "A".repeat(64), b.handle.slice(0, 63), "../etc"]) {
    const out = await waitForConnection(null, waitOpts(b, v, clock(NOW), { handle: bad }));
    assert.equal(out.state, "not-started", `handle ${JSON.stringify(bad)} was not refused`);
  }
  assert.equal(b.store.reads, 0, "an untrusted handle must not reach a query");
  assert.equal(v.asked.length, 0);
});

await check("a row that vanishes between polls is link-gone, not a connection", async () => {
  // Deleted during the BASELINE call, so the in-loop row read is the leg that
  // notices.
  const b = await bench();
  const v = vendor((n) => {
    if (n === 1) { b.store.rows.delete(b.handle); return []; }
    return [acct(ACCOUNT_NEW)];
  });
  const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
  assert.equal(out.state, "link-gone");
  assert.equal(b.written.length, 0);
});

await check("a row that vanishes UNDER THE LEASE is link-gone, not 'somebody else recorded it'",
  async () => {
    // The other leg: the row survives the read and is gone by the time the
    // compare-and-set runs. `complete` changes nothing either way, and reading
    // that as "the callback handled it" would put a false all-clear in the log
    // for a link that no longer exists.
    const b = await bench();
    const v = vendor((n) => {
      if (n === 1) return [];
      b.store.rows.delete(b.handle);
      return [acct(ACCOUNT_NEW)];
    });
    const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));
    assert.equal(out.state, "link-gone");
    assert.equal(b.written.length, 0);
  });

// ===========================================================================
// 7. THE LEASE IS A PROMISE, NOT A RECEIPT
// ===========================================================================

await check("a failed write hands the lease BACK, so the callback can still record it",
  async () => {
    const b = await bench({}, true);          // onConnected throws
    const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW)]));
    const out = await waitForConnection(null, waitOpts(b, v, clock(NOW)));

    assert.equal(out.state, "not-recorded");
    assert.equal(b.store.get(b.handle)?.completed_at, null,
      "a burned lease with no row anywhere is permanent silent data loss: the page says "
      + "connected forever, the account exists at the vendor, and no webhook will "
      + "ever mention it again");

    // And the proof that the hand-back is worth something: the callback now works.
    const done = await connectPageDone(
      b.token, { status: "success", connectedAccountId: ACCOUNT_NEW },
      {
        signedInAs: OWNER, store: b.store,
        provider: { async connections(): Promise<Connection[]> { return [acct(ACCOUNT_NEW)]; } },
        onConnected: async (): Promise<void> => {}, now: NOW + 1,
      },
    );
    assert.equal(done.state, "connected");
    assert.equal((done as { recorded: boolean }).recorded, true);
  });

await check("a store with no release still answers honestly rather than throwing", async () => {
  const b = await bench({}, true);
  const v = vendor((n) => (n === 1 ? [] : [acct(ACCOUNT_NEW)]));
  const noRelease = {
    read: b.store.read.bind(b.store),
    claim: b.store.claim.bind(b.store),
    complete: b.store.complete.bind(b.store),
  } as unknown as ConnectLinkStore;
  const out = await waitForConnection(null,
    waitOpts(b, v, clock(NOW), { store: noRelease }));
  assert.equal(out.state, "not-recorded");
});

await check("waitForConnection never throws, whatever the store does", async () => {
  const b = await bench();
  const v = vendor(() => [acct(ACCOUNT_NEW)]);
  const exploding = {
    async read(): Promise<StoredLink | null> { throw new Error("D1_ERROR: gone"); },
    async claim(): Promise<ClaimOutcome> { throw new Error("no"); },
    async complete(): Promise<ClaimOutcome> { throw new Error("no"); },
    async release(): Promise<ClaimOutcome> { throw new Error("no"); },
  } as unknown as ConnectLinkStore;
  let out: WaitOutcome | null = null;
  await assert.doesNotReject(async () => {
    out = await waitForConnection(null, waitOpts(b, v, clock(NOW), { store: exploding }));
  }, "it runs in ctx.waitUntil, where an unhandled rejection lands on a request "
    + "that was answered minutes ago");
  assert.equal((out as unknown as WaitOutcome | null)?.state, "failed");
});

// ===========================================================================
// 8. THE BUDGET SWITCH
// ===========================================================================

await check("waitBudgetMs: default, off, clamp, and an unreadable value", () => {
  assert.equal(waitBudgetMs(null), WAIT_BUDGET_MS);
  assert.equal(waitBudgetMs({}), WAIT_BUDGET_MS);
  assert.equal(waitBudgetMs({ CONNECT_WAIT_MS: "" }), WAIT_BUDGET_MS);
  assert.equal(waitBudgetMs({ CONNECT_WAIT_MS: "0" }), 0, "zero is the operator's off switch");
  assert.equal(waitBudgetMs({ CONNECT_WAIT_MS: 1234 }), 1234);
  assert.equal(waitBudgetMs({ CONNECT_WAIT_MS: " 90000 " }), 90000);
  assert.equal(waitBudgetMs({ CONNECT_WAIT_MS: String(60 * 60 * 1000) }), WAIT_CEILING_MS,
    "no configuration may put a Worker request context to sleep for an hour");
  for (const junk of ["banana", "-5", "NaN", {}, true]) {
    assert.equal(waitBudgetMs({ CONNECT_WAIT_MS: junk }), WAIT_BUDGET_MS,
      `an unreadable ${JSON.stringify(junk)} must fall back to the DEFAULT, not to off — `
      + "a typo in a dashboard field must not silently delete the backup");
  }
});

await check("the fingerprint is the callback's fingerprint, and never a token", async () => {
  const token = newToken();
  const handle = await handleOf(token);
  assert.equal(linkFingerprint(handle), `link:${handle.slice(0, 12)}`,
    "byte-identical to routes/connect.ts tokenFingerprint, so the redirect line and the "
    + "outcome line correlate without either carrying a token");
  assert.ok(!linkFingerprint(handle).includes(token));
  assert.equal(linkFingerprint(null), "link:none");
});

await check("the fingerprint never reprints what it was handed", () => {
  // It goes into a log line, and a log line must not be writable by whoever
  // called this function. A raw token here would put twelve characters of a
  // live credential into `wrangler tail`; the newline would let a caller forge
  // lines of their own.
  const rawToken = newToken();
  for (const junk of [rawToken, "../../etc/passwd", "aa\nconnect wait: all clear",
                      "AAAA".repeat(16), "", 42, {}]) {
    assert.equal(linkFingerprint(junk), "link:none",
      `linkFingerprint echoed ${JSON.stringify(junk)} into a log line`);
  }
});

// ===========================================================================
// 9. /go STARTS IT — DRIVEN AS HTTP, ON THE REAL ROUTE
// ===========================================================================

const APPS: Record<string, ToolkitMeta> = {
  [TOOLKIT]: {
    slug: TOOLKIT, name: "Zellibrix", logo: null,
    description: "Where your team keeps its notes.", appUrl: null,
    scopes: ["notes.read"],
  },
};
const VENDOR_URL = "https://vendor.example.invalid/link/abc123";

interface RouteRig {
  db: FakeD1;
  env: ConnectEnv;
  deps: ConnectDeps;
  store: MemoryStore;
  token: string;
  handle: string;
  ownerToken: string;
  written: Connection[];
  asked: string[];
  ctx: { waitUntil(p: Promise<unknown>): void; tasks: Promise<unknown>[] };
}

async function routeRig(opts: {
  budget?: string;
  holds?: (call: number) => Connection[];
} = {}): Promise<RouteRig> {
  const db = new FakeD1();
  db.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,'','')`,
  ).run(OWNER, PB_NOW, PB_NOW, `${OWNER}@anticipy-test.invalid`, "key-owner");

  const env = {
    DB: asD1(db),
    ANTICIPY_AUTH_SECRET: "connections-wait-test-secret",
    ...(opts.budget === undefined ? {} : { CONNECT_WAIT_MS: opts.budget }),
  } as unknown as ConnectEnv;

  const token = newToken();
  const handle = await handleOf(token);
  const store = new MemoryStore();
  // A REAL clock here: the poll runs in background time, so a frozen one would
  // be measuring something that does not happen in production.
  store.put({
    token_handle: handle, user_id: OWNER, toolkit: TOOLKIT, alias: null,
    expires_at: Date.now() + LINK_TTL_MS, used_at: null, completed_at: null,
  });

  const written: Connection[] = [];
  const asked: string[] = [];
  const holds = opts.holds ?? ((n: number) => (n === 1 ? [] : [acct(ACCOUNT_NEW)]));
  const deps: ConnectDeps = {
    store,
    provider: {
      async toolkit(s: string): Promise<ToolkitMeta> {
        const meta = APPS[s];
        if (!meta) throw new Error(`no catalog row for ${s}`);
        return meta;
      },
      async authorize(): Promise<{ redirectUrl: string }> { return { redirectUrl: VENDOR_URL }; },
      async connections(user: string): Promise<Connection[]> {
        asked.push(user);
        return holds(asked.length);
      },
    },
    words: {
      sentences: async (): Promise<string[]> => ["It can read your notes when you ask."],
    },
    onConnected: async (c: Connection): Promise<void> => { written.push(c); },
    now: () => Date.now(),
  };

  const tasks: Promise<unknown>[] = [];
  return {
    db, env, deps, store, token, handle, written, asked,
    ownerToken: await issueToken(env as never, OWNER, "key-owner"),
    ctx: { tasks, waitUntil(p: Promise<unknown>): void { tasks.push(p); } },
  };
}

function goReq(token: string, auth: string): Request {
  return new Request(`https://api.anticipy.ai/c/${token}/go`, {
    method: "POST",
    headers: {
      Authorization: auth,
      Origin: "https://api.anticipy.ai",
      "content-type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({}),
  });
}

await check("/go hands the poll to waitUntil and redirects without waiting on it", async () => {
  const r = await routeRig({ budget: "300" });
  let finished = false;

  const t0 = Date.now();
  const res = await connectRoute(goReq(r.token, r.ownerToken), r.env, r.deps, r.ctx);
  const elapsed = Date.now() - t0;

  assert.equal(res.status, 303, "the redirect is the redirect");
  assert.equal(res.headers.get("location"), VENDOR_URL);
  assert.equal(r.ctx.tasks.length, 1, "exactly one background task was handed to waitUntil");
  r.ctx.tasks[0]?.then(() => { finished = true; });
  assert.equal(finished, false, "the redirect did not wait on the poll");
  assert.ok(elapsed < 150,
    `the redirect took ${elapsed}ms — /go must not be delayed by a poll with a `
    + "300ms budget");

  await Promise.all(r.ctx.tasks);
  assert.equal(r.written.length, 1, "and the poll then recorded the connection");
  assert.equal(r.written[0]?.user_id, OWNER);
  assert.equal(r.written[0]?.connected_account_id, ACCOUNT_NEW);
  assert.deepEqual(r.asked, [OWNER, OWNER],
    "the vendor was asked about the owner on the STORED row, twice: a baseline and a poll");
});

await check("CONTROL: a normal callback flow is unaffected and does not wait on the poll",
  async () => {
    // The whole ordinary path — page, tap, callback — with the poll running
    // underneath it. Nothing about the callback may change.
    const r = await routeRig({ budget: "300" });
    const auth = `Bearer ${r.ownerToken}`;

    const view = await connectRoute(
      new Request(`https://api.anticipy.ai/c/${r.token}`, { headers: { Authorization: auth } }),
      r.env, r.deps, r.ctx);
    assert.equal(view.status, 200, "the page still draws");
    assert.equal(r.ctx.tasks.length, 0, "and viewing starts no poll: nothing is in flight yet");

    const go = await connectRoute(goReq(r.token, r.ownerToken), r.env, r.deps, r.ctx);
    assert.equal(go.status, 303);

    const done = await connectRoute(
      new Request(
        `https://api.anticipy.ai/c/${r.token}/done`
        + `?status=success&connected_account_id=${ACCOUNT_NEW}`,
        { headers: { Cookie: `${SESSION_COOKIE}=${r.ownerToken}` } },
      ), r.env, r.deps, r.ctx);

    assert.equal(done.status, 200, "the callback still answers 200");
    const body = await done.text();
    assert.ok(body.includes("Connected."), "and still says Connected");
    assert.equal(r.written.length, 1, "the callback wrote it");

    // Now let the poll finish. It must find the lease taken and add nothing.
    await Promise.all(r.ctx.tasks);
    assert.equal(r.written.length, 1,
      "the backup must be invisible when the primary worked — one connection, one flip");
    assert.equal(r.store.get(r.handle)?.completed_at !== null, true);
  });

await check("CONTROL: with the backup switched off /go is byte-identical and starts nothing",
  async () => {
    const on = await routeRig({ budget: "300" });
    const off = await routeRig({ budget: "0" });

    const a = await connectRoute(goReq(on.token, on.ownerToken), on.env, on.deps, on.ctx);
    const z = await connectRoute(goReq(off.token, off.ownerToken), off.env, off.deps, off.ctx);

    assert.equal(z.status, a.status);
    assert.equal(z.headers.get("location"), a.headers.get("location"));
    assert.equal(await z.text(), await a.text());
    assert.equal(off.ctx.tasks.length, 0, "CONNECT_WAIT_MS=0 starts no poll at all");
    assert.equal(off.asked.length, 0, "and spends no vendor call");
    await Promise.all(on.ctx.tasks);
  });

await check("a refused /go starts no poll", async () => {
  // A spent link. Nothing is in flight, so there is nothing to be the backup
  // for — and starting a poll here would spend vendor calls on every replayed
  // token anyone ever intercepts.
  const r = await routeRig({ budget: "300" });
  r.store.rows.set(r.handle, { ...r.store.rows.get(r.handle)!, used_at: Date.now() - 1 });
  const res = await connectRoute(goReq(r.token, r.ownerToken), r.env, r.deps, r.ctx);
  assert.notEqual(res.status, 303);
  assert.equal(r.ctx.tasks.length, 0);
  assert.equal(r.asked.length, 0);
});

await check("with no ExecutionContext the redirect still works and NO poll is started",
  async () => {
    // Both halves matter. A missing ctx must never cost the person their
    // redirect — and it must not start a poll either: a Worker cancels an
    // unheld promise the moment the response is returned, so it would finish
    // nothing in production, and off a Worker it is a real timer nobody holds
    // a handle to. That is not a backup; it is a suite that hangs.
    const r = await routeRig({ budget: "300" });
    const res = await connectRoute(goReq(r.token, r.ownerToken), r.env, r.deps);
    assert.equal(res.status, 303, "a missing ctx must never cost the person their redirect");
    assert.equal(res.headers.get("location"), VENDOR_URL);
    assert.equal(r.asked.length, 0, "and no poll was started behind it");
    // Nothing left running: if a timer had been armed, this suite could not
    // assert that, and the process would be the one to tell you, minutes later.
    await new Promise((done) => setTimeout(done, 20));
    assert.equal(r.asked.length, 0, "still nothing, twenty milliseconds later");
    assert.equal(r.written.length, 0);
  });

// ===========================================================================
// 10. SOURCE ANCHORS — each asserted to appear EXACTLY ONCE
// ===========================================================================

await check("the /go path is the only thing that starts the poll", () => {
  anchoredOnce(CONNECT_SRC,
    "    startWaiting(env, deps, token, go.owner, go.toolkit, now, ctx);",
    "routes/connect.ts");
  anchoredOnce(CONNECT_SRC, "ctx.waitUntil(task);", "routes/connect.ts");
  anchoredOnce(CONNECT_SRC, "waitForConnection(env, {", "routes/connect.ts");
  assert.equal(occurrences(CONNECT_SRC, "startWaiting("), 2,
    "startWaiting is declared once and called once — anything else means a second "
    + "leg of this file starts background work");
});

await check("the poll's owner and toolkit come off the redeemed link, not the request", () => {
  anchoredOnce(CONNECT_SRC,
    "return { state: \"ok\", redirectUrl, owner: link.user_id, toolkit: link.toolkit };",
    "routes/connect.ts");
  assert.equal(occurrences(CONNECT_SRC, "go.owner"), 1);
  assert.equal(occurrences(CONNECT_SRC, "signedInAs, toolkit"), 0,
    "nothing may hand the poll an owner read off the session or the request");
});

await check("the poll leases through the store the callback leases through", () => {
  anchoredOnce(WAIT_SRC, "const lease = await opts.store.complete(row.token_handle, at);",
    "connections/wait.ts");
  anchoredOnce(WAIT_SRC, "await opts.store.release(row.token_handle, at);",
    "connections/wait.ts");
  assert.equal(occurrences(WAIT_SRC, "completed_at ="), 0,
    "the lease is taken through the store's compare-and-set, never written by hand");
});

await check("the ceiling and the status floor are each in exactly one place", () => {
  anchoredOnce(WAIT_SRC, "const deadline = Math.min(opts.deadline, started + WAIT_CEILING_MS);",
    "connections/wait.ts");
  anchoredOnce(WAIT_SRC, "if (item.status !== \"connected\") continue;", "connections/wait.ts");
  anchoredOnce(WAIT_SRC, "writes_enabled: false,", "connections/wait.ts");
});

await check("wait.ts imports routes/connect.ts as TYPES only, so the graph stays acyclic", () => {
  anchoredOnce(WAIT_SRC, "import type {", "connections/wait.ts");
  assert.equal(occurrences(WAIT_SRC, "from \"../routes/connect.ts\""), 1);
  assert.equal(occurrences(WAIT_SRC, "import {"), 0,
    "a value import of routes/connect.ts would make connect.ts <-> wait.ts a real "
    + "cycle at run time");
});

await check("the vendor's name exists in wait.ts only where a person can never read it", () => {
  // The same rule connect-routes.test.ts applies to routes/connect.ts. COMMENTS
  // MAY NAME IT and here they must: the measured failure this module was
  // written from lives in a research file whose name carries the vendor, and a
  // citation nobody can follow is Law 4 failing inside the fix for it. What may
  // not exist is the name in CODE, where a value could reach a screen or a log.
  const code = WAIT_SRC
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
  assert.ok(code.length > 3000, "the comment stripper ate the file; the scan proves nothing");
  assert.ok(!/composio/i.test(code),
    "connections/wait.ts carries the vendor's name outside a comment");
  assert.equal(occurrences(WAIT_SRC, "research/2026-09-05-composio-connections.md"), 2,
    "and the two citations that justify the bound and the baseline are still there");
});

await check("src/index.ts hands the Worker's ExecutionContext to connectRoute", () => {
  // THE REASON THIS LEG EXISTS. Everything else in this file passed while the
  // poll was DEAD IN PRODUCTION: `fetch` took `_ctx` and threw it away, and
  // `connectRoute` was called with three arguments. connect.ts refuses to start
  // the poll without a ctx — correctly, because a Worker cancels background
  // work the moment a response is returned and a bare timer off a Worker is one
  // nobody can join — so every /go logged "the connection backup did NOT start"
  // and every suite here stayed green. A part nothing calls is the measured
  // failure of this repo, and it had already happened twice today.
  //
  // Anchored on literals that occur EXACTLY ONCE, and asserted to occur exactly
  // once: an anchor that silently matches nothing has produced three false
  // "it is tested" readings this week.
  const wired = "return connectRoute(request, env as unknown as ConnectEnv, undefined, ctx);";
  const n = INDEX_SRC.split(wired).length - 1;
  assert.equal(n, 1,
    `src/index.ts contains ${n} copies of ${JSON.stringify(wired)}. Without ` +
    "the fourth argument the connection backup never runs, and a browser that " +
    "dies between the vendor and /done loses the connection permanently.");

  // And the parameter it comes from is named, not discarded. `_ctx` is the
  // exact shape this was in when it was dark.
  assert.ok(
    /async fetch\(request: Request, env: Env, ctx: ExecutionContext\)/.test(INDEX_SRC),
    "src/index.ts's fetch does not bind `ctx`; a leading underscore here is " +
    "how the ExecutionContext was thrown away in the first place");
  assert.ok(
    !/async fetch\([^)]*_ctx[^)]*\)/.test(INDEX_SRC),
    "src/index.ts's fetch still binds `_ctx`");
});

console.log(`connections-wait: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
