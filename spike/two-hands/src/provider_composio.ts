// ---------------------------------------------------------------------------
// THE COMPOSIO ADAPTER — the API hand's one vendor, behind `Provider`.
// ---------------------------------------------------------------------------
// Composio is called over plain HTTP through an injected `fetchImpl`, and the
// SDK is deliberately not installed. Three vendors in this space changed shape
// inside a year (Pipedream acquired, Klavis pivoted, Browser Use retired Skills
// with a 410); an SDK pins us to their release cadence and hides the wire from
// the tests, and the wire is the only part of this we actually have to get
// right. Zero dependencies also means every test in this spike runs on a laptop
// with no account, no key and no network.
//
// The endpoints are the v3.1 Tool Router session API, because that is the only
// surface with the runtime tool SEARCH we chose Composio for. A session is
// created per user_id and everything else hangs off it:
//
//   POST /tool_router/session                       -> { session_id }
//   POST /tool_router/session/{id}/search           -> tool slugs + schemas
//   POST /tool_router/session/{id}/execute          -> { data, error, log_id }
//   POST /tool_router/session/{id}/link             -> { redirect_url }
//   GET  /connected_accounts?user_ids=...           -> connected accounts
//
// WHAT THIS FILE MAY NOT DO, and the reason it is the first thing written down:
// nothing here decides whether a tool is the right tool. The vendor's retrieval
// ORDERS candidates and this adapter carries that order through untouched; the
// only thing that may put a step on the API hand is a MatchJudge verdict of
// exactly "yes" (see the LAW1 block at the bottom of contract.ts). There is no
// score threshold in this file, and there is no list of app names or verbs that
// decides a routing outcome.

import type {
  CapabilitySignature,
  ConnectedApp,
  ExecErrorKind,
  ExecResult,
  Provider,
  SideEffect,
  ToolCandidate,
} from "./contract.ts";

/** v3.1 is the version whose Tool Router carries the search meta-tool. Pinned
 *  in the path, not floating: a silent bump to a version with a renamed
 *  `tool_schemas` key would surface here as "no tools exist", which reads to
 *  the router as "use the browser" and to us as a quiet, permanent regression. */
export const COMPOSIO_BASE_URL = "https://backend.composio.dev/api/v3.1";

/** The vendor's own cap on the search query field. Truncating here rather than
 *  letting the API 400 keeps a long `expected_effect` from turning every search
 *  for a wordy step into a hard failure. */
const USE_CASE_MAX = 1024;
const KNOWN_FIELDS_MAX = 500;

const DEFAULT_RETRY_DELAY_MS = 500;
/** A 429 with `Retry-After: 3600` is the vendor telling us to come back in an
 *  hour. Sleeping that long inside a step the owner is waiting on is worse than
 *  failing over to the browser hand immediately, so the honoured wait is
 *  capped and anything longer becomes a fast, honest failure. */
const MAX_RETRY_DELAY_MS = 5_000;

// ---------------------------------------------------------------------------
// Named failures. A spike that returns zeros because nobody set a key is worse
// than one that refuses, so every refusal below has a name and a `code` a gate
// can assert on.
// ---------------------------------------------------------------------------

/** No API key. Thrown rather than swallowed: `search()` returns an array, and
 *  an empty array is indistinguishable from "this owner has no tools" — which
 *  is exactly how a misconfigured spike reports a week of zeros as a finding. */
export class ComposioUnconfigured extends Error {
  constructor(op: string) {
    super(`composio ${op} refused: no API key was given to ComposioProvider`);
    this.name = "ComposioUnconfigured";
    this.code = "composio_no_api_key";
  }
}

/** The vendor answered, and the answer was a failure. Carries the HTTP status
 *  and the mapped kind so a caller does not have to re-derive either. */
export class ComposioRequestFailed extends Error {
  constructor(op: string, status: number, kind: ExecErrorKind, detail: string) {
    super(`composio ${op} failed (HTTP ${status}, ${kind})${detail ? `: ${detail}` : ""}`);
    this.name = "ComposioRequestFailed";
    this.code = "composio_request_failed";
    this.status = status;
    this.kind = kind;
  }
}

/** The vendor answered with a shape we cannot read. This exists so a renamed
 *  field can never be reported as an empty result: "0 candidates" is a claim
 *  about the owner's account, and we are only allowed to make it when we
 *  actually understood the response. */
export class ComposioResponseShape extends Error {
  constructor(op: string, detail: string) {
    super(`composio ${op} returned an unreadable shape: ${detail}`);
    this.name = "ComposioResponseShape";
    this.code = "composio_response_shape";
  }
}

// ---------------------------------------------------------------------------
// Small structural readers. These parse JSON the vendor sent; none of them
// reads natural language to decide anything.
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
function asFiniteNumber(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Does this body carry a vendor error?
 *
 *  Composio spells it two ways — a bare string, and an object with
 *  `message`/`code`/`status`. Checking only for a string let every STRUCTURED
 *  failure through as a success: on `execute` that meant a send that never
 *  happened climbing a capability's rung, and on `search` it meant a vendor
 *  outage reported as "this owner has no API for this step". Both are silent
 *  and both are permanent, so the two call sites share one reader. */
function bodyErrorPresent(raw: unknown): boolean {
  return typeof raw === "string" ? raw.length > 0 : asRecord(raw) !== null;
}

/** ONE canonical spelling for an app, everywhere.
 *
 *  Composio spells the same toolkit `"gmail"` in `connected_accounts`,
 *  `"GMAIL"` inside a tool slug, and sometimes `"Gmail"` in a label. The ledger
 *  keys `capability_stats`, `api_candidates` and `connect_nudges` by `app`; two
 *  spellings means one app climbing two separate rungs, so shadow mode never
 *  ends and the owner is nudged to connect something she connected last week.
 *  Every `app` this file emits, and every comparison it makes, goes through
 *  here first. */
export function toolkitSlug(raw: unknown): string {
  return String(raw ?? "").trim().toLowerCase();
}

/** The toolkit half of a Composio tool slug (`GMAIL_SEND_EMAIL` -> `gmail`).
 *  Splitting a structured identifier on its delimiter is plumbing, the same
 *  kind of thing as pulling a host out of a URL — it is not reading meaning out
 *  of prose, and it is only ever a fallback for when the vendor omits the
 *  `toolkit` field it normally sends. */
function toolkitFromSlug(slug: string): string {
  const cut = slug.indexOf("_");
  return toolkitSlug(cut > 0 ? slug.slice(0, cut) : slug);
}

// ---------------------------------------------------------------------------
// Error-kind mapping — by STATUS CODE, never by reading the vendor's prose.
// ---------------------------------------------------------------------------
/** Why status only: the router turns `auth` into a re-auth nudge to the owner
 *  and `schema` into a re-plan of the arguments. Guessing which one from the
 *  words in an error message means the day Composio rewords "invalid grant" the
 *  owner stops being asked to reconnect and the API hand fails forever in
 *  silence. A status code is a contract; an error sentence is copy.
 *
 *  400/422 are the argument-shape statuses and are the only ones called
 *  `schema`. 404 and 409 are NOT: a missing tool slug or a conflicting resource
 *  is not the caller's argument shape, and telling the router to re-plan
 *  arguments that were already correct spends a model call to produce the same
 *  request twice. */
export function execErrorKindForStatus(status: number): ExecErrorKind {
  if (status === 401 || status === 403) return "auth";
  if (status === 429) return "rate";
  if (status === 400 || status === 422) return "schema";
  return "other";
}

// ---------------------------------------------------------------------------
// Premium tools — the spend seatbelt, not a meaning judgement.
// ---------------------------------------------------------------------------
/** Composio bills some toolkits at the provider's cost plus 5% (browser
 *  automation lands near $0.70 a run). The whole promise of the second hand is
 *  that it is cheaper and faster than driving Chrome; an API hand that quietly
 *  routes through a billed-per-run tool has replaced the browser with a more
 *  expensive browser and nobody finds out until the invoice.
 *
 *  This is a check on what a step SPENDS, which is the seatbelt's own shape
 *  (does this send, pay, delete?), and it is deliberately NOT a check on what a
 *  step means. In particular there is no substring search of `description` for
 *  words like "browser" or "search": that would be a word list over natural
 *  language deciding a routing outcome, which is the exact thing this spike
 *  exists to avoid building.
 *
 *  Three states, because "the vendor says this is free", "the vendor says this
 *  is billed" and "the vendor said nothing" are three different facts:
 *    true  — the vendor declared it premium, or declared a positive per-call
 *            price, or the owner's configured `premiumToolkits` names it.
 *    false — the vendor explicitly declared it not premium.
 *    null  — nobody declared anything.
 *
 *  UNKNOWN IS KEPT, and that is the hole in this guard. Composio documents no
 *  premium flag on the tool object at all (checked 2026-09-05), so on the live
 *  API today every candidate is `null` and the only thing actually excluding
 *  anything is the caller's configured slug set. Failing closed instead —
 *  dropping every unknown — would drop every tool Composio has and leave the
 *  API hand permanently unreachable, which is a guard that guards nothing by
 *  being infinitely strict. The real fix is a live check of the search response
 *  against a known premium toolkit, and it is not done. */
export function premiumVerdict(
  meta: Record<string, unknown> | null,
  toolkit: string,
  configuredPremium: ReadonlySet<string>,
): boolean | null {
  if (configuredPremium.has(toolkit)) return true;
  if (!meta) return null;

  for (const key of ["premium", "is_premium"]) {
    if (typeof meta[key] === "boolean") return meta[key] as boolean;
  }
  // A declared per-call price is the vendor saying "billed per run" in numbers.
  // Read as a number, never as text, so a price string is treated as an absent
  // declaration rather than as a truthy value that excludes a free tool.
  const pricing = asRecord(meta.pricing) ?? asRecord(meta.billing);
  for (const source of [meta, pricing]) {
    if (!source) continue;
    for (const key of ["cost_usd", "price_usd", "per_call_usd"]) {
      const n = asFiniteNumber(source[key]);
      if (n !== null) return n > 0;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Connected-account status — a vendor enum, mapped fail-closed.
// ---------------------------------------------------------------------------
/** The contract carries three states and Composio has more (`INITIATED`,
 *  `FAILED`, `INACTIVE`, ...). Anything that is not explicitly ACTIVE or
 *  EXPIRED is reported as `revoked`, because the cost of the two mistakes is
 *  not symmetric: calling a dead account `active` routes a step to a hand with
 *  no credential and surfaces to the owner as the task failing, while calling a
 *  half-finished account `revoked` costs one connect nudge. */
export function mapConnectionStatus(raw: unknown): ConnectedApp["status"] {
  const token = String(raw ?? "").trim().toUpperCase();
  if (token === "ACTIVE") return "active";
  if (token === "EXPIRED") return "expired";
  return "revoked";
}

// ---------------------------------------------------------------------------
// The search query — built from the signature, without the owner's data.
// ---------------------------------------------------------------------------
/** The signature's `verb`, `object` and `expected_effect` describe the step
 *  without naming a hand, which is exactly what a retrieval query wants.
 *
 *  `app_hint` is NOT here and must never be: the contract calls it advisory and
 *  bars it from being a routing key, and scoping the vendor's search to the
 *  planner's guessed app would make it one — the planner's hunch would decide
 *  which tools are allowed to exist, and a wrong hunch would look identical to
 *  "no API exists for this". */
export function searchUseCase(sig: CapabilitySignature): string {
  const parts = [sig.verb, sig.object, sig.expected_effect]
    .map((p) => String(p ?? "").trim())
    .filter((p) => p.length > 0);
  return parts.join(" — ").slice(0, USE_CASE_MAX);
}

/** Input KEY NAMES only, sorted.
 *
 *  Two reasons, and the first one is privacy: `inputs` holds the owner's actual
 *  data — the recipient, the subject line, the amount. Retrieval does not need
 *  any of it, so shipping it to a vendor's search endpoint is a leak bought for
 *  nothing. The second is stability: unsorted keys make the same step produce a
 *  different query on every run, which moves results around for reasons that
 *  have nothing to do with the step. `signature_hash` excludes input values for
 *  the same reason, so this keeps the query and the hash looking at the same
 *  thing. */
export function searchKnownFields(sig: CapabilitySignature): string {
  const keys = Object.keys(sig.inputs ?? {}).sort();
  return keys.join(", ").slice(0, KNOWN_FIELDS_MAX);
}

// ---------------------------------------------------------------------------

const defaultSleep = (ms: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, ms));

function retryAfterMs(res: unknown, fallbackMs: number, capMs: number): number {
  const headers = (res as { headers?: { get?: (k: string) => string | null } })?.headers;
  const raw = typeof headers?.get === "function" ? headers.get("retry-after") : null;
  const seconds = raw === null || raw === undefined ? NaN : Number(raw);
  if (!Number.isFinite(seconds) || seconds < 0) return fallbackMs;
  return Math.min(seconds * 1000, capMs);
}

export interface ComposioOptions {
  apiKey?: string | null;
  baseUrl?: string;
  fetchImpl?: typeof globalThis.fetch;
  /** Off by default. Turning it on is the caller accepting a per-run bill. */
  allowPremium?: boolean;
  /** Toolkit slugs the owner knows are billed per run. Configuration, not code:
   *  the day Composio changes its price list this is one call-site edit, and no
   *  list of vendor names is baked into the adapter where nobody would think to
   *  look for it. */
  premiumToolkits?: Iterable<string>;
  retryDelayMs?: number;
  maxRetryDelayMs?: number;
  sleepImpl?: (ms: number) => Promise<void>;
  /** Monotonic clock for `execute()`'s duration. `performance.now()` by default
   *  rather than `Date.now()`: an NTP step during a slow call can make wall
   *  clock run backwards, and a negative `ms` poisons the ledger's p50/p95 for
   *  that capability forever. */
  clock?: () => number;
}

export class ComposioProvider implements Provider {
  #apiKey: string;
  #baseUrl: string;
  #fetch: typeof globalThis.fetch | undefined;
  #allowPremium: boolean;
  #premiumToolkits: Set<string>;
  #retryDelayMs: number;
  #maxRetryDelayMs: number;
  #sleep: (ms: number) => Promise<void>;
  #clock: () => number;
  /** userId -> session id, and userId -> the in-flight creation of one. The
   *  second map is not belt-and-braces: two steps for one owner starting at the
   *  same moment would otherwise mint two sessions, and a connect link minted
   *  in session A is a connection the execute issued against session B cannot
   *  see — the owner authorises Gmail and the very next step still says she has
   *  not connected it. */
  #sessions: Map<string, string>;
  #sessionsInFlight: Map<string, Promise<string>>;

  constructor(opts: ComposioOptions = {}) {
    this.name = "composio";
    // Trimmed because a key pasted out of a dashboard arrives with a newline,
    // and a header value with a newline is rejected by fetch as an invalid
    // header rather than as a bad key — an error nobody reads as "your key has
    // whitespace in it".
    this.#apiKey = typeof opts.apiKey === "string" ? opts.apiKey.trim() : "";
    this.#baseUrl = String(opts.baseUrl ?? COMPOSIO_BASE_URL).replace(/\/+$/, "");
    const impl = opts.fetchImpl ?? globalThis.fetch;
    // Bound to globalThis: an unbound `fetch` throws "Illegal invocation" the
    // first time it is called as a bare function in some runtimes, and that
    // failure would arrive at the router looking like a dead vendor.
    this.#fetch = typeof impl === "function"
      ? (opts.fetchImpl ? impl : impl.bind(globalThis))
      : undefined;
    this.#allowPremium = opts.allowPremium === true;
    this.#premiumToolkits = new Set(
      [...(opts.premiumToolkits ?? [])].map((t) => toolkitSlug(t)),
    );
    this.#retryDelayMs = asFiniteNumber(opts.retryDelayMs) ?? DEFAULT_RETRY_DELAY_MS;
    this.#maxRetryDelayMs = asFiniteNumber(opts.maxRetryDelayMs) ?? MAX_RETRY_DELAY_MS;
    this.#sleep = opts.sleepImpl ?? defaultSleep;
    this.#clock = opts.clock ?? (() => performance.now());
    this.#sessions = new Map();
    this.#sessionsInFlight = new Map();
    // Deliberately NOT thrown on a missing key. The router constructs providers
    // eagerly at startup; throwing here would take down the browser hand too,
    // and the browser hand is the one that still works without a Composio
    // account. Every method refuses by name instead.
  }

  /** Redact anything the vendor echoes back.
   *
   *  Composio error bodies quote the request, so a naive `message` passthrough
   *  puts the owner's email body into a log line. Nothing derived from a
   *  response ever reaches a message without going through here, and the key is
   *  scrubbed as a second line of defence in case a future edit ever puts a URL
   *  or a header into an error. The length guard matters: `replaceAll("")`
   *  inserts the replacement between every character, so an empty key would
   *  turn a short message into a wall of "[redacted]". */
  #safe(text: unknown): string {
    let out = String(text ?? "");
    if (this.#apiKey.length >= 8) out = out.split(this.#apiKey).join("[redacted]");
    return out.slice(0, 200);
  }

  /** A short machine token from a vendor error, or "".
   *
   *  Only `code`/`slug`-shaped values survive: no whitespace, at most 64
   *  characters. That is a redaction rule, not a classification rule — nothing
   *  branches on the token, it is only there so a human reading
   *  `last_fail_reason` can tell two failures apart. The vendor's prose
   *  `message` is deliberately dropped, because it is the field that quotes the
   *  owner's arguments back at us. */
  #errorToken(body: unknown): string {
    const root = asRecord(body);
    const err = asRecord(root?.error) ?? root;
    for (const key of ["code", "slug", "error_code", "type"]) {
      const token = asString(err?.[key]);
      if (token && token.length <= 64 && !/\s/.test(token)) return this.#safe(token);
    }
    return "";
  }

  /** One HTTP call, with the ONLY retry in this file.
   *
   *  429 retries exactly once. Nothing else retries, and that is the whole
   *  design rather than an omission: `execute()` writes to the owner's real
   *  accounts and Composio's execute endpoint takes no idempotency key, so a
   *  retried 500 on a send is a second email — the request that timed out may
   *  well have landed. 429 is the one status that is a promise the request was
   *  NOT executed, which is what makes it the one status safe to repeat. A 401
   *  is not retried either: the credential will not have healed in 500ms, and
   *  the router needs to see the auth failure to nudge the owner. */
  async #call(
    op: string,
    method: string,
    path: string,
    body?: unknown,
  ): Promise<{ status: number; ok: boolean; json: unknown }> {
    if (!this.#apiKey) throw new ComposioUnconfigured(op);
    if (typeof this.#fetch !== "function") {
      throw new ComposioRequestFailed(op, 0, "other", "no fetch implementation available");
    }
    const url = `${this.#baseUrl}${path}`;
    for (let attempt = 0; ; attempt++) {
      let res: Response;
      try {
        res = await this.#fetch(url, {
          method,
          headers: {
            // The vendor's project key header. This is the ONLY place the key
            // is ever written, and it is never logged, never put in an error,
            // and never returned to a caller.
            "x-api-key": this.#apiKey,
            "content-type": "application/json",
            accept: "application/json",
          },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
      } catch (cause) {
        // A transport failure carries the vendor's name only. The cause chain
        // of a fetch rejection can hold the full request, key header included.
        throw new ComposioRequestFailed(
          op, 0, "other", this.#safe((cause as Error)?.name ?? "transport failure"),
        );
      }
      const status = Number((res as { status?: unknown })?.status ?? 0);
      if (status === 429 && attempt === 0) {
        await this.#sleep(retryAfterMs(res, this.#retryDelayMs, this.#maxRetryDelayMs));
        continue;
      }
      let json: unknown = null;
      try {
        json = typeof (res as { json?: unknown }).json === "function" ? await res.json() : null;
      } catch {
        // A body that is not JSON is not a reason to lose the status; a 502 from
        // a load balancer arrives as HTML and still has to map to `other`.
        json = null;
      }
      return { status, ok: status >= 200 && status < 300, json };
    }
  }

  /** Throwing wrapper for the three methods whose return type cannot carry an
   *  error. `execute()` does not use this: it maps failures into ExecResult. */
  async #callOrThrow(op: string, method: string, path: string, body?: unknown): Promise<unknown> {
    const { status, ok, json } = await this.#call(op, method, path, body);
    if (!ok) {
      throw new ComposioRequestFailed(op, status, execErrorKindForStatus(status), this.#errorToken(json));
    }
    return json;
  }

  async #session(userId: string): Promise<string> {
    const cached = this.#sessions.get(userId);
    if (cached) return cached;
    const pending = this.#sessionsInFlight.get(userId);
    if (pending) return pending;

    const create = (async () => {
      // `user_id` is the whole point of the session: Composio scopes connected
      // accounts, and therefore which tools can actually run, to it. Sending
      // the wrong one executes a step against a different person's mailbox.
      const json = await this.#callOrThrow("session", "POST", "/tool_router/session", {
        user_id: userId,
      });
      const id = asString(asRecord(json)?.session_id);
      if (!id) {
        throw new ComposioResponseShape("session", "no session_id in the response");
      }
      this.#sessions.set(userId, id);
      return id;
    })();

    this.#sessionsInFlight.set(userId, create);
    try {
      return await create;
    } finally {
      this.#sessionsInFlight.delete(userId);
    }
  }

  /** Forget a session so the NEXT call mints a fresh one.
   *
   *  Note what this deliberately does not do: it does not re-issue the call
   *  that just failed. A 404 on a session-scoped execute probably means the
   *  session expired before the tool ran — but "probably" is not good enough
   *  when the tool sends money or email, and the vendor gives us no idempotency
   *  key to make the second attempt safe. One failed step that the owner can
   *  retry beats a duplicate she cannot undo. */
  #forgetSession(userId: string): void {
    this.#sessions.delete(userId);
  }

  // -------------------------------------------------------------------------
  // search
  // -------------------------------------------------------------------------
  async search(
    sig: CapabilitySignature,
    userId: string,
    opts: { connectedOnly: boolean; limit: number },
  ): Promise<ToolCandidate[]> {
    const limit = Math.max(0, Math.floor(asFiniteNumber(opts?.limit) ?? 0));
    if (limit === 0) return [];

    const sessionId = await this.#session(userId);
    let json: unknown;
    try {
      json = await this.#callOrThrow(
        "search",
        "POST",
        `/tool_router/session/${encodeURIComponent(sessionId)}/search`,
        {
          queries: [{ use_case: searchUseCase(sig), known_fields: searchKnownFields(sig) }],
        },
      );
    } catch (err) {
      if ((err as { status?: number })?.status === 404) this.#forgetSession(userId);
      throw err;
    }

    const root = asRecord(json);
    if (!root) throw new ComposioResponseShape("search", "response was not an object");
    // A body-level failure on an HTTP 200. Without this the vendor saying
    // "search is down" would be read as "this owner has no API for this step",
    // and the router would record a browser fallback as if it were a fact about
    // the owner's account rather than about the vendor's afternoon.
    if (root.success === false || bodyErrorPresent(root.error)) {
      throw new ComposioRequestFailed("search", 200, "other", this.#errorToken(root));
    }

    const schemas = asRecord(root.tool_schemas) ?? {};

    // THE VENDOR'S ORDER, PRESERVED. `primary_tool_slugs` before
    // `related_tool_slugs`, results in the order they came back, duplicates
    // dropped on first sight. This ordering is the entire contribution
    // retrieval is allowed to make to the outcome.
    const ordered: string[] = [];
    const seen = new Set<string>();
    for (const result of asArray(root.results)) {
      const r = asRecord(result);
      if (!r) continue;
      for (const key of ["primary_tool_slugs", "related_tool_slugs"]) {
        for (const raw of asArray(r[key])) {
          const slug = asString(raw);
          if (slug && !seen.has(slug)) {
            seen.add(slug);
            ordered.push(slug);
          }
        }
      }
    }
    if (ordered.length === 0) return [];

    const candidates: ToolCandidate[] = [];
    for (const slug of ordered) {
      const meta = asRecord(schemas[slug]);
      // A candidate with no schema is not a candidate: the caller cannot build
      // arguments for it, so offering it only produces a 400 later.
      if (!meta) continue;

      const toolkit = toolkitSlug(asString(meta.toolkit) ?? toolkitFromSlug(slug));
      const premium = premiumVerdict(meta, toolkit, this.#premiumToolkits);
      if (premium === true && !this.#allowPremium) continue;

      candidates.push({
        toolSlug: slug,
        app: toolkit,
        // THE SCORE. Carried through untouched when the vendor sends one. When
        // it sends only an ordering — which is what the v3.1 search response
        // actually returns — the position becomes a NEGATIVE number: 0, -1, -2.
        // Descending sort still reproduces the vendor's order exactly, and the
        // number cannot be mistaken for a confidence by a future reader looking
        // for something to compare against 0.75. That mistake is the one the
        // contract's LAW1 block was written to prevent, and a plausible-looking
        // 0.93 in this field is how it would get made.
        // The zero case is spelled out rather than written `-candidates.length`,
        // which produces -0: `Object.is(-0, 0)` is false and deepStrictEqual
        // agrees, but JSON round-trips it to 0 — so a ledger row written from a
        // live run and the same row replayed from a fixture would compare
        // unequal for a reason nobody would ever find.
        score: asFiniteNumber(meta.score)
          ?? (candidates.length === 0 ? 0 : -candidates.length),
        sideEffectHint: sideEffectHintFrom(meta),
        schema: asRecord(meta.input_schema) ?? {},
        description: asString(meta.description) ?? "",
      });
    }

    // Every slug the vendor ranked had no schema entry. That is a response we
    // did not understand, not an owner with no tools, and reporting it as an
    // empty list is how a renamed field becomes a silent permanent zero.
    if (candidates.length === 0 && ordered.length > 0 && Object.keys(schemas).length === 0) {
      throw new ComposioResponseShape(
        "search",
        `${ordered.length} tool slugs ranked but tool_schemas was empty`,
      );
    }

    const scoped = opts?.connectedOnly
      ? await this.#connectedOnly(userId, root, candidates)
      : candidates;
    return scoped.slice(0, limit);
  }

  /** Keep only candidates whose toolkit the owner has actually connected.
   *
   *  The search response usually carries `toolkit_connection_statuses`, which
   *  is free and consistent with the search that produced the candidates. When
   *  it does not, we ask `connections()` rather than assuming: routing a step to
   *  an unconnected app produces a 401 the owner reads as the task failing, and
   *  the browser hand would have simply worked. If neither source can be read,
   *  `connections()` throws and this whole search fails loudly — the one thing
   *  that must not happen is a confident empty list. */
  async #connectedOnly(
    userId: string,
    searchRoot: Record<string, unknown>,
    candidates: ToolCandidate[],
  ): Promise<ToolCandidate[]> {
    const connected = new Set<string>();
    const statuses = searchRoot.toolkit_connection_statuses;
    if (Array.isArray(statuses)) {
      for (const entry of statuses) {
        const s = asRecord(entry);
        if (s?.has_active_connection === true) connected.add(toolkitSlug(s.toolkit));
      }
    } else {
      for (const app of await this.connections(userId)) {
        if (app.status === "active") connected.add(toolkitSlug(app.app));
      }
    }
    return candidates.filter((c) => connected.has(c.app));
  }

  // -------------------------------------------------------------------------
  // connections
  // -------------------------------------------------------------------------
  async connections(userId: string): Promise<ConnectedApp[]> {
    const json = await this.#callOrThrow(
      "connections",
      "GET",
      `/connected_accounts?user_ids=${encodeURIComponent(userId)}`,
    );
    const root = asRecord(json);
    // v3 wraps list responses in `items`; a bare array is accepted too. If it
    // is neither, that is a shape we did not understand — and "this owner has
    // connected nothing" is far too consequential a claim to make by accident,
    // since it is what triggers a connect nudge to a person who already
    // connected the app.
    const items = Array.isArray(json)
      ? json
      : Array.isArray(root?.items)
        ? (root.items as unknown[])
        : null;
    if (items === null) {
      throw new ComposioResponseShape("connections", "no items array in the response");
    }

    const out: ConnectedApp[] = [];
    for (const entry of items) {
      const item = asRecord(entry);
      if (!item) continue;
      const toolkit = asRecord(item.toolkit);
      const app = toolkitSlug(asString(toolkit?.slug) ?? item.toolkit ?? item.toolkit_slug);
      const accountId = asString(item.id) ?? asString(item.connected_account_id) ?? "";
      if (!app || !accountId) continue;
      const params = asRecord(item.params) ?? asRecord(item.state) ?? null;
      const scopes = [...asArray(item.scopes), ...asArray(params?.scopes)]
        .map((s) => asString(s))
        .filter((s): s is string => s !== null);
      out.push({
        app,
        accountId,
        // The owner's own words for this account when she gave one, so a person
        // with two Gmail accounts can tell the nudge apart from the noise.
        label: asString(item.alias) ?? asString(item.label) ?? app,
        scopes,
        status: mapConnectionStatus(item.status),
      });
    }
    return out;
  }

  // -------------------------------------------------------------------------
  // connectLink
  // -------------------------------------------------------------------------
  async connectLink(userId: string, app: string, scopes?: string[]): Promise<{ url: string }> {
    const sessionId = await this.#session(userId);
    // SCOPES ARE NOT SENT, and that is a gap rather than a decision we like.
    // The v3.1 session link endpoint documents `toolkit`, `alias`,
    // `callback_url` and `experimental` — no scopes field — because scopes live
    // on the auth config, not on the link. Inventing a body field to carry them
    // risks a 400 that breaks connecting entirely, which is worse than a
    // narrowing we did not get; but a caller passing scopes here IS getting
    // less than it asked for, and until the auth-config path is built this
    // adapter cannot honour a narrower request than the app's default.
    const json = await this.#callOrThrow(
      "connectLink",
      "POST",
      `/tool_router/session/${encodeURIComponent(sessionId)}/link`,
      { toolkit: toolkitSlug(app) },
    );
    const url = asString(asRecord(json)?.redirect_url);
    if (!url) {
      // The nudge text promises the owner a working link. Returning "" would
      // send her a message with a dead button in it.
      throw new ComposioResponseShape("connectLink", "no redirect_url in the response");
    }
    return { url };
  }

  // -------------------------------------------------------------------------
  // execute
  // -------------------------------------------------------------------------
  async execute(
    userId: string,
    toolSlug: string,
    args: Record<string, unknown>,
    accountId?: string,
  ): Promise<ExecResult> {
    // Started before the session call on purpose: session creation is latency
    // the owner waits through, and hiding it would make the API hand look
    // faster than it is in the very numbers the week-1 gate is judged on.
    const startedAt = this.#clock();
    const elapsed = (): number => Math.max(0, Math.round(this.#clock() - startedAt));

    try {
      const sessionId = await this.#session(userId);
      const { status, ok, json } = await this.#call(
        "execute",
        "POST",
        `/tool_router/session/${encodeURIComponent(sessionId)}/execute`,
        {
          tool_slug: toolSlug,
          arguments: args ?? {},
          ...(accountId ? { account: accountId } : {}),
        },
      );

      if (!ok) {
        if (status === 404) this.#forgetSession(userId);
        return {
          ok: false,
          error: {
            kind: execErrorKindForStatus(status),
            message: `composio execute failed (HTTP ${status})${
              this.#errorToken(json) ? `: ${this.#errorToken(json)}` : ""
            }`,
          },
          ms: elapsed(),
          ...costFrom(json),
        };
      }

      // A 200 whose body carries an error. Composio's execute endpoint answers
      // `{ data, error, log_id }` and puts the TOOL's own failure in `error`
      // while the HTTP call itself succeeded. Reading only the status here
      // would record a failed send as a success, and a rung that climbs on
      // failed sends is the worst possible outcome of this whole spike.
      const root = asRecord(json);
      if (bodyErrorPresent(root?.error)) {
        // The kind comes from a structured status inside the error when the
        // vendor sends one, and is `other` when it does not. It is never
        // guessed from the words: a mis-kinded auth failure costs the owner a
        // re-auth nudge she never gets, and inventing one from prose is how
        // that starts happening silently after a vendor copy edit.
        const inner = asRecord(root?.error);
        const innerStatus = asFiniteNumber(inner?.status) ?? asFiniteNumber(root?.status);
        return {
          ok: false,
          error: {
            kind: innerStatus === null ? "other" : execErrorKindForStatus(innerStatus),
            message: `composio execute reported a tool failure${
              this.#errorToken(root) ? `: ${this.#errorToken(root)}` : ""
            }`,
          },
          ms: elapsed(),
          ...costFrom(json),
        };
      }

      return { ok: true, data: root?.data ?? null, ms: elapsed(), ...costFrom(json) };
    } catch (err) {
      // A missing key is `other`, NOT `auth`. `auth` makes the router nudge the
      // owner to reconnect her Gmail because WE forgot to set a server key —
      // she does the work, nothing changes, and she learns the product blames
      // her for its own configuration.
      const kind = err instanceof ComposioUnconfigured
        ? "other"
        : ((err as { kind?: ExecErrorKind })?.kind ?? "other");
      return {
        ok: false,
        error: { kind, message: this.#safe((err as Error)?.message ?? "composio execute failed") },
        ms: elapsed(),
      };
    }
  }
}

/** MCP-style annotations, read only in the direction that makes a step
 *  stricter or leaves it alone.
 *
 *  `destructiveHint` is honoured as `irreversible` and `readOnlyHint` as
 *  `read`; the absence of `readOnlyHint` is NEVER read as "write", because a
 *  tool that declares nothing has declared nothing. Emitting `read` at all is
 *  only safe because `tightenSideEffect` in the contract can ratchet up and
 *  never down — the MCP spec says these annotations are untrusted, so a tool
 *  calling itself read-only must not be able to turn a planned write into a
 *  read and slip past the confirmation gate. */
function sideEffectHintFrom(meta: Record<string, unknown>): SideEffect | undefined {
  const ann = asRecord(meta.annotations) ?? meta;
  if (ann.destructiveHint === true) return "irreversible";
  if (ann.readOnlyHint === true) return "read";
  return undefined;
}

/** The vendor's declared cost for this run, or nothing at all.
 *
 *  OMITTED rather than defaulted to 0. Composio documents no per-execution cost
 *  field (checked 2026-09-05), so on the live API today this is almost always
 *  absent — and writing 0 into the ledger's `cost_usd_total` would tell the
 *  router the API hand is free, which is exactly the claim the premium guard
 *  above exists to stop us making. An absent cost is an unknown cost. */
function costFrom(json: unknown): { costUsd?: number } {
  const root = asRecord(json);
  const usage = asRecord(root?.usage);
  for (const source of [root, usage]) {
    if (!source) continue;
    for (const key of ["cost_usd", "cost", "total_cost_usd"]) {
      const n = asFiniteNumber(source[key]);
      if (n !== null) return { costUsd: n };
    }
  }
  return {};
}
