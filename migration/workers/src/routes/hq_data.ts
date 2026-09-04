/**
 * HQ's auth spine -- internal_hq.pb.js, CONTRACT.md §7.
 *
 * hq.ts is the door: health, CORS, the retired 410s, the page. This is what a
 * person actually signs in THROUGH, and what every data route resolves its
 * actor with. Ported from internal_hq.pb.js, which
 * research/2026-09-04-hq-hook-IS-production.md established is the file
 * production is running (35/35 unauthenticated routes conform, error strings
 * verbatim), so this is a port from the real source and not from a guess.
 *
 * WHAT IS PROVEN AND WHAT IS NOT, stated here because a commit message stops
 * being read: the UNAUTHENTICATED behaviour of everything below is checked
 * against live production by TestHQGateSurfaceWithoutTheKey. The AUTHENTICATED
 * behaviour is NOT -- ANTICIPY_INTERNAL_KEY is not available to this machine,
 * so no response body here has ever been diffed against production's. Under
 * law 3 that makes the signed-in half UNPROVEN, however carefully it was
 * ported. It is written down in STATUS.md as such.
 */
import { sha256Hex } from "../llm.ts";
import { newRecordId, pbNow } from "../pb/wire.ts";
import { hqCors, type HqEnv } from "./hq.ts";

const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

/** `$security.equal`. Length is not secret; the bytes are. */
export function timingEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

/**
 * PocketBase's `record.get("email_on") !== false` DOES NOT SURVIVE THE PORT
 * NAIVELY, and this is the trap the whole file is most likely to fall into.
 *
 * In the JSVM that field is a real boolean, so `false !== false` is false and
 * the person who switched email off gets `email_on: false`. In D1 the same
 * field is INTEGER 0 -- and `0 !== false` is TRUE in JavaScript. Transcribing
 * the idiom would silently flip every opt-OUT back to opt-IN, and the only
 * symptom would be email arriving for somebody who had turned it off.
 *
 * So: 0, false, "0", "false" are false; NULL and undefined keep the "defaults
 * to on" meaning the `!== false` idiom was written for.
 */
export function boolDefaultTrue(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (v === 0 || v === false || v === "0" || v === "false") return false;
  return true;
}

/** `!!record.get(...)` over a D1 integer. Defaults to OFF, unlike the above. */
export function boolDefaultFalse(v: unknown): boolean {
  return !(v === null || v === undefined || v === 0 || v === false
           || v === "0" || v === "false" || v === "");
}

/**
 * PocketBase stores datetimes as "YYYY-MM-DD HH:MM:SS.sssZ"; JS wants a T.
 * The source appends a Z when the stored value carries no zone, because a
 * bare local-looking string parses as LOCAL time and would expire sessions
 * hours early or late depending on where the server sits.
 */
export function parsePbTime(raw: unknown): number {
  let s = String(raw ?? "").trim().replace(" ", "T");
  if (!s) return NaN;
  if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(s)) s += "Z";
  return Date.parse(s);
}

export function randomHex(n: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(Math.ceil(n / 2)));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("").slice(0, n);
}

export interface Person { [k: string]: unknown; id: string }

/** The public shape of a person. Never code_hash, never pw_hash. */
export function personOut(p: Person, extra?: Record<string, unknown>) {
  return {
    id: p.id,
    name: String(p.name ?? ""),
    is_admin: boolDefaultFalse(p.is_admin),
    role: String(p.role ?? ""),
    focus: String(p.focus ?? ""),
    tz: String(p.tz ?? ""),
    remind_pref: String(p.remind_pref ?? "") || "inapp",
    email_on: boolDefaultTrue(p.email_on),
    sms_on: boolDefaultTrue(p.sms_on),
    ...(extra ?? {}),
  };
}

/**
 * DUAL AUTH, and the reason it is not "key only".
 *
 * Ari is handed an eight-character code and NOTHING else -- he never holds the
 * shared key -- so a key-only HQ means his first screen is a 401. The session
 * is therefore a first-class credential.
 *
 * A session that fails to resolve answers 401 {reauth:true} and NEVER falls
 * through to the key branch. The silent downgrade from "this is Ari" to
 * "whoever holds the key says they are Ari" is the attack: an expired token
 * must not quietly become an unauthenticated actor_id the caller chose.
 */
export type Actor =
  | { ok: true; person: Person; viaSession: boolean }
  | { ok: false; response: Response };

export async function resolveActor(
  req: Request, env: HqEnv, opts?: { actorId?: string },
): Promise<Actor> {
  const cors = hqCors(req, env);
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) {
    return { ok: false, response: json(503, { error: "internal HQ is not configured" }, cors) };
  }

  const tok = req.headers.get("X-HQ-Session") || "";
  if (tok) {
    const sess = await env.DB.prepare(
      "SELECT * FROM internal_sessions WHERE token_hash = ?1 LIMIT 1",
    ).bind(await sha256Hex(tok)).first<Record<string, unknown>>();
    if (sess) {
      const t = parsePbTime(sess.expires);
      if (!isNaN(t) && Date.now() < t) {
        const p = await env.DB.prepare(
          "SELECT * FROM internal_people WHERE id = ?1 LIMIT 1",
        ).bind(String(sess.person ?? "")).first<Person>();
        if (p && boolDefaultFalse(p.active)) {
          return { ok: true, person: p, viaSession: true };
        }
      }
    }
    // No fall-through. Expired, revoked, deactivated: all reauth.
    return { ok: false, response: json(401, { reauth: true }, cors) };
  }

  if (!timingEqual(req.headers.get("X-Internal-Key") || "", key)) {
    return { ok: false, response: json(401, { error: "wrong key" }, cors) };
  }

  const who = String(opts?.actorId ?? "");
  if (!who) {
    return { ok: false, response: json(400, { error: "pick yourself first" }, cors) };
  }
  const actor = await env.DB.prepare(
    "SELECT * FROM internal_people WHERE id = ?1 LIMIT 1",
  ).bind(who).first<Person>();
  if (!actor) {
    return { ok: false, response: json(400, { error: "pick yourself first" }, cors) };
  }
  if (!boolDefaultFalse(actor.active)) {
    return { ok: false, response: json(400, { error: "that person is deactivated" }, cors) };
  }
  return { ok: true, person: actor, viaSession: false };
}

/** One row in internal_activity. Best-effort: the log must never fail a write. */
export async function logActivity(
  env: HqEnv, actor: Person | null,
  action: string, subject: string, verb: string, ref: string,
): Promise<void> {
  try {
    await env.DB.prepare(
      // internal_activity has NO `updated` column -- it is append-only by
      // design, an entry is never edited. Checked against D1, not assumed.
      "INSERT INTO internal_activity (id, created, actor, actor_name, action, subject, verb, ref) "
      + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
    ).bind(newRecordId(), pbNow(), actor?.id ?? "",
           String(actor?.name ?? ""), action, subject, verb, ref).run();
  } catch { /* the log is not the transaction */ }
}

// ---------------------------------------------------------------------------
// POST /internal/session -- eight characters in, a thirty-day token out.
// ---------------------------------------------------------------------------
export async function hqSession(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  // 503 when the key is unset even though this route does not CHECK the key.
  // Stops a half-configured deploy leaving one door open in an area every
  // other door has shut. The area is shut or it is not.
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }

  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; } catch { /* {} */ }

  // ONE SENTENCE FOR EVERY FAILURE -- wrong code, revoked code, deactivated
  // person, tripped ceiling. Different messages would tell a stranger whether
  // a code exists, whether that person is still on the team, and whether they
  // are being rate limited: three facts they can only misuse.
  const no = () => json(200, {
    ok: false,
    message: "That code didn't match anyone. Check it and try again.",
  }, cors);

  // Crockford: case-insensitive, separators are decoration, and the four
  // ambiguous glyphs fold onto what they look like. Codes get read aloud and
  // typed by hand; without this, O-for-0 would be indistinguishable from a
  // revoked code and the identical-message rule above would become a trap
  // instead of a defence.
  const raw = String(body.code ?? "").toUpperCase().replace(/[^A-Z0-9]/g, "")
    .replace(/I/g, "1").replace(/L/g, "1").replace(/O/g, "0").replace(/U/g, "V");
  if (raw.length !== 8) return no();

  // GLOBAL HOURLY CEILING, COUNTED ON THE ATTEMPT, BEFORE THE COMPARISON.
  // Global rather than per-IP because an attacker rotates addresses and a
  // three-person team never reaches forty tries in an hour. Counted before the
  // compare so a miss costs exactly what a hit does.
  const hourNow = new Date().toISOString().slice(0, 13);
  const ceiling = parseInt(env.ANTICIPY_HQ_LOGIN_CEILING || "40", 10);
  try {
    let meter = await env.DB.prepare(
      "SELECT * FROM internal_meter WHERE name = 'login' LIMIT 1",
    ).first<Record<string, unknown>>();
    if (!meter) {
      // Seed rather than skip. A brute-force guard that silently stops
      // counting is worse than none, because everything downstream keeps
      // reporting that it is guarded.
      await env.DB.prepare(
        "INSERT INTO internal_meter (id, created, updated, name, hour, calls, live_job_id) "
        + "VALUES (?1,?2,?3,'login',?4,0,'')",
      ).bind(newRecordId(), pbNow(), pbNow(), hourNow).run();
      meter = { id: null, hour: hourNow, calls: 0 };
      meter = await env.DB.prepare(
        "SELECT * FROM internal_meter WHERE name = 'login' LIMIT 1",
      ).first<Record<string, unknown>>();
      if (!meter) return no();
    }
    const used = String(meter.hour ?? "") === hourNow ? Number(meter.calls ?? 0) || 0 : 0;
    if (used >= ceiling) return no();
    await env.DB.prepare(
      "UPDATE internal_meter SET hour = ?1, calls = ?2, updated = ?3 WHERE id = ?4",
    ).bind(hourNow, used + 1, pbNow(), String(meter.id ?? "")).run();
  } catch {
    return no();   // cannot count -> refuse. Fail closed.
  }

  // Look up BY HASH and compare timing-safely anyway. Storing only sha256
  // means a nightly backup is not a pile of live credentials, and there is
  // deliberately no route in this file that reads a code back out.
  const codeHash = await sha256Hex(raw);
  const person = await env.DB.prepare(
    "SELECT * FROM internal_people WHERE code_hash = ?1 LIMIT 1",
  ).bind(codeHash).first<Person>();
  if (!person) return no();
  if (!timingEqual(codeHash, String(person.code_hash ?? ""))) return no();
  if (!boolDefaultFalse(person.active)) return no();

  const token = randomHex(64);
  const nowISO = pbNow();
  const expires = pbNow(new Date(Date.now() + 30 * 86400000));
  const xff = String(req.headers.get("X-Forwarded-For") || "");
  const ip = (xff ? xff.split(",")[0].trim()
                  : String(req.headers.get("CF-Connecting-IP") || "")).slice(0, 60);
  try {
    await env.DB.prepare(
      "INSERT INTO internal_sessions (id, created, person, token_hash, expires, ip, ua) "
      + "VALUES (?1,?2,?3,?4,?5,?6,?7)",
    ).bind(newRecordId(), nowISO, person.id, await sha256Hex(token), expires, ip,
           String(req.headers.get("User-Agent") || "").slice(0, 200)).run();
  } catch {
    return no();
  }

  // Keep the last ten sign-ins per person. The collection doubles as "who has
  // been in lately"; ten answers that and stops it growing without bound the
  // way internal_activity once filled the volume.
  try {
    const old = await env.DB.prepare(
      "SELECT id FROM internal_sessions WHERE person = ?1 ORDER BY created DESC LIMIT 50 OFFSET 10",
    ).bind(person.id).all<{ id: string }>();
    for (const row of old.results ?? []) {
      await env.DB.prepare("DELETE FROM internal_sessions WHERE id = ?1").bind(row.id).run();
    }
  } catch { /* trimming is housekeeping, not the sign-in */ }

  const first = !String(person.last_in ?? "");
  try {
    await env.DB.prepare(
      "UPDATE internal_people SET last_in = ?1, updated = ?2 WHERE id = ?3",
    ).bind(nowISO, pbNow(), person.id).run();
  } catch { /* the sign-in already happened */ }

  await logActivity(env, person, "person.signin",
    String(person.name ?? "") + (first ? " signed in for the first time" : " signed in"),
    first ? "signed in for the first time" : "signed in", person.id);

  return json(200, {
    ok: true, token, expires,
    person: personOut(person),
  }, cors);
}

// ---------------------------------------------------------------------------
// POST /internal/session/end -- "Sign out". Deletes the row, not the code.
// ---------------------------------------------------------------------------
export async function hqSessionEnd(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  const tok = req.headers.get("X-HQ-Session") || "";
  if (!tok) return json(200, { ok: true }, cors);   // already signed out; say so plainly
  try {
    await env.DB.prepare("DELETE FROM internal_sessions WHERE token_hash = ?1")
      .bind(await sha256Hex(tok)).run();
  } catch { /* fall through */ }
  // Always 200. Whether that token existed is not a thing this route reports.
  return json(200, { ok: true }, cors);
}

// ---------------------------------------------------------------------------
// GET /internal/me -- who am I, and what are the team rules.
// ---------------------------------------------------------------------------
export async function hqMe(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const url = new URL(req.url);
  const actor = await resolveActor(req, env, { actorId: url.searchParams.get("actor_id") ?? "" });
  if (!actor.ok) return actor.response;
  const p = actor.person;

  const cfg: Record<string, string> = {
    team_name: "Anticipy", perm_assign: "everyone", perm_delete: "creator",
  };
  try {
    const rows = await env.DB.prepare(
      "SELECT key, value FROM internal_config ORDER BY key ASC LIMIT 20",
    ).all<{ key: string; value: string }>();
    for (const c of rows.results ?? []) {
      if (c.key === "team_name" || c.key === "perm_assign" || c.key === "perm_delete") {
        cfg[c.key] = String(c.value ?? "");
      }
    }
  } catch { /* defaults above are the contract */ }

  const key = env.ANTICIPY_INTERNAL_KEY || "";
  const host = env.ANTICIPY_PUBLIC_HOST || url.host;

  return json(200, {
    // The page hides the "you're looking at HQ as Ari" switcher when this is
    // true. A real session must not be able to pretend to be somebody else,
    // and the control that would let it simply is not drawn.
    via_session: actor.viaSession,
    person: personOut(p, {
      email: String(p.email ?? ""),
      phone: String(p.phone ?? ""),
      has_code: !!String(p.code_hash ?? ""),
      // The subscribe-from-URL feed. Deterministic on purpose: no new column,
      // no minting flow, and rotating the team key revokes every feed at once.
      cal_url: "https://" + host + "/internal/cal/"
        + (await sha256Hex(key + String(p.id))) + ".ics",
    }),
    team_name: cfg.team_name,
    perm_assign: cfg.perm_assign,
    perm_delete: cfg.perm_delete,
  }, cors);
}

// ---------------------------------------------------------------------------
// POST /internal/clerk/exchange -- trade a verified Clerk sign-in for the HQ
// session everything else already speaks.
//
// WHY AN EXCHANGE AND NOT CLERK EVERYWHERE: fourteen handlers accept
// X-HQ-Session. Teaching Clerk to all fourteen means fourteen edits per future
// change, and a Clerk outage would take down every request in flight. One
// exchange at the door means the rest of the file does not know Clerk exists,
// and an outage only stops NEW sign-ins.
//
// WHY HS256 AND NOT CLERK'S DEFAULT RS256: the PocketBase JSVM could not check
// an RS256 signature and Clerk's server-side verify endpoint answers 410
// (deprecated, tried 2026-08-23). So the page asks Clerk for a token minted
// from the "hq" JWT TEMPLATE -- HS256, signed with a key only Clerk and this
// backend hold, short-lived, carrying the user's email as a claim. The email
// therefore comes from Clerk's signature rather than from the client.
//
// workerd COULD do RS256 via WebCrypto, and that is deliberately not taken
// here: this port's job is to answer identically to the file it replaces. A
// better scheme is a change to make once, on both, on purpose.
//
// WHO GETS IN: that email must match an ACTIVE row in internal_people,
// case-insensitively. Signing up to Clerk is open to the world; membership of
// HQ is decided on the People page. This route is the wall between those.
// ---------------------------------------------------------------------------

function b64urlToBytes(s: string): Uint8Array {
  const pad = s.length % 4 === 0 ? "" : "=".repeat(4 - (s.length % 4));
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + pad;
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/**
 * `$security.parseJWT` -- verify HS256 and enforce exp, or return null.
 *
 * Returns null for every failure with no distinction between them. Which part
 * of a token was wrong is not something a caller gets told.
 */
export async function parseJwtHs256(
  token: string, secret: string,
): Promise<Record<string, unknown> | null> {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    // The algorithm comes from OUR expectation, never from the token's header.
    // Trusting the header is the alg:none / alg-confusion forgery.
    const head = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[0])));
    if (String(head.alg) !== "HS256") return null;

    const key = await crypto.subtle.importKey(
      "raw", new TextEncoder().encode(secret),
      { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
    const ok = await crypto.subtle.verify(
      "HMAC", key, b64urlToBytes(parts[2]),
      new TextEncoder().encode(parts[0] + "." + parts[1]));
    if (!ok) return null;

    const claims = JSON.parse(new TextDecoder().decode(b64urlToBytes(parts[1])));
    // exp is enforced here because parseJWT enforced it. A token whose expiry
    // is merely absent does not get treated as eternal.
    const exp = Number(claims.exp);
    if (!Number.isFinite(exp) || Date.now() / 1000 >= exp) return null;
    return claims as Record<string, unknown>;
  } catch {
    return null;
  }
}

export async function hqClerkExchange(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  const jwtKey = env.CLERK_HQ_JWT_KEY || "";
  if (!jwtKey) return json(503, { error: "Clerk sign-in is not configured" }, cors);

  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; } catch { /* {} */ }
  const tok = String(body.token ?? "");
  // SHAPE BEFORE AUTHORITY. A missing token is a malformed request (400), not
  // a rejected one (401) -- the caller has not claimed anything yet.
  if (!tok || tok.split(".").length !== 3) {
    return json(400, { error: "no Clerk token in the request" }, cors);
  }

  const claims = await parseJwtHs256(tok, jwtKey);
  if (!claims) return json(401, { error: "Clerk did not recognise that sign-in" }, cors);
  const email = String(claims.email ?? "").trim();
  if (!email || !claims.sub) {
    return json(401, { error: "Clerk did not recognise that sign-in" }, cors);
  }

  const person = await env.DB.prepare(
    "SELECT * FROM internal_people WHERE active = 1 AND lower(email) = ?1 LIMIT 1",
  ).bind(email.toLowerCase()).first<Person>();
  if (!person) {
    // Name the email so the fix is obvious -- but only to somebody who has
    // just proven to Clerk that they own it. This is their own address.
    return json(403, { error: "You signed in as " + email
      + ", but nobody in HQ has that email. Ask an admin to add it to your"
      + " person on the People page." }, cors);
  }

  // From here this is /internal/session's mint, identical in shape: same
  // table, same hash-only storage, same 30-day expiry, same keep-ten.
  const token = randomHex(64);
  const nowISO = pbNow();
  const expires = pbNow(new Date(Date.now() + 30 * 86400000));
  const xff = String(req.headers.get("X-Forwarded-For") || "");
  const ip = (xff ? xff.split(",")[0].trim()
                  : String(req.headers.get("CF-Connecting-IP") || "")).slice(0, 60);
  try {
    await env.DB.prepare(
      "INSERT INTO internal_sessions (id, created, person, token_hash, expires, ip, ua) "
      + "VALUES (?1,?2,?3,?4,?5,?6,?7)",
    ).bind(newRecordId(), nowISO, person.id, await sha256Hex(token), expires, ip,
           String(req.headers.get("User-Agent") || "").slice(0, 200)).run();
  } catch {
    return json(500, { error: "could not start a session" }, cors);
  }
  try {
    const old = await env.DB.prepare(
      "SELECT id FROM internal_sessions WHERE person = ?1 ORDER BY created DESC LIMIT 50 OFFSET 10",
    ).bind(person.id).all<{ id: string }>();
    for (const row of old.results ?? []) {
      await env.DB.prepare("DELETE FROM internal_sessions WHERE id = ?1").bind(row.id).run();
    }
  } catch { /* housekeeping */ }
  try {
    await env.DB.prepare("UPDATE internal_people SET last_in = ?1, updated = ?2 WHERE id = ?3")
      .bind(nowISO, pbNow(), person.id).run();
  } catch { /* the sign-in already happened */ }

  return json(200, {
    ok: true, token, expires,
    person: { id: person.id, name: String(person.name ?? ""),
              is_admin: boolDefaultFalse(person.is_admin) },
  }, cors);
}
