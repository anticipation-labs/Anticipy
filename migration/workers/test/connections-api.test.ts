/**
 * test/connections-api.test.ts — the six /me/connections routes, driven as HTTP.
 *
 *   node --experimental-strip-types migration/workers/test/connections-api.test.ts
 *
 * WHAT IS REAL HERE AND WHAT IS NOT. The handler, the routing, the method
 * table, the token check, the status codes and every guard are the shipped
 * code. So is the STORE: `createD1Store` over a real SQLite loaded verbatim
 * from migration/d1/schema.sql, so `connections` and `connect_links` behave
 * with their real CHECKs, their real primary keys and the real cross-owner
 * predicate on the upsert. So is the account token — a real HMAC-signed one
 * from src/pb/auth.ts against a real `owners` row — so "signed in" here means
 * what it means in production and a stranger's token is a stranger's token
 * rather than a string a fake believed. So is `mintConnectLink`, which writes
 * the real row through the real store.
 *
 * Two ports are fakes because they are other modules: the vendor client and the
 * model that writes the permission sentences. Both are fakes with LOGS, so
 * "the vendor was never asked" is a measured fact and not an assumption.
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH, each with its own checks below:
 *
 *   THE WRONG PERSON. One operator's mailbox served everybody once already. The
 *   owner comes from the token and from nowhere else, so every route is driven
 *   with a body naming a second owner and the effect is measured against the
 *   database: a foreign `connected_account_id` in a write batch, a foreign one
 *   in a disconnect, a `user_id` on a link body, a stranger's whole session.
 *
 *   THE CONFIDENT EMPTY. `{ "items": [] }` to somebody with two connected apps
 *   is worse than an error: the screen paints a clean empty state and invites
 *   them to connect what they already have. Every route that can fail is failed
 *   on purpose and the body is checked for the ABSENCE of a list.
 *
 *   THE CLAIMED REVOKE. `revoked` is the only thing that licenses the word
 *   "revoked" on the phone. Every path where the far end did not confirm one is
 *   driven and the flag is checked false — including the one where our own row
 *   went and the vendor's did not.
 *
 *   THE CONTRACT DRIFT. The six paths and the two query names are read out of
 *   ConnectedAppsClient.swift's own source and compared to this Worker's, so a
 *   route renamed on either side is red here rather than 404 on a phone.
 *
 *   THE REGISTER. Every body every check produces is collected and scanned
 *   against words.ts's own FORBIDDEN_TERMS at the end of the file.
 *
 * TWENTY MUTATIONS were run against src/routes/connections_api.ts on
 * 2026-09-06, each anchored on a literal occurring EXACTLY ONCE in that file
 * (the script refuses to patch otherwise, because a regex that silently fails
 * to match produces a false "it is tested" reading). Nineteen went red on the
 * first run; ONE SURVIVED — dropping the owner-row-id shape check — and the
 * check that now kills it was written because of that, not before it. The
 * full report, with the check each mutation killed, is at the bottom of this
 * file.
 *
 * TWELVE MORE were run on 2026-09-06 when `?q=` stopped being a permanent 503
 * and was wired to a real catalog search (numbers 26-37 below). ONE SURVIVED —
 * a budget refusal that recorded its own attempt, which turns an hour of
 * cooldown into a permanent one for whoever keeps tapping — and the window
 * check was rewritten to keep tapping for exactly that reason.
 *
 * FIVE MORE on 2026-09-06 for `/skip`, the leg that lets a person say no. All
 * five went red, and the check that killed each is named:
 *
 *   skip accepting GET ................. a skip RECORDS the decline
 *   every skip claiming the setup card . a skip RECORDS the decline (7 not 14)
 *   a malformed `onboarding` guessed at  an onboarding flag that is not a
 *                                        boolean is a 400
 *   the body allowed to name the owner . a stranger cannot decline on somebody
 *                                        else's behalf
 *   a failed write answering ok:true ... a database that cannot write the
 *                                        decline says so
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import { createD1Store, forgetLiveColumns, type StoredConnection } from "../src/connections/store.ts";
import {
  ComposioConnections, connectionsFromEnv, resetConnectionsProvider, COMPOSIO_BASE_URL,
} from "../src/connections/provider.ts";
import { DEFAULT_CONNECT_MODEL } from "../src/connections/wiring.ts";
import { OPENROUTER_BASE } from "../src/llm.ts";
import { FORBIDDEN_TERMS, PermissionWordsRefused } from "../src/connections/words.ts";
import { LINK_TTL_MS } from "../src/connections/nudge.ts";
import { CONNECT_URL_BASE, MAX_PAGE_APPS, TOKEN_CHARS } from "../src/routes/connect.ts";
import { MAX_SEARCH_RESULTS } from "../src/connections/provider.ts";
import {
  connectionsApiRoute,
  parseConnectionsApiPath,
  CONNECTIONS_API_ROUTES,
  QUERY_SEARCH,
  QUERY_SLUGS,
  MAX_LINKS_PER_OWNER,
  LINK_WINDOW_MS,
  MAX_CATALOG_SLUGS,
  MAX_SIGNAL_APPS,
  MAX_WRITE_ROWS,
  MAX_SEARCHES_PER_OWNER,
  SEARCH_WINDOW_MS,
  connectionsApiDeps,
  resetSearchBudget,
  type ConnectionsApiDeps,
  type ConnectionsApiEnv,
} from "../src/routes/connections_api.ts";

const here = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(here, "..", "src", "routes", "connections_api.ts"), "utf8");
const WIRING_SOURCE = readFileSync(join(here, "..", "src", "connections", "wiring.ts"), "utf8");
const CLIENT_SWIFT = readFileSync(
  join(here, "..", "..", "..", "app", "ios", "Anticipy", "Backend", "ConnectedAppsClient.swift"),
  "utf8",
);

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

/** Every body every check produces, for the register scan at the end. */
const BODIES: { where: string; text: string }[] = [];
async function bodyOf(res: Response, where: string): Promise<string> {
  const text = await res.text();
  BODIES.push({ where, text });
  return text;
}
async function jsonOf(res: Response, where: string): Promise<Record<string, unknown>> {
  const text = await bodyOf(res, where);
  if (text === "") return {};
  return JSON.parse(text) as Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const NOW = 1_757_000_000_000;          // a fixed instant; every check owns time
const PB_NOW = "2026-09-05 12:00:00.000Z";
const OWNER = "ownerrefaaaaaa1";        // 15 lowercase alphanumerics, as D1 mints
const STRANGER = "strangerowner12";
const OWNER_ACCOUNT = "ca_OWNER_zellibrix";
const OWNER_ACCOUNT_2 = "ca_OWNER_quandle";
const STRANGER_ACCOUNT = "ca_STRANGER_zellibrix";

/** Two apps nobody has ever heard of. NOTHING in the Worker knows these names —
 *  that is the point of running the whole flow on them, and the check at the
 *  bottom asserts neither appears in the route's source. */
const APPS: Record<string, ToolkitLike> = {
  zellibrix: {
    slug: "zellibrix", name: "Zellibrix", logo: "https://cdn.example.invalid/z.png",
    description: "Where your team keeps its notes.", appUrl: "https://zellibrix.example.invalid",
    scopes: ["notes.read", "notes.write"],
    // A host the CATALOG declares, not one this file knows: the whole point of
    // running the mail-host column over an app nobody has heard of is that
    // neither half of the pipe can be passing because it recognised a name.
    mailHosts: ["mx.zellibrix.example.invalid"],
  },
  quandle_mail: {
    slug: "quandle_mail", name: "Quandle Mail", logo: null,
    description: null, appUrl: null, scopes: ["mail.read"],
  },
};

interface ToolkitLike {
  slug: string; name: string; logo: string | null; description: string | null;
  appUrl: string | null; scopes: string[];
  /** OPTIONAL HERE ON PURPOSE. `src/connections/provider.ts` builds this column
   *  on every row it reads, and against the live vendor it is EMPTY on every
   *  one of them (measured 2026-09-06; the receipt is in
   *  test/connections-provider.test.ts). A fake that omits it is therefore the
   *  ordinary case, and the route has to answer with a column either way. */
  mailHosts?: string[];
}

interface VendorLog {
  toolkit: string[];
  connections: string[];
  disconnect: { user: string; account: string }[];
  search: string[];
  sentences: string[];
}

interface RigOpts {
  /** What the vendor says it holds, per owner. */
  vendorHolds?(owner: string): unknown[];
  toolkit?(slug: string): Promise<ToolkitLike>;
  disconnect?(): Promise<{ revoked: boolean; deleted: boolean; revokeUnavailable: boolean }>;
  sentences?(meta: ToolkitLike): Promise<unknown>;
  /** Present only where a check needs the search arm wired. */
  search?(query: string): Promise<unknown>;
  now?(): number;
}

interface Rig {
  db: FakeD1;
  env: ConnectionsApiEnv;
  deps: ConnectionsApiDeps;
  log: VendorLog;
  ownerToken: string;
  strangerToken: string;
}

const vendorRow = (owner: string, toolkit: string, account: string): Record<string, unknown> => ({
  user_id: owner, toolkit, connected_account_id: account, alias: null,
  status: "connected", writes_enabled: false, last_used_at: null,
});

async function rig(opts: RigOpts = {}): Promise<Rig> {
  // `searchBudget` is module state, shared by every check in this process. A rig
  // that inherited the spend of the check above it would make the search checks
  // order-dependent, which is how a suite starts passing for the wrong reason.
  resetSearchBudget();
  const db = new FakeD1();
  for (const [id, key] of [[OWNER, "key-owner"], [STRANGER, "key-stranger"]]) {
    db.db.prepare(
      `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
         password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,'','')`,
    ).run(id, PB_NOW, PB_NOW, `${id}@anticipy-test.invalid`, key);
  }
  const env = {
    DB: asD1(db),
    ANTICIPY_AUTH_SECRET: "connections-api-test-secret",
  } as unknown as ConnectionsApiEnv;

  // THE REAL STORE over the REAL SCHEMA. Every guard the store carries —
  // refuseMixedOwners, the cross-owner predicate on the upsert, the CHECKs in
  // schema.sql — is live in every check below.
  const store = createD1Store(env as never);
  forgetLiveColumns(env as never);

  const seed: StoredConnection[] = [
    {
      user_id: OWNER as never, toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT,
      alias: null, status: "connected", writes_enabled: false, last_used_at: null,
    },
    {
      user_id: OWNER as never, toolkit: "quandle_mail", connected_account_id: OWNER_ACCOUNT_2,
      alias: "work", status: "connected", writes_enabled: false, last_used_at: null,
    },
    {
      user_id: STRANGER as never, toolkit: "zellibrix", connected_account_id: STRANGER_ACCOUNT,
      alias: null, status: "connected", writes_enabled: false, last_used_at: null,
    },
  ];
  for (const row of seed) await store.putConnection(row);

  const log: VendorLog = { toolkit: [], connections: [], disconnect: [], search: [], sentences: [] };
  const holds = opts.vendorHolds ?? ((owner: string): unknown[] =>
    owner === OWNER
      ? [vendorRow(OWNER, "zellibrix", OWNER_ACCOUNT), vendorRow(OWNER, "quandle_mail", OWNER_ACCOUNT_2)]
      : [vendorRow(STRANGER, "zellibrix", STRANGER_ACCOUNT)]);

  const deps = {
    store,
    provider: {
      async toolkit(slug: string): Promise<ToolkitLike> {
        log.toolkit.push(slug);
        if (opts.toolkit) return await opts.toolkit(slug);
        const meta = APPS[slug];
        if (!meta) throw new Error(`no catalog row for ${slug}`);
        return meta;
      },
      async connections(user: string): Promise<unknown[]> {
        log.connections.push(user);
        return holds(user);
      },
      async disconnect(user: string, account: string) {
        log.disconnect.push({ user, account });
        if (opts.disconnect) return await opts.disconnect();
        return { revoked: true, deleted: true, revokeUnavailable: false };
      },
    },
    words: {
      async sentences(meta: ToolkitLike): Promise<unknown> {
        log.sentences.push(meta.slug);
        if (opts.sentences) return await opts.sentences(meta);
        return [
          `Anticipy can read your ${meta.name} for the things you ask about.`,
          `It can add to your ${meta.name} when you ask it to.`,
          "You can turn this off any time in Settings.",
        ];
      },
    },
    now: opts.now ?? ((): number => NOW),
    ...(opts.search
      ? {
          async search(query: string): Promise<unknown> {
            log.search.push(query);
            return await opts.search!(query);
          },
        }
      : {}),
  } as unknown as ConnectionsApiDeps;

  return {
    db, env, deps, log,
    ownerToken: await issueToken(env as never, OWNER, "key-owner"),
    strangerToken: await issueToken(env as never, STRANGER, "key-stranger"),
  };
}

// --- requests ---------------------------------------------------------------

function getReq(path: string, token?: string | null): Request {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = token;
  return new Request("https://api.anticipy.ai" + path, { headers });
}

function postReq(path: string, token: string | null, body: unknown): Request {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token) headers.Authorization = token;
  return new Request("https://api.anticipy.ai" + path, {
    method: "POST", headers, body: JSON.stringify(body),
  });
}

const R = CONNECTIONS_API_ROUTES;

/** The connections table as SQLite holds it, read outside the code under test. */
function storedConnections(db: FakeD1): Record<string, unknown>[] {
  return db.rows(`SELECT * FROM "connections" ORDER BY "connected_account_id"`);
}
function storedLinks(db: FakeD1): Record<string, unknown>[] {
  return db.rows(`SELECT * FROM "connect_links" ORDER BY "expires_at"`);
}
function writesFlag(db: FakeD1, account: string): number {
  const row = db.rows<{ writes_enabled: number }>(
    `SELECT "writes_enabled" FROM "connections" WHERE "connected_account_id" = ?`, account)[0];
  return row ? Number(row.writes_enabled) : -1;
}

// ===========================================================================
// THE CONTRACT — read out of the client that already calls these
// ===========================================================================

/**
 * THE CENSUS, AND THE GAP LIST THAT IS NOW EMPTY.
 *
 * ConnectedAppsClient.Route. The phone builds every URL from these literals and
 * nothing else; a route renamed on either side must be red here rather than a
 * 404 on somebody's phone.
 *
 * `/me/connections/skip` and `/me/connections/signals` each sat on this list
 * while the Worker half had landed and the Swift half had not. Both halves are
 * in as of 2026-09-06, so the list is EMPTY and the census is exact in BOTH
 * directions — which is the strongest form it can take, and the form that makes
 * a route added on either side alone go red here. An exception may be added
 * back when a change genuinely lands in two halves, and it expires by going
 * off: the day the phone declares it, this check is red until the line is
 * deleted.
 */
const NOT_YET_ON_THE_PHONE: readonly string[] = [];

await check("every path the phone's client declares is a path this Worker serves", () => {
  const declared = [...new Set(
    [...CLIENT_SWIFT.matchAll(/static let \w+ = "(me\/connections[^"]*)"/g)]
      .map((m) => "/" + (m[1] as string)),
  )].sort();
  // A regex that quietly matched nothing would make every assertion below
  // vacuous in the direction that matters most.
  assert.ok(declared.length > 0,
    "the census read no routes at all out of ConnectedAppsClient.swift; the Route enum "
      + "moved and this scan is now measuring nothing");
  const served = Object.values(R).slice().sort();
  for (const path of declared) {
    assert.ok(served.includes(path),
      `the phone calls ${path} and this Worker does not serve it`);
  }
  const extra = served.filter((p) => !declared.includes(p));
  assert.deepEqual(extra, NOT_YET_ON_THE_PHONE.slice().sort(),
    "the phone's routes and this Worker's routes have drifted apart in a way nobody "
    + "wrote down — either the client gained a route this Worker does not serve, or "
    + "this Worker gained one and NOT_YET_ON_THE_PHONE was not updated");
});

await check("the two query names are the phone's own", () => {
  const query = /static let query = "([^"]+)"/.exec(CLIENT_SWIFT);
  const slugs = /static let slugs = "([^"]+)"/.exec(CLIENT_SWIFT);
  assert.ok(query && slugs, "ConnectedAppsClient.Field moved");
  assert.equal(QUERY_SEARCH, query[1]);
  assert.equal(QUERY_SLUGS, slugs[1]);
});

await check("no route names an owner", () => {
  // The client's own rule, checked from this end: not a path segment, not a
  // query key. `me/connections/{owner}` would be the wrong-person failure
  // arriving through a URL.
  for (const path of Object.values(R)) {
    assert.ok(!/\{|\}|:/.test(path), `${path} carries a parameter`);
    assert.equal(parseConnectionsApiPath(path + "/" + OWNER), null,
      `${path}/{owner} must not be a route`);
  }
});

// ===========================================================================
// ROUTING AND METHOD
// ===========================================================================

await check("a path that is not one of the six is a 404, not a guess", async () => {
  const r = await rig();
  for (const path of ["/me/connections/", "/me/connectionsX", "/me/connections/link/extra",
                      "/me/connections/LINK"]) {
    const res = await connectionsApiRoute(getReq(path, r.ownerToken), r.env, r.deps);
    assert.equal(res.status, 404, path);
    await bodyOf(res, `404 ${path}`);
  }
});

await check("a GET on /link is 405 and mints nothing", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(getReq(R.link, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("allow"), "POST");
  await bodyOf(res, "405 link");
  // THE POINT: a link prefetcher, an <img> or an address-bar preload must not
  // be able to spend this owner's mint budget.
  assert.equal(storedLinks(r.db).length, 0, "a GET must not have minted a link");
});

await check("a GET on /writes is 405 and flips nothing", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(getReq(R.writes, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("allow"), "POST");
  await bodyOf(res, "405 writes");
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0);
});

await check("a POST on the list route is 405", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.list, r.ownerToken, {}), r.env, r.deps);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("allow"), "GET");
  await bodyOf(res, "405 list");
});

await check("the CONTROL: the same six with their own verbs are not 405", async () => {
  // A method table that refused everything would pass every check above and
  // ship a dead feature.
  const r = await rig();
  const answers = [
    await connectionsApiRoute(getReq(R.list, r.ownerToken), r.env, r.deps),
    await connectionsApiRoute(getReq(`${R.catalog}?${QUERY_SLUGS}=zellibrix`, r.ownerToken), r.env, r.deps),
    await connectionsApiRoute(postReq(R.writes, r.ownerToken, { rows: [] }), r.env, r.deps),
    await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, { connected_account_id: OWNER_ACCOUNT }), r.env, r.deps),
    await connectionsApiRoute(postReq(R.sentences, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps),
    await connectionsApiRoute(postReq(R.link, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps),
  ];
  for (const [i, res] of answers.entries()) {
    assert.equal(res.status, 200, `leg ${i} answered ${res.status}`);
    await bodyOf(res, `control leg ${i}`);
  }
});

// ===========================================================================
// WHO IS ASKING
// ===========================================================================

await check("no credential is 401 on every leg, and nothing is touched", async () => {
  const r = await rig();
  const calls: Request[] = [
    getReq(R.list), getReq(`${R.catalog}?${QUERY_SLUGS}=zellibrix`),
    postReq(R.writes, null, { rows: [{ toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: true }] }),
    postReq(R.disconnect, null, { connected_account_id: OWNER_ACCOUNT }),
    postReq(R.sentences, null, { toolkit: "zellibrix" }),
    postReq(R.link, null, { toolkit: "zellibrix" }),
    getReq(R.signals),
  ];
  for (const req of calls) {
    const res = await connectionsApiRoute(req, r.env, r.deps);
    assert.equal(res.status, 401, new URL(req.url).pathname);
    await bodyOf(res, "401 " + new URL(req.url).pathname);
  }
  // The store, the catalog and the model are not reached at all: an anonymous
  // caller costs this Worker one HMAC verification and nothing else.
  assert.deepEqual(r.log, { toolkit: [], connections: [], disconnect: [], search: [], sentences: [] });
  assert.equal(storedLinks(r.db).length, 0);
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0);
});

await check("a token that is not a token is 401", async () => {
  const r = await rig();
  for (const bad of ["", "   ", "not.a.token", "Bearer nonsense", r.ownerToken + "x"]) {
    const res = await connectionsApiRoute(getReq(R.list, bad), r.env, r.deps);
    assert.equal(res.status, 401, JSON.stringify(bad));
    await bodyOf(res, "401 bad token");
  }
});

await check("a deleted account's token stops working", async () => {
  const r = await rig();
  r.db.db.prepare(`DELETE FROM owners WHERE id = ?`).run(OWNER);
  const res = await connectionsApiRoute(getReq(R.list, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 401);
  await bodyOf(res, "401 deleted account");
});

await check("an account whose id is not an owner ROW id is refused, not 500ed", async () => {
  // `owners.id` is `TEXT PRIMARY KEY` with no shape constraint (schema.sql:422),
  // so an imported, hand-made or legacy row can carry an id that is not the 15
  // lowercase alphanumerics this feature binds to. Everything downstream calls
  // `ownerId()`, which THROWS — and src/index.ts wraps none of this in a
  // try/catch, so without the shape check here that throw is a Worker exception
  // and the phone sees a 1101 rather than an answer. It is also the last place a
  // display name could be stopped before it reaches a query.
  const r = await rig();
  const ODD = "Legacy-Admin-1";
  r.db.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,'','')`,
  ).run(ODD, PB_NOW, PB_NOW, "legacy@anticipy-test.invalid", "key-legacy");
  const token = await issueToken(r.env as never, ODD, "key-legacy");

  const calls: Request[] = [
    getReq(R.list, token),
    getReq(`${R.catalog}?${QUERY_SLUGS}=zellibrix`, token),
    postReq(R.writes, token, { rows: [{ toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: true }] }),
    postReq(R.disconnect, token, { connected_account_id: OWNER_ACCOUNT }),
    postReq(R.sentences, token, { toolkit: "zellibrix" }),
    postReq(R.link, token, { toolkit: "zellibrix" }),
  ];
  for (const req of calls) {
    let res: Response;
    try {
      res = await connectionsApiRoute(req, r.env, r.deps);
    } catch (err) {
      assert.fail(`${new URL(req.url).pathname} threw out of the route: ${(err as Error).message}`);
    }
    assert.equal(res.status, 401, new URL(req.url).pathname);
    await bodyOf(res, "401 odd owner id");
  }
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0);
  assert.equal(storedLinks(r.db).length, 0);
  assert.deepEqual(r.log.disconnect, []);
});

await check("the CONTROL: a live token is accepted with and without Bearer", async () => {
  const r = await rig();
  for (const header of [r.ownerToken, `Bearer ${r.ownerToken}`]) {
    const res = await connectionsApiRoute(getReq(R.list, header), r.env, r.deps);
    assert.equal(res.status, 200, header.slice(0, 10));
    await bodyOf(res, "200 accepted");
  }
});

// ===========================================================================
// GET /me/connections
// ===========================================================================

await check("the list is this owner's rows, in the phone's own column names", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(getReq(R.list, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("cache-control"), "no-store");
  const body = await jsonOf(res, "list ok");
  const items = body.items as Record<string, unknown>[];
  assert.equal(items.length, 2);
  // `Connection(row:)` reads exactly these and drops a row it cannot read
  // whole, so every one of them has to be here and spelled this way.
  for (const row of items) {
    assert.deepEqual(Object.keys(row).slice().sort(), [
      "alias", "connected_account_id", "last_used_at", "status", "toolkit",
      "user_id", "writes_enabled",
    ]);
    assert.equal(row.user_id, OWNER);
    assert.equal(typeof row.writes_enabled, "boolean",
      "writes_enabled must be a real JSON boolean; writesOptedIn accepts true and 1 and nothing else");
  }
  assert.deepEqual(items.map((i) => i.connected_account_id).sort(),
    [OWNER_ACCOUNT_2, OWNER_ACCOUNT].sort());
});

await check("a stranger's rows are not in this owner's list", async () => {
  const r = await rig();
  const body = await jsonOf(
    await connectionsApiRoute(getReq(R.list, r.ownerToken), r.env, r.deps), "list scoping");
  const ids = (body.items as Record<string, unknown>[]).map((i) => i.connected_account_id);
  assert.ok(!ids.includes(STRANGER_ACCOUNT), "somebody else's account reached this owner's screen");

  // AND THE CONTROL, from the other side: the stranger's own token sees the
  // stranger's own row and not this owner's. A route that answered an empty
  // list for everybody would pass the half above.
  const theirs = await jsonOf(
    await connectionsApiRoute(getReq(R.list, r.strangerToken), r.env, r.deps), "list stranger");
  assert.deepEqual((theirs.items as Record<string, unknown>[]).map((i) => i.connected_account_id),
    [STRANGER_ACCOUNT]);
});

await check("a database that cannot answer is never an empty list", async () => {
  const r = await rig();
  r.db.failOn = (sql) => sql.includes(`FROM "connections"`);
  const res = await connectionsApiRoute(getReq(R.list, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "list refused");
  assert.equal(body.ok, false);
  assert.ok(!("items" in body),
    "a failed read answered with a list; somebody with two connected apps would be told they have none");
});

// ===========================================================================
// GET /me/connections/catalog
// ===========================================================================

await check("?slugs= describes the toolkits it was given", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SLUGS}=zellibrix,quandle_mail`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  const items = (await jsonOf(res, "catalog slugs")).items as Record<string, unknown>[];
  assert.equal(items.length, 2);
  const z = items.find((i) => i.slug === "zellibrix")!;
  assert.equal(z.name, "Zellibrix");
  // snake_case, because the phone reads row["app_url"] while the provider's
  // ToolkitMeta spells it appUrl. This boundary is where that is translated.
  assert.equal(z.app_url, "https://zellibrix.example.invalid");
  assert.deepEqual(z.scopes, ["notes.read", "notes.write"]);
  const q = items.find((i) => i.slug === "quandle_mail")!;
  assert.equal(q.logo, null);
  assert.equal(q.app_url, null);
});

await check("?slugs= carries the catalog's own mail hosts, and a column even when it has none",
  async () => {
    const r = await rig();
    const res = await connectionsApiRoute(
      getReq(`${R.catalog}?${QUERY_SLUGS}=zellibrix,quandle_mail`, r.ownerToken), r.env, r.deps);
    assert.equal(res.status, 200);
    const items = (await jsonOf(res, "catalog mail hosts")).items as Record<string, unknown>[];

    // THE SEAM, END TO END. `ConnectOnboardingPolicy.seeds(fromMailExchanger:)`
    // matches a resolved exchanger against `entry.mailHosts` and can seed
    // nothing at all unless the column reaches the phone. snake_case beside
    // `app_url`, because this is the same boundary and one decoder reads both.
    const z = items.find((i) => i.slug === "zellibrix")!;
    assert.deepEqual(z.mail_hosts, ["mx.zellibrix.example.invalid"],
      "the catalog's own mail hosts did not reach the phone, so the MX signal "
        + "has nothing to match against and onboarding pre-ticks nothing");

    // ALWAYS PRESENT, EVEN EMPTY. "The catalog names none" and "this server is
    // too old to have the column" are different facts, and only one of them is
    // true; a missing key makes the phone guess which.
    const q = items.find((i) => i.slug === "quandle_mail")!;
    assert.ok(Object.prototype.hasOwnProperty.call(q, "mail_hosts"),
      "a row with no mail hosts dropped the column instead of carrying an empty one");
    assert.deepEqual(q.mail_hosts, []);
  });

await check("nothing but a real host reaches the wire as a mail host", async () => {
  // The same discipline readScopes keeps: a blank is not a host, and a
  // non-string is not one either. Both would arrive at hostLabels() on the
  // phone as a line that matches nothing and cannot be read.
  const r = await rig({
    toolkit: async (slug: string): Promise<ToolkitLike> => ({
      ...APPS.zellibrix!, slug,
      mailHosts: [null, 42, "", "   ", "  mx.example.invalid  "] as never,
    }),
  });
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SLUGS}=zellibrix`, r.ownerToken), r.env, r.deps);
  const items = (await jsonOf(res, "catalog mail junk")).items as Record<string, unknown>[];
  assert.deepEqual(items[0]!.mail_hosts, ["mx.example.invalid"]);
});

await check("one unreadable slug does not cost the others their names", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SLUGS}=zellibrix,no_such_app`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  const items = (await jsonOf(res, "catalog partial")).items as Record<string, unknown>[];
  assert.deepEqual(items.map((i) => i.slug), ["zellibrix"]);
});

await check("every slug unreadable is an outage, not an empty catalog", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SLUGS}=no_such_app,also_missing`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "catalog all failed");
  assert.ok(!("items" in body),
    "a dead catalog answered with a list; four connected apps would render with no names as if that were data");
});

await check("an empty ask is an empty answer, and a huge one is refused", async () => {
  const r = await rig();
  const empty = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SLUGS}=`, r.ownerToken), r.env, r.deps);
  assert.equal(empty.status, 200);
  assert.deepEqual((await jsonOf(empty, "catalog empty ask")).items, []);
  assert.equal(r.log.toolkit.length, 0, "nothing was asked, so the catalog was not called");

  const many = Array.from({ length: MAX_CATALOG_SLUGS + 1 }, (_, i) => `app_${i}`).join(",");
  const big = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SLUGS}=${many}`, r.ownerToken), r.env, r.deps);
  assert.equal(big.status, 400);
  await bodyOf(big, "catalog too many");
  assert.equal(r.log.toolkit.length, 0, "a query string must not be able to fan out to the vendor");
});

await check("?q= with no search port is an outage, never an empty catalog", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SEARCH}=work%20mail`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "catalog search unwired");
  assert.ok(!("items" in body),
    "the search box answered 'nothing matched' when the truth is that nothing was asked");
});

await check("?q= hands the letters to the catalog byte for byte", async () => {
  // LAW 1. The one thing done to the query is percent-decoding it out of the
  // URL, which is transport. No trim, no lowercase, no tokenising, no ranking:
  // which app somebody meant is the catalog's question and a model's.
  const typed = "  My Work Mail (2nd) ";
  const r = await rig({ search: async () => [APPS.zellibrix] });
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SEARCH}=${encodeURIComponent(typed)}`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  assert.deepEqual(r.log.search, [typed],
    "the query reached the catalog altered; the spec's rule is 'as typed'");
  const items = (await jsonOf(res, "catalog search ok")).items as Record<string, unknown>[];
  assert.deepEqual(items.map((i) => i.slug), ["zellibrix"]);
});

await check("a search port that throws or answers a non-list is an outage", async () => {
  for (const [what, search] of [
    ["throws", async (): Promise<unknown> => { throw new Error("catalog down"); }],
    ["answers an object", async (): Promise<unknown> => ({ items: [] })],
  ] as [string, (q: string) => Promise<unknown>][]) {
    const r = await rig({ search });
    const res = await connectionsApiRoute(
      getReq(`${R.catalog}?${QUERY_SEARCH}=x`, r.ownerToken), r.env, r.deps);
    assert.equal(res.status, 503, what);
    assert.ok(!("items" in await jsonOf(res, `catalog search ${what}`)), what);
  }
});

await check("the real wiring FILLS the search port, so ?q= is not a permanent 503", async () => {
  // THE FINDING THIS CLOSES. `ConnectionsApiDeps.search` was declared and
  // nothing filled it, so "Add an app" answered 503 to every letter anybody
  // typed. Built from the real `connectionsApiDeps` — not the rig's fake deps —
  // because the defect was in the WIRING and a fake would have hidden it.
  const db = new FakeD1();
  const env = { DB: asD1(db), ANTICIPY_AUTH_SECRET: "s" } as unknown as ConnectionsApiEnv;
  const wired = connectionsApiDeps(env);
  assert.ok(wired, "connectionsApiDeps refused to build with a DB binding present");
  assert.equal(typeof wired!.search, "function",
    "nothing fills ConnectionsApiDeps.search, so the search box answers 503 to everybody");
  // And it is the ADAPTER's search, not a second one invented here: with no
  // COMPOSIO_API_KEY bound it refuses by name without issuing a request, which
  // is the provider's own unconfigured behaviour reaching this seam.
  await assert.rejects(() => wired!.search!("mail"), (err: Error) => {
    assert.equal(err.name, "ConnectionsUnconfigured");
    return true;
  });
});

await check("?q= with nothing typed is a 400 and the catalog is never asked", async () => {
  // Not a 503: nothing failed. The phone cannot produce this — both call sites
  // refuse to send a blank (ConnectOnboardingPolicy.searchQuery,
  // ConnectedAppsModel.search) — so it is everything else that can reach a URL.
  for (const raw of ["", "%20%20", "%09"]) {
    const r = await rig({ search: async () => [APPS.zellibrix] });
    const res = await connectionsApiRoute(
      getReq(`${R.catalog}?${QUERY_SEARCH}=${raw}`, r.ownerToken), r.env, r.deps);
    assert.equal(res.status, 400, JSON.stringify(raw));
    const body = await jsonOf(res, `catalog search blank ${raw}`);
    assert.ok(!("items" in body), "a blank search answered with a list");
    assert.deepEqual(r.log.search, [],
      "an empty query was forwarded; at the vendor that is the first page of the whole catalog");
  }
});

await check("?q= with letters and spaces around them still goes out untouched", async () => {
  // The CONTROL on the blank check above: it measures emptiness only. A query
  // that has anything in it keeps its spaces, because the client deliberately
  // does not trim (ConnectedAppsClientTests pins "  work mail  ").
  const typed = "  work mail  ";
  const r = await rig({ search: async () => [APPS.zellibrix] });
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SEARCH}=${encodeURIComponent(typed)}`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  assert.deepEqual(r.log.search, [typed]);
  await bodyOf(res, "catalog search spaces kept");
});

await check("the route cuts a search answer to MAX_SEARCH_RESULTS", async () => {
  // Defence in depth over the provider's own cap: this is the seam a port that
  // is NOT the provider comes through, and a phone rendering one scrolling list
  // must not be handed 1,400 rows by anything.
  const many = Array.from({ length: MAX_SEARCH_RESULTS + 40 }, (_, i) => ({
    slug: `app${i}`, name: `App ${i}`, logo: null, description: null, appUrl: null, scopes: [],
  }));
  const r = await rig({ search: async () => many });
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SEARCH}=a`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  const items = (await jsonOf(res, "catalog search capped")).items as Record<string, unknown>[];
  assert.equal(items.length, MAX_SEARCH_RESULTS);
  assert.equal(items[0]!.slug, "app0", "the cut took from the wrong end, so the order changed");
});

await check("a search answer holding junk is an outage, not a 500 and not a short list", async () => {
  // The last place a port's answer is touched. `catalogRow` reads fields off
  // each row, so a null or a bare string in that array throws — and an uncaught
  // throw out of a route handler is a 500 with a stack in it, on a path a
  // signed-in stranger can reach.
  const r = await rig({ search: async () => [APPS.zellibrix, null, "gmail"] });
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SEARCH}=x`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 503, "a port answering junk produced something other than an outage");
  const body = await jsonOf(res, "catalog search junk");
  assert.ok(!("items" in body), "a junk answer came back as a list");
});

await check("an empty answer FROM THE CATALOG is 200 and empty — nothing matched", async () => {
  // The one empty search list that is an answer rather than a failure: the
  // catalog was reached and said so. Every other empty is a 503 above.
  const r = await rig({ search: async () => [] });
  const res = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SEARCH}=qqzzqq`, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  assert.deepEqual((await jsonOf(res, "catalog search nothing matched")).items, []);
});

await check("the search budget stops the owner past the ceiling, and asks the catalog nothing", async () => {
  const r = await rig({ search: async () => [APPS.zellibrix] });
  const ask = (): Promise<Response> => connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SEARCH}=mail`, r.ownerToken), r.env, r.deps);

  for (let i = 0; i < MAX_SEARCHES_PER_OWNER; i++) {
    assert.equal((await ask()).status, 200, `search ${i + 1} was refused early`);
  }
  assert.equal(r.log.search.length, MAX_SEARCHES_PER_OWNER);

  const over = await ask();
  assert.equal(over.status, 429, "the ceiling does not stop anything");
  const body = await jsonOf(over, "catalog search over budget");
  assert.ok(!("items" in body), "a refused search answered with a list");
  assert.equal(r.log.search.length, MAX_SEARCHES_PER_OWNER,
    "the catalog was asked anyway, so the budget bounds nothing it exists to bound");

  // A refusal records nothing, so an hour's cooldown does not become a
  // permanent one for somebody who kept tapping.
  assert.equal((await ask()).status, 429);
  await bodyOf(await ask(), "catalog search still over");
});

await check("the search budget is per owner: one owner's spend is not another's", async () => {
  const r = await rig({ search: async () => [APPS.zellibrix] });
  const url = `${R.catalog}?${QUERY_SEARCH}=mail`;
  for (let i = 0; i < MAX_SEARCHES_PER_OWNER; i++) {
    await connectionsApiRoute(getReq(url, r.ownerToken), r.env, r.deps);
  }
  assert.equal((await connectionsApiRoute(getReq(url, r.ownerToken), r.env, r.deps)).status, 429);
  const stranger = await connectionsApiRoute(getReq(url, r.strangerToken), r.env, r.deps);
  assert.equal(stranger.status, 200,
    "one person's searching spent everybody's budget; the count is not keyed by owner");
  await bodyOf(stranger, "catalog search other owner");
});

await check("the search budget is a WINDOW: an hour later the same owner is served", async () => {
  let clock = NOW;
  const r = await rig({ search: async () => [APPS.zellibrix], now: () => clock });
  const url = `${R.catalog}?${QUERY_SEARCH}=mail`;
  for (let i = 0; i < MAX_SEARCHES_PER_OWNER; i++) {
    await connectionsApiRoute(getReq(url, r.ownerToken), r.env, r.deps);
  }
  // AND THEY KEEP TAPPING, once a second, for as long as they are refused. A
  // refusal that RECORDED its own attempt would push this owner's window
  // forward on every tap, and an hour's cooldown would become a permanent one
  // for exactly the person most likely to keep trying.
  for (let i = 1; i <= MAX_SEARCHES_PER_OWNER; i++) {
    clock = NOW + i * 1000;
    assert.equal((await connectionsApiRoute(getReq(url, r.ownerToken), r.env, r.deps)).status, 429);
  }
  // An hour after the last search that actually happened.
  clock = NOW + SEARCH_WINDOW_MS + 1;
  const later = await connectionsApiRoute(getReq(url, r.ownerToken), r.env, r.deps);
  assert.equal(later.status, 200,
    "the window never rolled: either it does not roll at all, or the refusals kept pushing it "
      + "forward, and a heavy afternoon is a permanent ban");
  await bodyOf(later, "catalog search after the window");
});

await check("an anonymous caller cannot spend anybody's search budget", async () => {
  // The 401 gate runs before the budget: an owner id is what the budget is
  // keyed by, and there is no owner until a credential has been verified.
  const r = await rig({ search: async () => [APPS.zellibrix] });
  for (let i = 0; i < MAX_SEARCHES_PER_OWNER + 5; i++) {
    const res = await connectionsApiRoute(
      getReq(`${R.catalog}?${QUERY_SEARCH}=mail`), r.env, r.deps);
    assert.equal(res.status, 401);
  }
  assert.equal(r.log.search.length, 0);
  const mine = await connectionsApiRoute(
    getReq(`${R.catalog}?${QUERY_SEARCH}=mail`, r.ownerToken), r.env, r.deps);
  assert.equal(mine.status, 200, "an anonymous flood spent a signed-in owner's budget");
  await bodyOf(mine, "catalog search after anonymous flood");
});

await check("a catalog call naming neither q nor slugs is a 400", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(getReq(R.catalog, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 400);
  await bodyOf(res, "catalog no arg");
});

// ===========================================================================
// POST /me/connections/writes
// ===========================================================================

await check("the write toggle flips this owner's own row", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, {
    rows: [{ toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: true }],
  }), r.env, r.deps);
  assert.equal(res.status, 200);
  await bodyOf(res, "writes ok");
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 1);
  // And back off again, because a toggle that only goes one way is a toggle
  // that silently keeps a permission somebody withdrew.
  await connectionsApiRoute(postReq(R.writes, r.ownerToken, {
    rows: [{ toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: false }],
  }), r.env, r.deps);
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0);
});

await check("a batch naming somebody else's account writes NOTHING", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, {
    // Row one is genuinely this owner's; row two is the stranger's. A route
    // that filtered rather than refused would flip row one and silently drop
    // row two — a smaller batch than the screen just moved.
    rows: [
      { toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: true },
      { toolkit: "zellibrix", connected_account_id: STRANGER_ACCOUNT, writes_enabled: true },
    ],
  }), r.env, r.deps);
  assert.equal(res.status, 403);
  await bodyOf(res, "writes foreign row");
  assert.equal(writesFlag(r.db, STRANGER_ACCOUNT), 0, "another owner's toggle was flipped");
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0,
    "the batch was applied in part; validation must finish before anything is written");
});

await check("a body naming another owner changes nothing at all", async () => {
  // THE WHOLE POINT OF THE ROUTE'S SHAPE. There is no field a caller can set to
  // become somebody else, so setting one has no effect whatsoever.
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, {
    user_id: STRANGER,
    owner: STRANGER,
    rows: [{
      toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT,
      writes_enabled: true, user_id: STRANGER,
    }],
  }), r.env, r.deps);
  assert.equal(res.status, 200);
  await bodyOf(res, "writes foreign owner named");
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 1, "the signed-in owner's own row is what moved");
  assert.equal(writesFlag(r.db, STRANGER_ACCOUNT), 0, "the named owner's row moved");
  const rows = storedConnections(r.db);
  assert.equal(rows.find((x) => x.connected_account_id === OWNER_ACCOUNT)!.user_id, OWNER,
    "a body field re-bound a row to another owner");
});

await check("writes_enabled must be a real boolean", async () => {
  const r = await rig();
  for (const value of ["true", 1, "1", "yes", null, undefined, {}]) {
    const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, {
      rows: [{ toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: value }],
    }), r.env, r.deps);
    assert.equal(res.status, 400, JSON.stringify(value));
    await bodyOf(res, "writes bad boolean");
  }
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0,
    "a coerced truthy value opted somebody into changes they never agreed to");
});

await check("the body cannot change anything but the toggle", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, {
    rows: [{
      toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: true,
      // Every one of these is ignored: only `writes_enabled` is this request's
      // to set, and everything else comes from the STORED row.
      status: "disconnected", alias: "personal", last_used_at: 999, user_id: STRANGER,
    }],
  }), r.env, r.deps);
  assert.equal(res.status, 200);
  await bodyOf(res, "writes extra fields");
  const row = storedConnections(r.db).find((x) => x.connected_account_id === OWNER_ACCOUNT)!;
  assert.equal(row.status, "connected", "a body field rewrote the connection's status");
  assert.equal(row.alias, "", "a body field rewrote the account alias");
  assert.equal(row.last_used_at, null);
  assert.equal(row.writes_enabled, 1);
});

await check("a toolkit that disagrees with the stored row is refused", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, {
    rows: [{ toolkit: "quandle_mail", connected_account_id: OWNER_ACCOUNT, writes_enabled: true }],
  }), r.env, r.deps);
  assert.equal(res.status, 409);
  await bodyOf(res, "writes toolkit mismatch");
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0);
});

await check("a malformed batch is a 400 and writes nothing", async () => {
  const r = await rig();
  const bad: unknown[] = [
    { rows: "everything" },
    { rows: [{ toolkit: "", connected_account_id: OWNER_ACCOUNT, writes_enabled: true }] },
    { rows: [{ toolkit: "zellibrix", connected_account_id: "  ", writes_enabled: true }] },
    { rows: [{ toolkit: "zellibrix", writes_enabled: true }] },
    { rows: [null] },
    // The same account twice with two answers has no correct outcome.
    { rows: [
      { toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: true },
      { toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: false },
    ] },
    { rows: Array.from({ length: MAX_WRITE_ROWS + 1 }, () => (
      { toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: true })) },
    {},
  ];
  for (const body of bad) {
    const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, body), r.env, r.deps);
    assert.equal(res.status, 400, JSON.stringify(body).slice(0, 60));
    await bodyOf(res, "writes malformed");
  }
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0);
});

await check("an empty batch is a no-op, not an error", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, { rows: [] }), r.env, r.deps);
  assert.equal(res.status, 200);
  await bodyOf(res, "writes empty");
});

await check("a database that cannot save says so", async () => {
  const r = await rig();
  r.db.failOn = (sql) => sql.startsWith(`INSERT INTO "connections"`);
  const res = await connectionsApiRoute(postReq(R.writes, r.ownerToken, {
    rows: [{ toolkit: "zellibrix", connected_account_id: OWNER_ACCOUNT, writes_enabled: true }],
  }), r.env, r.deps);
  assert.equal(res.status, 503);
  assert.equal((await jsonOf(res, "writes db down")).ok, false);
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0);
});

// ===========================================================================
// POST /me/connections/disconnect
// ===========================================================================

await check("a disconnect revokes, deletes, and says both happened", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT,
  }), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "disconnect ok");
  assert.deepEqual(body, {
    revoked: true, deleted: true, revoke_unavailable: false, app_name: "Zellibrix",
  });
  assert.equal(r.log.disconnect.length, 1);
  assert.equal(r.log.disconnect[0]!.user, OWNER, "the vendor was asked about the token's owner");
  assert.equal(r.log.disconnect[0]!.account, OWNER_ACCOUNT);
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), -1, "our own row survived a successful disconnect");
  assert.equal(writesFlag(r.db, STRANGER_ACCOUNT), 0, "somebody else's row went too");
});

await check("the app's name comes from the catalog, never from a list here", async () => {
  const r = await rig();
  const body = await jsonOf(await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT_2,
  }), r.env, r.deps), "disconnect name");
  assert.equal(body.app_name, "Quandle Mail");
  assert.ok(r.log.toolkit.includes("quandle_mail"),
    "the catalog was not asked; the name would have had to be hardcoded");
});

await check("a catalog blip costs the name and not the disconnect", async () => {
  const r = await rig({ toolkit: async () => { throw new Error("catalog down"); } });
  const res = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT,
  }), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "disconnect no name");
  assert.equal(body.app_name, "");
  assert.equal(body.revoked, true);
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), -1, "the row should be gone");
});

await check("an unrevokable account never reads as revoked", async () => {
  // The measured 5%: the account is not in a revocable state, the provider says
  // so, and the copy must send the person to the app's own settings rather than
  // tell them their access is gone.
  const r = await rig({
    disconnect: async () => ({ revoked: false, deleted: true, revokeUnavailable: true }),
  });
  const body = await jsonOf(await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT,
  }), r.env, r.deps), "disconnect unrevokable");
  assert.equal(body.revoked, false, "an unrevokable account was reported as revoked");
  assert.equal(body.revoke_unavailable, true);
  assert.equal(body.deleted, true);
});

await check("a revoke that happened and a delete that did not is reported as both", async () => {
  const r = await rig({
    disconnect: async () => ({ revoked: true, deleted: false, revokeUnavailable: false }),
  });
  const body = await jsonOf(await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT,
  }), r.env, r.deps), "disconnect half");
  assert.equal(body.revoked, true);
  assert.equal(body.deleted, false, "our answer claimed the record was gone at both ends");
});

await check("our own row surviving is reported, not smoothed over", async () => {
  const r = await rig();
  r.db.failOn = (sql) => sql.startsWith(`DELETE FROM "connections"`);
  const body = await jsonOf(await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT,
  }), r.env, r.deps), "disconnect local delete failed");
  assert.equal(body.revoked, true, "the far end genuinely revoked and the person is owed that");
  assert.equal(body.deleted, false,
    "our row is still on file and the answer said it was gone");
});

await check("a vendor that will not answer means nothing is deleted", async () => {
  const r = await rig({
    disconnect: async () => { throw new Error("provider unavailable"); },
  });
  const res = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT,
  }), r.env, r.deps);
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "disconnect provider down");
  assert.equal(body.ok, false);
  assert.ok(!("revoked" in body), "a failed disconnect answered with the shape of a result");
  // THE IRREVERSIBLE MISTAKE THIS PREVENTS: the account id is the only handle
  // we will ever have for revoking this token. Destroying it while the token
  // may still be live is the one thing that cannot be undone.
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0, "the only handle for revoking was thrown away");
});

await check("a catalog that cannot list means the vendor is never asked to delete", async () => {
  const r = await rig({
    vendorHolds: () => { throw new Error("listing down"); },
  });
  const res = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT,
  }), r.env, r.deps);
  assert.equal(res.status, 503);
  await bodyOf(res, "disconnect listing down");
  assert.equal(r.log.disconnect.length, 0,
    "revoke and delete take an account id and no user scoping; neither may run on no evidence");
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), 0);
});

await check("somebody else's account id is a 404 and reaches no vendor call", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: STRANGER_ACCOUNT,
  }), r.env, r.deps);
  assert.equal(res.status, 404);
  await bodyOf(res, "disconnect not yours");
  assert.equal(r.log.disconnect.length, 0, "a stranger's connection was passed to the vendor's delete");
  assert.equal(r.log.connections.length, 0, "the vendor was asked about it at all");
  assert.equal(writesFlag(r.db, STRANGER_ACCOUNT), 0, "a stranger's row was deleted");
});

await check("an invented account id is a 404 and discloses nothing more", async () => {
  const r = await rig();
  const made = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: "ca_NEVER_EXISTED",
  }), r.env, r.deps);
  const theirs = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: STRANGER_ACCOUNT,
  }), r.env, r.deps);
  assert.equal(made.status, theirs.status);
  assert.equal(await bodyOf(made, "disconnect invented"),
    await bodyOf(theirs, "disconnect stranger repeat"),
    "an id that exists under somebody else answers differently from one that never existed");
});

await check("a row the vendor no longer holds can still leave the screen", async () => {
  // THE SELF-HEAL. The commonest way this happens is a previous disconnect that
  // revoked and deleted at the far end and then failed to delete here. Without
  // this branch the row could never be removed, and the person would be looking
  // at a connection that does not exist.
  const r = await rig({ vendorHolds: () => [] });
  const res = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, {
    connected_account_id: OWNER_ACCOUNT,
  }), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "disconnect stale row");
  assert.equal(body.revoked, false, "there was nothing to revoke, so nothing may say it was revoked");
  assert.equal(body.deleted, true);
  assert.equal(r.log.disconnect.length, 0, "there was nothing at the far end to disconnect");
  assert.equal(writesFlag(r.db, OWNER_ACCOUNT), -1);
});

await check("a disconnect with no account id is a 400", async () => {
  const r = await rig();
  for (const body of [{}, { connected_account_id: "" }, { connected_account_id: "   " },
                      { connected_account_id: 7 }]) {
    const res = await connectionsApiRoute(postReq(R.disconnect, r.ownerToken, body), r.env, r.deps);
    assert.equal(res.status, 400, JSON.stringify(body));
    await bodyOf(res, "disconnect bad body");
  }
  assert.equal(r.log.disconnect.length, 0);
});

// ===========================================================================
// POST /me/connections/sentences
// ===========================================================================

await check("the three sentences come from the catalog row's own scopes", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(
    postReq(R.sentences, r.ownerToken, { toolkit: "  Zellibrix  " }), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "sentences ok");
  const lines = body.sentences as string[];
  assert.equal(lines.length, 3);
  assert.ok(lines[0]!.includes("Zellibrix"), "the app's name came from somewhere other than the catalog");
  // Case and padding are plumbing; nothing maps one slug onto a different one.
  assert.deepEqual(r.log.toolkit, ["zellibrix"]);
  assert.deepEqual(r.log.sentences, ["zellibrix"]);
});

await check("no sentences is never an empty list", async () => {
  const cases: [string, () => Promise<unknown>][] = [
    ["the writer refused", async () => { throw new Error("PermissionWordsRefused"); }],
    ["it returned nothing", async () => []],
    ["one of three was blank", async () => ["a claim.", "   ", "another claim."]],
    ["it was not a list", async () => ({ sentences: ["a", "b", "c"] })],
  ];
  for (const [what, sentences] of cases) {
    const r = await rig({ sentences });
    const res = await connectionsApiRoute(
      postReq(R.sentences, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps);
    assert.equal(res.status, 503, what);
    const body = await jsonOf(res, `sentences ${what}`);
    assert.ok(!("sentences" in body),
      `${what}: a consent sheet was offered a blank or partial list of claims`);
  }
});

await check("an unknown app has no sentences rather than invented ones", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(
    postReq(R.sentences, r.ownerToken, { toolkit: "no_such_app" }), r.env, r.deps);
  assert.equal(res.status, 503);
  assert.equal(r.log.sentences.length, 0, "the writer was asked about an app the catalog cannot name");
  await bodyOf(res, "sentences unknown app");
});

await check("a sentences call with no toolkit is a 400", async () => {
  const r = await rig();
  for (const body of [{}, { toolkit: "" }, { toolkit: "   " }, { toolkit: 3 }]) {
    const res = await connectionsApiRoute(postReq(R.sentences, r.ownerToken, body), r.env, r.deps);
    assert.equal(res.status, 400, JSON.stringify(body));
    await bodyOf(res, "sentences bad body");
  }
  assert.equal(r.log.toolkit.length, 0);
});

// ===========================================================================
// POST /me/connections/link
// ===========================================================================

const sha256Hex = (s: string): string => createHash("sha256").update(s).digest("hex");

await check("a link is minted, bound to this owner, and never written down raw", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("cache-control"), "no-store");
  const body = await jsonOf(res, "link ok");
  const url = String(body.url);
  assert.ok(url.startsWith(`${CONNECT_URL_BASE}/`),
    `the minted link is not on our own connect base: ${url}`);
  const token = url.slice(`${CONNECT_URL_BASE}/`.length);
  assert.equal(token.length, TOKEN_CHARS, "routes/connect.ts routes exactly this many characters");
  assert.match(token, /^[A-Za-z0-9_-]+$/);
  assert.equal(body.expires_at, NOW + LINK_TTL_MS);

  const rows = storedLinks(r.db);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.user_id, OWNER, "the link was bound to somebody other than the token's owner");
  assert.equal(rows[0]!.toolkit, "zellibrix");
  assert.equal(rows[0]!.used_at, null);
  assert.equal(rows[0]!.completed_at, null);
  assert.equal(rows[0]!.token_handle, sha256Hex(token),
    "the row must hold sha256(token) and never the token itself");
  assert.ok(!JSON.stringify(rows).includes(token),
    "the raw token reached the database; one read would be a live link to somebody's account");
});

await check("a link body naming another owner binds to the signed-in one", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.link, r.ownerToken, {
    toolkit: "zellibrix", user_id: STRANGER, owner: STRANGER,
  }), r.env, r.deps);
  assert.equal(res.status, 200);
  await bodyOf(res, "link foreign owner named");
  assert.deepEqual(storedLinks(r.db).map((x) => x.user_id), [OWNER],
    "a body field decided whose account a connect link binds");
});

await check("the mint budget stops the seventh link in an hour", async () => {
  // THE CLOCK ADVANCES BETWEEN CALLS, AND THAT IS NEW. Until 2026-09-06 this
  // check minted six links at one frozen instant, which passed while the budget
  // counted ROWS — and counting rows is what charged a four-app connect page
  // four times for one tap of one Connect button. The budget now counts MINTS
  // (distinct mint instants in the window), so a rig that freezes the clock is
  // a rig in which six separate HTTP requests happened in the same millisecond,
  // which is not a thing production can do. One millisecond apart is enough and
  // is the realistic case.
  let clock = NOW;
  const r = await rig({ now: () => clock });
  for (let i = 0; i < MAX_LINKS_PER_OWNER; i++) {
    clock = NOW + i;
    const res = await connectionsApiRoute(
      postReq(R.link, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps);
    // THE CONTROL: every one under the ceiling must work, or the limit is an
    // outage rather than a limit.
    assert.equal(res.status, 200, `link ${i + 1} of ${MAX_LINKS_PER_OWNER}`);
    await bodyOf(res, `link ${i}`);
  }
  clock = NOW + MAX_LINKS_PER_OWNER;
  const over = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps);
  assert.equal(over.status, 429);
  const body = await jsonOf(over, "link over budget");
  assert.ok(!("url" in body), "a refused mint answered with a link anyway");
  assert.equal(storedLinks(r.db).length, MAX_LINKS_PER_OWNER,
    "the refused mint still wrote a row");
});

await check("links outside the window do not count, and neither do other people's", async () => {
  const r = await rig();
  // MAX links minted just outside the hour, plus the whole of somebody else's
  // budget. Neither may cost this owner a mint.
  const old = NOW - LINK_WINDOW_MS - 1 + LINK_TTL_MS;
  for (let i = 0; i < MAX_LINKS_PER_OWNER; i++) {
    r.db.db.prepare(
      `INSERT INTO connect_links (token_handle, user_id, toolkit, alias, expires_at, used_at, completed_at)
       VALUES (?,?,?,'',?,NULL,NULL)`,
    ).run(sha256Hex(`old-${i}`), OWNER, "zellibrix", old);
    r.db.db.prepare(
      `INSERT INTO connect_links (token_handle, user_id, toolkit, alias, expires_at, used_at, completed_at)
       VALUES (?,?,?,'',?,NULL,NULL)`,
    ).run(sha256Hex(`stranger-${i}`), STRANGER, "zellibrix", NOW + LINK_TTL_MS);
  }
  const res = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps);
  assert.equal(res.status, 200,
    "an expired link of this owner's, or a live one of somebody else's, cost them a mint");
  await bodyOf(res, "link window control");
});

await check("a link call with no toolkit is a 400 and mints nothing", async () => {
  const r = await rig();
  for (const body of [{}, { toolkit: "" }, { toolkit: "  " }, { toolkit: [] }]) {
    const res = await connectionsApiRoute(postReq(R.link, r.ownerToken, body), r.env, r.deps);
    assert.equal(res.status, 400, JSON.stringify(body));
    await bodyOf(res, "link bad body");
  }
  assert.equal(storedLinks(r.db).length, 0);
});

await check("a database that cannot mint says so, and answers no url", async () => {
  const r = await rig();
  r.db.failOn = (sql) => sql.startsWith(`INSERT INTO "connect_links"`);
  const res = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps);
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "link db down");
  assert.ok(!("url" in body));
  assert.equal(storedLinks(r.db).length, 0);
});

// ---------------------------------------------------------------------------
// ONE CONNECT BUTTON, ONE LINK — spec page 25.
//
// THE DEFECT THESE REPRODUCE, measured on 2026-09-06 before the change: this
// route minted ONE row per call, so the setup card's single Connect button
// asked for a link per ticked app and walked the person through four separate
// browser round trips for one decision. routes/connect.ts could already DRAW,
// walk, tap, call back and skip a page of apps; nothing in the Worker could
// make one.
// ---------------------------------------------------------------------------

await check("four ticked apps become ONE link, in the order they were ticked", async () => {
  const r = await rig();
  const wanted = ["zellibrix", "quandle_mail", "borogrove", "tuletide"];
  const res = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkits: wanted }), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "page mint");
  const url = String(body.url);
  const token = url.slice(`${CONNECT_URL_BASE}/`.length);
  assert.equal(token.length, TOKEN_CHARS);
  assert.deepEqual(body.toolkits, wanted,
    "the phone ticked a set and must be told which set this link actually carries");

  const rows = storedLinks(r.db);
  assert.equal(rows.length, wanted.length, "one link per app was minted, or one app was dropped");
  // EVERY ROW AT ITS OWN DERIVED HANDLE, and app 0 at the plain one — which is
  // what makes every link already in the wild resolve unchanged.
  for (let i = 0; i < wanted.length; i++) {
    const handle = i === 0 ? sha256Hex(token) : sha256Hex(`${token} ${i}`);
    const row = rows.find((x) => x.token_handle === handle);
    assert.ok(row, `app ${i} is not at its own page handle`);
    assert.equal(row!.toolkit, wanted[i], `app ${i} is the wrong app`);
    assert.equal(row!.user_id, OWNER);
    assert.equal(row!.expires_at, NOW + LINK_TTL_MS, "one page, one expiry");
    assert.equal(row!.used_at, null);
  }
  assert.ok(!JSON.stringify(rows).includes(token),
    "the raw token reached the database on the page path");
});

await check("a page of ONE is byte-identical to the link every build in the wild mints",
  async () => {
    // THE CONTROL for the check above. `{toolkit: x}` and `{toolkits: [x]}` must
    // produce the same row at the same handle, or the compatibility story is a
    // promise rather than a structure.
    const one = await rig();
    await bodyOf(await connectionsApiRoute(
      postReq(R.link, one.ownerToken, { toolkit: "zellibrix" }), one.env, one.deps), "old shape");
    const many = await rig();
    await bodyOf(await connectionsApiRoute(
      postReq(R.link, many.ownerToken, { toolkits: ["zellibrix"] }), many.env, many.deps),
      "new shape");

    const shape = (rows: Record<string, unknown>[]) =>
      rows.map((x) => ({ ...x, token_handle: "<hash>" }));
    assert.equal(storedLinks(one.db).length, 1);
    assert.deepEqual(shape(storedLinks(many.db) as never), shape(storedLinks(one.db) as never),
      "a page of one is not the row a one-app link has always been");
  });

await check("a page too long, or naming an app twice, is refused WHOLE", async () => {
  const r = await rig();
  const bodies: Record<string, unknown>[] = [
    // Past the reader's own ceiling. Truncating would drop apps the person
    // ticked and tell nobody.
    { toolkits: Array.from({ length: MAX_PAGE_APPS + 1 }, (_, i) => `app_${i}`) },
    { toolkits: ["zellibrix", "zellibrix"] },
    { toolkits: ["zellibrix", "ZELLIBRIX"] },
    { toolkits: [] },
    { toolkits: ["zellibrix", ""] },
    { toolkits: ["zellibrix", null] },
    { toolkits: ["zellibrix", 7] },
    { toolkits: "zellibrix" },
    // Two fields disagreeing about what somebody ticked is a client bug, and
    // picking a winner would connect a set nobody chose.
    { toolkit: "zellibrix", toolkits: ["borogrove"] },
  ];
  for (const body of bodies) {
    const res = await connectionsApiRoute(postReq(R.link, r.ownerToken, body), r.env, r.deps);
    // 400 AND NOT 503, and the difference is the whole check. `mintConnectPage`
    // refuses every one of these too, as a library invariant — but it THROWS,
    // and a throw here becomes "we are broken, try again later" for a body that
    // will never be acceptable. A phone told 503 retries; a phone told 400 stops
    // and the bug is visible. Accepting either status let a mutation that
    // deleted this route's own duplicate check pass, because the refusal simply
    // moved one layer down and changed nothing the test could see.
    assert.equal(res.status, 400, `${JSON.stringify(body)} answered ${res.status}`);
    await bodyOf(res, "page refused");
  }
  assert.equal(storedLinks(r.db).length, 0,
    "a refused page still wrote rows — half a page is worse than none");
});

await check("a page that cannot be written whole writes NOTHING", async () => {
  // ALL OR NONE, which is the entire reason `putAll` is a method and not a loop
  // at the call site. A page half in the database is a person looking at fewer
  // apps than they ticked, with nothing anywhere saying which ones are missing.
  const r = await rig();
  r.db.failOn = (sql) => sql.startsWith(`INSERT INTO "connect_links"`);
  const res = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkits: ["zellibrix", "borogrove", "tuletide"] }),
    r.env, r.deps);
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "page db down");
  assert.ok(!("url" in body));
  assert.equal(storedLinks(r.db).length, 0);
});

await check("a page whose THIRD row fails rolls the first two back", async () => {
  // THE CHECK ABOVE IS NOT ENOUGH ON ITS OWN and this is the difference. It
  // fails EVERY insert, so a minter looping `put` one row at a time would pass
  // it — nothing is written either way. The property is a TRANSACTION, and only
  // a partial failure can see one: fail the third statement and the first two
  // must be gone.
  const r = await rig();
  let seen = 0;
  r.db.failOn = (sql) => sql.startsWith(`INSERT INTO "connect_links"`) && ++seen >= 3;
  const res = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkits: ["zellibrix", "borogrove", "tuletide"] }),
    r.env, r.deps);
  assert.equal(res.status, 503);
  await bodyOf(res, "page partial failure");
  assert.equal(storedLinks(r.db).length, 0,
    "two apps of a three-app page survived: the person opens their link and one app they "
    + "ticked is simply not there, with nothing anywhere saying which");
});

await check("a page of many spends ONE of the owner's six mints, not many", async () => {
  // THE OUTAGE THIS REPRODUCES, and it was live in the working tree before this
  // check existed. The budget counted `connect_links` ROWS, and a page of four
  // apps writes four of them — so ticking four apps, changing your mind and
  // ticking four again put the person over a six-an-hour ceiling and locked
  // them out of connecting ANYTHING for an hour. A rate limit that fires on the
  // second use of the feature it limits is an outage in a limit's clothing.
  //
  // A page is one link: one token, one expiry, one tap of one Connect button.
  let clock = NOW;
  const r = await rig({ now: () => clock });
  for (let i = 0; i < MAX_LINKS_PER_OWNER; i++) {
    clock = NOW + i;
    const res = await connectionsApiRoute(
      postReq(R.link, r.ownerToken, { toolkits: ["zellibrix", "borogrove", "tuletide"] }),
      r.env, r.deps);
    assert.equal(res.status, 200, `page ${i + 1} of ${MAX_LINKS_PER_OWNER}`);
    await bodyOf(res, `page ${i}`);
  }
  // 18 rows, 6 mints. The rows are the CONTROL: if the budget were still
  // counting them, the third page would already have been refused.
  assert.equal(storedLinks(r.db).length, 3 * MAX_LINKS_PER_OWNER);

  clock = NOW + MAX_LINKS_PER_OWNER;
  const over = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkits: ["zellibrix"] }), r.env, r.deps);
  assert.equal(over.status, 429, "the budget is per LINK and a page is one link");
  await bodyOf(over, "page over budget");
});

await check("a page of twelve is minted, not refused by the budget it costs one of", async () => {
  // MAX_PAGE_APPS (12) is larger than MAX_LINKS_PER_OWNER (6). Under the old
  // row-counting budget any page past six apps was refused before the minter
  // ever saw it — the ceiling on how MANY links you may ask for silently became
  // a ceiling on how many apps one page may hold, at half the declared number.
  const r = await rig();
  const wanted = Array.from({ length: MAX_PAGE_APPS }, (_, i) => `app_${i}`);
  const res = await connectionsApiRoute(
    postReq(R.link, r.ownerToken, { toolkits: wanted }), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "twelve app page");
  assert.equal((body.toolkits as string[]).length, MAX_PAGE_APPS);
  assert.equal(storedLinks(r.db).length, MAX_PAGE_APPS);
});

await check("a page body naming another owner binds every row to the signed-in one", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(postReq(R.link, r.ownerToken, {
    toolkits: ["zellibrix", "borogrove"], user_id: STRANGER, owner: STRANGER,
  }), r.env, r.deps);
  assert.equal(res.status, 200);
  await bodyOf(res, "page foreign owner named");
  assert.deepEqual(new Set(storedLinks(r.db).map((x) => x.user_id)), new Set([OWNER]),
    "a body field decided whose account a page of connect links binds");
});

// ===========================================================================
// 7. POST /me/connections/skip — SAYING NO, AND THE LADDER IT ENTERS
//
// THE DEFECT THIS SECTION REPRODUCES, measured before the route existed: no
// user action anywhere in the system recorded a decline. Onboarding's Skip
// wrote a flag into UserDefaults on the device, so `connect_nudges` never
// moved, the snooze table (14 / 45 / stop) could not be ENTERED by a human
// action, and the same person was asked again at the next scoring moment — on
// a second phone, or after a reinstall, from the first minute.
//
// Every check below reads the row out of SQLite outside the code under test.
// "It answered 200" is not the property; "the database now says no" is.
// ===========================================================================

/** `connect_nudges` as SQLite holds it, read outside the code under test. */
function storedNudges(db: FakeD1): Record<string, unknown>[] {
  return db.rows(`SELECT * FROM "connect_nudges" ORDER BY "toolkit"`);
}
const DAY_MS = 24 * 60 * 60 * 1000;
/** A slug nothing in the catalog, the seed or the Worker has ever heard of. */
const UNASKED = "plindle_docs";

await check("a skip RECORDS the decline — the row exists, and it is level 1", async () => {
  const r = await rig();
  assert.equal(storedNudges(r.db).length, 0, "no nudge row exists before the skip");

  const res = await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: UNASKED }), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "skip records");
  assert.equal(body.ok, true);
  assert.equal(body.state, "recorded");
  assert.equal(body.level, 1);

  const rows = storedNudges(r.db);
  assert.equal(rows.length, 1, "the skip wrote nothing into connect_nudges");
  assert.equal(rows[0]!.user_id, OWNER);
  assert.equal(rows[0]!.toolkit, UNASKED);
  assert.equal(rows[0]!.state, "declined");
  assert.equal(Number(rows[0]!.level), 1);
  assert.equal(Number(rows[0]!.acted_at), NOW,
    "acted_at is what separates a tap from 72 hours of silence");
  assert.equal(Number(rows[0]!.snooze_until) - NOW, 14 * DAY_MS,
    "an ordinary decline is the spec's fourteen days");

  // A DECLINE COSTS NOBODY A VENDOR ROUND TRIP. Saying no must be the cheapest
  // thing in the product, or it is the thing that gets rate-limited away.
  assert.equal(r.log.toolkit.length, 0);
  assert.equal(r.log.connections.length, 0);
});

await check("the onboarding skip is the SEVEN-day soft snooze, and it is a different row",
  async () => {
    const soft = await rig();
    const softRes = await connectionsApiRoute(
      postReq(R.skip, soft.ownerToken, { toolkit: UNASKED, onboarding: true }),
      soft.env, soft.deps);
    assert.equal(softRes.status, 200);
    await bodyOf(softRes, "skip onboarding");
    const softRow = storedNudges(soft.db)[0]!;
    assert.equal(softRow.trigger, "onboarding",
      "the row must SAY it was a setup card, or nothing downstream can tell the two apart");
    assert.equal(Number(softRow.snooze_until) - NOW, 7 * DAY_MS);
    // THE LADDER, WHICH THIS CHECK DID NOT READ UNTIL 2026-09-06 and which is
    // the whole of what "not a real decline" means. Seven days instead of
    // fourteen was the only thing measured, while the row underneath said
    // `declined` at level 1 — and level 1 raises the ask threshold from 0.50 to
    // 0.80, silencing in_task, onboarding and repeated_use for that app forever.
    assert.equal(Number(softRow.level), 0, "a skipped setup card climbed the decline ladder");
    assert.equal(softRow.state, "declined_soft");

    // THE CONTROL, AND THE POINT: the same tap without the setup card is the
    // real decline. Conflating them is what page 21 forbids in one sentence.
    const real = await rig();
    const realRes = await connectionsApiRoute(
      postReq(R.skip, real.ownerToken, { toolkit: UNASKED, onboarding: false }),
      real.env, real.deps);
    await bodyOf(realRes, "skip not onboarding");
    const realRow = storedNudges(real.db)[0]!;
    assert.equal(realRow.trigger, null);
    assert.equal(Number(realRow.level), 1, "an ordinary decline IS a rung and must still climb");
    assert.equal(realRow.state, "declined");
    assert.equal(Number(realRow.snooze_until) - NOW, 14 * DAY_MS);
    assert.notEqual(Number(softRow.snooze_until), Number(realRow.snooze_until));
  });

await check("the acknowledgement says SOFT about the row it wrote, not about the moment",
  async () => {
    // WHAT THE PHONE READS. `ConnectOnboardingPolicy.serverAgreedWithSkip` takes
    // the level and the snooze off this body and refuses to believe a skip
    // landed unless they mean what its own card means — so these two numbers are
    // the contract, not decoration.
    const soft = await rig();
    const ok = await jsonOf(await connectionsApiRoute(
      postReq(R.skip, soft.ownerToken, { toolkit: UNASKED, onboarding: true }),
      soft.env, soft.deps), "soft ack");
    assert.equal(ok.state, "recorded");
    assert.equal(ok.level, 0);
    assert.equal(ok.soft, true);
    assert.equal(Number(ok.snooze_until) - NOW, 7 * DAY_MS);

    // THE CONTROL, AND IT IS THE ONE THAT MATTERS: a row whose MOMENT is still
    // `onboarding` but which is already on the ladder. The decline it takes is a
    // real one, and a `soft` flag read off the trigger rather than off the row
    // the ladder actually wrote would answer TRUE here — telling the phone a
    // hard decline was a seven-day shrug.
    const hard = await rig();
    hard.db.db.prepare(
      `INSERT INTO connect_nudges (user_id, toolkit, state, level, snooze_until, "trigger",
         sent_at, acted_at, channel) VALUES (?,?,?,?,?,?,?,?,?)`,
    ).run(OWNER, UNASKED, "declined", 1, NOW - DAY_MS, "onboarding", NOW - 30 * DAY_MS,
      NOW - 30 * DAY_MS, "ios");
    const climbed = await jsonOf(await connectionsApiRoute(
      postReq(R.skip, hard.ownerToken, { toolkit: UNASKED, onboarding: true }),
      hard.env, hard.deps), "hard ack");
    assert.equal(climbed.state, "recorded");
    assert.equal(climbed.level, 2);
    assert.equal(climbed.soft, false,
      "the acknowledgement called a level-2 decline a soft snooze, because it read the "
      + "moment that produced the ask instead of the row the ladder wrote");
  });

await check("an absent onboarding flag is the LONGER quiet, never the shorter one", async () => {
  const r = await rig();
  await bodyOf(await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: UNASKED }), r.env, r.deps), "skip no flag");
  assert.equal(Number(storedNudges(r.db)[0]!.snooze_until) - NOW, 14 * DAY_MS,
    "not-stated must never be read as the setup card: that would shorten a snooze "
    + "nobody asked to shorten");
});

await check("an onboarding flag that is not a boolean is a 400 and writes nothing", async () => {
  for (const bad of ["true", 1, "yes", {}, []]) {
    const r = await rig();
    const res = await connectionsApiRoute(
      postReq(R.skip, r.ownerToken, { toolkit: UNASKED, onboarding: bad }), r.env, r.deps);
    assert.equal(res.status, 400, JSON.stringify(bad));
    await bodyOf(res, "skip bad flag");
    assert.equal(storedNudges(r.db).length, 0,
      "a malformed claim about the surface must not be guessed at in either direction");
  }
});

await check("a second tap does NOT walk somebody from L1 to L2", async () => {
  const r = await rig();
  const first = await jsonOf(await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: UNASKED }), r.env, r.deps), "skip once");
  assert.equal(first.state, "recorded");
  const second = await jsonOf(await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: UNASKED }), r.env, r.deps), "skip twice");
  assert.equal(second.state, "already-declined",
    "a refresh, a double tap or a retried POST must not climb the ladder");
  assert.equal(second.level, 1);
  const rows = storedNudges(r.db);
  assert.equal(rows.length, 1);
  assert.equal(Number(rows[0]!.level), 1);
  assert.equal(Number(rows[0]!.snooze_until) - NOW, 14 * DAY_MS,
    "the second tap must not have pushed the snooze out either");
});

await check("THE CONTROL: a decline after a NEW ask does climb — L2 is 45 days", async () => {
  const r = await rig();
  const store = createD1Store(r.env as never);
  await bodyOf(await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: UNASKED }), r.env, r.deps), "ladder L1");
  // The ask engine asks again once the snooze has run out. That is the only
  // thing that reopens the ladder, and it must still reopen it — a rung nobody
  // can climb is a product that stops asking after one no, which is the OTHER
  // failure and just as wrong.
  const asked = { ...storedNudges(r.db)[0]! } as Record<string, unknown>;
  await store.putNudge({
    ...(asked as never),
    state: "asked", sent_at: NOW + 20 * DAY_MS, acted_at: null, snooze_until: null,
  } as never);
  // The same database, twenty days later: only the clock moves.
  const res = await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: UNASKED }), r.env,
    { ...r.deps, now: () => NOW + 20 * DAY_MS });
  const body = await jsonOf(res, "ladder L2");
  assert.equal(body.state, "recorded");
  assert.equal(body.level, 2);
  assert.equal(Number(storedNudges(r.db)[0]!.snooze_until) - (NOW + 20 * DAY_MS), 45 * DAY_MS);
});

await check("an app this owner already has connected has nothing to decline", async () => {
  const r = await rig();
  const store = createD1Store(r.env as never);
  await store.putNudge({
    user_id: OWNER as never, toolkit: "zellibrix" as never, state: "connected", level: 0,
    snooze_until: null, trigger: null, sent_at: NOW - DAY_MS, acted_at: NOW - DAY_MS,
    channel: "sms",
  } as never);
  const body = await jsonOf(await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps), "skip connected");
  assert.equal(body.state, "nothing-to-decline");
  const row = storedNudges(r.db).find((n) => n.toolkit === "zellibrix")!;
  assert.equal(row.state, "connected",
    "declining an app they already have would stop the router using a live connection");
  assert.equal(storedConnections(r.db).length, 3, "and it must not touch the connections table");
});

await check("a signed-out skip records nothing at all", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(
    postReq(R.skip, null, { toolkit: UNASKED }), r.env, r.deps);
  assert.equal(res.status, 401);
  await bodyOf(res, "skip signed out");
  assert.equal(storedNudges(r.db).length, 0);
});

await check("a stranger cannot decline on somebody else's behalf", async () => {
  const r = await rig();
  // Every shape a caller could reach for: an owner on the body, and a whole
  // second session. Neither may put a row under OWNER.
  const res = await connectionsApiRoute(
    postReq(R.skip, r.strangerToken, { toolkit: UNASKED, user_id: OWNER, owner: OWNER }),
    r.env, r.deps);
  assert.equal(res.status, 200, "the stranger may decline for THEMSELVES");
  await bodyOf(res, "skip stranger");
  const rows = storedNudges(r.db);
  assert.equal(rows.length, 1);
  assert.equal(rows[0]!.user_id, STRANGER,
    "a body field named an owner and the row followed it — that is the wrong-person failure");
});

await check("a skip with no toolkit is a 400 and writes nothing", async () => {
  const r = await rig();
  for (const bad of [{}, { toolkit: "" }, { toolkit: "   " }, { toolkit: 7 }]) {
    const res = await connectionsApiRoute(postReq(R.skip, r.ownerToken, bad), r.env, r.deps);
    assert.equal(res.status, 400, JSON.stringify(bad));
    await bodyOf(res, "skip bad slug");
  }
  assert.equal(storedNudges(r.db).length, 0);
});

await check("a GET on /skip is 405 — a prefetcher must not decline for somebody", async () => {
  const r = await rig();
  const res = await connectionsApiRoute(getReq(R.skip, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("allow"), "POST");
  assert.equal(storedNudges(r.db).length, 0);
  await bodyOf(res, "skip GET");

  // THE CONTROL: the same route, POSTed, still records. A guard that refuses
  // both is an outage, not a guard.
  const ok = await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: UNASKED }), r.env, r.deps);
  assert.equal(ok.status, 200);
  await bodyOf(ok, "skip GET control");
  assert.equal(storedNudges(r.db).length, 1);
});

await check("a database that cannot write the decline says so — never { ok: true }", async () => {
  const r = await rig();
  r.db.failOn = (sql) => sql.startsWith(`INSERT INTO "connect_nudges"`);
  const res = await connectionsApiRoute(
    postReq(R.skip, r.ownerToken, { toolkit: UNASKED }), r.env, r.deps);
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "skip db down");
  assert.notEqual(body.ok, true,
    "a phone told its skip landed will not send it again, and the server never heard it");
  r.db.failOn = undefined;
  assert.equal(storedNudges(r.db).length, 0);
});

// ===========================================================================
// 8. GET /me/connections/signals — WHAT TO PRE-TICK, AND THE THREE EMPTIES
//
// THE DEFECT THIS SECTION REPRODUCES, measured on 2026-09-06 before the route
// existed. Spec page 45, onboarding step 2: "Which apps do you live in?" with
// "detected apps pre-selected from the email domain signal". The evidence
// table and the ranker both existed and were tested; there was no door between
// them and the phone, so `OnboardingConnectStep` passed literal empty arrays
// and pre-selected nothing. Step 2 was a heading over a search box, and the
// one screen whose whole job is "we already know what you use" said nothing.
//
// THE THREE EMPTIES ARE THE POINT, and they are three because the screen
// draws them three ways:
//
//   we looked, and you have no evidence yet   200  { items: [], state: none }
//   we could not look                         503  { state: unreadable }
//   the catalog could not name any of them    503  { state: catalog-unreadable }
//
// Collapsing the last two into the first is the confident-empty failure this
// whole file exists to prevent, wearing a new hat: a person with months of
// evidence told they have none, on the screen that then asks them to connect
// what they already live in.
// ===========================================================================

/** `app_usage_signals` as SQLite holds it, read outside the code under test. */
function storedSignals(db: FakeD1): Record<string, unknown>[] {
  return db.rows(`SELECT * FROM "app_usage_signals" ORDER BY "toolkit", "alias"`);
}

/** One piece of evidence, written through the REAL store the way signals.ts's
 *  six doors write it — the same table, the same CHECKs, the same key. The
 *  weight is handed in rather than taken from a band, because these checks are
 *  about the ORDER the route hands back and an explicit weight is the only way
 *  to state the order that is expected. */
async function seedSignal(
  env: ConnectionsApiEnv,
  row: {
    user?: string; toolkit: string; source?: string; weight: number;
    at?: number; alias?: "work" | "personal" | null;
  },
): Promise<void> {
  const store = createD1Store(env as never);
  await store.recordSignal(
    {
      user_id: (row.user ?? OWNER) as never,
      toolkit: row.toolkit,
      source: (row.source ?? "mx") as never,
      alias: row.alias ?? null,
    },
    () => ({ weight: row.weight, last_seen_at: row.at ?? NOW }),
  );
}

/** A catalog that can name any slug it is handed. The names are built from the
 *  slug so nothing in this file has to hold a list of apps either. */
const namesAnything = async (slug: string): Promise<ToolkitLike> => ({
  slug, name: `The ${slug} app`, logo: null, description: null,
  appUrl: `https://${slug}.example.invalid`, scopes: ["things.read"],
});

interface SignalItem {
  slug: string; name: string; app_url: string | null; scopes: string[];
  mail_hosts: string[];
  alias: string | null; last_seen_at: number; sources: string[];
}

await check("THE CONTROL: this owner's ranked apps come back in weight order, named",
  async () => {
    const r = await rig({ toolkit: namesAnything });
    // Deliberately seeded out of order, and one of them is the weakest thing
    // in the table — so an answer that echoed the insert order, or the table's
    // own row order, would be a different list from this one.
    await seedSignal(r.env, { toolkit: "orrery_02", weight: 0.4, source: "mx" });
    await seedSignal(r.env, { toolkit: "orrery_01", weight: 0.9, source: "observer" });
    await seedSignal(r.env, { toolkit: "orrery_03", weight: 0.1, source: "link" });

    const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
    assert.equal(res.status, 200);
    const body = await jsonOf(res, "signals control") as unknown as
      { items: SignalItem[]; state: string };
    assert.equal(body.state, "ranked");
    assert.deepEqual(body.items.map((i) => i.slug), ["orrery_01", "orrery_02", "orrery_03"],
      "the ranked order is not the order that reached the phone");

    // THE CATALOG ROW RIDES ALONG, so the phone draws a row with a name and a
    // logo without a second round trip — and it is the SAME shape ?slugs=
    // answers with, so one decoder on the phone reads both.
    const top = body.items[0]!;
    assert.equal(top.name, "The orrery_01 app");
    assert.equal(top.app_url, "https://orrery_01.example.invalid");
    assert.deepEqual(top.scopes, ["things.read"]);
    assert.deepEqual(top.sources, ["observer"]);
    assert.equal(top.last_seen_at, NOW);
    assert.equal(top.alias, null);
  });

await check("a ranked row carries the catalog's mail hosts, the same column ?slugs= carries",
  async () => {
    // Both doors feed the same screen: onboarding pre-ticks what /signals
    // ranked and offers the rest through catalog search, and the phone decodes
    // one row shape. A column on one door and not the other is a seed that
    // works or not depending on which way the person got to the app.
    const r = await rig({
      toolkit: async (slug: string): Promise<ToolkitLike> => ({
        ...(await namesAnything(slug)), mailHosts: [`mx.${slug}.example.invalid`],
      }),
    });
    await seedSignal(r.env, { toolkit: "orrery_01", weight: 0.9 });
    const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
    assert.equal(res.status, 200);
    const body = await jsonOf(res, "signals mail hosts") as unknown as { items: SignalItem[] };
    assert.deepEqual(body.items[0]!.mail_hosts, ["mx.orrery_01.example.invalid"]);
  });

await check("an owner with no evidence is told so — 200, empty, and honest", async () => {
  const r = await rig({ toolkit: namesAnything });
  const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "signals none");
  assert.deepEqual(body.items, []);
  assert.equal(body.state, "none");
  // Nothing was asked of the catalog: there was nothing to name.
  assert.deepEqual(r.log.toolkit, []);
});

await check("evidence we cannot READ is an outage, never an empty list", async () => {
  const r = await rig({ toolkit: namesAnything });
  await seedSignal(r.env, { toolkit: "orrery_01", weight: 0.9 });
  r.db.failOn = (sql) => sql.includes("app_usage_signals");
  const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
  r.db.failOn = null;
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "signals unreadable");
  assert.equal(body.state, "unreadable");
  assert.equal(body.items, undefined,
    "a database that could not be read answered with a list; the screen will paint a "
      + "clean empty state over this person's evidence");
  assert.notEqual(body.ok, true);
});

await check("a catalog that can name NOTHING is a DIFFERENT outage, and says which", async () => {
  const r = await rig({ toolkit: async (): Promise<ToolkitLike> => { throw new Error("no catalog"); } });
  await seedSignal(r.env, { toolkit: "orrery_01", weight: 0.9 });
  const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 503);
  const body = await jsonOf(res, "signals catalog down");
  // THE POINT OF THE FIELD. Both failures are 503 and the phone draws them
  // differently — one is "ask me again", the other is "we know your apps and
  // cannot name them". A single shape makes that distinction unreachable.
  assert.equal(body.state, "catalog-unreadable");
  assert.equal(body.items, undefined);
  assert.notEqual(body.ok, true);
});

await check("the three empty answers are three, not one", async () => {
  // Written as its own check because the property is about the SET: any two of
  // them collapsing is the defect, and each check above can only see its own.
  const named = await rig({ toolkit: namesAnything });
  const none = await connectionsApiRoute(getReq(R.signals, named.ownerToken), named.env, named.deps);
  const noneBody = await jsonOf(none, "three empties: none");

  const unread = await rig({ toolkit: namesAnything });
  await seedSignal(unread.env, { toolkit: "orrery_01", weight: 0.9 });
  unread.db.failOn = (sql) => sql.includes("app_usage_signals");
  const down = await connectionsApiRoute(getReq(R.signals, unread.ownerToken), unread.env, unread.deps);
  unread.db.failOn = null;
  const downBody = await jsonOf(down, "three empties: unreadable");

  const blind = await rig({ toolkit: async (): Promise<ToolkitLike> => { throw new Error("no catalog"); } });
  await seedSignal(blind.env, { toolkit: "orrery_01", weight: 0.9 });
  const dark = await connectionsApiRoute(getReq(R.signals, blind.ownerToken), blind.env, blind.deps);
  const darkBody = await jsonOf(dark, "three empties: catalog");

  const answers = [
    `${none.status}/${noneBody.state}`,
    `${down.status}/${downBody.state}`,
    `${dark.status}/${darkBody.state}`,
  ];
  assert.equal(new Set(answers).size, 3,
    `two of the three empty answers are the same shape: ${answers.join(" , ")}`);
});

await check("one app the catalog cannot name does not cost the others theirs", async () => {
  const r = await rig({
    toolkit: async (slug: string): Promise<ToolkitLike> => {
      if (slug === "orrery_02") throw new Error("no catalog row");
      return await namesAnything(slug);
    },
  });
  await seedSignal(r.env, { toolkit: "orrery_01", weight: 0.9 });
  await seedSignal(r.env, { toolkit: "orrery_02", weight: 0.5 });
  await seedSignal(r.env, { toolkit: "orrery_03", weight: 0.1 });

  const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "signals partial") as unknown as
    { items: SignalItem[]; state: string };
  assert.deepEqual(body.items.map((i) => i.slug), ["orrery_01", "orrery_03"]);
  assert.equal(body.state, "ranked");
});

await check("the cap holds: at most MAX_SIGNAL_APPS, cut from the TOP of the order", async () => {
  const r = await rig({ toolkit: namesAnything });
  // One more app than the cap, each worth strictly less than the one before,
  // so which ones survive is a fact about the cut and not about a tie.
  const wanted: string[] = [];
  for (let i = 0; i < MAX_SIGNAL_APPS + 4; i++) {
    const slug = `orrery_${String(i).padStart(2, "0")}`;
    await seedSignal(r.env, { toolkit: slug, weight: 1 - i / 100 });
    if (i < MAX_SIGNAL_APPS) wanted.push(slug);
  }
  const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await jsonOf(res, "signals cap") as unknown as { items: SignalItem[] };
  assert.equal(body.items.length, MAX_SIGNAL_APPS);
  assert.deepEqual(body.items.map((i) => i.slug), wanted,
    "the cap did not cut the ranked order; it chose within it");
  // AND IT IS A COST CEILING TOO: the apps past the cut cost no vendor round
  // trip. A cap applied after the lookups would be four requests nobody reads.
  assert.equal(r.log.toolkit.length, MAX_SIGNAL_APPS,
    `the catalog was asked ${r.log.toolkit.length} times for ${MAX_SIGNAL_APPS} rows`);
});

await check("one row per app, however many of this owner's accounts the evidence names",
  async () => {
    const r = await rig({ toolkit: namesAnything });
    await seedSignal(r.env, { toolkit: "orrery_01", weight: 0.2, alias: "personal", source: "link" });
    await seedSignal(r.env, { toolkit: "orrery_01", weight: 0.9, alias: "work", source: "observer" });
    await seedSignal(r.env, { toolkit: "orrery_02", weight: 0.5 });

    const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
    const body = await jsonOf(res, "signals aliases") as unknown as { items: SignalItem[] };
    assert.deepEqual(body.items.map((i) => i.slug), ["orrery_01", "orrery_02"],
      "one app arrived twice; the screen draws the same name, logo and checkbox twice");
    // The STRONGEST line represents the app, so the account named beside it is
    // the one the evidence is actually about.
    assert.equal(body.items[0]!.alias, "work");
    assert.equal(r.log.toolkit.length, 2, "the same app was looked up twice");
  });

await check("a stranger's evidence is never in this owner's answer", async () => {
  const r = await rig({ toolkit: namesAnything });
  await seedSignal(r.env, { toolkit: "orrery_mine", weight: 0.5 });
  await seedSignal(r.env, { user: STRANGER, toolkit: "orrery_theirs", weight: 0.99 });

  const mine = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
  const mineBody = await jsonOf(mine, "signals mine") as unknown as { items: SignalItem[] };
  assert.deepEqual(mineBody.items.map((i) => i.slug), ["orrery_mine"],
    "somebody else's apps reached this owner — and they would be pre-ticked");

  // THE CONTROL, so the check above cannot pass because the route returns
  // nothing to anybody: the stranger's own token gets the stranger's own row.
  const theirs = await connectionsApiRoute(getReq(R.signals, r.strangerToken), r.env, r.deps);
  const theirsBody = await jsonOf(theirs, "signals theirs") as unknown as { items: SignalItem[] };
  assert.deepEqual(theirsBody.items.map((i) => i.slug), ["orrery_theirs"]);
});

await check("a POST on /signals is 405", async () => {
  const r = await rig({ toolkit: namesAnything });
  const res = await connectionsApiRoute(postReq(R.signals, r.ownerToken, {}), r.env, r.deps);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("allow"), "GET");
  await bodyOf(res, "405 signals");
});

await check("reading the evidence never writes any", async () => {
  const r = await rig({ toolkit: namesAnything });
  await seedSignal(r.env, { toolkit: "orrery_01", weight: 0.9, source: "observer" });
  const before = storedSignals(r.db);
  const res = await connectionsApiRoute(getReq(R.signals, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  await bodyOf(res, "signals read-only");
  // A route that could record evidence while answering a question about it
  // would let anybody with a session weight their own table — and the weight
  // is what eventually licenses interrupting somebody.
  assert.deepEqual(storedSignals(r.db), before);
});

await check("MAX_SIGNAL_APPS is 8 — the number, not just the name", () => {
  // Every loop above counts to this constant, so only its NAME was pinned. It
  // is two things at once: the length of a pre-ticked list a person will read
  // before tapping Connect, and the number of vendor round trips one request
  // may cost. Both get worse quietly if it drifts.
  assert.equal(MAX_SIGNAL_APPS, 8,
    `MAX_SIGNAL_APPS is now ${MAX_SIGNAL_APPS}. If that is deliberate, say why here and `
      + "change this line; a pre-ticked list longer than a screen is consent by fatigue.");
  assert.ok(MAX_SIGNAL_APPS <= MAX_CATALOG_SLUGS,
    "one /signals call may now cost more vendor round trips than ?slugs= is allowed to");
});

// ===========================================================================
// THE PRODUCTION WIRING — the path src/index.ts actually takes
//
// Every check above this line injects `r.deps`. `connectionsApiDeps` — the ONLY
// wiring a real request uses, because src/index.ts calls
// `connectionsApiRoute(request, env)` with no third argument — was executed by
// nothing. Measured on 2026-09-06 with an anchor-unique mutation harness:
// replacing that function's whole body with `return null` left `npm test` at
// "60 passed, 0 failed". Sixty green checks over a path production does not
// take is the defect class that cost this repo the most that day.
//
// So this section calls the factory BY NAME, asserts each port is the shipped
// implementation by identity or by behaviour rather than by being non-null,
// and ends with the control: a request served exactly as index.ts serves one.
//
// ONE PORT OF THE VENDOR AND ONE OF THE MODEL ARE STUBBED, at `globalThis.fetch`
// and nowhere higher. Everything between these checks and that socket — the
// factory, the D1 store, the vendor adapter, the sentence writer, the words
// audit, the routes — is the shipped code.
// ===========================================================================

interface FetchCall { url: string; body: string }

interface Socket {
  calls: FetchCall[];
  /** The raw assistant text the model answers with. */
  modelText: string;
  catalogFails: boolean;
  restore(): void;
}

/** The one boundary this Worker does not control. Installed BEFORE any deps are
 *  built, because `ComposioConnections` binds `globalThis.fetch` when it is
 *  CONSTRUCTED and the isolate caches one adapter. */
function socket(): Socket {
  const real = globalThis.fetch;
  const s: Socket = {
    calls: [],
    modelText: JSON.stringify({ sentences: MODEL_LINES }),
    catalogFails: false,
    restore: () => { globalThis.fetch = real; },
  };
  globalThis.fetch = (async (input: unknown, init?: { body?: unknown }) => {
    const url = String((input as { url?: string })?.url ?? input);
    s.calls.push({ url, body: String(init?.body ?? "") });
    const reply = (status: number, value: unknown): Response =>
      new Response(JSON.stringify(value), {
        status, headers: { "content-type": "application/json" },
      });
    if (url.startsWith(COMPOSIO_BASE_URL)) {
      if (s.catalogFails) return reply(500, { error: "the vendor is down" });
      const meta = APPS.zellibrix;
      const row = {
        slug: meta.slug, name: meta.name, logo: meta.logo,
        description: meta.description, app_url: meta.appUrl, scopes: meta.scopes,
      };
      // `GET /toolkits?search=` answers a page; `GET /toolkits/{slug}` answers
      // one row. Two shapes, because the adapter reads them differently.
      return reply(200, url.includes("/toolkits?") ? { items: [row] } : row);
    }
    return reply(200, { choices: [{ message: { content: s.modelText } }] });
  }) as typeof globalThis.fetch;
  resetConnectionsProvider();
  return s;
}

/** Three lines a model could plausibly write that words.ts will accept: three of
 *  them, distinct, under 80 characters, no exclamation, no URL, none of the
 *  register the spec forbids. */
const MODEL_LINES = [
  "Anticipy can read your Zellibrix notes when you ask about them.",
  "It can add a note for you when you ask it to.",
  "You can turn this off any time in Settings.",
];

/** A Worker configured the way a deployed one is: the rig's own D1 and auth
 *  secret, plus the vendor secret and the model key production holds. */
function wiredEnv(r: Rig, over: Record<string, unknown> = {}): ConnectionsApiEnv {
  return {
    ...(r.env as unknown as Record<string, unknown>),
    COMPOSIO_API_KEY: "ck_test_not_a_real_key",
    OPENROUTER_API_KEY: "or_test_not_a_real_key",
    ...over,
  } as unknown as ConnectionsApiEnv;
}

/** A toolkit row with no scopes. `permissionSentences` refuses before the writer
 *  is called, so a refusal here proves BOTH that the audit is real and that
 *  nothing was asked to invent a permission. */
const SCOPELESS = {
  slug: "zellibrix", name: "Zellibrix", logo: null, description: null,
  appUrl: null, scopes: [] as string[],
};

await check("connectionsApiDeps hands a configured Worker deps, and neither optional port",
  async () => {
    const s = socket();
    try {
      const r = await rig();
      const deps = connectionsApiDeps(wiredEnv(r));
      assert.ok(deps, "the only wiring a real request uses handed back nothing at all");
      assert.equal(typeof deps.store.connectionsForOwner, "function");
      assert.equal(typeof deps.provider.toolkit, "function");
      assert.equal(typeof deps.words.sentences, "function");

      // SEARCH IS FILLED NOW, and this leg says the opposite of what it said an
      // hour ago. That is not drift: two agents worked the same file at once,
      // one pinning `search` as unset (true then, and the reason `?q=` answered
      // an honest 503 rather than lying about an empty catalog) while the other
      // built the provider's catalog search. Both were right in turn; the port
      // exists, so the assertion that matters is the stronger one.
      //
      // A FUNCTION IS NOT ENOUGH — the whole point of this leg is that
      // production takes a path the suite executes, so the port has to reach
      // the real provider rather than any callable. It is called.
      assert.equal(typeof deps.search, "function",
        "the search port is unfilled, so `?q=` answers 503 and 'Add an app' cannot "
          + "find anything — which is the one way into a connection nobody asked for");
      const hits = await deps.search!("a query no local list could answer");
      assert.ok(Array.isArray(hits),
        "the wired search did not answer with a list, so the box the person types "
          + "into is wired to something that is not a catalog");

      // `now` stays unset for its own reason: it is the tests' clock, and
      // production owns the real one.
      assert.equal(deps.now, undefined, "the wiring pinned the clock production owns");
    } finally { s.restore(); }
  });

await check("the wired search hands the letters to the catalog byte for byte", async () => {
  const s = socket();
  try {
    const r = await rig();
    const deps = connectionsApiDeps(wiredEnv(r))!;

    // A PHRASE, not a slug. Nothing in this Worker may read it, rank it, match
    // it against a local list of app names or answer with a did-you-mean —
    // that is deciding what somebody's words MEANT, and it belongs to the
    // catalog. HARNESS-LAWS law 1, in the one place the spec spends a
    // paragraph forbidding it.
    const typed = "where my team keeps notes";
    const found = await deps.search!(typed);
    assert.equal(found.length, 1, "the catalog's own answer did not come back");
    assert.equal(found[0].name, APPS.zellibrix.name,
      "the row that came back is not the catalog's, so the search box is answering "
        + "from somewhere inside this Worker");

    const call = s.calls.find((c) => c.url.includes("/toolkits?"));
    assert.ok(call, "the catalog was never searched, so the letters were answered locally");
    assert.ok(call.url.includes(encodeURIComponent(typed)),
      `the typed phrase did not reach the catalog unchanged: ${call.url}`);
  } finally { s.restore(); }
});

await check("the wired store is the real D1 one, over this Worker's own binding", async () => {
  const s = socket();
  try {
    const r = await rig();
    const deps = connectionsApiDeps(wiredEnv(r))!;

    // READ: the rows the rig wrote into SQLite, and only this owner's. A memory
    // store or a stub would answer an empty list here.
    const rows = await deps.store.connectionsForOwner(OWNER);
    assert.deepEqual(rows.map((c) => c.connected_account_id).sort(),
      [OWNER_ACCOUNT_2, OWNER_ACCOUNT].sort(),
      "the wired store did not read this Worker's own connections table");
    assert.ok(!rows.some((c) => c.connected_account_id === STRANGER_ACCOUNT));

    // WRITE: through the port, read back out of SQLite outside the code under
    // test. This is the assertion a `return null` factory cannot survive and a
    // fake store cannot fake.
    await deps.store.putConnection({
      user_id: OWNER as never, toolkit: "zellibrix",
      connected_account_id: "ca_OWNER_wired", alias: null, status: "connected",
      writes_enabled: false, last_used_at: null,
    });
    const stored = storedConnections(r.db)
      .filter((row) => row.connected_account_id === "ca_OWNER_wired");
    assert.equal(stored.length, 1,
      "a write through the wired store never reached this Worker's D1 binding");
  } finally { s.restore(); }
});

await check("the wired provider is the shipped adapter, from the isolate's own factory",
  async () => {
    const s = socket();
    try {
      const r = await rig();
      const env = wiredEnv(r);
      const deps = connectionsApiDeps(env)!;
      assert.ok(deps.provider instanceof ComposioConnections,
        "the catalog port is not the shipped adapter");
      assert.equal(deps.provider, connectionsFromEnv(env as never),
        "the wiring built its own adapter instead of taking the isolate's, so a session "
          + "minted for one request would be invisible to the next screen");

      // And it really talks to the catalog: the app's name comes off the wire,
      // and NOTHING in the Worker knows this app exists.
      const meta = await deps.provider.toolkit("zellibrix");
      assert.equal(meta.name, APPS.zellibrix.name);
      assert.deepEqual(meta.scopes, APPS.zellibrix.scopes);
      assert.ok(s.calls.some((c) => c.url === `${COMPOSIO_BASE_URL}/toolkits/zellibrix`),
        "the catalog was never asked, so the name came from somewhere it must not come from");
    } finally { s.restore(); }
  });

await check("the wired words port is the real audit, not three fixed lines", async () => {
  const s = socket();
  try {
    const r = await rig();
    const deps = connectionsApiDeps(wiredEnv(r))!;
    const before = s.calls.length;
    // A permission sentence written without a scope is an invention about what
    // the connection gets. A stub returning three plausible lines passes every
    // other check in this section and fails this one.
    await assert.rejects(() => deps.words.sentences(SCOPELESS as never), PermissionWordsRefused,
      "the wired words port invented sentences for a toolkit that declares no scopes");
    assert.equal(s.calls.length, before,
      "a model was asked to write permissions for a toolkit that declares none");
  } finally { s.restore(); }
});

await check("the wired sentences come from a real model call over this Worker's own LLM path",
  async () => {
    const s = socket();
    try {
      const r = await rig();
      const lines = await connectionsApiDeps(wiredEnv(r))!.words.sentences(
        APPS.zellibrix as never);
      // The model's OWN words, not a house-written replacement.
      assert.deepEqual(lines, MODEL_LINES,
        "what reached the phone is not what the model said");

      const call = s.calls.find((c) => c.url.startsWith(OPENROUTER_BASE));
      assert.ok(call,
        "no model was called, so the sentence writer here is a stub and the phone and the "
          + "connect page can describe one app two ways");
      assert.ok(call.body.includes(DEFAULT_CONNECT_MODEL),
        `the connect model is not the one this Worker holds a key for: ${call.body.slice(0, 120)}`);
      // The prompt is built from the CATALOG ROW, so an app nobody has heard of
      // still gets its own sentences.
      for (const scope of APPS.zellibrix.scopes) {
        assert.ok(call.body.includes(scope),
          `the prompt was built without the catalog's own scope ${scope}`);
      }
    } finally { s.restore(); }
  });

await check("with the DB binding unset there is no wiring, and the door still says 401",
  async () => {
    const s = socket();
    try {
      const r = await rig();
      const blind = wiredEnv(r, { DB: undefined });
      assert.equal(connectionsApiDeps(blind), null,
        "a Worker with no database handed back deps, so a store that cannot answer would be "
          + "asked for somebody's connections");

      // AND THE ROUTE ANSWERS 401, NOT 503 — worth writing down rather than
      // leaving to be found. `DB` is the ONLY hard precondition of this
      // factory, and the credential is verified against that same binding one
      // step earlier, so an unbound DB is refused at the door as "not you"
      // before it can ever be reported as "not wired". The 503 below the token
      // check is a backstop for a future precondition, not a live branch.
      const res = await connectionsApiRoute(getReq(R.list, r.ownerToken), blind);
      assert.equal(res.status, 401,
        "a Worker with no database answered something other than the signed-out answer");
      await bodyOf(res, "wiring: no DB binding");
    } finally { s.restore(); }
  });

await check("the vendor secret is NOT a precondition for these six routes, on purpose",
  async () => {
    const s = socket();
    try {
      const r = await rig();
      const noVendor = wiredEnv(r, { COMPOSIO_API_KEY: undefined });

      // DELIBERATELY NOT NULL, unlike connectDeps. Three of these six routes are
      // pure D1, and refusing them all would tell somebody with two connected
      // apps that Anticipy cannot read them because a text-generation secret is
      // unset. Each route answers for its OWN missing configuration instead.
      assert.ok(connectionsApiDeps(noVendor),
        "an unset vendor secret took down listing connections, flipping the write toggle "
          + "and minting a link, none of which the vendor is involved in");

      // Pure D1, through the production path, with no vendor at all.
      const list = await connectionsApiRoute(getReq(R.list, r.ownerToken), noVendor);
      assert.equal(list.status, 200, "an unset vendor secret hid this owner's own connections");
      const items = (await jsonOf(list, "wiring: list with no vendor")).items as unknown[];
      assert.equal(items.length, 2);

      // And the leg that DOES need the vendor fails on its own terms: an outage,
      // never `{ items: [] }`, and NOT ONE REQUEST is issued.
      const before = s.calls.length;
      const catalog = await connectionsApiRoute(
        getReq(`${R.catalog}?${QUERY_SLUGS}=zellibrix`, r.ownerToken), noVendor);
      assert.equal(catalog.status, 503, "an unconfigured catalog answered as though it worked");
      const body = await jsonOf(catalog, "wiring: catalog with no vendor");
      assert.ok(!("items" in body),
        "a Worker with no catalog told a screen with two connected apps that neither has a name");
      assert.equal(s.calls.length, before,
        "a Worker with no vendor secret still called out to the vendor");
    } finally { s.restore(); }
  });

await check("THE CONTROL: served exactly as src/index.ts serves it, with no injected deps",
  async () => {
    const s = socket();
    try {
      const r = await rig();
      const env = wiredEnv(r);

      // NO THIRD ARGUMENT. This is `connectionsApiRoute(request, env)` — the one
      // call site in src/index.ts, and the path every real phone takes. It must
      // reach the REAL store and answer with this owner's own rows.
      const mine = await connectionsApiRoute(getReq(R.list, r.ownerToken), env);
      assert.notEqual(mine.status, 503,
        "the production path answered 'not wired', which is what every phone would get");
      assert.equal(mine.status, 200);
      const items = (await jsonOf(mine, "wiring: control list")).items as
        Record<string, unknown>[];
      assert.deepEqual(items.map((row) => row.connected_account_id).sort(),
        [OWNER_ACCOUNT_2, OWNER_ACCOUNT].sort(),
        "the production path answered from something other than this Worker's own D1");
      assert.ok(!items.some((row) => row.user_id !== OWNER),
        "a stranger's row reached this owner through the production path");

      // THE DIFFERENCE BETWEEN 'NOT WIRED' AND 'NOT YOU', on the same Worker and
      // the same route, one credential apart. A 503 to a signed-out caller would
      // mean the wiring is broken; a 401 means it is fine and they are not
      // signed in — and the phone renders those two as different screens.
      const nobody = await connectionsApiRoute(getReq(R.list), env);
      assert.equal(nobody.status, 401, "a signed-out caller was told about the wiring");
      const refused = await jsonOf(nobody, "wiring: control signed out");
      assert.equal(refused.ok, false);
      assert.ok(!("items" in refused));

      // Neither call cost this Worker a vendor round trip: the list is pure D1
      // and the 401 is decided before anything is built.
      assert.equal(s.calls.length, 0,
        "the production path called the vendor to answer a question about our own table");
    } finally { s.restore(); }
  });

// ===========================================================================
// THE WHOLE-SUITE SCANS
// ===========================================================================

await check("nothing this file can answer uses the forbidden register", () => {
  assert.ok(BODIES.length > 40, `only ${BODIES.length} bodies were collected; the scan is thin`);
  for (const { where, text } of BODIES) {
    // OUR OWN CONNECT BASE IS STRIPPED FIRST, and nothing else is. It is a
    // hostname in a machine-readable field the phone opens and never shows, and
    // it happens to contain "api" between two dots — which is a boundary, so
    // the same whole-word rule words.ts uses trips on our own host. Every OTHER
    // URL survives the strip, so a raw vendor link in a body still trips
    // "composio" here, which is the thing this scan exists to catch.
    const hay = text.toLowerCase().split(CONNECT_URL_BASE.toLowerCase()).join(" ");
    for (const term of FORBIDDEN_TERMS) {
      // Whole word or whole phrase, so "capital" does not trip "api" — the same
      // rule words.ts applies, because a scan looser than the audit would
      // report failures the product does not have.
      const re = new RegExp(`(^|[^a-z0-9])${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}($|[^a-z0-9])`);
      assert.ok(!re.test(hay), `${where} said "${term}": ${text.slice(0, 160)}`);
    }
  }
});

await check("every answer is no-store and typed as JSON", async () => {
  const r = await rig();
  const answers = [
    await connectionsApiRoute(getReq(R.list, r.ownerToken), r.env, r.deps),
    await connectionsApiRoute(getReq(R.list), r.env, r.deps),
    await connectionsApiRoute(getReq("/me/connections/nope", r.ownerToken), r.env, r.deps),
    await connectionsApiRoute(getReq(R.link, r.ownerToken), r.env, r.deps),
  ];
  for (const res of answers) {
    assert.equal(res.headers.get("cache-control"), "no-store", String(res.status));
    if (res.status !== 405) {
      assert.equal(res.headers.get("content-type"), "application/json; charset=utf-8");
      assert.equal(res.headers.get("x-content-type-options"), "nosniff");
    }
    await bodyOf(res, "header scan");
  }
});

await check("no app is named in the route's source", () => {
  // Every check above ran on two apps invented for this file. If either name
  // appears in the shipped source, something was hardcoded and "a new app in
  // the catalog is a new app in Anticipy with zero code" is false.
  for (const name of ["Zellibrix", "zellibrix", "Quandle", "quandle_mail"]) {
    assert.ok(!SOURCE.includes(name), `the route names ${name}`);
  }
});

await check("no REAL app is named in the route's executable code either", () => {
  // LAW 1, over the shipped source rather than over behaviour. The two invented
  // names above only catch a hardcode somebody copied out of this file; the way
  // a search box actually acquires a local opinion is one `if (q === "gmail")`
  // added in a hurry, and no behavioural check catches a case nobody wrote.
  //
  // Comments are removed first, because this file discusses real apps in prose
  // and must go on being allowed to. STRING LITERALS ARE KEPT: a name in a
  // literal is exactly the violation.
  //
  // The stripper is line-based, which is only sound while no CODE line in this
  // file contains "//" — inside a string or a regex it would cut the line in
  // half and the scan would silently measure less than it claims. That
  // precondition is the first control below. (test/connections-provider.test.ts
  // carries the character-level scanner, because the adapter has both `"://"`
  // and regex literals in code; this file has neither, and a second copy of 60
  // lines of scanner is its own kind of drift.)
  const code = SOURCE
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .map((line) => line.replace(/\/\/.*$/, ""))
    .join("\n");

  // CONTROL 1 — the precondition the stripper rests on.
  for (const line of code.split("\n")) {
    assert.ok(!line.includes("//"),
      `a code line in connections_api.ts now contains "//": ${line.trim()}. The line-based `
        + "strip above is no longer sound; use the scanner in connections-provider.test.ts.");
  }
  // CONTROL 2 — prose really went, and code really stayed.
  assert.ok(SOURCE.includes("one mailbox served everybody")
    || SOURCE.includes("mailbox was connected by hand"));
  assert.ok(!code.includes("mailbox was connected by hand"), "the stripper left comments in");
  assert.ok(code.includes("MAX_SEARCHES_PER_OWNER"), "the stripper ate code");
  assert.ok(code.includes("Sign in first."), "the stripper ate a string literal");

  const APP_NAMES = [
    "gmail", "googlecalendar", "googledrive", "google_drive", "outlook", "notion",
    "slack", "dropbox", "salesforce", "github", "gitlab", "linear", "asana",
    "trello", "hubspot", "shopify", "zoom", "jira", "confluence", "calendly",
    "airtable", "discord", "telegram", "whatsapp", "spotify", "figma",
  ];
  const found = (hay: string): string[] => APP_NAMES.filter((name) =>
    new RegExp(`(^|[^a-z0-9_])${name}($|[^a-z0-9_])`, "i").test(hay));

  // CONTROL 3 — the scan finds a name when one IS in a branch. Without this,
  // the assertion below passes for a scan that matches nothing at all.
  assert.deepEqual(found('if (q.toLowerCase().includes("gmail")) return refuse(404, x);'), ["gmail"]);

  assert.deepEqual(found(code), [],
    `src/routes/connections_api.ts names ${found(code).join(", ")} in code. Which app somebody `
      + "meant is the catalog's question; a name here is this Worker answering it.");
});

await check("the phone and the connect page share one sentence writer", () => {
  // A second construction here would be a second answer to what an app is
  // allowed to say about itself, and the two would diverge the first time one
  // was edited.
  const anchor = "makePermissionWords(makeSentenceWriter(env))";
  const mine = SOURCE.split(anchor).length - 1;
  const theirs = WIRING_SOURCE.split(anchor).length - 1;
  assert.equal(mine, 1, `the route builds the sentence writer ${mine} times, not once`);
  assert.equal(theirs, 1,
    "src/connections/wiring.ts no longer builds the connect page's writer this way; "
      + "the phone and the page can now describe one app two ways");
});

await check("the vendor's name is nowhere in the source either", () => {
  assert.ok(!/composio/i.test(SOURCE.replace(/^.*provider\.ts.*$/gm, "")),
    "the route's own text names the vendor outside an import path");
});

// ===========================================================================
// MUTATIONS RUN AGAINST src/routes/connections_api.ts, 2026-09-06.
//
// Each is anchored on a literal occurring EXACTLY ONCE in that file — the
// script refuses to patch otherwise, because a regex that silently fails to
// match produces a false "it is tested" reading, and that mistake was made
// twice in this repo on 2026-09-05. ALL TWENTY WENT RED; the check each one
// killed is named beside it. Number 2 SURVIVED the first run and the check that
// kills it ("an account whose id is not an owner ROW id is refused, not 500ed")
// was written because of that, not before it.
//
//   1  the 401 gate made unreachable
//      -> "no credential is 401 on every leg, and nothing is touched"
//   2  `return /^[a-z0-9]{15}$/.test(id) ? id : null;` -> `return id;`
//      -> "an account whose id is not an owner ROW id is refused, not 500ed"
//   3  a foreign row in a write batch filtered (`continue`) instead of refused
//      -> "a batch naming somebody else's account writes NOTHING"
//   4  validate-then-write collapsed into one pass
//      -> "a batch naming somebody else's account writes NOTHING"
//   5  `if (on !== true && on !== false)` -> `if (on === undefined)`
//      -> "writes_enabled must be a real boolean"
//   6  the request body spread over the stored row
//      -> "the body cannot change anything but the toggle"
//   7  the stored-toolkit cross-check removed
//      -> "a toolkit that disagrees with the stored row is refused"
//   8  the not-yours gate removed from disconnect
//      -> "somebody else's account id is a 404 and reaches no vendor call"
//   9  `revoked: out?.revoked === true` -> `revoked: true`
//      -> "an unrevokable account never reads as revoked"
//  10  `deleted: out?.deleted === true && localDeleted` -> `deleted: true`
//      -> "our own row surviving is reported, not smoothed over"
//  11  a dead vendor answered 200 with a result shape
//      -> "a vendor that will not answer means nothing is deleted"
//  12  `if (items.length === 0 && failures > 0)` -> `if (false)`
//      -> "every slug unreadable is an outage, not an empty catalog"
//  13  `if (recent >= MAX_LINKS_PER_OWNER)` -> `if (false)`
//      -> "the mint budget stops the seventh link in an hour"
//  14  handleList's 503 -> `json(200, { items: [] })`
//      -> "a database that cannot answer is never an empty list"
//  15  the unwired search arm's 503 -> `json(200, { items: [] })`
//      -> "?q= with no search port is an outage, never an empty catalog"
//  16  `if (!vendorHolds)` -> `if (false)`
//      -> "a row the vendor no longer holds can still leave the screen"
//  17  the sentences floor made unreachable
//      -> "no sentences is never an empty list"
//  18  `if (method !== wants)` -> `if (false)`
//      -> "a GET on /link is 405 and mints nothing"
//  19  a failed vendor listing read as "they do not hold it"
//      -> "a catalog that cannot list means the vendor is never asked to delete"
//  20  `app_url` handed over as `appUrl`
//      -> "?slugs= describes the toolkits it was given"
//
// ALL TWENTY RAN AGAINST INJECTED DEPS, and none of them touched the wiring.
// A twenty-first, run 2026-09-06 with the same harness, is why the production
// section above exists:
//
//  21  `connectionsApiDeps`'s whole body -> `return null`
//      -> SURVIVED. "60 passed, 0 failed." The function is the ONLY wiring a
//         real request uses — src/index.ts calls
//         `connectionsApiRoute(request, env)` with no third argument — so
//         sixty green checks were describing a path production does not take.
//
// FIVE MORE, RUN AFTER THAT SECTION WAS WRITTEN, ALL KILLED:
//  21  `connectionsApiDeps` -> `return null`
//      -> "THE CONTROL: served exactly as src/index.ts serves it, with no
//         injected deps" (and eight others)
//  22  the store swapped for one whose write and read are no-ops
//      -> "the wired store is the real D1 one, over this Worker's own binding"
//  23  `words` swapped for a stub returning three fixed lines
//      -> "the wired words port is the real audit, not three fixed lines"
//  24  `connectionsFromEnv(env)` -> a second adapter under another key
//      -> "the wired provider is the shipped adapter, from the isolate's own
//         factory"
//  25  the `search:` line deleted from the returned deps
//      -> "the wired search hands the letters to the catalog byte for byte"
//
// AND THE SEARCH BOX ITSELF, 2026-09-06 — the finding that `?q=` answered 503
// unconditionally because `ConnectionsApiDeps.search` was declared and nothing
// filled it. Numbers 26-36 patch this file's route; the adapter's own eleven
// are in test/connections-provider.test.ts.
//
//  26  `search: (query) => provider.search(query)` deleted from
//      `connectionsApiDeps` — the defect exactly as it shipped
//      -> "the real wiring FILLS the search port, so ?q= is not a permanent 503"
//  27  `if (query.trim() === "")` -> `if (false)`
//      -> "?q= with nothing typed is a 400 and the catalog is never asked"
//  28  that same blank branch's 400 -> 503
//      -> "?q= with nothing typed is a 400 and the catalog is never asked"
//  29  `hits.slice(0, MAX_SEARCH_RESULTS)` -> `hits`
//      -> "the route cuts a search answer to MAX_SEARCH_RESULTS"
//  30  `if (!spendSearch(owner, now))` -> `if (false)`
//      -> "the search budget stops the owner past the ceiling, and asks the
//         catalog nothing"
//  31  the same branch left in place but the port called before it
//      -> "the search budget stops the owner past the ceiling…"
//  32  `spendSearch(owner, now)` -> `spendSearch("everybody", now)`
//      -> "the search budget is per owner: one owner's spend is not another's"
//  33  the window filter dropped, so a spend never expires
//      -> "the search budget is a WINDOW: an hour later the same owner is served"
//  34  the refusal branch made to record its own attempt (SURVIVED first run)
//      -> "the search budget is a WINDOW: an hour later the same owner is served"
//  35  the 429 answered as `json(200, { items: [] })`
//      -> "the search budget stops the owner past the ceiling…"
//  36  the 401 gate made to fall through for the catalog leg only, and
//      `if (query.toLowerCase().includes("gmail")) …` added to searchCatalog
//      -> "an anonymous caller cannot spend anybody's search budget" and
//         "no REAL app is named in the route's executable code either"
//  37  the guard around the row mapping removed, so a port answering
//      `[meta, null, "gmail"]` throws out of the handler
//      -> "a search answer holding junk is an outage, not a 500 and not a
//         short list"
// ===========================================================================

await check("/me/connections: the status the store holds is the status the phone reads", async () => {
  // THE FIELD THE WHOLE NEEDS-RECONNECT SURFACE CROSSES ON, and until now
  // nothing asserted it. Every fixture in this file was `status: "connected"`,
  // so an audit on 2026-09-06 replaced `status: c.status` with
  // `status: "connected"` — a hardcode reporting a dead credential, and the
  // disconnected stranger's row, as live — and all 80 checks stayed green.
  //
  // The expiry webhook writes `needs_reconnect`, and this route is the ONLY way
  // that reaches the phone: connections_api returns it verbatim and the phone's
  // ConnectionsPolicy.statusLine turns it into "Needs connecting again". A
  // constant here means a person is told an app is working while every request
  // through it fails, and the ask to fix it never appears.
  const r = await rig();
  // The rig seeds every row `connected`, which is exactly the blind spot. One
  // row is moved to `needs_reconnect` through the real store, the way the
  // expiry webhook moves it.
  const store = createD1Store(r.env as never);
  await store.putConnection({
    user_id: OWNER as never, toolkit: "quandle_mail",
    connected_account_id: OWNER_ACCOUNT_2, alias: "work",
    status: "needs_reconnect", writes_enabled: false, last_used_at: null,
  } as StoredConnection);

  const res = await connectionsApiRoute(getReq(R.list, r.ownerToken), r.env, r.deps);
  assert.equal(res.status, 200);
  const body = await res.json() as { items: { toolkit: string; status: string }[] };
  const byToolkit = new Map(body.items.map((i) => [i.toolkit, i.status]));

  assert.equal(byToolkit.get("quandle_mail"), "needs_reconnect",
    "a connection the vendor said had expired is reported to the phone as something "
      + "else; the person is told it works while every request through it fails");
  // THE CONTROL, and the reason one row is not enough: a route returning a
  // constant "needs_reconnect" would pass the line above and be just as wrong.
  assert.equal(byToolkit.get("zellibrix"), "connected",
    "a live connection is no longer reported as connected");
  assert.ok(new Set(byToolkit.values()).size > 1,
    "every row came back with the same status, so this route is not reading the store");
});


await check("MAX_LINKS_PER_OWNER is 6 — the number, not just the name", () => {
  // THE 429 CEILING ON CONNECT-LINK MINTING, and it was asserted only against itself.
  // Raised 6 -> 600 by the same audit with all 80 checks green. Each link is a
  // single-use door into somebody's account for ten minutes; how many may be open
  // at once is the security property, and the loops that mint them all count to
  // this constant, so only its NAME was pinned and never its size.
  assert.equal(MAX_LINKS_PER_OWNER, 6,
    `MAX_LINKS_PER_OWNER is now ${MAX_LINKS_PER_OWNER}. If that is deliberate, say why here `
      + "and change this line; a ceiling must not move by accident.");
});


console.log(`\n${passes} passed, ${failures} failed`);
if (failures > 0) process.exit(1);
