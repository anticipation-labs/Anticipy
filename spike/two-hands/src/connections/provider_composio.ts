// ---------------------------------------------------------------------------
// THE COMPOSIO ADAPTER BEHIND `ConnectionProvider` — ONE OWNER AT A TIME.
// ---------------------------------------------------------------------------
// Everything in this file exists to make ONE failure impossible: a connection
// bound to the wrong person. During the spike an operator's own Gmail and
// Calendar were connected by hand with `user_id: "omar"`, which is one
// mailbox serving everybody; it had to be revoked and deleted. So the shape of
// this adapter is not "call Composio", it is "call Composio for exactly this
// owner row id, and refuse rather than guess":
//
//   * every public method starts by re-validating the owner id AT RUNTIME,
//     because `OwnerId` is a TypeScript brand and this repo runs with
//     `--experimental-strip-types` — the brand is gone before the code runs, so
//     the only thing standing between a display name and a Composio session is
//     the check below;
//   * the session cache is keyed by owner and carries a REVERSE index, so a
//     session id handed to two owners is a refusal, not a shared mailbox;
//   * `connections()` refuses a response carrying somebody else's `user_id`
//     rather than stamping ours over it;
//   * `disconnect()` proves the account belongs to this owner BEFORE touching
//     it, because the vendor's revoke and delete endpoints take an account id
//     and no user scoping at all — an unscoped id in an unscoped endpoint is a
//     delete of a stranger's connection.
//
// Zero dependencies and an injected `fetchImpl`: the SDK would hide the wire,
// and the wire is the part that has already been wrong once (see
// `manage_connections` below). Every test in this spike runs with no key, no
// account and no network.
//
// ENDPOINTS, measured live 2026-09-05 against api v3.1:
//   POST   /tool_router/session                      -> 201 {session_id, mcp,
//                                                       config, tool_router_tools}
//   POST   /tool_router/session/{sid}/link           -> {redirect_url}
//   GET    /connected_accounts?user_ids={owner}      -> {items:[…]}
//   POST   /connected_accounts/{id}/revoke           -> 200 ACTIVE / 409 not
//   DELETE /connected_accounts/{id}                  -> 200
// `GET /toolkits/{slug}` is the one endpoint here that was NOT measured that
// day; `toolkit()` says so at its call site and refuses an unreadable answer
// rather than inventing a name.
//
// WHAT THIS FILE MAY NOT DO. It contains no app names, no permission copy and
// no phrasing. Which toolkit a person meant is a model's question (contract's
// `ToolkitJudge`); what the connect page says is generated from the metadata
// this file fetches (contract's `PermissionWords`). Nothing here reads natural
// language to decide an outcome — the only string comparisons below are
// against vendor ENUMS and vendor TOOL IDENTIFIERS, which is the same kind of
// plumbing as reading an HTTP status.

import {
  ownerId,
  type AccountAlias,
  type Connection,
  type ConnectionProvider,
  type DisconnectResult,
  type OwnerId,
  type Toolkit,
  type ToolkitMeta,
} from "./contract.ts";

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

// ---------------------------------------------------------------------------
// NAMED FAILURES. A method that returns an empty list because nobody set a key
// is worse than one that refuses: "this owner has connected nothing" is the
// claim that triggers a connect nudge to somebody who connected last week.
// ---------------------------------------------------------------------------

/** No API key. Thrown by every method, including `disconnect()` — whose return
 *  type could carry `{revoked:false, deleted:false}` but must not, because that
 *  shape reads to a caller as "we tried and the provider could not", and the
 *  confirmation copy for it tells the owner their access was removed. */
export class ConnectionsUnconfigured extends Error {
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
  constructor(op: string, detail: string) {
    super(`connections ${op} returned an unreadable shape: ${detail}`);
    this.name = "ConnectionsResponseShape";
    this.code = "connections_response_shape";
  }
}

/** A required argument that is not the owner id was blank or unusable. */
export class ConnectionsBadArgument extends Error {
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
 *  because that flag drives copy shown to a human: "access was removed here,
 *  you may need to clear it in the app's own settings".
 *
 *  401/403 are excluded on purpose. They mean OUR key is wrong, not that THEIR
 *  account resists revoking — telling somebody to go clean up Google's settings
 *  because we misconfigured a header is a lie about their own security. */
export function revokeIsDefinitivelyUnavailable(status: number): boolean {
  if (status === 401 || status === 403) return false;
  return !isRetryableStatus(status);
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

/** Re-validate an owner id at runtime.
 *
 *  `OwnerId` is erased before this code runs. Without this call the branded
 *  type is a comment, and `session("omar")` type-checks in any caller that has
 *  a stray `as OwnerId` in it. */
export function requireOwner(op: string, raw: unknown): OwnerId {
  const seen = raw === null || raw === undefined ? "" : String(raw).trim();
  try {
    return ownerId(seen);
  } catch {
    throw new ConnectionsOwnerRequired(
      op,
      seen.length === 0 ? "blank" : `not an owner row id (${seen.length} characters)`,
    );
  }
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
 *  Upper-cased for an EXACT identifier comparison, never a substring search. */
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
    if (!record) continue;
    const named = asString(record.name) ?? asString(record.slug) ?? asString(record.tool_slug);
    if (named) out.push(named.trim().toUpperCase());
  }
  return out;
}

/** Scopes, gathered from every place the toolkit response is known to put them.
 *
 *  Best-effort and documented as such, because `GET /toolkits/{slug}` was not
 *  among the endpoints measured on 2026-09-05. An empty array therefore means
 *  "the vendor told us nothing", NOT "this app asks for nothing" — and the
 *  permission sentences must treat it that way. Rendering "Anticipy will be
 *  able to:" followed by nothing, on a page whose next tap is a Google consent
 *  screen asking for permission to delete all mail, is the worst copy this
 *  product could ship. */
function readScopes(root: Record<string, unknown>): string[] {
  const meta = asRecord(root.meta);
  const found: string[] = [];
  const seen = new Set<string>();
  const take = (v: unknown): void => {
    for (const raw of asArray(v)) {
      const scope = asString(raw);
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
  }
  return found;
}

// ---------------------------------------------------------------------------

export interface ComposioConnectionsOptions {
  apiKey?: string | null;
  baseUrl?: string;
  /** Always injected in tests. Defaults to `globalThis.fetch`, which is why
   *  there is no network anywhere in this spike's suite. */
  fetchImpl?: typeof globalThis.fetch;
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
    out = out.replace(/\b(?:https?|wss?):\/\/\S+/gi, "[redacted-url]");
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
      this.#sessions.set(owner, id);
      this.#sessionOwners.set(id, owner);
      return id;
    })();

    this.#inFlight.set(owner, create);
    try {
      return await create;
    } finally {
      this.#inFlight.delete(owner);
    }
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
      const echoed = asString(item.user_id) ?? asString(item.user_ids);
      if (echoed !== null && echoed.trim() !== owner) {
        throw new ConnectionsOwnerMismatch(
          "connections",
          "the vendor returned an account bound to a different user_id than the one queried",
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
      // Retryable, or our own credential. STOP — do not delete. The delete
      // destroys the account id, and that id is the only handle we will ever
      // have for revoking this token. Failing now leaves a person still
      // connected, which they can retry; deleting now leaves a live token at
      // Google that nobody can ever reach again.
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
    const meta = asRecord(root.meta);

    const name = asString(root.name) ?? asString(meta?.name);
    if (!name) {
      // Refusing beats defaulting to the slug. "Connect your googlecalendar" is
      // the sentence a slug fallback ships, in the register the spec spends a
      // page forbidding, and it would look like a copy decision rather than a
      // broken fetch.
      throw new ConnectionsResponseShape(
        "toolkit",
        `no name for ${JSON.stringify(asked)}; the connect page has nothing to call this app`,
      );
    }

    return {
      // The vendor's own spelling when it gives one: `connections()` returns
      // canonical slugs in `toolkit.slug`, so taking the canonical form here is
      // what keeps the connect page and the row it later produces on the same
      // key.
      slug: toolkitSlug(asString(root.slug) ?? asked),
      name,
      logo: asString(root.logo) ?? asString(meta?.logo) ?? null,
      description: asString(root.description) ?? asString(meta?.description) ?? null,
      appUrl: asString(root.app_url) ?? asString(meta?.app_url) ?? asString(root.appUrl) ?? null,
      scopes: readScopes(root),
    };
  }
}
