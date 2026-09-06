/**
 * test/connections-webhook.test.ts — POST /connections/events, driven as HTTP.
 *
 *   node --experimental-strip-types migration/workers/test/connections-webhook.test.ts
 *
 * WHAT IS REAL HERE AND WHAT IS NOT. The handler, the signature check, the
 * status codes, the event reader and the two writes are the shipped code. So is
 * the WIRING — every check below runs through `webhookDeps(env)`, the same
 * function src/index.ts reaches through, because the failure this repo actually
 * ships is a tested part nothing calls (`installConnectWiring` had zero callers
 * for a day and every /c/ leg answered 503). So is the STORE: `createD1Store`
 * over a real SQLite loaded verbatim from migration/d1/schema.sql, so the CHECK
 * constraints, the primary keys and the cross-owner predicate on the upsert are
 * the real ones. Only the clock is injected.
 *
 * THE SIGNATURE IS COMPUTED TWICE, BY TWO DIFFERENT IMPLEMENTATIONS. The route
 * signs with WebCrypto; this file signs with `node:crypto` createHmac. A test
 * that verified the route against the route's own HMAC would pass for a route
 * that signed with the empty string.
 *
 * THE FAILURES THIS FILE EXISTS TO CATCH:
 *
 *   THE FORGED EXPIRY. An unauthenticated POST that marks a connection expired
 *   strips the API hand off a working account and texts its owner about a
 *   problem that does not exist. Every refusal below is measured against the
 *   DATABASE (the row is unchanged) and against the BINDING (`db.log` is empty
 *   — the store was never even asked), not against a status code alone.
 *
 *   THE WRONG PERSON. An event naming somebody else's account must not move a
 *   row, and must not be swallowed as a 200 either: our owner-binding
 *   disagreeing with the vendor's is the exact failure this feature was built
 *   around (one operator's mailbox serving everybody).
 *
 *   THE RETRY STORM. An account we do not hold is a 200 and a no-op. A vendor
 *   retries an error forever, and a connection somebody already disconnected is
 *   not a problem.
 *
 *   THE ERASED HISTORY. The flip writes ONE field. `level`, `snooze_until`,
 *   `sent_at`, `trigger`, `acted_at`, `channel` and `writes_enabled` are read
 *   back and compared field by field, because a webhook that reset them would
 *   turn every vendor retry into a fresh licence to text somebody, and would
 *   silently revoke the "let Anticipy make changes" opt-in.
 *
 *   THE SUITE NOBODY RUNS. This file asserts its own presence in
 *   package.json's `test` script and the route's own registration in
 *   src/index.ts. Three suites were written and left out of CI on 2026-09-06;
 *   each time hundreds of checks silently did not run.
 *
 * THE MUTATION REPORT is at the bottom: every mutation, the literal it was
 * anchored on (each occurring EXACTLY ONCE in the source), and the check that
 * killed it.
 */
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { FakeD1, asD1 } from "./fake-d1.ts";
import {
  createD1Store, forgetLiveColumns,
  type StoredConnection, type StoredNudge,
} from "../src/connections/store.ts";
import { FORBIDDEN_TERMS, TRIGGER_SCORE } from "../src/connections/words.ts";
import {
  connectionsWebhook,
  webhookDeps,
  checkSignature,
  offeredSignatures,
  readEvent,
  isExpiredEvent,
  signedPayload,
  signPayload,
  webhookKeyBytes,
  CONNECTIONS_WEBHOOK_PATH,
  EXPIRED_EVENT_TYPES,
  SIGNATURE_TOLERANCE_MS,
  MAX_BODY_BYTES,
  type ConnectionsWebhookDeps,
  type ConnectionsWebhookEnv,
} from "../src/routes/connections_webhook.ts";

const here = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(here, "..", "src", "routes", "connections_webhook.ts"), "utf8");
const INDEX_SOURCE = readFileSync(join(here, "..", "src", "index.ts"), "utf8");
const PACKAGE_JSON = readFileSync(join(here, "..", "package.json"), "utf8");

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

// ---------------------------------------------------------------------------
// FIXTURES
// ---------------------------------------------------------------------------

const NOW = 1_757_000_000_000;            // a fixed instant; every check owns time
const TS = String(Math.floor(NOW / 1000));
const SECRET = "webhook-secret-2f8a1c";
const WEBHOOK_ID = "msg_2f8a1c";

const OWNER = "ownerwebhook001";          // 15 lowercase alphanumerics, as D1 mints
const OTHER = "ownerwebhook002";

/** Two apps nobody has ever heard of. NOTHING in the Worker knows these names —
 *  the whole flow runs on them, and a check at the bottom asserts the route's
 *  source names no real app either. */
const APP = "zellibrix";
const APP_2 = "quandle_mail";

const OWNER_ACCOUNT = "ca_OWNER_zellibrix";
const OWNER_ACCOUNT_2 = "ca_OWNER_quandle";
const OTHER_ACCOUNT = "ca_OTHER_zellibrix";
const UNKNOWN_ACCOUNT = "ca_NOBODY_HOLDS_THIS";

const URL = `https://api.anticipy.ai${CONNECTIONS_WEBHOOK_PATH}`;

/** The clause that keeps a marked expiry from reading as a finished surface.
 *  One literal, one occurrence in the route — a phrase that appears twice is a
 *  second answer, and a phrase that appears zero times is a check that passes
 *  because its regex quietly stopped matching. */
const UNTOLD = "NOBODY HAS BEEN TOLD";

const conn = (over: Partial<StoredConnection> = {}): StoredConnection => ({
  user_id: OWNER as never, toolkit: APP, connected_account_id: OWNER_ACCOUNT,
  alias: null, status: "connected", writes_enabled: false, last_used_at: null,
  ...over,
});

const nudgeRow = (over: Partial<StoredNudge> = {}): StoredNudge => ({
  user_id: OWNER as never, toolkit: APP, state: "connected", level: 0,
  snooze_until: null, trigger: null, sent_at: null, acted_at: null, channel: null,
  ...over,
});

interface Rig {
  db: FakeD1;
  env: ConnectionsWebhookEnv;
  deps: ConnectionsWebhookDeps;
}

interface RigOpts {
  secret?: string;
  connections?: StoredConnection[];
  nudges?: StoredNudge[];
}

async function rig(opts: RigOpts = {}): Promise<Rig> {
  const db = new FakeD1();
  const env = {
    DB: asD1(db),
    COMPOSIO_WEBHOOK_SECRET: opts.secret === undefined ? SECRET : opts.secret,
  } as unknown as ConnectionsWebhookEnv;
  forgetLiveColumns(env as never);

  // Seeded through the REAL store, so every row obeys the real schema.
  const store = createD1Store(env as never);
  const seed = opts.connections ?? [
    conn(),
    conn({ toolkit: APP_2, connected_account_id: OWNER_ACCOUNT_2, alias: "work" }),
    conn({ user_id: OTHER as never, connected_account_id: OTHER_ACCOUNT }),
  ];
  for (const row of seed) await store.putConnection(row);
  for (const row of opts.nudges ?? []) await store.putNudge(row);

  // THE REAL WIRING, with only the clock injected. A rig that built its own
  // store would test a store src/index.ts never reaches.
  const wired = webhookDeps(env);
  assert.ok(wired, "webhookDeps must build deps from a Worker env with a DB binding");
  const deps: ConnectionsWebhookDeps = { store: wired.store, now: () => NOW };

  // Everything the seeding did is behind us: from here, an empty log means the
  // handler never touched the database.
  db.log.length = 0;
  return { db, env, deps };
}

// ---------------------------------------------------------------------------
// THE SIGNATURE, computed independently of the code under test
// ---------------------------------------------------------------------------

/** The Standard Webhooks key derivation, written a second time on purpose. */
function keyBytes(secret: string): Buffer {
  const trimmed = secret.trim();
  if (trimmed.startsWith("whsec_")) {
    const raw = Buffer.from(trimmed.slice("whsec_".length), "base64");
    if (raw.byteLength > 0) return raw;
  }
  return Buffer.from(trimmed, "utf8");
}

function sign(secret: string, id: string, ts: string, body: string): string {
  return createHmac("sha256", keyBytes(secret)).update(`${id}.${ts}.${body}`).digest("base64");
}

interface PostOpts {
  body?: string;
  secret?: string;          // what the CALLER signs with
  id?: string;              // what the caller SENDS as webhook-id
  signedId?: string;        // what the caller SIGNED with, if different
  ts?: string;              // what the caller SENDS as webhook-timestamp
  signedTs?: string;
  signedBody?: string;      // the body the signature was computed over
  signature?: string;       // a whole header, verbatim
  headerPrefix?: string;    // "webhook" (default) or "svix"
  omit?: ("id" | "timestamp" | "signature")[];
  method?: string;
  contentLength?: boolean;  // false = stream the body, so no content-length
}

async function post(r: Rig, opts: PostOpts = {}): Promise<Response> {
  const body = opts.body ?? expired();
  const id = opts.id ?? WEBHOOK_ID;
  const ts = opts.ts ?? TS;
  const prefix = opts.headerPrefix ?? "webhook";
  const omit = new Set(opts.omit ?? []);
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (!omit.has("id")) headers[`${prefix}-id`] = id;
  if (!omit.has("timestamp")) headers[`${prefix}-timestamp`] = ts;
  if (!omit.has("signature")) {
    headers[`${prefix}-signature`] = opts.signature ?? "v1," + sign(
      opts.secret ?? SECRET,
      opts.signedId ?? id,
      opts.signedTs ?? ts,
      opts.signedBody ?? body,
    );
  }
  const init: RequestInit & { duplex?: string } = {
    method: opts.method ?? "POST", headers, body,
  };
  if (opts.contentLength === false) {
    init.body = new ReadableStream({
      start(c) { c.enqueue(new TextEncoder().encode(body)); c.close(); },
    }) as unknown as BodyInit;
    init.duplex = "half";
  }
  if (init.method === "GET" || init.method === "HEAD") delete (init as { body?: unknown }).body;
  return connectionsWebhook(new Request(URL, init as RequestInit), r.env, r.deps);
}

/** The vendor's documented envelope. `metadata` carries the ids. */
function expired(over: Record<string, unknown> = {}): string {
  return JSON.stringify({
    id: "evt_9c1",
    type: EXPIRED_EVENT_TYPES[0],
    metadata: {
      connected_account_id: OWNER_ACCOUNT,
      user_id: OWNER,
      auth_config_id: "ac_x1",
    },
    timestamp: "2026-09-06T12:00:00Z",
    ...over,
  });
}

// ---------------------------------------------------------------------------
// READBACK HELPERS — straight to SQLite, never through the code under test
// ---------------------------------------------------------------------------

const statusOf = (r: Rig, account: string): string | null => {
  const rows = r.db.rows<{ status: string }>(
    `SELECT status FROM connections WHERE connected_account_id = ?`, account,
  );
  return rows.length ? rows[0].status : null;
};
const nudgesOf = (r: Rig): Record<string, unknown>[] =>
  r.db.rows(`SELECT * FROM connect_nudges ORDER BY user_id, toolkit`);
const nudgeOf = (r: Rig, owner: string, toolkit: string): Record<string, unknown> | null => {
  const rows = r.db.rows(
    `SELECT * FROM connect_nudges WHERE user_id = ? AND toolkit = ?`, owner, toolkit,
  );
  return rows.length ? rows[0] : null;
};
const connectionCount = (r: Rig): number =>
  r.db.rows<{ n: number }>(`SELECT COUNT(*) AS n FROM connections`)[0].n;

/** Nothing was written AND nothing was read: the handler never reached the
 *  binding at all. The stronger half of "changes nothing". */
function untouched(r: Rig, where: string): void {
  assert.equal(r.db.log.length, 0, `${where}: the store was asked ${r.db.log.length} statement(s)`);
  assert.equal(statusOf(r, OWNER_ACCOUNT), "connected", `${where}: the connection moved`);
  assert.equal(nudgesOf(r).length, 0, `${where}: a nudge row was written`);
}

// ===========================================================================
// 1. THE SIGNATURE
// ===========================================================================

await check("an unsigned event is refused, and the store is never touched", async () => {
  const r = await rig();
  const res = await post(r, { omit: ["id", "timestamp", "signature"] });
  assert.equal(res.status, 403);
  await bodyOf(res, "unsigned");
  untouched(r, "unsigned");
});

await check("an event signed with the wrong secret is refused and changes nothing", async () => {
  const r = await rig();
  const res = await post(r, { secret: "not-the-secret" });
  assert.equal(res.status, 403);
  await bodyOf(res, "wrong secret");
  untouched(r, "wrong secret");
});

await check("a signature over one body does not sign a different one", async () => {
  const r = await rig();
  // A real, correctly signed event — for a body naming a DIFFERENT account.
  const res = await post(r, {
    body: expired(),
    signedBody: expired({ metadata: { connected_account_id: OTHER_ACCOUNT, user_id: OTHER } }),
  });
  assert.equal(res.status, 403);
  await bodyOf(res, "tampered body");
  untouched(r, "tampered body");
});

await check("the webhook-id is part of what is signed", async () => {
  const r = await rig();
  const res = await post(r, { id: "msg_replayed", signedId: WEBHOOK_ID });
  assert.equal(res.status, 403);
  untouched(r, "id swapped");
});

await check("the webhook-timestamp is part of what is signed", async () => {
  const r = await rig();
  const res = await post(r, { ts: String(Number(TS) - 10), signedTs: TS });
  assert.equal(res.status, 403);
  untouched(r, "timestamp swapped");
});

await check("each of the three headers is required on its own", async () => {
  for (const missing of ["id", "timestamp", "signature"] as const) {
    const r = await rig();
    const res = await post(r, { omit: [missing] });
    assert.equal(res.status, 403, `missing ${missing} was ${res.status}`);
    untouched(r, `missing ${missing}`);
  }
});

await check("a stale timestamp is refused even when the signature is real", async () => {
  const r = await rig();
  const old = String(Math.floor((NOW - SIGNATURE_TOLERANCE_MS - 1000) / 1000));
  const res = await post(r, { ts: old });
  assert.equal(res.status, 403);
  untouched(r, "stale");
});

await check("a timestamp beyond the window in the FUTURE is refused too", async () => {
  const r = await rig();
  const ahead = String(Math.floor((NOW + SIGNATURE_TOLERANCE_MS + 1000) / 1000));
  const res = await post(r, { ts: ahead });
  assert.equal(res.status, 403);
  untouched(r, "future");
});

await check("CONTROL: a timestamp inside the window is accepted", async () => {
  const r = await rig();
  const recent = String(Math.floor((NOW - SIGNATURE_TOLERANCE_MS + 2000) / 1000));
  const res = await post(r, { ts: recent });
  assert.equal(res.status, 200);
  assert.equal(statusOf(r, OWNER_ACCOUNT), "needs_reconnect");
});

await check("a timestamp that is not an integer count of seconds is refused", async () => {
  for (const ts of ["", "   ", "not-a-number", "1757000000.5", "1e9", "0x6a"]) {
    const r = await rig();
    const res = await post(r, { ts });
    assert.equal(res.status, 403, `timestamp ${JSON.stringify(ts)} was ${res.status}`);
    untouched(r, `timestamp ${JSON.stringify(ts)}`);
  }
});

await check("only a v1 signature counts, and an unknown version is not one", async () => {
  const r = await rig();
  const good = sign(SECRET, WEBHOOK_ID, TS, expired());
  const res = await post(r, { signature: `v2,${good}` });
  assert.equal(res.status, 403);
  untouched(r, "v2 only");
});

await check("a bare signature with no version prefix is refused", async () => {
  const r = await rig();
  const good = sign(SECRET, WEBHOOK_ID, TS, expired());
  const res = await post(r, { signature: good });
  assert.equal(res.status, 403);
  untouched(r, "no version");
});

await check("CONTROL: a rotation list is accepted when any entry matches", async () => {
  const r = await rig();
  const good = sign(SECRET, WEBHOOK_ID, TS, expired());
  const stale = sign("the-previous-secret", WEBHOOK_ID, TS, expired());
  const res = await post(r, { signature: `v1,${stale} v1,${good}` });
  assert.equal(res.status, 200);
  assert.equal(statusOf(r, OWNER_ACCOUNT), "needs_reconnect");
});

await check("the svix-* header aliases carry the same signature", async () => {
  const r = await rig();
  const res = await post(r, { headerPrefix: "svix" });
  assert.equal(res.status, 200);
  assert.equal(statusOf(r, OWNER_ACCOUNT), "needs_reconnect");
});

await check("a whsec_ secret keys the HMAC with its DECODED bytes", async () => {
  const raw = Buffer.from("0123456789abcdef0123456789abcdef", "utf8");
  const secret = "whsec_" + raw.toString("base64");

  // Signed with the decoded bytes, as the spec says: accepted.
  const ok = await rig({ secret });
  assert.equal((await post(ok, { secret })).status, 200);
  assert.equal(statusOf(ok, OWNER_ACCOUNT), "needs_reconnect");

  // Signed with the literal `whsec_...` string: not the same key, refused.
  const bad = await rig({ secret });
  const literal = createHmac("sha256", Buffer.from(secret, "utf8"))
    .update(signedPayload(WEBHOOK_ID, TS, expired())).digest("base64");
  const res = await post(bad, { signature: `v1,${literal}` });
  assert.equal(res.status, 403);
  untouched(bad, "whsec literal");
});

await check("the route's own HMAC agrees with node:crypto's", async () => {
  const payload = signedPayload(WEBHOOK_ID, TS, expired());
  assert.equal(await signPayload(SECRET, payload), sign(SECRET, WEBHOOK_ID, TS, expired()));
  assert.equal(
    Buffer.from(webhookKeyBytes(SECRET)).toString("hex"),
    keyBytes(SECRET).toString("hex"),
  );
});

await check("checkSignature is a floor: every non-match answers ok:false", async () => {
  const body = expired();
  const base = {
    secret: SECRET, id: WEBHOOK_ID, timestamp: TS,
    signature: "v1," + sign(SECRET, WEBHOOK_ID, TS, body), body, now: NOW,
  };
  assert.equal((await checkSignature(base)).ok, true);
  assert.equal((await checkSignature({ ...base, id: null })).cause, "missing-id");
  assert.equal((await checkSignature({ ...base, timestamp: null })).cause, "missing-timestamp");
  assert.equal((await checkSignature({ ...base, signature: null })).cause, "missing-signature");
  assert.equal((await checkSignature({ ...base, timestamp: "soon" })).cause, "bad-timestamp");
  assert.equal((await checkSignature({ ...base, now: NOW + 10 * 60_000 })).cause, "stale");
  assert.equal((await checkSignature({ ...base, signature: "v9,x" })).cause, "no-usable-signature");
  assert.equal((await checkSignature({ ...base, secret: "other" })).cause, "mismatch");
});

await check("offeredSignatures takes v1 entries and skips everything else", () => {
  assert.deepEqual(offeredSignatures("v1,abc"), ["abc"]);
  assert.deepEqual(offeredSignatures("v1,abc v1,def"), ["abc", "def"]);
  assert.deepEqual(offeredSignatures("v2,abc v1,def"), ["def"]);
  assert.deepEqual(offeredSignatures("v2,abc"), []);
  assert.deepEqual(offeredSignatures("abc"), []);
  assert.deepEqual(offeredSignatures("v1,"), []);
  assert.deepEqual(offeredSignatures(""), []);
});

// ===========================================================================
// 2. CONFIGURATION, METHOD, SIZE
// ===========================================================================

await check("an unset secret is a 503 that names nothing, never a 403", async () => {
  const r = await rig({ secret: "" });
  const res = await post(r);
  assert.equal(res.status, 503);
  const text = await bodyOf(res, "unset secret");
  assert.ok(!/forbidden/i.test(text), "a configuration problem must not read as a forged request");
  untouched(r, "unset secret");
});

await check("a GET is 405 with an Allow header and touches nothing", async () => {
  for (const method of ["GET", "PUT", "DELETE", "PATCH"]) {
    const r = await rig();
    const res = await post(r, { method });
    assert.equal(res.status, 405, `${method} was ${res.status}`);
    assert.equal(res.headers.get("allow"), "POST");
    untouched(r, method);
  }
});

await check("a body over the cap is refused before any of the crypto runs", async () => {
  const huge = JSON.stringify({ pad: "x".repeat(MAX_BODY_BYTES + 64) });
  const declared = await rig();
  const res = await post(declared, { body: huge });
  assert.equal(res.status, 413);
  await bodyOf(res, "huge body");
  untouched(declared, "huge body");

  // And with no content-length to believe — the measured half of the cap.
  const streamed = await rig();
  const res2 = await post(streamed, { body: huge, contentLength: false });
  assert.equal(res2.status, 413);
  untouched(streamed, "huge streamed body");
});

// ===========================================================================
// 3. THE CONTROL, AND WHAT THE FLIP TOUCHES
// ===========================================================================

await check(
  "CONTROL: a verified expiry marks BOTH the connection and the nudge needs_reconnect",
  async () => {
    const r = await rig();
    const res = await post(r);
    assert.equal(res.status, 200);
    const text = await bodyOf(res, "control");
    assert.deepEqual(JSON.parse(text), { ok: true, marked: "needs_reconnect" });

    // The API hand is withdrawn, so the router falls back to the browser and
    // Settings renders the ask.
    assert.equal(statusOf(r, OWNER_ACCOUNT), "needs_reconnect");
    // And the text half: the sweep's exclusions in due.ts read exactly this.
    const nudge = nudgeOf(r, OWNER, APP);
    assert.ok(nudge, "no connect_nudges row was written for the expired app");
    assert.equal(nudge.state, "needs_reconnect");
  },
);

await check("the bare event spelling is the same event", async () => {
  const r = await rig();
  const res = await post(r, { body: expired({ type: EXPIRED_EVENT_TYPES[1] }) });
  assert.equal(res.status, 200);
  assert.equal(statusOf(r, OWNER_ACCOUNT), "needs_reconnect");
  assert.equal(nudgeOf(r, OWNER, APP)?.state, "needs_reconnect");
});

await check("exactly the right owner's row moves, and nobody else's", async () => {
  const r = await rig();
  assert.equal((await post(r)).status, 200);
  // The same app, a different owner: untouched.
  assert.equal(statusOf(r, OTHER_ACCOUNT), "connected");
  // The same owner, a different app: untouched.
  assert.equal(statusOf(r, OWNER_ACCOUNT_2), "connected");
  // And exactly ONE nudge row exists in the whole table.
  const all = nudgesOf(r);
  assert.equal(all.length, 1, `${all.length} nudge rows were written`);
  assert.equal(all[0].user_id, OWNER);
  assert.equal(all[0].toolkit, APP);
});

await check("an event naming another owner's account is refused and writes nothing", async () => {
  const r = await rig();
  const body = expired({
    metadata: { connected_account_id: OTHER_ACCOUNT, user_id: OWNER },
  });
  const res = await post(r, { body });
  assert.equal(res.status, 409);
  await bodyOf(res, "wrong owner");
  assert.equal(statusOf(r, OTHER_ACCOUNT), "connected", "the holder's row moved");
  assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
  assert.equal(nudgesOf(r).length, 0, "a nudge row was written for a refused event");
});

await check("an event naming no owner at all is refused", async () => {
  const r = await rig();
  const res = await post(r, {
    body: expired({ metadata: { connected_account_id: OWNER_ACCOUNT } }),
  });
  assert.equal(res.status, 409);
  assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
  assert.equal(nudgesOf(r).length, 0);
});

await check("an owner id the event invents cannot move a row", async () => {
  const r = await rig();
  const res = await post(r, {
    body: expired({
      metadata: { connected_account_id: OWNER_ACCOUNT, user_id: "jose@anticipy.ai" },
    }),
  });
  assert.equal(res.status, 409);
  assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
});

await check("an account we do not hold is a quiet 200 and writes nothing", async () => {
  const r = await rig();
  const res = await post(r, {
    body: expired({ metadata: { connected_account_id: UNKNOWN_ACCOUNT, user_id: OWNER } }),
  });
  assert.equal(res.status, 200);
  const text = await bodyOf(res, "unknown account");
  assert.deepEqual(JSON.parse(text), { ok: true, ignored: "no such connection" });
  assert.equal(connectionCount(r), 3, "a connection row was created out of thin air");
  assert.equal(nudgesOf(r).length, 0);
});

await check("an event type we do not subscribe to is a quiet 200", async () => {
  for (const type of ["composio.trigger.message", "connected_account.created", "", "expired"]) {
    const r = await rig();
    const res = await post(r, { body: expired({ type }) });
    assert.equal(res.status, 200, `type ${JSON.stringify(type)} was ${res.status}`);
    const text = await bodyOf(res, `type ${JSON.stringify(type)}`);
    assert.deepEqual(JSON.parse(text), { ok: true, ignored: "not an expiry" });
    assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
    assert.equal(nudgesOf(r).length, 0);
  }
});

await check("a signed body that is not JSON is a 400 and writes nothing", async () => {
  for (const body of ["not json", "[]", '"a string"', "null", "42"]) {
    const r = await rig();
    const res = await post(r, { body });
    assert.ok(res.status === 400 || res.status === 200, `body ${body} was ${res.status}`);
    await bodyOf(res, `body ${body}`);
    assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
    assert.equal(nudgesOf(r).length, 0);
  }
  // The unparseable one is specifically a 400: a retry cannot fix it.
  const r = await rig();
  assert.equal((await post(r, { body: "not json" })).status, 400);
});

await check("an expiry naming no account is a 400 and writes nothing", async () => {
  const r = await rig();
  const res = await post(r, { body: expired({ metadata: { user_id: OWNER } }) });
  assert.equal(res.status, 400);
  await bodyOf(res, "no account");
  assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
  assert.equal(nudgesOf(r).length, 0);
});

await check("a connection the owner already disconnected is left alone", async () => {
  const r = await rig({ connections: [conn({ status: "disconnected" })] });
  const res = await post(r);
  assert.equal(res.status, 200);
  const text = await bodyOf(res, "already disconnected");
  assert.deepEqual(JSON.parse(text), { ok: true, ignored: "already disconnected" });
  assert.equal(statusOf(r, OWNER_ACCOUNT), "disconnected");
  assert.equal(nudgesOf(r).length, 0, "somebody who removed an app was queued for an ask");
});

await check("replaying the same event twice leaves one state, not two", async () => {
  const r = await rig();
  assert.equal((await post(r)).status, 200);
  const after1 = nudgeOf(r, OWNER, APP);
  assert.equal((await post(r)).status, 200);
  const after2 = nudgeOf(r, OWNER, APP);

  assert.equal(connectionCount(r), 3, "the replay created a second connection row");
  assert.equal(nudgesOf(r).length, 1, "the replay created a second nudge row");
  assert.equal(statusOf(r, OWNER_ACCOUNT), "needs_reconnect");
  assert.deepEqual(after2, after1, "the replay changed the nudge row");
});

await check("the ask's own history survives the flip", async () => {
  const seeded = nudgeRow({
    state: "declined", level: 2, snooze_until: NOW + 5 * 86_400_000,
    trigger: "in_task", sent_at: NOW - 20 * 86_400_000, acted_at: NOW - 20 * 86_400_000,
    channel: "sms",
  });
  const r = await rig({ nudges: [seeded] });
  assert.equal((await post(r)).status, 200);
  const after = nudgeOf(r, OWNER, APP);
  assert.ok(after);
  assert.equal(after.state, "needs_reconnect", "the state did not flip");
  // Every other column, unchanged. These are how "declined twice" and "we
  // already raised this" stay true; nudge.ts's reconnect branch reads sent_at.
  assert.equal(after.level, 2);
  assert.equal(after.snooze_until, seeded.snooze_until);
  assert.equal(after.trigger, "in_task");
  assert.equal(after.sent_at, seeded.sent_at);
  assert.equal(after.acted_at, seeded.acted_at);
  assert.equal(after.channel, "sms");
});

await check("a first-ever nudge row is created when there is none", async () => {
  const r = await rig();
  assert.equal((await post(r)).status, 200);
  const after = nudgeOf(r, OWNER, APP);
  assert.ok(after, "no row was created for an owner who had never been asked");
  assert.equal(after.state, "needs_reconnect");
  assert.equal(after.level, 0);
  assert.equal(after.snooze_until, null);
  assert.equal(after.sent_at, null);
  assert.equal(after.acted_at, null, "an expiry claimed an action the owner never took");
});

await check("the write opt-in and the alias survive the flip", async () => {
  const r = await rig({
    connections: [conn({ writes_enabled: true, alias: "personal", last_used_at: NOW - 1000 })],
  });
  assert.equal((await post(r)).status, 200);
  const row = r.db.rows<Record<string, unknown>>(
    `SELECT * FROM connections WHERE connected_account_id = ?`, OWNER_ACCOUNT,
  )[0];
  assert.equal(row.status, "needs_reconnect");
  assert.equal(row.writes_enabled, 1, "the owner's 'let Anticipy make changes' was revoked");
  assert.equal(row.alias, "personal", "the refresh link would lose the account alias");
  assert.equal(row.last_used_at, NOW - 1000);
  assert.equal(row.toolkit, APP);
  assert.equal(row.user_id, OWNER);
});

await check("the toolkit comes from the stored row, never from the event", async () => {
  const r = await rig();
  const res = await post(r, {
    body: expired({
      metadata: {
        connected_account_id: OWNER_ACCOUNT, user_id: OWNER, toolkit: "not_this_app",
      },
      data: { toolkit: "nor_this_one" },
    }),
  });
  assert.equal(res.status, 200);
  const all = nudgesOf(r);
  assert.equal(all.length, 1);
  assert.equal(all[0].toolkit, APP, "the nudge was filed under the app the EVENT named");
});

await check("the ids may arrive in metadata, in data, or at the top level", async () => {
  const shapes: Record<string, unknown>[] = [
    { metadata: { connected_account_id: OWNER_ACCOUNT, user_id: OWNER } },
    { data: { connected_account_id: OWNER_ACCOUNT, user_id: OWNER } },
    { connected_account_id: OWNER_ACCOUNT, user_id: OWNER },
    { metadata: { connectedAccountId: OWNER_ACCOUNT, userId: OWNER } },
  ];
  for (const shape of shapes) {
    const r = await rig();
    const res = await post(r, {
      body: JSON.stringify({ type: EXPIRED_EVENT_TYPES[0], ...shape }),
    });
    assert.equal(res.status, 200, `${JSON.stringify(shape)} was ${res.status}`);
    assert.equal(statusOf(r, OWNER_ACCOUNT), "needs_reconnect", JSON.stringify(shape));
  }
});

await check("the vendor's plural owner echo is read, and an ambiguous one is not", async () => {
  // connections/provider.ts measured this against the live vendor: `user_ids`
  // is the spelling the REQUEST uses, so an array echo is the likeliest shape,
  // and handling only a bare string "read as silence". Silence here would mean
  // every expiry refused forever, with a green deploy.
  const ok = await rig();
  const res = await post(ok, {
    body: expired({ metadata: { connected_account_id: OWNER_ACCOUNT, user_ids: [OWNER] } }),
  });
  assert.equal(res.status, 200);
  assert.equal(statusOf(ok, OWNER_ACCOUNT), "needs_reconnect");

  // Two names in one array is not an answer to "whose account is this", and
  // picking the first would be this file choosing a person out of a list.
  for (const users of [[OWNER, OTHER], [OTHER, OWNER], [], [null], [7]]) {
    const r = await rig();
    const refused = await post(r, {
      body: expired({ metadata: { connected_account_id: OWNER_ACCOUNT, user_ids: users } }),
    });
    assert.equal(refused.status, 409, `user_ids ${JSON.stringify(users)} was ${refused.status}`);
    assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
    assert.equal(nudgesOf(r).length, 0);
  }
});

await check("the event's own toolkit is never even read", () => {
  // The structural half of the check above: `readEvent` returns three fields,
  // and a fourth one appearing here is somebody starting to take the app off
  // the event instead of off our own row.
  const keys = Object.keys(
    readEvent({ type: EXPIRED_EVENT_TYPES[0], metadata: { toolkit: "not_this_app" } }),
  ).sort();
  assert.deepEqual(keys, ["accountId", "owner", "type"]);
});

await check("a stored row this system could not have minted is not acted on", async () => {
  // A `user_id` that passes schema.sql's `length = 15` CHECK but is not an id
  // this system mints (uppercase). `ownerOfAccount` cannot name a holder for
  // it, so the event is a quiet 200 and NOTHING is written — rather than a
  // flip that the store then refuses halfway through with a 500.
  const r = await rig({ connections: [] });
  const weird = "OwnerWebhook001";
  r.db.db.prepare(
    `INSERT INTO connections (connected_account_id, user_id, toolkit, alias, status,
       writes_enabled, last_used_at) VALUES (?,?,?,'','connected',0,NULL)`,
  ).run(OWNER_ACCOUNT, weird, APP);
  r.db.log.length = 0;

  const res = await post(r, {
    body: expired({ metadata: { connected_account_id: OWNER_ACCOUNT, user_id: weird } }),
  });
  assert.equal(res.status, 200);
  const text = await bodyOf(res, "unmintable owner");
  assert.deepEqual(JSON.parse(text), { ok: true, ignored: "no such connection" });
  assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
  assert.equal(nudgesOf(r).length, 0);
});

await check("readEvent invents nothing it was not given", () => {
  assert.deepEqual(readEvent(null), { type: "", accountId: "", owner: "" });
  assert.deepEqual(readEvent([]), { type: "", accountId: "", owner: "" });
  assert.deepEqual(readEvent({ type: 7 }), { type: "", accountId: "", owner: "" });
  assert.deepEqual(
    readEvent({ type: " x ", metadata: { connected_account_id: " ca_1 ", user_id: OWNER } }),
    { type: "x", accountId: "ca_1", owner: OWNER },
  );
  assert.equal(readEvent({ metadata: { connected_account_id: "" } }).accountId, "");
  assert.equal(readEvent({ metadata: { connected_account_id: 5 } }).accountId, "");
  assert.equal(isExpiredEvent(EXPIRED_EVENT_TYPES[0]), true);
  assert.equal(isExpiredEvent("composio.connected_account.expired.v2"), false);
  assert.equal(isExpiredEvent(""), false);
});

// ===========================================================================
// 4. WHEN THE WRITES FAIL — the vendor's retry is the transaction
// ===========================================================================

await check("a failed nudge write is a 500, so the vendor retries", async () => {
  const r = await rig();
  r.db.failOn = (sql) => /INSERT INTO "connect_nudges"/.test(sql);
  const res = await post(r);
  assert.equal(res.status, 500, "a write that did not land answered as if it had");
  await bodyOf(res, "nudge write failed");
  // The half that PROTECTS the person landed first, on purpose: the router is
  // already off the dead credential.
  assert.equal(statusOf(r, OWNER_ACCOUNT), "needs_reconnect");
  assert.equal(nudgesOf(r).length, 0);

  // The retry repairs rather than doubling.
  r.db.failOn = null;
  assert.equal((await post(r)).status, 200);
  assert.equal(nudgesOf(r).length, 1);
  assert.equal(nudgeOf(r, OWNER, APP)?.state, "needs_reconnect");
  assert.equal(connectionCount(r), 3);
});

await check("a failed connection write writes no nudge either", async () => {
  const r = await rig();
  r.db.failOn = (sql) => /INSERT INTO "connections"/.test(sql);
  const res = await post(r);
  assert.equal(res.status, 500);
  assert.equal(statusOf(r, OWNER_ACCOUNT), "connected");
  assert.equal(
    nudgesOf(r).length, 0,
    "the ask was queued for a connection whose status never moved",
  );
});

await check("a read that fails is a 500, never a quiet 200", async () => {
  const r = await rig();
  r.db.failOn = (sql) => /SELECT "user_id" FROM "connections"/.test(sql);
  const res = await post(r);
  assert.equal(res.status, 500, "an unreadable database answered as 'no such connection'");
  assert.equal(nudgesOf(r).length, 0);
});

await check("a row that vanishes mid-flight is a quiet 200", async () => {
  const r = await rig();
  const deps: ConnectionsWebhookDeps = {
    now: () => NOW,
    store: {
      ...r.deps.store,
      async ownerOfAccount() { return OWNER; },
      async readConnection() { return null; },
    },
  };
  const res = await connectionsWebhook(
    new Request(URL, {
      method: "POST",
      headers: {
        "webhook-id": WEBHOOK_ID,
        "webhook-timestamp": TS,
        "webhook-signature": "v1," + sign(SECRET, WEBHOOK_ID, TS, expired()),
      },
      body: expired(),
    }),
    r.env,
    deps,
  );
  assert.equal(res.status, 200);
  const text = await bodyOf(res, "vanished");
  assert.deepEqual(JSON.parse(text), { ok: true, ignored: "no such connection" });
  assert.equal(nudgesOf(r).length, 0);
});

// ===========================================================================
// 5. THE HALF THAT IS NOT BUILT
// ---------------------------------------------------------------------------
// The phone half of the needs-reconnect surface is live: Settings reads
// `connections.status`. The TEXT half reaches nobody, and cannot from here —
// three things in the ask pipeline refuse a reconnect and none of them lives in
// a file this route may edit (see AND NOBODY IS TOLD in the route's header).
// What this section pins is that the gap cannot read as success and cannot be
// forgotten.
// ===========================================================================

/** Everything the code under test logged while `fn` ran. */
async function logsOf(fn: () => Promise<unknown>): Promise<string[]> {
  const lines: string[] = [];
  const real = console.log;
  console.log = (...args: unknown[]): void => { lines.push(args.map((a) => String(a)).join(" ")); };
  try { await fn(); } finally { console.log = real; }
  return lines;
}

await check("a marked expiry does not read as success: the log says nobody was told",
  async () => {
    // THE FAILURE THIS CATCHES IS A LOG LINE, and this repo has been bitten by
    // that exact shape twice: the ears were deaf for 30 hours behind a leg that
    // printed a reassuring sentence. "needs reconnect" alone is the row moving;
    // the surface is two halves and only one of them happened.
    const r = await rig();
    const lines = await logsOf(() => post(r));
    const marked = lines.filter((l) => l.includes("needs reconnect"));
    assert.equal(marked.length, 1, `the marked outcome logged ${marked.length} lines`);
    assert.ok(marked[0]!.includes(UNTOLD),
      `the log reads as a working surface: ${JSON.stringify(marked[0])}`);
    // CONTROL: it is still the line that says WHAT moved, for WHOM. A warning
    // that lost the fact is not an improvement.
    assert.ok(marked[0]!.includes(OWNER) && marked[0]!.includes(APP),
      "the log stopped naming the owner and the app it moved");
  });

await check("CONTROL: an outcome that changed nothing does not claim anybody was untold",
  async () => {
    // The warning belongs to the one outcome that leaves a person waiting to be
    // told. An ignored event has nobody to tell.
    const r = await rig();
    const lines = await logsOf(() => post(r, {
      body: expired({ metadata: { connected_account_id: UNKNOWN_ACCOUNT, user_id: OWNER } }),
    }));
    assert.ok(lines.length > 0, "the ignored event logged nothing at all");
    for (const line of lines) {
      assert.ok(!line.includes(UNTOLD), `an ignored event warned about somebody: ${line}`);
    }
  });

await check("PIN: the day a reconnect has a moment to name, this file gets wired", () => {
  // NOT A LAW-2 EXPIRY, and the difference matters: there is no tape in the
  // route, and nothing here goes green by being deleted. This is a WAKE-UP. It
  // goes red the day `TRIGGER_SCORE` grows a sixth moment — which is the day
  // `shouldAsk`'s reconnect branch becomes reachable honestly, and the day the
  // two lines that hand a marked expiry to `sendConnectAsk` belong in the route.
  //
  // Read the failure message, then read AND NOBODY IS TOLD in
  // src/routes/connections_webhook.ts. Do not "fix" this by editing the list.
  assert.deepEqual(
    Object.keys(TRIGGER_SCORE).sort(),
    ["in_task", "laptop_closed", "onboarding", "repeated_use", "user_named_it"],
    "the moments an ask may be tied to have changed. If one of them can name a "
      + "credential expiring, wire connections_webhook.ts to sendConnectAsk and delete "
      + "this pin; if not, update the list and leave the pin standing.",
  );
});

await check("the gap is written down where the next reader stands", () => {
  // HARNESS-LAWS law 4: a conclusion that lives only in a conversation gets
  // re-derived, wrong, by the next session. Anchored on a literal that occurs
  // EXACTLY ONCE in the route.
  const anchor = "AND NOBODY IS TOLD. WHY NOT, MEASURED RATHER THAN ASSUMED";
  const n = SOURCE.split(anchor).length - 1;
  assert.equal(n, 1, `the route records the gap ${n} times`);
  const warnings = SOURCE.split(UNTOLD).length - 1;
  assert.equal(warnings, 1, `the route carries ${warnings} copies of the untold warning`);
  // And the three blockers are named rather than gestured at, so the next
  // reader can check them instead of trusting them.
  for (const named of ["whatIsMissing", "tasksThatWouldHaveUsedIt", "MOMENT_SENTENCE"]) {
    assert.ok(SOURCE.includes(named), `the note does not name ${named}`);
  }
});

// ===========================================================================
// 6. THE WIRING, THE REGISTRATION, AND THE REGISTER
// ===========================================================================

await check("webhookDeps refuses to build without a DB binding", () => {
  assert.equal(webhookDeps({} as ConnectionsWebhookEnv), null);
  assert.equal(webhookDeps(null as unknown as ConnectionsWebhookEnv), null);
});

await check("a Worker with no DB binding answers 503, not 500", async () => {
  const env = { COMPOSIO_WEBHOOK_SECRET: SECRET } as ConnectionsWebhookEnv;
  const res = await connectionsWebhook(
    new Request(URL, {
      method: "POST",
      headers: {
        "webhook-id": WEBHOOK_ID,
        "webhook-timestamp": TS,
        "webhook-signature": "v1," + sign(SECRET, WEBHOOK_ID, TS, expired()),
      },
      body: expired(),
    }),
    env,
  );
  assert.equal(res.status, 503);
  await bodyOf(res, "no binding");
});

await check("src/index.ts actually routes this path to this handler", () => {
  // The measured failure of this repo: a tested part nothing calls. Anchored on
  // literals that occur EXACTLY ONCE in src/index.ts.
  const anchors = [
    `if (path === CONNECTIONS_WEBHOOK_PATH) {`,
    `return connectionsWebhook(request, env as unknown as ConnectionsWebhookEnv);`,
  ];
  for (const anchor of anchors) {
    const n = INDEX_SOURCE.split(anchor).length - 1;
    assert.equal(n, 1, `src/index.ts contains ${n} copies of ${JSON.stringify(anchor)}`);
  }
  assert.equal(CONNECTIONS_WEBHOOK_PATH, "/connections/events");
});

await check("this suite is in package.json's test script", () => {
  const anchor = "test/connections-webhook.test.ts";
  const n = PACKAGE_JSON.split(anchor).length - 1;
  assert.equal(n, 1, `package.json names this suite ${n} times; CI would not run it`);
  const script = (JSON.parse(PACKAGE_JSON) as { scripts: { test: string } }).scripts.test;
  assert.ok(script.includes(anchor), "the `test` script does not run this file");
});

await check("no app is named in the route's source", () => {
  // NO APP IS HARDCODED. The toolkit comes off the stored row at run time, so a
  // real app name appearing here would mean it stopped being generic.
  for (const app of ["gmail", "notion", "slack", "googlecalendar", "outlook", "github"]) {
    assert.ok(
      !new RegExp(`\\b${app}\\b`, "i").test(SOURCE),
      `the route's source names ${app}`,
    );
  }
});

await check("no response body this suite produced carries a forbidden term", () => {
  assert.ok(BODIES.length > 10, `only ${BODIES.length} bodies were collected`);
  for (const { where, text } of BODIES) {
    const lower = text.toLowerCase();
    for (const term of FORBIDDEN_TERMS) {
      const hit = new RegExp(`(^|[^a-z])${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^a-z]|$)`);
      assert.ok(!hit.test(lower), `the body at ${where} used ${JSON.stringify(term)}: ${text}`);
    }
  }
});

// ===========================================================================
// MUTATION REPORT — src/routes/connections_webhook.ts, 2026-09-06.
// 38 mutations, ALL 38 KILLED. Harness: one anchor per mutation, and the
// harness REFUSES to patch an anchor that does not occur EXACTLY ONCE in the
// file — a regex that silently fails to match produces a false "it is tested"
// reading, which is how three false green readings were produced in this repo
// on 2026-09-06 alone.
//
// TWO OF THESE "PASSED" ON THE FIRST RUN BECAUSE THE MUTATION WAS A NO-OP, and
// that is the same false reading wearing a different hat. #2 injected its
// always-yes return AFTER every refusal in `checkSignature`, so it changed
// nothing; #28 read the toolkit off `JSON.parse("{}")`, which is always empty.
// Both were rewritten to be real mutations and both then died. A survivor is
// only news once you have read the patch.
//
//   1  `if (!verdict.ok)` -> `if (false)`
//      -> 12 checks, first: "an unsigned event is refused, and the store is
//         never touched"
//   2  `checkSignature` returning ok:true before it reads anything
//      -> 13 checks, first: "an unsigned event is refused..."
//   3  the webhook-id dropped from `signedPayload`
//      -> 29 checks (every signed request stops verifying)
//   4  the webhook-timestamp dropped from `signedPayload`      -> 29 checks
//   5  `Math.abs(skew) > TOLERANCE` -> `skew > TOLERANCE`
//      -> "a timestamp beyond the window in the FUTURE is refused too"
//   6  the freshness window removed
//      -> "a stale timestamp is refused even when the signature is real"
//   7  the `/^-?\d{1,15}$/` timestamp shape check removed
//      -> "a timestamp that is not an integer count of seconds is refused"
//   8  the `v1` version test removed from `offeredSignatures`
//      -> "only a v1 signature counts, and an unknown version is not one"
//   9  `constantTimeEqual(candidate, mine)` -> a length compare
//      -> "an event signed with the wrong secret is refused and changes nothing"
//  10  `webhookKeyBytes` never decoding a `whsec_` secret
//      -> "a whsec_ secret keys the HMAC with its DECODED bytes"
//  11  the unset-secret branch removed (it then 403s)
//      -> "an unset secret is a 503 that names nothing, never a 403"
//  12  that same branch answering 403 instead of 503        -> same check
//  13  the method check removed
//      -> "a GET is 405 with an Allow header and touches nothing"
//  14  the MEASURED body cap removed (the declared one left)
//      -> "a body over the cap is refused before any of the crypto runs"
//  15  `if (!isExpiredEvent(...))` -> `if (false)`, so every event is acted on
//      -> "an event type we do not subscribe to is a quiet 200"
//  16  `EXPIRED_EVENT_TYPES.includes(type)` -> `type.includes("expired")`
//      -> same check, plus "readEvent invents nothing it was not given"
//  17  the empty-account-id branch removed
//      -> "an expiry naming no account is a 400 and writes nothing"
//  18  the owner compare removed entirely
//      -> "an event naming another owner's account is refused and writes
//         nothing" (+2 more)
//  19  the owner compare skipped when the event names nobody
//      -> "an event naming no owner at all is refused"
//  20  `ownerOfAccount` replaced by a read scoped to the EVENT's owner — the
//      shape where a wrong-person event becomes a shrug
//      -> "an event naming another owner's account is refused..." (+3 more)
//  21  the not-held outcome answered 404 (a retry storm)
//      -> "an account we do not hold is a quiet 200 and writes nothing"
//  22  the wrong-owner refusal answered 200
//      -> "an event naming another owner's account is refused..." (+2 more)
//  23  the `disconnected` guard removed
//      -> "a connection the owner already disconnected is left alone"
//  24  the flip also writing `writes_enabled: false`
//      -> "the write opt-in and the alias survive the flip"
//  25  the flip also writing `alias: null`                  -> same check
//  26  `existing ?? freshNudge(...)` -> always `freshNudge(...)`
//      -> "the ask's own history survives the flip"
//  27  the flip stamping `acted_at`
//      -> "a first-ever nudge row is created when there is none" (+2 more)
//  28  the toolkit read off the EVENT (both `readNudge` and `freshNudge`)
//      -> "the toolkit comes from the stored row, never from the event",
//         "the event's own toolkit is never even read"
//  29  the `putNudge` call deleted
//      -> 8 checks, first: "CONTROL: a verified expiry marks BOTH the
//         connection and the nudge needs_reconnect"
//  30  the `putConnection` call deleted                     -> 11 checks
//  31  the two writes reordered so the nudge lands first    -> 11 checks,
//      including "a failed connection write writes no nudge either"
//  32  the catch around `markNeedsReconnect` answering 200
//      -> "a failed nudge write is a 500, so the vendor retries" (+2 more)
//  33  `ownerOfAccount` swallowing a database failure and answering null
//      -> "a read that fails is a 500, never a quiet 200"
//  34  `ownerId(owner)` dropped from `ownerOfAccount`
//      -> "a stored row this system could not have minted is not acted on".
//      THIS ONE SURVIVED THE FIRST RUN. No HTTP path could reach it, because
//      our own store refuses to write a malformed `user_id` — so the check
//      that kills it seeds the row through SQLite directly, past the store,
//      which is the only way that row can exist (a hand-run migration, a
//      restored backup, a `wrangler d1 execute`). The check was written
//      because of the survivor, not before it.
//  35  the `webhook-` header prefix made unreadable (aliases only)
//      -> 25 checks, including every CONTROL
//  36  the registration in src/index.ts deleted
//      -> "src/index.ts actually routes this path to this handler"
//  37  `OWNER_KEYS` back to the singular spellings only — the shape that reads
//      the vendor's array echo as silence and refuses every expiry forever
//      -> "the vendor's plural owner echo is read, and an ambiguous one is not"
//  38  `v.length === 1` -> `v.length >= 1`, so a two-name array resolves to
//      whoever the vendor listed first
//      -> same check
//
// 2026-09-06, SECOND PASS — section 5, the half that is not built. Five more
// mutations, ALL FIVE KILLED, same harness and same one-anchor-one-occurrence
// rule.
//
//  39  the untold clause dropped from the `marked` log line, leaving the
//      sentence this file shipped with — the one that reads as the surface
//      working while the text half reaches nobody
//      -> 2 checks, first: "a marked expiry does not read as success"
//  40  the same warning printed on EVERY event, before the type is read
//      -> "CONTROL: an outcome that changed nothing does not claim anybody was
//         untold" — a warning on an ignored event is noise that trains an
//         operator to skip the line that matters
//  41  the `marked` line stopped naming the owner and the app
//      -> "a marked expiry does not read as success" (its CONTROL half: a
//         warning that lost the fact is not an improvement)
//  42  the header's AND NOBODY IS TOLD note deleted
//      -> "the gap is written down where the next reader stands" (law 4: a
//         finding that lives only in a chat is re-derived, wrong)
//  43  the note kept but the three blockers replaced by a gesture
//      -> same check: `whatIsMissing`, `tasksThatWouldHaveUsedIt` and
//         `MOMENT_SENTENCE` are named so the next reader can CHECK them
//
// AND ONE MUTATION OF ANOTHER FILE, to prove the wake-up pin is a pin: a sixth
// entry added to `TRIGGER_SCORE` in src/connections/words.ts (restored
// immediately) turns "PIN: the day a reconnect has a moment to name…" red. A
// pin that cannot be shown to fire is a comment.
// ===========================================================================

console.log(`\n${passes} passed, ${failures} failed`);
if (failures > 0) process.exit(1);
