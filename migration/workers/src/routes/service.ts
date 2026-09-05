/**
 * The small service routes.
 *
 *   GET  /worker/owners        the brain asks who exists
 *   POST /admin/purge-audit    drain the audit ledger
 *   POST /auth/claim           attach pre-account rows to an account
 *   POST /me/phone/remove      take the number off
 *   POST /me/profile/upsert    write the profile
 *
 * Ported from worker_owners.pb.js, audit_retention.pb.js, claim_legacy.pb.js,
 * phone_remove.pb.js and owner_profile_upsert.pb.js.
 *
 * /worker/owners RETURNS TWO FIELDS AND NOTHING ELSE. The brain needs to know
 * which owners exist and how to match their pre-account rows; it does not need
 * their email, phone, name or birthday, and this endpoint is authorised by a
 * SHARED SERVICE TOKEN that every worker process carries. The contract asserts
 * the key set exactly -- `set(item.keys()) == {"id", "legacy_uuid"}` -- so
 * widening it later is a test failure and not a silent PII leak.
 *
 * WHAT WAS HERE UNTIL 2026-09-05: authClaim, phoneRemove and profileUpsert
 * each verified the account token and then answered
 * `503 {ok:false, message:"… not yet ported"}`. Measured on api.anticipy.ai
 * that day with a real signed-in account (audit F02/F03): profile upsert 503,
 * phone removal 503, claim 503, and no owner_profile row written -- so on
 * Cloudflare a TestFlight signup could not save its phone (OnboardingView's
 * phoneSaveFailed bounce), could not save name/email/birthday, never reported
 * its timezone (quiet hours judged in the server's zone), could not remove its
 * number, and adopted none of its pre-account rows. The three bodies below are
 * the ports of backend/pb_hooks/owner_profile_upsert.pb.js, phone_remove.pb.js
 * and claim_legacy.pb.js.
 *
 * ONE TRANSACTION, WHERE D1 HAS ONE. All three hooks lean on PocketBase's
 * `runInTransaction`, whose real work is that the write half is ALL-OR-NOTHING
 * and that a verification failure rolls the writes back. D1 has no interactive
 * transaction -- a handler cannot hold one open across an await -- but
 * `env.DB.batch()` IS one: every statement commits together or none does. So
 * each route here reads, decides, and then puts every write in a SINGLE batch.
 * The consequence, stated rather than hidden: the hooks' IN-transaction proof
 * (re-read before commit, throw to roll back) cannot exist here, so the proof
 * runs AFTER the batch. A batch that throws answers with the hook's rollback
 * sentence and has written nothing; a batch that lands but does not verify
 * answers with the hook's post-commit sentence, which is the one the hook uses
 * for exactly this case -- "the server could not verify it, refresh before
 * relying on it". Neither ever answers ok:true over unproven state, which is
 * the property the transaction was bought for. The storage-level backstop for
 * two simultaneous first writers is unchanged and is the real one: the partial
 * unique index idx_owner_profile_owner_ref (migration/d1/schema.sql:369-370).
 */
import { verifyToken, type AuthEnv } from "../pb/auth.ts";
import { newRecordId, pbNow } from "../pb/wire.ts";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json" },
  });

export interface ServiceEnv extends AuthEnv {
  DB: D1Database;
  ANTICIPY_SERVICE_TOKEN?: string;
}

/** Length-checked, difference-accumulating compare. */
function tokenOk(env: ServiceEnv, req: Request): boolean {
  const want = env.ANTICIPY_SERVICE_TOKEN || "";
  const got = req.headers.get("X-Anticipy-Token") || "";
  if (!want || got.length !== want.length) return false;
  let d = 0;
  for (let i = 0; i < got.length; i++) d |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return d === 0;
}

const forbidden = () => json(403, { error: "forbidden" });
const signIn = () => json(401, { ok: false, message: "Sign in first." });

export async function workerOwners(req: Request, env: ServiceEnv): Promise<Response> {
  if (!tokenOk(env, req)) return forbidden();
  const url = new URL(req.url);
  const page = Math.max(1, parseInt(url.searchParams.get("page") || "1", 10) || 1);
  // Clamped, not trusted: perPage=9999 answers 200 rows, not 9999.
  const perPage = Math.min(200, Math.max(1,
    parseInt(url.searchParams.get("perPage") || "200", 10) || 200));

  const total = await env.DB.prepare(`SELECT COUNT(*) n FROM owners`).first<{ n: number }>();
  const rows = await env.DB
    .prepare(`SELECT id, legacy_uuid FROM owners ORDER BY created LIMIT ? OFFSET ?`)
    .bind(perPage, (page - 1) * perPage)
    .all<{ id: string; legacy_uuid: string | null }>();

  const totalItems = total?.n ?? 0;
  return json(200, {
    page, perPage, totalItems,
    totalPages: Math.max(1, Math.ceil(totalItems / perPage)),
    // Exactly two fields. See the note at the top of this file.
    items: (rows.results ?? []).map((r) => ({ id: r.id, legacy_uuid: r.legacy_uuid ?? "" })),
  });
}

export async function purgeAudit(req: Request, env: ServiceEnv): Promise<Response> {
  if (!tokenOk(env, req)) return forbidden();
  // The audit ledger is certification evidence, not customer data: regenerable
  // by re-running a cohort. Left uncapped it filled the production volume to
  // the point SQLite could not write ANY row -- and the visible symptom was a
  // password-reset text going out whose code could never be stored.
  const KEEP = 300;
  const res = await env.DB.prepare(
    `DELETE FROM agent_llm_audit WHERE id NOT IN (
       SELECT id FROM agent_llm_audit ORDER BY created DESC LIMIT ?)`)
    .bind(KEEP).run();
  return json(200, { ok: true, deleted: (res.meta?.changes as number) ?? 0, kept: KEEP });
}

// ---------------------------------------------------------------------------
// The account routes. CONTRACT.md §6.8, §6.9, §6.10.
// ---------------------------------------------------------------------------

/**
 * The eight fields a person owns on their own profile
 * (owner_profile_upsert.pb.js:53-66). `owner_ref` and `owner_id` are NOT here
 * and may never be: ownership is derived from the token, never sent.
 */
const EDITABLE = [
  "phone", "name", "first_name", "last_name", "email", "birthday",
  "facts", "timezone",
] as const;
type Editable = (typeof EDITABLE)[number];

const isEditable = (key: string): key is Editable =>
  (EDITABLE as readonly string[]).includes(key);

/** A profile row as D1 holds it. Every column is TEXT NOT NULL DEFAULT ''. */
type ProfileRow = Record<string, unknown>;

const str = (v: unknown): string => String(v ?? "");

/**
 * The account, read whole.
 *
 * `SELECT *` on purpose: owner_profile_upsert.pb.js seeds a first profile from
 * "every same-named text field on the account", which is email and phone today
 * and stays correct if an account migration adds another identity column. The
 * password digest and tokenKey come back in this row and are read by NOTHING
 * below -- only the eight names in EDITABLE plus legacy_uuid are ever touched,
 * and none of them can name a hidden column.
 */
async function accountRow(env: ServiceEnv, ref: string): Promise<Record<string, unknown> | null> {
  return env.DB.prepare(`SELECT * FROM "owners" WHERE "id" = ?1 LIMIT 1`)
    .bind(ref).first<Record<string, unknown>>();
}

/**
 * Every profile for this account, NEWEST FIRST -- `-updated,-created,-id`.
 *
 * The sort is the hook's and it is load-bearing: profiles[0] is authoritative
 * for EVERY field, INCLUDING an empty phone written by the removal flow, and
 * older non-empty duplicates never value-merge back in. pbNow()'s format sorts
 * lexicographically in chronological order, which is why a TEXT compare is the
 * right one here (migration/d1/schema.sql:88-95).
 */
async function profilesFor(env: ServiceEnv, ref: string, limit = 0): Promise<ProfileRow[]> {
  const cap = limit > 0 ? ` LIMIT ${limit}` : "";
  const res = await env.DB.prepare(
    `SELECT * FROM "owner_profile" WHERE "owner_ref" = ?1
      ORDER BY "updated" DESC, "created" DESC, "id" DESC${cap}`,
  ).bind(ref).all<ProfileRow>();
  return res.results ?? [];
}

/**
 * POST /auth/claim -- adopt the rows this device made before accounts existed.
 * claim_legacy.pb.js.
 */
export async function authClaim(req: Request, env: ServiceEnv): Promise<Response> {
  const auth = await verifyToken(env, req.headers.get("Authorization") || "");
  if (!auth) return signIn();

  let body: Record<string, unknown> = {};
  try {
    const parsed: unknown = await req.json();
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      body = parsed as Record<string, unknown>;
    }
  } catch { body = {}; }
  const legacy = str(body.legacy_uuid).trim();

  // THE UUID HAS TO BE THE ONE RECORDED ON THIS ACCOUNT AT SIGN-UP, or calling
  // it evidence is a lie. It is not a secret: agents.owner IS the phone's uuid
  // and the deliberately anonymous six-digit pair-code lookup hands the row
  // out. So the attack was: read a stranger's uuid off a pair code, sign up a
  // throwaway account, POST it here, and every legacy row moved -- including
  // the owner_profile carrying that person's name, email, phone and birthday.
  // And because an inbound text resolves through owner_profile.phone BEFORE
  // owners (src/pb/sender.ts), every "yes, go ahead" the real owner texted was
  // thereafter filed under the stranger and released into their browser.
  // owners.legacy_uuid is UNIQUE, and the app posts back the value it
  // registered, so equality against the recorded one is the entire test -- and
  // an account with nothing recorded can claim nothing.
  const recorded = str(auth.row.legacy_uuid).trim();
  if (legacy && legacy !== recorded) {
    console.log(`claim: refused ${legacy} for ${auth.claims.id} (not this account's device)`);
    return json(403, { ok: false, message: "That device isn't on this account." });
  }

  const ref = String(auth.claims.id);
  const claimed: Record<string, number> = {
    jobs: 0, owner_profile: 0, segments: 0, agents: 0, events: 0,
  };

  // 1. Rows that can prove they are this person's.
  if (legacy.length >= 8) {
    for (const table of ["jobs", "owner_profile", "segments", "agents"] as const) {
      // owner_profile calls the pre-accounts uuid `owner_id`; the rest call it
      // `owner`. Naming the wrong one throws for the WHOLE query -- which is
      // how the 2026-08-05 `agents` fix claimed nothing for two days.
      const field = table === "owner_profile" ? "owner_id" : "owner";
      try {
        const rows = await env.DB.prepare(
          `SELECT "id" FROM "${table}" WHERE "${field}" = ?1 AND "owner_ref" = ''
            ORDER BY "created" DESC LIMIT 500`,
        ).bind(legacy).all<{ id: string }>();
        claimed[table] = await adopt(env, table, (rows.results ?? []).map((r) => String(r.id)), ref);
      } catch (err) {
        // Per-table swallow, exactly as the hook has it: one table that cannot
        // be read must not lose the tables that can.
        console.log(`claim: ${table} could not be claimed:`, String(err).slice(0, 160));
      }
    }
  }

  // 2. Transcripts, only when there is no one else they could belong to.
  // `events` has NEVER had an owner column, so there is no evidence on the row
  // at all. With two or more accounts the honest answer is to leave them
  // unowned and invisible rather than hand one person another person's
  // transcripts -- which was seen for real: a brand-new account opened the app
  // onto someone else's spoken sentences.
  try {
    const owners = await env.DB.prepare(
      `SELECT "id" FROM "owners" ORDER BY "created" DESC LIMIT 2`,
    ).all<{ id: string }>();
    const rows = owners.results ?? [];
    if (rows.length === 1 && String(rows[0]!.id) === ref) {
      const orphans = await env.DB.prepare(
        `SELECT "id" FROM "events" WHERE "owner_ref" = '' ORDER BY "created" DESC LIMIT 2000`,
      ).all<{ id: string }>();
      claimed.events = await adopt(env, "events", (orphans.results ?? []).map((r) => String(r.id)), ref);
    }
  } catch (err) {
    console.log("claim: transcripts could not be claimed:", String(err).slice(0, 160));
  }

  console.log(`claim: ${JSON.stringify(claimed)} for ${ref}`);
  return json(200, { ok: true, claimed });
}

/**
 * Stamp `owner_ref` on rows already proven to be this account's, and answer
 * how many rows actually changed.
 *
 * CHUNKED BECAUSE D1 IS. A bound-parameter list is capped (100 per statement),
 * and claim's own caps are 500 rows per table and 2000 events -- so an id list
 * goes out in slices of 50 inside ONE batch. The count is the DATABASE's
 * `changes`, not the length of the list: a row somebody else claimed between
 * the SELECT and the UPDATE is not one this call adopted, and reporting the
 * list length would tell the phone it recovered history it did not.
 */
async function adopt(env: ServiceEnv, table: string, ids: string[], ref: string): Promise<number> {
  if (!ids.length) return 0;
  const now = pbNow();
  const stmts: D1PreparedStatement[] = [];
  for (let i = 0; i < ids.length; i += 50) {
    const slice = ids.slice(i, i + 50);
    const holes = slice.map((_, n) => `?${n + 3}`).join(", ");
    stmts.push(env.DB.prepare(
      `UPDATE "${table}" SET "owner_ref" = ?1, "updated" = ?2
        WHERE "id" IN (${holes}) AND "owner_ref" = ''`,
    ).bind(ref, now, ...slice));
  }
  const results = await env.DB.batch(stmts);
  return results.reduce((n, r) => n + Number(r.meta?.changes ?? 0), 0);
}

/**
 * POST /me/phone/remove -- take the number off everywhere it can still route.
 * phone_remove.pb.js.
 */
export async function phoneRemove(req: Request, env: ServiceEnv): Promise<Response> {
  const auth = await verifyToken(env, req.headers.get("Authorization") || "");
  if (!auth) return signIn();
  // Structurally unreachable while `owners` is the only auth collection
  // (pb/auth.ts refuses any other collectionName outright), and kept because
  // it is the documented refusal and the day a second auth collection exists
  // is the day its absence would be a hole rather than dead code.
  if (auth.claims.collectionName !== "owners") {
    return json(403, {
      ok: false, message: "Only an account can remove its own phone number.",
    });
  }
  const ref = str(auth.claims.id).trim();
  if (!ref) return json(400, { ok: false, message: "No account on that token." });

  const ROLLED_BACK = "I couldn't verify that every copy was removed, so the change was not completed.";
  const UNVERIFIED = "The server could not verify the removal. Refresh your account before relying on it.";

  let matching!: { id: string }[];
  let ownership!: { sql: string; params: string[] };
  try {
    const owner = await accountRow(env, ref);
    if (!owner) throw new Error("the account is not readable");
    ownership = ownershipClause(ref, str(owner.legacy_uuid).trim());
    const rows = await env.DB.prepare(
      `SELECT "id" FROM "owner_profile" WHERE ${ownership.sql} ORDER BY "id"`,
    ).bind(...ownership.params).all<{ id: string }>();
    matching = rows.results ?? [];
  } catch (err) {
    console.log("phone remove: could not read the account:", String(err).slice(0, 200));
    return json(500, { ok: false, message: ROLLED_BACK });
  }

  const now = pbNow();
  try {
    await env.DB.batch([
      env.DB.prepare(`UPDATE "owners" SET "phone" = '', "updated" = ?1 WHERE "id" = ?2`)
        .bind(now, ref),
      env.DB.prepare(
        `UPDATE "owner_profile" SET "phone" = '', "updated" = ?1 WHERE ${shift(ownership.sql, 1)}`,
      ).bind(now, ...ownership.params),
    ]);
  } catch (err) {
    console.log("phone remove: the write was refused:", String(err).slice(0, 200));
    return json(500, { ok: false, message: ROLLED_BACK });
  }

  // The proof, run again through an ordinary read. UNKNOWN IS FAILURE and is
  // never interpreted as an empty phone -- a thrown read here answers 500, so
  // the phone never shows "removed" over a number that is still routable.
  try {
    const after = await accountRow(env, ref);
    if (!after) throw new Error("the account vanished mid-removal");
    if (str(after.phone).trim()) throw new Error("committed owner phone is not empty");
    const left = await env.DB.prepare(
      `SELECT "id" FROM "owner_profile" WHERE (${ownership.sql}) AND "phone" != '' LIMIT 1`,
    ).bind(...ownership.params).first();
    if (left) throw new Error("committed profile phone is not empty");
  } catch (err) {
    console.log("phone remove: post-commit verification failed:", String(err).slice(0, 200));
    return json(500, { ok: false, message: UNVERIFIED });
  }

  console.log(`phone remove: cleared account seed and ${matching.length} profile row(s)`);
  return json(200, { ok: true, phone: "", clearedProfiles: matching.length });
}

/**
 * Which profile rows are this account's, for the purpose of REVOKING a number.
 *
 * The ownerless residue (`owner_ref = ''` with a matching `owner_id`) is
 * included on purpose: claim_legacy historically swallowed an individual
 * profile save failure, and such a row is still safely attributable by the
 * account's unique legacy UUID -- or by the account ref, which is the
 * fresh-profile fallback for `owner_id`. Revocation has to cover that residue
 * or an old number stays routable after a 200. Nothing else may match: this is
 * a REVOCATION filter, so a row it wrongly includes is only ever a phone
 * cleared that did not need clearing, never someone else's row read out.
 */
function ownershipClause(ref: string, legacy: string): { sql: string; params: string[] } {
  if (legacy) {
    return {
      sql: `"owner_ref" = ?1 OR ("owner_ref" = '' AND ("owner_id" = ?1 OR "owner_id" = ?2))`,
      params: [ref, legacy],
    };
  }
  return {
    sql: `"owner_ref" = ?1 OR ("owner_ref" = '' AND "owner_id" = ?1)`,
    params: [ref],
  };
}

/** Re-number `?N` placeholders when the clause is preceded by other binds. */
function shift(sql: string, by: number): string {
  return sql.replace(/\?(\d+)/g, (_m, n: string) => `?${Number(n) + by}`);
}

/**
 * POST /me/profile/upsert -- one authenticated partial write in, one complete
 * canonical profile out. owner_profile_upsert.pb.js.
 *
 * Settings saves identity details and the phone independently, and those
 * requests can be in flight together. The old client path made each one do a
 * list followed by either POST or PATCH, so two first writes could both see no
 * row and create two different partial profiles; later reads took whichever
 * was newest, and a person's name or phone appeared to vanish. Here the read,
 * merge, write and duplicate cleanup are one decision and one batch.
 */
export async function profileUpsert(req: Request, env: ServiceEnv): Promise<Response> {
  const auth = await verifyToken(env, req.headers.get("Authorization") || "");
  if (!auth) return signIn();
  if (auth.claims.collectionName !== "owners") {
    return json(403, { ok: false, message: "Only an account can update its own profile." });
  }
  const ref = str(auth.claims.id).trim();
  if (!ref) return json(400, { ok: false, message: "No account on that token." });

  let parsed: unknown;
  try { parsed = await req.json(); }
  catch { return json(400, { ok: false, message: "The profile update was unreadable." }); }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return json(400, { ok: false, message: "The profile update must be an object." });
  }
  const patch = parsed as Record<string, unknown>;
  for (const key of Object.keys(patch)) {
    if (!isEditable(key)) {
      return json(400, { ok: false, message: "That field is not part of the owner profile." });
    }
    if (typeof patch[key] !== "string") {
      return json(400, { ok: false, message: "Profile fields must be text." });
    }
  }

  const ROLLED_BACK = "I couldn't verify the complete profile, so nothing was reported as saved.";
  const UNVERIFIED = "The server could not verify the saved profile. Refresh before relying on it.";

  let owner!: Record<string, unknown>;
  let existing!: ProfileRow[];
  try {
    // The account read is part of the same decision. A FAILED read is unknown
    // state and refuses; it is never converted into empty seeds, which would
    // blank a real profile on one bad round trip.
    const row = await accountRow(env, ref);
    if (!row) throw new Error("the account is not readable");
    owner = row;
    existing = await profilesFor(env, ref);
  } catch (err) {
    console.log("owner profile upsert: could not read the account:", String(err).slice(0, 200));
    return json(500, { ok: false, message: ROLLED_BACK });
  }

  const now = pbNow();
  const stmts: D1PreparedStatement[] = [];
  let canonicalId: string;
  let removedDuplicates = 0;

  if (existing.length) {
    canonicalId = str(existing[0]!.id);
    // The newest row is authoritative; every older duplicate is deleted, not
    // merged. On D1 the partial unique index makes a duplicate unreachable for
    // anything written HERE -- this branch is for rows imported from before it
    // existed (migration/d1/schema.sql:371-377 keeps that history).
    for (let i = 1; i < existing.length; i++) {
      stmts.push(env.DB.prepare(`DELETE FROM "owner_profile" WHERE "id" = ?1`)
        .bind(str(existing[i]!.id)));
      removedDuplicates++;
    }
    // Ownership comes only from the token. owner_id is a legacy device
    // linkage, not authority: keep an existing value, then prefer the
    // account's recorded legacy UUID, and finally the account id, so this
    // required structural field is never blank.
    const ownerId = str(existing[0]!.owner_id).trim() || str(owner.legacy_uuid).trim() || ref;
    const sets = [`"owner_ref" = ?1`, `"owner_id" = ?2`, `"updated" = ?3`];
    const vals: string[] = [ref, ownerId, now];
    // PRESENCE, NOT TRUTHINESS. `""` is a real value and clears the field;
    // omission keeps whatever the canonical row already holds.
    for (const field of EDITABLE) {
      if (!(field in patch)) continue;
      vals.push(String(patch[field]));
      sets.push(`"${field}" = ?${vals.length}`);
    }
    vals.push(canonicalId);
    stmts.push(env.DB.prepare(
      `UPDATE "owner_profile" SET ${sets.join(", ")} WHERE "id" = ?${vals.length}`,
    ).bind(...vals));
  } else {
    canonicalId = newRecordId();
    const ownerId = str(owner.legacy_uuid).trim() || ref;
    // Seed every editable field from the same-named field on the account, then
    // apply the body over it. Account values seed ONLY the first profile:
    // once a profile exists its empty phone or email is authoritative and must
    // not resurrect the sign-up-era copy.
    const cols = ["id", "created", "updated", "owner_ref", "owner_id", ...EDITABLE];
    const vals: string[] = [canonicalId, now, now, ref, ownerId];
    for (const field of EDITABLE) {
      vals.push(field in patch ? String(patch[field]) : str(owner[field]));
    }
    stmts.push(env.DB.prepare(
      `INSERT INTO "owner_profile" (${cols.map((c) => `"${c}"`).join(", ")})
       VALUES (${vals.map((_, i) => `?${i + 1}`).join(", ")})`,
    ).bind(...vals));
  }

  try {
    await env.DB.batch(stmts);
  } catch (err) {
    // The partial unique index catching a simultaneous first writer lands
    // here, and so does any other refusal. Nothing was written.
    console.log("owner profile upsert: the write was refused:", String(err).slice(0, 200));
    return json(500, { ok: false, message: ROLLED_BACK });
  }

  // Read back through an ordinary read and PROVE it. A concurrent partial
  // writer may legitimately have changed a field this request omitted, so the
  // proof pins uniqueness and THIS request's explicit fields, then returns the
  // latest complete row rather than a stale pre-write snapshot.
  let saved: ProfileRow;
  try {
    const rows = await profilesFor(env, ref, 2);
    if (rows.length !== 1 || str(rows[0]!.id) !== canonicalId) {
      throw new Error("committed profile is not uniquely canonical");
    }
    saved = rows[0]!;
    for (const field of EDITABLE) {
      if (field in patch && str(saved[field]) !== patch[field]) {
        throw new Error("committed profile field disagrees: " + field);
      }
    }
  } catch (err) {
    console.log("owner profile upsert: post-commit verification failed:", String(err).slice(0, 200));
    return json(500, { ok: false, message: UNVERIFIED });
  }

  // The COMPLETE canonical row, because AnticipyBackend.swift:410-420 verifies
  // every field it sent round-trips and that profile.owner_ref is its own
  // account id before it will paint "Saved".
  const profile: Record<string, string> = {
    id: str(saved.id),
    owner_ref: str(saved.owner_ref),
    owner_id: str(saved.owner_id),
  };
  for (const field of EDITABLE) profile[field] = str(saved[field]);

  return json(200, { ok: true, profile, removedDuplicates });
}
