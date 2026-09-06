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
 *
 * WHAT THAT ROUND STILL COULD NOT SEE, and section 6 was written for. Every
 * check above section 6 calls `connectDeps`, and `connectDeps` is not what
 * production installs: src/index.ts hands over `connectWiring` and
 * `connectAuthWiring`, two exported consts that wrap it. Measured 2026-09-06
 * with an anchor-unique harness (an anchor occurring other than exactly once
 * refuses to patch, because a regex that silently missed has produced three
 * false "it is tested" readings in this repo):
 *
 *   `connectAuthWiring` gutted to `return null` — SURVIVED, npm test 60/0.
 *   The phone-code half of the connect chain had a production path no
 *   assertion in this repo executed.
 *
 * FIVE MUTATIONS RUN AGAINST src/connections/wiring.ts AFTER section 6, ALL
 * KILLED, with the check that killed each:
 *   `connectWiring` -> null
 *     -> "connectWiring — the value src/index.ts installs — builds the four REAL ports"
 *   `connectAuthWiring` -> null
 *     -> "CONTROL: /c/{token}/code with NO injected deps reaches the real wiring"
 *   `codes:` swapped for one whose `insert` writes nothing
 *     -> "connectAuthWiring — the other value src/index.ts installs — is the code half, over D1"
 *   `toolkitName` returning a hardcoded app name instead of asking the catalog
 *     -> "connectAuthWiring's app name comes from the catalog, and a blip costs only the name"
 *   `connectAuthWiring` no longer refusing when `connectDeps` refuses
 *     -> "CONTROL: the same request on a Worker with no vendor secret is the honest 503"
 *
 * AND THREE AGAINST src/index.ts's ROUTER, which section 7 exists for. All
 * KILLED, all previously invisible — no test in this repo went through
 * `worker.fetch` for either prefix:
 *   the `/me/connections` branch deleted
 *     -> "worker.fetch routes /me/connections to the six routes, not to the 404"
 *   `path.startsWith("/c/")` pointed at a prefix nothing uses
 *     -> "worker.fetch routes /c/{token} and /c/{token}/code, and neither is a 404"
 *   the `/c/` branch no longer chaining connectAuthRoute before connectRoute
 *     -> "worker.fetch routes /c/{token} and /c/{token}/code, and neither is a 404"
 *
 * SECTION 9 (2026-09-06) closes four findings from the Connections audits.
 * Every check there went RED against the code as it stood before its fix, and
 * SIXTEEN MUTATIONS were run against src/connections/wiring.ts afterwards —
 * 16 killed, 0 survivors, each anchored on a literal the source carries
 * exactly once (an anchor matching anything other than once refused to patch,
 * because a regex that silently missed has produced three false "it is
 * tested" readings in this repo):
 *   the twin never recording the link; the row taken BEFORE the send;
 *   `sent_at` left null; `needs_reconnect` overwritten as `asked`; the decline
 *   ladder reset by a solicited link; every reply stamped `ignore` again; a
 *   question not marked as one; the claim dropped entirely; the age bound
 *   removed from `unfinished`; stranded rows still counted by
 *   `resultDelivered`; the two-sentence log collapsed back into one; the bound
 *   widened to 100000 days; the account picked by row order again; the
 *   ambiguity refusing silently instead of asking; the refusal widened until
 *   it also refuses an owner with ONE account; the new sentence dropped from
 *   `textReplySentences`.
 *
 * SECTION 10 (2026-09-06) is the round-2 audit ON SECTION 9's OWN FIX. Writing
 * the twin's link down was right; writing it down as `state: 'asked'` said a
 * thing that is not true of it, and 72 hours later `maturedBySilence` turned an
 * errand somebody TEXTED US FOR into a decline against them. Over-correction is
 * a defect. Four mutations against src/connections/wiring.ts, all KILLED, each
 * anchored on a literal the source carries exactly once:
 *   the solicited row saying `asked` again (section 9's shape)
 *     -> "ROUND 2 FINDING 2: an unfinished link the owner asked for is not a
 *        decline" (and the three section-9 checks)
 *   an outstanding push carried through untouched
 *     -> "ROUND 2 FINDING 2: asking for a link ANSWERS the push that was
 *        already out"
 *   `sent_at` no longer stamped
 *     -> "ROUND 2 FINDING 3: a link the owner asked for DOES spend the weekly
 *        budget"
 *   the trigger no longer naming who asked
 *     -> "FINDING 1: a link the owner asked for is written down"
 *
 * SECTION 11 (2026-09-06, round 2) closes ONE finding of its own:
 * `nudgeMomentFor`'s evidence query still carried `AND "weight" > 0`, the
 * predicate src/connections/due.ts had just deleted as "an aliveness test no
 * code path can make false". The fix had been applied in one of the two places
 * that had it. Three checks went RED against the code as it stood; SEVEN
 * MUTATIONS were run afterwards, 7 killed, 0 survivors, each anchored on a
 * literal wiring.ts carries exactly once:
 *   the aliveness filter deleted outright; the floor back to `> 0`; the decay
 *   skipped so the STORED weight decides; `ALIVE_WEIGHT_FLOOR` typed here
 *   instead of imported; the whole decay seam re-implemented locally; the
 *   deleted SQL predicate put back; a junk weight coerced to a live one.
 *
 * TWO OF THE SEVEN SURVIVED THEIR FIRST DRAFT, and both were checks that read
 * as evidence and were not. "the floor is imported" asked only whether the
 * NAME appeared, so a local `const ALIVE_WEIGHT_FLOOR = 0.00625` passed it;
 * and the no-weight-predicate check grepped the whole file, so it failed on
 * the COMMENT above the fixed query. That second one is the same shape that
 * let overnight/is_connect_live.py's hand-copy of due.ts's candidate query
 * drift for a round while a whole-file substring check called it agreement —
 * a substring check over a source file cannot tell code from prose. Both now
 * read the statement and the import line rather than the words around them.
 *
 * LAW 3: everything in sections 9, 10 and 11 is REPO-GREEN. No deploy has
 * carried any of it, and until one has, none of it is fixed in the sense law 3
 * means.
 */
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { FakeD1, asD1, type FakeStatement } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import {
  connectRoute, connectWiringInstalled, tokenHandle, SESSION_COOKIE,
  type ConnectEnv, type Connection,
} from "../src/routes/connect.ts";
import {
  connectAuthWiring, connectDeps, connectWiring, handleInboundText, makeSentenceWriter,
  nudgeMomentFor, runTextCommandPlan, textReplySentences, SENTENCE_ATTEMPTS, TEXT_REPLY,
  type ConnectWiringEnv, type NudgeWiringEnv,
} from "../src/connections/wiring.ts";
import {
  connectAuthRoute, connectAuthWiringInstalled, type ConnectAuthEnv,
} from "../src/routes/connect_auth.ts";
import {
  ComposioConnections, connectionsFromEnv, resetConnectionsProvider, COMPOSIO_BASE_URL,
} from "../src/connections/provider.ts";
import { MAX_SENTENCE_CHARS, PermissionWordsRefused, permissionSentences, forbiddenTermIn }
  from "../src/connections/words.ts";
import {
  createD1Store, createMemoryStore, CrossOwnerWrite, ownerId, type ConnectionsStore,
} from "../src/connections/store.ts";
// THE POLICY THE TWIN'S ROW IS READ BY. Section 10 asserts what a row the twin
// writes MEANS, and meaning is not a column: it is what `maturedBySilence` and
// `shouldAsk` do with it three days later. Importing them is the only way to
// measure that rather than to assert a string.
import {
  GLOBAL_ASK_INTERVAL_DAYS, SILENCE_IS_A_SOFT_NO_HOURS, SNOOZE_DAYS,
  maturedBySilence, shouldAsk,
} from "../src/connections/nudge.ts";
import type { ConnectNudge, NudgeContext }
  from "../../../spike/two-hands/src/connections/contract.ts";
import { SENDBLUE_BASE } from "../src/messaging.ts";
// THE LINK UNDER TEST, twice over. Loading the Worker's entry point is what
// installs the wiring, and if either install line is deleted the first check
// below goes red. The DEFAULT EXPORT is the other half: section 7 drives
// `worker.fetch` so the router branch that hands a request to these routes is
// executed too, rather than assumed. On 2026-09-06 the deployed Worker answered
// 404 on `/c/<43 chars>` while `/api/health` answered 200 — the prefix was not
// carried at all — and no repo check could have seen it, because no repo check
// went through the router.
import worker from "../src/index.ts";

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
  /** The catalog row the vendor serves. Mutable so a check can serve prose the
   *  vendor really publishes rather than the fixture's tidy sentence. */
  app: Record<string, unknown>;
  /** The status the model answers with. 500 is a provider having a bad day. */
  modelStatus: number;
  restore: () => void;
}

function socket(): Socket {
  const real = globalThis.fetch;
  const s: Socket = {
    calls: [],
    modelText: JSON.stringify({ sentences: GOOD_SENTENCES }),
    app: APP as Record<string, unknown>,
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
      if (url.includes("/toolkits/")) return json(200, s.app);
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


await check("an over-long line is sent back to the model with the count that broke", async () => {
  // THE MEASUREMENT THIS EXISTS FOR. Against the live model on 2026-09-06,
  // Gmail's eleven scopes produced the same 84-character line SIX TIMES OUT OF
  // SIX. The prompt already states the 80-character limit. So the writer asks
  // again, showing the model the line it wrote and the count it broke — and
  // with that, Gmail went 0/6 to 6/6.
  const s = socket();
  const r = await rig();
  const write = makeSentenceWriter(r.env);
  const meta = { slug: APP.slug, name: APP.name, logo: null, description: null,
                 appUrl: null, scopes: APP.scopes } as never;

  const tooLongLine = "A".repeat(MAX_SENTENCE_CHARS + 4);
  let turn = 0;
  Object.defineProperty(s, "modelText", {
    get() {
      turn += 1;
      return turn === 1
        ? JSON.stringify({ sentences: [tooLongLine, GOOD_SENTENCES[1], GOOD_SENTENCES[2]] })
        : JSON.stringify({ sentences: GOOD_SENTENCES });
    },
    configurable: true,
  });

  const out = await write(meta);
  assert.deepEqual(out, GOOD_SENTENCES, "the second answer was not returned");
  assert.equal(turn, 2, `the model was asked ${turn} time(s); the retry did not fire`);

  // WHAT THE SECOND REQUEST CARRIED. Asking again identically is pointless —
  // the prompt already said 80 and the model already missed it — so the retry
  // is only worth anything if it names the failure.
  const modelCalls = s.calls.filter((c) => !c.url.startsWith(COMPOSIO_BASE_URL));
  assert.equal(modelCalls.length, 2, "the model was not called twice");
  const second = modelCalls[1]!.body;
  assert.ok(second.includes(tooLongLine),
    "the retry did not show the model the line it wrote");
  assert.ok(second.includes(String(MAX_SENTENCE_CHARS + 4)),
    "the retry did not say how long that line was");
  assert.ok(second.includes(String(MAX_SENTENCE_CHARS)),
    "the retry did not repeat the limit");
  s.restore();
});

await check("a reply that already fits is returned without a second model call", async () => {
  // THE CONTROL. A retry that fires on every request would double the latency
  // of every connect page and double the spend, for nothing.
  const s = socket();
  const r = await rig();
  const write = makeSentenceWriter(r.env);
  const meta = { slug: APP.slug, name: APP.name, logo: null, description: null,
                 appUrl: null, scopes: APP.scopes } as never;

  s.modelText = JSON.stringify({ sentences: GOOD_SENTENCES });
  assert.deepEqual(await write(meta), GOOD_SENTENCES);
  const modelCalls = s.calls.filter((c) => !c.url.startsWith(COMPOSIO_BASE_URL));
  assert.equal(modelCalls.length, 1,
    `a good first answer cost ${modelCalls.length} model calls`);
  s.restore();
});

await check("the retry gives up rather than looping, and words.ts still judges", async () => {
  // THE LIMIT DOES NOT MOVE. A model that never complies is handed back over
  // the limit, and words.ts refuses it with cause "too-long". Raising the cap
  // would have been the easy green and the wrong one: 80 characters is what a
  // person reads, and an unread line is not consent.
  const s = socket();
  const r = await rig();
  const write = makeSentenceWriter(r.env);
  const meta = { slug: APP.slug, name: APP.name, logo: null, description: null,
                 appUrl: null, scopes: APP.scopes } as never;

  // THREE DISTINCT over-long lines. The first draft repeated one line and
  // words.ts refused it as `duplicate` before it ever reached the length rule
  // -- the judge working correctly, and the fixture measuring the wrong refusal.
  const stubborn = [
    "Anticipy can read every message in your mailbox " + "b".repeat(40),
    "Anticipy can send mail from your address whenever " + "c".repeat(40),
    "Anticipy can delete anything it finds in there for " + "d".repeat(40),
  ];
  for (const line of stubborn) {
    assert.ok(line.length > MAX_SENTENCE_CHARS, "the fixture line is not over the limit");
  }
  s.modelText = JSON.stringify({ sentences: stubborn });
  const out = await write(meta);
  const modelCalls = s.calls.filter((c) => !c.url.startsWith(COMPOSIO_BASE_URL));
  assert.ok(modelCalls.length <= SENTENCE_ATTEMPTS,
    `the writer made ${modelCalls.length} model calls; the bound is ${SENTENCE_ATTEMPTS}`);
  assert.ok(modelCalls.length > 1, "it did not retry at all");
  assert.deepEqual(out, stubborn,
    "the writer repaired or truncated the answer instead of handing it to the judge");

  const verdict = await permissionSentences(meta, async () => out) as { cause?: string };
  assert.equal(verdict.cause, "too-long",
    "words.ts stopped refusing an over-long line, so the limit moved");
  s.restore();
});

await check("a vendor description carrying a forbidden word is DROPPED, not shown", async () => {
  // THE ONE SCREEN THE REGISTER RULE EXISTS FOR, and the vendor's own prose
  // walked straight onto it. Measured against the live catalog on 2026-09-06,
  // four of eight descriptions carry "integration" — gmail, googlecalendar,
  // linear and github — and the string below is the real Gmail one, verbatim.
  //
  // Every sentence this product WRITES is screened by permissionSentences. The
  // description was rendered with esc() and nothing else, so the page could say
  // "integration", "api" or the vendor's own name while the copy beside it was
  // forbidden from doing so.
  const vendorProse = "Gmail is Google's email service, featuring spam protection, "
    + "search functionality and integration with other Google services.";

  const s1 = socket();
  const r1 = await rig();
  seedLink(r1);
  s1.app = { ...APP, description: vendorProse };
  const html = await (await connectRoute(
    getReq(`/c/${r1.token}`, r1.ownerToken), r1.env as ConnectEnv)).text();
  s1.restore();

  assert.ok(html.includes(APP.name), "the page stopped naming the app entirely");
  assert.ok(!html.includes("integration"),
    "the vendor's description reached the consent page carrying a forbidden word");
  assert.ok(!html.includes("spam protection"), "the description was shown after all");

  // THE CONTROL: a clean description IS shown. A screen that dropped every
  // description would pass every line above and be a different bug.
  const s2 = socket();
  const r2 = await rig();
  seedLink(r2);
  s2.app = { ...APP, description: "Where your team keeps its notes." };
  const clean = await (await connectRoute(
    getReq(`/c/${r2.token}`, r2.ownerToken), r2.env as ConnectEnv)).text();
  s2.restore();
  assert.ok(clean.includes("Where your team keeps its notes."),
    "a description with nothing wrong with it was dropped too");
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
// 6. THE TWO EXPORTED FACTORIES src/index.ts ACTUALLY INSTALLS
//
// Everything above this point calls `connectDeps`. That is the function the
// wiring is BUILT from, and it is not the value production hands over:
// src/index.ts passes `connectWiring` and `connectAuthWiring`, two exported
// consts that wrap it. Until these checks existed, gutting either of those to
// `return null` left `npm test` at 0 failed for `connectAuthWiring` — measured
// 2026-09-06 with the anchor-unique mutation harness, not reasoned about — so
// the phone-code half of the connect chain had a production path no assertion
// in this repo executed.
//
// Every check below therefore calls the EXPORTED CONST BY NAME, and the two
// controls at the end drive the two routes with NO injected deps, which is
// exactly how src/index.ts calls them.
// ===========================================================================

/** A toolkit row with no scopes, for the one refusal that proves the words port
 *  is the real audit rather than three fixed lines. `permissionSentences`
 *  refuses before the writer is called, so this also proves nothing was asked. */
const SCOPELESS = { slug: "zellibrix", name: "Zellibrix", logo: null, description: null,
                    appUrl: null, scopes: [] as string[] };

await check("connectWiring — the value src/index.ts installs — builds the four REAL ports",
  async () => {
    const s = socket();
    const r = await rig();
    seedLink(r, { alias: "work" });

    // THE EXPORTED CONST, not connectDeps. This is the object `installConnectWiring`
    // was handed at module load, called the way routes/connect.ts calls it.
    const deps = connectWiring(r.env as ConnectEnv);
    assert.ok(deps, "connectWiring handed a fully configured Worker no deps at all");

    // STORE: the real D1 one, over this Worker's own binding. A memory store or
    // a stub would answer null for a row only SQLite has ever seen.
    const row = await deps.store.read(r.handle);
    assert.ok(row, "connectWiring's store did not read this Worker's own connect_links table");
    assert.equal(row.user_id, OWNER);
    assert.equal(row.toolkit, APP.slug);
    assert.equal(row.alias, "work");

    // PROVIDER: the shipped adapter, and the ISOLATE's one, so a link minted in
    // one request is visible to the next screen.
    assert.ok(deps.provider instanceof ComposioConnections,
      "connectWiring's catalog port is not the shipped adapter");
    assert.equal(deps.provider, connectionsFromEnv(r.env),
      "connectWiring built its own adapter instead of taking the isolate's");
    const meta = await deps.provider.toolkit(APP.slug);
    assert.equal(meta.name, APP.name, "the app's name did not come off the catalog");
    assert.ok(s.calls.some((c) => c.url === `${COMPOSIO_BASE_URL}/toolkits/${APP.slug}`),
      "connectWiring's provider never asked the catalog");

    // WORDS: the real audit. A stub returning three fixed lines passes every
    // other assertion in this check and fails this one.
    const before = s.calls.length;
    await assert.rejects(() => deps.words.sentences(SCOPELESS as never), PermissionWordsRefused,
      "connectWiring's words port invented sentences for a toolkit with no scopes");
    assert.equal(s.calls.length, before,
      "a model was asked to write permissions for a toolkit that declares none");

    assert.equal(typeof deps.onConnected, "function");
    // Left unset for the same three reasons connectDeps leaves them unset.
    assert.equal(deps.now, undefined, "connectWiring pinned the clock production owns");
    assert.equal(deps.successStatus, undefined);
    assert.equal(deps.baseUrl, undefined,
      "a baseUrl here shadows env.CONNECT_BASE_URL, and a preview whose callback URL "
        + "silently points at production is what that variable exists to prevent");
    s.restore();
  });

await check("connectWiring refuses without the vendor secret, and the CONTROL is the same rig with it",
  async () => {
    const s = socket();
    const unset = await rig({ COMPOSIO_API_KEY: undefined });
    assert.equal(connectWiring(unset.env as ConnectEnv), null,
      "connectWiring handed back deps on a Worker with no catalog, so the page it draws "
        + "cannot name the app and no link can be redeemed");
    assert.equal(s.calls.length, 0, "an unconfigured Worker still called out to the vendor");

    // THE CONTROL. One variable apart, so the null above is the missing secret
    // and not something broken in the rig.
    const set = await rig();
    assert.ok(connectWiring(set.env as ConnectEnv),
      "connectWiring refuses a Worker that has everything, so the check above proves nothing");
    s.restore();
  });

await check("connectAuthWiring — the other value src/index.ts installs — is the code half, over D1",
  async () => {
    const s = socket();
    const r = await rig();
    seedLink(r);

    const deps = connectAuthWiring(r.env);
    assert.ok(deps, "connectAuthWiring handed a configured Worker no deps, so no code is textable");

    // LINKS: the SAME connect_links table connect.ts is wired with. Two stores
    // would be two answers to "is this link still live", and one route could
    // text a code for a link the other had already spent.
    const link = await deps.links.read(r.handle);
    assert.ok(link, "connectAuthWiring's link store did not read this Worker's own table");
    assert.equal(link.user_id, OWNER);

    // CODES: the real D1 code store. Written through the port, read back out of
    // SQLite outside the code under test.
    const at = NOW;
    await deps.codes.insert({
      id: "codeaaaaaaaaaa1",
      token_handle: r.handle,
      user_id: OWNER as never,
      code_hash: "c".repeat(64),
      expires_at: at + 600_000,
      attempts: 0,
      used_at: null,
      created_at: at,
    });
    const raw = r.d1.db.prepare(
      `SELECT "id", "user_id" FROM "connect_codes" WHERE "token_handle" = ?`,
    ).all(r.handle) as { id: string; user_id: string }[];
    assert.equal(raw.length, 1,
      "connectAuthWiring's code store did not write to this Worker's connect_codes table");
    assert.equal(raw[0].user_id, OWNER);
    const newest = await deps.codes.newest(r.handle);
    assert.equal(newest?.id, "codeaaaaaaaaaa1");

    // The clock and the id mint are the tests' and production's respectively,
    // exactly as connectDeps leaves them.
    assert.equal(deps.now, undefined, "connectAuthWiring pinned the clock production owns");
    assert.equal(deps.newId, undefined);
    s.restore();
  });

await check("connectAuthWiring's app name comes from the catalog, and a blip costs only the name",
  async () => {
    const s = socket();
    const r = await rig();
    const deps = connectAuthWiring(r.env)!;

    // NO APP IS HARDCODED: the Worker has never heard of this one.
    assert.equal(await deps.toolkitName(APP.slug), APP.name,
      "the name in the text did not come off the catalog");
    assert.ok(s.calls.some((c) => c.url === `${COMPOSIO_BASE_URL}/toolkits/${APP.slug}`),
      "the catalog was never asked, so the name came from somewhere it must not come from");

    // A catalog outage costs the app's NAME in one sentence of the text, never
    // the code itself — so this port swallows rather than throws.
    s.catalogFails = true;
    assert.equal(await deps.toolkitName(APP.slug), null,
      "a catalog blip escaped as a throw, which stops somebody signing in over a display name");
    s.restore();
  });

await check("connectAuthWiring refuses without the vendor secret, and the CONTROL is the same rig with it",
  async () => {
    const s = socket();
    const unset = await rig({ COMPOSIO_API_KEY: undefined });
    assert.equal(connectAuthWiring(unset.env), null,
      "the code half is live on a Worker whose page half is not, so somebody can be texted a "
        + "code for a link no page can ever draw");
    const set = await rig();
    assert.ok(connectAuthWiring(set.env),
      "connectAuthWiring refuses a Worker that has everything, so the check above proves nothing");
    s.restore();
  });

await check("CONTROL: /c/{token}/code with NO injected deps reaches the real wiring", async () => {
  const s = socket();
  const r = await rig();
  seedLink(r);

  // The wiring is installed by loading src/index.ts, the same way the page half
  // is. A gate leg can ask this; it cannot ask whether the factory works.
  assert.equal(connectAuthWiringInstalled(), true,
    "src/index.ts does not install the connect-auth wiring, so /c/{token}/code answers 503 "
      + "for every token there has ever been");

  // NO DEPS ARGUMENT — exactly how src/index.ts calls this. A 200 here is the
  // only assertion in the repo that executes `connectAuthWiring` through the
  // route, and gutting that factory to `return null` turns it into the 503.
  const res = await connectAuthRoute(
    getReq(`/c/${r.token}/code`), r.env as unknown as ConnectAuthEnv);
  assert.ok(res, "the code route did not claim its own path");
  const html = await res.text();
  assert.equal(res.status, 200,
    `the wired Worker refused to offer a code: ${html.slice(0, 200)}`);
  assert.ok(html.includes("<form"), "the offer page has no way to ask for the code");
  assert.ok(html.includes(`/c/${r.token}/code`), "the form does not post back to this link");
  s.restore();
});

await check("CONTROL: the same request on a Worker with no vendor secret is the honest 503",
  async () => {
    const s = socket();
    const r = await rig({ COMPOSIO_API_KEY: undefined });
    seedLink(r);
    // One variable apart from the check above. This is what "not wired" looks
    // like, so the 200 above is "wired" and not "the route always answers 200".
    const res = await connectAuthRoute(
      getReq(`/c/${r.token}/code`), r.env as unknown as ConnectAuthEnv);
    assert.ok(res);
    const html = await res.text();
    assert.equal(res.status, 503, "an unconfigured Worker offered to text a code anyway");
    assert.ok(!html.includes("<form"), "an unwired Worker offered a button that cannot work");
    assert.equal(s.calls.length, 0, "an unconfigured Worker still called out to the vendor");
    s.restore();
  });

// ===========================================================================
// 7. THE ROUTER — the last piece of wiring nothing executed
//
// Everything above calls a route function directly. `src/index.ts` decides
// which requests ever REACH one, and that decision is wiring too: a branch
// removed, reordered or shadowed takes the whole feature down while every
// route function in the repo still passes its own suite. That is not
// hypothetical — measured on 2026-09-06, `GET https://api.anticipy.ai/c/<43
// chars>` answered 404 while `/api/health` answered 200, and
// test/evidence-bytes.test.ts exists because two other routes shipped written,
// correct and unrouted.
//
// So these two go through `worker.fetch`, with the real env, the real wiring
// and no injected deps: exactly what a phone and a browser get.
// ===========================================================================

const ctx = { waitUntil() {}, passThroughOnException() {} } as unknown as ExecutionContext;

await check("worker.fetch routes /me/connections to the six routes, not to the 404", async () => {
  const s = socket();
  const r = await rig();

  // SIGNED IN: 200, from the real D1 store through the real wiring. This owner
  // has connected nothing, so the list is empty — an empty list is the honest
  // answer HERE, where the store answered; it is a failure only when something
  // could not be read, and that polarity is pinned in connections-api.test.ts.
  const mine = await worker.fetch(
    new Request("https://api.anticipy.ai/me/connections",
      { headers: { Authorization: r.ownerToken } }),
    r.env as never, ctx);
  assert.notEqual(mine.status, 404,
    "the Worker does not carry /me/connections at all, so every Connected Apps screen "
      + "shows 'I couldn't read your connected apps'");
  assert.equal(mine.status, 200, `the router reached something that refused: ${mine.status}`);
  assert.deepEqual(await mine.json(), { items: [] });

  // SIGNED OUT: 401 and JSON, so the phone renders "sign in", not "we are down".
  // A 404 here would be indistinguishable from an unrouted Worker.
  const nobody = await worker.fetch(
    new Request("https://api.anticipy.ai/me/connections"), r.env as never, ctx);
  assert.equal(nobody.status, 401, "an unrouted or misrouted door answered the signed-out call");
  assert.equal(nobody.headers.get("content-type"), "application/json; charset=utf-8");
  assert.equal(s.calls.length, 0, "the vendor was asked about our own table");
  s.restore();
});

await check("worker.fetch routes /c/{token} and /c/{token}/code, and neither is a 404", async () => {
  const s = socket();
  const r = await rig();
  seedLink(r);

  // THE CODE HALF FIRST, because index.ts chains them: connectAuthRoute answers
  // null for anything that is not its own, and connect.ts keeps every path it
  // owned. A branch that stopped chaining would 404 one of these two.
  const code = await worker.fetch(
    new Request(`https://api.anticipy.ai/c/${r.token}/code`), r.env as never, ctx);
  assert.notEqual(code.status, 404,
    "the deployed shape of 2026-09-06: the Worker does not carry the /c/ prefix, so every "
      + "link Anticipy has ever texted is a dead end");
  assert.equal(code.status, 200, "the router reached something that refused to offer a code");
  assert.ok((await code.text()).includes("<form"), "the offer page has no way to ask");

  // THE PAGE HALF, signed out. 401 rather than 404: the door exists and this
  // caller has proved nothing, which is a different sentence.
  const page = await worker.fetch(
    new Request(`https://api.anticipy.ai/c/${r.token}`), r.env as never, ctx);
  assert.equal(page.status, 401, "the page half is unrouted or answers a stranger");
  const html = await page.text();
  assert.doesNotMatch(html, /zellibrix/i,
    "the app the owner is connecting was named to whoever intercepted the text");
  s.restore();
});

// ===========================================================================
// 8. NO APP IS HARDCODED — the scan the whole feature turns on
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

// ===========================================================================
// 9. THE NUDGE HALF AND THE TEXT TWIN — four defects, each reproduced first
//
// Three adversarial audits read the Connections round on 2026-09-06. These
// four are the ones that could reach a PERSON: a second text nobody asked
// for, an ask that can never stop holding, a question stamped as answered,
// and an account disconnected by coin flip. Every check below was written to
// go RED against the code as it stood, and each carries its CONTROL — the
// good case, in the same check, so a fix that buys silence by refusing
// everything cannot pass.
//
// WHY THEY LIVE HERE and not beside the rest of the twin's checks in
// connections-endtoend.test.ts: this suite owns src/connections/wiring.ts,
// and the four defects are all wiring.ts's own — the moment query, the
// executor's two branches, and the event claim.
// ===========================================================================

/** 15 lowercase alphanumerics, the shape D1 mints and the only shape the
 *  owner-id rule accepts. Its own owner, so nothing in sections 1-8 can be
 *  read by these checks or written by them. */
const TWIN_OWNER = "ownertwinaaa111";
const TWIN_PHONE = "+15557770123";
const TWIN_NOW = Date.now();
const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;

/**
 * A fixed-offset zone in which this owner's local hour right now is 14:00.
 * COMPUTED, NEVER NAMED: quiet hours are owner-local, and a hardcoded zone is
 * a suite that passes all morning and fails every evening.
 */
function awakeZone(): string {
  const utcHour = new Date(TWIN_NOW).getUTCHours();
  const offset = ((14 - utcHour) % 24 + 24) % 24;
  return offset <= 14 ? `Etc/GMT-${offset}` : `Etc/GMT+${24 - offset}`;
}

interface TwinSocket {
  calls: FetchCall[];
  /** What the vendor's catalog search answers. Empty is the shape that makes
   *  `planTextCommand` return `ask_which_app`, which is finding 2's subject. */
  search: Record<string, unknown>[];
  /** What the command judge answers. The match judge is never reached while
   *  `search` is empty, which is why there is one knob and not two. */
  command: unknown;
  restore: () => void;
}

/** The one fake: `globalThis.fetch`. Three hosts — the vendor's catalog, the
 *  carrier, and the model — and everything between this file and that socket
 *  is the shipped Worker. */
function twinSocket(): TwinSocket {
  const real = globalThis.fetch;
  const s: TwinSocket = {
    calls: [],
    search: [],
    command: { kind: "none" },
    restore: () => { globalThis.fetch = real; },
  };
  globalThis.fetch = (async (input: unknown, init?: { body?: unknown }) => {
    const url = String((input as { url?: string })?.url ?? input);
    const body = String(init?.body ?? "");
    s.calls.push({ url, body });
    const json = (status: number, value: unknown): Response =>
      new Response(JSON.stringify(value), {
        status, headers: { "content-type": "application/json" },
      });
    if (url.startsWith(COMPOSIO_BASE_URL)) {
      if (url.includes("/toolkits?search=")) return json(200, { items: s.search });
      if (url.includes("/toolkits/")) return json(200, APP);
      return json(200, {});
    }
    if (url.startsWith(SENDBLUE_BASE)) {
      return json(200, { message_handle: "mh-wiring", status: "QUEUED" });
    }
    // WHICH OF OUR OWN PROMPTS IS THIS? Matched against a string THIS REPO
    // wrote into its own system prompt, never against anything a person said.
    const answer = body.includes("list_connected") ? s.command : { kind: "unclear" };
    return json(200, { choices: [{ message: { content: JSON.stringify(answer) } }] });
  }) as typeof globalThis.fetch;
  resetConnectionsProvider();
  return s;
}

interface TwinRig { d1: FakeD1; env: NudgeWiringEnv; }

/** A Worker configured the way a deployed one is, plus the carrier the twin
 *  replies through. */
function twinRig(): TwinRig {
  const d1 = new FakeD1();
  d1.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,?,'')`,
  ).run(TWIN_OWNER, PB_NOW, PB_NOW, `${TWIN_OWNER}@anticipy-test.invalid`,
        "key-twin", TWIN_PHONE);
  d1.db.prepare(
    `INSERT INTO owner_profile (id, created, updated, owner_id, phone, name, first_name,
       last_name, email, birthday, facts, owner_ref, timezone)
     VALUES (?,?,?,?,?,'','','','','','',?,?)`,
  ).run("proftwinaaa1111", PB_NOW, PB_NOW, TWIN_OWNER, TWIN_PHONE, TWIN_OWNER, awakeZone());
  const env = {
    DB: asD1(d1),
    ANTICIPY_AUTH_SECRET: "connections-wiring-test-secret",
    COMPOSIO_API_KEY: "ck_test_not_a_real_key",
    OPENROUTER_API_KEY: "or_test_not_a_real_key",
    SENDBLUE_API_KEY_ID: "sbkid-test",
    SENDBLUE_API_SECRET_KEY: "sbsecret-test",
    SENDBLUE_FROM_NUMBER: "+15550009999",
  } as unknown as NudgeWiringEnv;
  return { d1, env };
}

function twinJob(r: TwinRig, id: string, status: string, touchedAt: number): void {
  const at = new Date(touchedAt).toISOString();
  r.d1.db.prepare(
    `INSERT INTO jobs (id, created, updated, goal, status, owner_ref)
     VALUES (?,?,?,'a small errand',?,?)`,
  ).run(id, at, at, status, TWIN_OWNER);
}

function twinSignal(
  r: TwinRig, toolkit: string, alias = "",
  over: { seenAt?: number; weight?: number } = {},
): void {
  // THE AGE IS A PARAMETER because the stored weight is not the weight: a row
  // is worth `weight * 2^(-age / 30 days)` to everything that reads it, and the
  // default here — an hour old — is the one age at which a wrong reader and a
  // right one give the same answer.
  r.d1.db.prepare(
    `INSERT INTO app_usage_signals (user_id, toolkit, source, alias, weight, last_seen_at)
     VALUES (?,?,'observer',?,?,?)`,
  ).run(TWIN_OWNER, toolkit, alias, over.weight ?? 3, over.seenAt ?? TWIN_NOW - HOUR_MS);
}

function twinConnection(
  r: TwinRig, id: string, toolkit: string, alias: string | null, status = "connected",
): void {
  r.d1.db.prepare(
    `INSERT INTO connections (connected_account_id, user_id, toolkit, alias, status,
       writes_enabled, last_used_at) VALUES (?,?,?,?,?,0,NULL)`,
  ).run(id, TWIN_OWNER, toolkit, alias ?? "", status);
}

function twinNudge(r: TwinRig, toolkit: string, over: {
  state?: string; level?: number; snooze_until?: number | null; sent_at?: number | null;
  trigger?: string | null;
} = {}): void {
  r.d1.db.prepare(
    `INSERT INTO connect_nudges (user_id, toolkit, state, level, snooze_until, trigger,
       sent_at, acted_at, channel) VALUES (?,?,?,?,?,?,?,NULL,NULL)`,
  ).run(TWIN_OWNER, toolkit, over.state ?? "never_asked", over.level ?? 0,
        over.snooze_until ?? null, over.trigger ?? null, over.sent_at ?? null);
}

const twinNudgeRow = (r: TwinRig, toolkit: string): Record<string, unknown> | undefined =>
  r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM connect_nudges WHERE user_id = ? AND toolkit = ?`, TWIN_OWNER, toolkit)[0];

const twinTexts = (s: TwinSocket): string[] =>
  s.calls.filter((c) => c.url.startsWith(SENDBLUE_BASE)).map((c) => {
    try { return String((JSON.parse(c.body) as { content?: unknown }).content ?? ""); }
    catch { return ""; }
  });

/** Run something with console.log captured, and hand back every line. The
 *  three findings below all turn on what an operator can SEE, and a log line
 *  nobody asserts is a log line that gets reworded into uselessness. */
async function withLogs<T>(fn: () => Promise<T>): Promise<{ value: T; lines: string[] }> {
  const lines: string[] = [];
  const real = console.log;
  console.log = ((...a: unknown[]) => { lines.push(a.map(String).join(" ")); }) as typeof console.log;
  try { return { value: await fn(), lines }; }
  finally { console.log = real; }
}

const WIRING_SRC = readFileSync(
  fileURLToPath(new URL("../src/connections/wiring.ts", import.meta.url)), "utf8");

/** Anchor on a literal the source carries EXACTLY ONCE, and assert the count.
 *  An anchor that matches nothing — or matches two places — has produced
 *  several false "it is tested" readings in this repo this week. */
function anchoredOnce(literal: string): void {
  assert.equal(WIRING_SRC.split(literal).length - 1, 1,
    `the anchor ${JSON.stringify(literal)} does not occur exactly once in wiring.ts, so `
      + "the check that leans on it proves nothing");
}

// ---------------------------------------------------------------------------
// FINDING 1 — the twin's own sends escaped the seven-day cap
// ---------------------------------------------------------------------------

await check("FINDING 1: a link the owner asked for is written down, so the sweep can see it",
  async () => {
    // THE DEFECT. The twin minted a link, texted it, and wrote NO
    // connect_nudges row. `sendConnectAsk` reads `connect_nudges.sent_at` for
    // the spec's "one connect ask per user per 7 days across all apps", so an
    // owner who texted "connect <app>" at 9am could be interrupted by the
    // sweep about a DIFFERENT app at 10am. The row is also what the 72-hour
    // soft-no and the decline ladder read, so without it a link nobody tapped
    // is invisible to both.
    const s = twinSocket();
    const r = twinRig();
    const before = Date.now();
    const outcome = await runTextCommandPlan(
      { kind: "connect", owner: ownerId(TWIN_OWNER), toolkit: APP.slug, appName: APP.name },
      r.env);
    assert.equal(outcome.replied, true, `the twin did not reply: ${outcome.detail}`);
    assert.equal(twinTexts(s).length, 1, "the owner got no link");

    const row = twinNudgeRow(r, APP.slug);
    assert.ok(row, "the twin texted a connect link and wrote no connect_nudges row, so the "
      + "seven-day cap, the 72-hour soft-no and the decline ladder are all blind to it");
    // AND IT SAYS `never_asked`, WHICH IS THE TRUE SENTENCE. Round 2 (section
    // 10) found the original `asked` here: that word means "we pushed a link
    // and are waiting", and 72 hours of quiet on it is a soft no. We have not
    // asked this owner about this app — they asked us. `sent_at` and the
    // trigger below are what say a link went, and who wanted it.
    assert.equal(row.state, "never_asked",
      "a link the owner asked for is recorded as an ask WE pushed, so ignoring it for three "
        + "days will be read as a decline");
    assert.ok(typeof row.sent_at === "number" && row.sent_at >= before,
      "the row carries no sent_at, which is the only column the seven-day cap reads");
    assert.equal(row.channel, "sms");
    assert.equal(row.trigger, "user_named_it",
      "the trigger must say the owner named it themselves, because that is what happened");

    // AND THE LINK IS REAL: one row in connect_links, bound to this owner.
    assert.equal(
      r.d1.rows(`SELECT * FROM connect_links WHERE user_id = ?`, TWIN_OWNER).length, 1,
      "the reply's link is not in connect_links, so it cannot redeem");
    s.restore();
  });

await check("FINDING 1 CONTROL: the twin still serves an owner the ladder has already stopped",
  async () => {
    // THE OTHER DIRECTION, and the one that matters more. The spec's own words
    // for decline level 3 are "stop asking — user must bring it up (\"connect
    // <app>\") or Settings". A recorded ask must never become a reason to
    // refuse the person's own request: the twin reads no policy at all, and
    // this is what says so.
    const s = twinSocket();
    const r = twinRig();
    twinNudge(r, APP.slug, {
      state: "declined", level: 3, snooze_until: TWIN_NOW + 3000 * DAY_MS,
      sent_at: TWIN_NOW - HOUR_MS, trigger: "in_task",
    });
    const outcome = await runTextCommandPlan(
      { kind: "connect", owner: ownerId(TWIN_OWNER), toolkit: APP.slug, appName: APP.name },
      r.env);
    assert.equal(outcome.replied, true,
      `a level-3 decline stopped the owner's OWN request: ${outcome.detail}`);
    assert.equal(twinTexts(s).length, 1, "the owner asked for a link and did not get one");

    // AND THE DECLINE IS NOT ERASED. The level and the snooze the ladder
    // earned survive; only the ask half of the row is rewritten.
    const row = twinNudgeRow(r, APP.slug);
    assert.equal(row?.level, 3, "the solicited link reset the decline ladder to zero");
    // AND THE WORD `declined` SURVIVES TOO, not just the number. routes/
    // connect.ts `recordSkip` reads this exact state to recognise a tap it has
    // already counted ("a refresh, a double tap or a retried POST must not walk
    // somebody from ask me in a fortnight to never ask me again"); a solicited
    // link that rewrote it would hand that guard a row it cannot recognise.
    assert.equal(row?.state, "declined",
      "a link the owner asked for erased the state their own three declines earned");
    assert.ok(typeof row?.snooze_until === "number" && row.snooze_until > TWIN_NOW,
      "the snooze the ladder earned was dropped");
    s.restore();
  });

await check("FINDING 1: a solicited link never retires the weekly reconnect cadence", async () => {
  // `needs_reconnect` is not a rung on the decline ladder — it is a live
  // connection that broke — and stamping it `asked` would quietly end the
  // spec's "one gentle ask, then weekly max" (page 24) for a connection this
  // owner already chose once. The row keeps its state and gains the timestamp,
  // which is the true statement: the reconnect WAS raised, just now.
  const s = twinSocket();
  const r = twinRig();
  twinNudge(r, APP.slug, { state: "needs_reconnect", sent_at: TWIN_NOW - 30 * DAY_MS });
  const outcome = await runTextCommandPlan(
    { kind: "connect", owner: ownerId(TWIN_OWNER), toolkit: APP.slug, appName: APP.name },
    r.env);
  assert.equal(outcome.replied, true, outcome.detail);
  const row = twinNudgeRow(r, APP.slug);
  assert.equal(row?.state, "needs_reconnect",
    "a repair link the owner asked for turned a broken connection into an ordinary ask, "
      + "and the weekly reconnect cadence stopped");
  assert.ok(typeof row?.sent_at === "number" && row.sent_at > TWIN_NOW - DAY_MS,
    "the reconnect was raised and the row does not say when");
  s.restore();
});

await check("FINDING 1: a reply that never went out spends nothing", async () => {
  // The row is written AFTER the send, not before, and this is the reason: a
  // carrier failure must not leave an owner holding a decline for a link they
  // were never given. `sendConnectAsk` takes the lease first because an
  // unwritten SWEEP ask gets re-sent; here the failure direction is reversed.
  const s = twinSocket();
  const r = twinRig();
  const real = globalThis.fetch;
  globalThis.fetch = (async (input: unknown, init?: { body?: unknown }) => {
    const url = String((input as { url?: string })?.url ?? input);
    if (url.startsWith(SENDBLUE_BASE)) {
      return new Response(JSON.stringify({ error_code: 400 }), { status: 500 });
    }
    return real(input as never, init as never);
  }) as typeof globalThis.fetch;
  const outcome = await runTextCommandPlan(
    { kind: "connect", owner: ownerId(TWIN_OWNER), toolkit: APP.slug, appName: APP.name },
    r.env);
  globalThis.fetch = real;
  assert.equal(outcome.replied, false, "the carrier refused and the twin thought it replied");
  assert.equal(twinNudgeRow(r, APP.slug), undefined,
    "a text that never left the building spent this owner's weekly interruption and "
      + "started a 72-hour decline clock against them");
  s.restore();
});

// ---------------------------------------------------------------------------
// FINDING 2 — a clarifying question stamped as handled
// ---------------------------------------------------------------------------

await check("FINDING 2: a question the twin asked is not stamped 'ignore'", async () => {
  // THE DEFECT. `if (outcome.replied) await claimEvent(...)` stamped
  // decision='ignore' for EVERY reply, including `ask_which_app` — the one
  // plan whose whole purpose is to be answered. 'ignore' is the brain's own
  // word for "nothing further is needed for this line", and that is false of
  // a line the product has just asked a question about.
  const s = twinSocket();
  s.command = { kind: "command", command: "connect_app" };
  const r = twinRig();
  r.d1.db.prepare(
    `INSERT INTO events (id, created, updated, device_id, kind, text, speaker, owner_ref)
     VALUES (?,?,?,'phone','sms_reply',?,'owner',?)`,
  ).run("evtwinaaaaaaa01", PB_NOW, PB_NOW, "set up that thing for me", TWIN_OWNER);

  const outcome = await handleInboundText(
    r.env, TWIN_OWNER, "set up that thing for me", "evtwinaaaaaaa01");
  assert.equal(outcome.kind, "ask_which_app",
    `the fixture did not produce the plan under test: ${outcome.kind} (${outcome.detail})`);
  assert.equal(outcome.replied, true, "the twin asked nothing");
  assert.equal(twinTexts(s)[0], TEXT_REPLY.whichApp);

  const row = r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM events WHERE id = 'evtwinaaaaaaa01'`)[0];
  assert.notEqual(row.decision, "ignore",
    "the twin asked the owner a question and stamped their message 'ignore' — the row "
      + "says handled while the product is still waiting for the answer");
  // 'ask' is the brain's own vocabulary for this row's decision column
  // (schema.sql: ignore|act|ask), and it is the true one here.
  assert.equal(row.decision, "ask");
  s.restore();
});

await check("FINDING 2 CONTROL: an answered message is still claimed, so nobody is texted twice",
  async () => {
    // The claim must not be lost in the fix. brain/worker.py `fetch_unprocessed`
    // polls `kind="sms_reply" && decision=""`, so a row left blank is answered
    // a second time by a brain that knows nothing about connections.
    const s = twinSocket();
    s.command = { kind: "command", command: "list_connected" };
    const r = twinRig();
    r.d1.db.prepare(
      `INSERT INTO events (id, created, updated, device_id, kind, text, speaker, owner_ref)
       VALUES (?,?,?,'phone','sms_reply',?,'owner',?)`,
    ).run("evtwinaaaaaaa02", PB_NOW, PB_NOW, "what have I got set up", TWIN_OWNER);

    const outcome = await handleInboundText(
      r.env, TWIN_OWNER, "what have I got set up", "evtwinaaaaaaa02");
    assert.equal(outcome.kind, "list_connections", outcome.detail);
    assert.equal(outcome.replied, true);
    const row = r.d1.rows<Record<string, unknown>>(
      `SELECT * FROM events WHERE id = 'evtwinaaaaaaa02'`)[0];
    assert.equal(row.decision, "ignore",
      "a message the twin fully answered was left unclaimed, so the brain answers it too "
        + "and one text gets two replies");
    s.restore();
  });

// ---------------------------------------------------------------------------
// FINDING 3 — a stranded job held the ask forever
// ---------------------------------------------------------------------------

await check("FINDING 3: a job nobody has touched in months no longer holds the ask", async () => {
  // THE DEFECT. `taskInFlight` counted every jobs row not done/failed/
  // cancelled, over ALL TIME with no age bound — and `resultDelivered` reads
  // the same count — so ONE stranded row silenced this owner's connect ask
  // for the rest of their life, and the hold read exactly like a healthy busy
  // moment in the log.
  const s = twinSocket();
  const r = twinRig();
  twinSignal(r, APP.slug);
  twinJob(r, "jobtwindone001", "done", TWIN_NOW - HOUR_MS);
  twinJob(r, "jobtwinstuck01", "running", TWIN_NOW - 200 * DAY_MS);

  const { value: moment, lines } = await withLogs(() =>
    nudgeMomentFor(r.env)(ownerId(TWIN_OWNER), APP.slug, "in_task", TWIN_NOW));
  assert.ok(moment, "the moment could not be established at all");
  assert.equal(moment.taskInFlight, false,
    "a job stranded since two hundred days ago still reads as a step in progress, so this "
      + "owner can never be asked anything again");
  assert.equal(moment.resultDelivered, true,
    "the same stranded row also holds `resultDelivered` false forever, so bounding only "
      + "taskInFlight would leave the ask held by the second floor");

  // AND THE LOG SAYS WHICH IT IS. "busy right now" and "stuck since March"
  // were the same sentence, which is why nobody found this for a month.
  const said = lines.join("\n");
  assert.ok(said.includes("stranded, holding nothing"),
    `the log does not name the stranded rows: ${said}`);
  assert.ok(said.includes("not touched since 20"),
    `the log does not say since when, which is the whole difference: ${said}`);
  anchoredOnce("stranded, holding nothing");
  s.restore();
});

await check("FINDING 3 CONTROL: a job running right now still holds the ask, and says so",
  async () => {
    // The floor the bound must not remove: "an ask must never land mid-step".
    const s = twinSocket();
    const r = twinRig();
    twinSignal(r, APP.slug);
    twinJob(r, "jobtwindone002", "done", TWIN_NOW - HOUR_MS);
    twinJob(r, "jobtwinbusy001", "running", TWIN_NOW - HOUR_MS);

    const { value: moment, lines } = await withLogs(() =>
      nudgeMomentFor(r.env)(ownerId(TWIN_OWNER), APP.slug, "in_task", TWIN_NOW));
    assert.equal(moment?.taskInFlight, true,
      "a job that moved an hour ago read as stranded — the bound is wrong in the one "
        + "direction that texts somebody mid-errand");
    assert.equal(moment?.resultDelivered, false);
    const said = lines.join("\n");
    assert.ok(said.includes("busy now, the ask holds"),
      `the log does not say the owner is genuinely busy: ${said}`);
    anchoredOnce("busy now, the ask holds");
    s.restore();
  });

await check("FINDING 3: an owner with nothing open is not logged about at all", async () => {
  // A line per candidate per tick about nothing is how a log stops being read.
  const s = twinSocket();
  const r = twinRig();
  twinSignal(r, APP.slug);
  twinJob(r, "jobtwindone003", "done", TWIN_NOW - HOUR_MS);
  const { value: moment, lines } = await withLogs(() =>
    nudgeMomentFor(r.env)(ownerId(TWIN_OWNER), APP.slug, "in_task", TWIN_NOW));
  assert.equal(moment?.taskInFlight, false);
  assert.deepEqual(lines.filter((l) => l.includes("the ask holds")), []);
  s.restore();
});

// ---------------------------------------------------------------------------
// FINDING 4 — the account picked by row order
// ---------------------------------------------------------------------------

await check("FINDING 4: two accounts and no alias is a question, never a coin flip", async () => {
  // THE DEFECT. `rows.find((r) => r.alias === plan.alias) ?? rows[0]` labelled
  // whichever row D1 happened to return first. That row is the one the router
  // then uses for everything the owner calls "work" — a real mailbox, chosen
  // by row order.
  const s = twinSocket();
  const r = twinRig();
  twinConnection(r, "ca_twin_one", APP.slug, null);
  twinConnection(r, "ca_twin_two", APP.slug, null);

  const outcome = await runTextCommandPlan(
    { kind: "choose_account", owner: ownerId(TWIN_OWNER), toolkit: APP.slug,
      appName: APP.name, alias: "work" },
    r.env);
  assert.equal(outcome.replied, true, `the twin said nothing at all: ${outcome.detail}`);

  const labelled = r.d1.rows<Record<string, unknown>>(
    `SELECT * FROM connections WHERE user_id = ? AND alias = 'work'`, TWIN_OWNER);
  assert.deepEqual(labelled, [],
    "one of two indistinguishable accounts was labelled 'work' by row order, and the "
      + "router will now send this owner's work mail from whichever one D1 listed first");
  assert.equal(twinTexts(s)[0], TEXT_REPLY.whichAccount(APP.name),
    "ambiguity must ASK. Silence and a guess are the two wrong answers");
  s.restore();
});

await check("FINDING 4 CONTROL: one account, or a named one, is still labelled at once",
  async () => {
    // The good case, twice, because a refusal that refuses everything is not a
    // fix. ONE account is unambiguous — "use my work <app>" says that this is
    // the work one. And an account already carrying the alias is the row the
    // owner named, whatever else is beside it.
    const s = twinSocket();
    const only = twinRig();
    twinConnection(only, "ca_twin_solo", APP.slug, null);
    const first = await runTextCommandPlan(
      { kind: "choose_account", owner: ownerId(TWIN_OWNER), toolkit: APP.slug,
        appName: APP.name, alias: "work" },
      only.env);
    assert.equal(first.replied, true, first.detail);
    assert.equal(
      only.d1.rows(`SELECT * FROM connections WHERE user_id = ? AND alias = 'work'`,
        TWIN_OWNER).length,
      1, "an owner with exactly one account was asked which one they meant");
    assert.equal(twinTexts(s)[0], TEXT_REPLY.accountSet(APP.name, "work"));

    const named = twinRig();
    twinConnection(named, "ca_twin_work", APP.slug, "work");
    twinConnection(named, "ca_twin_home", APP.slug, "personal");
    const second = await runTextCommandPlan(
      { kind: "choose_account", owner: ownerId(TWIN_OWNER), toolkit: APP.slug,
        appName: APP.name, alias: "work" },
      named.env);
    assert.equal(second.replied, true, second.detail);
    const rows = named.d1.rows<Record<string, unknown>>(
      `SELECT * FROM connections WHERE user_id = ? AND alias = 'work'`, TWIN_OWNER);
    assert.equal(rows.length, 1, "the row the owner named was not the one that was kept");
    assert.equal(rows[0].connected_account_id, "ca_twin_work");
    s.restore();
  });

await check("FINDING 4: the question the twin asks about an account clears words.ts", () => {
  // It is a sentence this repo signs, so it goes through the same audit every
  // other one does — and it is added to `textReplySentences`, which is what
  // connections-endtoend.test.ts scans, so it cannot be forgotten there.
  const lines = textReplySentences(APP.name, "https://api.anticipy.ai/c/x");
  assert.ok(lines.includes(TEXT_REPLY.whichAccount(APP.name)),
    "the new sentence is not in the audit list, so no suite scans it");
  for (const line of [TEXT_REPLY.whichAccount(APP.name)]) {
    assert.equal(forbiddenTermIn(line), null, `the account question carries: ${line}`);
    assert.ok(!line.includes("!"), "the account question shouts");
    assert.ok(line.length <= 320, "the account question is longer than one text");
  }
});

// ---------------------------------------------------------------------------
// SECTION 10 — ROUND 2: what the row the twin writes actually MEANS
//
// Section 9 closed the hole where the twin wrote no row at all. It closed it by
// writing the row every sweep ask writes — `state: 'asked'` — and that is a
// sentence about a different fact. `asked` means "we put a connect link in
// front of this person and are waiting"; 72 hours of silence on it is a soft
// no, and the ladder advances. A link somebody TEXTED US FOR and did not
// finish that week is not a no about anything.
//
// Both checks below drive the real `runTextCommandPlan` over the real D1 store
// and then hand the row it wrote to the real policy. The CONTROL differs from
// the row under test in exactly ONE field — the one the fix changes — so what
// is measured is that field and nothing else.
// ---------------------------------------------------------------------------

/** The row the twin wrote, read back through the shipped store rather than as
 *  a raw SQLite record: what the policy sees is what is asserted. */
async function twinNudgeOf(r: TwinRig, toolkit: string): Promise<ConnectNudge> {
  const row = await createD1Store(r.env as never).readNudge(TWIN_OWNER, toolkit);
  assert.ok(row, "the twin wrote no connect_nudges row at all");
  return row;
}

/** A well-evidenced, post-result, wide-awake moment — the one shape the policy
 *  is allowed to send in. Everything under test below is therefore the row, not
 *  the moment. */
function twinCtx(over: Partial<NudgeContext> = {}): NudgeContext {
  return {
    now: TWIN_NOW,
    trigger: "in_task",
    localHour: 14,
    taskInFlight: false,
    resultDelivered: true,
    tasksThatWouldHaveUsedIt: 3,
    lastAskAnyAppAt: null,
    ...over,
  };
}

await check("ROUND 2 FINDING 2: an unfinished link the owner asked for is not a decline",
  async () => {
    // THE DEFECT. Somebody texts "connect zellibrix", gets the link, and does
    // not finish it that week. `recordSolicitedAsk` wrote `state: 'asked'`, so
    // 72 hours later `maturedBySilence` reads their own errand as a soft no,
    // stamps decline level 1 and snoozes the next REAL moment for a fortnight.
    // The 72-hour rule exists so we "do not re-send into a void" (page 24). A
    // person who texted us is not a void.
    const s = twinSocket();
    const r = twinRig();
    const outcome = await runTextCommandPlan(
      { kind: "connect", owner: ownerId(TWIN_OWNER), toolkit: APP.slug, appName: APP.name },
      r.env);
    assert.equal(outcome.replied, true, `the twin did not reply: ${outcome.detail}`);
    assert.equal(twinTexts(s).length, 1, "the owner got no link");

    const row = await twinNudgeOf(r, APP.slug);
    assert.ok(typeof row.sent_at === "number", "the row carries no sent_at to age");
    // Three days and an hour of silence — past the soft-no line by an hour.
    const later = row.sent_at + (SILENCE_IS_A_SOFT_NO_HOURS + 1) * HOUR_MS;

    const aged = maturedBySilence(row, later);
    assert.equal(aged.level, 0,
      "an errand the owner asked for and did not finish advanced the decline ladder to "
        + `level ${aged.level}`);
    assert.equal(aged.state, row.state, "silence rewrote the state of a link the owner asked for");
    assert.equal(aged.snooze_until, null,
      "an unfinished errand snoozed this owner's next real moment");

    // AND THE POLICY AGREES, which is the half that reaches a person: a real
    // in-task moment for this app, three days later, is not fenced off by a
    // decline nobody made.
    const verdict = shouldAsk(aged, twinCtx({ now: later, lastAskAnyAppAt: null }),
                              { owner: ownerId(TWIN_OWNER), toolkit: APP.slug });
    assert.equal(verdict.decision, "ask",
      `a real moment three days later was refused: ${verdict.reason}`);

    // THE CONTROL, and it differs from the row above in ONE FIELD. A link the
    // product PUSHED — `state: 'asked'`, which is what `sendConnectAsk` writes
    // — must still mature into a soft no, or the 72-hour rule is gone.
    const pushed = maturedBySilence({ ...row, state: "asked" }, later);
    assert.equal(pushed.state, "declined",
      "silence on a link WE pushed no longer counts as a soft no");
    assert.equal(pushed.level, 1);
    assert.equal(pushed.snooze_until, later - HOUR_MS + SNOOZE_DAYS[1] * DAY_MS,
      "the pushed ask's snooze does not start when the silence matured");
    s.restore();
  });

await check("ROUND 2 FINDING 2: asking for a link ANSWERS the push that was already out",
  async () => {
    // THE OTHER HALF OF THE SAME DEFECT, and the one a fresh owner cannot show.
    // We pushed a link for this app two hours ago, so the row says `asked` and
    // its 72-hour clock is running. The owner then TEXTS for the link — which
    // is them answering, in the only direction that matters. If the twin
    // carries `asked` through, the clock simply restarts and matures three days
    // later into a decline nobody made; the push is no longer outstanding, and
    // the row has to stop saying that it is.
    const s = twinSocket();
    const r = twinRig();
    twinNudge(r, APP.slug, { state: "asked", sent_at: TWIN_NOW - 2 * HOUR_MS,
                             trigger: "in_task" });
    const outcome = await runTextCommandPlan(
      { kind: "connect", owner: ownerId(TWIN_OWNER), toolkit: APP.slug, appName: APP.name },
      r.env);
    assert.equal(outcome.replied, true, `the twin did not reply: ${outcome.detail}`);

    const row = await twinNudgeOf(r, APP.slug);
    assert.equal(row.state, "never_asked",
      "the push we had out is still recorded as outstanding, so the owner answering it will "
        + "mature into a decline three days from now");
    assert.equal(row.level, 0, "the ladder moved");

    const aged = maturedBySilence(row, (row.sent_at as number) + (SILENCE_IS_A_SOFT_NO_HOURS + 1) * HOUR_MS);
    assert.equal(aged.level, 0,
      "answering our push by asking for the link was recorded as declining it");
    assert.equal(aged.snooze_until, null);
    s.restore();
  });

await check("ROUND 2 FINDING 3: a link the owner asked for DOES spend the weekly budget",
  async () => {
    // THE DECISION, made deliberately and stated here so the next reader does
    // not have to infer it from a column. See `recordSolicitedAsk` in
    // src/connections/wiring.ts for the reasoning; this is the executable half.
    //
    //   SPENDS THE 7-DAY BUDGET: every connect link that reaches this owner's
    //   phone, whoever asked for it. One link is one decision to make, and the
    //   cap is a promise about the person's attention, not about our intent.
    //
    //   DOES NOT ENTER THE DECLINE LADDER: only links the product pushed. The
    //   ladder measures whether we are welcome; a link somebody requested says
    //   we are.
    //
    // The cost of the first half is real and is the reason this check names it:
    // for one week after texting "connect <app>", even a laptop-closed moment
    // (score 1.0, the strongest trigger in the product) is held. That is the
    // cap working — it is the same week any pushed ask would have spent.
    const s = twinSocket();
    const r = twinRig();
    await runTextCommandPlan(
      { kind: "connect", owner: ownerId(TWIN_OWNER), toolkit: APP.slug, appName: APP.name },
      r.env);
    const row = await twinNudgeOf(r, APP.slug);
    assert.ok(typeof row.sent_at === "number",
      "the solicited link left no sent_at, which is the only column the 7-day cap reads");

    // A DIFFERENT app, the strongest moment there is, one day later.
    const other = { ...row, toolkit: "otherapp", state: "never_asked" as const,
                    level: 0 as const, snooze_until: null, trigger: null, sent_at: null };
    const held = shouldAsk(
      other,
      twinCtx({ now: row.sent_at + DAY_MS, trigger: "laptop_closed", lastAskAnyAppAt: row.sent_at }),
      { owner: ownerId(TWIN_OWNER), toolkit: "otherapp" });
    assert.equal(held.decision, "hold",
      "a solicited link spent nothing, so the sweep may interrupt this owner again this week");
    assert.match(held.reason, /across all apps/);

    // AND IT IS A WEEK, not forever: the same moment on day 8 goes through.
    const later = shouldAsk(
      other,
      twinCtx({
        now: row.sent_at + (GLOBAL_ASK_INTERVAL_DAYS + 1) * DAY_MS,
        trigger: "laptop_closed",
        lastAskAnyAppAt: row.sent_at,
      }),
      { owner: ownerId(TWIN_OWNER), toolkit: "otherapp" });
    assert.equal(later.decision, "ask", `day 8 was still held: ${later.reason}`);
    s.restore();
  });

// ===========================================================================
// 11. FINDING 5 — the aliveness test due.ts deleted was still one file over
// ============================================================================
// THE DEFECT. `nudgeMomentFor`'s evidence query carried `AND "weight" > 0` —
// the exact predicate src/connections/due.ts deleted on 2026-09-06 as "an
// aliveness test no code path can make false". signals.ts decays on READ and
// the stored column only ever RISES, so `weight > 0` was true for a row nobody
// had refreshed in four hundred days, and `tasksThatWouldHaveUsedIt` — the
// spec's own bar, "we do not ask about an app on a hunch" — counted it.
//
// The fix was applied in one of the two places that had it. This is the other,
// and it goes through the SAME seam: `decayedWeight` from signals.ts and
// `ALIVE_WEIGHT_FLOOR` from due.ts, imported rather than re-derived, so the
// boundary is stated once and the two files cannot disagree about who is alive.

await check("FINDING 5: a signal nobody has refreshed in a year is not evidence", async () => {
  const s = twinSocket();
  const r = twinRig();
  // FOUR HUNDRED DAYS, which is thirteen half-lives: this row is worth about a
  // ten-thousandth of what it was stored at, and due.ts's own candidate query
  // would never hand this owner to the policy at all.
  twinSignal(r, APP.slug, "", { seenAt: TWIN_NOW - 400 * DAY_MS });
  twinJob(r, "jobtwindone010", "done", TWIN_NOW - HOUR_MS);

  const moment = await nudgeMomentFor(r.env)(
    ownerId(TWIN_OWNER), APP.slug, "in_task", TWIN_NOW);
  assert.ok(moment, "the moment could not be established at all");
  assert.equal(moment.tasksThatWouldHaveUsedIt, 0,
    "an app this owner has not touched in over a year still counts as a task that would "
      + "have used it, so the spec's one evidence bar passes on a corpse and somebody gets "
      + "a text about an app they stopped using last spring");
  anchoredOnce("return alive > ALIVE_WEIGHT_FLOOR;");
  s.restore();
});

await check("FINDING 5 CONTROL: the same row, fresh, is still evidence", async () => {
  // The floor must not have eaten the feature. Same weight, same source, same
  // owner — only the age differs, which is the whole of what decay is.
  const s = twinSocket();
  const r = twinRig();
  twinSignal(r, APP.slug, "", { seenAt: TWIN_NOW - 2 * DAY_MS });
  twinJob(r, "jobtwindone011", "done", TWIN_NOW - HOUR_MS);

  const moment = await nudgeMomentFor(r.env)(
    ownerId(TWIN_OWNER), APP.slug, "in_task", TWIN_NOW);
  assert.equal(moment?.tasksThatWouldHaveUsedIt, 1,
    "a browser run two days ago no longer counts as evidence — the floor is eating live "
      + "signals, which is the direction that asks nobody anything ever again");
  s.restore();
});

await check("FINDING 5: a dead row's account label does not name the connection", async () => {
  // `alias` is read off the same rows, and it becomes the account a connection
  // is BOUND to. An alias carried by evidence too stale to justify the ask is
  // the wrong mailbox chosen by a row nobody has touched in a year.
  const s = twinSocket();
  const r = twinRig();
  twinSignal(r, APP.slug, "work", { seenAt: TWIN_NOW - 400 * DAY_MS });
  twinJob(r, "jobtwindone012", "done", TWIN_NOW - HOUR_MS);

  const moment = await nudgeMomentFor(r.env)(
    ownerId(TWIN_OWNER), APP.slug, "in_task", TWIN_NOW);
  assert.equal(moment?.alias, null,
    "a dead signal still names the account the ask would bind, so the row that decides "
      + "which real mailbox this is has not been touched since last spring");

  // THE CONTROL, so the null above is the AGE and not the alias being dropped.
  const fresh = twinRig();
  twinSignal(fresh, APP.slug, "work", { seenAt: TWIN_NOW - 2 * DAY_MS });
  twinJob(fresh, "jobtwindone013", "done", TWIN_NOW - HOUR_MS);
  const live = await nudgeMomentFor(fresh.env)(
    ownerId(TWIN_OWNER), APP.slug, "in_task", TWIN_NOW);
  assert.equal(live?.alias, "work", "a live signal's account label was dropped too");
  s.restore();
});

await check("FINDING 5: a row whose weight is not a number is not evidence", async () => {
  // A hand-written row or a bad backfill. SQLite's REAL affinity keeps a text
  // weight as text and `CHECK ("weight" >= 0)` accepts it, so the database is
  // not the guard here. The seam is: `decayedWeight` answers 0 for a weight it
  // cannot read, and 0 is under the floor. This file adds no second opinion
  // about that — it just must not wave the row through.
  const s = twinSocket();
  const r = twinRig();
  r.d1.db.prepare(
    `INSERT INTO app_usage_signals (user_id, toolkit, source, alias, weight, last_seen_at)
     VALUES (?,?,'observer','','not-a-number',?)`,
  ).run(TWIN_OWNER, APP.slug, TWIN_NOW - HOUR_MS);
  twinJob(r, "jobtwindone014", "done", TWIN_NOW - HOUR_MS);

  const moment = await nudgeMomentFor(r.env)(
    ownerId(TWIN_OWNER), APP.slug, "in_task", TWIN_NOW);
  assert.equal(moment?.tasksThatWouldHaveUsedIt, 0,
    "a row carrying a weight nothing can read counted as a task that would have used "
      + "the app, so one malformed row is enough to justify texting somebody");
  s.restore();
});

await check("FINDING 5: the floor is due.ts's, imported, and there is only one of it", () => {
  // ONE DEFINITION, and this is what "the same seam" means in a diff rather
  // than in a sentence. wiring.ts states no number of its own: it imports the
  // boundary from due.ts and the arithmetic from signals.ts, so retuning the
  // half-life moves both readers at once. A second copy here is how the two
  // files came to disagree in the first place.
  // IMPORTED, AND NOT MERELY MENTIONED. A mutation that typed
  // `const ALIVE_WEIGHT_FLOOR = 0.00625` here instead of importing it survived
  // the first draft of this check, which only asked whether the name appeared.
  // The number is derived in due.ts from signals.ts's own half-life; a copy of
  // its VALUE stops moving the day either is retuned, which is precisely how
  // this file and due.ts came to disagree about `weight > 0`.
  assert.match(WIRING_SRC, /import \{[^}]*\bALIVE_WEIGHT_FLOOR\b[^}]*\} from "\.\/due\.ts";/,
    "wiring.ts does not import due.ts's floor, so it is deciding aliveness itself");
  assert.match(WIRING_SRC,
    /import \{[^}]*\bdecayedWeight\b[^}]*\} from "\.\/signals\.ts";/,
    "wiring.ts does not use signals.ts's decay, so it has a second opinion about age");
  for (const name of ["ALIVE_WEIGHT_FLOOR", "DEFAULT_HALF_LIFE_MS", "SOURCE_DECAYS"]) {
    assert.equal(new RegExp(`(?:const|let|function)\\s+${name}\\b`).test(WIRING_SRC), false,
      `wiring.ts declares its own ${name}, which is a second definition of alive`);
  }
  // AND THE PREDICATE IS READ OUT OF THE STATEMENT, not grepped for in the
  // file. This check's first draft scanned WIRING_SRC and failed on the COMMENT
  // above the fixed query, which quotes the predicate it deleted — the same
  // shape that let overnight/is_connect_live.py's copy of due.ts's query drift
  // for a round while a whole-file substring check called it agreement.
  assert.equal(WIRING_SRC.split('FROM "app_usage_signals"').length - 1, 1,
    "there is more than one read of app_usage_signals in wiring.ts, so slicing to the "
      + "first one proves nothing about the other");
  const read = WIRING_SRC.split('FROM "app_usage_signals"')[1] ?? "";
  const statement = read.slice(0, read.indexOf("`"));
  assert.equal(/"weight"\s*(?:<=|>=|<>|=|<|>)/.test(statement), false,
    `the weight predicate is back in the evidence query — it is true for every row that `
      + `has ever existed, because the stored column only ever rises: ${statement}`);
});

console.log(`connections-wiring: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
