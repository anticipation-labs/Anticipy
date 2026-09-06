// ---------------------------------------------------------------------------
// THE COMPOSIO ADAPTER BEHIND `ConnectionProvider` — ONE OWNER AT A TIME.
// ---------------------------------------------------------------------------
// Ported out of spike/two-hands/src/connections/provider_composio.ts, which had
// been through two adversarial rounds and fifteen mutations. The behaviour and
// the reasoning are the spike's; what changed on the way into the Worker is
// listed at the bottom of this header, each item with the failure it prevents.
//
// Everything in this file exists to make ONE failure impossible: a connection
// bound to the wrong person. During the spike an operator's own Gmail and
// Calendar were connected by hand with `user_id: "omar"`, which is one mailbox
// serving everybody; it had to be revoked and deleted. So the shape of this
// adapter is not "call Composio", it is "call Composio for exactly this owner
// row id, and refuse rather than guess":
//
//   * every public method starts by re-validating the owner id AT RUNTIME,
//     because `OwnerId` is a TypeScript brand and both the Worker bundle and
//     the test runner strip types — the brand is gone before the code runs, so
//     the only thing standing between a display name and a Composio session is
//     the check below;
//   * the session cache is keyed by owner and carries a REVERSE index, so a
//     session id handed to two owners is a refusal, not a shared mailbox;
//   * `connections()` refuses a response carrying somebody else's `user_id`
//     rather than stamping ours over it — and refuses just as hard when the
//     row's owner cannot be read at all, because "the vendor did not say" is
//     not "the vendor agreed";
//   * `disconnect()` proves the account belongs to this owner BEFORE touching
//     it, because the vendor's revoke and delete endpoints take an account id
//     and no user scoping at all — an unscoped id in an unscoped endpoint is a
//     delete of a stranger's connection.
//
// Zero dependencies and an injected `fetchImpl`: the SDK would hide the wire,
// and the wire is the part that has already been wrong once (see
// `manage_connections` below). Every test over this file runs with no key, no
// account and no network.
//
// ENDPOINTS, measured live 2026-09-05 against api v3.1:
//   POST   /tool_router/session                      -> 201 {session_id, mcp,
//                                                       config, tool_router_tools}
//   POST   /tool_router/session/{sid}/link           -> {redirect_url}
//   GET    /connected_accounts?user_ids={owner}      -> {items:[…]}
//   POST   /connected_accounts/{id}/revoke           -> 200 ACTIVE / 409 not
//   DELETE /connected_accounts/{id}                  -> 200
// The two catalog endpoints were not measured that day. They were on 2026-09-06,
// against this account's live key, and every claim below is from that run rather
// than from the docs:
//   GET /toolkits?search={q}&limit={n}  -> 200 {items, next_cursor, total_pages,
//                                          current_page, total_items}
//                                         item: {slug, name, type, auth_schemes,
//                                          …, meta:{description, logo, app_url,
//                                          categories, tools_count, …}}
//   GET /toolkits/{slug}                -> 200 the same row plus base_url,
//                                          enabled and auth_config_details
// Three search probes, because the answers are the reason for three branches:
//   search=calendar        -> 3 items, slugs googlecalendar/outlook/googletasks
//                             (lowercase slugs, display-cased names)
//   search=qqzzxx…         -> 200 {items: [], total_items: 0} — a REAL "nothing
//                             matched", which is why an empty list from the
//                             vendor is an answer and every other empty is not
//   search=  (blank/spaces) -> a blank value returns the first page of the whole
//                             catalog (total_items 1505) and a spaces-only value
//                             is a vendor 400. Neither is a search, which is why
//                             routes/connections_api.ts refuses one before it
//                             gets here.
// A search row carries NO auth_config_details, so `scopes` is always empty on
// one — see `readToolkitMeta`.
//
// WHAT THIS FILE MAY NOT DO. It contains no app names, no permission copy and
// no phrasing. Which toolkit a person meant is a model's question (contract's
// `ToolkitJudge`); what the connect page says is generated from the metadata
// this file fetches (contract's `PermissionWords`). Nothing here reads natural
// language to decide an outcome — the only string comparisons below are against
// vendor ENUMS and vendor TOOL IDENTIFIERS, which is the same kind of plumbing
// as reading an HTTP status. HARNESS-LAWS law 1, "senses".
//
// WHAT CHANGED IN THE PORT, and why:
//   1. `readOwnerEcho` now ranks a positive `ours` ABOVE `unreadable`. In the
//      spike a row that unambiguously named the queried owner was refused if
//      any OTHER owner-ish field on it was blank — so one empty `user_ids: []`
//      beside a correct `user_id` took the whole call down, the Settings screen
//      showed no connections, and the nudge engine would then ask a person to
//      connect the app they connected last week. A guard that had become an
//      outage. `foreign` still outranks everything: a stranger named anywhere
//      is still the loudest thing this adapter can say.
//   2. Redaction is no longer blind to SCHEMELESS urls. `#safe` stripped only
//      `scheme://…`, so a vendor error token shaped like
//      `connect.<vendor>.dev/link/abc` — no whitespace, short, no "://", so it
//      passes `#errorToken` — reached a log line intact. Same blindness, same
//      fix, as the one in words.ts.
//   3. `connectionsFromEnv()` and the session-cache ceiling exist because this
//      now runs in a Worker isolate rather than a one-shot script. See each.
//
// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
// 2026-09-05, pages 20-31.

// TYPES ONLY, and deliberately so. `import type` is erased before this file is
// bundled or run, so the Worker's deployed bytes carry no dependency on the
// spike tree at all — but the types are the contract's OWN declarations rather
// than a second copy, so `OwnerId`'s brand is the same nominal type everywhere
// and a display name cannot be passed where an id belongs. The two runtime
// facts this file needs from the contract (the owner-id shape and, in words.ts,
// the trigger names) are re-declared below and PINNED to the contract's source
// text by test/connections-provider.test.ts, so a change there goes red here.
// When the Worker grows its own contract module, this is one line to repoint.
import type {
  AccountAlias,
  Connection,
  ConnectionProvider,
  DisconnectResult,
  OwnerId,
  Toolkit,
  ToolkitMeta,
} from "../../../../spike/two-hands/src/connections/contract.ts";

/** Pinned in the path, not floating. A silent bump to a version that renames
 *  `tool_router_tools` would make the guard below unable to see the connection
 *  tool — so the version this adapter was measured against is written down. */
export const COMPOSIO_BASE_URL = "https://backend.composio.dev/api/v3.1";

/** The vendor meta-tool that lets the MODEL start a connection on its own,
 *  which in practice means pasting a raw `connect.composio.dev/...` link into a
 *  text. The spec's first rule is that WE own the ask: our link, our page, our
 *  ten-minute token. So the session is created with the tool switched off and
 *  the response is checked for it by name.
 *
 *  This is an exact identifier match against a vendor tool id — not a search
 *  for words inside a description, and not a list of app names. Nothing about
 *  what a person MEANT is decided here. */
export const MANAGE_CONNECTIONS_TOOL = "COMPOSIO_MANAGE_CONNECTIONS";

/** The owner ROW id shape, as `ownerId()` in the connections contract defines
 *  it: 15 lowercase alphanumerics, never a name and never an email.
 *
 *  Re-declared here rather than imported so the deployed Worker has no runtime
 *  edge into the spike tree. The copy is not free-floating: the provider test
 *  reads the contract's own source and fails if this pattern and that one stop
 *  agreeing, which is the same trick test/llm-proxy.test.ts uses to keep the
 *  Worker's reply floor and the extension's from drifting apart. */
export const OWNER_ID_SHAPE = /^[a-z0-9]{15}$/;

/** How many owners' sessions one isolate keeps before it forgets all of them.
 *
 *  The spike was a script that ran once; this is a Worker isolate that can live
 *  for hours and serve everybody, so an unbounded owner→session map is a slow
 *  leak in a 128MB budget. Clearing the whole cache is chosen over an LRU
 *  because the cost of a miss is one extra `POST /tool_router/session` and the
 *  cost of an LRU is code nobody can check. Correctness does not depend on it:
 *  the cache is an optimisation, and the wrong-person guards are on the wire. */
export const MAX_CACHED_SESSIONS = 500;

/** THE SEARCH CAP, and it is a CEILING no caller can raise.
 *
 *  `search()` asks the vendor for at most this many rows and cuts whatever
 *  comes back to this many regardless, because `limit` is a request and a
 *  vendor that ignores it would put the whole catalog — 1,400+ toolkits — on a
 *  phone that renders one scrolling list.
 *
 *  Forty rather than ten: the whole point of `?q=` is connecting an app nobody
 *  ever asked about, and a tight cut is a local ranking decision wearing a
 *  number's clothes — it silently decides that the 11th row the VENDOR ranked
 *  is not worth showing. Forty is past where anybody scrolls and far short of
 *  a payload that matters. There is no second page: one search box asks one
 *  question, and `next_cursor` is deliberately not read, so nothing here can
 *  walk the catalog. */
export const MAX_SEARCH_RESULTS = 40;

// ---------------------------------------------------------------------------
// NAMED FAILURES. A method that returns an empty list because nobody set a key
// is worse than one that refuses: "this owner has connected nothing" is the
// claim that triggers a connect nudge to somebody who connected last week.
// ---------------------------------------------------------------------------

/** No API key — in the Worker, `env.COMPOSIO_API_KEY` unbound. Thrown by every
 *  method, including `disconnect()` — whose return type could carry
 *  `{revoked:false, deleted:false}` but must not, because that shape reads to a
 *  caller as "we tried and the provider could not", and the confirmation copy
 *  for it tells the owner their access was removed. */
export class ConnectionsUnconfigured extends Error {
  readonly code: string;
  constructor(op: string) {
    super(`connections ${op} refused: no API key was given to ComposioConnections`);
    this.name = "ConnectionsUnconfigured";
    this.code = "connections_no_api_key";
  }
}

/** The caller passed something that is not an owner ROW id.
 *
 *  The offending value is deliberately NOT echoed. A caller that confuses "who
 *  is this" with "what do we call them" passes a name or an email address, and
 *  an error message is the one place in a server that is guaranteed to reach a
 *  log file — so this reports the SHAPE (blank, or wrong length) and nothing
 *  else. The contract's own `ownerId()` carries the value for a caller that
 *  wants it at the point of failure. */
export class ConnectionsOwnerRequired extends Error {
  readonly code: string;
  constructor(op: string, detail: string) {
    super(
      `connections ${op} refused: the owner id was ${detail} — every Composio call binds `
        + "to the owner ROW id (15 lowercase alphanumerics), never a name or an email",
    );
    this.name = "ConnectionsOwnerRequired";
    this.code = "connections_owner_required";
  }
}

/** Something in this exchange belongs to a different owner. The whole module
 *  exists to make this loud: it is the failure that already happened once, and
 *  it is silent by nature — a stranger's mailbox works perfectly. */
export class ConnectionsOwnerMismatch extends Error {
  readonly code: string;
  constructor(op: string, detail: string) {
    super(`connections ${op} refused: ${detail}`);
    this.name = "ConnectionsOwnerMismatch";
    this.code = "connections_owner_mismatch";
  }
}

/** The session came back with the connection meta-tool still available. Not a
 *  warning: a session in this state hands the model a tool that sends the owner
 *  a raw vendor link, which is the one thing the spec forbids outright. */
export class ConnectionsManageConnectionsOn extends Error {
  readonly code: string;
  constructor(detail: string) {
    super(
      `connections session refused: ${detail} — the session must be created with `
        + "manage_connections off so the model can never paste a raw vendor link into a text",
    );
    this.name = "ConnectionsManageConnectionsOn";
    this.code = "connections_manage_connections_on";
  }
}

/** The vendor answered, and the answer was a failure. Carries the status and
 *  whether an unchanged retry could plausibly work, so `disconnect()` does not
 *  have to re-derive either. */
export class ConnectionsRequestFailed extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;
  constructor(op: string, status: number, detail: string) {
    super(`connections ${op} failed (HTTP ${status})${detail ? `: ${detail}` : ""}`);
    this.name = "ConnectionsRequestFailed";
    this.code = "connections_request_failed";
    this.status = status;
    this.retryable = isRetryableStatus(status);
  }
}

/** The vendor answered with a shape we cannot read. Separate from a failure on
 *  purpose: "we did not understand the answer" and "this owner has nothing"
 *  must never collapse into the same empty list. */
export class ConnectionsResponseShape extends Error {
  readonly code: string;
  constructor(op: string, detail: string) {
    super(`connections ${op} returned an unreadable shape: ${detail}`);
    this.name = "ConnectionsResponseShape";
    this.code = "connections_response_shape";
  }
}

/** A required argument that is not the owner id was blank or unusable. */
export class ConnectionsBadArgument extends Error {
  readonly code: string;
  constructor(op: string, detail: string) {
    super(`connections ${op} refused: ${detail}`);
    this.name = "ConnectionsBadArgument";
    this.code = "connections_bad_argument";
  }
}

// ---------------------------------------------------------------------------
// Structural readers. These parse JSON the vendor sent. None of them reads
// prose to decide anything.
// ---------------------------------------------------------------------------

function asRecord(v: unknown): Record<string, unknown> | null {
  return v !== null && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}
function asArray(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}
function asString(v: unknown): string | null {
  return typeof v === "string" && v.length > 0 ? v : null;
}

/** ONE canonical spelling for a toolkit, everywhere.
 *
 *  Composio spells the same toolkit `"gmail"` in `connected_accounts` and
 *  sometimes `"Gmail"` in a label. Every table in the connections contract is
 *  keyed by `(user_id, toolkit)`; two spellings means one app with two nudge
 *  rows, so the owner is asked to connect something they connected last week
 *  and the connected one never counts. Case folding an identifier is plumbing,
 *  not meaning. */
export function toolkitSlug(raw: unknown): string {
  return String(raw ?? "").trim().toLowerCase();
}

/** Will trying the exact same request again plausibly succeed?
 *
 *  Read from the STATUS only. `disconnect()` branches on this — a retryable
 *  revoke failure must not be followed by a delete, because the delete destroys
 *  the account id that is our only handle for ever revoking that token. Status
 *  0 is this file's spelling for a transport failure, where the request may
 *  well have landed and the answer was lost. */
export function isRetryableStatus(status: number): boolean {
  return status === 0 || status === 408 || status === 425 || status === 429 || status >= 500;
}

/** Did the vendor give a DEFINITE answer that this particular account cannot be
 *  revoked programmatically? Only then may `revokeUnavailable` be reported,
 *  because that flag does two irreversible things at once: `disconnect()` goes
 *  on to DELETE the row, and the confirmation copy tells a human "access was
 *  removed here, you may need to clear it in the app's own settings".
 *
 *  409 is the only status that carries that meaning, and it is the measured one
 *  — "the account is not in a revocable state". It is an ALLOW-LIST rather than
 *  "everything that is not retryable" because that inverse read the whole 4xx
 *  range as a statement about the owner's account:
 *    * 401/403 mean OUR key is wrong. Telling somebody to go clean up Google's
 *      settings because we misconfigured a header is a lie about their own
 *      security.
 *    * 400/404/405/422 mean OUR REQUEST was wrong — a stale id, a renamed path,
 *      a body the vendor rejected. Deleting on one of those destroys the only
 *      handle that could ever revoke a token that is still live at Google, and
 *      the person is told to go fix it themselves.
 *    * anything unmeasured (410, 418, a status added next quarter) is not
 *      understood, and a claim about somebody's security is not a thing to make
 *      out of a number we have never seen.
 *  Everything outside the allow-list falls through to `disconnect()`'s refusal
 *  branch: no delete, and a named failure the owner can retry. */
export function revokeIsDefinitivelyUnavailable(status: number): boolean {
  return status === 409;
}

/** Composio's connected-account status enum, mapped fail-closed.
 *
 *  Measured statuses: INITIATED, INITIALIZING, ACTIVE, EXPIRED. ACTIVE is the
 *  only one with a usable credential and EXPIRED is the only one that means
 *  "you had this and it broke". Everything else — a half-finished OAuth, a
 *  FAILED row, a status added next quarter — reports `disconnected`, because
 *  the two mistakes do not cost the same: calling a dead account connected
 *  routes a task to a hand with no credential and the owner watches it fail,
 *  while calling a half-finished account disconnected costs one nudge. */
export function mapConnectionStatus(raw: unknown): Connection["status"] {
  const token = String(raw ?? "").trim().toUpperCase();
  if (token === "ACTIVE") return "connected";
  if (token === "EXPIRED") return "needs_reconnect";
  return "disconnected";
}

/** The contract's closed alias set, read out of a vendor string.
 *
 *  Case folded, because "Work" and "work" are one account label and the spec's
 *  normal case is two Google accounts told apart by exactly this word. Anything
 *  outside the set becomes `null` rather than being carried through: the
 *  contract types this field `AccountAlias | null`, and a third value would sail
 *  past every consumer's switch and land in the database as a label nothing can
 *  match. */
export function readAlias(raw: unknown): AccountAlias | null {
  const token = String(raw ?? "").trim().toLowerCase();
  if (token === "work") return "work";
  if (token === "personal") return "personal";
  return null;
}

/** A millisecond timestamp, or null for "the vendor did not say".
 *
 *  Note what is NOT read here: `updated_at`. It moves whenever anything about
 *  the row changes, so reading it as "last used" would tell the router a
 *  connection is warm because somebody renamed it. An unknown last-use is null,
 *  and null must be read as unknown — never as "never used". */
export function readLastUsedAt(raw: unknown): number | null {
  if (typeof raw === "number") return Number.isFinite(raw) ? raw : null;
  const text = asString(raw);
  if (!text) return null;
  const ms = Date.parse(text);
  return Number.isFinite(ms) ? ms : null;
}

/** Whose account is this row, as far as the vendor's own answer can say?
 *
 *  FOUR states, because three of them are not the same thing. "a stranger",
 *  "there is something here and it is not an owner id we can read", and "this
 *  row names nobody" all used to collapse into the one answer the caller then
 *  treated as agreement.
 *
 *  Only `ours` may be adopted. This is a FLOOR — does anything confirm this row
 *  belongs to the owner we asked for? — and a floor that waves through when
 *  nobody answers is a decoration. What gets waved through here is a stranger's
 *  connection, stamped with our validated owner id and handed to `disconnect()`
 *  as ownership proof over `/{id}/revoke` and `DELETE /{id}`, two endpoints
 *  that take an account id and no user scoping at all. */
export type OwnerEcho = "ours" | "foreign" | "unreadable" | "absent";

/** The keys a connected-account row is known or likely to name its owner
 *  under. `user_ids` plural is first among equals: it is the spelling the
 *  REQUEST uses, so an array echo is the likeliest shape of all — and it read
 *  as silence for as long as only a bare string was handled. */
const OWNER_ECHO_KEYS = ["user_id", "user_ids", "userId", "userIds", "user"] as const;

export function readOwnerEcho(item: Record<string, unknown>, owner: string): OwnerEcho {
  let ours = false;
  let foreign = false;
  let unreadable = false;

  const one = (v: unknown): void => {
    const text = typeof v === "string" ? v.trim() : "";
    if (text.length === 0) unreadable = true;
    else if (text === owner) ours = true;
    else foreign = true;
  };

  for (const key of OWNER_ECHO_KEYS) {
    const value = item[key];
    // `undefined` is not a JSON value, so a key holding it is indistinguishable
    // from a key that is not there. `null` IS a JSON value and is unreadable,
    // not absent: the vendor sent an owner field and put nothing in it.
    if (value === undefined) continue;

    if (Array.isArray(value)) {
      // An empty array names nobody. A multi-element array naming us AND
      // somebody else is not agreement either — `foreign` wins below.
      if (value.length === 0) unreadable = true;
      else for (const element of value) one(element);
      continue;
    }
    const nested = asRecord(value);
    if (nested !== null) {
      const inner = nested.id ?? nested.user_id ?? nested.userId;
      if (inner === undefined) unreadable = true;
      else one(inner);
      continue;
    }
    one(value);
  }

  // THE ORDER IS THE WHOLE VERDICT, and it changed in this port.
  //
  // 1. A stranger named ANYWHERE in the row outranks everything else: the
  //    scoping did not hold, and that is the loudest thing this adapter can
  //    say. A row naming us AND somebody else is not agreement.
  // 2. A POSITIVE, unambiguous naming of the owner we asked for is next, and in
  //    the spike it was not — `unreadable` was tested first, so a row carrying
  //    a correct `user_id` beside an empty `user_ids: []` was refused, and with
  //    it the entire `connections()` call. That is a guard that became an
  //    outage: the owner's Settings page shows nothing, "you have not connected
  //    Notion" becomes true for a person who connected it last week, and the
  //    nudge engine asks them again. Nothing is waved through by this: the
  //    floor asked "does anything confirm this row is the owner's" and
  //    something did.
  // 3. Only then the two quiet verdicts, which both refuse at the call site.
  //    `unreadable` before `absent` because "there was an owner field and we
  //    could not read it" is the one that tells the next person which field to
  //    go and look at.
  if (foreign) return "foreign";
  if (ours) return "ours";
  if (unreadable) return "unreadable";
  return "absent";
}

/** Which owner-ish FIELDS the row carried, names only and never values.
 *
 *  A refusal is only useful if the next person can act on it, and the action
 *  here is always "read the field the vendor actually sends". Key names are
 *  constants from the list above, so nothing of the owner's leaks into a log
 *  line by this route. */
function ownerEchoFields(item: Record<string, unknown>): string {
  const seen = OWNER_ECHO_KEYS.filter((key) => item[key] !== undefined);
  return seen.length === 0 ? "none" : seen.join(", ");
}

/** Re-validate an owner id at runtime.
 *
 *  `OwnerId` is erased before this code runs — by the Worker's bundler and by
 *  `node --experimental-strip-types` alike. Without this call the branded type
 *  is a comment, and `session("omar")` type-checks in any caller that has a
 *  stray `as OwnerId` in it.
 *
 *  IT IS ALSO THE SEAM FOR CALLERS HOLDING A PLAIN STRING. A route that resolved
 *  the signed-in owner out of D1 has a `string`, and the way across is
 *  `provider.connections(requireOwner("connect page", id))` — never `as OwnerId`.
 *  The cast is a lie the compiler believes and the wire finds out about; this
 *  call refuses a name, an email or a blank before a request is issued, which is
 *  the whole failure this module is shaped around. */
export function requireOwner(op: string, raw: unknown): OwnerId {
  const seen = raw === null || raw === undefined ? "" : String(raw).trim();
  if (!OWNER_ID_SHAPE.test(seen)) {
    throw new ConnectionsOwnerRequired(
      op,
      seen.length === 0 ? "blank" : `not an owner row id (${seen.length} characters)`,
    );
  }
  return seen as OwnerId;
}

function requireToolkit(op: string, raw: unknown): Toolkit {
  const slug = toolkitSlug(raw);
  if (slug.length === 0) {
    throw new ConnectionsBadArgument(op, "no toolkit slug was given");
  }
  return slug;
}

function requireAccountId(op: string, raw: unknown): string {
  const id = raw === null || raw === undefined ? "" : String(raw).trim();
  if (id.length === 0) {
    throw new ConnectionsBadArgument(op, "no connected account id was given");
  }
  return id;
}

/** Our own callback, checked before it is handed to the vendor.
 *
 *  A blank or relative callback is not a small bug: the person taps a connect
 *  link, finishes at Google, and lands nowhere — and because Composio publishes
 *  no success webhook (only `expired`), the callback is the ONLY moment we
 *  learn the connection happened. A silent empty string here is a connection
 *  that works at the vendor and never appears in the product. */
function requireCallbackUrl(op: string, raw: unknown): string {
  const text = raw === null || raw === undefined ? "" : String(raw).trim();
  if (text.length === 0) {
    throw new ConnectionsBadArgument(op, "no callbackUrl was given");
  }
  let parsed: URL;
  try {
    parsed = new URL(text);
  } catch {
    throw new ConnectionsBadArgument(op, "callbackUrl is not an absolute URL");
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new ConnectionsBadArgument(op, "callbackUrl is not an http(s) URL");
  }
  return text;
}

/** Every tool identifier in a session's tool list, however the vendor spells
 *  the entries — plain strings today, objects with a `name` in some responses.
 *  Upper-cased for an EXACT identifier comparison, never a substring search.
 *
 *  `null` means NO VERDICT, and one unreadable entry is enough to produce it.
 *  This used to skip an entry it could not name and return the rest, so a list
 *  whose entries carried their identifier under any other key came back as an
 *  EMPTY array — and the caller reads "empty and readable" as "the connection
 *  tool is confirmed absent". That is a floor lifting itself: the entry nobody
 *  could parse is precisely the entry that might BE the connection tool, and
 *  the session would have been accepted with the model holding a tool that
 *  texts people raw vendor links.
 *
 *  A genuinely empty array is a different answer and stays a verdict: zero
 *  entries is the vendor saying the model is handed nothing, and nothing does
 *  not contain the tool. */
function toolIdentifiers(raw: unknown): string[] | null {
  if (!Array.isArray(raw)) return null;
  const out: string[] = [];
  for (const entry of raw) {
    const direct = asString(entry);
    if (direct) {
      out.push(direct.trim().toUpperCase());
      continue;
    }
    const record = asRecord(entry);
    // The spellings a tool list is known to use, including the nested
    // `function.name` of an OpenAI-shaped entry. Deliberately NOT `id`: a row
    // whose `id` is a uuid and whose identifier lives elsewhere would read as a
    // confidently parsed non-match, which is the hole above wearing a hat.
    const named = record === null
      ? null
      : asString(record.name)
        ?? asString(record.slug)
        ?? asString(record.tool_slug)
        ?? asString(record.tool_name)
        ?? asString(asRecord(record.function)?.name);
    if (named === null) return null;
    out.push(named.trim().toUpperCase());
  }
  return out;
}

/** Scopes, gathered from every place the toolkit response is known to put them.
 *
 *  Best-effort and documented as such, because `GET /toolkits/{slug}` was not
 *  among the endpoints measured on 2026-09-05. An empty array therefore means
 *  "the vendor told us nothing", NOT "this app asks for nothing" — and the
 *  permission sentences must treat it that way (words.ts refuses on an empty
 *  scope list rather than generating from nothing). Rendering "Anticipy will be
 *  able to:" followed by nothing, on a page whose next tap is a Google consent
 *  screen asking for permission to delete all mail, is the worst copy this
 *  product could ship. */
function readScopes(root: Record<string, unknown>): string[] {
  const meta = asRecord(root.meta);
  const found: string[] = [];
  const seen = new Set<string>();
  const take = (v: unknown): void => {
    for (const raw of asArray(v)) {
      // TRIMMED, and a scope that is only whitespace is not a scope. It would
      // reach the model as an empty bullet under "What the connection would
      // cover", and the model would have to write a permission sentence about
      // nothing -- which is the exact thing the no-scopes floor exists to stop,
      // arriving through the door marked "we have scopes".
      const scope = (asString(raw) ?? "").trim();
      if (scope && !seen.has(scope)) {
        seen.add(scope);
        found.push(scope);
      }
    }
  };
  take(root.scopes);
  take(meta?.scopes);
  for (const detail of asArray(root.auth_config_details)) {
    take(asRecord(detail)?.scopes);
    // `required_scopes` is the field the note below used to point at. It is
    // real, and on this account it is EMPTY for eleven of the twelve toolkits
    // measured — outlook has one. Read anyway: an app that declares a required
    // scope is naming the thing it cannot work without.
    take(asRecord(detail)?.required_scopes);
  }
  // WHERE THE SCOPES ACTUALLY ARE, measured against the live vendor on
  // 2026-09-06 with production's own key:
  //
  //     composio_managed_auth: [ { mode: "OAUTH2",
  //                                scopes: { available: [ "https://mail.google..." ] } } ]
  //
  //     gmail 11   googlecalendar 2   googledrive 2   slack 47   linear 5
  //     github 7   hubspot 33   outlook 12   googledocs 3   googlesheets 3
  //     notion 0   asana 0
  //
  // Not under `scopes`, not under `meta.scopes`, not under
  // `auth_config_details[].scopes`. Every path this function had was looking
  // somewhere the data has never been, which is why it returned [] for every
  // app and permissionSentences — correctly refusing to invent consent copy out
  // of nothing — closed every route to a connection in the product.
  for (const managed of asArray(root.composio_managed_auth)) {
    take(asRecord(asRecord(managed)?.scopes)?.available);
  }
  return found;
}

/** One catalog row, from either endpoint that produces one, or null.
 *
 *  `GET /toolkits/{slug}` and `GET /toolkits?search=` return the SAME row shape
 *  — the detail endpoint adds `auth_config_details`, which only `readScopes`
 *  looks at — so they share one reader. Two readers would be two answers to
 *  what an app is called, and the search list and the connect page would
 *  eventually disagree about the same toolkit.
 *
 *  `null` means the row cannot be shown: no name, or no slug. Both are fatal to
 *  a row rather than cosmetic — the slug is the vendor primary key every later
 *  call is made with, and a nameless row renders as a blank line with a Connect
 *  button on it. WHAT THE CALLER DOES WITH `null` DIFFERS, and deliberately:
 *  `toolkit()` refuses the whole call, because it was asked about one app and
 *  has no answer; `search()` drops the row, because one unreadable row in forty
 *  must not cost the other thirty-nine — and `search()` still refuses when
 *  NOTHING was readable, which is the shape that would otherwise claim an empty
 *  catalog.
 *
 *  `fallbackSlug` is the slug the caller ASKED about. `search()` passes null: it
 *  asked about no slug at all, so a row that names none is unusable rather than
 *  attributable to anything. */
function readToolkitMeta(
  root: Record<string, unknown>,
  fallbackSlug: string | null,
): ToolkitMeta | null {
  const meta = asRecord(root.meta);
  const name = asString(root.name) ?? asString(meta?.name);
  // The vendor's own spelling when it gives one: `connections()` returns
  // canonical slugs in `toolkit.slug`, so taking the canonical form here is what
  // keeps a catalog row and the connection it later produces on the same key.
  const slug = toolkitSlug(asString(root.slug) ?? fallbackSlug ?? "");
  if (!name || slug.length === 0) return null;
  return {
    slug,
    name,
    logo: asString(root.logo) ?? asString(meta?.logo) ?? null,
    description: asString(root.description) ?? asString(meta?.description) ?? null,
    appUrl: asString(root.app_url) ?? asString(meta?.app_url) ?? asString(root.appUrl) ?? null,
    // EMPTY ON EVERY SEARCH ROW, and that is the vendor's shape rather than a
    // gap here: measured 2026-09-06, a listing row carries no
    // `auth_config_details` at all. Empty means UNKNOWN, exactly as it does for
    // `toolkit()`, and words.ts refuses to generate permission sentences from
    // nothing — so the phone's disclosure sheet asks
    // `/me/connections/sentences`, which does the detail fetch, and never builds
    // consent copy out of a search row.
    //
    // THE NOTE THAT USED TO BE HERE WAS WRONG, and it was wrong in the most
    // expensive way available: it concluded "the data is not merely under
    // another key, it is absent", and that conclusion closed the file. It said
    // adding another key name "would be a change that looks like a fix and
    // moves nothing measurable."
    //
    // The data was there the whole time, under
    // `composio_managed_auth[].scopes.available` — eleven scopes for gmail,
    // forty-seven for slack, thirty-three for hubspot. Four toolkits were
    // checked, three key paths were tried, none of them was the right one, and
    // the absence of the data was written down as a fact about the vendor
    // instead of as a fact about where we had looked. Every route to a
    // connection in this product was closed by it: permissionSentences refuses
    // on an empty scope list, correctly, so no consent copy could be built for
    // any app and nobody could connect anything.
    //
    // Two toolkits really do publish none — notion and asana, both OAUTH2 with
    // an empty `available`. Those stay refused, and that is the floor working
    // rather than the bug: an app whose permissions we cannot name is an app we
    // cannot honestly ask about.
    scopes: readScopes(root),
  };
}

/**
 * What a LOG will treat as a link, not what a parser would.
 *
 * The spike stripped `scheme://…` and nothing else, which left one route open:
 * `#errorToken` passes any short, whitespace-free vendor `code` that does not
 * contain "://", so a token shaped like `connect.<vendor>.dev/link/abc` — the
 * exact thing this product must never write down — reached the log intact. Same
 * blindness as the one fixed in words.ts, same fix.
 *
 * The second alternative REQUIRES a slash after the host, deliberately: without
 * it, an ordinary sentence ending in "…in the browser.Connect it" reads as a
 * host, and over-redacting an error message costs the next person the only
 * information they had. Every tokenised link this redaction exists to catch
 * carries a path.
 */
const URL_SHAPED = /\b(?:https?|wss?):\/\/\S+|(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}\/\S*/gi;

// ---------------------------------------------------------------------------

export interface ComposioConnectionsOptions {
  apiKey?: string | null;
  baseUrl?: string;
  /** Always injected in tests. Defaults to `globalThis.fetch`, which is why
   *  there is no network anywhere in this suite. */
  fetchImpl?: typeof globalThis.fetch;
}

/** The one Worker binding this module needs. Declared here rather than imported
 *  from `src/index.ts`'s `Env` so nothing else has to change to wire it up, and
 *  so a caller can pass any object that carries the key. It is a SECRET
 *  (`wrangler secret put COMPOSIO_API_KEY`), never a plain var — a key in
 *  wrangler.jsonc is a key in git. */
export interface ConnectionsEnv {
  COMPOSIO_API_KEY?: string;
}

export class ComposioConnections implements ConnectionProvider {
  #apiKey: string;
  #baseUrl: string;
  #fetch: typeof globalThis.fetch | undefined;
  /** owner -> session id. */
  #sessions: Map<string, string>;
  /** session id -> the ONE owner it was minted for. This is the reverse index,
   *  and it is not paranoia about our own code: if the vendor ever hands the
   *  same `session_id` to two owners, both owners' tools run in one session and
   *  one person's Gmail answers for the other. Nothing else in the system would
   *  ever notice, because a stranger's mailbox works perfectly. */
  #sessionOwners: Map<string, string>;
  /** owner -> the in-flight creation of a session. Two taps from one owner in
   *  the same second would otherwise mint two sessions, and a link minted in
   *  session A is a connection session B cannot see — the person authorises
   *  Gmail and the next screen still says they have not connected it. */
  #inFlight: Map<string, Promise<string>>;

  constructor(opts: ComposioConnectionsOptions = {}) {
    // Trimmed because a key pasted from a dashboard arrives with a newline, and
    // a header value with a newline is rejected by fetch as an invalid HEADER
    // rather than as a bad key — an error nobody reads as "your key has
    // whitespace in it".
    this.#apiKey = typeof opts.apiKey === "string" ? opts.apiKey.trim() : "";
    this.#baseUrl = String(opts.baseUrl ?? COMPOSIO_BASE_URL).replace(/\/+$/, "");
    const impl = opts.fetchImpl ?? globalThis.fetch;
    // Bound to globalThis when it is the platform's own: an unbound `fetch`
    // throws "Illegal invocation" the first time it is called as a bare
    // function, which would reach a caller looking like a dead vendor.
    this.#fetch = typeof impl === "function"
      ? (opts.fetchImpl ? impl : impl.bind(globalThis))
      : undefined;
    this.#sessions = new Map();
    this.#sessionOwners = new Map();
    this.#inFlight = new Map();
    // Deliberately NOT thrown on a missing key: this is constructed at startup
    // beside things that still work without Composio. Every method refuses by
    // name instead.
  }

  // -------------------------------------------------------------------------
  // Redaction. The only text this adapter ever puts in an error goes through
  // here.
  // -------------------------------------------------------------------------
  /** Strip the key and any URL out of text derived from a response.
   *
   *  Two separate leaks, one choke point. Composio's error bodies quote the
   *  request back, so a naive passthrough of `message` can carry a header or an
   *  argument; and a `redirect_url` is a single-use credential in URL form —
   *  the whole point of `anticipy.ai/c/{token}` is that the vendor's tokenised
   *  link is never written down anywhere, a log line included.
   *
   *  The key's length guard matters: `split("").join(x)` inserts the
   *  replacement between every character, so an empty key would turn a short
   *  message into a wall of "[redacted]". */
  #safe(text: unknown): string {
    let out = String(text ?? "");
    if (this.#apiKey.length >= 8) out = out.split(this.#apiKey).join("[redacted]");
    out = out.replace(URL_SHAPED, "[redacted-url]");
    return out.slice(0, 200);
  }

  /** A short machine token from a vendor error, or "".
   *
   *  Only `code`/`slug`-shaped values survive: no whitespace, at most 64
   *  characters, and nothing URL-shaped. The vendor's prose `message` is
   *  dropped on purpose — it is the field that quotes our request back at us.
   *  This is a REDACTION rule; nothing in this file branches on the token, it
   *  exists so a human reading two failures can tell them apart. */
  #errorToken(body: unknown): string {
    const root = asRecord(body);
    const err = asRecord(root?.error) ?? root;
    for (const key of ["code", "slug", "error_code", "type"]) {
      const token = asString(err?.[key]);
      if (token && token.length <= 64 && !/\s/.test(token) && !token.includes("://")) {
        return this.#safe(token);
      }
    }
    return "";
  }

  // -------------------------------------------------------------------------
  // Transport
  // -------------------------------------------------------------------------
  /** One HTTP call. No retries live here.
   *
   *  `authorize()` retries a dead session once, at its own call site, because
   *  minting a link changes nothing in the world. `disconnect()` deliberately
   *  never retries: revoke and delete both act on a real credential and the
   *  endpoint takes no idempotency key. */
  async #call(
    op: string,
    method: string,
    path: string,
    body?: unknown,
  ): Promise<{ status: number; ok: boolean; json: unknown }> {
    // THE UNBOUND-BINDING GATE. Before the URL is built and before any fetch:
    // with `env.COMPOSIO_API_KEY` unset this Worker issues no request at all,
    // and the caller gets a named failure rather than a 401 from the vendor or,
    // worse, an empty connections list.
    if (!this.#apiKey) throw new ConnectionsUnconfigured(op);
    if (typeof this.#fetch !== "function") {
      throw new ConnectionsRequestFailed(op, 0, "no fetch implementation available");
    }
    let res: Response;
    try {
      res = await this.#fetch(`${this.#baseUrl}${path}`, {
        method,
        headers: {
          // The ONLY place the key is written. It is never logged, never put in
          // an error, and never returned to a caller.
          "x-api-key": this.#apiKey,
          "content-type": "application/json",
          accept: "application/json",
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      // The vendor's name only. A fetch rejection's cause chain can hold the
      // whole request, key header included.
      throw new ConnectionsRequestFailed(
        op,
        0,
        this.#safe((cause as Error)?.name ?? "transport failure"),
      );
    }
    const status = Number((res as { status?: unknown })?.status ?? 0);
    let json: unknown = null;
    try {
      json = typeof (res as { json?: unknown }).json === "function" ? await res.json() : null;
    } catch {
      // A body that is not JSON must not cost us the status: a 502 from a load
      // balancer arrives as HTML and still has to be reported as a 502.
      json = null;
    }
    return { status, ok: status >= 200 && status < 300, json };
  }

  async #callOrThrow(op: string, method: string, path: string, body?: unknown): Promise<unknown> {
    const { status, ok, json } = await this.#call(op, method, path, body);
    if (!ok) throw new ConnectionsRequestFailed(op, status, this.#errorToken(json));
    return json;
  }

  // -------------------------------------------------------------------------
  // session
  // -------------------------------------------------------------------------
  async session(user: OwnerId): Promise<{ sessionId: string }> {
    const owner = requireOwner("session", user);
    return { sessionId: await this.#sessionId(owner) };
  }

  async #sessionId(owner: OwnerId): Promise<string> {
    const cached = this.#sessions.get(owner);
    if (cached) return cached;
    const pending = this.#inFlight.get(owner);
    if (pending) return pending;

    const create = (async () => {
      const json = await this.#callOrThrow("session", "POST", "/tool_router/session", {
        // The whole point of the session. Composio scopes connected accounts,
        // and therefore which credentials can run, to this value. The wrong one
        // here is one person's mailbox serving everybody.
        user_id: owner,
        // THE INPUT KEY IS `enable`. Measured 2026-09-05: `{"enabled": false}`
        // is a 400 ("Unrecognized key(s)") and a bare `false` is a 400
        // ("Expected object, received boolean"). The config that comes BACK
        // spells it `enabled`, which is exactly how the first version of this
        // was written with the tool still switched on.
        manage_connections: { enable: false },
      });
      const root = asRecord(json);
      const id = asString(root?.session_id);
      if (!id) throw new ConnectionsResponseShape("session", "no session_id in the response");

      // Checked BEFORE caching, so a refused session is never reused and the
      // next call gets a clean attempt rather than the poisoned one.
      this.#assertManageConnectionsOff(root as Record<string, unknown>);

      const claimed = this.#sessionOwners.get(id);
      if (claimed !== undefined && claimed !== owner) {
        throw new ConnectionsOwnerMismatch(
          "session",
          "the vendor returned a session id already minted for a different owner — "
            + "two owners sharing one session is one person's accounts answering for another",
        );
      }
      this.#remember(owner, id);
      return id;
    })();

    this.#inFlight.set(owner, create);
    try {
      return await create;
    } finally {
      this.#inFlight.delete(owner);
    }
  }

  /** Cache one owner's session, keeping the isolate's memory bounded.
   *
   *  A Worker isolate can live for hours and serve every owner on the account,
   *  and the spike's maps had no ceiling because the spike was a script that
   *  exited. Past `MAX_CACHED_SESSIONS` both maps are dropped whole: the only
   *  cost is a re-mint on the next call, and the wrong-person guards do not
   *  live here — they are on the wire, in `#assertManageConnectionsOff` and in
   *  `connections()`. The reverse index is a tripwire on the VENDOR handing one
   *  session to two owners; a cleared cache narrows the window it watches, and
   *  a shared session would still be caught by the `user_id` scoping on every
   *  request made inside it. */
  #remember(owner: OwnerId, sessionId: string): void {
    if (this.#sessions.size >= MAX_CACHED_SESSIONS) {
      this.#sessions.clear();
      this.#sessionOwners.clear();
    }
    this.#sessions.set(owner, sessionId);
    this.#sessionOwners.set(sessionId, owner);
  }

  /** Prove the connection meta-tool is off, from the vendor's own answer.
   *
   *  Two independent confirmations, because they fail differently: `config`
   *  echoes what the vendor THINKS we asked for, and `tool_router_tools` is what
   *  the model will actually be handed. Either one saying the tool is live is a
   *  refusal.
   *
   *  Neither being readable is ALSO a refusal, and that direction is chosen
   *  deliberately. This is a floor — "does anything confirm the tool is off?" —
   *  and a floor that lifts itself when nobody answers is a decoration. The cost
   *  of getting it wrong is not symmetric: refusing is a loud outage on the
   *  connect path that we fix in an afternoon, while waving through leaves the
   *  model holding a tool that texts people raw vendor links, and nothing
   *  anywhere would report it. */
  #assertManageConnectionsOff(root: Record<string, unknown>): void {
    const config = asRecord(root.config);
    const manage = asRecord(config?.manage_connections);
    const enabled = typeof manage?.enabled === "boolean"
      ? manage.enabled
      : typeof manage?.enable === "boolean"
        ? manage.enable
        : null;

    const tools = toolIdentifiers(root.tool_router_tools);
    const managePresent = tools === null ? null : tools.includes(MANAGE_CONNECTIONS_TOOL);

    if (enabled === true) {
      throw new ConnectionsManageConnectionsOn(
        "the session config came back with manage_connections enabled",
      );
    }
    if (managePresent === true) {
      throw new ConnectionsManageConnectionsOn(
        `${MANAGE_CONNECTIONS_TOOL} is still in the session's tool list`,
      );
    }
    if (enabled === null && managePresent === null) {
      throw new ConnectionsResponseShape(
        "session",
        "neither config.manage_connections nor tool_router_tools could be read, so nothing "
          + "confirms the connection tool is off",
      );
    }
  }

  /** Forget a session so the next call mints a fresh one. The reverse index is
   *  cleared too, or a re-minted id would collide with its own owner's ghost. */
  #forgetSession(owner: OwnerId): void {
    const id = this.#sessions.get(owner);
    if (id !== undefined) this.#sessionOwners.delete(id);
    this.#sessions.delete(owner);
  }

  // -------------------------------------------------------------------------
  // authorize
  // -------------------------------------------------------------------------
  /** The vendor's connect URL, minted at REDEEM time.
   *
   *  Never at send time. Composio's own links expire in ten minutes; four were
   *  generated ahead of time on 2026-09-05 and all four were dead before anyone
   *  tapped them. `anticipy.ai/c/{token}` is what goes in the text, and this is
   *  what that page calls when the token is redeemed. */
  async authorize(
    user: OwnerId,
    toolkit: Toolkit,
    opts: { callbackUrl: string; alias?: AccountAlias | null },
  ): Promise<{ redirectUrl: string }> {
    const owner = requireOwner("authorize", user);
    const slug = requireToolkit("authorize", toolkit);
    const callbackUrl = requireCallbackUrl("authorize", opts?.callbackUrl);
    const alias = opts?.alias === null || opts?.alias === undefined
      ? null
      : readAlias(opts.alias);
    if (opts?.alias !== null && opts?.alias !== undefined && alias === null) {
      // A mislabelled account is the "which of my two Gmails is this" failure
      // the alias exists to prevent, and it is invisible until the wrong
      // mailbox answers.
      throw new ConnectionsBadArgument(
        "authorize",
        'alias must be "work" or "personal" when it is given at all',
      );
    }

    const body: Record<string, unknown> = {
      toolkit: slug,
      // Documented on the v3.1 session link endpoint but NOT among the fields
      // measured on 2026-09-05. It is sent because Composio publishes no
      // success webhook — only `expired` — so the callback is the only moment
      // the product learns a connection happened.
      callback_url: callbackUrl,
    };
    if (alias !== null) body.alias = alias;

    for (let attempt = 0; ; attempt++) {
      const sessionId = await this.#sessionId(owner);
      const { status, ok, json } = await this.#call(
        "authorize",
        "POST",
        `/tool_router/session/${encodeURIComponent(sessionId)}/link`,
        body,
      );
      if (status === 404 && attempt === 0) {
        // The session died between minting and this tap. Retrying is safe HERE
        // and nowhere else in this file: generating a link creates nothing in
        // the world, and the alternative is a person standing on our connect
        // page watching it fail for a reason they cannot act on.
        this.#forgetSession(owner);
        continue;
      }
      if (!ok) throw new ConnectionsRequestFailed("authorize", status, this.#errorToken(json));

      const url = asString(asRecord(json)?.redirect_url);
      if (!url) {
        // Deliberately says nothing about the body. The one field we wanted is
        // the field we must never write down.
        throw new ConnectionsResponseShape("authorize", "no redirect_url in the response");
      }
      return { redirectUrl: url };
    }
  }

  // -------------------------------------------------------------------------
  // connections
  // -------------------------------------------------------------------------
  async connections(user: OwnerId): Promise<Connection[]> {
    const owner = requireOwner("connections", user);
    const json = await this.#callOrThrow(
      "connections",
      "GET",
      `/connected_accounts?user_ids=${encodeURIComponent(owner)}`,
    );

    const root = asRecord(json);
    const items = Array.isArray(json)
      ? json
      : Array.isArray(root?.items)
        ? (root.items as unknown[])
        : null;
    if (items === null) {
      throw new ConnectionsResponseShape("connections", "no items array in the response");
    }

    const out: Connection[] = [];
    let unreadable = 0;
    for (const entry of items) {
      const item = asRecord(entry);
      if (!item) {
        unreadable++;
        continue;
      }

      // THE WRONG-PERSON GUARD, and the reason it refuses rather than filters.
      // The query is scoped by `user_ids`, so an account for anybody else means
      // the scoping did not hold. Dropping the stray row quietly would leave us
      // returning the rest as though the response were trustworthy; stamping
      // OUR owner id over the vendor's would launder a stranger's mailbox into
      // this owner's connections table under the right name, which is exactly
      // the failure this contract's `OwnerId` type was created for.
      //
      // It fails CLOSED in both non-answers. It used to check only a bare
      // non-empty string under `user_id`/`user_ids`, so an array — the plural
      // the request itself sends — a camelCase key, a nested `user.id`, a
      // number or an empty string all read as "the vendor did not say", the
      // check was skipped, and the stray row was adopted. `disconnect()` then
      // used that laundered list as its ownership proof for two endpoints with
      // no user scoping, and deleting a stranger's connection returns 200.
      const echo = readOwnerEcho(item, owner);
      if (echo === "foreign") {
        throw new ConnectionsOwnerMismatch(
          "connections",
          "the vendor returned an account bound to a different user_id than the one queried",
        );
      }
      if (echo !== "ours") {
        // A shape refusal rather than a mismatch: we are not claiming this row
        // belongs to somebody else, only that nothing in it says it is ours.
        // If this ever fires against the live endpoint, the fix is to read the
        // field the vendor actually sends — never to let an unowned row
        // through, because nothing downstream can tell the difference.
        throw new ConnectionsResponseShape(
          "connections",
          echo === "absent"
            ? "a connected account named no owner at all, so nothing in the response ties it "
              + "to the owner that was queried"
            : "a connected account named an owner that could not be read as the one queried "
              + `(owner fields present: ${ownerEchoFields(item)})`,
        );
      }

      // Read as a STRING at every step. `item.toolkit` is an object in the
      // measured shape, and letting it fall through to `String(...)` would
      // stamp "[object object]" into the connections table as a toolkit slug —
      // a row that matches no catalog entry and no nudge, forever.
      const slug = toolkitSlug(
        asString(asRecord(item.toolkit)?.slug)
          ?? asString(item.toolkit_slug)
          ?? asString(item.toolkit)
          ?? "",
      );
      const accountId = asString(item.id) ?? asString(item.connected_account_id);
      if (slug.length === 0 || accountId === null) {
        unreadable++;
        continue;
      }

      out.push({
        // OUR validated owner, not an echo. Every row this method emits is
        // about the owner that was asked for, or the call has already thrown.
        user_id: owner,
        toolkit: slug,
        connected_account_id: accountId,
        alias: readAlias(item.alias ?? item.label),
        status: mapConnectionStatus(item.status),
        // FALSE, ALWAYS, AND NOT A PLACEHOLDER. `writes_enabled` is the
        // Settings toggle "let Anticipy make changes" and it lives in D1, not
        // at the vendor — Composio has no idea whether this person opted in.
        // The Two Hands ladder cannot reach rung 3 without it, so a provider
        // that guessed `true` here would let an API hand send mail on behalf of
        // somebody who never agreed to it. A caller merging these rows with the
        // stored ones must take the STORED value for this field and never this
        // one.
        writes_enabled: false,
        last_used_at: readLastUsedAt(item.last_used_at),
      });
    }

    if (unreadable > 0) {
      // Not skipped in silence. "You have not connected Notion" is the claim
      // that sends somebody a connect text about the app they connected
      // yesterday, and it is far too consequential to make out of a field we
      // could not read.
      throw new ConnectionsResponseShape(
        "connections",
        `${unreadable} of ${items.length} connected accounts had no readable id or toolkit`,
      );
    }
    return out;
  }

  // -------------------------------------------------------------------------
  // disconnect — REVOKE, THEN DELETE.
  // -------------------------------------------------------------------------
  /** Delete alone leaves the token live at Google while the product told the
   *  person their access was revoked. So revoke first, delete second, and say
   *  honestly which of the two actually happened.
   *
   *  The ownership check in front of both is not ceremony: `/{id}/revoke` and
   *  `DELETE /{id}` take an account id and NO user scoping whatsoever, so a
   *  caller holding the wrong id — a stale row, a mixed-up loop, a text command
   *  resolved against another owner — would delete a stranger's connection and
   *  get a 200 for it. This method is the only place that can make those two
   *  endpoints owner-scoped. */
  async disconnect(user: OwnerId, connectedAccountId: string): Promise<DisconnectResult> {
    const owner = requireOwner("disconnect", user);
    const accountId = requireAccountId("disconnect", connectedAccountId);

    const owned = await this.connections(owner);
    if (!owned.some((c) => c.connected_account_id === accountId)) {
      throw new ConnectionsOwnerMismatch(
        "disconnect",
        `connected account ${JSON.stringify(accountId)} is not one of this owner's accounts`,
      );
    }

    const revoke = await this.#call(
      "disconnect revoke",
      "POST",
      `/connected_accounts/${encodeURIComponent(accountId)}/revoke`,
    );

    let revoked = false;
    let revokeUnavailable = false;
    if (revoke.ok) {
      revoked = true;
    } else if (revokeIsDefinitivelyUnavailable(revoke.status)) {
      // 409 is the measured shape: the account is not in a revocable state.
      // About 5% of connections cannot be revoked programmatically at all, and
      // the contract's answer is to say so rather than claim a revoke that did
      // not happen.
      revokeUnavailable = true;
    } else {
      // Retryable, our own credential, our own request, or a status nobody has
      // measured. STOP — do not delete. The delete destroys the account id, and
      // that id is the only handle we will ever have for revoking this token.
      // Failing now leaves a person still connected, which they can retry;
      // deleting now leaves a live token at Google that nobody can ever reach
      // again — and the copy for `revokeUnavailable` would have sent them off
      // to clear settings for a failure that was ours.
      throw new ConnectionsRequestFailed(
        "disconnect revoke",
        revoke.status,
        this.#errorToken(revoke.json),
      );
    }

    const del = await this.#call(
      "disconnect delete",
      "DELETE",
      `/connected_accounts/${encodeURIComponent(accountId)}`,
    );
    // A 404 means the row is already gone, which is the state delete was for.
    const deleted = del.ok || del.status === 404;

    if (!deleted) {
      if (revoked) {
        // The dangerous half succeeded: the token is dead at the provider and
        // only the vendor's bookkeeping row survives. Throwing here would tell
        // the caller the disconnect failed, and the copy for that would tell a
        // person their access is still live when it is not. Report it instead.
        return { revoked: true, deleted: false, revokeUnavailable: false };
      }
      throw new ConnectionsRequestFailed(
        "disconnect delete",
        del.status,
        this.#errorToken(del.json),
      );
    }
    return { revoked, deleted: true, revokeUnavailable };
  }

  // -------------------------------------------------------------------------
  // toolkit
  // -------------------------------------------------------------------------
  /** Name, logo, description, app URL and scopes — everything the connect page
   *  renders. NO APP IS HARDCODED anywhere in this product: a new toolkit in
   *  the catalog is a new app in Anticipy with zero code, and the only way that
   *  is true is if the page is built from this. */
  async toolkit(slug: Toolkit): Promise<ToolkitMeta> {
    const asked = requireToolkit("toolkit", slug);
    // NOT among the endpoints measured on 2026-09-05. Every field below is read
    // defensively for that reason, and a missing name refuses rather than
    // falling back.
    const json = await this.#callOrThrow(
      "toolkit",
      "GET",
      `/toolkits/${encodeURIComponent(asked)}`,
    );
    const root = asRecord(json);
    if (!root) throw new ConnectionsResponseShape("toolkit", "response was not an object");

    const out = readToolkitMeta(root, asked);
    if (out === null) {
      // Refusing beats defaulting to the slug. "Connect your googlecalendar" is
      // the sentence a slug fallback ships, in the register the spec spends a
      // page forbidding, and it would look like a copy decision rather than a
      // broken fetch.
      throw new ConnectionsResponseShape(
        "toolkit",
        `no name for ${JSON.stringify(asked)}; the connect page has nothing to call this app`,
      );
    }
    return out;
  }

  // -------------------------------------------------------------------------
  // search — THE ONLY WAY TO ADD AN APP NOBODY ASKED ABOUT
  // -------------------------------------------------------------------------
  /**
   * The whole catalog, searched with the letters somebody typed.
   *
   * ── LAW 1 IS THE WHOLE DESIGN OF THIS METHOD ─────────────────────────────
   *
   * The typed phrase is percent-encoded into the query string and handed to the
   * VENDOR. That is the only thing done to it. There is no local filter, no
   * local ranking, no did-you-mean, no synonym table and no list of app names
   * anywhere in this file — which is why `?q=` could not simply be pointed at
   * `toolkit(slug)`: treating a phrase a person typed as a vendor primary key
   * would be this adapter deciding what their words MEANT, and getting it wrong
   * silently, with "nothing matched" as the alibi.
   *
   * What comes back is returned in THE ORDER THE VENDOR GAVE. Re-sorting is the
   * same violation with a numeric face on it: whichever row we promoted would be
   * our opinion about which app they meant, formed with no context at all.
   *
   * ── AN EMPTY LIST IS AN ANSWER, AND ONLY WHEN THE VENDOR GAVE IT ─────────
   *
   * `items: []` from the vendor means "nothing in the catalog matches those
   * letters", which the search box renders honestly. Every other outcome —
   * no key, a dead network, a non-2xx, a body with no `items` array, a page of
   * rows none of which can be read — THROWS, so the route answers 503 and the
   * screen says it could not reach us. The one thing this must never do is
   * return `[]` because something went wrong: that tells a person the catalog
   * holds nothing, and the catalog holds 1,400 apps.
   *
   * Capped at `MAX_SEARCH_RESULTS` on both halves: it is sent as the vendor's
   * own `limit`, AND the answer is cut to it whatever arrives.
   *
   * ── NO OWNER, AND THAT IS NOT AN OVERSIGHT ───────────────────────────────
   *
   * Every other public method here re-validates an owner row id at runtime
   * because it reaches a credential of one particular person's. The catalog is
   * the vendor's global list of what CAN be connected; it names nobody, returns
   * nothing about anybody's accounts, and is identical for every owner. Adding
   * an owner argument would put a value on the wire that this endpoint has no
   * meaning for, and would teach the next reader that the owner check is
   * ceremony rather than the thing standing between a display name and somebody
   * else's mailbox. The route is still behind the signed-in gate and its own
   * per-owner budget.
   *
   * ENDPOINT MEASURED LIVE 2026-09-06 — path, both parameters, the envelope and
   * the row shape, plus the no-match and blank answers this method's branches
   * are built on. The measurements are in this file's header. Every field is
   * still read defensively, because a shape that held on one afternoon is not a
   * contract.
   */
  async search(query: string, opts?: { limit?: number }): Promise<ToolkitMeta[]> {
    const wanted = Number(opts?.limit ?? MAX_SEARCH_RESULTS);
    // A CEILING, not a default: `MAX_SEARCH_RESULTS` is the most any caller can
    // ask for, and an unusable number falls back to it rather than reaching the
    // vendor as `limit=NaN`.
    const limit = Number.isFinite(wanted) && wanted >= 1
      ? Math.min(MAX_SEARCH_RESULTS, Math.trunc(wanted))
      : MAX_SEARCH_RESULTS;

    const json = await this.#callOrThrow(
      "catalog search",
      "GET",
      `/toolkits?search=${encodeURIComponent(query)}&limit=${limit}`,
    );

    const root = asRecord(json);
    const items = Array.isArray(json)
      ? json
      : Array.isArray(root?.items)
        ? (root.items as unknown[])
        : null;
    if (items === null) {
      // NOT an empty list. "We could not read the answer" and "the catalog holds
      // nothing that matches" are different sentences on a person's screen.
      throw new ConnectionsResponseShape("catalog search", "no items array in the response");
    }

    const out: ToolkitMeta[] = [];
    let unreadable = 0;
    for (const entry of items) {
      const row = asRecord(entry);
      const meta = row === null ? null : readToolkitMeta(row, null);
      if (meta === null) unreadable++;
      else out.push(meta);
    }

    // ONE unreadable row among readable ones is dropped in silence, and that is
    // the opposite of what `connections()` does with an unreadable row — on
    // purpose. There, a dropped row becomes "you have not connected Notion" and
    // texts somebody about the app they connected last week. Here, a dropped row
    // is one line missing from a list of forty, and refusing the whole search
    // over it would break the search box every time the vendor ships a
    // half-populated entry.
    //
    // ALL of them unreadable is the different thing, and it refuses: a page of
    // rows we cannot parse is a shape change or an outage, and returning `[]`
    // for it would say the catalog has nothing matching those letters.
    if (out.length === 0 && unreadable > 0) {
      throw new ConnectionsResponseShape(
        "catalog search",
        `${unreadable} of ${items.length} catalog rows could not be read, so nothing here is `
          + "an answer about what the catalog holds",
      );
    }

    // The vendor's order, cut to the cap. Never re-sorted.
    return out.slice(0, limit);
  }
}

// ---------------------------------------------------------------------------
// THE WORKER SEAM
// ---------------------------------------------------------------------------

/** The isolate's one provider, so the owner→session cache is worth having.
 *
 *  A Worker handler is called per request; constructing a new adapter each time
 *  would throw the session cache away every request and mint a fresh session
 *  per tap — which is not only slower, it is how one owner ends up with a link
 *  minted in a session the next screen cannot see. Keyed by the key itself so a
 *  rotated secret replaces the instance instead of serving the old one for the
 *  life of the isolate; exactly one entry is ever held. */
let isolateProvider: { key: string; provider: ComposioConnections } | null = null;

/**
 * The adapter for a request's `env`.
 *
 * With `COMPOSIO_API_KEY` unbound this still returns a working object, and
 * every method on it throws `ConnectionsUnconfigured` without issuing a
 * request — deliberately, because the alternatives are worse than an error: a
 * provider that is `null` makes every call site invent its own fallback, and a
 * provider that returns `[]` tells the nudge engine this owner has connected
 * nothing, which is the claim that texts somebody about the app they connected
 * last week.
 *
 * No base-URL override is read from `env`. The version is pinned in the path
 * because the `manage_connections` guard reads `tool_router_tools` by name;
 * tests inject a `baseUrl` through the constructor instead, so no deployed
 * variable can point this adapter at another host.
 */
export function connectionsFromEnv(env: ConnectionsEnv | null | undefined): ComposioConnections {
  const key = typeof env?.COMPOSIO_API_KEY === "string" ? env.COMPOSIO_API_KEY.trim() : "";
  if (isolateProvider !== null && isolateProvider.key === key) return isolateProvider.provider;
  const provider = new ComposioConnections({ apiKey: key });
  isolateProvider = { key, provider };
  return provider;
}

/** Drop the isolate's cached provider. For tests, and for a caller that has
 *  just rotated the secret and wants the next request to start clean. */
export function resetConnectionsProvider(): void {
  isolateProvider = null;
}
