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
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import { createD1Store, forgetLiveColumns, type StoredConnection } from "../src/connections/store.ts";
import { FORBIDDEN_TERMS } from "../src/connections/words.ts";
import { LINK_TTL_MS } from "../src/connections/nudge.ts";
import { CONNECT_URL_BASE, TOKEN_CHARS } from "../src/routes/connect.ts";
import {
  connectionsApiRoute,
  parseConnectionsApiPath,
  CONNECTIONS_API_ROUTES,
  QUERY_SEARCH,
  QUERY_SLUGS,
  MAX_LINKS_PER_OWNER,
  LINK_WINDOW_MS,
  MAX_CATALOG_SLUGS,
  MAX_WRITE_ROWS,
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
  },
  quandle_mail: {
    slug: "quandle_mail", name: "Quandle Mail", logo: null,
    description: null, appUrl: null, scopes: ["mail.read"],
  },
};

interface ToolkitLike {
  slug: string; name: string; logo: string | null; description: string | null;
  appUrl: string | null; scopes: string[];
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

await check("the six paths are the six the phone's client declares", () => {
  // ConnectedAppsClient.Route. The phone builds every URL from these literals
  // and nothing else; a route renamed on either side must be red here rather
  // than a 404 on somebody's phone.
  const declared = [...CLIENT_SWIFT.matchAll(/static let \w+ = "(me\/connections[^"]*)"/g)]
    .map((m) => "/" + (m[1] as string));
  assert.equal(declared.length, 6,
    "ConnectedAppsClient.Route no longer declares six routes; this file's census is stale");
  const served = Object.values(R).slice().sort();
  assert.deepEqual(declared.slice().sort(), served,
    "the phone's routes and this Worker's routes have drifted apart");
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
  const r = await rig();
  for (let i = 0; i < MAX_LINKS_PER_OWNER; i++) {
    const res = await connectionsApiRoute(
      postReq(R.link, r.ownerToken, { toolkit: "zellibrix" }), r.env, r.deps);
    // THE CONTROL: every one under the ceiling must work, or the limit is an
    // outage rather than a limit.
    assert.equal(res.status, 200, `link ${i + 1} of ${MAX_LINKS_PER_OWNER}`);
    await bodyOf(res, `link ${i}`);
  }
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
// ===========================================================================

console.log(`\n${passes} passed, ${failures} failed`);
if (failures > 0) process.exit(1);
