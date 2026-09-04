/**
 * HQ's People page -- internal_hq.pb.js:333-611, CONTRACT.md §7.
 *
 * Two routes and both of them are privilege boundaries:
 *   POST  /internal/people   self-serve join, and the one place a login code
 *                            is minted
 *   PATCH /internal/people   self-edit contacts; admin-only role/active
 *
 * See hq_data.ts for what is proven here and what is not.
 */
import { sha256Hex } from "../llm.ts";
import { newRecordId, pbNow } from "../pb/wire.ts";
import { hqCors, type HqEnv } from "./hq.ts";
import {
  boolDefaultFalse, boolDefaultTrue, isoNow, logActivity, resolveActor,
  type Person,
} from "./hq_data.ts";

const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const PHONE_RE = /^\+?\d{8,15}$/;
const PREFS = ["inapp", "email", "sms", "both"];

/**
 * CROCKFORD BASE32, EIGHT CHARACTERS. The alphabet excludes I, L, O and U, so
 * a code read aloud cannot land on the wrong character.
 *
 * That is not cosmetic. Every sign-in failure returns the SAME sentence, so a
 * transcription slip would be indistinguishable from a revoked code and the
 * person would have no way to tell which happened.
 *
 * 32^8 is about 1.1e12. Against the 40-attempts-an-hour ceiling in
 * /internal/session that is not a brute force, it is a geological era.
 */
const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
function mintCode(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(8));
  let out = "";
  // Rejection-free because 256 % 32 === 0, so the modulo is unbiased here.
  for (const b of bytes) out += CROCKFORD[b % 32];
  return out;
}

// ---------------------------------------------------------------------------
// POST /internal/people -- self-serve join. Anyone with the key adds
// themselves; minting a CODE is a separate, admin-only act.
// ---------------------------------------------------------------------------
export async function hqPeopleCreate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; } catch { /* {} */ }

  // A session, if present, IS the actor and overrides anything the body claims.
  const viaSession = await resolveActor(req, env, {
    actorId: String(body.actor_id ?? ""), optional: true,
  });
  if (!viaSession.ok) return viaSession.response;

  const name = String(body.name ?? "").trim();
  const email = String(body.email ?? "").trim();
  const phone = String(body.phone ?? "").trim().replace(/[\s()-]/g, "");
  if (!name || name.length > 120) {
    return json(400, { error: "a name between 1 and 120 characters, please" }, cors);
  }
  if (email && !EMAIL_RE.test(email)) {
    return json(400, { error: "that email doesn't look right" }, cors);
  }
  if (phone && !PHONE_RE.test(phone)) {
    return json(400, {
      error: "phone should be digits with an optional +, like +16045550142",
    }, cors);
  }
  try {
    const dupes = await env.DB.prepare(
      "SELECT name FROM internal_people WHERE active = 1 ORDER BY name ASC LIMIT 200",
    ).all<{ name: string }>();
    for (const d of dupes.results ?? []) {
      if (String(d.name ?? "").toLowerCase() === name.toLowerCase()) {
        return json(400, {
          error: name + " is already on the team — pick yourself from the list instead",
        }, cors);
      }
    }
  } catch { /* a duplicate check that cannot run does not block a join */ }

  const role = String(body.role ?? "").trim().slice(0, 80);
  const focus = String(body.focus ?? "").trim().slice(0, 140);
  // IANA id, not "Pacific (PT)". The reminder engine turns "9am" into UTC with
  // this string; a friendly label is something the page renders, not something
  // the server can compute an hour from.
  const tz = String(body.tz ?? "").trim().slice(0, 60);
  const pref = String(body.remind_pref ?? "").trim();
  if (pref && !PREFS.includes(pref)) {
    return json(400, { error: "reminders are in-app, email, sms or both" }, cors);
  }

  // MINTING A LOGIN CODE IS AN ADMIN ACT, AND ONLY AN ADMIN ACT.
  //
  // Self-serve join stays open: anyone holding the shared key can add
  // themselves. But a code is a credential, so the branch that mints one
  // demands a named admin. Without this, anyone with the key could mint a code
  // for a new ADMIN account and convert "holds the shared key" into "is a
  // person with a durable session" -- a privilege upgrade the shared key was
  // never meant to grant.
  const wantsCode = !!body.mint_code;
  let minter: Person | null = null;
  if (wantsCode) {
    const who = viaSession.person ? String(viaSession.person.id) : String(body.actor_id ?? "");
    if (!who) return json(400, { error: "pick yourself first" }, cors);
    minter = await env.DB.prepare(
      "SELECT * FROM internal_people WHERE id = ?1 LIMIT 1",
    ).bind(who).first<Person>();
    if (!minter) return json(400, { error: "pick yourself first" }, cors);
    if (!boolDefaultFalse(minter.active)) {
      return json(400, { error: "that person is deactivated" }, cors);
    }
    if (!boolDefaultFalse(minter.is_admin)) {
      return json(403, { error: "only an admin can hand out login codes" }, cors);
    }
  }
  const minterIsAdmin = !!(minter && boolDefaultFalse(minter.is_admin));
  if ("is_admin" in body && !!body.is_admin && !minterIsAdmin) {
    return json(403, { error: "only an admin can make someone an administrator" }, cors);
  }

  const id = newRecordId();
  let plain = "";
  let codeHash = "";
  let codeSetAt = "";
  if (wantsCode) {
    // Only sha256 is stored. This database is backed up nightly and there is
    // deliberately NO route in HQ that can read a code back out. It is
    // returned once, below, and then exists only in the admin's clipboard.
    plain = mintCode();
    codeHash = await sha256Hex(plain);
    codeSetAt = isoNow();          // T-format column
  }
  await env.DB.prepare(
    "INSERT INTO internal_people (id, created, updated, name, email, phone, role, focus, tz,"
    + " remind_pref, email_on, sms_on, is_admin, active, code_hash, code_set_at, last_in)"
    + " VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,1,?14,?15,'')",
  ).bind(id, pbNow(), pbNow(), name, email, phone, role, focus, tz,
         pref || "inapp",
         boolDefaultTrue(body.email_on) ? 1 : 0,
         boolDefaultTrue(body.sms_on) ? 1 : 0,
         minterIsAdmin && !!body.is_admin ? 1 : 0,
         codeHash, codeSetAt).run();

  await logActivity(env, minter ?? ({ id, name } as Person), "person.join",
    minter ? String(minter.name ?? "") + " added " + name + " to the team"
           : name + " joined the team",
    minter ? "added " + name + " to the team" : "joined the team", id);

  const out: Record<string, unknown> = {
    id, name, email, phone, role, focus, tz,
    remind_pref: pref || "inapp",
    is_admin: minterIsAdmin && !!body.is_admin,
    active: true,
  };
  // The plaintext leaves the building exactly here, exactly once. It is not
  // logged, not written to activity, and not in /internal/state.
  if (plain) out.code = plain.slice(0, 4) + "-" + plain.slice(4);
  return json(200, out, cors);
}

// ---------------------------------------------------------------------------
// PATCH /internal/people -- self-edit contacts; admin-only role/active.
// ---------------------------------------------------------------------------
export async function hqPeopleUpdate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; } catch { /* {} */ }

  const resolved = await resolveActor(req, env, {
    actorId: String(body.actor_id ?? ""), optional: true,
  });
  if (!resolved.ok) return resolved.response;
  const actor = resolved.person;
  // Its OWN message, not /internal/me's "pick yourself first": this route is
  // recording who made a change, not asking who you are.
  if (!actor) {
    return json(400, { error: "who is making this change? actor_id missing" }, cors);
  }
  if (!boolDefaultFalse(actor.active)) {
    return json(400, { error: "that person is deactivated" }, cors);
  }

  const targetId = String(body.person_id ?? "");
  const target = targetId
    ? await env.DB.prepare("SELECT * FROM internal_people WHERE id = ?1 LIMIT 1")
        .bind(targetId).first<Person>()
    : null;
  if (!target) return json(404, { error: "no such person" }, cors);

  const isSelf = String(actor.id) === String(target.id);
  const isAdmin = boolDefaultFalse(actor.is_admin);
  const wantsRoleChange = "is_admin" in body || "active" in body;
  if (wantsRoleChange && !isAdmin) {
    return json(403, { error: "only an admin can change roles" }, cors);
  }
  if (!isSelf && !isAdmin) {
    return json(403, { error: "you can only edit your own details" }, cors);
  }

  const sets: string[] = [];
  const binds: unknown[] = [];
  const put = (col: string, value: unknown) => {
    sets.push(`${col} = ?${sets.length + 1}`); binds.push(value);
  };

  if ("email" in body) {
    const email = String(body.email ?? "").trim();
    if (email && !EMAIL_RE.test(email)) {
      return json(400, { error: "that email doesn't look right" }, cors);
    }
    put("email", email);
  }
  if ("phone" in body) {
    const phone = String(body.phone ?? "").trim().replace(/[\s()-]/g, "");
    if (phone && !PHONE_RE.test(phone)) {
      return json(400, { error: "phone should be digits with an optional +" }, cors);
    }
    put("phone", phone);
  }
  if ("role" in body) put("role", String(body.role ?? "").trim().slice(0, 80));
  if ("focus" in body) put("focus", String(body.focus ?? "").trim().slice(0, 140));
  if ("tz" in body) put("tz", String(body.tz ?? "").trim().slice(0, 60));
  if ("remind_pref" in body) {
    const pref = String(body.remind_pref ?? "").trim();
    if (!PREFS.includes(pref)) {
      return json(400, { error: "reminders are in-app, email, sms or both" }, cors);
    }
    put("remind_pref", pref);
  }
  // `!!body.x` here, NOT the defaults-to-true rule: an explicit PATCH says
  // exactly what it means, and only the fields present are touched.
  if ("email_on" in body) put("email_on", body.email_on ? 1 : 0);
  if ("sms_on" in body) put("sms_on", body.sms_on ? 1 : 0);
  // code_hash is deliberately NOT patchable here. Rotating a credential has to
  // sign the old sessions out, and that happens in exactly one place:
  // POST /internal/people/code. A second door onto this field would be a
  // second door that forgets to close them.
  if ("is_admin" in body) put("is_admin", body.is_admin ? 1 : 0);

  let deactivating = false;
  if ("active" in body) {
    if (!body.active && boolDefaultFalse(target.is_admin)) {
      // Never let the last admin lock everyone out.
      let admins = 0;
      try {
        const row = await env.DB.prepare(
          "SELECT COUNT(*) n FROM internal_people WHERE active = 1 AND is_admin = 1",
        ).first<{ n: number }>();
        admins = Number(row?.n ?? 0);
      } catch { admins = 0; }
      if (admins <= 1) {
        return json(400, {
          error: "that's the last admin — promote someone else first",
        }, cors);
      }
    }
    put("active", body.active ? 1 : 0);
    deactivating = !body.active;
  }

  if (sets.length) {
    binds.push(pbNow(), target.id);
    await env.DB.prepare(
      `UPDATE internal_people SET ${sets.join(", ")}, updated = ?${binds.length - 1} `
      + `WHERE id = ?${binds.length}`,
    ).bind(...binds).run();
  }

  // DEACTIVATING SOMEONE SIGNS THEM OUT NOW, not when their token expires.
  // resolveActor re-checks `active` on every request so a live session would
  // already be refused -- but leaving the rows behind means a REACTIVATION
  // silently restores a thirty-day-old token somebody may have pasted
  // somewhere. Deleting them makes reinstatement a fresh sign-in.
  if (deactivating) {
    try {
      await env.DB.prepare("DELETE FROM internal_sessions WHERE person = ?1")
        .bind(target.id).run();
    } catch { /* the deactivation itself already landed */ }
  }

  await logActivity(env, actor, "person.update",
    String(actor.name ?? "") + " updated " + String(target.name ?? ""),
    "", String(target.id));
  return json(200, { ok: true }, cors);
}
