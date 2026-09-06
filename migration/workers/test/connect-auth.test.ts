/**
 * test/connect-auth.test.ts — the one-tap phone code for a texted connect link.
 *
 *   node --experimental-strip-types migration/workers/test/connect-auth.test.ts
 *
 * WHAT IS REAL HERE AND WHAT IS NOT. The handler, the routing, the method
 * guards, the cross-site guard, the HTML, the status codes, the HMAC session
 * and the whole send/check path are the shipped code. The `connect_codes` store
 * is the SHIPPED D1 implementation running against a real SQLite loaded with
 * the real migration/d1/schema.sql — plus `CONNECT_CODES_DDL`, because that one
 * table has not landed in schema.sql yet and the store's SQL had to meet a real
 * database anyway. The text really leaves through src/messaging.ts `sendText`,
 * against a loopback Sendblue that records the body, so the code under test is
 * the code that runs in production down to the wire format.
 *
 * The `connect_links` store is a fake, for the same reason connect-routes.test.ts
 * fakes it: it is another module's table. It is written to that interface's own
 * rule — no `await` between a check and its write.
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH:
 *
 *   THE ORACLE. `POST /c/{token}/code` is the one endpoint in the product that
 *   must do real work for a real token and nothing for an invented one, so it
 *   is the natural place for the string-sorter connect.ts closed on its own
 *   three legs to reappear. Five tokens in five states — live, expired, spent,
 *   never-existed, and one whose owner has no phone — must produce ONE
 *   response, byte for byte once the caller's own token is normalised out.
 *
 *   THE CEILING. Five guesses, counted with a compare-and-set, and the sixth
 *   refused even when it is right.
 *
 *   THE WRONG LINK. A code texted for link A must not open link B, and the
 *   binding is the SIGNATURE rather than a comparison — so the check here
 *   presents A's cookie on B's path and expects nothing.
 *
 *   THE DROPPED STATE. The phone puts `state={attempt id}` on the link it opens
 *   and `ConnectHandoff.parseDone` refuses any callback that comes back without
 *   it. Until 2026-09-06 the code flow lost it — the 303 after a correct code
 *   went to `/c/{token}` with no query — so a person who proved who they were
 *   could finish the connect and the phone would refuse the deep link home. The
 *   state is carried through the offer, the send, the box and the redirect, it
 *   is carried VERBATIM, and one that was never sent is never invented.
 *
 *   THE SESSION THAT IS NOT A LOGIN. The cookie must be refused by
 *   src/pb/auth.ts `verifyToken`, must be scoped by Path to one link, must die
 *   at its stamped instant, and must not exist at all when
 *   ANTICIPY_AUTH_SECRET is unbound.
 *
 *   THE REGISTER. "Composio", "authorize", "permissions", "integration",
 *   "OAuth", "API", "verify" — every page body and every text message this
 *   suite produces is collected and scanned at the end. Bodies are scanned as
 *   the PERSON reads them (tags stripped), because `/c/{t}/verify` is a route
 *   name in a form action and not a word anybody is shown.
 *
 * MUTATIONS THIS FILE MUST GO RED ON (run, not asserted — see the report):
 *   the dead-link check dropped from mintAndSend; the spent-link check dropped;
 *   the per-link and per-owner ceilings dropped; the minimum gap dropped; the
 *   attempt ceiling dropped; `charge` moved after the compare; `spend` ignored;
 *   the MAC's handle term dropped (so any link's cookie opens any other);
 *   the session expiry not checked; the unset-secret refusal removed; the
 *   cross-site guard deleted; GET allowed on /verify; the code stored in the
 *   clear; SameSite=Lax weakened to none / the Path widened to "/".
 */
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken, verifyToken } from "../src/pb/auth.ts";
import {
  CALLBACK_WINDOW_MS, LINK_TTL_MS, SESSION_COOKIE, connectPageView, tokenHandle,
  type ClaimOutcome, type ConnectLinkStore, type StoredLink, type ToolkitMeta,
} from "../src/routes/connect.ts";
import {
  CODE_SESSION_GRACE_MS, CODE_TTL_MS, CONNECT_CODES_DDL, MAX_ATTEMPTS,
  MAX_CODES_PER_LINK, MAX_CODES_PER_OWNER, MIN_GAP_MS, SESSION_COOKIE_PREFIX,
  connectAuthRoute, connectAuthWiringInstalled, connectCodeText, connectCodesTableReady,
  connectSession, createD1ConnectCodeStore, createMemoryConnectCodeStore,
  parseConnectAuthPath,
  type ConnectAuthDeps, type ConnectAuthEnv,
} from "../src/routes/connect_auth.ts";

let failures = 0;
let passes = 0;
async function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  try { await fn(); passes++; }
  catch (err) { failures++; console.error("FAIL " + what + "\n     " + (err as Error).message); }
}

/** Every page body and every text this suite produces, for the scans at the end. */
const BODIES: { where: string; text: string }[] = [];
const TEXTS: { where: string; text: string }[] = [];

// ---------------------------------------------------------------------------
// A LOOPBACK SENDBLUE. The real sendText runs; only the socket is ours.
// ---------------------------------------------------------------------------

interface SentText { to: string; body: string }
const SENT: SentText[] = [];
let sendFails = false;

const realFetch = globalThis.fetch;
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  if (!url.startsWith("http://127.0.0.1:9797")) {
    throw new Error("the suite reached a host it should never reach: " + url);
  }
  const body = JSON.parse(String(init?.body ?? "{}")) as { number?: string; content?: string };
  if (sendFails) {
    return new Response(JSON.stringify({ status: "ERROR", error_code: 400 }),
      { status: 200, headers: { "content-type": "application/json" } });
  }
  SENT.push({ to: String(body.number ?? ""), body: String(body.content ?? "") });
  TEXTS.push({ where: "sms", text: String(body.content ?? "") });
  return new Response(JSON.stringify({ message_handle: "mh_1", status: "QUEUED" }),
    { status: 200, headers: { "content-type": "application/json" } });
}) as typeof fetch;

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const NOW = 1_757_000_000_000;
const OWNER_HOUR = 60 * 60 * 1000;
const PB_NOW = "2026-09-05 12:00:00.000Z";
const OWNER = "ownerrefaaaaaa1";
const STRANGER = "strangerowner12";
const PHONE = "+15551230000";
const SECRET = "connect-auth-test-secret";

/** Two invented apps. Nothing in the Worker knows these names. */
const APPS: Record<string, ToolkitMeta> = {
  zellibrix: {
    slug: "zellibrix", name: "Zellibrix", logo: null,
    description: "Where your team keeps its notes.", appUrl: null,
    scopes: ["notes.read"],
  },
  quandle_mail: {
    slug: "quandle_mail", name: "Quandle Mail", logo: null,
    description: null, appUrl: null, scopes: ["mail.read"],
  },
};

/** The `connect_links` store, to the interface's own rule: check and write with
 *  no await between them. */
class MemoryLinkStore implements ConnectLinkStore {
  rows = new Map<string, StoredLink>();
  reads = 0;
  put(row: StoredLink): void { this.rows.set(row.token_handle, { ...row }); }
  async read(handle: string): Promise<StoredLink | null> {
    this.reads++;
    const row = this.rows.get(handle);
    return row ? { ...row } : null;
  }
  async claim(handle: string, usedAt: number): Promise<ClaimOutcome> {
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.used_at !== null) return { won: false, row: { ...row } };
    const next = { ...row, used_at: usedAt };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }
  async complete(handle: string, at: number): Promise<ClaimOutcome> {
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.completed_at !== null) return { won: false, row: { ...row } };
    const next = { ...row, completed_at: at };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }
  async release(handle: string, at: number): Promise<ClaimOutcome> {
    const row = this.rows.get(handle);
    if (!row) return { won: false, row: null };
    if (row.completed_at !== at) return { won: false, row: { ...row } };
    const next = { ...row, completed_at: null };
    this.rows.set(handle, next);
    return { won: true, row: { ...next } };
  }
}

interface Rig {
  db: FakeD1;
  env: ConnectAuthEnv;
  deps: ConnectAuthDeps;
  links: MemoryLinkStore;
  token: string;
  handle: string;
  clock: { now: number };
  ownerToken: string;
  strangerToken: string;
  /** Mint a second link for the same owner and return its token + handle. */
  another(opts?: { toolkit?: string; owner?: string }): Promise<{ token: string; handle: string }>;
}

interface RigOpts {
  toolkit?: string;
  expiresAt?: number;
  usedAt?: number | null;
  /** No phone anywhere, or an explicit empty profile phone. */
  phone?: string | null;
  profilePhone?: string | null;
  toolkitName?: (slug: string) => Promise<string | null>;
  secret?: string;
}

const newToken = (): string => randomBytes(32).toString("base64url");

async function rig(opts: RigOpts = {}): Promise<Rig> {
  const db = new FakeD1();
  db.db.exec(CONNECT_CODES_DDL);
  for (const [id, key, phone] of [[OWNER, "key-owner", opts.phone === undefined ? PHONE : (opts.phone ?? "")],
                                  [STRANGER, "key-stranger", "+15559990000"]] as [string, string, string][]) {
    db.db.prepare(
      `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
         password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,?,'')`,
    ).run(id, PB_NOW, PB_NOW, `${id}@anticipy-test.invalid`, key, phone);
  }
  if (opts.profilePhone !== undefined) {
    db.db.prepare(
      `INSERT INTO owner_profile (id, created, updated, owner_id, phone, owner_ref)
       VALUES (?,?,?,?,?,?)`,
    ).run("prof" + OWNER, PB_NOW, PB_NOW, OWNER, opts.profilePhone ?? "", OWNER);
  }

  const env = {
    DB: asD1(db),
    ANTICIPY_AUTH_SECRET: opts.secret === undefined ? SECRET : opts.secret,
    SENDBLUE_API_KEY_ID: "sb-id",
    SENDBLUE_API_SECRET_KEY: "sb-secret",
    SENDBLUE_FROM_NUMBER: "+15550001111",
    SENDBLUE_API_BASE: "http://127.0.0.1:9797",
  } as unknown as ConnectAuthEnv;

  const links = new MemoryLinkStore();
  const slug = opts.toolkit ?? "zellibrix";
  const token = newToken();
  const handle = await tokenHandle(token);
  links.put({
    token_handle: handle, user_id: OWNER, toolkit: slug, alias: null,
    expires_at: opts.expiresAt ?? NOW + LINK_TTL_MS,
    used_at: opts.usedAt ?? null, completed_at: null,
  });

  const clock = { now: NOW };
  const deps: ConnectAuthDeps = {
    links,
    codes: createD1ConnectCodeStore({ DB: asD1(db) }),
    toolkitName: opts.toolkitName ?? (async (s: string) => APPS[s]?.name ?? null),
    now: () => clock.now,
  };

  return {
    db, env, deps, links, token, handle, clock,
    ownerToken: await issueToken(env as never, OWNER, "key-owner"),
    strangerToken: await issueToken(env as never, STRANGER, "key-stranger"),
    async another(o = {}) {
      const t = newToken();
      const h = await tokenHandle(t);
      links.put({
        token_handle: h, user_id: (o.owner ?? OWNER), toolkit: o.toolkit ?? slug, alias: null,
        expires_at: NOW + LINK_TTL_MS, used_at: null, completed_at: null,
      });
      return { token: t, handle: h };
    },
  };
}

// --- requests ---------------------------------------------------------------

function getReq(path: string, headers: Record<string, string> = {}): Request {
  return new Request("https://api.anticipy.ai" + path, { headers });
}

function postReq(
  path: string,
  opts: { form?: Record<string, string>; origin?: string | null; fetchSite?: string;
          cookie?: string; auth?: string } = {},
): Request {
  const headers: Record<string, string> = {
    "content-type": "application/x-www-form-urlencoded",
  };
  const origin = opts.origin === undefined ? "https://api.anticipy.ai" : opts.origin;
  if (origin !== null) headers.Origin = origin;
  if (opts.fetchSite) headers["Sec-Fetch-Site"] = opts.fetchSite;
  if (opts.cookie) headers.Cookie = opts.cookie;
  if (opts.auth) headers.Authorization = opts.auth;
  return new Request("https://api.anticipy.ai" + path, {
    method: "POST", headers,
    body: new URLSearchParams(opts.form ?? {}).toString(),
  });
}

async function bodyOf(res: Response, where: string): Promise<string> {
  const text = await res.text();
  BODIES.push({ where, text });
  return text;
}

/** The same page for two different tokens differs only by the token, which the
 *  caller supplied. Normalise it out and the two must be byte-identical. */
const normalise = (html: string, token: string): string =>
  html.split(token).join("{TOKEN}");

/** How many times a literal appears. Counted rather than matched: a regex that
 *  silently stopped matching reads as a pass, and did so three times in one day
 *  on this feature. */
const occurrences = (haystack: string, needle: string): number =>
  haystack.split(needle).length - 1;

/** `name=value` out of a Set-Cookie, ready to send back as `Cookie`. */
function cookiePair(setCookie: string | null): string {
  assert.ok(setCookie, "expected a Set-Cookie");
  return String(setCookie).split(";")[0] as string;
}

/** Drive POST /code and pull the code back out of the text that was sent. */
async function askForCode(r: Rig, token = r.token): Promise<string | null> {
  const before = SENT.length;
  const res = await connectAuthRoute(postReq(`/c/${token}/code`), r.env, r.deps);
  assert.ok(res, "the route answered null for its own path");
  await bodyOf(res as Response, "POST /code");
  if (SENT.length === before) return null;
  const body = (SENT[SENT.length - 1] as SentText).body;
  const m = /\b(\d{6})\b/.exec(body);
  return m ? (m[1] as string) : null;
}

// ===========================================================================
// ROUTING AND METHODS
// ===========================================================================

await check("parseConnectAuthPath takes only the two shapes, anchored", () => {
  const t = "A".repeat(43);
  assert.deepEqual(parseConnectAuthPath(`/c/${t}/code`), { leg: "offer", token: t, segment: "code" });
  assert.deepEqual(parseConnectAuthPath(`/c/${t}/verify`), { leg: "check", token: t, segment: "verify" });
  for (const bad of [
    `/c/${t}`, `/c/${t}/go`, `/c/${t}/done`, `/c/${t}/code/`, `/c/${t}/code/x`,
    `/x/c/${t}/code`, `/c/../../etc/code`, `/c/${"A".repeat(42)}/code`,
    `/c/${"A".repeat(44)}/code`, `/c/${t}/CODE`, null, 42, undefined,
  ]) {
    assert.equal(parseConnectAuthPath(bad as never), null, String(bad));
  }
});

await check("connectAuthRoute answers null for connect.ts's own three legs", async () => {
  const r = await rig();
  for (const path of [`/c/${r.token}`, `/c/${r.token}/go`, `/c/${r.token}/done`, "/c/", "/health"]) {
    assert.equal(await connectAuthRoute(getReq(path), r.env, r.deps), null, path);
  }
});

await check("GET /code draws the offer and NEVER touches the link store", async () => {
  const r = await rig();
  const res = await connectAuthRoute(getReq(`/c/${r.token}/code`), r.env, r.deps);
  assert.ok(res);
  assert.equal((res as Response).status, 200);
  const html = await bodyOf(res as Response, "GET /code");
  assert.match(html, /Text me a code/);
  assert.equal(r.links.reads, 0, "the offer page read the store — that is the oracle");
  // And it says the optional line, which is a product rule, not decoration.
  assert.match(html, /optional/);
});

await check("the offer page is byte-identical for a real token and an invented one", async () => {
  const r = await rig();
  const fake = newToken();
  const a = await bodyOf(
    (await connectAuthRoute(getReq(`/c/${r.token}/code`), r.env, r.deps)) as Response, "GET /code real");
  const b = await bodyOf(
    (await connectAuthRoute(getReq(`/c/${fake}/code`), r.env, r.deps)) as Response, "GET /code fake");
  assert.equal(normalise(a, r.token), normalise(b, fake));
});

await check("the offer carries the phone's state, and invents one nobody sent", async () => {
  const r = await rig();
  const withState = await bodyOf((await connectAuthRoute(
    getReq(`/c/${r.token}/code?state=ATTEMPT-1234`), r.env, r.deps)) as Response,
    "GET /code with state");
  assert.equal(occurrences(withState, '<input type="hidden" name="state" value="ATTEMPT-1234">'), 1,
    "the offer drops the attempt id, so nothing downstream can hand it back to the phone");

  const without = await bodyOf((await connectAuthRoute(
    getReq(`/c/${r.token}/code`), r.env, r.deps)) as Response, "GET /code no state");
  assert.equal(occurrences(without, 'name="state"'), 0,
    "a state nobody sent was invented, and the phone refuses one it did not mint");

  // The same shape check connect.ts applies, in the same place: this value is
  // reflected into a hidden field, into a URL another company reads and into a
  // deep link.
  const bad = await bodyOf((await connectAuthRoute(
    getReq(`/c/${r.token}/code?state=${encodeURIComponent('"><script>x</script>')}`),
    r.env, r.deps)) as Response, "GET /code bad state");
  assert.equal(occurrences(bad, 'name="state"'), 0);
  assert.equal(occurrences(bad, "script"), 0);
});

await check("GET /verify is 405, and so is PUT anywhere — a prefetch cannot spend a guess", async () => {
  const r = await rig();
  const get = await connectAuthRoute(getReq(`/c/${r.token}/verify`), r.env, r.deps);
  assert.equal((get as Response).status, 405);
  assert.equal((get as Response).headers.get("allow"), "POST");
  const put = new Request(`https://api.anticipy.ai/c/${r.token}/code`, { method: "PUT" });
  const res = await connectAuthRoute(put, r.env, r.deps);
  assert.equal((res as Response).status, 405);
  assert.equal((res as Response).headers.get("allow"), "GET, POST");
  assert.equal(SENT.length, 0, "a 405 sent a text");
});

await check("an unwired Worker answers 503 and never 200 — and says so", async () => {
  const r = await rig();
  assert.equal(connectAuthWiringInstalled(), false,
    "nothing installs connect-auth wiring yet; when something does, this check moves");
  const res = await connectAuthRoute(postReq(`/c/${r.token}/code`), r.env);
  assert.equal((res as Response).status, 503);
  const html = await bodyOf(res as Response, "503 unwired");
  assert.match(html, /switched on/);
  assert.equal(SENT.length, 0);
});

await check("a cross-site POST is refused before anything is sent", async () => {
  const r = await rig();
  for (const opts of [{ origin: "https://evil.example" }, { fetchSite: "cross-site" }]) {
    SENT.length = 0;
    const res = await connectAuthRoute(postReq(`/c/${r.token}/code`, opts), r.env, r.deps);
    assert.equal((res as Response).status, 403);
    await bodyOf(res as Response, "403 cross-site");
    assert.equal(SENT.length, 0, "a cross-site POST made somebody's phone ring");
  }
});

await check("CONTROL: a same-origin POST with an Origin header still works", async () => {
  SENT.length = 0;
  const r = await rig();
  const code = await askForCode(r);
  assert.ok(code, "the cross-site guard refused our own page — that is an outage, not a guard");
});

// ===========================================================================
// THE ORACLE
// ===========================================================================

await check("POST /code answers one thing for five different tokens", async () => {
  const seen: string[] = [];
  const cases: { what: string; make: () => Promise<{ r: Rig; token: string }> }[] = [
    { what: "live", make: async () => { const r = await rig(); return { r, token: r.token }; } },
    { what: "expired", make: async () => {
        const r = await rig({ expiresAt: NOW - 1 }); return { r, token: r.token }; } },
    { what: "spent", make: async () => {
        const r = await rig({ usedAt: NOW - 1000 }); return { r, token: r.token }; } },
    { what: "never existed", make: async () => {
        const r = await rig(); return { r, token: newToken() }; } },
    { what: "owner has no phone", make: async () => {
        const r = await rig({ phone: "" }); return { r, token: r.token }; } },
  ];
  for (const c of cases) {
    SENT.length = 0;
    const { r, token } = await c.make();
    const res = await connectAuthRoute(postReq(`/c/${token}/code`), r.env, r.deps);
    assert.ok(res);
    assert.equal((res as Response).status, 200, c.what);
    const html = await bodyOf(res as Response, "POST /code " + c.what);
    seen.push(normalise(html, token));
    // Only the live one may text anybody.
    assert.equal(SENT.length, c.what === "live" ? 1 : 0, c.what + ": wrong number of texts");
  }
  for (const s of seen.slice(1)) {
    assert.equal(s, seen[0], "two tokens produced two pages — that is the oracle");
  }
});

await check("an explicit empty profile phone is canonical: no text, same answer", async () => {
  SENT.length = 0;
  // owners.phone is set, the profile row says the person removed it. Falling
  // back would re-affiliate the sign-up number they took off.
  const r = await rig({ phone: PHONE, profilePhone: "" });
  const res = await connectAuthRoute(postReq(`/c/${r.token}/code`), r.env, r.deps);
  assert.equal((res as Response).status, 200);
  await bodyOf(res as Response, "POST /code empty profile phone");
  assert.equal(SENT.length, 0);
});

await check("CONTROL: a profile phone is used when it is there", async () => {
  SENT.length = 0;
  const r = await rig({ phone: PHONE, profilePhone: "+15557778888" });
  await askForCode(r);
  assert.equal(SENT.length, 1);
  assert.equal((SENT[0] as SentText).to, "+15557778888");
});

await check("a provider that refuses leaves NO live code and the same answer", async () => {
  const r = await rig();
  sendFails = true;
  const res = await connectAuthRoute(postReq(`/c/${r.token}/code`), r.env, r.deps);
  sendFails = false;
  assert.equal((res as Response).status, 200);
  await bodyOf(res as Response, "POST /code provider refused");
  const rows = r.db.rows(`SELECT * FROM connect_codes`);
  assert.equal(rows.length, 0, "a code nobody received was left live in the table");
});

// ===========================================================================
// THE TEXT
// ===========================================================================

await check("the text names the app, the life and the phishing tell", async () => {
  SENT.length = 0;
  const r = await rig({ toolkit: "quandle_mail" });
  const code = await askForCode(r);
  assert.ok(code);
  const body = (SENT[0] as SentText).body;
  assert.ok(body.startsWith(code + " is your Anticipy code"), body);
  assert.match(body, /connect your Quandle Mail/);
  assert.match(body, /10 minutes/);
  assert.match(body, /If you didn't ask to connect anything, ignore this/);
});

await check("no app is hardcoded: a catalog that cannot answer still texts a code", async () => {
  SENT.length = 0;
  const r = await rig({ toolkitName: async () => { throw new Error("catalog down"); } });
  const code = await askForCode(r);
  assert.ok(code, "a catalog blip cost the whole code, not just the name");
  const body = (SENT[0] as SentText).body;
  assert.match(body, /connect the app you asked about/);
  assert.doesNotMatch(body, /Zellibrix/);
});

await check("connectCodeText carries no app name of its own", () => {
  assert.match(connectCodeText("123456", "Notion"), /connect your Notion\./);
  assert.match(connectCodeText("123456", null), /connect the app you asked about\./);
  assert.match(connectCodeText("123456", "   "), /connect the app you asked about\./);
});

await check("the code is stored HASHED and never in the clear", async () => {
  const r = await rig();
  const code = await askForCode(r);
  assert.ok(code);
  const rows = r.db.rows<Record<string, unknown>>(`SELECT * FROM connect_codes`);
  assert.equal(rows.length, 1);
  const dump = JSON.stringify(rows);
  assert.ok(!dump.includes(code as string), "the six digits are in the table: " + dump);
  assert.equal(String((rows[0] as Record<string, unknown>).code_hash).length, 64);
});

// ===========================================================================
// THE CEILINGS
// ===========================================================================

await check("one code at a time: a second ask spends the first", async () => {
  const r = await rig();
  const first = await askForCode(r);
  r.clock.now = NOW + MIN_GAP_MS;
  const second = await askForCode(r);
  assert.ok(first && second && first !== second);
  const live = r.db.rows<{ code_hash: string }>(
    `SELECT code_hash FROM connect_codes WHERE used_at IS NULL`);
  assert.equal(live.length, 1, "two live codes for one link");
  // And the first one no longer opens anything.
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: first as string } }), r.env, r.deps);
  assert.equal((res as Response).status, 400);
  await bodyOf(res as Response, "verify superseded code");
  assert.equal((res as Response).headers.get("set-cookie"), null);
});

await check("the minimum gap: a second ask inside a minute texts nothing", async () => {
  SENT.length = 0;
  const r = await rig();
  assert.ok(await askForCode(r));
  r.clock.now = NOW + MIN_GAP_MS - 1;
  assert.equal(await askForCode(r), null, "a text went out inside the gap");
  r.clock.now = NOW + MIN_GAP_MS;
  assert.ok(await askForCode(r), "the gap never reopens");
});

await check("the per-link ceiling stops at MAX_CODES_PER_LINK", async () => {
  const r = await rig();
  for (let i = 0; i < MAX_CODES_PER_LINK; i++) {
    r.clock.now = NOW + i * MIN_GAP_MS;
    assert.ok(await askForCode(r), "ask " + i);
  }
  r.clock.now = NOW + MAX_CODES_PER_LINK * MIN_GAP_MS;
  assert.equal(await askForCode(r), null, "the per-link ceiling did not hold");
});

await check("the per-owner ceiling holds ACROSS links — a second stolen link sprays no more",
  async () => {
    const r = await rig();
    const tokens = [r.token];
    for (let i = 0; i < MAX_CODES_PER_OWNER; i++) tokens.push((await r.another()).token);
    let sent = 0;
    for (let i = 0; i < tokens.length; i++) {
      // A fresh link each time, so only the OWNER ceiling can stop it.
      r.clock.now = NOW + i * MIN_GAP_MS;
      if (await askForCode(r, tokens[i] as string)) sent++;
    }
    assert.equal(sent, MAX_CODES_PER_OWNER,
      "the owner ceiling let " + sent + " texts through");
  });

await check("five guesses and no more, even when the sixth is right", async () => {
  const r = await rig();
  const code = await askForCode(r);
  assert.ok(code);
  for (let i = 0; i < MAX_ATTEMPTS; i++) {
    const wrong = String((Number(code) + i + 1) % 1000000).padStart(6, "0");
    const res = await connectAuthRoute(
      postReq(`/c/${r.token}/verify`, { form: { code: wrong } }), r.env, r.deps);
    assert.equal((res as Response).status, 400, "guess " + i);
    await bodyOf(res as Response, "verify wrong " + i);
  }
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code } }), r.env, r.deps);
  assert.equal((res as Response).status, 400, "the ceiling let the right code through");
  await bodyOf(res as Response, "verify correct past ceiling");
  assert.equal((res as Response).headers.get("set-cookie"), null);
  const row = r.db.rows<{ attempts: number }>(`SELECT attempts FROM connect_codes`)[0];
  assert.equal(Number((row as { attempts: number }).attempts), MAX_ATTEMPTS);
});

await check("CONTROL: four wrong guesses then the right one still gets through", async () => {
  const r = await rig();
  const code = await askForCode(r);
  assert.ok(code);
  for (let i = 0; i < MAX_ATTEMPTS - 1; i++) {
    const wrong = String((Number(code) + i + 1) % 1000000).padStart(6, "0");
    await bodyOf((await connectAuthRoute(
      postReq(`/c/${r.token}/verify`, { form: { code: wrong } }), r.env, r.deps)) as Response,
      "verify wrong (control) " + i);
  }
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code } }), r.env, r.deps);
  assert.equal((res as Response).status, 303, "a typo cost the person their code");
  assert.ok((res as Response).headers.get("set-cookie"));
});

await check("an empty box and a junk body are wrong codes, not 500s", async () => {
  const r = await rig();
  assert.ok(await askForCode(r));
  for (const req of [
    postReq(`/c/${r.token}/verify`, { form: {} }),
    postReq(`/c/${r.token}/verify`, { form: { code: "" } }),
    new Request(`https://api.anticipy.ai/c/${r.token}/verify`, {
      method: "POST", headers: { Origin: "https://api.anticipy.ai", "content-type": "application/json" },
      body: "{not json",
    }),
  ]) {
    const res = await connectAuthRoute(req, r.env, r.deps);
    assert.equal((res as Response).status, 400);
    await bodyOf(res as Response, "verify junk");
  }
});

await check("a code is single use: the same right code twice opens once", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const first = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  assert.equal((first as Response).status, 303);
  const second = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  assert.equal((second as Response).status, 400);
  await bodyOf(second as Response, "verify replayed code");
  assert.equal((second as Response).headers.get("set-cookie"), null);
});

// ===========================================================================
// EXPIRY, AT THE BOUNDARY
// ===========================================================================

await check("a code dies AT its instant, not after it", async () => {
  const r = await rig();
  const code = await askForCode(r);
  r.clock.now = NOW + CODE_TTL_MS - 1;
  const alive = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  assert.equal((alive as Response).status, 303, "the code died a millisecond early");

  const r2 = await rig();
  const code2 = await askForCode(r2);
  r2.clock.now = NOW + CODE_TTL_MS;
  const dead = await connectAuthRoute(
    postReq(`/c/${r2.token}/verify`, { form: { code: code2 as string } }), r2.env, r2.deps);
  assert.equal((dead as Response).status, 400, "the code outlived its ten minutes");
  await bodyOf(dead as Response, "verify expired code");
  assert.equal((dead as Response).headers.get("set-cookie"), null);
  // And it did NOT spend a guess: an expired code is refused before the ceiling.
  const row = r2.db.rows<{ attempts: number }>(`SELECT attempts FROM connect_codes`)[0];
  assert.equal(Number((row as { attempts: number }).attempts), 0);
});

await check("a link dies AT its instant: no code at expires_at, a code one ms before", async () => {
  // The mirror of connect.ts's own `ttlDeadline` rule. `>` here would leave a
  // one-millisecond window in which a dead link can still text somebody, which
  // no reader would expect and no other check would cover.
  SENT.length = 0;
  assert.equal(await askForCode(await rig({ expiresAt: NOW })), null,
    "a link texted a code at the instant it expired");
  assert.ok(await askForCode(await rig({ expiresAt: NOW + 1 })),
    "a link went dead a millisecond early");
});

await check("a link bound to a NAME instead of an owner row id texts nobody", async () => {
  // The one failure this whole feature is shaped around, arriving from the
  // store rather than from a request: `user_id` must be the 15-character owner
  // ROW id. The row below has a real owners record and a real phone, so
  // nothing downstream would stop it — only the shape check does.
  SENT.length = 0;
  const r = await rig();
  r.db.db.prepare(
    `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,?,'')`,
  ).run("omar", PB_NOW, PB_NOW, "omar@anticipy-test.invalid", "key-omar", PHONE);
  const named = newToken();
  r.links.put({
    token_handle: await tokenHandle(named), user_id: "omar" as never, toolkit: "zellibrix",
    alias: null, expires_at: NOW + LINK_TTL_MS, used_at: null, completed_at: null,
  });
  const res = await connectAuthRoute(postReq(`/c/${named}/code`), r.env, r.deps);
  assert.equal((res as Response).status, 200);
  await bodyOf(res as Response, "POST /code for a link bound to a name");
  assert.equal(SENT.length, 0, "a connect code was texted for a link bound to \"omar\"");
});

await check("a LOST charge race refuses the right code — the ceiling is believed", async () => {
  // Sequential guesses are stopped by the attempts the row already carries; the
  // compare-and-set's ANSWER only matters when two guesses race, and a route
  // that ignored it would hand an attacker unlimited guesses for the price of
  // one increment. Injected rather than raced, so the check is deterministic.
  const r = await rig();
  const code = await askForCode(r);
  const deps: ConnectAuthDeps = { ...r.deps, codes: { ...r.deps.codes, charge: async () => false } };
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, deps);
  assert.equal((res as Response).status, 400, "a guess that lost the charge was still evaluated");
  await bodyOf(res as Response, "verify with a lost charge");
  assert.equal((res as Response).headers.get("set-cookie"), null);
});

await check("a LOST spend race mints no session — single use is believed", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const deps: ConnectAuthDeps = { ...r.deps, codes: { ...r.deps.codes, spend: async () => false } };
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, deps);
  assert.equal((res as Response).status, 400, "two browsers racing one code both got a session");
  await bodyOf(res as Response, "verify with a lost spend");
  assert.equal((res as Response).headers.get("set-cookie"), null);
});

await check("a code row naming a different owner than its link opens nothing", async () => {
  // A store that assembles a row from a join can get the key right and the
  // payload wrong. This is the field that decides whose account a session
  // names, so the two halves are compared rather than assumed.
  const r = await rig();
  const code = await askForCode(r);
  const codes = {
    ...r.deps.codes,
    newest: async (h: string) => {
      const row = await r.deps.codes.newest(h);
      return row ? { ...row, user_id: STRANGER as never } : null;
    },
  };
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env,
    { ...r.deps, codes });
  assert.equal((res as Response).status, 400, "a session was minted for the wrong owner");
  await bodyOf(res as Response, "verify with a mismatched code row");
  assert.equal((res as Response).headers.get("set-cookie"), null);
});

await check("the session dies AT its stamped instant, not after it", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  const cookie = cookiePair((res as Response).headers.get("set-cookie"));
  const until = NOW + LINK_TTL_MS + CODE_SESSION_GRACE_MS;
  const req = getReq(`/c/${r.token}`, { Cookie: cookie });
  assert.equal(await connectSession(req, r.env, until - 1), OWNER);
  assert.equal(await connectSession(req, r.env, until), null);
  assert.equal(await connectSession(req, r.env, until + 60_000), null);
});

await check("CODE_SESSION_GRACE_MS is connect.ts's own callback window", () => {
  // Written out rather than imported to keep an import cycle out of module
  // init; this is the check that catches the drift that would cause.
  assert.equal(CODE_SESSION_GRACE_MS, CALLBACK_WINDOW_MS);
});

await check("the cookie's Max-Age matches the instant it was stamped with", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  const raw = String((res as Response).headers.get("set-cookie"));
  const m = /Max-Age=(\d+)/.exec(raw);
  assert.ok(m);
  assert.equal(Number(m?.[1]), Math.floor((LINK_TTL_MS + CODE_SESSION_GRACE_MS) / 1000));
});

// ===========================================================================
// ONE LINK, AND ONLY ONE
// ===========================================================================

await check("a code for link A does not open link B", async () => {
  const r = await rig();
  const b = await r.another({ toolkit: "quandle_mail" });
  const codeA = await askForCode(r);
  assert.ok(codeA);
  const res = await connectAuthRoute(
    postReq(`/c/${b.token}/verify`, { form: { code: codeA as string } }), r.env, r.deps);
  assert.equal((res as Response).status, 400);
  await bodyOf(res as Response, "verify A's code at B");
  assert.equal((res as Response).headers.get("set-cookie"), null);
  // And A's code is untouched — B's attempt did not spend it.
  const ok = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: codeA as string } }), r.env, r.deps);
  assert.equal((ok as Response).status, 303);
});

await check("a cookie for link A does not answer for link B", async () => {
  const r = await rig();
  const b = await r.another();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  const cookie = cookiePair((res as Response).headers.get("set-cookie"));
  assert.equal(await connectSession(getReq(`/c/${r.token}`, { Cookie: cookie }), r.env, NOW), OWNER);
  assert.equal(await connectSession(getReq(`/c/${b.token}`, { Cookie: cookie }), r.env, NOW), null);
  // Even renamed onto B's cookie slot, the signature covers B's handle and fails.
  const renamed = SESSION_COOKIE_PREFIX + b.handle.slice(0, 16) + "=" + cookie.split("=").slice(1).join("=");
  assert.equal(await connectSession(getReq(`/c/${b.token}`, { Cookie: renamed }), r.env, NOW), null);
});

await check("two links in one browser keep two sessions — neither logs the other out",
  async () => {
    // A person connecting a second app must not be signed out of the first.
    // The cookie NAME carries the link's handle prefix for exactly this, and
    // one shared name would make the browser keep only the newer value.
    const r = await rig();
    const b = await r.another({ toolkit: "quandle_mail" });
    const codeA = await askForCode(r);
    r.clock.now = NOW + MIN_GAP_MS;
    const codeB = await askForCode(r, b.token);
    assert.ok(codeA && codeB);
    const setA = cookiePair((await connectAuthRoute(
      postReq(`/c/${r.token}/verify`, { form: { code: codeA as string } }),
      r.env, r.deps) as Response).headers.get("set-cookie"));
    const setB = cookiePair((await connectAuthRoute(
      postReq(`/c/${b.token}/verify`, { form: { code: codeB as string } }),
      r.env, r.deps) as Response).headers.get("set-cookie"));
    assert.notEqual(setA.split("=")[0], setB.split("=")[0],
      "both links were given the same cookie name");
    const jar = `${setA}; ${setB}`;
    assert.equal(await connectSession(getReq(`/c/${r.token}`, { Cookie: jar }), r.env, NOW), OWNER);
    assert.equal(await connectSession(getReq(`/c/${b.token}`, { Cookie: jar }), r.env, NOW), OWNER);
  });

await check("the cookie is Path-scoped to its own link and nothing else", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  const raw = String((res as Response).headers.get("set-cookie"));
  assert.ok(raw.includes(`Path=/c/${r.token};`), raw);
  assert.ok(!/Path=\/;/.test(raw), "the cookie was widened to the whole origin");
  assert.ok(raw.includes("HttpOnly"), raw);
  assert.ok(raw.includes("Secure"), raw);
  assert.ok(raw.includes("SameSite=Lax"), raw);
  assert.ok(!/SameSite=None/i.test(raw), raw);
  assert.ok(raw.startsWith(SESSION_COOKIE_PREFIX), raw);
});

// ===========================================================================
// THE SESSION IS NOT A LOGIN
// ===========================================================================

await check("the code session is refused by the account-token verifier", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  const value = cookiePair((res as Response).headers.get("set-cookie")).split("=").slice(1).join("=");
  assert.equal(await verifyToken(r.env as never, value), null,
    "a texted code minted something the data API would accept");
  // And presented in the account-session cookie slot it is still nothing.
  const asAccount = getReq(`/c/${r.token}`, { Cookie: `${SESSION_COOKIE}=${value}` });
  assert.equal(await connectSession(asAccount, r.env, NOW), null);
});

await check("no ANTICIPY_AUTH_SECRET, no code session — it fails closed", async () => {
  const r = await rig({ secret: "" });
  const code = await askForCode(r);
  assert.ok(code, "the send path should still work; only the session is refused");
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  assert.equal((res as Response).status, 400);
  await bodyOf(res as Response, "verify with no secret");
  assert.equal((res as Response).headers.get("set-cookie"), null);
});

await check("a tampered cookie is nothing at all", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  const pair = cookiePair((res as Response).headers.get("set-cookie"));
  const [name, ...rest] = pair.split("=");
  const value = rest.join("=");
  const parts = value.split(".");
  const forged = [
    `${name}=1.${STRANGER}.${parts[2]}.${parts[3]}`,           // another owner
    `${name}=1.${OWNER}.${Number(parts[2]) + 3600_000}.${parts[3]}`, // a longer life
    `${name}=2.${OWNER}.${parts[2]}.${parts[3]}`,               // another version
    `${name}=${value.slice(0, -2)}xx`,                          // a bent signature
    `${name}=${OWNER}`,                                         // not even the shape
  ];
  for (const c of forged) {
    assert.equal(await connectSession(getReq(`/c/${r.token}`, { Cookie: c }), r.env, NOW), null, c);
  }
  // CONTROL: untouched, it still works.
  assert.equal(await connectSession(getReq(`/c/${r.token}`, { Cookie: pair }), r.env, NOW), OWNER);
});

await check("a signed-in account token wins over a code cookie, even a stranger's", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  const cookie = cookiePair((res as Response).headers.get("set-cookie"));
  const req = getReq(`/c/${r.token}`, { Cookie: cookie, Authorization: r.strangerToken });
  assert.equal(await connectSession(req, r.env, NOW), STRANGER,
    "a stale code cookie quietly promoted a signed-in stranger into somebody else's link");
});

await check("a cookie whose name matches only as a substring is not ours", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  const pair = cookiePair((res as Response).headers.get("set-cookie"));
  const evil = "evil" + pair;
  assert.equal(await connectSession(getReq(`/c/${r.token}`, { Cookie: evil }), r.env, NOW), null);
  // CONTROL: ours alongside a decoy still reads.
  assert.equal(
    await connectSession(getReq(`/c/${r.token}`, { Cookie: `${evil}; ${pair}` }), r.env, NOW), OWNER);
});

// ===========================================================================
// AFTER THE TAP
// ===========================================================================

await check("a spent link mints no new session: no code, and no session from an old one",
  async () => {
    SENT.length = 0;
    const r = await rig();
    const code = await askForCode(r);
    assert.ok(code);
    // The owner taps Connect. connect.ts's compare-and-set spends the link.
    const claim = await r.links.claim(r.handle, NOW + 1000);
    assert.equal(claim.won, true);
    r.clock.now = NOW + 2000;

    // 1. Asking again texts NOTHING, and says the same thing it always says.
    const before = SENT.length;
    const res = await connectAuthRoute(postReq(`/c/${r.token}/code`), r.env, r.deps);
    assert.equal((res as Response).status, 200);
    await bodyOf(res as Response, "POST /code on a spent link");
    assert.equal(SENT.length, before, "a spent link still texted somebody");

    // 2. A code that was minted before the tap and never used opens nothing now.
    const check2 = await connectAuthRoute(
      postReq(`/c/${r.token}/verify`, { form: { code } }), r.env, r.deps);
    assert.equal((check2 as Response).status, 400,
      "a stolen link, tapped and spent, still minted a session");
    await bodyOf(check2 as Response, "verify on a spent link");
    assert.equal((check2 as Response).headers.get("set-cookie"), null);
  });

await check("CONTROL: a session minted BEFORE the tap survives it, so /done can finish",
  async () => {
    const r = await rig();
    const code = await askForCode(r);
    const res = await connectAuthRoute(
      postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
    const cookie = cookiePair((res as Response).headers.get("set-cookie"));
    await r.links.claim(r.handle, NOW + 1000);
    // The vendor round trip took twenty minutes — longer than the link's own
    // ten. If this reads null, the connection exists at the vendor and there is
    // no webhook that will ever mention it again.
    const later = NOW + 20 * 60 * 1000;
    assert.equal(
      await connectSession(getReq(`/c/${r.token}/done`, { Cookie: cookie }), r.env, later), OWNER);
  });

// ===========================================================================
// THE CONTROL THAT MATTERS: the page goes through
// ===========================================================================

await check("CONTROL: a correct code lets the connect page draw", async () => {
  const r = await rig();
  const provider = { toolkit: async (s: string) => APPS[s] as ToolkitMeta };
  const words = { sentences: async (m: ToolkitMeta) => [`Anticipy can read your ${m.name}.`] };

  // Before: the browser has nothing, and connect.ts says so.
  const anonymous = getReq(`/c/${r.token}`);
  const who0 = await connectSession(anonymous, r.env, NOW);
  assert.equal(who0, null);
  const before = await connectPageView(r.token, {
    signedInAs: who0, store: r.links, provider, words, now: NOW,
  });
  assert.equal(before.state, "sign-in-required");

  // The one tap.
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps);
  assert.equal((res as Response).status, 303);
  assert.equal((res as Response).headers.get("location"), `/c/${r.token}`);
  const cookie = cookiePair((res as Response).headers.get("set-cookie"));

  // After: the same page, the same store, the same everything — it draws.
  const who = await connectSession(getReq(`/c/${r.token}`, { Cookie: cookie }), r.env, NOW);
  assert.equal(who, OWNER);
  const after = await connectPageView(r.token, {
    signedInAs: who, store: r.links, provider, words, now: NOW,
  });
  assert.equal(after.state, "ok");
  assert.equal((after as { toolkit: ToolkitMeta }).toolkit.name, "Zellibrix");
});

// ===========================================================================
// THE STATE, END TO END
// ===========================================================================

await check("the send carries the state on to the code box and to \"ask for another\"", async () => {
  const r = await rig();
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/code`, { form: { state: "ATTEMPT-1234" } }), r.env, r.deps);
  const html = await bodyOf(res as Response, "POST /code with state");
  assert.equal(occurrences(html, '<input type="hidden" name="state" value="ATTEMPT-1234">'), 1,
    "the box the person types into forgot which attempt they are finishing");
  assert.equal(occurrences(html, `href="/c/${r.token}/code?state=ATTEMPT-1234"`), 1,
    "asking for a second code starts an attempt the phone will not recognise");
});

await check("THE STATE SURVIVES THE CODE: a correct code lands back on the page holding it",
  async () => {
    const r = await rig();
    const code = await askForCode(r);
    const res = await connectAuthRoute(
      postReq(`/c/${r.token}/verify`, { form: { code: code as string, state: "ATTEMPT-1234" } }),
      r.env, r.deps) as Response;
    assert.equal(res.status, 303);
    assert.equal(res.headers.get("location"), `/c/${r.token}?state=ATTEMPT-1234`,
      "the sign-in dropped ?state=, so the attempt id is gone and ConnectHandoff.parseDone "
      + "refuses the deep link home — the person finishes the connect and the app never hears");
  });

await check("CONTROL: a code with no state lands back on a page with no state", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string } }), r.env, r.deps) as Response;
  assert.equal(res.status, 303);
  assert.equal(res.headers.get("location"), `/c/${r.token}`,
    "a state nobody sent was invented; the phone refuses one it did not mint");
});

await check("a state that is not the phone's shape is dropped, not carried", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string, state: "not a state!" } }),
    r.env, r.deps) as Response;
  assert.equal(res.status, 303);
  assert.equal(res.headers.get("location"), `/c/${r.token}`);
});

await check("the state is carried VERBATIM — encoded for the wire, never re-encoded", async () => {
  const r = await rig();
  const code = await askForCode(r);
  // The phone's own alphabet allows "%" (ConnectHandoff.isOpaqueToken), which
  // is the character a second round of encoding changes: "%2F" becomes "%252F"
  // and what comes back to the app is not what it sent.
  const state = "A%2FB-1234";
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: code as string, state } }),
    r.env, r.deps) as Response;
  const back = new URL(String(res.headers.get("location")), "https://api.anticipy.ai")
    .searchParams.get("state");
  assert.equal(back, state, "what the browser asks for next is not the state the phone minted");
});

await check("a wrong code comes back to a box that still holds the state", async () => {
  const r = await rig();
  const code = await askForCode(r);
  const wrong = code === "000000" ? "111111" : "000000";
  const res = await connectAuthRoute(
    postReq(`/c/${r.token}/verify`, { form: { code: wrong, state: "ATTEMPT-1234" } }),
    r.env, r.deps) as Response;
  assert.equal(res.status, 400);
  assert.equal(occurrences(await bodyOf(res, "verify wrong, state kept"),
    '<input type="hidden" name="state" value="ATTEMPT-1234">'), 1,
    "one typo cost the person the attempt their phone is waiting on");
});

// ===========================================================================
// THE STORE ITSELF
// ===========================================================================

await check("connectCodesTableReady tells the truth both ways", async () => {
  const withIt = new FakeD1();
  withIt.db.exec(CONNECT_CODES_DDL);
  assert.equal(await connectCodesTableReady({ DB: asD1(withIt) }), true);
  // DROPPED, not "absent from schema.sql". It used to be the second: the table
  // lived only in CONNECT_CODES_DDL, so a bare FakeD1 was already without it.
  // It is in schema.sql now (that is where schemas belong), so the state this
  // leg exists to cover — a LIVE database that has not had the migration
  // applied — has to be built on purpose. Removing the table rather than
  // reaching for a doctored schema keeps the two databases identical in every
  // other respect, which is what makes the comparison mean anything.
  const without = new FakeD1();
  without.db.exec('DROP TABLE IF EXISTS "connect_codes";');
  assert.equal(await connectCodesTableReady({ DB: asD1(without) }), false);
});

await check("a missing connect_codes table is a dead feature, not a 500 and not a tell",
  async () => {
    SENT.length = 0;
    const db = new FakeD1();
    // The un-migrated live database, built by dropping what schema.sql now
    // creates. See the note in the leg above.
    db.db.exec('DROP TABLE IF EXISTS "connect_codes";');
    for (const [id, key] of [[OWNER, "key-owner"]] as [string, string][]) {
      db.db.prepare(
        `INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
           password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,?,'')`,
      ).run(id, PB_NOW, PB_NOW, `${id}@x.invalid`, key, PHONE);
    }
    const env = {
      DB: asD1(db), ANTICIPY_AUTH_SECRET: SECRET,
      SENDBLUE_API_KEY_ID: "sb-id", SENDBLUE_API_SECRET_KEY: "sb-secret",
      SENDBLUE_FROM_NUMBER: "+15550001111", SENDBLUE_API_BASE: "http://127.0.0.1:9797",
    } as unknown as ConnectAuthEnv;
    const links = new MemoryLinkStore();
    const token = newToken();
    links.put({
      token_handle: await tokenHandle(token), user_id: OWNER, toolkit: "zellibrix",
      alias: null, expires_at: NOW + LINK_TTL_MS, used_at: null, completed_at: null,
    });
    const deps: ConnectAuthDeps = {
      links, codes: createD1ConnectCodeStore({ DB: asD1(db) }),
      toolkitName: async () => "Zellibrix", now: () => NOW,
    };
    const res = await connectAuthRoute(postReq(`/c/${token}/code`), env, deps);
    assert.equal((res as Response).status, 200, "a missing table 500ed the page");
    await bodyOf(res as Response, "POST /code with no table");
    assert.equal(await connectCodesTableReady({ DB: asD1(db) }), false);
  });

await check("charge is a compare-and-set: a concurrent pair increments once", async () => {
  const codes = createMemoryConnectCodeStore();
  await codes.insert({
    id: "c1", token_handle: "h".repeat(64), user_id: OWNER as never,
    code_hash: "a".repeat(64), expires_at: NOW + CODE_TTL_MS, attempts: 0,
    used_at: null, created_at: NOW,
  });
  const [a, b] = await Promise.all([codes.charge("c1", 0, 1), codes.charge("c1", 0, 1)]);
  assert.equal([a, b].filter(Boolean).length, 1, "both guesses won the same charge");
  assert.equal((codes.rows.get("c1") as { attempts: number }).attempts, 1);
});

await check("spend is a compare-and-set: one of two concurrent winners", async () => {
  const codes = createMemoryConnectCodeStore();
  await codes.insert({
    id: "c1", token_handle: "h".repeat(64), user_id: OWNER as never,
    code_hash: "a".repeat(64), expires_at: NOW + CODE_TTL_MS, attempts: 0,
    used_at: null, created_at: NOW,
  });
  const [a, b] = await Promise.all([codes.spend("c1", NOW), codes.spend("c1", NOW)]);
  assert.equal([a, b].filter(Boolean).length, 1);
});

await check("the D1 store and the memory store answer the same questions", async () => {
  const db = new FakeD1();
  db.db.exec(CONNECT_CODES_DDL);
  const stores = [createD1ConnectCodeStore({ DB: asD1(db) }), createMemoryConnectCodeStore()];
  const handle = "b".repeat(64);
  for (const s of stores) {
    assert.equal(await s.newest(handle), null);
    assert.deepEqual(await s.window(handle, OWNER as never, NOW - OWNER_HOUR),
      { forLink: 0, forOwner: 0, newestForLink: null });
    await s.insert({
      id: "c1", token_handle: handle, user_id: OWNER as never, code_hash: "a".repeat(64),
      expires_at: NOW + CODE_TTL_MS, attempts: 0, used_at: null, created_at: NOW,
    });
    await s.insert({
      id: "c2", token_handle: handle, user_id: OWNER as never, code_hash: "d".repeat(64),
      expires_at: NOW + CODE_TTL_MS, attempts: 0, used_at: null, created_at: NOW + 1000,
    });
    const newest = await s.newest(handle);
    assert.equal(newest?.id, "c2", "the older code is still live");
    assert.deepEqual(await s.window(handle, OWNER as never, NOW - OWNER_HOUR),
      { forLink: 2, forOwner: 2, newestForLink: NOW + 1000 });
    assert.equal(await s.charge("c2", 0, 1), true);
    assert.equal(await s.charge("c2", 0, 1), false);
    assert.equal(await s.spend("c2", NOW + 2000), true);
    assert.equal(await s.spend("c2", NOW + 2000), false);
    assert.equal(await s.newest(handle), null);
  }
});

// ===========================================================================
// THE WHOLE-SUITE SCANS
// ===========================================================================

/** What the PERSON reads: tags and attributes stripped, so a form action of
 *  `/c/{token}/verify` is not mistaken for a word anybody was shown. */
const visible = (html: string): string =>
  html.replace(/<style[\s\S]*?<\/style>/gi, " ").replace(/<[^>]*>/g, " ");

await check("no page and no text ever says Composio, or any of the jargon", () => {
  const banned: [string, RegExp][] = [
    ["composio", /composio/i],
    ["authorize", /\bauthoris|\bauthoriz/i],
    ["grant access", /grant\s+access/i],
    ["permission", /\bpermission/i],
    ["integration", /\bintegration/i],
    ["oauth", /\boauth\b/i],
    ["api", /\bapi\b/i],
    ["verify", /\bverif/i],
    ["credential", /\bcredential/i],
    ["token", /\btoken\b/i],
  ];
  assert.ok(BODIES.length > 20, "the scan ran on " + BODIES.length + " bodies — too few to mean much");
  assert.ok(TEXTS.length > 5, "the scan ran on " + TEXTS.length + " texts — too few to mean much");
  for (const { where, text } of BODIES) {
    const shown = visible(text);
    for (const [name, re] of banned) {
      assert.ok(!re.test(shown), `${where} showed the word "${name}": ${shown.slice(0, 200)}`);
    }
  }
  for (const { where, text } of TEXTS) {
    for (const [name, re] of banned) {
      assert.ok(!re.test(text), `${where} said "${name}": ${text}`);
    }
  }
});

await check("no page ever carries a code, a token or a session value", () => {
  for (const { where, text } of BODIES) {
    for (const t of TEXTS) {
      const code = /\b(\d{6})\b/.exec(t.text)?.[1];
      if (code) assert.ok(!text.includes(code), `${where} rendered a texted code`);
    }
    assert.ok(!text.includes(SESSION_COOKIE_PREFIX),
      `${where} rendered the session cookie's name into the page`);
  }
});

await check("no source file in this feature names an app", async () => {
  const { readFileSync } = await import("node:fs");
  const { fileURLToPath } = await import("node:url");
  const { dirname, join } = await import("node:path");
  const here = dirname(fileURLToPath(import.meta.url));
  const src = readFileSync(join(here, "..", "src", "routes", "connect_auth.ts"), "utf8");
  for (const app of ["Notion", "Gmail", "Slack", "googlecalendar", "Zellibrix"]) {
    // "Notion" appears once, in the copy example on connectCodeText's own test
    // in the header — not in this file. Nothing here may name a real app.
    const hits = src.split(app).length - 1;
    assert.ok(hits === 0, `connect_auth.ts names ${app} ${hits} time(s)`);
  }
});

globalThis.fetch = realFetch;

console.log(`\nconnect-auth: ${passes} passed, ${failures} failed`);
if (failures > 0) process.exit(1);
