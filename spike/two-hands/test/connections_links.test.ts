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

function stubProvider(opts: { authorize?: () => never | { redirectUrl: unknown }; failToolkit?: boolean } = {}) {
  const authorizeCalls: AuthorizeCall[] = [];
  const toolkitCalls: string[] = [];
  return {
    authorizeCalls,
    toolkitCalls,
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
  claims = 0;
  completes = 0;
  async put(row: StoredLink): Promise<void> {
    this.puts++;
    await tick();
    return this.inner.put(row);
  }
  async read(handle: string): Promise<StoredLink | null> {
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
  const base = { signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 1 };
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
    { signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000 },
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
    { signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000 },
  );
  assert.equal(done.state, "connected");
  assert.equal(s.recorded[0]!.user_id, OWNER);
});

test("a refreshed callback shows the same page and records exactly once", async () => {
  const store = new MemoryConnectLinkStore();
  const s = sink();
  const link = await tapped(store);
  const params = { status: CALLBACK_SUCCESS, connectedAccountId: "ca_BNgvxQtJ703C" };
  const opts = { signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000 };
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
      { signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000 },
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
      { signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 60_000 },
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
    { signedInAs: OWNER, store, onConnected: s.onConnected, successStatus: "ACTIVE", now: T0 + 60_000 },
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
    { signedInAs: OWNER, store, onConnected: s.onConnected, now: wellPastTheTtl },
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
  const late = await connectPageDone(link.token, params, {
    signedInAs: OWNER, store, onConnected: s.onConnected, now: usedAt + CALLBACK_WINDOW_MS,
  });
  assert.deepEqual(late, { state: "expired" });
  assert.equal(s.recorded.length, 0);
  const justInTime = await connectPageDone(link.token, params, {
    signedInAs: OWNER, store, onConnected: s.onConnected, now: usedAt + CALLBACK_WINDOW_MS - 1,
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
    { signedInAs: STRANGER, store, onConnected: s.onConnected, now: T0 + 60_000 },
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
    { signedInAs: null, store, onConnected: s.onConnected, now: T0 + 60_000 },
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
      signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 2,
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
      { signedInAs: OWNER, store, onConnected: s.onConnected, now: T0 + 3 },
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
