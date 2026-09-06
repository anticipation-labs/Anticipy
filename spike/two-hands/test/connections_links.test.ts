// WHAT THESE TESTS ARE DEFENDING.
//
// One thing, mostly: that a connect link cannot bind an app to the wrong
// person. Everything else in this file is downstream of that sentence. A text
// message is readable over a shoulder, sits in a synced Messages database and
// passes through a carrier log, so the link in it must be worth nothing on its
// own — worth nothing to whoever intercepts it, worth nothing twice, and worth
// nothing after ten minutes.
//
// The second thing is the measured failure of 2026-09-05: four Composio connect
// links generated at SEND time, all four dead before anyone tapped them
// (research/2026-09-05-composio-connections.md, item 3). The test named "mint
// asks the vendor for nothing" is that receipt, and it is the one that goes red
// if somebody ever moves `authorize` back to mint time to save a round trip.
//
// No network, no key, no account, no vendor. Every stub below is local, and the
// two stub toolkits are invented slugs on purpose: if any assertion in this
// file depended on an app being Gmail or Notion, the module would have an app
// list in it and HARNESS-LAWS law 1 would have been broken by its own tests.
//
//   node --experimental-strip-types --test test/connections_links.test.ts

import test from "node:test";
import assert from "node:assert/strict";

import {
  CALLBACK_SUCCESS,
  CALLBACK_WINDOW_MS,
  CONNECT_URL_BASE,
  MemoryConnectLinkStore,
  TOKEN_CHARS,
  callbackUrl,
  connectPageDone,
  connectPageGo,
  connectPageView,
  connectUrl,
  mint,
  parseConnectPath,
  redeem,
  tokenFingerprint,
  tokenHandle,
  type ClaimOutcome,
  type ConnectLinkStore,
  type StoredLink,
} from "../src/connections/links.ts";
import { LINK_TTL_MS, ownerId, type Connection, type ToolkitMeta } from "../src/connections/contract.ts";

// ---------------------------------------------------------------------------
// LOCAL STUBS. Nothing here imports another agent's module.
// ---------------------------------------------------------------------------

const OWNER = ownerId("sxkotd1h02qb6gw");
const STRANGER = ownerId("qeuy6sv1raof9rw");

// Two toolkits nobody has ever heard of. If the module works for these it works
// for whatever the catalog adds next week, which is the actual requirement.
const SLUG_A = "kettlebright";
const SLUG_B = "morrowdesk";

const tick = () => new Promise<void>((r) => setTimeout(r, 0));

interface AuthorizeCall {
  user: string;
  toolkit: string;
  callbackUrl: string;
  alias: string | null | undefined;
}

/**
 * An account the vendor really is holding for an owner.
 *
 * The callback's `connected_account_id` is the VENDOR's handle for whichever
 * credential answered, and a query string is not evidence of whose it is. So
 * every `done` test below has to say what the vendor would actually report if
 * asked — which is the whole point of asking.
 */
function acct(
  id: string,
  over: { user?: string; toolkit?: string; alias?: "work" | "personal" | null } = {},
): Connection {
  return {
    user_id: (over.user ?? OWNER) as Connection["user_id"],
    toolkit: over.toolkit ?? SLUG_A,
    connected_account_id: id,
    alias: over.alias ?? "work",
    status: "connected",
    writes_enabled: false,
    last_used_at: null,
  };
}

function stubProvider(opts: {
  authorize?: () => never | { redirectUrl: unknown };
  failToolkit?: boolean;
  /** What `connections(user)` will report. Empty by default: a vendor that has
   *  never heard of the account on the callback is the DEFAULT case, not the
   *  exotic one, and a stub that vouched for anything would make the ownership
   *  check untestable. */
  accounts?: Connection[];
  failConnections?: boolean;
} = {}) {
  const authorizeCalls: AuthorizeCall[] = [];
  const toolkitCalls: string[] = [];
  const connectionsCalls: string[] = [];
  return {
    authorizeCalls,
    toolkitCalls,
    connectionsCalls,
    /** The vendor's own list for this owner. Scoped by the argument, so a stub
     *  that returned somebody else's row would be modelling a broken vendor —
     *  which one test below does deliberately. */
    async connections(user: string): Promise<Connection[]> {
      connectionsCalls.push(user);
      if (opts.failConnections) throw new Error("composio 503 — connected_accounts unreachable");
      return (opts.accounts ?? []).map((c) => ({ ...c }));
    },
    async toolkit(slug: string): Promise<ToolkitMeta> {
      toolkitCalls.push(slug);
      if (opts.failToolkit) throw new Error("catalog unreachable");
      // Generated from the slug, never from a table of apps.
      return {
        slug,
        name: slug.toUpperCase(),
        logo: `https://cdn.example/${slug}.png`,
        description: `the ${slug} app`,
        appUrl: `https://${slug}.example`,
        scopes: [`${slug}.read`, `${slug}.write`],
      };
    },
    async authorize(
      user: string,
      toolkit: string,
      o: { callbackUrl: string; alias?: string | null },
    ): Promise<{ redirectUrl: string }> {
      authorizeCalls.push({ user, toolkit, callbackUrl: o.callbackUrl, alias: o.alias });
      if (opts.authorize) return opts.authorize() as { redirectUrl: string };
      return { redirectUrl: `https://vendor.example/link/${toolkit}` };
    },
  };
}

// Sentences generated from the toolkit's own scopes. The register the spec
// fixes ("connect your X", never "authorize" or "permissions") is the words
// module's job, not this one's; this stub only proves the seam is wired.
const words = {
  async sentences(meta: ToolkitMeta): Promise<string[]> {
    return meta.scopes.map((s) => `Anticipy can use your ${meta.name} to ${s}.`);
  },
};

function sink() {
  const recorded: Connection[] = [];
  return {
    recorded,
    onConnected: async (c: Connection) => {
      recorded.push(c);
    },
  };
}

/**
 * A store that behaves like a real one over a network: every call yields the
 * event loop before and after, so two concurrent redeems genuinely interleave
 * instead of running to completion one after the other. The compare-and-set
 * itself is delegated untouched — the latency is around it, which is where a
 * D1 round trip's latency actually is.
 */
class YieldingStore implements ConnectLinkStore {
  inner = new MemoryConnectLinkStore();
  puts = 0;
  reads = 0;
  claims = 0;
  completes = 0;
  releases = 0;
  async put(row: StoredLink): Promise<void> {
    this.puts++;
    await tick();
    return this.inner.put(row);
  }
  async read(handle: string): Promise<StoredLink | null> {
    this.reads++;
    await tick();
    const row = await this.inner.read(handle);
    await tick();
    return row;
  }
  async claim(handle: string, usedAt: number): Promise<ClaimOutcome> {
    this.claims++;
    await tick();
    const out = await this.inner.claim(handle, usedAt);
    await tick();
    return out;
  }
  async complete(handle: string, at: number): Promise<ClaimOutcome> {
    this.completes++;
    await tick();
    const out = await this.inner.complete(handle, at);
    await tick();
    return out;
  }
  async release(handle: string, at: number): Promise<ClaimOutcome> {
    this.releases++;
    await tick();
    const out = await this.inner.release(handle, at);
    await tick();
    return out;
  }
}

/**
 * D1 serves reads from a replica that can be seconds behind the write. This
 * store models the worst version of that: `read` ALWAYS reports the link as
 * fresh and never completed, while the compare-and-sets tell the truth. Any
 * implementation that decides "already used" from the row it read hands out a
 * second "ok" here.
 */
class StaleReplicaStore implements ConnectLinkStore {
  inner = new MemoryConnectLinkStore();
  put(row: StoredLink) {
    return this.inner.put(row);
  }
  async read(handle: string): Promise<StoredLink | null> {
    const row = await this.inner.read(handle);
    return row ? { ...row, used_at: null, completed_at: null } : null;
  }
  claim(handle: string, usedAt: number) {
    return this.inner.claim(handle, usedAt);
  }
  complete(handle: string, at: number) {
    return this.inner.complete(handle, at);
  }
  release(handle: string, at: number) {
    return this.inner.release(handle, at);
  }
}

const T0 = 1_757_000_000_000;

async function freshLink(store: ConnectLinkStore, over: { toolkit?: string; alias?: "work" | "personal" | null; now?: number } = {}) {
  return mint(OWNER, over.toolkit ?? SLUG_A, {
    store,
    alias: over.alias ?? "work",
    now: over.now ?? T0,
  });
}

// ---------------------------------------------------------------------------
// MINT
// ---------------------------------------------------------------------------

test("a token is 43 url-safe base64 characters and never repeats", async () => {
  const store = new MemoryConnectLinkStore();
  const seen = new Set<string>();
  for (let i = 0; i < 200; i++) {
    const link = await freshLink(store);
    assert.equal(link.token.length, TOKEN_CHARS);
    assert.match(link.token, /^[A-Za-z0-9_-]{43}$/);
    seen.add(link.token);
  }
  assert.equal(seen.size, 200);
});

test("MINT ASKS THE VENDOR FOR NOTHING — the 2026-09-05 receipt", async () => {
  // Four Composio links were generated at send time and all four expired
  // unused, because the vendor's own link lives ten minutes. If this test ever
  // fails, somebody has moved the vendor call back to send time and the links
  // in tonight's texts are dead on arrival again.
  //
  // The first draft of this test asserted that a provider `mint` had no way of
  // reaching was never called, which is a test that reads as compliant and
  // enforces nothing. The tripwire below is the real check: it is a provider
  // handed to `mint` on which ANY property access throws, so the day somebody
  // adds a provider to MintOptions and calls it, this goes red rather than
  // green. The counted calls afterwards are the other half — zero vendor calls
  // from mint through the page, exactly one at the tap.
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const tripwire = new Proxy({}, {
    get(_t, prop) {
      throw new Error(`mint reached the vendor: ${String(prop)}`);
    },
  });

  const link = await mint(OWNER, SLUG_A, {
    store,
    alias: "work",
    now: T0,
    provider: tripwire,
    authorize: tripwire,
  } as never);
  await mint(OWNER, SLUG_B, { store, now: T0, provider: tripwire } as never);
  assert.equal(provider.authorizeCalls.length, 0);

  await connectPageView(link.token, { signedInAs: OWNER, store, provider, words, now: T0 + 1 });
  assert.equal(provider.authorizeCalls.length, 0, "drawing the page must not mint a vendor link");

  await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 2 });
  assert.equal(provider.authorizeCalls.length, 1, "the vendor link is minted at the tap, once");
});

test("the link we send is ours, never the vendor's", async () => {
  const link = await freshLink(new MemoryConnectLinkStore());
  const url = connectUrl(link.token);
  assert.equal(url, `${CONNECT_URL_BASE}/${link.token}`);
  assert.ok(url.startsWith("https://anticipy.ai/c/"));
  // Nothing the mint hands back is a vendor URL — the whole object, not just
  // the fields we happen to look at.
  assert.ok(!JSON.stringify(link).includes("http"));
});

test("a link expires exactly LINK_TTL_MS after it was minted", async () => {
  const link = await freshLink(new MemoryConnectLinkStore(), { now: T0 });
  assert.equal(link.expires_at, T0 + LINK_TTL_MS);
  assert.equal(link.used_at, null);
});

test("a display name or an email where an owner id belongs is refused, and nothing is stored", async () => {
  // The failure this whole contract exists for: during the spike `user_id` was
  // "omar", which is how one operator's mailbox ends up serving everybody.
  const store = new MemoryConnectLinkStore();
  for (const bad of ["omar", "jose@anticipy.ai", "", "SXKOTD1H02QB6GW", "sxkotd1h02qb6g"]) {
    await assert.rejects(() => mint(bad, SLUG_A, { store }), /not an owner id/);
  }
  assert.equal(store.all().length, 0);
});

test("an alias outside the contract's two is refused", async () => {
  const store = new MemoryConnectLinkStore();
  await assert.rejects(
    () => mint(OWNER, SLUG_A, { store, alias: "Work" as never }),
    /alias must be/,
  );
  await assert.rejects(
    () => mint(OWNER, SLUG_A, { store, alias: "school" as never }),
    /alias must be/,
  );
  assert.equal(store.all().length, 0);
});

test("the store keeps a HANDLE, never the token", async () => {
  // A D1 backup, a `wrangler d1 execute` paste or a debugging dump must not be
  // a pile of live links.
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const dump = JSON.stringify(store.all());
  assert.ok(!dump.includes(link.token));
  assert.equal(store.all()[0]!.token_handle, tokenHandle(link.token));
});

test("a duplicate handle is refused rather than overwritten", async () => {
  // 256 bits do not collide by accident, so a second row with the same handle
  // means something is re-minting; overwriting would re-bind a link that is
  // already in somebody's pocket.
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const row = store.all()[0]!;
  await assert.rejects(() => store.put({ ...row, user_id: STRANGER }), /already exists/);
  const after = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 });
  assert.equal(after.outcome, "ok");
  assert.equal(after.outcome === "ok" && after.link.user_id, OWNER);
});

test("a slug is trimmed and lowercased, and separators are NOT collapsed", async () => {
  const store = new MemoryConnectLinkStore();
  const a = await mint(OWNER, "  MorrowDesk \n", { store, now: T0 });
  assert.equal(a.toolkit, "morrowdesk");
  // `x_y` and `x-y` are two different vendor primary keys. Guessing they are
  // one app would connect the wrong one; src/signature.ts collapses them
  // because there they are one planner WORD, which is a different question.
  const u = await mint(OWNER, "morrow_desk", { store, now: T0 });
  const h = await mint(OWNER, "morrow-desk", { store, now: T0 });
  assert.notEqual(u.toolkit, h.toolkit);
  await assert.rejects(() => mint(OWNER, "   ", { store }), /must not be empty/);
  await assert.rejects(() => mint(OWNER, 7 as never, { store }), /must be a slug string/);
});

// ---------------------------------------------------------------------------
// THE EXPIRY BOUNDARY
// ---------------------------------------------------------------------------

test("a link is alive one millisecond before it expires", async () => {
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const r = await redeem(link.token, { signedInAs: OWNER, store, now: link.expires_at - 1 });
  assert.equal(r.outcome, "ok");
});

test("a link is dead AT its expiry instant, not a millisecond after", async () => {
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const r = await redeem(link.token, { signedInAs: OWNER, store, now: link.expires_at });
  assert.equal(r.outcome, "expired");
  // And it stayed unspent, so nothing was consumed by the refusal.
  assert.equal(store.all()[0]!.used_at, null);
});

test("the page refuses at the same instant the redeem does", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  const alive = await connectPageView(link.token, {
    signedInAs: OWNER, store, provider, words, now: link.expires_at - 1,
  });
  assert.equal(alive.state, "ok");
  const dead = await connectPageView(link.token, {
    signedInAs: OWNER, store, provider, words, now: link.expires_at,
  });
  assert.equal(dead.state, "expired");
});

// ---------------------------------------------------------------------------
// SINGLE USE
// ---------------------------------------------------------------------------

test("a second redeem is already-used", async () => {
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const first = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 });
  const second = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 2 });
  assert.equal(first.outcome, "ok");
  assert.equal(second.outcome, "already-used");
  assert.equal(first.outcome === "ok" && first.link.used_at, T0 + 1);
});

test("two concurrent redeems yield exactly one ok", async () => {
  const store = new YieldingStore();
  const link = await freshLink(store);
  const [a, b] = await Promise.all([
    redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 }),
    redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 }),
  ]);
  const outcomes = [a.outcome, b.outcome].sort();
  assert.deepEqual(outcomes, ["already-used", "ok"]);
});

test("twenty-five concurrent redeems yield exactly one ok", async () => {
  const store = new YieldingStore();
  const link = await freshLink(store);
  const results = await Promise.all(
    Array.from({ length: 25 }, () =>
      redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 })),
  );
  assert.equal(results.filter((r) => r.outcome === "ok").length, 1);
  assert.equal(results.filter((r) => r.outcome === "already-used").length, 24);
});

test("the used bit is decided by the store's compare-and-set, NOT by the row that was read", async () => {
  // A read replica that is behind reports the link as fresh forever. An
  // implementation that read `used_at` and branched on it would hand out an
  // unlimited number of "ok"s here — one per stale read.
  const store = new StaleReplicaStore();
  const link = await freshLink(store);
  const first = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 });
  const second = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 2 });
  const third = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 3 });
  assert.equal(first.outcome, "ok");
  assert.equal(second.outcome, "already-used");
  assert.equal(third.outcome, "already-used");
});

test("redeem never writes the row itself — the only write is the claim", async () => {
  const store = new YieldingStore();
  const link = await freshLink(store);
  assert.equal(store.puts, 1); // the mint
  await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 });
  await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 2 });
  assert.equal(store.puts, 1);
  assert.equal(store.claims, 2);
});

// ---------------------------------------------------------------------------
// WRONG USER — the interception case
// ---------------------------------------------------------------------------

test("a stranger redeeming learns nothing at all", async () => {
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store, { toolkit: SLUG_B, alias: "personal" });
  const r = await redeem(link.token, { signedInAs: STRANGER, store, now: T0 + 1 });
  assert.deepEqual(r, { outcome: "wrong-user" });
  const leaked = JSON.stringify(r);
  for (const secret of [SLUG_B, OWNER, STRANGER, link.token, "personal"]) {
    assert.ok(!leaked.includes(secret), `wrong-user result leaked ${secret}`);
  }
});

test("A STRANGER CANNOT BURN THE OWNER'S LINK", async () => {
  // If a failed redeem consumed the token, anyone who read the text over a
  // shoulder could make every connect link the owner is sent dead on arrival —
  // a denial of service that looks exactly like the product being broken.
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  for (let i = 0; i < 5; i++) {
    assert.equal(
      (await redeem(link.token, { signedInAs: STRANGER, store, now: T0 + i })).outcome,
      "wrong-user",
    );
  }
  assert.equal(store.all()[0]!.used_at, null);
  const owner = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 9 });
  assert.equal(owner.outcome, "ok");
});

test("nobody signed in is not the owner, and does not spend the link", async () => {
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const r = await redeem(link.token, { signedInAs: null, store, now: T0 + 1 });
  assert.deepEqual(r, { outcome: "wrong-user" });
  assert.equal(store.all()[0]!.used_at, null);
});

test("a malformed session fails closed instead of throwing", async () => {
  // A 500 on a bad cookie is a denial of service handed to whoever can set one.
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  for (const junk of ["jose@anticipy.ai", "omar", "", 7, {}, undefined]) {
    const r = await redeem(link.token, { signedInAs: junk as never, store, now: T0 + 1 });
    assert.deepEqual(r, { outcome: "wrong-user" });
  }
  assert.equal(store.all()[0]!.used_at, null);
});

test("an expired link tells a stranger no more than it tells anyone else", async () => {
  // The order of the checks IS the privacy model. If the owner check came
  // first, a real-but-expired token would answer "wrong-user" forever, which
  // tells whoever intercepted the text that the token was genuine — long after
  // it could do anything, and permanently.
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const stranger = await redeem(link.token, { signedInAs: STRANGER, store, now: link.expires_at });
  const unknown = await redeem("D".repeat(43), { signedInAs: STRANGER, store, now: link.expires_at });
  assert.deepEqual(stranger, { outcome: "expired" });
  assert.deepEqual(stranger, unknown);
});

test("a store that answers with the wrong row is refused, not obeyed", async () => {
  // The lookup is by handle, so comparing the handle again looks redundant. It
  // is not: week 2 puts this on D1, where the row that comes back is whatever
  // the query matched. A `COLLATE NOCASE` column, a stray `LIKE`, a trimmed key
  // or a cache that returns a near neighbour all hand back a row that is not
  // the one asked for — and without this compare, presenting ANY well-formed
  // token would redeem somebody's real link, because the claim would then be
  // aimed at the handle on the row that came back.
  class WildcardReadStore implements ConnectLinkStore {
    inner = new MemoryConnectLinkStore();
    put(row: StoredLink) { return this.inner.put(row); }
    async read(_handle: string): Promise<StoredLink | null> {
      return this.inner.all()[0] ?? null; // a WHERE clause that matches everything
    }
    claim(handle: string, usedAt: number) { return this.inner.claim(handle, usedAt); }
    complete(handle: string, at: number) { return this.inner.complete(handle, at); }
    release(handle: string, at: number) { return this.inner.release(handle, at); }
  }
  const store = new WildcardReadStore();
  await freshLink(store);
  const neverMinted = "E".repeat(43);
  const r = await redeem(neverMinted, { signedInAs: OWNER, store, now: T0 + 1 });
  assert.deepEqual(r, { outcome: "expired" });
  assert.equal(store.inner.all()[0]!.used_at, null);
});

test("a row that vanishes under the claim is the unknown answer, not the used one", async () => {
  class VanishingStore implements ConnectLinkStore {
    inner = new MemoryConnectLinkStore();
    put(row: StoredLink) { return this.inner.put(row); }
    read(handle: string) { return this.inner.read(handle); }
    async claim(): Promise<ClaimOutcome> { return { won: false, row: null }; }
    complete(handle: string, at: number) { return this.inner.complete(handle, at); }
    release(handle: string, at: number) { return this.inner.release(handle, at); }
  }
  const store = new VanishingStore();
  const link = await freshLink(store);
  const r = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 });
  assert.deepEqual(r, { outcome: "expired" });
});

test("the store hands out copies, so a caller cannot edit the database", async () => {
  // The field a caller is most likely to touch on a row it was handed is
  // `used_at` — the one field this module refuses to decide anywhere but in the
  // compare-and-set.
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const handle = tokenHandle(link.token);
  const row = (await store.read(handle))!;
  row.used_at = T0 + 5;
  row.user_id = STRANGER;
  const again = (await store.read(handle))!;
  assert.equal(again.used_at, null);
  assert.equal(again.user_id, OWNER);
  store.all()[0]!.used_at = T0 + 5;
  assert.equal((await store.read(handle))!.used_at, null);
});

// ---------------------------------------------------------------------------
// NOT AN ORACLE
// ---------------------------------------------------------------------------

test("an unknown token is indistinguishable from an expired one", async () => {
  const store = new MemoryConnectLinkStore();
  const real = await freshLink(store);
  const expired = await redeem(real.token, { signedInAs: OWNER, store, now: real.expires_at });
  const unknown = await redeem("A".repeat(43), { signedInAs: OWNER, store, now: T0 + 1 });
  const wrongShape = await redeem("nope", { signedInAs: OWNER, store, now: T0 + 1 });
  const notAString = await redeem(null as never, { signedInAs: OWNER, store, now: T0 + 1 });
  const empty = await redeem("", { signedInAs: OWNER, store, now: T0 + 1 });
  for (const r of [unknown, wrongShape, notAString, empty]) {
    assert.deepEqual(r, expired);
  }
});

test("the page is not an oracle either", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const real = await freshLink(store);
  const deps = { signedInAs: OWNER, store, provider, words };
  const expired = await connectPageView(real.token, { ...deps, now: real.expires_at });
  const unknown = await connectPageView("B".repeat(43), { ...deps, now: T0 + 1 });
  const junk = await connectPageView("../../etc/passwd", { ...deps, now: T0 + 1 });
  assert.deepEqual(unknown, expired);
  assert.deepEqual(junk, expired);
  // And the catalog was never asked about a token that does not exist.
  assert.equal(provider.toolkitCalls.length, 0);
});

test("the callback is not an oracle either", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const real = await freshLink(store);
  const base = {
    signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 1,
    provider: stubProvider({ accounts: [acct("ca_BNgvxQtJ703C")] }),
  };
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_BNgvxQtJ703C" };
  // A `done` for a token that never went through `/go` is forged or out of
  // order; it answers exactly what an unknown token answers.
  const neverStarted = await connectPageDone(real.token, params, base);
  const unknown = await connectPageDone("C".repeat(43), params, base);
  assert.deepEqual(neverStarted, { state: "expired" });
  assert.deepEqual(unknown, neverStarted);
  assert.equal(s.recorded.length, 0);
});

// ---------------------------------------------------------------------------
// GET /c/{token}
// ---------------------------------------------------------------------------

test("the page is drawn from the catalog at run time, and consumes nothing", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store, { toolkit: SLUG_B, alias: "personal" });
  const view = await connectPageView(link.token, {
    signedInAs: OWNER, store, provider, words, now: T0 + 1,
  });
  assert.equal(view.state, "ok");
  if (view.state !== "ok") return;
  assert.equal(view.toolkit.slug, SLUG_B);
  assert.equal(view.toolkit.name, SLUG_B.toUpperCase());
  assert.equal(view.alias, "personal");
  assert.deepEqual(view.sentences, [
    `Anticipy can use your ${SLUG_B.toUpperCase()} to ${SLUG_B}.read.`,
    `Anticipy can use your ${SLUG_B.toUpperCase()} to ${SLUG_B}.write.`,
  ]);
  assert.equal(view.expires_at, link.expires_at);
  // Opening the page and thinking better of it must not spend the link, and
  // neither must a link prefetcher.
  assert.equal(store.all()[0]!.used_at, null);
  assert.equal((await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 2 })).outcome, "ok");
});

test("a signed-out page does not name the app", async () => {
  // Before a session exists we cannot tell the owner from whoever picked up
  // their phone. Naming the app here prints the answer above the lock screen.
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store, { toolkit: SLUG_B });
  const view = await connectPageView(link.token, {
    signedInAs: null, store, provider, words, now: T0 + 1,
  });
  assert.deepEqual(view, { state: "sign-in-required" });
  assert.ok(!JSON.stringify(view).includes(SLUG_B));
  assert.equal(provider.toolkitCalls.length, 0);
});

test("a stranger's page does not name the app either", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store, { toolkit: SLUG_B });
  const view = await connectPageView(link.token, {
    signedInAs: STRANGER, store, provider, words, now: T0 + 1,
  });
  assert.deepEqual(view, { state: "wrong-user" });
  assert.equal(provider.toolkitCalls.length, 0);
});

test("a spent link says so on the page", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 });
  const view = await connectPageView(link.token, {
    signedInAs: OWNER, store, provider, words, now: T0 + 2,
  });
  assert.deepEqual(view, { state: "already-used" });
});

test("a catalog outage on the page is a retry, not a state", async () => {
  // Nothing has been consumed at this point, so the honest answer is an error
  // the Worker can retry — swallowing it would teach the page to render an app
  // with no name and no permission sentences.
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider({ failToolkit: true });
  const link = await freshLink(store);
  await assert.rejects(
    () => connectPageView(link.token, { signedInAs: OWNER, store, provider, words, now: T0 + 1 }),
    /catalog unreachable/,
  );
  assert.equal(store.all()[0]!.used_at, null);
});

// ---------------------------------------------------------------------------
// POST /c/{token}/go
// ---------------------------------------------------------------------------

test("the vendor link is minted at the tap, with the owner ROW ID and our callback", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store, { toolkit: SLUG_B, alias: "personal" });
  const go = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 1 });
  assert.equal(go.state, "ok");
  assert.equal(go.state === "ok" && go.redirectUrl, `https://vendor.example/link/${SLUG_B}`);
  assert.equal(provider.authorizeCalls.length, 1);
  const call = provider.authorizeCalls[0]!;
  assert.equal(call.user, OWNER);
  assert.equal(call.toolkit, SLUG_B);
  assert.equal(call.alias, "personal");
  assert.equal(call.callbackUrl, callbackUrl(link.token));
  assert.ok(call.callbackUrl.startsWith("https://anticipy.ai/c/"));
  assert.ok(call.callbackUrl.endsWith("/done"));
});

test("the tap spends the link", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 1 });
  const again = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 2 });
  assert.deepEqual(again, { state: "already-used" });
  assert.equal(provider.authorizeCalls.length, 1);
});

test("two concurrent taps produce exactly one vendor link", async () => {
  // Reversed — authorize first, claim second — both taps would open a
  // connection request at the vendor and only one would ever be handed back.
  const store = new YieldingStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  const results = await Promise.all(
    Array.from({ length: 8 }, () =>
      connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 1 })),
  );
  assert.equal(results.filter((r) => r.state === "ok").length, 1);
  assert.equal(provider.authorizeCalls.length, 1);
});

test("a vendor outage burns the link rather than re-opening it", async () => {
  // The token is already spent when the vendor is called, and it stays spent.
  // Un-spending it on an error hands anyone who can make the vendor time out
  // unlimited attempts at a link that was supposed to work once.
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider({
    authorize: () => {
      throw new Error("composio 503 — connect.composio.dev unreachable");
    },
  });
  const link = await freshLink(store);
  const go = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 1 });
  assert.deepEqual(go, { state: "provider-unavailable" });
  // And the vendor's error text — which names them — never reaches the caller.
  assert.ok(!JSON.stringify(go).toLowerCase().includes("composio"));
  const again = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 2 });
  assert.deepEqual(again, { state: "already-used" });
});

test("a 200 with no URL in it is an outage, not a redirect", async () => {
  const store = new MemoryConnectLinkStore();
  for (const bad of [undefined, "", "   ", null, 42, {}]) {
    const provider = stubProvider({ authorize: () => ({ redirectUrl: bad }) });
    const link = await freshLink(store);
    const go = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 1 });
    assert.deepEqual(go, { state: "provider-unavailable" });
  }
});

test("a signed-out tap asks for a sign-in and does NOT spend the link", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  const go = await connectPageGo(link.token, { signedInAs: null, store, provider, now: T0 + 1 });
  assert.deepEqual(go, { state: "sign-in-required" });
  assert.equal(provider.authorizeCalls.length, 0);
  const owner = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 2 });
  assert.equal(owner.state, "ok");
});

test("a stranger's tap gets wrong-user, no vendor call, and the link survives", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  const go = await connectPageGo(link.token, { signedInAs: STRANGER, store, provider, now: T0 + 1 });
  assert.deepEqual(go, { state: "wrong-user" });
  assert.equal(provider.authorizeCalls.length, 0);
  assert.equal((await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 2 })).state, "ok");
});

test("an expired tap never reaches the vendor", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  const go = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: link.expires_at });
  assert.deepEqual(go, { state: "expired" });
  assert.equal(provider.authorizeCalls.length, 0);
});

// ---------------------------------------------------------------------------
// GET /c/{token}/done
// ---------------------------------------------------------------------------

async function tapped(store: ConnectLinkStore, over: { toolkit?: string; alias?: "work" | "personal" | null } = {}) {
  const provider = stubProvider();
  const link = await freshLink(store, over);
  const go = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 1 });
  assert.equal(go.state, "ok");
  return link;
}

test("a success records one connection, bound to the mint-time owner, with writes OFF", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store, { toolkit: SLUG_B, alias: "personal" });
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "  ca_sHENw6KtQ8Kx " },
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: stubProvider({
        accounts: [acct("ca_sHENw6KtQ8Kx", { toolkit: SLUG_B, alias: "personal" })],
      }),
    },
  );
  assert.equal(done.state, "connected");
  assert.equal(done.state === "connected" && done.recorded, true);
  assert.equal(s.recorded.length, 1);
  assert.deepEqual(s.recorded[0], {
    user_id: OWNER,
    toolkit: SLUG_B,
    connected_account_id: "ca_sHENw6KtQ8Kx",
    alias: "personal",
    status: "connected",
    // The Two Hands ladder cannot reach rung 3 without this being turned on
    // deliberately in Settings. A connection that arrived write-enabled would
    // let the first step that ever ran against it send mail, having asked the
    // owner for nothing but a connection.
    writes_enabled: false,
    last_used_at: null,
  });
});

test("THE CALLBACK CANNOT NAME ITS OWN OWNER", async () => {
  // The worst failure available in this product is binding a connection to the
  // wrong person. The owner comes from the stored row — bound at mint time to
  // an id that passed `ownerId()` — so a query string that carries a user_id
  // changes nothing.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const done = await connectPageDone(
    link.token,
    {
      status: CALLBACK_SUCCESS,
      connectedAccountId: "ca_BNgvxQtJ703C",
      user_id: STRANGER,
      owner: STRANGER,
    } as never,
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: stubProvider({ accounts: [acct("ca_BNgvxQtJ703C")] }),
    },
  );
  assert.equal(done.state, "connected");
  assert.equal(s.recorded[0]!.user_id, OWNER);
});

test("a refreshed callback shows the same page and records exactly once", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_BNgvxQtJ703C" };
  const opts = {
    signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
    provider: stubProvider({ accounts: [acct("ca_BNgvxQtJ703C")] }),
  };
  const first = await connectPageDone(link.token, params, opts);
  const second = await connectPageDone(link.token, params, { ...opts, now: T0 + 61_000 });
  const third = await connectPageDone(link.token, params, { ...opts, now: T0 + 62_000 });
  assert.equal(first.state === "connected" && first.recorded, true);
  assert.equal(second.state === "connected" && second.recorded, false);
  assert.equal(third.state === "connected" && third.recorded, false);
  assert.equal(s.recorded.length, 1);
});

test("concurrent callbacks record exactly once", async () => {
  const store = new YieldingStore();
  const s = sink();
  const link = await tapped(store);
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_BNgvxQtJ703C" };
  const results = await Promise.all(
    Array.from({ length: 10 }, () =>
      connectPageDone(link.token, params, {
        signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
        provider: stubProvider({ accounts: [acct("ca_BNgvxQtJ703C")] }),
      })),
  );
  assert.equal(results.filter((r) => r.state === "connected" && r.recorded).length, 1);
  assert.equal(s.recorded.length, 1);
});

test("a callback that is not a success writes nothing", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  for (const status of [null, "", "failed", "INITIATED", "Success", "success ", undefined]) {
    const done = await connectPageDone(
      link.token,
      { status: status as never, connectedAccountId: "ca_BNgvxQtJ703C" },
      {
        signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
        provider: stubProvider({ accounts: [acct("ca_BNgvxQtJ703C")] }),
      },
    );
    assert.deepEqual(done, { state: "not-connected" }, `status ${JSON.stringify(status)}`);
  }
  assert.equal(s.recorded.length, 0);
});

test("a success with no account id writes nothing", async () => {
  // A connection row with no account id is a row the router will route to and
  // the ledger will count, and the first the owner hears of it is a step that
  // fails.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  for (const id of [null, "", "   ", undefined, 5]) {
    const done = await connectPageDone(
      link.token,
      { status: CALLBACK_SUCCESS, connectedAccountId: id as never },
      {
        signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
        provider: stubProvider({ accounts: [acct("ca_BNgvxQtJ703C")] }),
      },
    );
    assert.deepEqual(done, { state: "not-connected" });
  }
  assert.equal(s.recorded.length, 0);
});

test("the vendor's spelling of success is configuration, not code", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const done = await connectPageDone(
    link.token,
    { status: "ACTIVE", connectedAccountId: "ca_x" },
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, successStatus: "ACTIVE",
      now: T0 + 60_000, provider: stubProvider({ accounts: [acct("ca_x")] }),
    },
  );
  assert.equal(done.state, "connected");
  assert.equal(s.recorded.length, 1);
});

test("A COMPLETED OAUTH ROUND TRIP SURVIVES THE TEN-MINUTE LINK TTL", async () => {
  // The link's TTL answers "how long may an untapped link sit in a text". The
  // vendor round trip is a different and much slower question: a password
  // manager, a 2FA push, an account chooser, and in the Notion case a login the
  // person did not have. Refusing the callback here would throw away a
  // connection that EXISTS at the vendor — and Composio has no success webhook,
  // so nothing would ever tell us about it again.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const wellPastTheTtl = T0 + 45 * 60 * 1000;
  assert.ok(wellPastTheTtl > link.expires_at);
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_BNgvxQtJ703C" },
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: wellPastTheTtl,
      provider: stubProvider({ accounts: [acct("ca_BNgvxQtJ703C")] }),
    },
  );
  assert.equal(done.state, "connected");
  assert.equal(s.recorded.length, 1);
});

test("the callback window closes at the instant it expires", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const usedAt = T0 + 1;
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_BNgvxQtJ703C" };
  const provider = stubProvider({ accounts: [acct("ca_BNgvxQtJ703C")] });
  const late = await connectPageDone(link.token, params, {
    signedInAs: OWNER, store, onConnected: s.onConnected, provider,
    now: usedAt + CALLBACK_WINDOW_MS,
  });
  assert.deepEqual(late, { state: "expired" });
  assert.equal(s.recorded.length, 0);
  const justInTime = await connectPageDone(link.token, params, {
    signedInAs: OWNER, store, onConnected: s.onConnected, provider,
    now: usedAt + CALLBACK_WINDOW_MS - 1,
  });
  assert.equal(justInTime.state, "connected");
});

test("a stranger cannot complete somebody else's connection", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store, { toolkit: SLUG_B });
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_theirs" },
    {
      signedInAs: STRANGER, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: stubProvider({ accounts: [acct("ca_theirs", { toolkit: SLUG_B })] }),
    },
  );
  assert.deepEqual(done, { state: "wrong-user" });
  assert.equal(s.recorded.length, 0);
  assert.ok(!JSON.stringify(done).includes(SLUG_B));
});

test("a signed-out callback records nothing", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_x" },
    {
      signedInAs: null, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: stubProvider({ accounts: [acct("ca_x")] }),
    },
  );
  assert.deepEqual(done, { state: "sign-in-required" });
  assert.equal(s.recorded.length, 0);
});

// ---------------------------------------------------------------------------
// LOGGING
// ---------------------------------------------------------------------------

test("no refusal anywhere carries the token, and the fingerprint is not the token", async () => {
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const s = sink();
  const link = await freshLink(store);
  const spent = await freshLink(store);
  await redeem(spent.token, { signedInAs: OWNER, store, now: T0 + 1 });

  const refusals: unknown[] = [
    await redeem(link.token, { signedInAs: STRANGER, store, now: T0 + 1 }),
    await redeem(link.token, { signedInAs: OWNER, store, now: link.expires_at }),
    await redeem(spent.token, { signedInAs: OWNER, store, now: T0 + 2 }),
    await connectPageView(link.token, { signedInAs: null, store, provider, words, now: T0 + 1 }),
    await connectPageView(spent.token, { signedInAs: OWNER, store, provider, words, now: T0 + 2 }),
    await connectPageGo(link.token, { signedInAs: STRANGER, store, provider, now: T0 + 1 }),
    await connectPageDone(link.token, { status: "no", connectedAccountId: null }, {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 2, provider,
    }),
  ];
  for (const r of refusals) {
    const text = JSON.stringify(r);
    assert.ok(!text.includes(link.token), `a refusal carried the token: ${text}`);
    assert.ok(!text.includes(spent.token), `a refusal carried the token: ${text}`);
  }

  const fp = tokenFingerprint(link.token);
  assert.ok(!fp.includes(link.token));
  assert.equal(fp.length, "link:".length + 12);
  assert.equal(fp, tokenFingerprint(link.token));
  assert.notEqual(fp, tokenFingerprint(spent.token));
  assert.equal(tokenFingerprint(""), "link:none");
});

test("a mint refusal names the value the caller passed, never a token", async () => {
  const store = new MemoryConnectLinkStore();
  await assert.rejects(
    () => mint("jose@anticipy.ai", SLUG_A, { store }),
    (e: Error) => e.message.includes("jose@anticipy.ai") && e.message.includes("owner ROW id"),
  );
});

test("the shared refusal objects cannot be poisoned by a caller", async () => {
  // All three, not one: they are module-level constants handed to every caller,
  // and a route that patched a field on the answer it got back would be
  // rewriting the answer every LATER caller receives. ESM is always strict
  // mode, so frozen means the attempt throws rather than silently taking.
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const spent = await freshLink(store);
  await redeem(spent.token, { signedInAs: OWNER, store, now: T0 + 1 });

  const refusals = [
    await redeem(link.token, { signedInAs: STRANGER, store, now: T0 + 1 }),
    await redeem(link.token, { signedInAs: OWNER, store, now: link.expires_at }),
    await redeem(spent.token, { signedInAs: OWNER, store, now: T0 + 2 }),
  ];
  assert.deepEqual(refusals.map((r) => r.outcome), ["wrong-user", "expired", "already-used"]);
  for (const r of refusals) {
    assert.ok(Object.isFrozen(r), `${r.outcome} is shared and patchable`);
    assert.throws(() => {
      (r as { outcome: string }).outcome = "ok";
    }, TypeError);
  }
});

// ---------------------------------------------------------------------------
// ROUTES
// ---------------------------------------------------------------------------

test("the three page routes parse, and nothing else does", async () => {
  const link = await freshLink(new MemoryConnectLinkStore());
  const t = link.token;
  assert.deepEqual(parseConnectPath(`/c/${t}`), { leg: "view", token: t });
  assert.deepEqual(parseConnectPath(`/c/${t}/go`), { leg: "go", token: t });
  assert.deepEqual(parseConnectPath(`/c/${t}/done`), { leg: "done", token: t });
  assert.deepEqual(parseConnectPath(new URL(connectUrl(t)).pathname), { leg: "view", token: t });
  assert.deepEqual(parseConnectPath(new URL(callbackUrl(t)).pathname), { leg: "done", token: t });
  for (const bad of [
    `/c/${t}/`,
    `/c/${t}/GO`,
    `/c/${t}/go/extra`,
    `/c/${t}/../done`,
    `/c/${t.slice(0, 42)}`,
    `/c/${t}x`,
    "/c/",
    "/c",
    `/x/${t}`,
    "",
    null,
    7,
  ]) {
    assert.equal(parseConnectPath(bad as never), null, `parsed ${String(bad)}`);
  }
});

// ---------------------------------------------------------------------------
// LAW 1 — NO APP IS HARDCODED
// ---------------------------------------------------------------------------

test("a toolkit nobody has ever heard of runs the whole flow, with zero code", async () => {
  // The spec's rule is that names, logos, permission words and the ask all come
  // from the catalog at run time. The proof is behavioural rather than a grep:
  // two invented slugs, the same flow, identical results modulo the slug. If
  // anything in the module ever special-cased an app, one of these two would
  // start behaving differently from the other.
  const run = async (slug: string) => {
    const store = new MemoryConnectLinkStore();
    const provider = stubProvider();
    const s = sink();
    const link = await mint(OWNER, slug, { store, alias: "work", now: T0 });
    const view = await connectPageView(link.token, {
      signedInAs: OWNER, store, provider, words, now: T0 + 1,
    });
    const go = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 2 });
    const done = await connectPageDone(
      link.token,
      { status: CALLBACK_SUCCESS, connectedAccountId: `ca_${slug}` },
      {
        signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 3,
        provider: stubProvider({ accounts: [acct(`ca_${slug}`, { toolkit: slug })] }),
      },
    );
    return { view, go, done, recorded: s.recorded, authorize: provider.authorizeCalls };
  };

  const a = await run(SLUG_A);
  const b = await run(SLUG_B);
  const shape = (o: unknown, slug: string) =>
    JSON.parse(JSON.stringify(o).split(slug).join("<SLUG>").split(slug.toUpperCase()).join("<NAME>"));

  assert.equal(a.view.state, "ok");
  assert.equal(a.go.state, "ok");
  assert.equal(a.done.state, "connected");
  assert.equal(a.recorded.length, 1);
  assert.equal(a.authorize.length, 1);
  assert.deepEqual(shape(a.view, SLUG_A), shape(b.view, SLUG_B));
  assert.deepEqual(shape(a.go, SLUG_A), shape(b.go, SLUG_B));
  assert.deepEqual(shape(a.done, SLUG_A), shape(b.done, SLUG_B));
  assert.deepEqual(shape(a.recorded, SLUG_A), shape(b.recorded, SLUG_B));
});

// ---------------------------------------------------------------------------
// FINDING 6 — THE ROUTES ARE NOT A TOKEN ORACLE
// ---------------------------------------------------------------------------

test("AN UNAUTHENTICATED CALLER CANNOT TELL A LIVE TOKEN FROM A MADE-UP ONE", async () => {
  // The file's own privacy model says a link alone must be worth nothing to
  // whoever reads the text over a shoulder. It was worth one thing: a signed-out
  // request could sort strings into "a real Anticipy token" and "not one",
  // because a live token answered `sign-in-required` while an invented one
  // answered `expired`. That is an oracle, and it answers before anybody has
  // proved who they are — so it is available to exactly the person the SMS
  // threat model is about. Every shape below must give one answer.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const provider = stubProvider({ accounts: [acct("ca_x")] });

  const live = await freshLink(store);
  const stale = await freshLink(store);
  const spent = await freshLink(store);
  await redeem(spent.token, { signedInAs: OWNER, store, now: T0 + 1 });
  const claimed = await tapped(store); // through /go, waiting on the vendor
  const invented = "F".repeat(43);
  const nonsense = "../../etc/passwd";

  const late = stale.expires_at + 5_000;
  const probes: Array<[string, number]> = [
    [live.token, T0 + 2],
    [stale.token, late],
    [spent.token, T0 + 2],
    [claimed.token, T0 + 2],
    [invented, T0 + 2],
    [nonsense, T0 + 2],
  ];

  const redeems: unknown[] = [];
  for (const [tok, at] of probes) {
    redeems.push(await redeem(tok, { signedInAs: null, store, now: at }));
  }
  for (const r of redeems) {
    assert.deepEqual(r, redeems[0], "redeem told an anonymous caller which token was real");
  }

  const views: unknown[] = [];
  for (const [tok, at] of probes) {
    views.push(await connectPageView(tok, { signedInAs: null, store, provider, words, now: at }));
  }
  for (const v of views) {
    assert.deepEqual(v, views[0], "the connect page told an anonymous caller which token was real");
  }
  assert.equal(provider.toolkitCalls.length, 0, "and the catalog was never asked");

  const gos: unknown[] = [];
  for (const [tok, at] of probes) {
    gos.push(await connectPageGo(tok, { signedInAs: null, store, provider, now: at }));
  }
  for (const g of gos) {
    assert.deepEqual(g, gos[0], "the tap told an anonymous caller which token was real");
  }

  const dones: unknown[] = [];
  for (const [tok, at] of probes) {
    dones.push(await connectPageDone(
      tok,
      { status: CALLBACK_SUCCESS, connectedAccountId: "ca_x" },
      { signedInAs: null, store, onConnected: s.onConnected, provider, now: at },
    ));
  }
  for (const d of dones) {
    assert.deepEqual(d, dones[0], "the callback told an anonymous caller which token was real");
  }

  // And no anonymous probe spent, completed or recorded anything.
  assert.equal(s.recorded.length, 0);
  assert.equal(provider.authorizeCalls.length, 0);
  assert.equal(store.all().filter((r) => r.completed_at !== null).length, 0);
  assert.equal(
    store.all().filter((r) => r.used_at !== null).length,
    2,
    "only the owner's own redeem and the owner's own tap",
  );
});

test("the signed-in owner is still told the four answers apart — the control", async () => {
  // A guard that refuses everything is an outage. Collapsing the ANONYMOUS case
  // must not collapse the case the page exists for: a signed-in person has to
  // be told "this worked", "this is too old", "you already used this" and "this
  // link is not yours", or there is nothing to put on the screen.
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const ok = await freshLink(store);
  const old = await freshLink(store);
  const used = await freshLink(store);
  await redeem(used.token, { signedInAs: OWNER, store, now: T0 + 1 });
  const theirs = await freshLink(store);

  assert.equal((await redeem(ok.token, { signedInAs: OWNER, store, now: T0 + 2 })).outcome, "ok");
  assert.equal((await redeem(old.token, { signedInAs: OWNER, store, now: old.expires_at })).outcome, "expired");
  assert.equal((await redeem(used.token, { signedInAs: OWNER, store, now: T0 + 2 })).outcome, "already-used");
  assert.equal((await redeem(theirs.token, { signedInAs: STRANGER, store, now: T0 + 2 })).outcome, "wrong-user");

  const view = (tok: string, who: string | null, now: number) =>
    connectPageView(tok, { signedInAs: who, store, provider, words, now });
  const fresh = await freshLink(store);
  assert.equal((await view(fresh.token, OWNER, T0 + 2)).state, "ok");
  assert.equal((await view(old.token, OWNER, old.expires_at)).state, "expired");
  assert.equal((await view(used.token, OWNER, T0 + 2)).state, "already-used");
  assert.equal((await view(fresh.token, STRANGER, T0 + 2)).state, "wrong-user");
  assert.equal((await view(fresh.token, null, T0 + 2)).state, "sign-in-required");
});

test("an anonymous request never touches the store, so it cannot be timed either", async () => {
  // The states matching is half of it. If a signed-out request still ran the
  // lookup, a real handle and an invented one would differ by a round trip —
  // the same oracle, read off a stopwatch instead of a status code.
  const store = new YieldingStore();
  const provider = stubProvider({ accounts: [acct("ca_x")] });
  const s = sink();
  const link = await freshLink(store);
  const before = store.reads;

  await redeem(link.token, { signedInAs: null, store, now: T0 + 1 });
  await connectPageView(link.token, { signedInAs: null, store, provider, words, now: T0 + 1 });
  await connectPageGo(link.token, { signedInAs: null, store, provider, now: T0 + 1 });
  await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_x" },
    { signedInAs: null, store, onConnected: s.onConnected, provider, now: T0 + 1 },
  );

  assert.equal(store.reads, before, "a signed-out caller must not be able to time a row lookup");
  assert.equal(store.claims, 0);
  assert.equal(store.completes, 0);
});

// ---------------------------------------------------------------------------
// FINDING 3 — REDEEM VERIFIES THE ROW THE COMPARE-AND-SET HANDED BACK
// ---------------------------------------------------------------------------

/**
 * A store whose compare-and-set WINS but answers with a neighbouring row. These
 * are the same D1 shapes `locate` already defends the READ against — a COLLATE
 * NOCASE column, a stray LIKE, a trimmed key, a cache — aimed at the write,
 * which is the half nobody was checking.
 */
class WildcardClaimStore implements ConnectLinkStore {
  inner = new MemoryConnectLinkStore();
  corrupt = true;
  put(row: StoredLink) { return this.inner.put(row); }
  read(handle: string) { return this.inner.read(handle); }
  async claim(handle: string, usedAt: number): Promise<ClaimOutcome> {
    const out = await this.inner.claim(handle, usedAt);
    if (!out.won || !out.row || !this.corrupt) return out;
    return {
      won: true,
      row: { ...out.row, token_handle: "0".repeat(64), user_id: STRANGER, toolkit: SLUG_B },
    };
  }
  complete(handle: string, at: number) { return this.inner.complete(handle, at); }
  release(handle: string, at: number) { return this.inner.release(handle, at); }
}

test("REDEEM REFUSES A ROW THAT IS NOT THE ROW IT ASKED FOR", async () => {
  // `locate` runs exactly this check thirty lines earlier and says why. redeem
  // was the one path that took the store's word for it — and it is the path
  // that decides which owner gets authorized at the vendor.
  const store = new WildcardClaimStore();
  const link = await freshLink(store);
  const r = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 });
  assert.deepEqual(r, { outcome: "expired" });
  // The write already happened, so the link stays spent. That is the correct
  // direction to fail: a store answering wrongly is not a reason to hand out a
  // second live link.
  assert.equal(store.inner.all()[0]!.used_at, T0 + 1);
});

test("and the vendor is never asked to authorize the neighbour's owner", async () => {
  // The concrete failure, end to end: without the check, `connectPageGo` takes
  // the returned link at face value and opens an OAuth flow for STRANGER, on a
  // toolkit nobody asked for, in the owner's browser.
  const store = new WildcardClaimStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  const go = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 1 });
  assert.notEqual(go.state, "ok");
  assert.deepEqual(provider.authorizeCalls, []);
});

test("the same store, answering honestly, still redeems and still authorizes — the control", async () => {
  const store = new WildcardClaimStore();
  store.corrupt = false;
  const provider = stubProvider();
  const link = await freshLink(store, { toolkit: SLUG_B, alias: "personal" });
  const go = await connectPageGo(link.token, { signedInAs: OWNER, store, provider, now: T0 + 1 });
  assert.equal(go.state, "ok");
  assert.equal(provider.authorizeCalls.length, 1);
  assert.equal(provider.authorizeCalls[0]!.user, OWNER);
  assert.equal(provider.authorizeCalls[0]!.toolkit, SLUG_B);

  const other = new WildcardClaimStore();
  other.corrupt = false;
  const plain = await freshLink(other);
  const r = await redeem(plain.token, { signedInAs: OWNER, store: other, now: T0 + 1 });
  assert.equal(r.outcome, "ok");
  assert.equal(r.outcome === "ok" && r.link.user_id, OWNER);
  assert.equal(r.outcome === "ok" && r.link.used_at, T0 + 1);
});

// ---------------------------------------------------------------------------
// FINDING 2 — THE ACCOUNT ON THE CALLBACK MUST BE THIS OWNER'S
// ---------------------------------------------------------------------------

test("A CALLBACK CANNOT BIND AN ACCOUNT THE VENDOR DOES NOT HOLD FOR THIS OWNER", async () => {
  // `user_id` says who WE think this is. `connected_account_id` is the vendor's
  // handle for whose credential actually answers, and it arrives on a query
  // string a browser can edit. Written verbatim it produces a row saying "this
  // owner's Kettlebright is ca_somebody_elses" — and the first step that runs
  // against it reaches into another person's account holding our key. The old
  // docstring called that impossible; it was not.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_somebody_elses" },
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: stubProvider({ accounts: [acct("ca_mine")] }),
    },
  );
  assert.deepEqual(done, { state: "not-connected" });
  assert.equal(s.recorded.length, 0);
  assert.ok(!JSON.stringify(done).includes("ca_somebody_elses"));
});

test("an account the vendor holds for a DIFFERENT owner is refused, not obeyed", async () => {
  // The provider seam gets the same treatment as the store seam: the call is
  // scoped by owner, so a row that comes back bound to somebody else means the
  // scoping did not hold, and it is not evidence about our owner.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_theirs" },
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: stubProvider({ accounts: [acct("ca_theirs", { user: STRANGER })] }),
    },
  );
  assert.deepEqual(done, { state: "not-connected" });
  assert.equal(s.recorded.length, 0);
});

test("an account the vendor holds on a DIFFERENT toolkit is refused", async () => {
  // The link is bound to one toolkit at mint time. Filing a calendar credential
  // under the mail row sends every future mail step at the wrong account.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store, { toolkit: SLUG_A });
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_x" },
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: stubProvider({ accounts: [acct("ca_x", { toolkit: SLUG_B })] }),
    },
  );
  assert.deepEqual(done, { state: "not-connected" });
  assert.equal(s.recorded.length, 0);
});

test("a vendor that cannot be asked is a retry, never a connection", async () => {
  // Recording is the privilege here, so it needs positive evidence rather than
  // the absence of an objection. But a vendor outage is not a failed connect —
  // the account may well exist — so the answer must be a state the person can
  // retry, and nothing may be consumed by it.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_real" };
  const down = await connectPageDone(link.token, params, {
    signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
    provider: stubProvider({ accounts: [acct("ca_real")], failConnections: true }),
  });
  assert.deepEqual(down, { state: "could-not-confirm" });
  assert.equal(s.recorded.length, 0);
  assert.equal(store.all()[0]!.completed_at, null, "an outage must not burn the exactly-once bit");
  // The vendor's error text names them; the person is owed one sentence.
  assert.ok(!JSON.stringify(down).toLowerCase().includes("composio"));

  const back = await connectPageDone(link.token, params, {
    signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 61_000,
    provider: stubProvider({ accounts: [acct("ca_real")] }),
  });
  assert.equal(back.state === "connected" && back.recorded, true);
  assert.equal(s.recorded.length, 1);
});

test("a confirmed account is recorded, and the vendor was asked about the ROW's owner — the control", async () => {
  // Without this the whole check could be `return not-connected` and every test
  // above would still pass, while nobody could ever connect anything.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store, { toolkit: SLUG_A, alias: "personal" });
  const provider = stubProvider({
    // The vendor's own spelling of the slug, which is not guaranteed to match
    // our normalized one. Case and padding are plumbing, not two apps.
    accounts: [acct("ca_real", { toolkit: ` ${SLUG_A.toUpperCase()} ` })],
  });
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_real" },
    { signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000, provider },
  );
  assert.equal(done.state, "connected");
  assert.equal(done.state === "connected" && done.recorded, true);
  assert.equal(s.recorded.length, 1);
  assert.equal(s.recorded[0]!.connected_account_id, "ca_real");
  assert.equal(s.recorded[0]!.user_id, OWNER);
  assert.equal(s.recorded[0]!.alias, "personal", "the alias is ours, from the mint, not the vendor's");
  assert.equal(s.recorded[0]!.writes_enabled, false);
  // Asked about the STORED row's owner — never the session, never the query.
  assert.deepEqual(provider.connectionsCalls, [OWNER]);
});

// ---------------------------------------------------------------------------
// FINDING 5 — A FAILED WRITE IS NOT A CONNECTION
// ---------------------------------------------------------------------------

test("A FAILED WRITE DOES NOT LEAVE THE PAGE SAYING CONNECTED FOREVER", async () => {
  // The exactly-once bit used to be burned BEFORE the write. One failing
  // `onConnected` — a D1 blip, a constraint, a cold container — and the token
  // was completed with no row anywhere: every refresh answered "connected,
  // recorded: false", the person was told they were done, and the connection
  // existed at the vendor with nothing on our side pointing at it. Composio
  // publishes no success webhook, so nothing would ever mention it again. That
  // is permanent, silent data loss, and it is one `throw` away at all times.
  const store = new MemoryConnectLinkStore();
  const recorded: Connection[] = [];
  let failures = 1;
  const onConnected = async (c: Connection) => {
    if (failures-- > 0) throw new Error("D1_ERROR: no such table: connections");
    recorded.push(c);
  };
  const link = await tapped(store);
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_real" };
  const opts = {
    signedInAs: OWNER, store, onConnected, now: T0 + 60_000,
    provider: stubProvider({ accounts: [acct("ca_real")] }),
  };

  const first = await connectPageDone(link.token, params, opts);
  assert.deepEqual(first, { state: "not-recorded" }, "a write that failed is not a connection");
  assert.equal(recorded.length, 0);

  // THE RECOVERY. The lease is released, so the refresh the person is about to
  // make is the one that writes the row.
  const second = await connectPageDone(link.token, params, { ...opts, now: T0 + 61_000 });
  assert.equal(second.state === "connected" && second.recorded, true);
  assert.equal(recorded.length, 1);

  // And it is exactly-once again the moment it succeeds.
  const third = await connectPageDone(link.token, params, { ...opts, now: T0 + 62_000 });
  assert.equal(third.state === "connected" && third.recorded, false);
  assert.equal(recorded.length, 1);
});

test("a store that cannot release the lease still refuses to say connected", async () => {
  // `release` is on the interface, but a week-2 D1 store that ships without it
  // must degrade to an honest refusal — not to a TypeError thrown from inside
  // the error path, and above all not to the old answer, "connected".
  class NoReleaseStore implements ConnectLinkStore {
    inner = new MemoryConnectLinkStore();
    put(row: StoredLink) { return this.inner.put(row); }
    read(handle: string) { return this.inner.read(handle); }
    claim(handle: string, usedAt: number) { return this.inner.claim(handle, usedAt); }
    complete(handle: string, at: number) { return this.inner.complete(handle, at); }
  }
  const store = new NoReleaseStore() as unknown as ConnectLinkStore;
  const link = await tapped(store);
  const done = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_real" },
    {
      signedInAs: OWNER,
      store,
      onConnected: async () => { throw new Error("D1_ERROR: write failed"); },
      now: T0 + 60_000,
      provider: stubProvider({ accounts: [acct("ca_real")] }),
    },
  );
  assert.deepEqual(done, { state: "not-recorded" });
});

test("release clears only the completion it took", async () => {
  // Conditional, like every other write in this module. An unconditional
  // release would let a stale caller re-open the exactly-once window under a
  // connection somebody else has already recorded.
  const store = new MemoryConnectLinkStore();
  const link = await freshLink(store);
  const handle = tokenHandle(link.token);
  await store.claim(handle, T0 + 1);
  assert.equal((await store.complete(handle, T0 + 2)).won, true);

  const notMine = await store.release(handle, T0 + 999);
  assert.equal(notMine.won, false, "a caller that does not hold the lease cannot release it");
  assert.equal((await store.read(handle))!.completed_at, T0 + 2);

  const mine = await store.release(handle, T0 + 2);
  assert.equal(mine.won, true);
  assert.equal((await store.read(handle))!.completed_at, null);
});

// ---------------------------------------------------------------------------
// FINDING 7 — NOBODY CAN CONSENT TO AN EMPTY LIST
// ---------------------------------------------------------------------------

test("A CONNECT PAGE WITH NO PERMISSION SENTENCES REFUSES RATHER THAN RENDERING", async () => {
  // The page's whole job is to say what Anticipy will be able to do before the
  // person agrees to it. Rendering `state: "ok"` with an empty list asks them to
  // consent to nothing, and it looks exactly like a page that finished loading.
  // This module cannot audit the words, but it can refuse to publish silence.
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  const empties: unknown[] = [
    [], [""], ["   "], ["\n\t "], ["a real sentence.", ""], [null], [7],
    null, undefined, "three sentences", {},
  ];
  for (const bad of empties) {
    const brokenWords = { async sentences(): Promise<string[]> { return bad as never; } };
    await assert.rejects(
      () => connectPageView(link.token, {
        signedInAs: OWNER, store, provider, words: brokenWords, now: T0 + 1,
      }),
      /permission sentences/,
      `rendered a consent page from ${JSON.stringify(bad)}`,
    );
  }
  assert.equal(store.all()[0]!.used_at, null, "and the refusal consumed nothing");
});

test("one real sentence is enough to render — the control", async () => {
  // How MANY sentences there are is the words module's question, not this
  // one's. A count rule here would be an outage the first time a toolkit with
  // one scope reaches the catalog.
  const store = new MemoryConnectLinkStore();
  const provider = stubProvider();
  const link = await freshLink(store);
  const oneLine = {
    async sentences(): Promise<string[]> { return ["Anticipy can read your calendar."]; },
  };
  const view = await connectPageView(link.token, {
    signedInAs: OWNER, store, provider, words: oneLine, now: T0 + 1,
  });
  assert.equal(view.state, "ok");
  assert.deepEqual(view.state === "ok" && view.sentences, ["Anticipy can read your calendar."]);
});

test("everything the caller is handed comes from the row LOCATE verified", async () => {
  // The other half of the same check. Here the write answers with the right key
  // and a mangled payload — a join that picked up a neighbouring alias, a column
  // served from a cache. `alias` is which of two Google accounts this becomes,
  // and `expires_at` is what the page prints; both must come from the row that
  // was checked against the handle, not from the write's echo of it.
  class MangledEchoStore implements ConnectLinkStore {
    inner = new MemoryConnectLinkStore();
    put(row: StoredLink) { return this.inner.put(row); }
    read(handle: string) { return this.inner.read(handle); }
    async claim(handle: string, usedAt: number): Promise<ClaimOutcome> {
      const out = await this.inner.claim(handle, usedAt);
      if (!out.won || !out.row) return out;
      return { won: true, row: { ...out.row, alias: "personal", expires_at: 1 } };
    }
    complete(handle: string, at: number) { return this.inner.complete(handle, at); }
    release(handle: string, at: number) { return this.inner.release(handle, at); }
  }
  const store = new MangledEchoStore();
  const link = await freshLink(store, { alias: "work" });
  const r = await redeem(link.token, { signedInAs: OWNER, store, now: T0 + 1 });
  assert.equal(r.outcome, "ok");
  assert.equal(r.outcome === "ok" && r.link.alias, "work");
  assert.equal(r.outcome === "ok" && r.link.expires_at, link.expires_at);
  assert.equal(r.outcome === "ok" && r.link.used_at, T0 + 1, "only the used bit comes from the write");
});

// ===========================================================================
// FINDING D — THE VENDOR IS ASKED BEFORE THE LEASE IS TAKEN
// ===========================================================================
// Finding 5's fix put the exactly-once lease AFTER the write it authorises, so
// a failed `onConnected` hands the lease back and the person's refresh writes
// the row. That fix has a second half nobody was holding: the lease is also
// taken after the OWNERSHIP check, and it has to be.
//
// Move `complete()` above the `vendorVouchesFor` refusal and the whole suite
// stayed green while this happened: a forged or stale callback — an account id
// the vendor does not hold for this owner — burns the exactly-once bit on its
// way to being refused. The real callback that arrives a second later then
// loses the lease, answers `connected, recorded: false`, and NOTHING IS EVER
// WRITTEN. Composio publishes no success webhook, so nothing mentions that
// connection again. It is the permanent silent data loss of finding 5, reached
// through the door finding 2 built.
//
// Anyone holding the callback URL can send that first request, which makes it
// cheap to do on purpose as well as easy to do by accident.

/** A store that counts the two writes that matter, and delegates them
 *  untouched. `completes` is the lease being TAKEN — the number this section
 *  is about. */
class CountingStore implements ConnectLinkStore {
  inner = new MemoryConnectLinkStore();
  completes = 0;
  releases = 0;
  put(row: StoredLink) { return this.inner.put(row); }
  read(handle: string) { return this.inner.read(handle); }
  claim(handle: string, usedAt: number) { return this.inner.claim(handle, usedAt); }
  complete(handle: string, at: number): Promise<ClaimOutcome> {
    this.completes++;
    return this.inner.complete(handle, at);
  }
  release(handle: string, at: number): Promise<ClaimOutcome> {
    this.releases++;
    return this.inner.release(handle, at);
  }
  all() { return this.inner.all(); }
}

test("A REFUSED CALLBACK DOES NOT BURN THE EXACTLY-ONCE LEASE", async () => {
  const store = new CountingStore();
  const s = sink();
  const link = await tapped(store);
  const provider = stubProvider({ accounts: [acct("ca_mine")] });
  const opts = { signedInAs: OWNER, store, onConnected: s.onConnected, provider };

  // An account id the vendor does not hold for this owner. Refused — and the
  // refusal must cost the owner nothing.
  const forged = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_somebody_elses" },
    { ...opts, now: T0 + 60_000 },
  );
  assert.deepEqual(forged, { state: "not-connected" });
  assert.equal(
    store.completes,
    0,
    "the lease was taken on the way to refusing: the real callback can now never write",
  );
  assert.equal(store.all()[0]!.completed_at, null);

  // THE CONSEQUENCE, spelled out rather than inferred from the counter: the
  // genuine callback still writes the connection.
  const real = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_mine" },
    { ...opts, now: T0 + 61_000 },
  );
  assert.equal(real.state === "connected" && real.recorded, true, JSON.stringify(real));
  assert.equal(s.recorded.length, 1);
  assert.equal(s.recorded[0]!.connected_account_id, "ca_mine");
});

test("nor does a vendor outage, nor a callback that is not a success", async () => {
  // The other two refusals on the same route, for the same reason: every one of
  // them is a state the person retries, and a retry that cannot write is a
  // dead end wearing a friendly sentence.
  const store = new CountingStore();
  const s = sink();
  const link = await tapped(store);
  const opts = { signedInAs: OWNER, store, onConnected: s.onConnected };

  const down = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_mine" },
    { ...opts, now: T0 + 60_000, provider: stubProvider({ failConnections: true }) },
  );
  assert.deepEqual(down, { state: "could-not-confirm" });

  const notSuccess = await connectPageDone(
    link.token,
    { status: "denied", connectedAccountId: "ca_mine" },
    { ...opts, now: T0 + 60_500, provider: stubProvider({ accounts: [acct("ca_mine")] }) },
  );
  assert.deepEqual(notSuccess, { state: "not-connected" });

  assert.equal(store.completes, 0, "a refusal took the lease");

  const real = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: "ca_mine" },
    { ...opts, now: T0 + 61_000, provider: stubProvider({ accounts: [acct("ca_mine")] }) },
  );
  assert.equal(real.state === "connected" && real.recorded, true);
  assert.equal(s.recorded.length, 1);
});

test("the lease IS taken once the vendor vouches — the control", async () => {
  // Without this the ordering pin above is satisfied by deleting `complete`
  // altogether, which would make every refresh of the callback write the
  // connection again. Exactly-once is the property; ordering is how it is kept.
  const store = new CountingStore();
  const s = sink();
  const link = await tapped(store);
  const opts = {
    signedInAs: OWNER, store, onConnected: s.onConnected,
    provider: stubProvider({ accounts: [acct("ca_mine")] }),
  };
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_mine" };

  const first = await connectPageDone(link.token, params, { ...opts, now: T0 + 60_000 });
  assert.equal(first.state === "connected" && first.recorded, true);
  assert.equal(store.completes, 1);
  assert.equal(store.all()[0]!.completed_at, T0 + 60_000);

  const refresh = await connectPageDone(link.token, params, { ...opts, now: T0 + 60_100 });
  assert.equal(refresh.state === "connected" && refresh.recorded, false);
  assert.equal(store.completes, 2, "the second caller still ASKS; it simply loses");
  assert.equal(s.recorded.length, 1, "and the row is written once");
});

// ===========================================================================
// FINDING E — EVERY FAIL-CLOSED LEG IN `vendorVouchesFor`, DRIVEN
// ===========================================================================
// The ownership check answers false on anything it cannot read: a non-array, an
// entry that is not an object, and three fields that must each be a string
// before they are compared. All five were DECORATIVE under test — each could be
// flipped from `return false` to `return true` with the suite green, because
// every existing case fed it a well-formed list and disagreed only on the
// VALUES.
//
// That matters because the list is a vendor's answer over a network. A shape we
// did not expect is not a yes; it is the absence of an answer, and binding a
// stranger's mailbox on the absence of an answer is the highest-severity defect
// this file has. Each leg below now has a case that only it refuses, and each
// case has a well-formed twin that must still connect — so a leg cannot be
// "fixed" by refusing everything.

/** A vendor that answers with exactly this, whatever it is. `stubProvider`
 *  cannot express a malformed answer: it maps over an array of `Connection`,
 *  which is the shape under test. */
function vendorSaying(listed: unknown) {
  const calls: string[] = [];
  return {
    calls,
    async connections(user: string): Promise<Connection[]> {
      calls.push(user);
      return listed as Connection[];
    },
  };
}

/** One `done` against a vendor answering `listed`. Returns the page state and
 *  what was written, so every leg below reads the same two facts. */
async function doneAgainst(listed: unknown, accountId = "ca_real") {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const state = await connectPageDone(
    link.token,
    { status: CALLBACK_SUCCESS, connectedAccountId: accountId },
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: vendorSaying(listed),
    },
  );
  return { state, recorded: s.recorded, completedAt: store.all()[0]!.completed_at };
}

/** The entry that DOES vouch, as a plain object rather than through `acct`, so
 *  each leg below can spoil exactly one field of it and nothing else. */
const wellFormed = () => ({
  connected_account_id: "ca_real",
  user_id: OWNER as string,
  toolkit: SLUG_A,
  status: "connected",
});

test("E1: an answer that is not a list vouches for nothing", async () => {
  for (const listed of [null, undefined, "ca_real", 7, true, {}, { 0: wellFormed(), length: 1 }]) {
    const got = await doneAgainst(listed);
    assert.deepEqual(got.state, { state: "not-connected" }, JSON.stringify(listed));
    assert.equal(got.recorded.length, 0, JSON.stringify(listed));
    assert.equal(got.completedAt, null, JSON.stringify(listed));
  }
});

test("E2: an entry that is not an object vouches for nothing", async () => {
  // A JSON array of bare id strings is a shape a vendor could plausibly return,
  // and reading one as a match would bind on a value nothing was compared to.
  for (const entry of [null, undefined, "ca_real", 7, true]) {
    const got = await doneAgainst([entry]);
    assert.deepEqual(got.state, { state: "not-connected" }, JSON.stringify(entry));
    assert.equal(got.recorded.length, 0);
  }
});

test("E3: an entry whose account id is not a string vouches for nothing", async () => {
  for (const id of [undefined, null, 7, {}, ["ca_real"]]) {
    const got = await doneAgainst([{ ...wellFormed(), connected_account_id: id }]);
    assert.deepEqual(got.state, { state: "not-connected" }, JSON.stringify(id));
    assert.equal(got.recorded.length, 0);
  }
});

test("E4: an entry whose owner is not a string vouches for nothing", async () => {
  // The list was asked for BY owner, so an entry with no readable owner is an
  // unscoped answer, and an unscoped answer is not evidence about ours.
  for (const user of [undefined, null, 7, {}, [OWNER]]) {
    const got = await doneAgainst([{ ...wellFormed(), user_id: user }]);
    assert.deepEqual(got.state, { state: "not-connected" }, JSON.stringify(user));
    assert.equal(got.recorded.length, 0);
  }
});

test("E5: an entry whose toolkit is not a string vouches for nothing", async () => {
  // Without this leg an entry with no readable toolkit would file whatever
  // credential answered under the app the link was minted for — a calendar
  // token in the mail row, and every future mail step aimed at it.
  for (const toolkit of [undefined, null, 7, {}, [SLUG_A]]) {
    const got = await doneAgainst([{ ...wellFormed(), toolkit }]);
    assert.deepEqual(got.state, { state: "not-connected" }, JSON.stringify(toolkit));
    assert.equal(got.recorded.length, 0);
  }
});

test("E's control: the well-formed entry each leg spoils DOES connect", async () => {
  // Five refusals prove nothing on their own — `return false` refuses all of
  // them and everybody else too, and nobody could ever connect anything. This
  // is the same object each case above spoils one field of, unspoiled.
  const got = await doneAgainst([wellFormed()]);
  assert.equal(got.state.state, "connected");
  assert.equal(got.state.state === "connected" && got.state.recorded, true);
  assert.equal(got.recorded.length, 1);
  assert.equal(got.recorded[0]!.connected_account_id, "ca_real");
  assert.equal(got.recorded[0]!.user_id, OWNER);
  assert.equal(got.completedAt, T0 + 60_000);
});

test("E's control: one unreadable entry does not spoil a readable one beside it", async () => {
  // A vendor list is many rows and one of them being junk is not a verdict on
  // the rest. Refusing the whole list on a single bad entry would be an outage
  // for an owner whose account is right there in it.
  const got = await doneAgainst([null, { ...wellFormed(), user_id: 7 }, wellFormed()]);
  assert.equal(got.state.state, "connected");
  assert.equal(got.recorded.length, 1);
});

// ===========================================================================
// FINDING F — THREE ORACLES THAT WERE COPIES OF THE THING THEY MEASURED
// ===========================================================================
// `CALLBACK_SUCCESS` and `CALLBACK_WINDOW_MS` are asserted all over this file
// by being IMPORTED and handed back to the module. That proves the module is
// self-consistent and nothing else: change `CALLBACK_SUCCESS` to "banana" and
// every one of those tests still passes, while production stops recognising the
// vendor's callbacks. Change `CALLBACK_WINDOW_MS` to a second and the boundary
// tests still pass, while every real OAuth round trip expires mid-password-
// manager. An oracle that is a copy of the implementation catches nothing —
// this layer measured that once already, which is why the connect-link prefix
// is written out in each suite rather than imported.
//
// So the values are written down here, independently, and the behaviour is
// driven with the literals rather than with the constants.

test("F1: the vendor's spelling of success is 'success', written out", () => {
  assert.equal(CALLBACK_SUCCESS, "success");
});

test("F1: a callback carrying the literal word connects, and a near miss does not", async () => {
  // Driven with literals on purpose. If the constant drifts, this goes red;
  // if the constant is what the test reads, nothing can.
  const yes = await doneAgainstStatus("success");
  assert.equal(yes.state.state, "connected");
  assert.equal(yes.recorded.length, 1);

  for (const wrong of ["SUCCESS", " success", "success ", "successful", "ok", "true", "", null]) {
    const no = await doneAgainstStatus(wrong);
    assert.deepEqual(no.state, { state: "not-connected" }, JSON.stringify(wrong));
    assert.equal(no.recorded.length, 0, JSON.stringify(wrong));
  }
});

/** One `done` whose only variable is the vendor's status field. */
async function doneAgainstStatus(status: string | null) {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const state = await connectPageDone(
    link.token,
    { status, connectedAccountId: "ca_real" },
    {
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
      provider: stubProvider({ accounts: [acct("ca_real")] }),
    },
  );
  return { state, recorded: s.recorded };
}

test("F2: the callback window is one hour, written out, and is NOT the link's TTL", () => {
  assert.equal(CALLBACK_WINDOW_MS, 3_600_000);
  assert.equal(CALLBACK_WINDOW_MS, 60 * 60 * 1000);
  // The two answer different questions and the docstring says so: LINK_TTL_MS
  // is how long an UNTAPPED link may sit in a text; this is how long the vendor
  // round trip may take — a password manager, a 2FA push, a workspace picker,
  // and in the Notion case a login the person did not have. Collapsing them
  // would throw away connections that exist at the vendor, with no webhook that
  // would ever mention them again.
  assert.notEqual(CALLBACK_WINDOW_MS, LINK_TTL_MS);
  assert.ok(CALLBACK_WINDOW_MS > LINK_TTL_MS);
});

test("F2: the hour is the hour, measured with the literal rather than the constant", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const usedAt = T0 + 1;
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_real" };
  const provider = stubProvider({ accounts: [acct("ca_real")] });
  const opts = { signedInAs: OWNER, store, onConnected: s.onConnected, provider };

  const late = await connectPageDone(link.token, params, { ...opts, now: usedAt + 3_600_000 });
  assert.deepEqual(late, { state: "expired" }, "an hour after the tap the callback is dead");
  assert.equal(s.recorded.length, 0);

  const justInTime = await connectPageDone(link.token, params, {
    ...opts, now: usedAt + 3_600_000 - 1,
  });
  assert.equal(justInTime.state, "connected", "and one millisecond before it, it is alive");
  assert.equal(s.recorded.length, 1);
});

test("F3: a callback with no provider to ask throws where an operator will see it", async () => {
  // A missing provider is a WIRING bug in the Worker, not a person's problem.
  // The alternative — degrading to `could-not-confirm` — would tell every owner
  // "try again" forever while nothing was ever wrong on their side, and the
  // product would look broken to the only people who could not fix it.
  //
  // There was no test for this at all, so the guard could be deleted, softened
  // to a state, or turned into `!== undefined` with the suite green.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_real" };

  for (const provider of [undefined, null, {}, { connections: null }, { connections: "yes" }]) {
    await assert.rejects(
      () => connectPageDone(link.token, params, {
        signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000,
        provider: provider as never,
      }),
      (e: unknown) => {
        assert.ok(e instanceof TypeError, `not a TypeError: ${String(e)}`);
        // It has to say WHY, or the operator reads "cannot read properties of
        // undefined" and starts guessing.
        assert.ok(/confirmed/.test(e.message), e.message);
        return true;
      },
      JSON.stringify(provider),
    );
  }
  assert.equal(s.recorded.length, 0);
  assert.equal(store.all()[0]!.completed_at, null, "and the wiring bug consumed nothing");
});

test("F3's control: the guard fires only on the path that needs a provider", async () => {
  // Every refusal that is settled before the account id has to be confirmed
  // must still answer normally with no provider wired, or one wiring bug turns
  // every state on this route into a 500 — including the ones that tell a
  // person to sign in.
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const bare = { store, onConnected: s.onConnected, provider: undefined as never };
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_real" };

  assert.deepEqual(
    await connectPageDone(link.token, params, { ...bare, signedInAs: null, now: T0 + 60_000 }),
    { state: "sign-in-required" },
  );
  assert.deepEqual(
    await connectPageDone(link.token, params, { ...bare, signedInAs: STRANGER, now: T0 + 60_000 }),
    { state: "wrong-user" },
  );
  assert.deepEqual(
    await connectPageDone(link.token, params, { ...bare, signedInAs: OWNER, now: T0 + 3_700_000 }),
    { state: "expired" },
  );
  // And a callback the vendor did not call a success never needs asking about.
  assert.deepEqual(
    await connectPageDone(
      link.token,
      { status: "denied", connectedAccountId: "ca_real" },
      { ...bare, signedInAs: OWNER, now: T0 + 60_000 },
    ),
    { state: "not-connected" },
  );
  assert.equal(s.recorded.length, 0);
});
