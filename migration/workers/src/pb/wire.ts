/**
 * src/pb/wire.ts — PocketBase's response shapes, reproduced byte-for-byte.
 *
 * These are not internal conveniences. They are the contract five shipped
 * clients parse. Every shape here is pinned to the code that reads it:
 *
 *   {items, totalItems, …}   clients/ios/Anticipy/Backend/AnticipyBackend.swift:340,548,580,634,681
 *   {token, record}          clients/ios/.../AnticipyBackend.swift:468-478
 *   {items}                  extension/background.js:372, 526, 690, 987
 *                            brain/pb.py (every call), brain/worker.py:134…
 *   404 body                 migration/spec/CONTRACT.md §0.5
 */

/** PocketBase list envelope. migration/spec/CONTRACT.md:126. */
export interface ListResponse<T = Record<string, unknown>> {
  page: number;
  perPage: number;
  totalItems: number;
  totalPages: number;
  items: T[];
}

export const json = (status: number, body: unknown, extra?: HeadersInit): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

/**
 * PocketBase's 404. The iPhone distinguishes it from a 403 in at least one
 * place (SettingsView.swift:270-284, "that code didn't match" vs "I can't
 * reach Anticipy"), so the body shape is load-bearing, not decoration.
 */
export const notFound = (): Response =>
  json(404, { code: 404, message: "The requested resource wasn't found.", data: {} });

/** PocketBase's 400 for a malformed filter/sort. */
export const badRequest = (message: string, data: Record<string, unknown> = {}): Response =>
  json(400, { code: 400, message, data });

/** guard.pb.js and friends answer with a bare {error} object, not PB's shape. */
export const refuse = (status: number, error: string, detail?: string): Response =>
  json(status, detail === undefined ? { error } : { error, detail });

/** GET /api/health. CONTRACT.md §0.5. The runbooks' liveness probe. */
export const health = (): Response =>
  json(200, { code: 200, message: "API is healthy.", data: {} });

// ---------------------------------------------------------------------------
// Record ids
// ---------------------------------------------------------------------------

/**
 * PocketBase mints a 15-character lowercase-alphanumeric id.
 * evidence.pb.js:83 calls it "the collection's 15-character ID" for the
 * collection case; record ids share the alphabet and length.
 *
 * crypto.getRandomValues is used rather than Math.random because these ids are
 * guessed at in the wild: guard.pb.js:203-220 exists because "somebody
 * guessing ids" reached the anonymous surface.
 */
const ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";

export function newRecordId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(15));
  let out = "";
  for (const b of bytes) out += ID_ALPHABET[b % ID_ALPHABET.length];
  return out;
}

// ---------------------------------------------------------------------------
// Dates
// ---------------------------------------------------------------------------

/**
 * PocketBase's autodate wire format: "YYYY-MM-DD HH:MM:SS.sssZ".
 *
 * A SPACE, not a 'T'. Always UTC. Always three millisecond digits. This is NOT
 * ISO-8601 and `new Date(x)` parses it inconsistently across engines —
 * migration/d1/schema.sql:88-95 says so and the schema keeps the two formats
 * apart on purpose. Several TEXT columns hold real ISO-8601 instead because a
 * client wrote them (events.spoken_at, segments.started_at,
 * password_resets.expires, every internal_* timestamp) and MUST NOT be
 * normalised — schema.sql:121-130.
 *
 * Use this ONLY for `created`/`updated` and for PocketBase `date` fields.
 */
export function pbNow(at: Date = new Date()): string {
  return at.toISOString().replace("T", " ").replace(/Z$/, "Z");
}

/**
 * The tolerant reader. internal_hq.pb.js:2144-2150 (`pbTime`) does exactly
 * this, for exactly this reason: the tree holds both formats and a parse that
 * returns NaN silently becomes "the far future" in every `until > Date.now()`
 * test (workflow_guard.pb.js:160-161, guard.pb.js:318-320, evidence.pb.js:125-129
 * all warn about it).
 */
export function pbTime(v: unknown): number {
  if (!v) return NaN;
  let t = String(v).trim().replace(" ", "T");
  if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(t)) t += "Z";
  return new Date(t).getTime();
}

/**
 * Fail-closed deadline test. `NaN > Date.now()` is false, which is the correct
 * direction — but only because it is written this way round. `!(until <= now)`
 * would let an unparseable date through as the far future.
 */
export const stillInTheFuture = (v: unknown, now = Date.now()): boolean => pbTime(v) > now;

// ---------------------------------------------------------------------------
// Row <-> record
// ---------------------------------------------------------------------------

/**
 * Columns PocketBase never returns over REST, so neither may we.
 * migration/d1/schema.sql:437-443 records this independently
 * (`import_d1.py:214-216` reached the same list): they exist only inside
 * /pb_data/data.db.
 *
 * `agents.agent_token` is on this list and IS the browser's credential. A
 * single accidental serialisation hands anyone reading a job list the ability
 * to impersonate every paired Chrome install.
 */
export const HIDDEN_COLUMNS: Readonly<Record<string, readonly string[]>> = {
  owners: ["password", "tokenKey"],
  agents: ["agent_token"],
  internal_people: ["code_hash", "password_hash"],
  internal_sessions: ["token_hash"],
  internal_passwords: ["secret_enc", "secret_gcm"],
  password_resets: ["code_hash"],
};

/** Columns that are INTEGER 0/1 in D1 and `true`/`false` on the wire. */
export type BoolColumns = Readonly<Record<string, readonly string[]>>;

/**
 * D1 row -> PocketBase record JSON.
 *
 * Two conversions and one deletion, and all three are wrong-answer bugs if
 * skipped:
 *   1. bool  INTEGER 0/1 -> JSON true/false. `rec.paired` is read as a boolean
 *      by extension/background.js:357 and by guard.pb.js:441.
 *   2. number REAL -> JSON number (already correct; kept explicit so a future
 *      NUMERIC affinity change is visible here).
 *   3. hidden columns removed.
 */
export function rowToRecord(
  collection: string,
  row: Record<string, unknown>,
  boolColumns: readonly string[],
): Record<string, unknown> {
  const hidden = HIDDEN_COLUMNS[collection] ?? [];
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(row)) {
    if (hidden.includes(k)) continue;
    out[k] = boolColumns.includes(k) ? Boolean(v) : v;
  }
  // PocketBase stamps every record with its collection. Clients do not read
  // these two today, but the Admin-UI-shaped tooling in the runbooks does.
  out.collectionName = collection;
  return out;
}
