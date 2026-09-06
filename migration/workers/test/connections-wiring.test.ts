/**
 * test/connections-wiring.test.ts — the link that was missing.
 *
 *   node --experimental-strip-types migration/workers/test/connections-wiring.test.ts
 *
 * WHAT THIS FILE IS FOR. On 2026-09-05 every part of the connect feature was
 * written and tested and `installConnectWiring` had ZERO callers, so every
 * /c/{token} leg answered 503 for every token there has ever been. Five green
 * suites over five parts said nothing about that, because none of them asked
 * whether anything joins them up. This one does, and it asks it the only way
 * that means anything: by loading `src/index.ts` — the real entry point, the
 * same module wrangler deploys — and then driving `connectRoute` with NO
 * injected deps, which is the production path.
 *
 * WHAT IS REAL HERE AND WHAT IS NOT. The wiring, the D1 store, the vendor
 * adapter, the sentence writer, the words audit, the routes, the HTML, the
 * schema (migration/d1/schema.sql, loaded into SQLite) and the account token
 * (a real HMAC from src/pb/auth.ts against a real `owners` row) are all the
 * shipped code. The ONE thing replaced is `globalThis.fetch`, because the two
 * things on the other side of it are another company's HTTP API and a language
 * model. Everything between this file and that socket is production code.
 *
 * NO APP IS HARDCODED, and the whole suite runs on `zellibrix`, an app that
 * exists nowhere but in this file. If a name, a logo or a scope word ever
 * appears in the Worker, this suite keeps passing and the product stops being
 * generic — so the page drawn at the end is scanned for the invented name it
 * could only have got from the catalog.
 *
 * MUTATIONS THIS FILE MUST GO RED ON (run 2026-09-06, not asserted — 19 of 21
 * killed; see the report for the two survivors and why they are survivors):
 *   the `installConnectWiring(connectWiring)` line deleted from src/index.ts;
 *   `onConnected` calling `putConnection` instead of `recordConnection`;
 *   `recordConnection`'s D1 batch split into two awaited statements;
 *   the `WHERE EXISTS` predicate dropped from the nudge insert;
 *   the cross-owner predicate dropped from the shared connections upsert;
 *   `recordConnection` no longer raising on a zero-change upsert;
 *   the memory store writing the nudge on a refused connection;
 *   `missingConfig` returning null unconditionally;
 *   `writes_enabled` forced true in the wiring;
 *   the nudge upsert's DO UPDATE widened to overwrite `level`;
 *   the memory flip resetting the decline ladder, or never creating a row;
 *   `makePermissionWords` swapped for a stub that returns three fixed lines;
 *   the prompt built without the catalog's scopes;
 *   an unreadable model reply repaired into three sentences;
 *   the fenced-reply unwrap removed; the model's own text ignored;
 *   `''` no longer mapping to a null alias; the clock pinned in the deps.
 */
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { FakeD1, asD1, type FakeStatement } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import {
  connectRoute, connectWiringInstalled, tokenHandle, SESSION_COOKIE,
  type ConnectEnv, type Connection,
} from "../src/routes/connect.ts";
import { connectDeps, makeSentenceWriter, type ConnectWiringEnv } from "../src/connections/wiring.ts";
import {
  ComposioConnections, connectionsFromEnv, resetConnectionsProvider, COMPOSIO_BASE_URL,
} from "../src/connections/provider.ts";
import { PermissionWordsRefused } from "../src/connections/words.ts";
import {
  createD1Store, createMemoryStore, CrossOwnerWrite, type ConnectionsStore,
} from "../src/connections/store.ts";
// THE LINK UNDER TEST. Imported for its side effect and nothing else: loading
// the Worker's entry point is what installs the wiring, and if that line is
// ever deleted the first check below goes red.
import "../src/index.ts";

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const PB_NOW = "2026-09-05 12:00:00.000Z";
const OWNER = "ownerrefaaaaaa1";      // 15 lowercase alphanumerics, as D1 mints
const STRANGER = "strangerowner12";
const NOW = 1_757_000_000_000;
const LINK_TTL_MS = 10 * 60 * 1000;

/** An app that exists nowhere but here. The Worker has never heard of it, and
 *  the page it draws at the end must still carry its name. */
const APP = {
  slug: "zellibrix",
  name: "Zellibrix",
  logo: "https://cdn.example.invalid/z.png",
  description: "Where your team keeps its notes.",
  app_url: "https://zellibrix.example.invalid",
  scopes: ["notes.read", "notes.write"],
};

/** Three lines a model could plausibly write, that words.ts will accept: three
 *  of them, distinct, under 80 characters, no exclamation, no URL, and none of
 *  the register the spec forbids. */
const GOOD_SENTENCES = [
  "Anticipy can read your Zellibrix notes when you ask about them.",
  "It can add a note for you when you ask it to.",
  "You can turn this off any time in Settings.",
];

interface FetchCall { url: string; body: string }

/** Every request the Worker made to the outside world, and what answers it. */
interface Socket {
  calls: FetchCall[];
  /** What the model says next, as the raw assistant text. */
  modelText: string;
  /** Set to make the catalog answer 500, the way a vendor outage does. */
  catalogFails: boolean;
  /** The status the model answers with. 500 is a provider having a bad day. */
  modelStatus: number;
  restore: () => void;
}

function socket(): Socket {
  const real = globalThis.fetch;
  const s: Socket = {
    calls: [],
    modelText: JSON.stringify({ sentences: GOOD_SENTENCES }),
    catalogFails: false,
    modelStatus: 200,
    restore: () => { globalThis.fetch = real; },
  };
  globalThis.fetch = (async (input: unknown, init?: { body?: unknown }) => {
    const url = String((input as { url?: string })?.url ?? input);
    s.calls.push({ url, body: String(init?.body ?? "") });
    const json = (status: number, value: unknown): Response =>
      new Response(JSON.stringify(value), {
        status, headers: { "content-type": "application/json" },
      });
    if (url.startsWith(COMPOSIO_BASE_URL)) {
      if (s.catalogFails) return json(500, { error: "the vendor is down" });
      if (url.includes("/toolkits/")) return json(200, APP);
      return json(200, {});
    }
    // Both model paths land here; the reply shape is the chat-completions one,
    // which is what src/llm.ts's OpenRouter leg returns unchanged.
    if (s.modelStatus !== 200) return json(s.modelStatus, { error: { message: "upstream" } });
    return json(200, { choices: [{ message: { content: s.modelText } }] });
  }) as typeof globalThis.fetch;
  // The adapter binds globalThis.fetch when it is CONSTRUCTED, and the isolate
  // caches one adapter, so a stub installed after that would never be reached.
  resetConnectionsProvider();
  return s;
}

interface Rig {
  d1: FakeD1;
  env: ConnectWiringEnv;
  token: string;
  handle: string;
  ownerToken: string;
}

/** A Worker configured the way a deployed one is: a D1 binding with the real
 *  schema, an auth secret, the vendor secret and a model key. */
async function rig(over: Partial<ConnectWiringEnv> = {}): Promise<Rig> {
  const d1 = new FakeD1();
  for (const [id, key] of [[OWNER, "key-owner"], [STRANGER, "key-stranger"]]) {
    d1.db.prepare(
      `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
         password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,'','')`,
    ).run(id, PB_NOW, PB_NOW, `${id}@anticipy-test.invalid`, key);
  }
  const env = {
    DB: asD1(d1),
    ANTICIPY_AUTH_SECRET: "connections-wiring-test-secret",
    COMPOSIO_API_KEY: "ck_test_not_a_real_key",
    OPENROUTER_API_KEY: "or_test_not_a_real_key",
    ...over,
  } as unknown as ConnectWiringEnv;

  const token = randomBytes(32).toString("base64url");
  const handle = await tokenHandle(token);
  return {
    d1, env, token, handle,
    ownerToken: await issueToken(env as never, OWNER, "key-owner"),
  };
}

/** A live, unspent connect link for OWNER, written straight into SQLite so the
 *  store is being READ rather than being asked to confirm its own write. */
function seedLink(r: Rig, opts: { toolkit?: string; alias?: string; expiresAt?: number } = {}): void {
  r.d1.db.prepare(
    `INSERT INTO connect_links (token_handle,user_id,toolkit,alias,expires_at,used_at,completed_at)
     VALUES (?,?,?,?,?,NULL,NULL)`,
  ).run(r.handle, OWNER, opts.toolkit ?? APP.slug, opts.alias ?? "",
        opts.expiresAt ?? Date.now() + LINK_TTL_MS);
}

const connection = (over: Partial<Connection> = {}): Connection => ({
  user_id: OWNER,
  toolkit: APP.slug,
  connected_account_id: "ca_VENDOR_1",
  alias: null,
  status: "connected",
  writes_enabled: false,
  last_used_at: null,
  ...over,
});

function getReq(path: string, token?: string): Request {
  const headers: Record<string, string> = {};
  if (token) headers.Cookie = `${SESSION_COOKIE}=${token}`;
  return new Request("https://api.anticipy.ai" + path, { headers });
}

/** A binding that counts how many BATCHES went through it and remembers the
 *  statements each one carried. `onConnected` must use exactly one. */
function countingBinding(d1: FakeD1) {
  const state = { batches: 0, batched: [] as string[][] };
  const binding = {
    prepare: (sql: string) => d1.prepare(sql),
    async batch(stmts: FakeStatement[]) {
      state.batches++;
      state.batched.push(stmts.map((s) => s.sql));
      return d1.batch(stmts);
    },
    exec: (sql: string) => d1.exec(sql),
  } as unknown as D1Database;
  return { binding, state };
}

const writes = (d1: FakeD1, from: number): string[] =>
  d1.log.slice(from).filter((sql) => /^\s*(INSERT|UPDATE|DELETE)/i.test(sql));

// ===========================================================================
// 1. THE WIRING IS INSTALLED
// ===========================================================================

await check("loading the Worker's entry point installs the connect wiring", () => {
  // The whole defect, as one assertion. Before src/index.ts called
  // installConnectWiring this was false in production and every /c/ leg
  // answered 503 — while five suites over five finished modules stayed green.
  assert.equal(connectWiringInstalled(), true,
    "src/index.ts does not install the connect wiring, so every /c/ route on the "
      + "deployed Worker answers 503 and no person can connect anything");
});

await check("a configured Worker gets all four ports, and none of the three optional ones", async () => {
  const s = socket();
  const r = await rig();
  const deps = connectDeps(r.env);
  assert.ok(deps, "a fully configured Worker was handed no deps at all");
  assert.equal(typeof deps.store.read, "function");
  assert.equal(typeof deps.store.claim, "function");
  assert.equal(typeof deps.store.complete, "function");
  assert.equal(typeof deps.store.release, "function");
  assert.equal(typeof deps.provider.toolkit, "function");
  assert.equal(typeof deps.provider.authorize, "function");
  assert.equal(typeof deps.provider.connections, "function");
  assert.equal(typeof deps.words.sentences, "function");
  assert.equal(typeof deps.onConnected, "function");

  // LEFT UNSET ON PURPOSE, each for its own reason, and each one a defect if it
  // is filled in here: `now` is the tests' clock and production owns the real
  // one; `successStatus` is the vendor's spelling and there is nowhere yet to
  // configure it; and `baseUrl` would SHADOW env.CONNECT_BASE_URL, which is the
  // variable a preview deployment sets so its callbacks do not point at
  // production.
  assert.equal(deps.now, undefined, "the wiring pinned the clock production owns");
  assert.equal(deps.successStatus, undefined);
  assert.equal(deps.baseUrl, undefined,
    "a baseUrl here shadows env.CONNECT_BASE_URL, and a preview whose callback URL "
      + "silently points at production is what that variable exists to prevent");
  s.restore();
});

// ===========================================================================
// 2. EACH DEP IS THE REAL ONE
// ===========================================================================

await check("store: the real D1 store, over this Worker's own binding", async () => {
  const s = socket();
  const r = await rig();
  seedLink(r, { alias: "work" });
  const deps = connectDeps(r.env)!;

  // Written by SQLite, read by the port. A fake store would answer null here.
  const row = await deps.store.read(r.handle);
  assert.ok(row, "the store port did not read this Worker's own connect_links table");
  assert.equal(row.user_id, OWNER);
  assert.equal(row.toolkit, APP.slug);
  assert.equal(row.alias, "work");

  // THE ALIAS MAPPING. The column is TEXT NOT NULL DEFAULT '' because '' is
  // part of a primary key elsewhere and SQLite counts NULLs in a unique index
  // as distinct; the contract wants `null`. A store that handed `""` back would
  // put "(your  account)" on the connect page.
  const r2 = await rig();
  seedLink(r2);
  const bare = await connectDeps(r2.env)!.store.read(r2.handle);
  assert.equal(bare?.alias, null, "the empty-string alias was not mapped back to null");

  // And the compare-and-set is the real one: one winner, and the loser is told
  // the row is already spent rather than handed a second live link.
  const first = await deps.store.claim(r.handle, NOW);
  const second = await deps.store.claim(r.handle, NOW);
  assert.equal(first.won, true);
  assert.equal(second.won, false);
  assert.equal(second.row?.used_at, NOW);
  s.restore();
});

await check("provider: the real vendor adapter, from the isolate's own factory", async () => {
  const s = socket();
  const r = await rig();
  const deps = connectDeps(r.env)!;
  assert.ok(deps.provider instanceof ComposioConnections,
    "the catalog port is not the shipped adapter");
  assert.equal(deps.provider, connectionsFromEnv(r.env),
    "the wiring built its own adapter instead of taking the isolate's, so every request "
      + "would mint a fresh session and a link minted in one session would be invisible "
      + "to the next screen");

  // And it really talks to the catalog: the app's name comes back off the wire,
  // and nothing in the Worker knew it.
  const meta = await deps.provider.toolkit(APP.slug);
  assert.equal(meta.name, APP.name);
  assert.deepEqual(meta.scopes, APP.scopes);
  assert.ok(s.calls.some((c) => c.url === `${COMPOSIO_BASE_URL}/toolkits/${APP.slug}`),
    "the catalog was never asked");
  s.restore();
});

await check("words: the real audit, and it REFUSES rather than inventing sentences", async () => {
  const s = socket();
  const r = await rig();
  const deps = connectDeps(r.env)!;
  const before = s.calls.length;

  // A toolkit with no scopes. A permission sentence not derived from a scope is
  // an invention about what the connection gets, so the model is not even
  // asked. A stub that returned three fixed lines would pass every other check
  // in this file and fail this one.
  const err = await deps.words.sentences({
    slug: "zellibrix", name: "Zellibrix", logo: null, description: null, appUrl: null, scopes: [],
  } as never).then(() => null, (e: Error) => e);
  assert.ok(err instanceof PermissionWordsRefused,
    `a scopeless toolkit produced sentences instead of a refusal (${String(err)})`);
  assert.equal(err.refusal.cause, "no-scopes");
  assert.equal(s.calls.length, before,
    "the model was asked to write sentences with nothing to derive them from");
  s.restore();
});

await check("words: the model's own words reach the page, and the prompt is built from the catalog",
  async () => {
    const s = socket();
    const r = await rig();
    const deps = connectDeps(r.env)!;
    const meta = await deps.provider.toolkit(APP.slug);
    const lines = await deps.words.sentences(meta);

    assert.deepEqual(lines, GOOD_SENTENCES,
      "the sentences were rewritten on their way to the page; what a person consents to "
        + "must be what the model actually wrote");

    const ask = s.calls[s.calls.length - 1]!;
    assert.match(ask.url, /chat\/completions$/, "the sentence writer did not use the model path");
    // EVERY concrete word in the prompt came from the catalog row.
    for (const scope of APP.scopes) {
      assert.ok(ask.body.includes(scope), `the prompt did not carry the scope ${scope}`);
    }
    assert.ok(ask.body.includes(APP.name), "the prompt did not carry the app's own name");
    s.restore();
  });

await check("words: a model answer that breaks the register is refused, not published", async () => {
  const s = socket();
  const r = await rig();
  const deps = connectDeps(r.env)!;
  const meta = await deps.provider.toolkit(APP.slug);

  // Two sentences where the page shows three. Padding would invent a
  // permission; trimming would hide one.
  s.modelText = JSON.stringify({ sentences: GOOD_SENTENCES.slice(0, 2) });
  const short = await deps.words.sentences(meta).then(() => null, (e: Error) => e);
  assert.ok(short instanceof PermissionWordsRefused, "two sentences were published as three");
  assert.equal(short.refusal.cause, "wrong-count");

  // The register the spec forbids, arriving from the model.
  s.modelText = JSON.stringify({
    sentences: [
      "Anticipy asks for permissions on your Zellibrix account.",
      GOOD_SENTENCES[1], GOOD_SENTENCES[2],
    ],
  });
  const stiff = await deps.words.sentences(meta).then(() => null, (e: Error) => e);
  assert.ok(stiff instanceof PermissionWordsRefused,
    "a consent-screen word reached the page the spec spends a page forbidding it on");
  assert.equal(stiff.refusal.cause, "forbidden-word");

  // A reply nobody can read is handed on AS ITSELF, so it is refused here
  // rather than becoming three sentences the writer invented on the way past.
  s.modelText = "I'd be happy to help with that.";
  const prose = await deps.words.sentences(meta).then(() => null, (e: Error) => e);
  assert.ok(prose instanceof PermissionWordsRefused, "a model's chattiness was drawn as consent copy");
  assert.equal(prose.refusal.cause, "malformed-reply");

  // NOBODY ANSWERED is its own state, and it is not permission to make three
  // sentences up.
  s.modelText = "";
  const quiet = await deps.words.sentences(meta).then(() => null, (e: Error) => e);
  assert.ok(quiet instanceof PermissionWordsRefused);
  assert.equal(quiet.refusal.cause, "no-verdict");
  s.restore();
});

await check("a model that is down refuses the page, and never publishes a blank list", async () => {
  const s = socket();
  const r = await rig();
  seedLink(r);
  s.modelStatus = 500;
  // The consent page's claims are a FLOOR: showing a person what they are about
  // to hand over is a privilege that needs a verdict, and a provider having a
  // bad day is not one. The page must refuse, never render a Connect button
  // over nothing.
  const res = await connectRoute(getReq(`/c/${r.token}`, r.ownerToken), r.env as ConnectEnv);
  const html = await res.text();
  assert.equal(res.status, 503, "a dead model drew a consent page");
  assert.ok(!html.includes("<form"), "a Connect button was drawn over a blank list of claims");
  assert.ok(!html.includes(APP.name), "the page named the app it could say nothing about");
  s.restore();
});

await check("the sentence writer hands a shape back rather than repairing it", async () => {
  const s = socket();
  const r = await rig();
  const write = makeSentenceWriter(r.env);
  const meta = { slug: APP.slug, name: APP.name, logo: null, description: null,
                 appUrl: null, scopes: APP.scopes } as never;

  s.modelText = JSON.stringify(GOOD_SENTENCES);              // a bare array
  assert.deepEqual(await write(meta), GOOD_SENTENCES, "a bare array was not accepted");

  s.modelText = "```json\n" + JSON.stringify({ sentences: GOOD_SENTENCES }) + "\n```";
  assert.deepEqual(await write(meta), GOOD_SENTENCES, "a fenced reply was not unwrapped");

  // Unreadable comes back AS ITSELF, for words.ts to call malformed-reply. It
  // is never turned into three sentences by this file.
  s.modelText = "I'd be happy to help with that.";
  assert.equal(await write(meta), "I'd be happy to help with that.");
  s.restore();
});

// ===========================================================================
// 3. onConnected — ONE BATCH, IDEMPOTENT
// ===========================================================================

await check("onConnected writes the connection AND flips the nudge, in ONE batch", async () => {
  const s = socket();
  const r = await rig();
  const counted = countingBinding(r.d1);
  const deps = connectDeps({ ...r.env, DB: counted.binding })!;

  const from = r.d1.log.length;
  await deps.onConnected(connection());

  assert.equal(counted.state.batches, 1,
    "the two halves went out as separate statements — two failure modes under one "
      + "exactly-once lease, and the half that failed would be invisible");
  const batched = counted.state.batched[0]!;
  assert.equal(batched.length, 2, "the batch did not carry both halves");
  assert.match(batched[0]!, /INSERT INTO "connections"/);
  assert.match(batched[1]!, /INSERT INTO "connect_nudges"/);
  assert.deepEqual(writes(r.d1, from).length, 2,
    "something was written outside the batch");

  const conn = r.d1.rows<Record<string, unknown>>(`SELECT * FROM connections`);
  assert.equal(conn.length, 1);
  assert.equal(conn[0]!.user_id, OWNER);
  assert.equal(conn[0]!.toolkit, APP.slug);
  assert.equal(conn[0]!.connected_account_id, "ca_VENDOR_1");
  assert.equal(conn[0]!.status, "connected");
  // THE WRITE OPT-IN, off by default. A connection that arrived write-enabled
  // would let the first step that ran against it send mail on the owner's
  // behalf, having been asked for nothing but a connection.
  assert.equal(conn[0]!.writes_enabled, 0, "the connection was written with writes ON");

  const nudge = r.d1.rows<Record<string, unknown>>(`SELECT * FROM connect_nudges`);
  assert.equal(nudge.length, 1, "the nudge row was not flipped, so this owner keeps being "
    + "asked to connect the app they just connected");
  assert.equal(nudge[0]!.user_id, OWNER);
  assert.equal(nudge[0]!.toolkit, APP.slug);
  assert.equal(nudge[0]!.state, "connected");
  assert.ok(Number(nudge[0]!.acted_at) > 0, "the connect was not stamped as an action");
  s.restore();
});

await check("onConnected is idempotent: a refresh leaves one row and one flip", async () => {
  const s = socket();
  const r = await rig();
  const deps = connectDeps(r.env)!;

  // The documented case: the write committed and then the response was lost, so
  // the person's refresh attempts it again. Delivering the same connection
  // twice is a repaired row; delivering it zero times is a connection that
  // exists at the vendor and nowhere here.
  await deps.onConnected(connection());
  await deps.onConnected(connection());

  assert.equal(r.d1.rows(`SELECT * FROM connections`).length, 1,
    "a refresh wrote a second connections row");
  const nudge = r.d1.rows<Record<string, unknown>>(`SELECT * FROM connect_nudges`);
  assert.equal(nudge.length, 1, "a refresh wrote a second nudge row");
  assert.equal(nudge[0]!.state, "connected");
  s.restore();
});

await check("the flip keeps the ask's own history — level, trigger, sent_at, channel", async () => {
  const s = socket();
  const r = await rig();
  // This owner was asked about this app and said no, twice.
  r.d1.db.prepare(
    `INSERT INTO connect_nudges (user_id,toolkit,state,level,snooze_until,trigger,sent_at,acted_at,channel)
     VALUES (?,?,?,?,?,?,?,?,?)`,
  ).run(OWNER, APP.slug, "declined", 2, 111, "in_task", 222, 333, "sms");

  await connectDeps(r.env)!.onConnected(connection());

  const nudge = r.d1.rows<Record<string, unknown>>(`SELECT * FROM connect_nudges`)[0]!;
  assert.equal(nudge.state, "connected", "the state was not flipped");
  assert.ok(Number(nudge.acted_at) > 333, "acted_at was not moved to this connect");
  // NOT this write's to erase. The declines are how the spec's timers get tuned
  // and how "this owner has said no twice" survives; a connect that reset them
  // would restart the ladder at zero the day the app is disconnected.
  assert.equal(nudge.level, 2, "the decline ladder was reset by a connect");
  assert.equal(nudge.trigger, "in_task", "the moment the ask came from was erased");
  assert.equal(nudge.sent_at, 222, "the ask's own timestamp was erased");
  assert.equal(nudge.channel, "sms");
  s.restore();
});

await check("a display name never reaches a query, even from inside the wiring", async () => {
  const s = socket();
  const r = await rig();
  const deps = connectDeps(r.env)!;
  const from = r.d1.log.length;
  // `user_id` is bound at mint time and routes/connect.ts never reads an owner
  // off a request, so this cannot happen today. It is checked anyway because
  // the type is ERASED before this line runs, and one operator's own mailbox
  // served everybody once already.
  const err = await deps.onConnected(connection({ user_id: "jose@anticipy.ai" as never }))
    .then(() => null, (e: Error) => e);
  assert.ok(err, "an email address was accepted as an owner");
  assert.match(err.message, /owner ROW id/);
  assert.deepEqual(writes(r.d1, from), [], "a row was written for a name");
  s.restore();
});

// ===========================================================================
// 4. A MIXED OWNER IS REFUSED — and neither half lands
// ===========================================================================

await check("onConnected refuses a connected account that belongs to somebody else", async () => {
  const s = socket();
  const r = await rig();
  const deps = connectDeps(r.env)!;

  // The vendor's account id is unique ACROSS owners, so a plain upsert on it
  // re-binds a stranger's account to this owner in one statement.
  await deps.onConnected(connection({ user_id: STRANGER, connected_account_id: "ca_THEIRS" }));

  const err = await deps.onConnected(connection({ connected_account_id: "ca_THEIRS" }))
    .then(() => null, (e: Error) => e);
  assert.ok(err instanceof CrossOwnerWrite,
    `a stranger's connected account was re-bound to this owner (${String(err)})`);

  const rows = r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM connections WHERE connected_account_id='ca_THEIRS'`);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.user_id, STRANGER, "the stranger's row was re-bound");

  // AND NEITHER DID THE OTHER HALF. This is why the two statements share one
  // batch and why the nudge insert is conditional on the connections row being
  // this owner's: a flip written for a refused connection tells the ask engine
  // an app is connected that is not, and this owner would never be asked about
  // it again.
  assert.deepEqual(
    r.d1.rows(`SELECT * FROM connect_nudges WHERE user_id=? AND toolkit=?`, OWNER, APP.slug),
    [], "the nudge was flipped for a connection that was refused");

  // THE CONTROL, on the same database: this owner's OWN account still records,
  // so the guard is a guard and not an outage.
  await deps.onConnected(connection({ connected_account_id: "ca_MINE" }));
  assert.equal(
    r.d1.rows(`SELECT * FROM connections WHERE user_id=? AND connected_account_id='ca_MINE'`, OWNER)
      .length, 1);
  assert.equal(
    r.d1.rows(`SELECT * FROM connect_nudges WHERE user_id=? AND toolkit=?`, OWNER, APP.slug)
      .length, 1);
  s.restore();
});

// ===========================================================================
// 4b. THE SAME FOUR PROPERTIES AGAINST THE IN-MEMORY STORE
// ===========================================================================
// `recordConnection` was added to the ConnectionsStore interface, so it exists
// twice: once in SQL and once in the fake the modules above this one unit-test
// with. A fake that accepts what D1 refuses is a test suite that passes on a
// product that does not work — measured here rather than assumed, because the
// mutation that made the fake write the nudge on a refused connection was
// invisible to every other check in this file.

async function recordConformance(
  kind: string, make: () => { store: ConnectionsStore; close: () => void },
): Promise<void> {
  const at = 1_757_000_111_000;

  await check(`[${kind}] recordConnection writes the connection and flips the nudge`, async () => {
    const { store, close } = make();
    await store.recordConnection(connection() as never, at);
    assert.equal((await store.connectionsForOwner(OWNER)).length, 1);
    const nudges = await store.nudgesForOwner(OWNER);
    assert.equal(nudges.length, 1);
    assert.equal(nudges[0]!.state, "connected");
    assert.equal(nudges[0]!.acted_at, at);
    close();
  });

  await check(`[${kind}] recordConnection is idempotent`, async () => {
    const { store, close } = make();
    await store.recordConnection(connection() as never, at);
    await store.recordConnection(connection() as never, at + 5);
    assert.equal((await store.connectionsForOwner(OWNER)).length, 1);
    assert.equal((await store.nudgesForOwner(OWNER)).length, 1);
    close();
  });

  await check(`[${kind}] recordConnection keeps the ask's own history`, async () => {
    const { store, close } = make();
    await store.putNudge({
      user_id: OWNER as never, toolkit: APP.slug, state: "declined", level: 2,
      snooze_until: 111, trigger: "in_task", sent_at: 222, acted_at: 333, channel: "sms",
    });
    await store.recordConnection(connection() as never, at);
    const nudge = (await store.nudgesForOwner(OWNER))[0]!;
    assert.equal(nudge.state, "connected");
    assert.equal(nudge.level, 2, "the decline ladder was reset by a connect");
    assert.equal(nudge.trigger, "in_task");
    assert.equal(nudge.sent_at, 222);
    close();
  });

  await check(`[${kind}] a cross-owner recordConnection writes NEITHER half`, async () => {
    const { store, close } = make();
    await store.recordConnection(
      connection({ user_id: STRANGER, connected_account_id: "ca_THEIRS" }) as never, at);
    const err = await store
      .recordConnection(connection({ connected_account_id: "ca_THEIRS" }) as never, at)
      .then(() => null, (e: Error) => e);
    assert.ok(err instanceof CrossOwnerWrite, `a stranger's account was re-bound (${String(err)})`);
    assert.equal((await store.connectionsForOwner(OWNER)).length, 0);
    assert.deepEqual(await store.nudgesForOwner(OWNER), [],
      "the nudge was flipped for a connection that was refused");
    // CONTROL: the stranger still has theirs, so this is a refusal and not a wipe.
    assert.equal((await store.connectionsForOwner(STRANGER)).length, 1);
    close();
  });
}

await recordConformance("memory", () => ({ store: createMemoryStore(), close: () => {} }));
await recordConformance("d1", () => {
  const d1 = new FakeD1();
  return { store: createD1Store({ DB: asD1(d1) }), close: () => {} };
});

// ===========================================================================
// 5. THE CONTROL — a wired Worker draws the page an unwired one refuses to
// ===========================================================================

await check("a wired Worker draws the connect page, on an app it has never heard of", async () => {
  const s = socket();
  const r = await rig();
  seedLink(r);

  // NO DEPS ARGUMENT. This is the production path, through the wiring
  // src/index.ts installed, and it is the request that answered 503 in
  // production on 2026-09-05.
  const res = await connectRoute(getReq(`/c/${r.token}`, r.ownerToken), r.env as ConnectEnv);
  const html = await res.text();
  assert.equal(res.status, 200, `the wired Worker refused to draw the page: ${html.slice(0, 200)}`);
  assert.ok(html.includes("<form"), "the page has no way to say yes");

  // The app's name, logo and claims came off the catalog and the model. Nothing
  // in the Worker knows this app exists.
  assert.ok(html.includes(APP.name), "the page did not name the app");
  assert.ok(html.includes(APP.logo), "the catalog's logo was not drawn");
  for (const line of GOOD_SENTENCES) {
    assert.ok(html.includes(line), `the page is missing a line the person is agreeing to: ${line}`);
  }
  assert.match(html, /optional/i, "connecting is always optional and every ask says so");

  // The register, on the one page in the product where it matters most.
  const visible = html.replace(/<[^>]*>/g, " ");
  for (const term of ["composio", "authorize", "permission", "permissions", "integration",
                      "api", "oauth"]) {
    assert.doesNotMatch(visible, new RegExp(`\\b${term}\\b`, "i"),
      `"${term}" reached a person's screen`);
  }
  s.restore();
});

await check("with COMPOSIO_API_KEY unset the wiring still installs and the route answers 503",
  async () => {
    const s = socket();
    const r = await rig({ COMPOSIO_API_KEY: undefined });
    seedLink(r);

    // STILL INSTALLED. A missing secret is not a missing feature, and the deploy
    // check that asks "can this Worker serve connect pages at all" must not be
    // answered by whether one variable is set.
    assert.equal(connectWiringInstalled(), true);

    const res = await connectRoute(getReq(`/c/${r.token}`, r.ownerToken), r.env as ConnectEnv);
    const html = await res.text();
    assert.equal(res.status, 503, "an unconfigured Worker did not say so");
    assert.ok(!html.includes("<form"), "an unwired Worker drew a consent page");
    assert.match(html, /nothing has changed/i);
    // The honest 503, not the hopeful one. "Refresh in a moment" is a lie when
    // the secret is permanently unset.
    assert.doesNotMatch(html, /refresh/i,
      "the page told the person to refresh a Worker that will never be able to answer");
    assert.equal(s.calls.length, 0, "an unconfigured Worker still called out to the vendor");
    s.restore();
  });

await check("a Worker with no model key answers the same 503, rather than a blank consent page",
  async () => {
    const s = socket();
    const r = await rig({ OPENROUTER_API_KEY: undefined });
    seedLink(r);
    assert.equal(connectDeps(r.env), null,
      "a Worker that cannot write the permission sentences handed back deps anyway, so the "
        + "only page it could draw is a Connect button over a blank list of claims");
    const res = await connectRoute(getReq(`/c/${r.token}`, r.ownerToken), r.env as ConnectEnv);
    assert.equal(res.status, 503);
    assert.ok(!(await res.text()).includes("<form"));
    s.restore();
  });

await check("CONTROL: the 503s above are the wiring's, not a broken page or a dead vendor",
  async () => {
    const s = socket();
    const r = await rig();
    seedLink(r);
    // Same Worker, same request, one difference: the catalog is down. A vendor
    // outage must NOT read as an unconfigured Worker — it is the one 503 where
    // "refresh in a moment" is true.
    s.catalogFails = true;
    const res = await connectRoute(getReq(`/c/${r.token}`, r.ownerToken), r.env as ConnectEnv);
    const html = await res.text();
    assert.equal(res.status, 503);
    assert.match(html, /refresh/i, "a transient vendor failure was reported as a dead feature");
    assert.ok(s.calls.length > 0, "the catalog was never asked, so this proves nothing");
    s.restore();
  });

await check("a signed-out caller is told nothing, wired or not", async () => {
  const s = socket();
  const r = await rig();
  seedLink(r);
  const res = await connectRoute(getReq(`/c/${r.token}`), r.env as ConnectEnv);
  const html = await res.text();
  assert.equal(res.status, 401, "the wiring let an anonymous caller past the session check");
  assert.doesNotMatch(html, /zellibrix/i,
    "the app the owner is connecting was named to whoever intercepted the text");
  assert.equal(s.calls.length, 0, "the vendor was asked about a caller who proved nothing");
  s.restore();
});

// ===========================================================================
// 6. NO APP IS HARDCODED — the scan the whole feature turns on
// ===========================================================================

await check("the wiring names no app, no logo and no scope word", async () => {
  const { readFileSync } = await import("node:fs");
  const { fileURLToPath } = await import("node:url");
  const { dirname, join } = await import("node:path");
  const here = dirname(fileURLToPath(import.meta.url));
  const source = readFileSync(join(here, "..", "src", "connections", "wiring.ts"), "utf8");
  const code = source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
  assert.ok(code.length > 2000, "the comment stripper ate the file; this scan proves nothing");
  for (const app of ["gmail", "notion", "slack", "googlecalendar", "zellibrix"]) {
    assert.doesNotMatch(code, new RegExp(`\\b${app}\\b`, "i"),
      `wiring.ts names ${app}; the day a toolkit is named in code is the day a toolkit `
        + "the catalog knows about renders a page with nothing on it");
  }
  // The vendor's name may appear in a comment and in the SECRET's name; it may
  // never appear where a page could print it.
  assert.ok(!/composio/i.test(code.replace(/COMPOSIO_API_KEY/g, "")),
    "wiring.ts carries the vendor's name outside a comment");
});

console.log(`connections-wiring: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
