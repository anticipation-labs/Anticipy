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
  connectRoute, tokenHandle, callbackUrl, connectWiringInstalled, connectPageGo,
  installConnectSessionReader, pageHandle, promiseTermIn, whoIsSignedIn,
  CALLBACK_WINDOW_MS, CONNECT_METHOD, LINK_TTL_MS, MAX_PAGE_APPS, REGISTER_TERMS,
  SESSION_COOKIE,
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
  // Two more, so a PAGE of apps can be four invented ones. Same point as the two
  // above and it matters more here: a page is where a file that had learned any
  // app's name would show it, because it would have to decide an order.
  torvex_boards: {
    slug: "torvex_boards", name: "Torvex Boards", logo: "https://cdn.example.invalid/t.png",
    description: "Where your team tracks work.", appUrl: null, scopes: ["boards.read"],
  },
  pindle_desk: {
    slug: "pindle_desk", name: "Pindle Desk", logo: null,
    description: null, appUrl: null, scopes: ["desk.read", "desk.write"],
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
const RENDERABLE: readonly string[] = [
  "zellibrix", "quandle_mail", "rapid_capital", "torvex_boards", "pindle_desk",
];

/** The four a person ticked on the onboarding card, in the order they were
 *  minted. All four invented; the page has to come out of the catalog. */
const PAGE: readonly string[] = ["zellibrix", "quandle_mail", "torvex_boards", "pindle_desk"];

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
// A PAGE OF APPS — spec page 25, "One Connect button opens a multi-app connect
// page", and the four gaps three audits named, closed here.
//
// WHAT A PAGE IS, structurally, so these checks are readable: N ordinary
// `connect_links` rows at handles derived from ONE token (`pageHandle`), which
// is why "four ticked apps become ONE link" is a claim about the store as much
// as about the page. Row 0 sits where a one-app link's row has always sat, and
// that is the whole backward-compatibility story — the CONTROL at the end of
// this section is the thing that proves it rather than asserting it.
//
// THE FAILURES THIS SECTION EXISTS TO CATCH:
//   the page drawing one app out of four (the render never read `apps`);
//   a card's button spending row 0 whatever it said (the form's index never
//     reached `/go`, so tapping the third app connected the first);
//   the vendor's callback finishing row 0 whatever it carried (same, on `/done`);
//   the background poll watching row 0 while row 3 was in flight;
//   one bad catalog row costing somebody the other three;
//   a browser that died mid-walk starting again from the beginning.
// ===========================================================================

/** A page of N apps on ONE token: row 0 where a one-app link's row has always
 *  been, the rest at derived handles. The vendor is made to vouch for every one
 *  of them, since a page walks them one at a time and each callback is checked
 *  against the vendor's own list. */
async function pageRig(
  slugs: readonly string[], opts: RigOpts = {},
): Promise<Rig & { slugs: readonly string[] }> {
  const r = await rig({
    ...opts,
    toolkit: slugs[0],
    vendorHolds: opts.vendorHolds ?? ((owner: string): Connection[] =>
      slugs.map((slug, i) => ({
        user_id: owner, toolkit: slug, connected_account_id: `ca_VENDOR_${i}`,
        alias: null, status: "connected" as const, writes_enabled: false, last_used_at: null,
      }))),
  });
  for (let i = 1; i < slugs.length; i++) {
    r.store.put({
      token_handle: await pageHandle(r.token, i),
      user_id: OWNER,
      toolkit: slugs[i]!,
      alias: null,
      expires_at: opts.expiresAt ?? NOW + LINK_TTL_MS,
      used_at: null,
      completed_at: null,
    });
  }
  return { ...r, slugs };
}

/** Tap one card. The hidden field the page rendered is the only thing that says
 *  which app this is. */
const goReq = (token: string, who: Who, app: number | string | null, state?: string): Request =>
  postReq(`/c/${token}/go`, who, {
    form: {
      ...(app === null ? {} : { app: String(app) }),
      ...(state === undefined ? {} : { state }),
    },
  });

/** The vendor coming back for one card. */
const doneFor = (token: string, app: number | string | null, account: string): string =>
  doneUrl(token, `status=success&connected_account_id=${account}`
    + (app === null ? "" : `&app=${app}`));

/** Connect one card end to end, the way a person does: tap, vendor, callback. */
async function connectCard(r: Rig, app: number, account: string): Promise<Response> {
  const go = await connectRoute(goReq(r.token, asHeader(r.ownerToken), app), r.env, r.deps);
  await bodyOf(go, `page go ${app}`);
  assert.equal(go.status, 303, `card ${app} did not redirect`);
  return await connectRoute(
    getReq(doneFor(r.token, app, account), asHeader(r.ownerToken)), r.env, r.deps);
}

await check("FOUR ticked apps are ONE link, and the page draws all four", async () => {
  const r = await pageRig(PAGE);

  // ONE TOKEN. Four rows, every one of them reachable only by hashing the token
  // the person is holding — which is what makes this one link and not four.
  assert.equal(r.store.rows.size, 4, "a page of four is four rows");
  for (let i = 0; i < PAGE.length; i++) {
    assert.ok(r.store.rows.has(await pageHandle(r.token, i)), `row ${i} is not on this token`);
  }

  const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 200);
  const html = await bodyOf(res, "page view four");

  for (const [i, slug] of PAGE.entries()) {
    const name = APPS[slug]!.name;
    assert.ok(html.includes(`<h2>Connect your ${name}</h2>`), `${slug} is not on the page`);
    assert.ok(html.includes(`>Connect ${name}</button>`), `${slug} has no button of its own`);
    assert.ok(html.includes(`read your ${name}`),
      `${slug}'s own three sentences are not on the page`);
    assert.ok(html.includes(`<input type="hidden" name="app" value="${i}">`),
      `${slug}'s button does not say which row it is, so it would spend row 0`);
  }

  // FOUR CONNECTS, ONE SKIP. "Skip still applies to the whole page."
  assert.equal((html.match(/<button class="go"/g) ?? []).length, 4, "one button per app");
  assert.equal((html.match(/<button class="later"/g) ?? []).length, 1,
    "the page is one decision, so it declines once");
  assert.equal((html.match(new RegExp(`action="/c/${r.token}/skip"`, "g")) ?? []).length, 1);
  assert.match(html, /This is optional/, "the optional sentence is per page, and still there");
  assert.equal(r.log.toolkit.length, 4, "the catalog was asked once per app and no more");
});

await check("each card connects its OWN app — the third button is not the first", async () => {
  const r = await pageRig(PAGE);
  const res = await connectRoute(
    goReq(r.token, asHeader(r.ownerToken), 2, "ATTEMPT-7"), r.env, r.deps);
  assert.equal(res.status, 303);
  await bodyOf(res, "page go card 2");

  assert.equal(r.log.authorize.length, 1);
  const call = r.log.authorize[0]!;
  assert.equal(call.toolkit, PAGE[2],
    "the vendor was asked to connect a different app than the one tapped");
  assert.equal(call.callbackUrl,
    callbackUrl(r.token, "https://api.anticipy.ai/c", "ATTEMPT-7", 2),
    "the callback does not say which row it is finishing");
  assert.ok(call.callbackUrl.includes("app=2"), "the index does not ride out to the vendor");
  assert.ok(!call.callbackUrl.includes(PAGE[2]!),
    "the app's SLUG is on a URL another company reads — an index is what rides, "
    + "because \"2\" tells whoever reads it nothing");

  // ONLY THAT ROW IS SPENT.
  for (let i = 0; i < PAGE.length; i++) {
    const row = r.store.rows.get(await pageHandle(r.token, i))!;
    assert.equal(row.used_at, i === 2 ? NOW : null, `row ${i} has the wrong used bit`);
  }
});

await check("the callback finishes the row it names, and writes THAT app", async () => {
  const r = await pageRig(PAGE);
  const done = await connectCard(r, 2, "ca_VENDOR_2");
  assert.equal(done.status, 200);
  await bodyOf(done, "page done card 2");
  assert.equal(r.written.length, 1);
  assert.equal(r.written[0]!.toolkit, PAGE[2],
    "the connection was filed under a different app than the one that was connected");
  assert.equal(r.written[0]!.connected_account_id, "ca_VENDOR_2");
  assert.equal(r.written[0]!.writes_enabled, false, "a page must not arrive write-enabled either");
  assert.equal(r.store.rows.get(await pageHandle(r.token, 2))!.completed_at, NOW);
  assert.equal(r.store.rows.get(await tokenHandle(r.token))!.completed_at, null,
    "the lease was taken on row 0 for a callback about row 2");
});

await check("the background poll watches the row that was SPENT, not row 0", async () => {
  // The poll cannot be started in this suite — no ExecutionContext is passed, on
  // purpose, because a real timer nobody can join held this file open for eleven
  // minutes per redirect. So the handle it would be started with is checked
  // where it is decided, and the call site is pinned by its own literal below.
  const r = await pageRig(PAGE);
  const go = await connectPageGo(r.token, {
    signedInAs: OWNER, store: r.store, provider: r.deps.provider,
    baseUrl: "https://api.anticipy.ai/c", state: null, now: NOW, app: 3,
  });
  assert.equal(go.state, "ok");
  assert.equal(go.state === "ok" && go.handle, await pageHandle(r.token, 3),
    "the poll would watch a row nobody is connecting");
  assert.notEqual(await pageHandle(r.token, 3), await tokenHandle(r.token));

  const anchor = "startWaiting(env, deps, go.handle, go.owner, go.toolkit, now, ctx);";
  assert.equal(occurrences(SOURCE, anchor), 1,
    "the redirect starts the backup on something other than the row it just spent");
});

await check("one app whose sentences cannot be written is DROPPED, the other three connect",
  async () => {
    const broken = PAGE[1]!;
    const r = await pageRig(PAGE, {
      // The catalog answers; the writer has nothing to say about this one. That
      // is a 503 for a one-app link and must be one missing card on a page.
      sentences: async (meta: ToolkitMeta) => (meta.slug === broken ? [] : [
        `Anticipy can read your ${meta.name} for the things you ask about.`,
        `It can add to your ${meta.name} when you ask it to.`,
        "You can turn this off any time in Settings.",
      ]),
    });

    const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 200,
      "one bad catalog row refused the whole page — the other three were connectable");
    const html = await bodyOf(res, "page view with a drop");
    assert.ok(!html.includes(APPS[broken]!.name), "the app that cannot be described is on the page");
    assert.equal((html.match(/<button class="go"/g) ?? []).length, 3, "three apps, three buttons");
    for (const i of [0, 2, 3]) {
      assert.ok(html.includes(`<h2>Connect your ${APPS[PAGE[i]!]!.name}</h2>`),
        `${PAGE[i]} went missing with the broken one`);
    }

    // AND THEY REALLY CONNECT — a card drawn is a card that works.
    for (const i of [0, 2, 3]) {
      const done = await connectCard(r, i, `ca_VENDOR_${i}`);
      await bodyOf(done, `drop-page done ${i}`);
      assert.equal(done.status, 200, `card ${i} did not connect`);
    }
    assert.deepEqual(r.written.map((c) => c.toolkit), [PAGE[0], PAGE[2], PAGE[3]]);

    // THE DROPPED ROW IS UNTOUCHED. Nothing spent, nothing written: fix the
    // catalog row and the same link offers it again.
    assert.equal(r.store.rows.get(await pageHandle(r.token, 1))!.used_at, null,
      "the dropped app's link was spent by a page that never offered it");
  });

await check("a page whose apps are ALL undrawable is the same 409 a one-app link gets",
  async () => {
    const r = await pageRig([VENDOR_NAMED[0]!.slug, NAMELESS[0]!.slug]);
    const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 409);
    const html = await bodyOf(res, "page all undrawable");
    assert.ok(!html.includes("<form"), "a Connect button over a page with nothing on it");
    assert.equal(r.store.rows.get(await tokenHandle(r.token))!.used_at, null,
      "the refusal spent the owner's link");
  });

await check("A BROWSER THAT DIES AFTER THE SECOND comes back to apps three and four",
  async () => {
    const r = await pageRig(PAGE);
    await bodyOf(await connectCard(r, 0, "ca_VENDOR_0"), "walk done 0");
    await bodyOf(await connectCard(r, 1, "ca_VENDOR_1"), "walk done 1");

    // The browser dies here. The person opens the SAME link again — the one in
    // the text, the one on the card — and the page is what is left of it.
    const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 200, "coming back to a half-walked page is a dead end");
    const html = await bodyOf(res, "page after two");

    for (const i of [0, 1]) {
      assert.ok(!html.includes(`>Connect ${APPS[PAGE[i]!]!.name}</button>`),
        `${PAGE[i]} is offered again after it was connected`);
    }
    for (const i of [2, 3]) {
      assert.ok(html.includes(`<h2>Connect your ${APPS[PAGE[i]!]!.name}</h2>`),
        `${PAGE[i]} was lost when the browser died`);
      assert.ok(html.includes(`<input type="hidden" name="app" value="${i}">`),
        `${PAGE[i]}'s place on the page moved — the indices are the rows, not the cards`);
    }
    assert.equal((html.match(/<button class="go"/g) ?? []).length, 2,
      "the walk restarted from the beginning");

    // And the rest of the walk still finishes.
    await bodyOf(await connectCard(r, 2, "ca_VENDOR_2"), "walk done 2");
    await bodyOf(await connectCard(r, 3, "ca_VENDOR_3"), "walk done 3");
    assert.deepEqual(r.written.map((c) => c.toolkit), [...PAGE]);

    // Now there is nothing left, and the page says so rather than drawing an
    // empty consent screen.
    const empty = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)),
      r.env, r.deps);
    assert.equal(empty.status, 410);
    assert.match(await bodyOf(empty, "page all used"), /has been used/i);
  });

await check("the done page hands back the rest of the page, and counts them honestly",
  async () => {
    const r = await pageRig(PAGE);
    const first = await connectCard(r, 0, "ca_VENDOR_0");
    const html = await bodyOf(first, "page done with rest");
    assert.ok(html.includes(`href="/c/${r.token}"`),
      "the walk ends here — there is no way back to the three they have not done");
    assert.ok(html.includes("Set up the others"));
    assert.ok(html.includes("anticipy://connected/"), "the way back into the app went missing");

    // Down to one, and "the others" stops being true.
    await bodyOf(await connectCard(r, 1, "ca_VENDOR_1"), "rest 1");
    const last = await connectCard(r, 2, "ca_VENDOR_2");
    const lastHtml = await bodyOf(last, "page done with one left");
    assert.ok(lastHtml.includes("Set up the last one"), "one app left was called \"the others\"");

    // And when there is nothing left, nothing is offered.
    const end = await connectCard(r, 3, "ca_VENDOR_3");
    const endHtml = await bodyOf(end, "page done with none left");
    assert.ok(!endHtml.includes("Set up the"),
      "a walk with nothing left still offered a way back to an empty page");
  });

await check("the phone's attempt id survives the walk back to the page", async () => {
  const r = await pageRig(PAGE);
  const go = await connectRoute(
    goReq(r.token, asHeader(r.ownerToken), 0, "ATTEMPT-42"), r.env, r.deps);
  await bodyOf(go, "walk go with state");
  const done = await connectRoute(getReq(
    `${doneFor(r.token, 0, "ca_VENDOR_0")}&state=ATTEMPT-42`, asHeader(r.ownerToken)),
    r.env, r.deps);
  const html = await bodyOf(done, "walk done with state");
  assert.ok(html.includes(`href="/c/${r.token}?state=ATTEMPT-42"`),
    "the way back drops the attempt id, so the app stops being able to match the walk");
});

await check("Skip applies to the WHOLE page — four apps, four declines, one tap", async () => {
  const r = await pageRig(PAGE);
  const res = await connectRoute(
    skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 200);
  // The apostrophe is escaped on its way to the page, so the assertion reads the
  // bytes a person's browser gets rather than the constant in the source.
  const skipHtml = await bodyOf(res, "page skip");
  assert.match(skipHtml, /bring these up again/i,
    "four apps were turned down and the page said \"this one\", which reads as if the "
    + "other three are still coming");
  assert.ok(!skipHtml.includes("bring this one up again"),
    "the one-app sentence was shown over a page of four");

  assert.equal(r.store.nudges.size, 4,
    "somebody who ticked four apps and said not now had one of them recorded");
  for (const slug of PAGE) {
    const row = r.store.nudges.get(`${OWNER}::${slug}`)!;
    assert.equal(row.state, "declined", `${slug} was not declined`);
    assert.equal(row.level, 1, `${slug} landed on the wrong rung`);
  }
  // NOT SPENT. Changing your mind inside the ten minutes still works, on every
  // card, exactly as it does for a one-app link.
  for (let i = 0; i < PAGE.length; i++) {
    assert.equal(r.store.rows.get(await pageHandle(r.token, i))!.used_at, null);
  }
});

await check("a page half connected and then skipped declines only what was left", async () => {
  const r = await pageRig(PAGE);
  await bodyOf(await connectCard(r, 0, "ca_VENDOR_0"), "half done 0");
  // The connection flips the nudge row through `onConnected` in production; the
  // suite's fake writes connections only, so the row is seeded here to be the
  // thing `recordSkip` must refuse to overwrite.
  await r.store.putNudge({
    user_id: OWNER as never, toolkit: PAGE[0]! as never, state: "connected", level: 0,
    snooze_until: null, trigger: null, sent_at: NOW - 1000, acted_at: NOW - 500, channel: "app",
  });

  const res = await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(res.status, 200);
  await bodyOf(res, "page skip after one");
  assert.equal(r.store.nudges.get(`${OWNER}::${PAGE[0]}`)!.state, "connected",
    "a live connection was replaced by a decline because the page was skipped");
  for (const slug of PAGE.slice(1)) {
    assert.equal(r.store.nudges.get(`${OWNER}::${slug}`)!.state, "declined", slug);
  }
});

await check("single use is per app, and the whole page still expires in ten minutes", async () => {
  const r = await pageRig(PAGE);
  await bodyOf(await connectRoute(goReq(r.token, asHeader(r.ownerToken), 1), r.env, r.deps),
    "reuse first");
  const second = await connectRoute(goReq(r.token, asHeader(r.ownerToken), 1), r.env, r.deps);
  assert.equal(second.status, 410, "the same card was spendable twice");
  assert.match(await bodyOf(second, "reuse second"), /has been used/i);
  assert.equal(r.log.authorize.length, 1, "the vendor was asked twice for one card");

  // Another card on the same page is untouched by that.
  const other = await connectRoute(goReq(r.token, asHeader(r.ownerToken), 2), r.env, r.deps);
  assert.equal(other.status, 303, "one spent card killed the rest of the page");
  await bodyOf(other, "reuse other card");

  // TEN MINUTES, for the page and every card on it.
  const old = await pageRig(PAGE, { expiresAt: NOW - 1 });
  const view = await connectRoute(getReq(`/c/${old.token}`, asHeader(old.ownerToken)),
    old.env, old.deps);
  assert.equal(view.status, 410);
  assert.match(await bodyOf(view, "page expired view"), /expired/i);
  for (const app of [0, 2, 3]) {
    const tap = await connectRoute(goReq(old.token, asHeader(old.ownerToken), app),
      old.env, old.deps);
    assert.equal(tap.status, 410, `card ${app} outlived the link`);
    await bodyOf(tap, `page expired go ${app}`);
  }
  assert.equal(old.log.authorize.length, 0, "an expired page still opened a vendor flow");
});

await check("a STRANGER cannot redeem a card, and cannot measure the page either", async () => {
  const r = await pageRig(PAGE);
  const view = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.strangerToken)),
    r.env, r.deps);
  assert.equal(view.status, 403);
  const html = await bodyOf(view, "page stranger view");
  for (const slug of PAGE) {
    assert.ok(!html.includes(APPS[slug]!.name), `${slug} was named to a signed-in stranger`);
  }
  assert.equal(r.store.reads, 1,
    "the page was WALKED for a stranger — how many apps somebody is connecting is a fact "
    + "about them, and the size of the walk is readable off a stopwatch");

  for (const app of [0, 1, 2, 3]) {
    const tap = await connectRoute(goReq(r.token, asHeader(r.strangerToken), app), r.env, r.deps);
    assert.equal(tap.status, 403, `a stranger spent card ${app}`);
    await bodyOf(tap, `page stranger go ${app}`);
    assert.equal(r.store.rows.get(await pageHandle(r.token, app))!.used_at, null);
  }
  assert.equal(r.log.authorize.length, 0);
  assert.equal(r.store.nudges.size, 0);

  // And signed out, nothing at all: not one store read, on any card.
  const anon = await pageRig(PAGE);
  for (const app of [0, 3]) {
    const tap = await connectRoute(goReq(anon.token, null, app), anon.env, anon.deps);
    assert.equal(tap.status, 401);
    await bodyOf(tap, `page anon go ${app}`);
  }
  assert.equal(anon.store.reads, 0, "a caller who proved nothing reached the store");
});

await check("a row at this token's OWN handle bound to somebody else is not on the page",
  async () => {
    // THE WRONG-PERSON FAILURE, ARRIVING THROUGH A LOOP VARIABLE. The minter
    // refuses a mixed batch (`ConnectionsStore.putAll`), so this cannot come out
    // of the shipped path — but if a store ever hands one back, drawing it would
    // put a stranger's app on the owner's consent screen and let the owner
    // connect it. The page ends at that row rather than skipping over it: a hole
    // in the middle would make every index after it mean one thing to the reader
    // and another to the writer.
    const r = await pageRig(PAGE);
    r.store.rows.set(await pageHandle(r.token, 2), {
      token_handle: await pageHandle(r.token, 2), user_id: STRANGER, toolkit: PAGE[2]!,
      alias: null, expires_at: NOW + LINK_TTL_MS, used_at: null, completed_at: null,
    });

    const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 200);
    const html = await bodyOf(res, "page with a stranger's row");
    assert.equal((html.match(/<button class="go"/g) ?? []).length, 2,
      "the page did not stop at the row that is not this owner's");
    assert.ok(!html.includes(`<input type="hidden" name="app" value="3">`),
      "the page carried on past the foreign row, so index 3 means two different rows");

    // And it cannot be connected either — `locate` compares the session to that
    // row's own owner, and the owner is not it.
    const tap = await connectRoute(goReq(r.token, asHeader(r.ownerToken), 2), r.env, r.deps);
    assert.equal(tap.status, 403, "the owner connected a row bound to somebody else");
    await bodyOf(tap, "page stranger row go");
    assert.equal(r.log.authorize.length, 0);

    // A skip must not walk that row's ladder either.
    const skip = await connectRoute(skipReq(r.token, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(skip.status, 200);
    await bodyOf(skip, "page stranger row skip");
    assert.equal(r.store.nudges.size, 2,
      "a decline was recorded against a row this owner does not own");
  });

await check("an index that is not one of the page's is refused, never rounded to app 0",
  async () => {
    // ROUNDING IS THE ONLY WAY THIS PARAMETER COULD HURT ANYBODY: it would open
    // a vendor flow for an app nobody tapped, and file the credential that comes
    // back under the wrong name.
    for (const bad of ["two", "1e0", "0x2", "-1", "1.0", "+3", String(MAX_PAGE_APPS), "999"]) {
      const r = await pageRig(PAGE);
      const tap = await connectRoute(goReq(r.token, asHeader(r.ownerToken), bad), r.env, r.deps);
      assert.equal(tap.status, 410, `${JSON.stringify(bad)} was accepted as an index`);
      await bodyOf(tap, `page bad index ${bad}`);
      assert.equal(r.log.authorize.length, 0, `${JSON.stringify(bad)} opened a vendor flow`);
      for (let i = 0; i < PAGE.length; i++) {
        assert.equal(r.store.rows.get(await pageHandle(r.token, i))!.used_at, null,
          `${JSON.stringify(bad)} spent row ${i}`);
      }
    }

    // THE CONTROL, and the line the refusals are drawn against: surrounding
    // whitespace is transport and is trimmed, because it cannot change WHICH row
    // is selected — only the digits can, and they are read whole or not at all.
    // A field that is nothing but spaces reads as absent, which is a one-app
    // link and row 0.
    const spaced = await pageRig(PAGE);
    const ok = await connectRoute(
      goReq(spaced.token, asHeader(spaced.ownerToken), " 1 "), spaced.env, spaced.deps);
    assert.equal(ok.status, 303, "a padded index was refused, which is an outage, not a guard");
    await bodyOf(ok, "page padded index");
    assert.equal(spaced.log.authorize[0]!.toolkit, PAGE[1],
      "a padded index selected a different row than its digits name");

    // The same on the callback, where rounding would file one app's credential
    // under another app's name.
    const r = await pageRig(PAGE);
    await bodyOf(await connectRoute(goReq(r.token, asHeader(r.ownerToken), 2), r.env, r.deps),
      "bad callback go");
    for (const bad of ["two", "-1", "999"]) {
      const done = await connectRoute(
        getReq(doneFor(r.token, bad, "ca_VENDOR_2"), asHeader(r.ownerToken)), r.env, r.deps);
      assert.equal(done.status, 410, `${JSON.stringify(bad)} was accepted on the callback`);
      await bodyOf(done, `page bad done ${bad}`);
      assert.equal(r.written.length, 0, `${JSON.stringify(bad)} wrote a connection`);
    }

    // AND THE SAME AGAIN WITH ROW 0 LIVE, because the loop above passes for the
    // wrong reason on its own: a callback rounded to app 0 lands on a row that
    // was never tapped, which `callbackDeadline` calls dead anyway. Measured —
    // the rounding mutation SURVIVED that loop. So here row 0 IS spent and is
    // waiting for its own callback, and the unreadable index carries row 0's own
    // account id: rounding writes that connection, refusing writes nothing.
    const live = await pageRig(PAGE);
    await bodyOf(await connectRoute(goReq(live.token, asHeader(live.ownerToken), 0),
      live.env, live.deps), "rounding go 0");
    await bodyOf(await connectRoute(goReq(live.token, asHeader(live.ownerToken), 2),
      live.env, live.deps), "rounding go 2");
    for (const bad of ["two", "-1", "999"]) {
      const done = await connectRoute(
        getReq(doneFor(live.token, bad, "ca_VENDOR_0"), asHeader(live.ownerToken)),
        live.env, live.deps);
      assert.equal(done.status, 410,
        `${JSON.stringify(bad)} was rounded to app 0, which had a real connect in flight`);
      await bodyOf(done, `page rounded done ${bad}`);
      assert.equal(live.written.length, 0,
        `${JSON.stringify(bad)} finished a row the vendor's callback did not name`);
      assert.equal(live.store.rows.get(await tokenHandle(live.token))!.completed_at, null,
        `${JSON.stringify(bad)} burned row 0's exactly-once lease`);
    }
  });

await check("a callback naming ANOTHER card's row binds nothing", async () => {
  // The index is on a query string a browser can edit. It selects a row — and
  // the row's own toolkit then has to be vouched for by the vendor's list before
  // a byte is written, which is what makes an edited index worthless.
  const r = await pageRig(PAGE);
  await bodyOf(await connectRoute(goReq(r.token, asHeader(r.ownerToken), 2), r.env, r.deps),
    "cross-card go");
  // Card 3's account id, pointed at card 2's row.
  const done = await connectRoute(
    getReq(doneFor(r.token, 2, "ca_VENDOR_3"), asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(done.status, 200);
  assert.match(await bodyOf(done, "cross-card done"), /didn&#39;t finish/i);
  assert.equal(r.written.length, 0,
    "an account the vendor holds on ANOTHER app was filed under this row");
  assert.equal(r.store.rows.get(await pageHandle(r.token, 2))!.completed_at, null,
    "the exactly-once lease was burned on a callback that wrote nothing");
});

await check("a callback for a card that never went through /go is dead", async () => {
  const r = await pageRig(PAGE);
  const done = await connectRoute(
    getReq(doneFor(r.token, 3, "ca_VENDOR_3"), asHeader(r.ownerToken)), r.env, r.deps);
  assert.equal(done.status, 410, "a callback arrived for a card nobody tapped");
  await bodyOf(done, "page untapped done");
  assert.equal(r.written.length, 0);
});

// ---------------------------------------------------------------------------
// THE CONTROL — a one-app link is what it was, byte for byte.
// ---------------------------------------------------------------------------

/**
 * The body a one-app link's page rendered BEFORE any of the above existed,
 * recorded from the committed renderer (`git show HEAD:...connect.ts`) driven
 * over the same fixture, 2026-09-06. The shell around it — doctype, title,
 * stylesheet — is shared with every other page in this file and is not what
 * pages touched; this is.
 *
 * IT IS A GOLDEN AND THAT IS THE POINT. Multi-app is allowed to add an intro, an
 * `<h2>`, a hidden index and a link back to the rest — and NONE of them may
 * appear here, because every link in the wild today is one of these and the
 * phone mints them by the thousand. If a deliberate copy change ever lands on
 * this page, this string is updated in the same diff, by hand, and whoever does
 * it has said out loud that every one-app link in every message thread changed.
 */
const ONE_APP_BODY = `<body>
<img class="logo" src="https://cdn.example.invalid/z.png" alt="">
<h1>Connect your Zellibrix</h1>
<p>Where your team keeps its notes.</p>
<p>Here's what Anticipy would be able to do:</p>
<ul>
  <li>Anticipy can read your Zellibrix for the things you ask about.</li>
  <li>It can add to your Zellibrix when you ask it to.</li>
  <li>You can turn this off any time in Settings.</li>
</ul>
<form method="post" action="/c/{TOKEN}/go">
  <button class="go" type="submit">Connect Zellibrix</button>
</form>
<form class="later" method="post" action="/c/{TOKEN}/skip">
  <button class="later" type="submit">Skip for now</button>
</form>
<p class="fine">This is optional — Anticipy works fine without it. You can turn it off any time in Settings. This link works for ten minutes and only for you.</p>
</body>`;

await check("CONTROL: a ONE-APP link is byte-identical to what it was before pages existed",
  async () => {
    const r = await rig();
    const res = await connectRoute(getReq(`/c/${r.token}`, asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(res.status, 200);
    const html = await bodyOf(res, "control one-app view");
    const end = html.indexOf("</body>") + "</body>".length;
    const body = normalise(html.slice(html.indexOf("<body>"), end), r.token);
    assert.equal(body, ONE_APP_BODY,
      "the one-app connect page changed; every link already in somebody's message thread "
      + "renders this");
    assert.ok(!html.includes('name="app"'),
      "a one-app link's button carries a page index, so its callback would carry one back");

    // THE TAP. No index posted, none on the callback: the URL the vendor is
    // handed is the URL it has always been handed.
    const go = await connectRoute(
      postReq(`/c/${r.token}/go`, asHeader(r.ownerToken), { form: { state: "ATTEMPT-1" } }),
      r.env, r.deps);
    assert.equal(go.status, 303);
    await bodyOf(go, "control one-app go");
    const call = r.log.authorize[0]!;
    assert.equal(call.callbackUrl,
      callbackUrl(r.token, "https://api.anticipy.ai/c", "ATTEMPT-1"));
    assert.ok(!call.callbackUrl.includes("app="), "an index reached a one-app callback");

    // THE CALLBACK. Nothing is walked, nothing is counted, and the page offers
    // no rest of a page that does not exist.
    const readsBefore = r.store.reads;
    const done = await connectRoute(
      getReq(doneUrl(r.token, "status=success&connected_account_id=ca_VENDOR_1&state=ATTEMPT-1"),
        asHeader(r.ownerToken)), r.env, r.deps);
    assert.equal(done.status, 200);
    const doneHtml = await bodyOf(done, "control one-app done");
    assert.ok(!doneHtml.includes("Set up the"),
      "a one-app callback offered a walk back to a page with one app on it");
    assert.ok(doneHtml.includes("anticipy://connected/zellibrix"));
    assert.equal(r.store.reads - readsBefore, 2,
      "a one-app callback paid for a page walk it can never have — it is one `locate` read "
      + "and one exactly-once lease, and a walk would be up to twelve more");
    assert.equal(r.written.length, 1);

    // AND THE DECLINE. One row read, one row written, one answer.
    const s = await rig();
    const skip = await connectRoute(skipReq(s.token, asHeader(s.ownerToken)), s.env, s.deps);
    assert.equal(skip.status, 200);
    assert.match(await bodyOf(skip, "control one-app skip"), /bring this one up again/i);
    assert.equal(s.store.nudges.size, 1);
  });

await check("CONTROL: a one-app link's row is where it has always been", async () => {
  // The derivation, stated as the property the whole backward-compatibility
  // story rests on: app 0 of a page IS `tokenHandle`, and no other index is.
  const token = await b64urlToken();
  assert.equal(await pageHandle(token, 0), await tokenHandle(token),
    "row 0 moved, so every link already minted resolves to nothing");
  assert.equal(await pageHandle(token), await tokenHandle(token), "the default is not row 0");
  const seen = new Set<string>();
  for (let i = 0; i < MAX_PAGE_APPS; i++) seen.add(await pageHandle(token, i));
  assert.equal(seen.size, MAX_PAGE_APPS, "two cards of one page share a row");
  // A page handle cannot be some OTHER token's plain handle: the separator is
  // outside the token alphabet.
  assert.notEqual(await pageHandle(token, 1), await tokenHandle(`${token}1`));
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

// ===========================================================================
// MUTATION REPORT — A PAGE OF APPS, 2026-09-06.
//
// SEVENTEEN mutations over src/routes/connect.ts, each anchored on a literal
// asserted to occur EXACTLY ONCE (the harness refuses to patch otherwise: a
// regex that silently fails to match reads as a pass, and did so three times in
// one day on this feature). SIXTEEN went red on the first run; the seventeenth
// is the interesting one and is written up below.
//
//   M1  the render draws only `apps[0]` — the page before this round existed
//       -> "FOUR ticked apps are ONE link, and the page draws all four"
//   M2  the tapped index never reaches /go (`app = null`), so every card spends
//       row 0 — tapping the third app connects the first
//       -> "each card connects its OWN app — the third button is not the first"
//   M3  the same on the callback, so every /done finishes row 0
//       -> "the callback finishes the row it names, and writes THAT app"
//   M4  the hidden index is never rendered, so no button says which row it is
//       -> "FOUR ticked apps are ONE link, and the page draws all four"
//   M5  the background poll started on `tokenHandle(token)` again — row 0 while
//       row 3 is in flight, which is the one signal that survives a browser
//       dying on the way back from the vendor, pointed at the wrong app
//       -> "the background poll watches the row that was SPENT, not row 0"
//   M6  `single` forced false: an index on every link already in the wild
//       -> "CONTROL: a ONE-APP link is byte-identical ..."
//   M7  one undrawable app refuses the whole page again
//       -> "one app whose sentences cannot be written is DROPPED ..."
//   M8  /skip records only the first app on the page
//       -> "Skip applies to the WHOLE page — four apps, four declines, one tap"
//   M9  the done page never offers the rest of the page
//   M10 `remaining` hard-coded to 0
//       -> both: "the done page hands back the rest of the page, and counts
//          them honestly"
//   M11 the `unsayable` state unhandled — the LIVE RED this part was handed:
//       `refusalPage` has no case for it, returns undefined, and the leg throws
//       -> "a toolkit named after the vendor cannot put that word on the page"
//          and three more
//   M12 `pageHandle(token, 0)` stops being `tokenHandle(token)` — every link
//       already minted resolves to nothing
//       -> "the owner's own live link renders the app the catalog named"
//   M13 the page walk stops checking whose row it just read
//       -> "a row at this token's OWN handle bound to somebody else ..."
//   M14 an already-spent card is offered again
//       -> "expired, used and wrong-user each get their own page for the OWNER"
//   M15 a bad index rounded to app 0 on the tap
//       -> "an index that is not one of the page's is refused, never rounded"
//   M16 a bad index rounded to app 0 on the CALLBACK.
//       **SURVIVED THE FIRST RUN, and the test that should have killed it was
//       passing for the wrong reason.** The refusal cases all pointed at rows
//       that had never been through /go, and `callbackDeadline` calls an
//       unclaimed row dead anyway — so the 410 the check asserted arrived
//       whether the index was refused or rounded. The check now spends row 0
//       first and hands the bad index row 0's own account id, so rounding writes
//       a connection and refusing writes nothing. Re-run: RED.
//   M17 the skip page saying "this one" over a page of four
//       -> "Skip applies to the WHOLE page"
//
// AND FIVE MORE over src/connections/store.ts, reported in that suite.
// ===========================================================================

console.log(`connect-routes: ${passes} checks passed, ${failures} failed`);
if (failures) process.exit(1);
