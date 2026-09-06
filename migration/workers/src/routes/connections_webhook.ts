/**
 * src/routes/connections_webhook.ts — POST /connections/events, the ONE webhook
 * the vendor actually publishes, and the one we were ignoring.
 *
 * THE SPEC LINE, VERBATIM: "No webhook for a successful connection. Only
 * composio.connected_account.expired." And the consequence it draws:
 * "Subscribe to expired for the reconnect nudge."
 *
 * So this file has exactly one job. A credential the owner gave us has died at
 * the far end; nothing else in this system can find that out until a task tries
 * to use it and fails in front of the person. What the spec's surface table
 * asks for when it happens is two rows and no drama:
 *
 *   NEEDS RECONNECT — "Your [app] connection needs a quick refresh, tap when
 *   convenient. Until then I'll use the browser." Underneath: "Router falls
 *   back to browser automatically. Refresh link is a normal connect link with
 *   the same account alias."
 *
 * Both halves of that are rows this file writes:
 *
 *   `connections.status = 'needs_reconnect'`  — the API hand stops being
 *       offered, the router falls back to the browser, and Settings → Connected
 *       Apps renders the ask on the phone (routes/connections_api.ts returns
 *       this column verbatim).
 *   `connect_nudges.state = 'needs_reconnect'` — the text half. The sweep in
 *       connections/due.ts stops excluding this owner (its NOT EXISTS clauses
 *       are written against exactly these two values), and nudge.ts `shouldAsk`
 *       takes its reconnect branch: one gentle ask, then weekly at most.
 *
 * NOT ONE WORD OF THE ASK IS WRITTEN HERE, and that is deliberate. The copy
 * belongs to the existing writer (connections/words.ts `askText`, audited by
 * `askMessage` against FORBIDDEN_TERMS), which is a model asked one question on
 * its own. A house-written "your mail needs reauthorization" would be both a
 * register violation and a claim about somebody's account that no model made.
 * This file flips two state fields and stops.
 *
 * ---------------------------------------------------------------------------
 * WHY THE VERIFICATION IS THE WHOLE FILE
 * ---------------------------------------------------------------------------
 * An unauthenticated POST that could mark a connection expired is a remote
 * "break this person's account" button: it strips the API hand off a working
 * connection, drops every task for that app back to the slow browser hand, and
 * TEXTS THE OWNER about a problem that does not exist. Repeat it and the
 * product turns into a machine that asks somebody to reconnect an app every
 * week forever. So nothing below touches the store until the signature checks
 * out — the same order routes/connect.ts uses for the session, and for the same
 * reason: an unproven caller must not even be able to learn whether we hold an
 * account id, by status code or by stopwatch.
 *
 * THE SCHEME, READ OFF THE VENDOR'S OWN DOCS (docs.composio.dev/docs/
 * webhook-verification, read 2026-09-06). It is Standard Webhooks:
 *
 *   headers      `webhook-id`, `webhook-timestamp`, `webhook-signature`
 *                (the `svix-*` spellings are the same spec's aliases and are
 *                accepted as a fallback — same values, different brand)
 *   signed input `{webhook-id}.{webhook-timestamp}.{raw body}`
 *   signature    HMAC-SHA256, base64, presented as `v1,<base64>`; the header
 *                may carry a SPACE-SEPARATED LIST of them during a secret
 *                rotation, and any one matching is a match
 *   freshness    the timestamp is unix SECONDS and must be inside 300 s
 *
 * This is a real signature over the real body, not the weaker shared-secret
 * compare routes/sendblue.ts is stuck with (Sendblue publishes no HMAC). It is
 * therefore NOT the "if the signing scheme cannot be established, require a
 * shared secret and name that as the weaker choice" fallback the task allowed:
 * the scheme was established, so the strong thing is what is built.
 *
 * THE ONE THING THE DOCS DO NOT PIN is how the secret string becomes HMAC key
 * bytes. Composio's page shows a plain string in `COMPOSIO_WEBHOOK_SECRET`;
 * Standard Webhooks specifies `whsec_<base64>` with the base64 body decoded.
 * `webhookKeyBytes` below handles both, decided by the shape of OUR OWN SECRET
 * and never by anything the caller sends — so it is a config question, not an
 * attacker-controlled branch. If the vendor's dashboard hands out a `whsec_`
 * secret, paste it verbatim and it works; if it hands out a plain one, the same.
 *
 * ---------------------------------------------------------------------------
 * WHAT EACH ANSWER MEANS, because a webhook's status code is a control loop
 * ---------------------------------------------------------------------------
 *   503  the secret is unset. A CONFIGURATION problem, never dressed as a
 *        forged request — the sendblue precedent: a 403 here would read as an
 *        attack forever while the product quietly ignored every expiry.
 *   405  not a POST. With an Allow header, so a misconfigured URL is legible.
 *   413  a body larger than we will buffer, refused before any crypto.
 *   403  unsigned, wrongly signed, replayed or stale. Nothing is read, nothing
 *        is written, and the answer is identical for all of them.
 *   400  signed, but the body is not JSON, or names no account. A retry cannot
 *        make a malformed body parse, so it must not be a 5xx.
 *   409  signed, and it names an account WE HOLD FOR SOMEBODY ELSE. Refused
 *        with nothing written. Deliberately not a 200: our owner-binding and
 *        the vendor's disagree, and that is the exact shape of the failure this
 *        whole feature was built around (one operator's mailbox serving
 *        everybody). It must be visible, not swallowed.
 *   200  handled, OR quietly ignored: an event type we do not subscribe to, an
 *        account we do not hold, a connection the owner already disconnected.
 *        None of those is a problem, and an error would have the vendor
 *        retrying it forever.
 *   500  the writes could not land. The vendor retries; the writes are
 *        idempotent, so the retry repairs rather than duplicates.
 *
 * ---------------------------------------------------------------------------
 * HARNESS-LAWS LAW 1
 * ---------------------------------------------------------------------------
 * Nothing here decides what a person MEANT. There is no prose in a webhook: the
 * matching below is a header name, a base64 blob, a unix timestamp, an opaque
 * vendor id, and one event-type literal from a machine's closed enum. That is
 * the senses-and-transport clause. No app is named in this file, and none can
 * be: the toolkit comes off the STORED CONNECTION ROW, never off the event
 * body, so a new app in the catalog is a new app here with zero code.
 *
 * Spec: "Connections: how Anticipy asks, learns, and never says Composio",
 * 2026-09-05, page 26 (the surface table's NEEDS RECONNECT row) and the
 * "Composio facts we build on" table.
 */
import {
  createD1Store, ownerId,
  type StoredConnection, type StoredNudge, type StoreEnv,
} from "../connections/store.ts";
import { freshNudge } from "../connections/nudge.ts";

// ---------------------------------------------------------------------------
// ENV AND CONSTANTS
// ---------------------------------------------------------------------------

export interface ConnectionsWebhookEnv {
  DB: D1Database;
  /**
   * The webhook secret from the vendor's dashboard. UNSET IS A 503, never a
   * 403: a missing secret is our problem and must not spend the rest of the
   * year looking like somebody attacking us.
   */
  COMPOSIO_WEBHOOK_SECRET?: string;
}

/** The one path. Exported so src/index.ts and the suite name it once. */
export const CONNECTIONS_WEBHOOK_PATH = "/connections/events";

/**
 * The only event we act on, in the two spellings the vendor's own pages use
 * (the namespaced envelope `type`, and the bare name its event catalogue
 * lists). Anything else — including the trigger messages that arrive on this
 * same URL — is a 200 and a no-op.
 *
 * Being wrong here fails SAFE in the one direction that matters: an unknown
 * spelling means we ignore an expiry and the connection keeps its API hand
 * until a call comes back with an auth failure, which is the spec's OTHER
 * trigger for the same state. Acting on an event we cannot name would be the
 * unsafe direction, and this list is why we do not.
 */
export const EXPIRED_EVENT_TYPES: readonly string[] = Object.freeze([
  "composio.connected_account.expired",
  "connected_account.expired",
]);

/** Standard Webhooks' own window, and the vendor's documented default. */
export const SIGNATURE_TOLERANCE_MS = 300_000;

/**
 * How much body we will buffer before refusing. The whole payload the vendor
 * documents is a few hundred bytes; the HMAC is computed over the raw body, so
 * the body must be held in memory before it can be believed, and a webhook URL
 * is public. 64 KiB is four orders of magnitude of headroom and still a bound.
 */
export const MAX_BODY_BYTES = 64 * 1024;

/** The signature version this file can verify. An entry carrying any other
 *  version is not a signature we may believe, so it is skipped rather than
 *  guessed at. */
export const SIGNATURE_VERSION = "v1";

// ---------------------------------------------------------------------------
// THE SEAM
// ---------------------------------------------------------------------------

/**
 * The four store operations this route needs, and no others.
 *
 * `ownerOfAccount` is the one that is not already on `ConnectionsStore`, and it
 * exists because of a distinction the tests care about: an event for an account
 * NOBODY holds is a quiet 200, while an event for an account WE HOLD FOR
 * SOMEBODY ELSE is a refusal. `readConnection(owner, id)` answers null for both
 * of those, which would collapse a wrong-person signal into a shrug. So the
 * account id — the table's own primary key, globally unique across owners — is
 * asked WHO HOLDS IT first, and every value that is then written comes from the
 * store's own checked read of that owner's row.
 */
export interface WebhookConnectionStore {
  /** The owner holding this vendor account id, or null if no row does. */
  ownerOfAccount(connectedAccountId: string): Promise<string | null>;
  readConnection(user: string, connectedAccountId: string): Promise<StoredConnection | null>;
  putConnection(row: StoredConnection): Promise<void>;
  readNudge(user: string, toolkit: string): Promise<StoredNudge | null>;
  putNudge(row: StoredNudge): Promise<void>;
}

export interface ConnectionsWebhookDeps {
  store: WebhookConnectionStore;
  /** Injectable clock. Tests own time; production passes nothing. */
  now?(): number;
}

// ---------------------------------------------------------------------------
// PLUMBING
// ---------------------------------------------------------------------------

const json = (status: number, body: unknown): Response =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json" },
  });

/**
 * Byte-wise over the longer of the two, so the answer does not depend on WHERE
 * the first difference is. The same loop as index.ts `timingSafeEqual` and
 * routes/sendblue.ts `secretEqual`; the lengths compared here are structurally
 * fixed (a base64 SHA-256 is always 44 characters, an owner id always 15).
 */
export function constantTimeEqual(a: unknown, b: unknown): boolean {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  let diff = ab.byteLength ^ bb.byteLength;
  const n = Math.max(ab.byteLength, bb.byteLength);
  for (let i = 0; i < n; i++) diff |= (ab[i] ?? 0) ^ (bb[i] ?? 0);
  return diff === 0;
}

function base64(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

function unbase64(s: string): Uint8Array | null {
  try {
    const bin = atob(s);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

/**
 * The HMAC key, from OUR OWN configured secret and from nothing a caller sends.
 *
 * Standard Webhooks mints secrets as `whsec_<base64>` and keys the HMAC with
 * the DECODED bytes; the vendor's own page shows a plain string. Both are
 * handled, chosen by the shape of the secret in our environment, so whichever
 * the dashboard hands out can be pasted verbatim. A `whsec_` secret whose body
 * is not base64 falls back to its raw bytes rather than throwing — the operator
 * pasted something unusual, and refusing every event forever over it would be
 * the silent outage this file exists to prevent.
 */
export function webhookKeyBytes(secret: string): Uint8Array {
  const trimmed = String(secret ?? "").trim();
  if (trimmed.startsWith("whsec_")) {
    const decoded = unbase64(trimmed.slice("whsec_".length));
    if (decoded && decoded.byteLength > 0) return decoded;
  }
  return new TextEncoder().encode(trimmed);
}

/** `{webhook-id}.{webhook-timestamp}.{raw body}` — the vendor's own input, and
 *  the raw body means the RAW body: the bytes that arrived, never a re-encoded
 *  JSON.stringify of what we parsed out of them. */
export function signedPayload(id: string, timestamp: string, body: string): string {
  return `${id}.${timestamp}.${body}`;
}

/** HMAC-SHA256, base64, over WebCrypto — a Worker has no `node:crypto`. */
export async function signPayload(secret: string, payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    webhookKeyBytes(secret) as unknown as ArrayBuffer,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return base64(new Uint8Array(sig));
}

/**
 * The `v1` signatures a header offers, in order.
 *
 * The header is a space-separated list so a secret can be rotated without
 * dropping events, and each entry is `<version>,<base64>`. An entry whose
 * version is not `v1` is SKIPPED, not guessed at: a signature scheme we cannot
 * compute is not a signature we may accept.
 */
export function offeredSignatures(header: string): string[] {
  return String(header ?? "")
    .split(/\s+/)
    .filter((part) => part !== "")
    .map((part) => {
      const comma = part.indexOf(",");
      if (comma < 0) return null;
      if (part.slice(0, comma) !== SIGNATURE_VERSION) return null;
      const value = part.slice(comma + 1);
      return value === "" ? null : value;
    })
    .filter((v): v is string => v !== null);
}

export type SignatureCause =
  | "signed"
  | "missing-id"
  | "missing-timestamp"
  | "missing-signature"
  | "bad-timestamp"
  | "stale"
  | "no-usable-signature"
  | "mismatch";

export interface SignatureVerdict {
  ok: boolean;
  cause: SignatureCause;
  /** Operator-facing. Never carries the body, the secret or a signature. */
  detail: string;
}

/**
 * IS THIS THE VENDOR? A FLOOR: every path that is not a match answers false,
 * and the absence of a verdict is never permission.
 *
 * The timestamp is checked BEFORE the HMAC so a replayed body — a real, once
 * valid, correctly signed event captured off the wire — is refused on its age
 * rather than accepted on its arithmetic.
 */
export async function checkSignature(input: {
  secret: string;
  id: string | null;
  timestamp: string | null;
  signature: string | null;
  body: string;
  now: number;
}): Promise<SignatureVerdict> {
  const id = input.id ?? "";
  const timestamp = input.timestamp ?? "";
  const signature = input.signature ?? "";
  if (id === "") return { ok: false, cause: "missing-id", detail: "no webhook-id header" };
  if (timestamp === "") {
    return { ok: false, cause: "missing-timestamp", detail: "no webhook-timestamp header" };
  }
  if (signature === "") {
    return { ok: false, cause: "missing-signature", detail: "no webhook-signature header" };
  }

  // Unix SECONDS, per the spec and the vendor's page. A value that is not an
  // integer is refused rather than coerced: `Number("")` is 0 and `Number("x")`
  // is NaN, and a NaN compared against a window is false in both directions —
  // which would either open the gate or close it depending on how the
  // comparison happened to be written.
  if (!/^-?\d{1,15}$/.test(timestamp)) {
    return {
      ok: false, cause: "bad-timestamp",
      detail: `webhook-timestamp is not an integer count of seconds (${timestamp.length} chars)`,
    };
  }
  const sentAt = Number(timestamp) * 1000;
  const skew = input.now - sentAt;
  if (Math.abs(skew) > SIGNATURE_TOLERANCE_MS) {
    // The age is named because it is the one number that separates a replay
    // from a clock problem from a unit problem — a vendor that started sending
    // MILLISECONDS would show up here as an event tens of thousands of years
    // in the future, and this line is where somebody would read that.
    return {
      ok: false, cause: "stale",
      detail: `webhook-timestamp is ${Math.round(skew / 1000)}s away from now; the window is `
        + `${SIGNATURE_TOLERANCE_MS / 1000}s`,
    };
  }

  const offered = offeredSignatures(signature);
  if (offered.length === 0) {
    return {
      ok: false, cause: "no-usable-signature",
      detail: `no ${SIGNATURE_VERSION} signature in the webhook-signature header`,
    };
  }

  const mine = await signPayload(input.secret, signedPayload(id, timestamp, input.body));
  // EVERY offered signature is compared, and the loop does not break early:
  // during a rotation the vendor sends two, and short-circuiting on the first
  // match would make the work depend on which one matched.
  let matched = false;
  for (const candidate of offered) {
    if (constantTimeEqual(candidate, mine)) matched = true;
  }
  if (!matched) {
    return {
      ok: false, cause: "mismatch",
      detail: `none of the ${offered.length} offered signature(s) matches this body`,
    };
  }
  return { ok: true, cause: "signed", detail: "signed by the configured secret" };
}

// ---------------------------------------------------------------------------
// THE EVENT
// ---------------------------------------------------------------------------

/**
 * What we read out of a verified event, and the ONLY things we read.
 *
 * The toolkit is deliberately NOT among them. Which app a connection is for is
 * already written down in our own row, keyed by the account id the event names,
 * and taking it off the event instead would file a mail credential's expiry
 * under the calendar row — an ask about the wrong app, and a nudge row nothing
 * ever clears.
 */
export interface ExpiredEvent {
  type: string;
  accountId: string;
  owner: string;
}

const ACCOUNT_KEYS = ["connected_account_id", "connectedAccountId"] as const;
/**
 * `user_ids` PLURAL IS IN THIS LIST BECAUSE IT WAS MEASURED, not because it is
 * pretty. connections/provider.ts learned it the expensive way against the live
 * vendor: the plural is "the spelling the REQUEST uses, so an array echo is the
 * likeliest shape of all — and it read as silence for as long as only a bare
 * string was handled". Silence here is not a small bug: every expiry would be
 * refused as "names no owner", forever, with a green deploy and a quiet log.
 */
const OWNER_KEYS = ["user_id", "user_ids", "userId", "userIds"] as const;
/** Where the vendor's envelope puts them: `metadata` in the documented shape,
 *  `data` for the trigger-style payloads, and the top level for the flattened
 *  form. First non-empty wins; all three are the vendor's own spellings. */
const CONTAINERS = ["metadata", "data"] as const;

function asRecord(v: unknown): Record<string, unknown> | null {
  return v !== null && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}

function pick(payload: Record<string, unknown>, keys: readonly string[]): string {
  const places: Record<string, unknown>[] = [];
  for (const name of CONTAINERS) {
    const inner = asRecord(payload[name]);
    if (inner) places.push(inner);
  }
  places.push(payload);
  for (const place of places) {
    for (const key of keys) {
      const v = place[key];
      if (typeof v === "string" && v.trim() !== "") return v.trim();
      // ONE element, and only one. An empty array names nobody, and an array
      // naming two people is not an answer to "whose account is this" — taking
      // the first would be this file picking a person out of a list, which is
      // the wrong-person failure with a loop in front of it. Both come back
      // empty and are refused upstream.
      if (Array.isArray(v) && v.length === 1) {
        const only = v[0];
        if (typeof only === "string" && only.trim() !== "") return only.trim();
      }
    }
  }
  return "";
}

/** The envelope, read structurally. Missing pieces come back empty rather than
 *  invented, and the caller decides what an empty one costs. */
export function readEvent(payload: unknown): ExpiredEvent {
  const root = asRecord(payload) ?? {};
  const type = typeof root.type === "string" ? root.type.trim() : "";
  return { type, accountId: pick(root, ACCOUNT_KEYS), owner: pick(root, OWNER_KEYS) };
}

/** Is this the one event we subscribe to? A string compare against a frozen
 *  list of the vendor's own spellings — a machine's closed enum, not prose. */
export function isExpiredEvent(type: string): boolean {
  return EXPIRED_EVENT_TYPES.includes(type);
}

// ---------------------------------------------------------------------------
// THE FLIP
// ---------------------------------------------------------------------------

export type MarkOutcome =
  | { state: "marked"; owner: string; toolkit: string }
  | { state: "not-held" }
  | { state: "already-disconnected"; owner: string }
  | { state: "wrong-owner"; holder: string }
  | { state: "gone" };

/**
 * The whole behaviour, once the caller is proven to be the vendor.
 *
 * THE ORDER OF THE TWO WRITES IS THE SAFETY MODEL, and it is not alphabetical.
 * The `connections` row goes first because it is the half that PROTECTS the
 * person: until it says `needs_reconnect`, the router keeps handing steps to a
 * credential that is dead, and every one of them fails in front of them. The
 * `connect_nudges` row goes second because it is the half that TALKS to them,
 * and talking can wait for a retry. If the second write fails the caller
 * answers 500, the vendor retries, and both writes are idempotent — a replay
 * leaves one state, not two.
 *
 * Two calls rather than one D1 batch, said plainly rather than hidden: the
 * store's one-batch method is `recordConnection`, and it hardcodes the
 * `connected` half of this state machine. A second copy of that SQL here would
 * be a second answer to "how is a connection written", and the two would
 * diverge the first time either was edited. What a batch would buy — both rows
 * or neither — is bought instead by the vendor's own retry over idempotent
 * writes, which is the property a webhook already has and a connect callback
 * (one browser, one lease, no retry) does not.
 */
export async function markNeedsReconnect(
  store: WebhookConnectionStore,
  event: { accountId: string; owner: string },
): Promise<MarkOutcome> {
  // WHO HOLDS THIS ACCOUNT — asked of the table's own primary key, before the
  // event's claim about an owner is used for anything.
  const holder = await store.ownerOfAccount(event.accountId);
  if (holder === null || holder === "") return { state: "not-held" };

  // AND IS IT THE OWNER THE EVENT NAMES? A FLOOR: an event that names nobody
  // cannot confirm anything, and is refused exactly like one that names the
  // wrong person. Constant-time because it is the same class of compare as the
  // one in routes/connect.ts `vendorVouchesFor`, and consistency here is
  // cheaper than deciding case by case which ids are worth protecting.
  if (!constantTimeEqual(holder, event.owner)) return { state: "wrong-owner", holder };

  const row = await store.readConnection(holder, event.accountId);
  // A row that vanished between the two reads is somebody disconnecting while
  // this ran. Nothing to mark, and nothing wrong.
  if (row === null) return { state: "gone" };

  // A CONNECTION THE OWNER ALREADY REMOVED IS NOT A PROBLEM. Flipping a
  // `disconnected` row to `needs_reconnect` would ask somebody to reconnect an
  // app they deliberately took away — the product arguing with a decision.
  if (row.status === "disconnected") return { state: "already-disconnected", owner: holder };

  // ONLY `status` CHANGES. `writes_enabled` especially is passed through: the
  // owner's "let Anticipy make changes" opt-in is a decision about an app, not
  // about a credential, and a token dying at the far end is not them changing
  // their mind. The alias rides along for the same reason — the spec's refresh
  // link is "a normal connect link with the same account alias".
  await store.putConnection({ ...row, status: "needs_reconnect" });

  // THE ASK'S OWN HISTORY SURVIVES. `level`, `snooze_until`, `trigger`,
  // `sent_at`, `acted_at` and `channel` are read back and written back
  // untouched: they are how "this owner declined twice" and "we already raised
  // this three days ago" stay true, and nudge.ts's reconnect branch reads
  // `sent_at` to hold the weekly cadence. Wiping them here would turn every
  // vendor retry into a fresh licence to text somebody.
  //
  // THE TOOLKIT COMES OFF THE STORED ROW. Never off the event.
  const existing = await store.readNudge(holder, row.toolkit);
  const base = existing ?? freshNudge(holder, row.toolkit);
  await store.putNudge({ ...base, state: "needs_reconnect" });

  return { state: "marked", owner: holder, toolkit: row.toolkit };
}

// ---------------------------------------------------------------------------
// THE WIRING
// ---------------------------------------------------------------------------

/**
 * The store, built from the binding.
 *
 * `ownerOfAccount` is one column of one row by primary key, and it is the only
 * statement this file owns. Everything it decides is then re-read through
 * `createD1Store`, so the row that gets written carries the store's own
 * `checkedConnection` guards, its live-column handling and its cross-owner
 * predicate rather than a second, weaker copy of them here.
 */
export function webhookStore(env: ConnectionsWebhookEnv): WebhookConnectionStore {
  const store = createD1Store(env as StoreEnv);
  return {
    async ownerOfAccount(connectedAccountId: string): Promise<string | null> {
      const id = typeof connectedAccountId === "string" ? connectedAccountId.trim() : "";
      if (id === "") return null;
      const row = await env.DB
        .prepare(`SELECT "user_id" FROM "connections" WHERE "connected_account_id" = ?1`)
        .bind(id)
        .first<{ user_id: unknown }>();
      const owner = row === null ? "" : String(row.user_id ?? "");
      // Shape-checked through the store's own guard: a `user_id` this system
      // could not have minted means the row is not one we may act on, and
      // "who holds it" is then honestly "nobody we can name".
      try {
        return ownerId(owner);
      } catch {
        return null;
      }
    },
    readConnection: (user, id) => store.readConnection(user, id),
    putConnection: (row) => store.putConnection(row),
    readNudge: (user, toolkit) => store.readNudge(user, toolkit),
    putNudge: (row) => store.putNudge(row),
  };
}

export function webhookDeps(env: ConnectionsWebhookEnv): ConnectionsWebhookDeps | null {
  if (!env || !env.DB) return null;
  return { store: webhookStore(env) };
}

// ---------------------------------------------------------------------------
// THE ROUTE
// ---------------------------------------------------------------------------

/** The first six characters of the account id, for a log line. Enough to
 *  correlate two lines about one connection, useless as an identifier. */
function shortId(accountId: string): string {
  return accountId.length <= 6 ? accountId : `${accountId.slice(0, 6)}…`;
}

/**
 * POST /connections/events.
 *
 * The whole path is handed over by src/index.ts, unknown methods included, so
 * this can answer 405 with an Allow header rather than fall through to the
 * generic 404 — a webhook URL that 404s reads, in a vendor dashboard, as a URL
 * somebody typed wrong.
 */
export async function connectionsWebhook(
  request: Request,
  env: ConnectionsWebhookEnv,
  injected?: ConnectionsWebhookDeps | null,
): Promise<Response> {
  if (request.method !== "POST") {
    return new Response(null, { status: 405, headers: { allow: "POST" } });
  }

  const secret = typeof env?.COMPOSIO_WEBHOOK_SECRET === "string"
    ? env.COMPOSIO_WEBHOOK_SECRET.trim()
    : "";
  if (secret === "") {
    // Configuration, and it says so. The variable is named in the LOG, which is
    // the operator's half; the body stays neutral because it is read in a
    // vendor's dashboard.
    console.log(
      "connections/events 503: not configured — COMPOSIO_WEBHOOK_SECRET is unset on this "
        + "Worker, so every expiry is being refused and no owner will ever be asked to "
        + "reconnect. Copy the webhook secret from the vendor's dashboard and "
        + "`wrangler secret put COMPOSIO_WEBHOOK_SECRET`.",
    );
    return json(503, { ok: false, error: "connection events are not configured here" });
  }

  // The declared size first, so an enormous body is refused before it is
  // buffered; the measured size after, because Content-Length is the sender's
  // claim about itself and the cap has to hold whether or not it was honest.
  const declared = Number(request.headers.get("content-length") ?? "");
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {
    console.log(`connections/events 413: declared ${declared} bytes, over ${MAX_BODY_BYTES}`);
    return json(413, { ok: false, error: "body too large" });
  }

  // The RAW body, because the signature is over the bytes that arrived — never
  // a re-encoding of what we parsed out of them.
  let body: string;
  try {
    body = await request.text();
  } catch {
    return json(400, { ok: false, error: "could not read the body" });
  }
  if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
    console.log(`connections/events 413: body over ${MAX_BODY_BYTES} bytes`);
    return json(413, { ok: false, error: "body too large" });
  }

  const head = (name: string): string | null => {
    const primary = request.headers.get(`webhook-${name}`);
    if (primary !== null && primary.trim() !== "") return primary.trim();
    const alias = request.headers.get(`svix-${name}`);
    return alias !== null && alias.trim() !== "" ? alias.trim() : null;
  };

  const deps = injected ?? webhookDeps(env);
  if (!deps) {
    console.log("connections/events 503: no DB binding on this Worker");
    return json(503, { ok: false, error: "connection events are not configured here" });
  }
  const now = deps.now ? deps.now() : Date.now();

  // NOTHING ABOVE THIS LINE HAS TOUCHED THE STORE, and nothing below it runs
  // for a caller who has not proved they are the vendor.
  const verdict = await checkSignature({
    secret, id: head("id"), timestamp: head("timestamp"),
    signature: head("signature"), body, now,
  });
  if (!verdict.ok) {
    console.log(`connections/events 403: ${verdict.cause} — ${verdict.detail}`);
    return json(403, { ok: false, error: "forbidden" });
  }

  let payload: unknown;
  try {
    payload = JSON.parse(body);
  } catch {
    // A body that is not JSON will not become JSON on a retry.
    console.log("connections/events 400: signed, but the body is not JSON");
    return json(400, { ok: false, error: "body must be a JSON object" });
  }

  const event = readEvent(payload);
  const webhookId = head("id") ?? "";
  if (!isExpiredEvent(event.type)) {
    // Every other event the vendor sends lands on this same URL. Ignoring one
    // is normal, and it must not look like a failure.
    console.log(
      `connections/events 200, ignored: ${JSON.stringify(event.type)} is not an expiry `
        + `(webhook-id ${webhookId})`,
    );
    return json(200, { ok: true, ignored: "not an expiry" });
  }

  if (event.accountId === "") {
    // Signed, and of the right type, but there is no account on it. That is a
    // shape we cannot act on and a retry cannot fix, so it is loud and 4xx.
    console.log(
      `connections/events 400: an expiry naming no account (webhook-id ${webhookId})`,
    );
    return json(400, { ok: false, error: "the event names no connected account" });
  }

  let outcome: MarkOutcome;
  try {
    outcome = await markNeedsReconnect(deps.store, event);
  } catch (err) {
    // The writes could not land. 500 so the vendor retries; both writes are
    // idempotent, so the retry repairs instead of doubling.
    console.log(
      `connections/events 500: could not mark ${shortId(event.accountId)} — `
        + String((err as Error)?.message ?? err),
    );
    return json(500, { ok: false, error: "could not record the expiry" });
  }

  switch (outcome.state) {
    case "marked":
      console.log(
        `connections/events 200: ${outcome.owner} ${outcome.toolkit} needs reconnect `
          + `(${shortId(event.accountId)}, webhook-id ${webhookId})`,
      );
      return json(200, { ok: true, marked: "needs_reconnect" });
    case "not-held":
      // An account we never had, or one already deleted. Not a problem, and an
      // error here would be retried forever.
      console.log(
        `connections/events 200, ignored: no connection holds ${shortId(event.accountId)} `
          + `(webhook-id ${webhookId})`,
      );
      return json(200, { ok: true, ignored: "no such connection" });
    case "already-disconnected":
      console.log(
        `connections/events 200, ignored: ${outcome.owner} already disconnected `
          + `${shortId(event.accountId)}`,
      );
      return json(200, { ok: true, ignored: "already disconnected" });
    case "gone":
      console.log(
        `connections/events 200, ignored: ${shortId(event.accountId)} was removed while `
          + "this event was being handled",
      );
      return json(200, { ok: true, ignored: "no such connection" });
    case "wrong-owner":
    default:
      // The event names one person and our row names another. Nothing is
      // written, and it is NOT a 200: this is the wrong-person failure the
      // whole feature is shaped around, and it must be visible in the vendor's
      // dashboard rather than absorbed by a green tick.
      console.log(
        `connections/events 409: the expiry for ${shortId(event.accountId)} `
          + (event.owner === ""
            ? "names no owner at all, so nothing confirms it"
            : "names an owner this connection does not belong to")
          + "; nothing was changed",
      );
      return json(409, { ok: false, error: "that account is not this owner's" });
  }
}
