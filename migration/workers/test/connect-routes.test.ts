/**
 * test/connect-routes.test.ts — the three /c/{token} legs, driven as HTTP.
 *
 *   node --experimental-strip-types migration/workers/test/connect-routes.test.ts
 *
 * WHAT IS REAL HERE AND WHAT IS NOT. The handler, the routing, the session
 * check, the HTML, the status codes and the whole four-state core are the
 * shipped code. The account token is a real HMAC-signed one from src/pb/auth.ts
 * against a real `owners` row in a real SQLite loaded from migration/d1/
 * schema.sql — so "signed in" here means what it means in production, and a
 * stranger's token is a stranger's token rather than a string a fake believed.
 *
 * The three injected ports are fakes because they are three other modules: the
 * `connect_links` store (whose D1 tables are not in schema.sql yet), the vendor
 * client, and the model that writes the sentences. The store fake is written to
 * the interface's OWN rule — compare-and-set with no `await` between the read
 * and the write — because the property being tested is single-use under a race,
 * and a fake that read-then-wrote would pass a test the real store would fail.
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH, each with its own check below:
 *
 *   THE ORACLE. Until 2026-09-05 a signed-out caller could sort strings into
 *   "a real Anticipy token" and "not one" — a live token answered one way and
 *   an invented one another — which is exactly the fact whoever intercepted the
 *   text wants, available for free and without spending the link. Five tokens
 *   in five different states must produce ONE response, byte for byte, on all
 *   three legs, and the store must not be read at all.
 *
 *   THE WRONG PERSON. The spike's `connectPageDone` wrote the callback's
 *   `connected_account_id` verbatim, and its own docstring claimed that could
 *   not bind one person's mailbox to another. It could: the id is on a query
 *   string a browser can edit. Four checks here try it — an account the vendor
 *   holds for somebody else, an account the vendor does not hold at all, an
 *   account on another toolkit, and a made-up one.
 *
 *   THE VENDOR URL. Every link a person is given is ours. The vendor's URL may
 *   exist in exactly one place in this Worker's output: the Location header of
 *   the one redirect from /go. Every body of every response every check makes
 *   is collected and scanned for it at the end of the file.
 *
 *   THE REGISTER. "Composio", "authorize", "permissions", "integration", "API",
 *   "OAuth" — the same collected bodies are scanned for all of them.
 *
 * MUTATIONS THIS FILE MUST GO RED ON (run, not asserted — see the report):
 *   the session check moved after the store read in `locate`; the used-token and
 *   unknown-token answers separated for an anonymous caller; `vendorVouchesFor`
 *   made to trust the query string; the owner comparison in it dropped; the
 *   lease taken as a receipt (no `release` on a failed write); /go accepting
 *   GET; the cross-site refusal deleted; `writes_enabled` defaulting true.
 */
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import {
  connectRoute, tokenHandle, callbackUrl, connectWiringInstalled,
  CALLBACK_WINDOW_MS, LINK_TTL_MS, SESSION_COOKIE,
  type ClaimOutcome, type ConnectDeps, type ConnectEnv, type ConnectLinkStore,
  type Connection, type StoredLink, type ToolkitMeta,
} from "../src/routes/connect.ts";

const here = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(here, "..", "src", "routes", "connect.ts"), "utf8");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

// Every body every check produces, for the two whole-suite scans at the end.
const BODIES: { where: string; text: string }[] = [];
async function bodyOf(res: Response, where: string): Promise<string> {
  const text = await res.text();
  BODIES.push({ where, text });
  return text;
}

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const NOW = 1_757_000_000_000;          // a fixed instant; every check owns time
const PB_NOW = "2026-09-05 12:00:00.000Z";
const OWNER = "ownerrefaaaaaa1";        // 15 lowercase alphanumerics, as D1 mints
const STRANGER = "strangerowner12";   // 15, like every id D1 mints
const VENDOR_URL = "https://vendor.example.invalid/link/abc123?scopes=read";

/**
 * The store, to the interface's own rule: `claim`, `complete` and `release` are
 * compare-and-sets with NO await between the read and the write. An async
 * function body runs synchronously to its first await, so on one event loop the
 * check and the set cannot be interleaved — which is the exact property D1's
 * single-statement UPDATE gives for real. A fake that read, awaited, then wrote
 * would let both of two concurrent taps win and this suite would call the
 * double-redeem bug a pass.
 */
class MemoryStore implements ConnectLinkStore {
  rows = new Map<string, StoredLink>();
  /** How many times the store was ASKED anything. The anonymous path must leave
   *  this at zero: a round trip is the same oracle read off a stopwatch. */
  reads = 0;

  put(row: StoredLink): void { this.rows.set(row.token_handle, { ...row }); }

  async read(handle: string): Promise<StoredLink | null> {
    this.reads++;
    const row = this.rows.get(handle);
    return row ? { ...row } : null;
  }

  async claim(handle: string, usedAt: number): Promise<ClaimOutcome> {
    this.reads++;
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.used_at !== null) return { won: false, row: { ...row } };
    const next: StoredLink = { ...row, used_at: usedAt };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }

  async complete(handle: string, completedAt: number): Promise<ClaimOutcome> {
    this.reads++;
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.completed_at !== null) return { won: false, row: { ...row } };
    const next: StoredLink = { ...row, completed_at: completedAt };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }

  async release(handle: string, completedAt: number): Promise<ClaimOutcome> {
    this.reads++;
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.completed_at !== completedAt) return { won: false, row: { ...row } };
    const next: StoredLink = { ...row, completed_at: null };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }
}

/** Two invented apps. NOTHING in the Worker knows these names — that is the
 *  point of running the whole flow on them. */
const APPS: Record<string, ToolkitMeta> = {
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

interface ProviderLog {
  authorize: { user: string; toolkit: string; callbackUrl: string; alias: unknown }[];
  connections: string[];
  toolkit: string[];
}

interface Rig {
  db: FakeD1;
  env: ConnectEnv;
  deps: ConnectDeps;
  store: MemoryStore;
  log: ProviderLog;
  written: Connection[];
  token: string;
  ownerToken: string;
  strangerToken: string;
}

interface RigOpts {
  toolkit?: string;
  alias?: "work" | "personal" | null;
  /** What the vendor says it holds for the owner it is asked about. */
  vendorHolds?: (owner: string) => Connection[];
  authorize?: () => Promise<{ redirectUrl: string }>;
  sentences?: (meta: ToolkitMeta) => Promise<string[]>;
  onConnected?: (c: Connection) => Promise<void>;
  now?: () => number;
  expiresAt?: number;
  usedAt?: number | null;
}

async function b64urlToken(): Promise<string> {
  return randomBytes(32).toString("base64url");
}

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
    ANTICIPY_AUTH_SECRET: "connect-routes-test-secret",
  } as unknown as ConnectEnv;

  const slug = opts.toolkit ?? "zellibrix";
  const store = new MemoryStore();
  const token = await b64urlToken();
  store.put({
    token_handle: await tokenHandle(token),
    user_id: OWNER,
    toolkit: slug,
    alias: opts.alias ?? null,
    expires_at: opts.expiresAt ?? NOW + LINK_TTL_MS,
    used_at: opts.usedAt ?? null,
    completed_at: null,
  });

  const log: ProviderLog = { authorize: [], connections: [], toolkit: [] };
  const written: Connection[] = [];
  const vendorHolds = opts.vendorHolds ?? ((owner: string): Connection[] => [{
    user_id: owner, toolkit: slug, connected_account_id: "ca_VENDOR_1", alias: null,
    status: "connected", writes_enabled: false, last_used_at: null,
  }]);

  const deps: ConnectDeps = {
    store,
    provider: {
      async toolkit(s: string): Promise<ToolkitMeta> {
        log.toolkit.push(s);
        const meta = APPS[s];
        if (!meta) throw new Error(`no catalog row for ${s}`);
        return meta;
      },
      async authorize(user, toolkit, o): Promise<{ redirectUrl: string }> {
        log.authorize.push({ user, toolkit, callbackUrl: o.callbackUrl, alias: o.alias ?? null });
        return opts.authorize ? await opts.authorize() : { redirectUrl: VENDOR_URL };
      },
      async connections(user): Promise<Connection[]> {
        log.connections.push(user);
        return vendorHolds(user);
      },
    },
    words: {
      sentences: opts.sentences ?? (async (meta: ToolkitMeta) => [
        `Anticipy can read your ${meta.name} for the things you ask about.`,
        `It can add to your ${meta.name} when you ask it to.`,
        "You can turn this off any time in Settings.",
      ]),
    },
    onConnected: opts.onConnected ?? (async (c: Connection) => { written.push(c); }),
    now: opts.now ?? (() => NOW),
  };

  return {
    db, env, deps, store, log, written, token,
    ownerToken: await issueToken(env as never, OWNER, "key-owner"),
    strangerToken: await issueToken(env as never, STRANGER, "key-stranger"),
  };
}

// --- requests ---------------------------------------------------------------

type Who = { header?: string; cookie?: string } | null;

function headersFor(who: Who, extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { ...extra };
  if (who?.header) h.Authorization = who.header;
  if (who?.cookie) h.Cookie = who.cookie;
  return h;
}

const asHeader = (t: string): Who => ({ header: t });
const asCookie = (t: string): Who => ({ cookie: `${SESSION_COOKIE}=${t}` });

function getReq(path: string, who: Who = null, extra: Record<string, string> = {}): Request {
  return new Request("https://anticipy.ai" + path, { headers: headersFor(who, extra) });
}

function postReq(
  path: string, who: Who = null,
  opts: { form?: Record<string, string>; origin?: string | null; fetchSite?: string } = {},
): Request {
  const extra: Record<string, string> = {};
  // Browsers send Origin on every POST; the default here is our own, so the
  // cross-site guard is exercised in its ALLOW direction on every other check.
  const origin = opts.origin === undefined ? "https://anticipy.ai" : opts.origin;
  if (origin !== null) extra.Origin = origin;
  if (opts.fetchSite) extra["Sec-Fetch-Site"] = opts.fetchSite;
  const body = new URLSearchParams(opts.form ?? {});
  return new Request("https://anticipy.ai" + path, {
    method: "POST",
    headers: { ...headersFor(who, extra), "content-type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
}

/** Status + body + every header, as one comparable string. Two responses that
 *  differ anywhere differ here. */
async function fingerprint(res: Response, where: string): Promise<string> {
  const text = await bodyOf(res, where);
  const headers = [...res.headers.entries()].sort().map(([k, v]) => `${k}: ${v}`).join("\n");
  return `${res.status}\n${headers}\n\n${text}`;
}

/** The five states a token can be in, all as tokens an anonymous caller might
 *  present. Each is a separate rig so nothing leaks between them. */
async function fiveTokens(): Promise<{ label: string; r: Rig; token: string }[]> {
  const live = await rig();
  const expired = await rig({ expiresAt: NOW - 1 });
  const used = await rig({ usedAt: NOW - 1000 });
  const other = await rig();
  // Somebody else's link, in the same store, live and untouched.
  other.store.put({
    token_handle: await tokenHandle(other.token), user_id: STRANGER, toolkit: "zellibrix",
    alias: null, expires_at: NOW + LINK_TTL_MS, used_at: null, completed_at: null,
  });
  const unknown = await rig();
  return [
    { label: "live", r: live, token: live.token },
    { label: "expired", r: expired, token: expired.token },
    { label: "already used", r: used, token: used.token },
    { label: "another owner's", r: other, token: other.token },
    { label: "never minted", r: unknown, token: await b64urlToken() },
  ];
}

// ===========================================================================
// ROUTING AND METHOD
// ===========================================================================

await check("the owner's own live link renders the app the catalog named", async () => {
  const r = await rig();
  const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 200);
  const html = await bodyOf(res, "view ok");
  assert.match(html, /Connect your Zellibrix/, "the app's name comes from the catalog row");
  assert.match(html, /Where your team keeps its notes\./, "so does its description");
  assert.equal(r.log.toolkit[0], "zellibrix", "the catalog is asked for the slug on the link");
});

await check("a GET on /go is refused — a prefetcher must not spend the link", async () => {
  const r = await rig();
  const res = await connectRoute(getReq(`/c/${r.token}/go`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("allow"), "POST");
  assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, null,
    "a refused method must not have consumed the token");
  assert.equal(r.log.authorize.length, 0, "and must not have asked the vendor for anything");

  // THE CONTROL: the same link, POSTed, still works. A guard that refuses both
  // is an outage, not a guard.
  const ok = await connectRoute(
    postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(ok.status, 303);
});

await check("a POST on the page itself is refused with Allow: GET", async () => {
  const r = await rig();
  const res = await connectRoute(postReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("allow"), "GET");
});

await check("a path that is not one of the three shapes is a 404, not a 500", async () => {
  const r = await rig();
  for (const path of ["/c/short", "/c/" + r.token + "/../go", "/c/" + r.token + "/extra"]) {
    const res = await connectRoute(getReq(path, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 404, path);
    await bodyOf(res, "404 " + path);
  }
});

// ===========================================================================
// THE ORACLE — the whole reason the session is settled before the lookup
// ===========================================================================

await check("signed out, five different tokens give ONE answer, byte for byte, on /c/{token}",
  async () => {
    const seen = new Map<string, string[]>();
    for (const { label, r, token } of await fiveTokens()) {
      const res = await connectRoute(getReq(`/c/${token}`), r.env, r.deps);
      const fp = await fingerprint(res, `anon view ${label}`);
      seen.set(fp, [...(seen.get(fp) ?? []), label]);
      assert.equal(r.store.reads, 0,
        `the store was asked about a ${label} token by a caller who proved nothing — `
        + "that round trip is the oracle, read off a stopwatch instead of a status code");
    }
    assert.equal(seen.size, 1,
      "an anonymous caller can sort tokens into states: " + JSON.stringify([...seen.values()]));
  });

await check("signed out, five different tokens give ONE answer on /go — and spend nothing",
  async () => {
    const seen = new Set<string>();
    for (const { label, r, token } of await fiveTokens()) {
      const res = await connectRoute(postReq(`/c/${token}/go`), r.env, r.deps);
      seen.add(await fingerprint(res, `anon go ${label}`));
      assert.equal(r.store.reads, 0, `the store was read on an anonymous /go (${label})`);
      assert.equal(r.log.authorize.length, 0, "the vendor was asked by an anonymous caller");
    }
    assert.equal(seen.size, 1, "an anonymous POST can tell the five states apart");
    // The live one specifically: still unspent, so the owner's own tap works.
    const live = (await fiveTokens())[0]!;
    assert.equal(live.r.store.rows.get(await tokenHandle(live.token))!.used_at, null);
  });

await check("signed out, five different tokens give ONE answer on /done", async () => {
  const seen = new Set<string>();
  for (const { label, r, token } of await fiveTokens()) {
    const res = await connectRoute(
      getReq(`/c/${token}/done?status=success&connected_account_id=ca_VENDOR_1`), r.env, r.deps);
    seen.add(await fingerprint(res, `anon done ${label}`));
    assert.equal(r.store.reads, 0, `the store was read on an anonymous /done (${label})`);
    assert.equal(r.written.length, 0, "a signed-out callback wrote a connection");
  }
  assert.equal(seen.size, 1, "an anonymous callback can tell the five states apart");
});

await check("a SIGNED-IN stranger cannot tell a real expired link from an invented one", async () => {
  // The order inside `locate` is what this is: expiry is checked BEFORE the
  // owner. Reversed, a real-but-expired token answers "wrong user" forever,
  // which tells whoever intercepted the text that the token was genuine —
  // permanently, and long after it could do anything.
  const real = await rig({ expiresAt: NOW - 1 });
  const fromReal = await fingerprint(
    await connectRoute(getReq(`/c/${real.token}`, asHeader(real.strangerToken)), real.env, real.deps),
    "stranger sees expired");
  const invented = await connectRoute(
    getReq(`/c/${await b64urlToken()}`, asHeader(real.strangerToken)), real.env, real.deps);
  const fromInvented = await fingerprint(invented, "stranger sees invented");
  assert.equal(fromReal, fromInvented,
    "an expired link and a string somebody made up are distinguishable to a stranger");
  assert.ok(!fromReal.includes("someone else"),
    "the wrong-user page confirmed the token was real");

  // THE CONTROL: a LIVE link still tells the stranger they are the wrong
  // person, or a household sharing a laptop can never be told why it failed.
  const live = await rig();
  const w = await connectRoute(getReq(`/c/${live.token}`, asHeader(live.strangerToken)),
    live.env, live.deps);
  assert.equal(w.status, 403);
  assert.match(await bodyOf(w, "stranger sees live"), /someone else/i);
});

await check("a store that answers with a NEIGHBOURING row is refused, not believed", async () => {
  // D1 is behind an interface: a COLLATE NOCASE column, a stray LIKE, a trimmed
  // key or a cache returning a near neighbour all produce a row that is not the
  // one asked for. Here the row that comes back is a stranger's, live and
  // well-formed — the shape that would open a vendor flow in somebody else's
  // name from the owner's own browser.
  const r = await rig();
  const wrong: StoredLink = {
    token_handle: await tokenHandle(await b64urlToken()),
    user_id: STRANGER, toolkit: "zellibrix", alias: null,
    expires_at: NOW + LINK_TTL_MS, used_at: null, completed_at: null,
  };
  r.store.read = async () => ({ ...wrong });
  const view = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(view.status, 410, "a row whose handle is not the one asked for was rendered");
  await bodyOf(view, "view neighbouring row");

  const go = await connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(go.status, 410);
  await bodyOf(go, "go neighbouring row");
  assert.equal(r.log.authorize.length, 0, "a vendor flow was opened in a stranger's name");
});

await check("a WRITE that lands on a different row than it was aimed at is refused", async () => {
  const r = await rig();
  const handle = await tokenHandle(r.token);
  const realClaim = r.store.claim.bind(r.store);
  r.store.claim = async (h: string, at: number) => {
    const out = await realClaim(h, at);
    // Won, and handed back somebody else's row. The claim has already written,
    // so the correct direction to fail is: the link stays spent and nobody gets
    // a redirect.
    return { won: out.won, row: out.row ? { ...out.row, user_id: STRANGER } : null };
  };
  const res = await connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 410);
  await bodyOf(res, "go wrong write row");
  assert.equal(r.log.authorize.length, 0,
    "the store's word was taken for it on the one path that decides whose account is connected");
  assert.equal(r.store.rows.get(handle)!.used_at, NOW,
    "a store answering wrongly is not a reason to hand out a second live link");
});

await check("the signed-out page names no app and no owner", async () => {
  const r = await rig();
  const res = await connectRoute(getReq(`/c/${r.token}`), r.env, r.deps);
  assert.equal(res.status, 401);
  const html = await bodyOf(res, "anon view copy");
  assert.doesNotMatch(html, /Zellibrix/i, "the app was named above the lock screen");
  assert.doesNotMatch(html, new RegExp(OWNER), "the owner id was printed to a stranger");
  assert.doesNotMatch(html, new RegExp(r.token), "the token was echoed into the page");
});

// ===========================================================================
// THE PAGE
// ===========================================================================

await check("the page shows the three sentences, the optional line and one Connect button",
  async () => {
    const r = await rig();
    const html = await bodyOf(
      await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps),
      "view sentences");
    assert.match(html, /Anticipy can read your Zellibrix for the things you ask about\./);
    assert.match(html, /It can add to your Zellibrix when you ask it to\./);
    assert.match(html, /You can turn this off any time in Settings\./);
    assert.match(html, /This is optional/,
      "connecting is always optional and every ask says so in one sentence");
    assert.match(html, new RegExp(`<form method="post" action="/c/${r.token}/go">`),
      "one button, pointed at our own /go");
    assert.equal((html.match(/<button/g) ?? []).length, 1, "exactly one button");
    assert.match(html, /Skip for now/);
    assert.match(html, /ten minutes/, "the person is told the link is short-lived");
  });

await check("NO APP IS HARDCODED — the whole flow runs on two invented slugs", async () => {
  for (const slug of Object.keys(APPS)) {
    const r = await rig({ toolkit: slug });
    const html = await bodyOf(
      await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps),
      "view " + slug);
    assert.match(html, new RegExp(`Connect your ${APPS[slug]!.name}`),
      `${slug} did not render from catalog metadata alone`);
    assert.match(html, new RegExp(`read your ${APPS[slug]!.name}`),
      "the sentences are generated per app, not typed into the Worker");
  }
  // And the cheap structural half: no vendor slug is a literal in the source.
  for (const real of ['"gmail"', '"notion"', '"slack"', '"googlecalendar"', '"outlook"']) {
    assert.ok(!SOURCE.includes(real),
      `connect.ts carries the app name ${real} — names come from the catalog at run time`);
  }
});

await check("catalog text is escaped, and a logo that is not https is dropped", async () => {
  const evil = "zellibrix";
  APPS[evil] = {
    ...APPS[evil]!,
    name: '<script>alert(1)</script>"',
    logo: "javascript:alert(1)",
  };
  try {
    const r = await rig({ toolkit: evil });
    const html = await bodyOf(
      await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps),
      "view escaping");
    assert.ok(!html.includes("<script>alert(1)</script>"),
      "a catalog name reached the page unescaped — script in our own origin, "
      + "which is the origin the session cookie lives on");
    assert.match(html, /&lt;script&gt;/);
    assert.ok(!html.includes("javascript:"), "a javascript: logo url was drawn into an attribute");
    assert.ok(!html.includes("<img"), "an unvouched logo must not be drawn at all");
  } finally {
    APPS[evil] = {
      slug: "zellibrix", name: "Zellibrix", logo: "https://cdn.example.invalid/z.png",
      description: "Where your team keeps its notes.", appUrl: "https://zellibrix.example.invalid",
      scopes: ["notes.read", "notes.write"],
    };
  }
});

await check("an https logo IS drawn — the control for the check above", async () => {
  const r = await rig();
  const html = await bodyOf(
    await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps),
    "view logo");
  assert.match(html, /<img class="logo" src="https:\/\/cdn\.example\.invalid\/z\.png"/);
});

await check("no sentences means no consent page — never a button over a blank list", async () => {
  for (const bad of [[], ["a real one", "   ", "another"]]) {
    const r = await rig({ sentences: async () => bad as string[] });
    const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
    const html = await bodyOf(res, "view empty sentences");
    assert.equal(res.status, 503, JSON.stringify(bad));
    assert.ok(!html.includes("<form"), "a person cannot consent to nothing");
  }
});

await check("the catalog being down is a retry, not a page with an unnamed app", async () => {
  const r = await rig({ toolkit: "not_in_the_catalog" });
  const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 503);
  const html = await bodyOf(res, "view catalog down");
  assert.ok(!html.includes("<form"));
});

await check("expired, used and wrong-user each get their own page for the OWNER", async () => {
  const expired = await rig({ expiresAt: NOW - 1 });
  const e = await connectRoute(getReq(`/c/${expired.token}`, asHeader(expired.ownerToken)),
    expired.env, expired.deps);
  assert.equal(e.status, 410);
  assert.match(await bodyOf(e, "view expired"), /expired/i);

  const used = await rig({ usedAt: NOW - 1000 });
  const u = await connectRoute(getReq(`/c/${used.token}`, asHeader(used.ownerToken)),
    used.env, used.deps);
  assert.equal(u.status, 410);
  assert.match(await bodyOf(u, "view used"), /has been used/i);

  const r = await rig();
  const w = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.strangerToken)), r.env, r.deps);
  assert.equal(w.status, 403);
  const html = await bodyOf(w, "view wrong user");
  assert.match(html, /signed in as someone else/i);
  assert.doesNotMatch(html, /Zellibrix/,
    "a signed-in stranger must not be told which app the owner is connecting");
});

// ===========================================================================
// THE SESSION
// ===========================================================================

await check("the browser's cookie is a session, and a look-alike cookie is not", async () => {
  const r = await rig();
  const ok = await connectRoute(getReq(`/c/${r.token}`, asCookie(r.ownerToken)), r.env, r.deps);
  assert.equal(ok.status, 200, "the cookie carrier is the whole browser path");
  await bodyOf(ok, "view cookie");

  const evil = await connectRoute(
    getReq(`/c/${r.token}`, { cookie: `evil_${SESSION_COOKIE}=${r.ownerToken}` }), r.env, r.deps);
  assert.equal(evil.status, 401, "a cookie whose name merely ENDS with ours was read as ours");
  await bodyOf(evil, "view evil cookie");
});

await check("an account token on the query string is not a session", async () => {
  const r = await rig();
  const res = await connectRoute(
    getReq(`/c/${r.token}?s=${encodeURIComponent(r.ownerToken)}&token=${r.ownerToken}`),
    r.env, r.deps);
  assert.equal(res.status, 401,
    "a credential in a URL lands in history, in logs and in a screenshot of the URL bar");
  await bodyOf(res, "view query token");
});

await check("a forged or malformed cookie is signed-out, never a 500", async () => {
  const r = await rig();
  for (const junk of ["", "not.a.token", "a.b.c", r.ownerToken + "x"]) {
    const res = await connectRoute(
      getReq(`/c/${r.token}`, { cookie: `${SESSION_COOKIE}=${junk}` }), r.env, r.deps);
    assert.equal(res.status, 401, JSON.stringify(junk));
    await bodyOf(res, "view junk cookie");
  }
});

// ===========================================================================
// /go — the only place a vendor link is ever produced
// ===========================================================================

await check("the tap mints the vendor link, spends the token and redirects", async () => {
  const r = await rig({ alias: "work" });
  const res = await connectRoute(
    postReq(`/c/${r.token}/go`, asHeader(r.ownerToken), { form: { state: "ATTEMPT-1234" } }),
    r.env, r.deps);

  assert.equal(res.status, 303);
  assert.equal(res.headers.get("location"), VENDOR_URL);
  assert.equal(await bodyOf(res, "go redirect"), "",
    "the vendor URL lives in the header and nowhere else");
  assert.equal(res.headers.get("referrer-policy"), "no-referrer",
    "our own token must not travel to the vendor in a Referer");

  assert.equal(r.log.authorize.length, 1, "exactly one vendor call per token, ever");
  const call = r.log.authorize[0]!;
  assert.equal(call.user, OWNER, "THE OWNER ROW ID — never a name, never an email");
  assert.equal(call.toolkit, "zellibrix");
  assert.equal(call.alias, "work", "the alias on the link is the account it becomes");
  // The request above arrives on anticipy.ai and the callback is expected on
  // api.anticipy.ai — DIFFERENT HOSTS ON PURPOSE. That is the property: the
  // callback origin comes from CONNECT_URL_BASE, never from the Host header,
  // because a callback built from a header hands the vendor a URL on whatever
  // host the request claimed to be. If these two are ever made to match, this
  // assertion stops testing anything.
  assert.equal(call.callbackUrl, callbackUrl(r.token, "https://api.anticipy.ai/c", "ATTEMPT-1234"),
    "the callback is OURS, carries the token, and echoes the phone's attempt id");

  assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, NOW, "the token is spent");
});

await check("the second tap on the same link is refused and asks the vendor nothing", async () => {
  const r = await rig();
  await bodyOf(await connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)),
    r.env, r.deps), "go first");
  const second = await connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)),
    r.env, r.deps);
  assert.equal(second.status, 410);
  assert.match(await bodyOf(second, "go second"), /has been used/i);
  assert.equal(r.log.authorize.length, 1, "single use is decided by the store, not by a read");
});

await check("two simultaneous taps: one redirect, one refusal, one vendor call", async () => {
  const r = await rig();
  const [a, b] = await Promise.all([
    connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)), r.env, r.deps),
    connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)), r.env, r.deps),
  ]);
  const codes = [a.status, b.status].sort();
  await bodyOf(a, "go race a");
  await bodyOf(b, "go race b");
  assert.deepEqual(codes, [303, 410], "both taps won the compare-and-set");
  assert.equal(r.log.authorize.length, 1,
    "a second live vendor request with nothing tracking it on our side");
});

await check("a vendor that does not answer leaves the link spent and says so", async () => {
  for (const authorize of [
    async () => { throw new Error("vendor 503 — with the vendor's own name in the text"); },
    async () => ({ redirectUrl: "" }),
  ]) {
    const r = await rig({ authorize });
    const res = await connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)),
      r.env, r.deps);
    assert.equal(res.status, 503);
    const html = await bodyOf(res, "go provider down");
    assert.match(html, /new link/i, "the person is offered a fresh link, not this one again");
    assert.ok(!html.includes("vendor 503"), "the vendor's error text reached the person");
    assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, NOW,
      "un-spending on an error hands unlimited attempts to whoever can make the vendor time out");
  }
});

await check("a cross-site POST cannot burn the owner's link", async () => {
  for (const opts of [
    { origin: "https://evil.example.invalid" },
    { fetchSite: "cross-site" },
    { origin: "not a url" },
  ]) {
    const r = await rig();
    const res = await connectRoute(
      postReq(`/c/${r.token}/go`, asHeader(r.ownerToken), opts), r.env, r.deps);
    assert.equal(res.status, 403, JSON.stringify(opts));
    await bodyOf(res, "go cross-site");
    assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, null,
      "a hidden form on another site spent the owner's single-use link");
    assert.equal(r.log.authorize.length, 0);
  }

  // THE CONTROLS: our own page, and a client that sends neither header, both
  // still work. A guard that refuses everything is an outage.
  for (const opts of [
    { origin: "https://anticipy.ai", fetchSite: "same-origin" },
    { origin: null },
  ]) {
    const r = await rig();
    const res = await connectRoute(
      postReq(`/c/${r.token}/go`, asHeader(r.ownerToken), opts), r.env, r.deps);
    assert.equal(res.status, 303, "the cross-site guard refused our own page: " + JSON.stringify(opts));
    await bodyOf(res, "go same-site control");
  }
});

await check("a stranger's tap and a signed-out tap spend nothing", async () => {
  const r = await rig();
  const w = await connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.strangerToken)),
    r.env, r.deps);
  assert.equal(w.status, 403);
  await bodyOf(w, "go stranger");
  assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, null,
    "a signed-in stranger burned somebody else's link");
  assert.equal(r.log.authorize.length, 0);
});

await check("a state that is not the phone's opaque shape is dropped, not reflected", async () => {
  const r = await rig();
  await bodyOf(await connectRoute(
    postReq(`/c/${r.token}/go`, asHeader(r.ownerToken), { form: { state: "<script>x</script>" } }),
    r.env, r.deps), "go bad state");
  assert.equal(r.log.authorize[0]!.callbackUrl, callbackUrl(r.token, "https://api.anticipy.ai/c"),
    "an unvalidated state reaches another company's server and comes back into our HTML");
});

// ===========================================================================
// /done — the callback, and the wrong-person failure
// ===========================================================================

/** A link that has been through /go, so the callback window is open. */
async function spent(opts: RigOpts = {}): Promise<Rig> {
  const r = await rig(opts);
  const handle = await tokenHandle(r.token);
  r.store.rows.set(handle, { ...r.store.rows.get(handle)!, used_at: NOW - 1000 });
  r.store.reads = 0;
  return r;
}

const doneUrl = (token: string, q: string) => `/c/${token}/done?${q}`;

await check("a confirmed account is recorded once and the page hands the phone back", async () => {
  const r = await spent({ alias: "personal" });
  const res = await connectRoute(
    getReq(doneUrl(r.token, "state=ATTEMPT-1234&status=success&connected_account_id=ca_VENDOR_1"),
      asHeader(r.ownerToken)), r.env, r.deps);

  assert.equal(res.status, 200);
  const html = await bodyOf(res, "done connected");
  assert.match(html, /Connected\./);
  assert.match(html, /Back to Anticipy/);
  assert.match(html,
    /anticipy:\/\/connected\/zellibrix\?state=ATTEMPT-1234&amp;status=connected&amp;connected_account_id=ca_VENDOR_1/,
    "the deep link is the phone's contract: ConnectHandoff.parseDone reads exactly these keys");

  assert.equal(r.log.connections[0], OWNER,
    "the vendor is asked about the STORED ROW's owner, never about the request");
  assert.equal(r.written.length, 1);
  const c = r.written[0]!;
  assert.equal(c.user_id, OWNER);
  assert.equal(c.toolkit, "zellibrix");
  assert.equal(c.connected_account_id, "ca_VENDOR_1");
  assert.equal(c.alias, "personal");
  assert.equal(c.writes_enabled, false,
    "a connection that arrived write-enabled lets the first step send mail on the owner's behalf");
});

await check("THE WRONG-PERSON CHECK: an account the vendor holds for somebody ELSE is refused",
  async () => {
    const r = await spent({
      vendorHolds: () => [{
        user_id: STRANGER, toolkit: "zellibrix", connected_account_id: "ca_THEIRS",
        alias: null, status: "connected", writes_enabled: false, last_used_at: null,
      }],
    });
    const res = await connectRoute(
      getReq(doneUrl(r.token, "status=success&connected_account_id=ca_THEIRS"),
        asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 200);
    assert.match(await bodyOf(res, "done foreign account"), /didn(&#39;|')t finish/i);
    assert.equal(r.written.length, 0,
      "one person's mailbox was bound to another, through a query string");
  });

await check("an account the vendor does not hold at all is refused", async () => {
  const r = await spent();
  const res = await connectRoute(
    getReq(doneUrl(r.token, "status=success&connected_account_id=ca_INVENTED"),
      asHeader(r.ownerToken)), r.env, r.deps);
  assert.match(await bodyOf(res, "done invented account"), /didn(&#39;|')t finish/i);
  assert.equal(r.written.length, 0, "the query string was believed without evidence");
});

await check("the right account on the WRONG toolkit is refused", async () => {
  const r = await spent({
    vendorHolds: (owner) => [{
      user_id: owner, toolkit: "quandle_mail", connected_account_id: "ca_VENDOR_1",
      alias: null, status: "connected", writes_enabled: false, last_used_at: null,
    }],
  });
  await bodyOf(await connectRoute(
    getReq(doneUrl(r.token, "status=success&connected_account_id=ca_VENDOR_1"),
      asHeader(r.ownerToken)), r.env, r.deps), "done wrong toolkit");
  assert.equal(r.written.length, 0,
    "a mail credential was about to be filed under the notes row");
});

await check("a vendor list we cannot read vouches for nothing", async () => {
  for (const holds of [
    () => ([null as unknown as Connection]),
    () => ([{ connected_account_id: "ca_VENDOR_1" } as unknown as Connection]),
    () => (undefined as unknown as Connection[]),
  ]) {
    const r = await spent({ vendorHolds: holds });
    await bodyOf(await connectRoute(
      getReq(doneUrl(r.token, "status=success&connected_account_id=ca_VENDOR_1"),
        asHeader(r.ownerToken)), r.env, r.deps), "done unreadable list");
    assert.equal(r.written.length, 0, "'nobody said yes' was read as 'nobody said no'");
  }
});

await check("no status, a wrong status or no account id writes nothing and asks nothing",
  async () => {
    for (const q of ["", "status=success", "connected_account_id=ca_VENDOR_1",
                     "status=cancelled&connected_account_id=ca_VENDOR_1",
                     "status=SUCCESS&connected_account_id=ca_VENDOR_1"]) {
      const r = await spent();
      const res = await connectRoute(getReq(doneUrl(r.token, q), asHeader(r.ownerToken)),
        r.env, r.deps);
      assert.match(await bodyOf(res, "done no status " + q), /didn(&#39;|')t finish/i, q);
      assert.equal(r.written.length, 0, q);
      assert.equal(r.log.connections.length, 0,
        "the vendor was asked before the callback's own word for success was checked");
    }
  });

await check("a refresh of the callback shows the same page and writes once", async () => {
  const r = await spent();
  const q = "status=success&connected_account_id=ca_VENDOR_1";
  const first = await connectRoute(getReq(doneUrl(r.token, q), asHeader(r.ownerToken)),
    r.env, r.deps);
  const second = await connectRoute(getReq(doneUrl(r.token, q), asHeader(r.ownerToken)),
    r.env, r.deps);
  assert.equal(first.status, 200);
  assert.equal(second.status, 200);
  assert.match(await bodyOf(first, "done first"), /Connected\./);
  assert.match(await bodyOf(second, "done refresh"), /Connected\./);
  assert.equal(r.written.length, 1, "a refresh recorded the connection twice");
});

await check("a write that fails hands the lease back so the next refresh finishes it", async () => {
  let attempts = 0;
  const written: Connection[] = [];
  const r = await spent({
    onConnected: async (c) => {
      attempts++;
      if (attempts === 1) throw new Error("D1_ERROR: the batch did not commit");
      written.push(c);
    },
  });
  const q = "status=success&connected_account_id=ca_VENDOR_1";

  const failed = await connectRoute(getReq(doneUrl(r.token, q), asHeader(r.ownerToken)),
    r.env, r.deps);
  assert.equal(failed.status, 500);
  const html = await bodyOf(failed, "done not recorded");
  assert.doesNotMatch(html, /Connected\./,
    "saying connected over a row that does not exist is how a connection is lost forever");
  assert.match(html, /Refresh/i);

  const retry = await connectRoute(getReq(doneUrl(r.token, q), asHeader(r.ownerToken)),
    r.env, r.deps);
  assert.equal(retry.status, 200);
  assert.match(await bodyOf(retry, "done retry"), /Connected\./);
  assert.equal(written.length, 1, "the released lease did not let the retry write");
});

await check("a vendor we cannot ASK is a retry, not a verdict", async () => {
  const r = await spent({
    vendorHolds: () => { throw new Error("vendor timeout"); },
  });
  const res = await connectRoute(
    getReq(doneUrl(r.token, "status=success&connected_account_id=ca_VENDOR_1"),
      asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 503);
  const html = await bodyOf(res, "done could not confirm");
  assert.match(html, /nothing has changed/i);
  assert.equal(r.written.length, 0);
  assert.equal(r.store.rows.get(await tokenHandle(r.token))!.completed_at, null,
    "nothing may be consumed when there is no evidence either way");
});

await check("a callback for a token that never went through /go is dead", async () => {
  const r = await rig();   // minted, never claimed
  const res = await connectRoute(
    getReq(doneUrl(r.token, "status=success&connected_account_id=ca_VENDOR_1"),
      asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 410);
  const html = await bodyOf(res, "done unclaimed");
  assert.ok(!html.includes("anticipy://"),
    "a page that may not name the app must not deep-link to it either");
  assert.equal(r.written.length, 0);
});

await check("the callback window is an hour from the tap, not the link's ten minutes", async () => {
  const inside = await spent({ now: () => NOW - 1000 + CALLBACK_WINDOW_MS - 1 });
  const ok = await connectRoute(
    getReq(doneUrl(inside.token, "status=success&connected_account_id=ca_VENDOR_1"),
      asHeader(inside.ownerToken)), inside.env, inside.deps);
  assert.equal(ok.status, 200,
    "a slow sign-in — a password manager, a 2FA push, an account chooser — was thrown away");
  await bodyOf(ok, "done inside window");

  const outside = await spent({ now: () => NOW - 1000 + CALLBACK_WINDOW_MS });
  const gone = await connectRoute(
    getReq(doneUrl(outside.token, "status=success&connected_account_id=ca_VENDOR_1"),
      asHeader(outside.ownerToken)), outside.env, outside.deps);
  assert.equal(gone.status, 410);
  await bodyOf(gone, "done outside window");
  assert.equal(outside.written.length, 0);
});

await check("a stranger's callback is refused before the vendor is asked anything", async () => {
  const r = await spent();
  const res = await connectRoute(
    getReq(doneUrl(r.token, "status=success&connected_account_id=ca_VENDOR_1"),
      asHeader(r.strangerToken)), r.env, r.deps);
  assert.equal(res.status, 403);
  const html = await bodyOf(res, "done stranger");
  assert.ok(!html.includes("anticipy://"));
  assert.doesNotMatch(html, /zellibrix/i);
  assert.equal(r.log.connections.length, 0);
  assert.equal(r.written.length, 0);
});

// ===========================================================================
// WIRING
// ===========================================================================

await check("an unwired Worker answers 503 and says so — never 404, never a page", async () => {
  const r = await rig();
  assert.equal(connectWiringInstalled(), false,
    "nothing has installed a wiring in this process, so the 503 below is the real path");
  for (const req of [
    getReq(`/c/${r.token}`, asHeader(r.ownerToken)),
    postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)),
    getReq(doneUrl(r.token, "status=success&connected_account_id=ca_VENDOR_1"),
      asHeader(r.ownerToken)),
  ]) {
    const res = await connectRoute(req, r.env);       // no deps: the production path
    assert.equal(res.status, 503, req.url);
    const html = await bodyOf(res, "unwired");
    assert.ok(!html.includes("<form"), "an unwired Worker drew a consent page");
    assert.match(html, /nothing has changed/i);
  }
});

// ===========================================================================
// TWO SCANS OVER EVERY BODY THIS SUITE PRODUCED
// ===========================================================================

await check("the vendor's URL never appears in a response body, anywhere", () => {
  for (const { where, text } of BODIES) {
    assert.ok(!text.includes(VENDOR_URL), `the vendor URL leaked into a body (${where})`);
    assert.ok(!text.includes("vendor.example.invalid"),
      `the vendor's host leaked into a body (${where})`);
  }
  assert.ok(BODIES.length > 40, "the scan is only worth its name over a real corpus");
});

await check("the product's register holds in every body: no Composio, no authorize, no API",
  () => {
    // spike/two-hands/src/connections/words.ts FORBIDDEN_TERMS, whole-word and
    // case-insensitive so "capital" does not trip "api".
    const forbidden = [
      "authorize", "authorise", "authorization", "authorisation",
      "grant access", "grants access", "granting access", "granted access",
      "permission", "permissions", "integration", "integrations",
      "api", "apis", "oauth", "composio",
    ];
    for (const { where, text } of BODIES) {
      const visible = text.replace(/<[^>]*>/g, " ");
      for (const term of forbidden) {
        const re = new RegExp(`\\b${term.replace(/ /g, "\\s+")}\\b`, "i");
        assert.ok(!re.test(visible),
          `"${term}" reached a person's screen (${where}) — the spec's register is `
          + '"connect your Notion", never a consent screen written by a legal team');
      }
    }
  });

await check("the source itself never says the vendor's name to a person", () => {
  // COMMENTS MAY NAME IT — connect.ts's own header does, twice, and must: the
  // reason our link exists at all is a measured failure of the vendor's link.
  // What may not exist is the name in CODE, where a page could print it. So the
  // comments come out first (block comments, then whole-line `//` ones, which
  // is every inline comment in that file) and what is left is scanned entire.
  const code = SOURCE
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
  assert.ok(code.length > 4000, "the comment stripper ate the file; the scan below proves nothing");
  assert.ok(!/composio/i.test(code),
    "connect.ts carries the vendor's name outside a comment — the product never says it");
});

console.log(`connect-routes: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
