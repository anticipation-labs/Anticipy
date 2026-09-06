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
 *   in five different states must produce ONE response, byte for byte once the
 *   caller's OWN token is normalised out, on all three legs — and the store
 *   must not be read at all. The token is normalised because the signed-out
 *   page now carries the way forward (`/c/{token}/code`), which is the token
 *   the caller already holds and nothing the store knows; every other byte of
 *   those five pages must still be identical.
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
 *   "OAuth" — the same collected bodies are scanned for all of them, over
 *   words.ts's own list rather than a copy of it. The one thing lifted out
 *   first is a third party's registered product name on that app's own page
 *   ("Moderation API"), because the scan is about the words THIS PRODUCT says
 *   and a proper noun is not one of them; the exemption is claimed per body,
 *   never globally, and the refusal pages claim none.
 *
 *   THE OVER-REFUSAL. Screening the catalog display name against that whole
 *   list made three live catalog rows unconnectable — 409, no button, no way
 *   forward, because their own makers put "API" in the name. Round two, finding
 *   1: the name is screened against the PROMISE half only (the vendor's name),
 *   and the register half is a rule about our own sentences.
 *
 * MUTATIONS THIS FILE MUST GO RED ON (run, not asserted — see the report):
 *   the session check moved after the store read in `locate`; the used-token and
 *   unknown-token answers separated for an anonymous caller; `vendorVouchesFor`
 *   made to trust the query string; the owner comparison in it dropped; the
 *   lease taken as a receipt (no `release` on a failed write); /go accepting
 *   GET; the cross-site refusal deleted; `writes_enabled` defaulting true.
 *
 * TEN MORE WERE RUN ON 2026-09-06 for the decline leg, each anchored on a
 * literal occurring EXACTLY ONCE in src/routes/connect.ts (the harness refuses
 * to patch otherwise, because a regex that silently fails to match reads as a
 * pass). ALL TEN WENT RED, and the check that killed each is named:
 *
 *   /skip accepting GET ................ Skip RECORDS the decline
 *   the cross-site refusal on /skip .... a cross-site POST cannot record one
 *   the wrong-user refusal in
 *     `connectPageSkip` ................ a stranger cannot decline for the owner
 *   the already-declined short circuit . a second Skip does NOT walk L1 to L2
 *   the connected guard ................ an app already connected has nothing
 *                                        to decline
 *   every skip seeded as onboarding .... Skip RECORDS the decline (7 days, not 14)
 *   the seed forgetting the setup card . the onboarding skip is SEVEN days
 *   the tap recorded as `silence` ...... Skip RECORDS the decline (acted_at)
 *   an unwritten decline drawn as a
 *     written one ...................... a decline that could NOT be written is
 *                                        never drawn as one that was
 *   Skip back to a GET form ............ the page's own Skip control is the POST
 *   the session ignored in
 *     `connectPageSkip` ................ signed out, five tokens give ONE answer
 *                                        on /skip
 *   `whoIsAsking` handed the leg's own
 *     path instead of the link's ....... a browser that proved itself with a
 *                                        PHONE CODE can decline
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
  installConnectSessionReader, promiseTermIn, whoIsSignedIn,
  CALLBACK_WINDOW_MS, CONNECT_METHOD, LINK_TTL_MS, REGISTER_TERMS, SESSION_COOKIE,
  type ClaimOutcome, type ConnectDeps, type ConnectEnv, type ConnectLinkStore,
  type Connection, type StoredLink, type ToolkitMeta,
} from "../src/routes/connect.ts";
// The list the exemption above is carved out of, and the matcher the one in
// connect.ts has to agree with. Imported rather than retyped: this file used to
// hold its own copy of FORBIDDEN_TERMS for the register scan, which is two
// copies of a list and no way to notice when they part company.
import { FORBIDDEN_TERMS, forbiddenTermIn } from "../src/connections/words.ts";
import type { ConnectNudge } from "../../../spike/two-hands/src/connections/contract.ts";

const here = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(here, "..", "src", "routes", "connect.ts"), "utf8");

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

// Every body every check produces, for the two whole-suite scans at the end.
//
// `quoting` is the ONE string a body was entitled to print verbatim even though
// the register scan would otherwise trip on it: a third party's registered
// product name, on that app's own consent page. It is passed by hand, at the
// four call sites that draw such a page, and nowhere else — a scan that
// exempted a word globally would exempt it on the refusal pages too, which is
// exactly where a leak would matter.
const BODIES: { where: string; text: string; quoting?: string }[] = [];
async function bodyOf(res: Response, where: string, quoting?: string): Promise<string> {
  const text = await res.text();
  BODIES.push({ where, text, quoting });
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

  // -- connect_nudges, which is where a NO goes ----------------------------
  //
  // Keyed (owner, app), like the real table's primary key, and scoped by BOTH on
  // the read — a fake that answered any row for any owner would let the suite
  // call a cross-owner write a pass. `putNudge` is deliberately dumb: the
  // production store's own CHECKs are exercised in connections-api.test.ts
  // against real SQLite, and this fake's job is only to remember.
  nudges = new Map<string, ConnectNudge>();
  /** Set by a check that wants the write to fail, which is the one path where
   *  the page must NOT claim the person's answer was kept. */
  nudgeWriteFails = false;

  private nudgeKey(user: string, toolkit: string): string { return `${user}::${toolkit}`; }

  async readNudge(user: string, toolkit: string): Promise<ConnectNudge | null> {
    this.reads++;
    const row = this.nudges.get(this.nudgeKey(String(user), toolkit));
    return row ? { ...row } : null;
  }

  async putNudge(row: ConnectNudge): Promise<void> {
    this.reads++;
    if (this.nudgeWriteFails) throw new Error("D1_ERROR: connect_nudges did not accept the row");
    this.nudges.set(this.nudgeKey(String(row.user_id), row.toolkit), { ...row });
  }
}

/** A store with the LINK half and nothing else — the shape a narrower wiring
 *  hands this file, and the one that must never be able to draw a page saying a
 *  decline was recorded. */
class LinkOnlyStore extends MemoryStore {
  override readNudge = undefined as unknown as MemoryStore["readNudge"];
  override putNudge = undefined as unknown as MemoryStore["putNudge"];
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

/**
 * CATALOG ROWS WHOSE OWN NAME IS THE ONE WORD THIS PRODUCT PROMISED NOBODY
 * WOULD EVER READ.
 *
 * Not invented: both are live catalog rows, read 2026-09-06. `describable`
 * already screens the catalog's DESCRIPTION; the name was rendered unscreened,
 * so the one screen the register rule exists for could print the one word the
 * spec treats not as a preference but as a promise.
 */
const VENDOR_NAMED: readonly { slug: string; name: string }[] = [
  { slug: "composio", name: "Composio" },
  { slug: "composio_search", name: "Composio Search" },
];

/**
 * CATALOG ROWS WHOSE OWN NAME CARRIES A REGISTER WORD AND IS NOT OURS TO
 * ARGUE WITH — the over-correction this round exists to undo.
 *
 * All three are live catalog rows, read 2026-09-06. The first version of the
 * name screen ran the display name against the whole of `FORBIDDEN_TERMS`, so
 * all three answered 409 with no button and no way forward: three real apps
 * somebody might genuinely want, permanently unconnectable, because their own
 * makers put "API" in the name. The register is a rule about the sentences THIS
 * PRODUCT writes. A proper noun is not this product writing.
 */
const NOT_OURS: readonly { slug: string; name: string }[] = [
  { slug: "aiml_api", name: "AI/ML API" },
  { slug: "api_labz", name: "API Labz" },
  { slug: "moderation_api", name: "Moderation API" },
];

/**
 * CATALOG ROWS WITH NO DISPLAY NAME AT ALL, one of them with the vendor's word
 * in its slug.
 *
 * These do not reach `viewPage` in the shipped wiring and the suite says so out
 * loud rather than dressing the guard up as behaviour a person can hit:
 * connections/provider.ts `readToolkitMeta` returns null for a nameless row so
 * `toolkit()` throws and this leg answers 503, and connections/words.ts
 * `metaProblem` refuses to write permission sentences for one. What they pin is
 * this file's own render floor — a third port wired tomorrow cannot make it draw
 * "Connect your " over a Connect button, and cannot make it print a vendor
 * primary key as somebody's app name. That floor REPLACED a slug fallthrough
 * whose comment claimed behaviour nothing executed (round-2 finding 2).
 */
const NAMELESS: readonly { slug: string; name: string }[] = [
  { slug: "composio_manage_connections", name: "   " },
  { slug: "blanknamed_notes", name: "   " },
];

for (const { slug, name } of [...VENDOR_NAMED, ...NOT_OURS, ...NAMELESS]) {
  APPS[slug] = { slug, name, logo: null, description: null, appUrl: null, scopes: ["thing.read"] };
}

/** THE BOUNDARY CONTROL, and it is the reason the screen is whole-word.
 *  "Rapid Capital" carries "api" twice as a SUBSTRING and is an ordinary name;
 *  refusing it would be an outage dressed as a rule. */
APPS.rapid_capital = {
  slug: "rapid_capital", name: "Rapid Capital", logo: null,
  description: null, appUrl: null, scopes: ["thing.read"],
};

/** The apps that have a name this product may print. Every one of them must
 *  render the whole consent page from catalog metadata alone. */
const RENDERABLE: readonly string[] = ["zellibrix", "quandle_mail", "rapid_capital"];

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
  /** A narrower store than production's, for the one check that proves an
   *  unrecordable decline is never drawn as a recorded one. */
  store?: MemoryStore;
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
  const store = opts.store ?? new MemoryStore();
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

/** The same page for two different tokens differs only by the token, which the
 *  caller supplied and already holds — exactly the normalisation
 *  connect-auth.test.ts does for the code pages. What must NOT differ is
 *  anything the STORE knows. */
const normalise = (text: string, token: string): string => text.split(token).join("{TOKEN}");

/** How many times a literal appears. Counted rather than matched: a regex that
 *  silently stopped matching reads as a pass, and did so three times in one day
 *  on this feature. */
const occurrences = (haystack: string, needle: string): number =>
  haystack.split(needle).length - 1;

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
      const fp = normalise(await fingerprint(res, `anon view ${label}`), token);
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
      seen.add(normalise(await fingerprint(res, `anon go ${label}`), token));
      assert.equal(r.store.reads, 0, `the store was read on an anonymous /go (${label})`);
      assert.equal(r.log.authorize.length, 0, "the vendor was asked by an anonymous caller");
    }
    assert.equal(seen.size, 1, "an anonymous POST can tell the five states apart");
    // The live one specifically: still unspent, so the owner's own tap works.
    const live = (await fiveTokens())[0]!;
    assert.equal(live.r.store.rows.get(await tokenHandle(live.token))!.used_at, null);
  });

await check("signed out, five different tokens give ONE answer on /skip — and record nothing",
  async () => {
    const seen = new Set<string>();
    for (const { label, r, token } of await fiveTokens()) {
      const res = await connectRoute(postReq(`/c/${token}/skip`), r.env, r.deps);
      seen.add(normalise(await fingerprint(res, `anon skip ${label}`), token));
      assert.equal(r.store.reads, 0,
        `the store was read on an anonymous /skip (${label}) — the decline leg must not be `
        + "the one place a stranger can sort real tokens from invented ones");
      assert.equal(r.store.nudges.size, 0, "an anonymous POST recorded a decline");
    }
    assert.equal(seen.size, 1, "an anonymous skip can tell the five states apart");
  });

await check("signed out, five different tokens give ONE answer on /done", async () => {
  const seen = new Set<string>();
  for (const { label, r, token } of await fiveTokens()) {
    const res = await connectRoute(
      getReq(`/c/${token}/done?status=success&connected_account_id=ca_VENDOR_1`), r.env, r.deps);
    seen.add(normalise(await fingerprint(res, `anon done ${label}`), token));
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
  // The caller's OWN token may appear exactly once, on the way forward, and
  // nowhere else. It is the one string on that page the caller already holds;
  // a second occurrence is a page that grew something else to say about a link
  // nobody has proved anything about.
  assert.equal(occurrences(html, r.token), 1,
    "the signed-out page says more about the caller's link than the way forward");
  assert.equal(occurrences(html, `href="/c/${r.token}/code"`), 1);
});

await check("the signed-out page is not a dead end — it offers the code, and reads nothing",
  async () => {
    // MEASURED ON PRODUCTION 2026-09-06: a real link, minted and opened in
    // Chrome, drew a page that said "sign in in this browser" and linked to
    // nothing. There is no web sign-in on this Worker and the person is holding
    // a phone, so that page was the end of the product.
    const r = await rig();
    const res = await connectRoute(getReq(`/c/${r.token}`), r.env, r.deps);
    assert.equal(res.status, 401);
    const html = await bodyOf(res, "anon view offer");
    assert.equal(occurrences(html, `href="/c/${r.token}/code"`), 1,
      "the wall has no door: nothing on the page starts the phone-code flow");
    assert.equal(occurrences(html, "Get a code by text"), 1,
      "the control is not in the product's register, or is not there at all");
    // THE OFFER IS NOT AN ORACLE. It is drawn before anything is looked up, and
    // /c/{token}/code never reads the store either, so it is the same offer for
    // a live link, a spent one and a string somebody made up.
    assert.equal(r.store.reads, 0,
      "the way forward was drawn from the store — the door became the oracle");
  });

await check("the offer is on every leg that says sign in — the tap and the callback too",
  async () => {
    const r = await rig();
    const go = await connectRoute(
      postReq(`/c/${r.token}/go`, null, { form: { state: "ATTEMPT-1234" } }), r.env, r.deps);
    assert.equal(go.status, 401);
    assert.equal(occurrences(await bodyOf(go, "anon go offer"),
      `href="/c/${r.token}/code?state=ATTEMPT-1234"`), 1,
      "a signed-out tap on Connect is a dead end");
    assert.equal(r.store.reads, 0, "the store was read on an anonymous /go");
    assert.equal(r.log.authorize.length, 0);

    // THE ONE THAT LOSES A CONNECTION. The browser comes back from the vendor
    // with no cookie, and a wall here means the account exists at the vendor
    // with no row anywhere and no webhook that will ever mention it again.
    const d = await rig();
    const done = await connectRoute(getReq(
      `/c/${d.token}/done?state=ATTEMPT-1234&status=success&connected_account_id=ca_VENDOR_1`),
      d.env, d.deps);
    assert.equal(done.status, 401);
    assert.equal(occurrences(await bodyOf(done, "anon done offer"),
      `href="/c/${d.token}/code?state=ATTEMPT-1234"`), 1,
      "the callback's own sign-in page offers nothing, so the connection is lost silently");
    assert.equal(d.store.reads, 0, "the store was read on an anonymous /done");
  });

await check("the phone's state rides the way forward, and one nobody sent is not invented",
  async () => {
    const r = await rig();
    const withState = await bodyOf(await connectRoute(
      getReq(`/c/${r.token}?state=ATTEMPT-1234`), r.env, r.deps), "anon view state");
    assert.equal(occurrences(withState, `href="/c/${r.token}/code?state=ATTEMPT-1234"`), 1,
      "the attempt id is dropped at the wall, so the deep link home is refused by parseDone");

    const without = await bodyOf(await connectRoute(
      getReq(`/c/${r.token}`), r.env, r.deps), "anon view no state");
    assert.equal(occurrences(without, "state="), 0,
      "a state nobody sent was invented, and the phone will refuse it");
    assert.equal(occurrences(without, `href="/c/${r.token}/code"`), 1,
      "and the way forward is still there without one");
  });

await check("the state on the way forward is carried VERBATIM, never re-encoded", async () => {
  const r = await rig();
  // The phone's own alphabet allows "%" (ConnectHandoff.isOpaqueToken), which
  // is the character a missing encode and a double encode each corrupt, in
  // opposite directions. What the next hop reads back must be what arrived.
  const state = "A%2FB-1234";
  const html = await bodyOf(await connectRoute(
    getReq(`/c/${r.token}?state=${encodeURIComponent(state)}`), r.env, r.deps),
    "anon view verbatim state");
  const m = /href="([^"]*\/code\?[^"]*)"/.exec(html);
  assert.ok(m, "no way forward on the page at all");
  const back = new URL((m[1] as string).replace(/&amp;/g, "&"), "https://api.anticipy.ai")
    .searchParams.get("state");
  assert.equal(back, state,
    "the attempt id the code flow will read is not the one the phone minted");
});

await check("a state that is not the phone's shape never reaches the way forward", async () => {
  const r = await rig();
  const bad = await bodyOf(await connectRoute(
    getReq(`/c/${r.token}?state=${encodeURIComponent('"><script>x</script>')}`), r.env, r.deps),
    "anon view bad state");
  assert.equal(occurrences(bad, "state="), 0, "an unvalidated state was reflected into our HTML");
  assert.equal(occurrences(bad, "script"), 0);

  // THE CONTROL: the same page, with a state the phone would actually mint,
  // carries it. A check that refuses both is an outage, not a check.
  const ok = await bodyOf(await connectRoute(
    getReq(`/c/${r.token}?state=ATTEMPT-1234`), r.env, r.deps), "anon view good state");
  assert.equal(occurrences(ok, "state=ATTEMPT-1234"), 1);
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
    // TWO buttons since Skip became a POST of its own (the page used to carry
    // one and a link): exactly one that connects and exactly one that declines.
    // Counted separately rather than as a total, because "two buttons" would
    // stay true if the second one were a second Connect.
    assert.equal((html.match(/<button/g) ?? []).length, 2, "exactly two buttons");
    assert.equal((html.match(/<button class="go"/g) ?? []).length, 1,
      "exactly one button connects");
    assert.equal((html.match(/<button class="later"/g) ?? []).length, 1,
      "exactly one button declines");
    assert.match(html, /Skip for now/);
    assert.match(html, /ten minutes/, "the person is told the link is short-lived");
  });

await check("NO APP IS HARDCODED — the whole flow runs on two invented slugs", async () => {
  // The apps whose own name this product may say, which is what "renders from
  // catalog metadata alone" means. The rest of APPS are the rows whose name is a
  // word the register bans, and they have their own section below: a page that
  // rendered one of THOSE from catalog metadata alone would be the defect.
  for (const slug of RENDERABLE) {
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

// ===========================================================================
// THE NAME ON THE PAGE
// ---------------------------------------------------------------------------
// TWO RULES WEARING ONE NAME, AND THIS SECTION IS WHERE THEY COME APART.
//
// words.ts's `FORBIDDEN_TERMS` holds both, and its own comment says so about the
// entry that is not like the others: the vendor's name is "the one word in this
// list that is not a register problem but a promise". Everything else in it is
// the REGISTER — the vocabulary of a consent screen written by a legal team,
// applied to the sentences THIS PRODUCT writes.
//
// A catalog display name is neither of those things: it is a proper noun
// somebody else registered, and the page can only quote it (the description can
// be dropped, a name cannot — it is the subject of the only sentence on this
// page that matters, and rewriting it is what a phishing page does). So the
// PROMISE half refuses the page and the REGISTER half does not, and both halves
// have their own checks below plus the control that kills the other mistake.
// ===========================================================================

/** One consent page, asked for by an owner holding their own live link. Returns
 *  the response and the visible text of it. `quoting` is passed only where the
 *  page is entitled to print a third party's registered name — see `bodyOf`. */
async function drawn(slug: string, quoting?: string):
    Promise<{ r: Rig; res: Response; visible: string; html: string }> {
  const r = await rig({ toolkit: slug });
  const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
  const html = await bodyOf(res, `name screen ${slug}`, quoting);
  return { r, res, visible: html.replace(/<[^>]*>/g, " ").toLowerCase(), html };
}

await check("a toolkit named after the vendor cannot put that word on the page", async () => {
  for (const { slug, name } of VENDOR_NAMED) {
    const { r, res, visible, html } = await drawn(slug);
    assert.equal(res.status, 409,
      `${slug}: a consent page was drawn for a name this product may not say`);
    assert.ok(!visible.includes(name.trim().toLowerCase()),
      `${slug}: ${JSON.stringify(name)} reached the page`);
    assert.ok(!visible.includes(slug.toLowerCase()),
      `${slug}: the slug reached the page`);
    // No button, so nothing can be consented to and nothing can be tapped.
    assert.ok(!html.includes("<form"), `${slug}: a Connect button over a name we cannot print`);
    // And the refusal costs the owner nothing: the link is still theirs to tap
    // once somebody gives that toolkit a display name in the catalog.
    assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, null,
      `${slug}: the refusal spent the owner's single-use link`);
    assert.equal(r.log.authorize.length, 0, `${slug}: the vendor was asked for a link anyway`);
  }
});

await check("an app somebody else called \"Moderation API\" can still be connected", async () => {
  // THE OVER-CORRECTION, PINNED. Three live catalog rows whose own makers put a
  // register word in the name. Screening the name against all of
  // FORBIDDEN_TERMS made every one of them unconnectable: 409, no button, and a
  // page that does not even say why. The person must end up with a way to
  // connect them, and this is it.
  for (const { slug, name } of NOT_OURS) {
    const { r, res, html } = await drawn(slug, name);
    assert.equal(res.status, 200,
      `${slug}: somebody else's app is unconnectable because of a word in its own name`);
    assert.ok(html.includes(`<h1>Connect your ${name}</h1>`), `${slug}: no heading`);
    assert.ok(html.includes(`>Connect ${name}</button>`), `${slug}: no Connect button`);
    assert.ok(html.includes(`/c/${r.token}/go`), `${slug}: the button goes nowhere`);
  }
});

await check("a name carrying BOTH halves is refused for the promise, not waved through", async () => {
  // The trap in composing this out of `forbiddenTermIn`: it returns the FIRST
  // term in list order and the vendor's name is LAST, so "Composio API" answers
  // "api" — which the register exemption waves through, putting the promised-away
  // word on the page. The screen asks over the promise terms alone.
  APPS.both_halves = {
    slug: "both_halves", name: "Composio API", logo: null,
    description: null, appUrl: null, scopes: ["thing.read"],
  };
  const { res, visible, html } = await drawn("both_halves");
  assert.equal(res.status, 409, "a register word in front of the vendor's name unlocked the page");
  assert.ok(!visible.includes("composio"), "the promised-away word reached the page");
  assert.ok(!html.includes("<form"), "a Connect button over a name we cannot print");
});

await check("a catalog row with no display name is never drawn, and never draws its slug",
  async () => {
    // The render floor. Not reachable through the shipped wiring — provider.ts
    // and words.ts both refuse a nameless row first — so what this pins is that
    // this file cannot be made to head a consent page with a vendor primary key,
    // or with nothing at all, by a port wired later. See NAMELESS.
    for (const { slug, name } of NAMELESS) {
      assert.equal(name.trim(), "", `${slug}: the fixture stopped being a nameless one`);
      const { r, res, visible, html } = await drawn(slug);
      assert.equal(res.status, 409, `${slug}: a consent page was drawn with no app name on it`);
      assert.ok(!visible.includes(slug.toLowerCase()),
        `${slug}: the slug was printed as the app's name`);
      assert.ok(!html.includes("<form"), `${slug}: a Connect button over a blank heading`);
      assert.ok(!html.includes("Connect your </h1>"), `${slug}: a heading with nothing in it`);
      assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, null,
        `${slug}: the refusal spent the owner's single-use link`);
    }
  });

await check("the refusal names nothing: the vendor's own name and a nameless row draw one page",
  async () => {
    const a = await drawn(VENDOR_NAMED[0]!.slug);
    const b = await drawn(NAMELESS[1]!.slug);
    assert.equal(
      normalise(a.html, a.r.token), normalise(b.html, b.r.token),
      "the page a refused app draws differs by app — something about it leaked through",
    );
  });

await check("CONTROL: an ordinary catalog name still renders the whole consent page", async () => {
  for (const [slug, heading] of [["zellibrix", "Zellibrix"], ["quandle_mail", "Quandle Mail"]]) {
    const { res, html } = await drawn(slug!);
    assert.equal(res.status, 200, `${slug}: an ordinary app stopped rendering`);
    assert.ok(html.includes(`<h1>Connect your ${heading}</h1>`), `${slug}: no heading`);
    assert.ok(html.includes("<form"), `${slug}: no Connect button`);
  }
});

await check("CONTROL: the screen is whole-word — an ordinary name that CONTAINS one renders",
  async () => {
    // "Rapid Capital" carries "api" twice as a substring. A screen written with
    // `includes` refuses it, and refusing a real app's real name is an outage
    // wearing the costume of a rule. This one holds for the promise half too:
    // the boundary rule lives in `promiseTermIn`, not only in words.ts.
    const { res, html } = await drawn("rapid_capital");
    assert.equal(res.status, 200, "a whole-word screen became a substring screen");
    assert.ok(html.includes("<h1>Connect your Rapid Capital</h1>"));
  });

await check("the exemption is derived from words.ts, and what is left over is the promise", () => {
  // THE DRIFT PIN. `REGISTER_TERMS` is a second copy of most of a list that
  // lives next door, and a copy nothing compares is a copy that rots. Two
  // things have to hold: every exempted term must still be a forbidden one (an
  // exemption for a word nobody bans exempts nothing and reads as if it did),
  // and the residue — what the name screen actually refuses — must be exactly
  // the promise the spec's title makes.
  for (const term of REGISTER_TERMS) {
    assert.ok(FORBIDDEN_TERMS.includes(term),
      `connect.ts exempts ${JSON.stringify(term)}, which words.ts does not forbid`);
  }
  assert.deepEqual(
    FORBIDDEN_TERMS.filter((t) => !REGISTER_TERMS.has(t)), ["composio"],
    "the half of FORBIDDEN_TERMS the name screen refuses is no longer just the vendor's name",
  );
});

await check("the two matchers agree on the boundary, term for term and case for case", () => {
  // `promiseTermIn` re-states words.ts's boundary rule because words.ts keeps
  // its own matcher private. Two matchers that disagree about the same string
  // are how this exemption would become a hole, so they are compared here on
  // strings built from the promise terms alone — where `forbiddenTermIn` can
  // only be answering about the same term.
  const promise = FORBIDDEN_TERMS.filter((t) => !REGISTER_TERMS.has(t));
  assert.ok(promise.length > 0, "there is nothing left for the name screen to refuse");
  let matched = 0;
  for (const term of promise) {
    for (const shape of [
      term, term.toUpperCase(), `${term[0]!.toUpperCase()}${term.slice(1)}`,
      `The ${term} Company`, `${term}-Labs`, `[${term}]`, `${term}.`, `${term} Search`,
      // …and the shapes a whole-word rule must NOT match.
      `${term}x`, `x${term}`, `x${term}x`, `${term}9`, `9${term}`,
    ]) {
      assert.equal(promiseTermIn(shape), forbiddenTermIn(shape),
        `the two matchers disagree about ${JSON.stringify(shape)}`);
      if (promiseTermIn(shape) !== null) matched += 1;
    }
  }
  assert.ok(matched >= promise.length * 8, "the corpus stopped exercising the matching direction");
});

await check("the name screen is at the render site, exactly once", () => {
  // The mutation anchor: one literal, one occurrence. A second copy of this
  // check somewhere else in the file is two answers to one question.
  const anchor = "const unsayable = promiseTermIn(name);";
  assert.equal(occurrences(SOURCE, anchor), 1,
    `connect.ts contains ${occurrences(SOURCE, anchor)} copies of the name screen`);
  // And it is the PROMISE half it runs, not the whole list: the register screen
  // belongs on the description, which is prose we are quoting rather than a name.
  assert.equal(occurrences(SOURCE, "forbiddenTermIn(name)"), 0,
    "the name is screened against the register again — the over-refusal is back");
  // Both screens run BEFORE anything is drawn: the heading is built from `name`,
  // so a screen placed after it has already put the word in a string.
  assert.ok(SOURCE.indexOf(anchor) < SOURCE.indexOf("<h1>Connect your ${esc(name)}"),
    "the name screen runs after the heading is built");
  assert.ok(SOURCE.indexOf('if (name === "") {') < SOURCE.indexOf(anchor),
    "the nameless floor runs after the promise screen, so a blank name reaches a regex first");
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

await check("THE CHAIN: the state on the page is the state that reaches the vendor",
  async () => {
    // The hop AFTER the phone-code redirect, and the one nothing covered until
    // 2026-09-06: `/c/{token}/verify` now 303s to `/c/{token}?state=…`, and if
    // the consent page does not put that value back into its own form the state
    // dies here instead — one hop later, just as silently, with the same ending
    // (ConnectHandoff.parseDone refusing the deep link home).
    const r = await rig();
    const html = await bodyOf(await connectRoute(
      getReq(`/c/${r.token}?state=ATTEMPT-1234`, asHeader(r.ownerToken)), r.env, r.deps),
      "view carries the state");
    // ONCE PER FORM, and both of them: the page now posts to /go and to /skip,
    // and an attempt id that survives Connect but dies on Skip is the same lost
    // handoff one button over.
    assert.equal(occurrences(html, '<input type="hidden" name="state" value="ATTEMPT-1234">'), 2,
      "the consent page dropped the attempt id the browser arrived with");

    // Posted back exactly as the page rendered it — read out of the HTML rather
    // than retyped, so this drives the chain instead of assuming it.
    const rendered = /name="state" value="([^"]*)"/.exec(html);
    assert.ok(rendered, "no state field to post");
    await bodyOf(await connectRoute(
      postReq(`/c/${r.token}/go`, asHeader(r.ownerToken),
        { form: { state: rendered[1] as string } }), r.env, r.deps), "go from the page");
    assert.equal(r.log.authorize[0]!.callbackUrl,
      callbackUrl(r.token, "https://api.anticipy.ai/c", "ATTEMPT-1234"),
      "the URL the other company sends the browser back to carries no attempt id");

    // THE CONTROL: no state on the page means no state invented anywhere.
    const bare = await rig();
    const plain = await bodyOf(await connectRoute(
      getReq(`/c/${bare.token}`, asHeader(bare.ownerToken)), bare.env, bare.deps), "view no state");
    assert.equal(occurrences(plain, 'name="state"'), 0);
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
// SAYING NO — /c/{token}/skip
//
// THE DEFECT THESE CHECKS REPRODUCE, and it is the whole decline half of the
// spec: "Skip for now" was a BARE ANCHOR to the marketing site. It navigated
// away and wrote nothing. `recordDecline` (connections/nudge.ts) had no caller
// anywhere in the Worker, so the snooze ladder — 14 days, then 45, then stop —
// could not be entered by any human action, and the person who tapped Skip was
// asked again at the next moment that scored high enough. Forever.
//
// Every check reads the ROW the store now holds. "It answered 200" is not the
// property being tested; "the system now knows they said no" is.
// ===========================================================================

const DAY = 24 * 60 * 60 * 1000;

/** The nudge row this rig's store holds for the owner and the app the link was
 *  minted for, read outside the code under test. */
const nudgeFor = (r: Rig, toolkit = "zellibrix"): ConnectNudge | undefined =>
  r.store.nudges.get(`${OWNER}::${toolkit}`);

/** A POST to the Skip form, exactly as the page's own form makes one. */
const skipReq = (
  token: string, who: Who, opts?: { form?: Record<string, string>; origin?: string | null;
                                    fetchSite?: string },
): Request => postReq(`/c/${token}/skip`, who, opts);

await check("Skip RECORDS the decline — the row exists, and it is level 1", async () => {
  const r = await rig();
  assert.equal(nudgeFor(r), undefined, "nothing is declined before the tap");

  const res = await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 200);
  const html = await bodyOf(res, "skip noted");
  assert.match(html, /Noted\./, "the person is told their answer was kept");

  const row = nudgeFor(r)!;
  assert.ok(row, "the tap wrote nothing: nobody can say no");
  assert.equal(row.user_id, OWNER);
  assert.equal(row.toolkit, "zellibrix");
  assert.equal(row.state, "declined");
  assert.equal(row.level, 1);
  assert.equal(row.acted_at, NOW,
    "acted_at is what separates a tap from 72 hours of silence, and the spec's timers "
    + "are tuned off the difference");
  assert.equal((row.snooze_until as number) - NOW, 14 * DAY,
    "a decline on the connect page is the spec's level 1: fourteen days");

  // A DECLINE COSTS NOBODY A VENDOR ROUND TRIP. Saying no must be the cheapest
  // thing in the product.
  assert.equal(r.log.authorize.length, 0);
  assert.equal(r.log.toolkit.length, 0);
});

await check("the page's own Skip control is the POST that records it", async () => {
  const r = await rig();
  const html = await bodyOf(
    await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps),
    "view skip form");
  assert.equal(CONNECT_METHOD.skip, "POST",
    "a leg that writes may not be a GET, whatever the page draws");
  assert.match(html, new RegExp(`<form class="later" method="post" action="/c/${r.token}/skip">`),
    "Skip is a bare anchor again — an anchor navigates away and records nothing, "
    + "which is the whole defect");
  assert.equal(occurrences(html, "Skip for now"), 1);
});

await check("a GET on /skip is refused — a prefetcher must not decline for the owner",
  async () => {
    const r = await rig();
    const res = await connectRoute(
      getReq(`/c/${r.token}/skip`, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 405);
    assert.equal(res.headers.get("allow"), "POST");
    assert.equal(nudgeFor(r), undefined,
      "a link prefetcher, an <img> tag or an address-bar preload silenced an app "
      + "nobody turned down");

    // THE CONTROL: the same link, POSTed, still records. A guard that refuses
    // both is an outage, not a guard.
    const ok = await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(ok.status, 200);
    await bodyOf(ok, "skip GET control");
    assert.equal(nudgeFor(r)!.level, 1);
  });

await check("a cross-site POST cannot record a decline", async () => {
  const r = await rig();
  for (const opts of [{ origin: "https://evil.example.invalid" }, { fetchSite: "cross-site" }]) {
    const res = await connectRoute(skipReq(r.token, asHeader(r.ownerToken), opts), r.env, r.deps);
    assert.equal(res.status, 403, JSON.stringify(opts));
    await bodyOf(res, "skip cross-site");
    assert.equal(nudgeFor(r), undefined,
      "a hidden form on any site could snooze an app the owner never turned down");
  }
  // THE CONTROL: our own page's POST, with our own Origin, still records.
  const ok = await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(ok.status, 200);
  await bodyOf(ok, "skip same-site control");
  assert.equal(nudgeFor(r)!.state, "declined");
});

await check("a signed-out Skip records nothing and is the same door as every other leg",
  async () => {
    const r = await rig();
    const res = await connectRoute(skipReq(r.token, null), r.env, r.deps);
    assert.equal(res.status, 401);
    const html = await bodyOf(res, "skip signed out");
    assert.equal(nudgeFor(r), undefined);
    assert.doesNotMatch(html, /Zellibrix/i,
      "a caller who has proved nothing must not be told which app the link is for");
    assert.match(html, new RegExp(`/c/${r.token}/code`), "the way forward is still offered");
  });

await check("a stranger cannot decline on the owner's behalf", async () => {
  const r = await rig();
  const res = await connectRoute(skipReq(r.token, asHeader(r.strangerToken)), r.env, r.deps);
  assert.equal(res.status, 403);
  const html = await bodyOf(res, "skip stranger");
  assert.doesNotMatch(html, /Zellibrix/i);
  assert.equal(r.store.nudges.size, 0,
    "somebody else's session silenced an app for an owner who never said a word");
});

await check("an expired link cannot record a decline", async () => {
  const r = await rig({ expiresAt: NOW - 1 });
  const res = await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 410);
  await bodyOf(res, "skip expired");
  assert.equal(r.store.nudges.size, 0);
});

await check("a second Skip does NOT walk somebody from L1 to L2", async () => {
  const r = await rig();
  await bodyOf(await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps),
    "skip once");
  const first = { ...nudgeFor(r)! };
  await bodyOf(await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps),
    "skip twice");
  const second = nudgeFor(r)!;
  assert.equal(second.level, 1,
    "a refresh, a double tap or a retried POST climbed the ladder — three of them would "
    + "reach level 3, which stops the asks for ten years over one finger");
  assert.equal(second.snooze_until, first.snooze_until);
});

await check("Skip does NOT spend the link — changing your mind still works", async () => {
  const r = await rig();
  await bodyOf(await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps),
    "skip then connect");
  assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, null,
    "a decline is not a redemption");
  const go = await connectRoute(postReq(`/c/${r.token}/go`, asHeader(r.ownerToken)),
    r.env, r.deps);
  assert.equal(go.status, 303, "somebody who taps Skip and thinks better of it inside the "
    + "ten minutes must still be able to connect");
});

await check("THE ROW'S OWN MOMENT decides the snooze, not the surface that asked", async () => {
  // Onboarding: the ask engine wrote `trigger: onboarding`, so this is the
  // spec's seven-day SOFT snooze rather than a real decline (page 21).
  const soft = await rig();
  soft.store.nudges.set(`${OWNER}::zellibrix`, {
    user_id: OWNER as never, toolkit: "zellibrix" as never, state: "asked", level: 0,
    snooze_until: null, trigger: "onboarding", sent_at: NOW - 1000, acted_at: null,
    channel: "sms",
  });
  await bodyOf(await connectRoute(skipReq(soft.token, asHeader(soft.ownerToken)),
    soft.env, soft.deps), "skip soft");
  const softRow = nudgeFor(soft)!;
  assert.equal(softRow.level, 1);
  assert.equal((softRow.snooze_until as number) - NOW, 7 * DAY,
    "a skipped setup card is not a real decline and must not carry a real decline's snooze");

  // THE CONTROL, AND THE POINT: any other moment is the fourteen-day L1. The two
  // are different rows and conflating them is what the spec forbids in one line.
  const real = await rig();
  real.store.nudges.set(`${OWNER}::zellibrix`, {
    user_id: OWNER as never, toolkit: "zellibrix" as never, state: "asked", level: 0,
    snooze_until: null, trigger: "in_task", sent_at: NOW - 1000, acted_at: null,
    channel: "sms",
  });
  await bodyOf(await connectRoute(skipReq(real.token, asHeader(real.ownerToken)),
    real.env, real.deps), "skip real");
  const realRow = nudgeFor(real)!;
  assert.equal((realRow.snooze_until as number) - NOW, 14 * DAY);
  assert.notEqual(softRow.snooze_until, realRow.snooze_until);
});

await check("an app this owner already has connected has nothing to decline", async () => {
  const r = await rig();
  const connected: ConnectNudge = {
    user_id: OWNER as never, toolkit: "zellibrix" as never, state: "connected", level: 0,
    snooze_until: null, trigger: "in_task", sent_at: NOW - DAY, acted_at: NOW - DAY,
    channel: "sms",
  };
  r.store.nudges.set(`${OWNER}::zellibrix`, connected);
  const res = await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 200);
  const html = await bodyOf(res, "skip already connected");
  assert.doesNotMatch(html, /Noted\./);
  assert.equal(nudgeFor(r)!.state, "connected",
    "declining an app they already have would stop the router using a live connection");
});

await check("a decline that could NOT be written is never drawn as one that was", async () => {
  // A store with no nudge half at all — a narrower wiring than production's.
  const narrow = await rig({ store: new LinkOnlyStore() });
  const res = await connectRoute(skipReq(narrow.token, asHeader(narrow.ownerToken)),
    narrow.env, narrow.deps);
  assert.equal(res.status, 500);
  const html = await bodyOf(res, "skip unrecordable");
  assert.doesNotMatch(html, /Noted\./,
    "a page saying the answer was kept over a row that does not exist is the same "
    + "defect this leg was built to close, with better manners");
  assert.match(html, /note that/i, "the honest failure page, not a claim the answer was kept");

  // And the same when the store is there and the WRITE fails.
  const failing = new MemoryStore();
  failing.nudgeWriteFails = true;
  const broken = await rig({ store: failing });
  const res2 = await connectRoute(skipReq(broken.token, asHeader(broken.ownerToken)),
    broken.env, broken.deps);
  assert.equal(res2.status, 500);
  assert.doesNotMatch(await bodyOf(res2, "skip write failed"), /Noted\./);
  assert.equal(broken.store.nudges.size, 0);
});

await check("a browser that proved itself with a PHONE CODE can decline", async () => {
  // THE POPULATION THIS PRODUCT ACTUALLY TEXTS. That browser holds no account
  // cookie; the only thing that makes it somebody is the code cookie
  // routes/connect_auth.ts mints, and `connectSession` honours one ONLY on the
  // link it was minted for — reading the link out of the REQUEST PATH with a
  // regex of its own that lists this file's leg names.
  //
  // Measured on 2026-09-06: that regex did not know `/skip`, so the same person
  // could tap Connect and could NOT tap Skip. Saying yes worked and saying no
  // answered "sign in to finish", which is the exact asymmetry the decline leg
  // exists to remove. `whoIsAsking` now asks about `/c/{token}` on every leg, so
  // this check runs the OTHER file's own regex — read out of its source — over
  // the path the reader was actually handed.
  const authSource = readFileSync(join(here, "..", "src", "routes", "connect_auth.ts"), "utf8");
  const after = authSource.split("function tokenFromPath")[1] ?? "";
  const literal = /const m = (\/\^[^\n]+?\/)\.exec\(pathname\);/.exec(after);
  assert.ok(literal, "connect_auth.ts's tokenFromPath moved; this check is stale rather than green");
  const theirs = new RegExp((literal![1] as string).slice(1, -1));

  const r = await rig();
  const seen: { path: string; auth: string | null }[] = [];
  installConnectSessionReader(async (req, env) => {
    const u = new URL(req.url);
    seen.push({ path: u.pathname, auth: req.headers.get("Authorization") });
    // Answer only if the credential survived the hop, so a fabricated request
    // that dropped the header would read as signed out and fail below.
    return await whoIsSignedIn(req, env);
  });
  try {
    const res = await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 200);
    await bodyOf(res, "skip via session reader");
    assert.equal(nudgeFor(r)!.state, "declined");
  } finally {
    // Back to the default behaviour: the narrow reader connect.ts falls back to.
    installConnectSessionReader((req, env) => whoIsSignedIn(req, env));
  }

  assert.equal(seen.length, 1, "the session was not read exactly once");
  assert.ok(seen[0]!.auth, "the credential did not survive the hop into the reader");
  const bound = theirs.exec(seen[0]!.path);
  assert.ok(bound,
    `the installed session reader was handed ${seen[0]!.path}, which connect_auth.ts's own `
    + "tokenFromPath cannot bind to a link — so a code cookie answers for Connect and not "
    + "for Skip, and the person who wants to say no is the one who cannot");
  assert.equal(bound![1], r.token, "it bound to a different link than the request is on");
});

await check("the way back into the app is offered only when the app started it", async () => {
  const withState = await rig();
  const html = await bodyOf(await connectRoute(
    skipReq(withState.token, asHeader(withState.ownerToken), { form: { state: "ATTEMPT-99" } }),
    withState.env, withState.deps), "skip deep link");
  assert.match(html, /anticipy:\/\/connected\/zellibrix\?state=ATTEMPT-99&amp;status=cancelled/,
    "the phone already parses `cancelled`; a skip is not a failure and must not say it is");

  // A browser that arrived from a TEXT has no attempt id, and ConnectHandoff
  // refuses a callback it cannot bind to one — so offering the link there is
  // offering a dead end.
  const noState = await rig();
  const plain = await bodyOf(await connectRoute(
    skipReq(noState.token, asHeader(noState.ownerToken)), noState.env, noState.deps),
    "skip no deep link");
  assert.ok(!plain.includes("anticipy://"));
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
    // words.ts's own FORBIDDEN_TERMS, whole-word and case-insensitive so
    // "capital" does not trip "api".
    //
    // WHAT `quoting` TAKES OUT, AND WHY IT IS NOT A HOLE. The scan is over the
    // words THIS PRODUCT says. On the consent page for an app whose maker
    // registered it as "Moderation API", the product is quoting a proper noun,
    // and a scan that refused that is the over-refusal one layer up wearing a
    // test's clothes. So exactly one string is removed from exactly the bodies
    // that were entitled to print it — the app's own name, on that app's own
    // page — and everything else in those bodies is scanned as normal:
    // "authorize your Moderation API" still fails on "authorize", and the
    // refusal pages, which pass no `quoting`, are scanned whole.
    let quoted = 0;
    for (const { where, text, quoting } of BODIES) {
      let visible = text.replace(/<[^>]*>/g, " ");
      if (quoting !== undefined) {
        assert.ok(visible.includes(quoting),
          `${where} was exempted for ${JSON.stringify(quoting)} and never printed it`);
        visible = visible.split(quoting).join(" ");
        quoted += 1;
      }
      for (const term of FORBIDDEN_TERMS) {
        const re = new RegExp(`\\b${term.replace(/ /g, "\\s+")}\\b`, "i");
        assert.ok(!re.test(visible),
          `"${term}" reached a person's screen (${where}) — the spec's register is `
          + '"connect your Notion", never a consent screen written by a legal team');
      }
    }
    assert.ok(quoted >= 3,
      "no body claimed the third-party-name exemption, so the scan is proving it unused rather "
      + "than proving it narrow");
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

// ===========================================================================
// MUTATION REPORT — the name screen in src/routes/connect.ts.
//
// ROUND ONE, 2026-09-06: six mutations, all six killed, and the screen they
// were run against was still wrong. Every one of them asked "is the rule still
// there", and none of them asked "does the rule refuse more than it should" —
// which is how a screen that made three real apps unconnectable passed a
// mutation report. Two of those six are gone below because what they pinned is
// gone: N2 ran the screen on `v.toolkit.name` instead of the printed `name`,
// and the slug fallthrough that distinction existed for was a branch nothing
// executed (round-2 finding 2), so the distinction went with it.
//
// ROUND TWO, 2026-09-06: NINE mutations, ALL NINE KILLED, run after the split.
// Each is anchored on a literal occurring EXACTLY ONCE in the file, and the
// harness aborts on an anchor that does not: a patch that silently fails to
// apply reads as "it is tested", which is how three false green readings were
// produced on this feature in one day. Four of the nine point at the
// OVER-refusal, because that is the direction round one could not see.
//
//   M1  `const unsayable = promiseTermIn(name)` -> `null`, the screen gone
//       -> 5 checks, first: "a toolkit named after the vendor cannot put that
//          word on the page"
//   M2  the register exemption removed — the name screened against all of
//       FORBIDDEN_TERMS again, which is the round-one defect exactly
//       -> 2 checks, first: "an app somebody else called \"Moderation API\" can
//          still be connected"
//   M3  the nameless floor deleted
//       -> 2 checks, first: "a catalog row with no display name is never drawn"
//   M4  `promiseTermIn` composed out of `forbiddenTermIn` with the exemption
//       applied to its FIRST match — the trap, since the vendor's name is last
//       in the list and "Composio API" would answer "api"
//       -> 2 checks, first: "a name carrying BOTH halves is refused for the
//          promise, not waved through"
//   M5  the whole-word boundary in `promiseTermIn` made a substring test
//       -> "the two matchers agree on the boundary, term for term"
//   M6  the exemption widened until it swallowed the promise as well
//       -> 6 checks, including the drift pin over words.ts's own list
//   M7  the promise refusal answering 200 instead of 409
//       -> 2 checks
//   M8  the refusal page rewritten to name the app it refused
//       -> 2 checks, including the two refusals drawing one page
//   M9  our OWN fine print rewritten in permissions language, with the
//       third-party-name exemption in place — the check that the exemption is
//       narrow rather than a hole in the register scan
//       -> the whole-suite register scan
// ===========================================================================

console.log(`connect-routes: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
