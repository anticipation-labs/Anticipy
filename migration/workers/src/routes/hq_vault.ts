/**
 * HQ's vault and its three admin routes -- internal_hq.pb.js, CONTRACT.md §7.
 *
 *   POST /internal/passwords  /passwords/reveal  /passwords/delete
 *   POST /internal/people/code      mint a login code, admin only
 *   POST /internal/notifs/read      mark your own notifications read
 *   POST /internal/settings         team name and the two permission questions
 *
 * See hq_data.ts for what is proven here and what is not.
 */
import { sha256Hex } from "../llm.ts";
import { newRecordId, pbNow } from "../pb/wire.ts";
import { hqCors, type HqEnv } from "./hq.ts";
import { boolDefaultFalse, isoNow, logActivity, resolveActor, type Person } from "./hq_data.ts";

const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

type Row = Record<string, unknown>;
const readBody = async (req: Request): Promise<Row> => {
  try { return (await req.json()) as Row; } catch { return {}; }
};

// ---------------------------------------------------------------------------
// $security.encrypt / $security.decrypt, reimplemented on WebCrypto
//
// PocketBase's helpers are AES-256-GCM with a 12-byte nonce PREPENDED to the
// ciphertext, the whole thing base64'd, and the key is the ASCII BYTES of the
// 32-character ANTICIPY_VAULT_KEY -- not a hex or base64 decode of it. That is
// why the length check below is `!== 32` on the STRING: 32 ASCII characters are
// exactly the 32 bytes AES-256 wants.
//
// This matters more than an implementation detail. It is what makes the
// migration a MOVE rather than a re-encryption: every secret_enc row already in
// D1 was written by PocketBase and must decrypt here unchanged. Verified by
// decrypting the real migrated row rather than by round-tripping our own
// ciphertext, which would have proved only that this file agrees with itself.
// ---------------------------------------------------------------------------
async function vaultKey(raw: string): Promise<CryptoKey> {
  return await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(raw), { name: "AES-GCM" }, false,
    ["encrypt", "decrypt"]);
}

export async function vaultEncrypt(plain: string, keyRaw: string): Promise<string> {
  const key = await vaultKey(keyRaw);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce }, key, new TextEncoder().encode(plain)));
  const joined = new Uint8Array(nonce.length + ct.length);
  joined.set(nonce, 0); joined.set(ct, nonce.length);
  let bin = "";
  for (const b of joined) bin += String.fromCharCode(b);
  return btoa(bin);
}

export async function vaultDecrypt(blob: string, keyRaw: string): Promise<string> {
  const bin = atob(blob);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  if (bytes.length <= 12) throw new Error("ciphertext too short");
  const key = await vaultKey(keyRaw);
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: bytes.slice(0, 12) }, key, bytes.slice(12));
  return new TextDecoder().decode(plain);
}

/** Key/session door plus a required, ACTIVE actor. */
async function actorOf(
  req: Request, env: HqEnv, body: Row, cors: Record<string, string>,
): Promise<{ ok: true; actor: Person } | { ok: false; response: Response }> {
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return { ok: false, response: json(503, { error: "internal HQ is not configured" }, cors) };
  }
  const resolved = await resolveActor(req, env, {
    actorId: String(body.actor_id ?? ""), optional: true,
  });
  if (!resolved.ok) return { ok: false, response: resolved.response };
  if (!resolved.person || !boolDefaultFalse(resolved.person.active)) {
    return { ok: false, response: json(400, { error: "pick yourself first" }, cors) };
  }
  return { ok: true, actor: resolved.person };
}

/** The vault's own 503, checked before the actor and before the key compare. */
function vaultKeyOr503(env: HqEnv, cors: Record<string, string>): string | Response {
  const vk = env.ANTICIPY_VAULT_KEY || "";
  if (vk.length !== 32) return json(503, { error: "the vault is not configured" }, cors);
  return vk;
}

// ---------------------------------------------------------------------------
// POST /internal/passwords -- upsert. secret_enc never leaves except at reveal.
// ---------------------------------------------------------------------------
export async function hqPasswordUpsert(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  const vk = vaultKeyOr503(env, cors);
  if (typeof vk !== "string") return vk;
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  let existing: Row | null = null;
  if (body.password_id) {
    existing = await env.DB.prepare("SELECT * FROM internal_passwords WHERE id = ?1 LIMIT 1")
      .bind(String(body.password_id)).first<Row>();
    if (!existing) return json(404, { error: "that entry is gone" }, cors);
  } else if (!String(body.service ?? "").trim()) {
    return json(400, { error: "which tool is this for?" }, cors);
  }

  const sets: Record<string, unknown> = {};
  if ("service" in body) sets.service = String(body.service ?? "").trim().slice(0, 120);
  if ("username" in body) sets.username = String(body.username ?? "").trim().slice(0, 200);
  if ("url" in body) sets.url = String(body.url ?? "").trim().slice(0, 500);
  if ("notes" in body) sets.notes = String(body.notes ?? "").slice(0, 2000);
  if ("secret" in body && String(body.secret ?? "") !== "") {
    // AN ABSENT OR EMPTY SECRET ON AN UPDATE MEANS "KEEP WHAT IS THERE".
    // An edit to fix a typo in the URL must never blank the password.
    try {
      sets.secret_enc = await vaultEncrypt(String(body.secret).slice(0, 500), vk);
    } catch {
      return json(500, { error: "could not encrypt that" }, cors);
    }
  }
  sets.updated_by = String(got.actor.id);

  try {
    if (existing) {
      const cols = Object.keys(sets);
      const binds = cols.map((c) => sets[c]);
      binds.push(pbNow(), String(existing.id));
      await env.DB.prepare(
        `UPDATE internal_passwords SET ${cols.map((c, i) => `${c} = ?${i + 1}`).join(", ")}, `
        + `updated = ?${binds.length - 1} WHERE id = ?${binds.length}`,
      ).bind(...binds).run();
      return json(200, { ok: true, id: existing.id }, cors);
    }
    const id = newRecordId();
    const cols = ["id", "created", "updated", "secret_enc", ...Object.keys(sets)];
    const binds: unknown[] = [id, pbNow(), pbNow(), sets.secret_enc ?? "",
                              ...Object.keys(sets).map((c) => sets[c])];
    // secret_enc appears once in the column list; drop the duplicate if the
    // caller supplied one.
    const seen = new Set<string>();
    const finalCols: string[] = []; const finalBinds: unknown[] = [];
    cols.forEach((c, i) => {
      if (seen.has(c)) return;
      seen.add(c); finalCols.push(c); finalBinds.push(binds[i]);
    });
    await env.DB.prepare(
      `INSERT INTO internal_passwords (${finalCols.join(", ")}) `
      + `VALUES (${finalBinds.map((_, i) => `?${i + 1}`).join(", ")})`,
    ).bind(...finalBinds).run();
    return json(200, { ok: true, id }, cors);
  } catch {
    return json(500, { error: "could not save" }, cors);
  }
}

// ---------------------------------------------------------------------------
// POST /internal/passwords/reveal -- the ONE route that decrypts, one row at a
// time. Plaintext exists in this response and nowhere else: never in the
// database, never in /internal/state, never in the activity feed.
// ---------------------------------------------------------------------------
export async function hqPasswordReveal(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  const vk = vaultKeyOr503(env, cors);
  if (typeof vk !== "string") return vk;
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  const row = await env.DB.prepare("SELECT * FROM internal_passwords WHERE id = ?1 LIMIT 1")
    .bind(String(body.password_id ?? "")).first<Row>();
  if (!row) return json(404, { error: "that entry is gone" }, cors);
  try {
    const plain = await vaultDecrypt(String(row.secret_enc ?? ""), vk);
    return json(200, { ok: true, secret: plain }, cors);
  } catch {
    return json(500, {
      error: "could not decrypt — was the vault key rotated?",
    }, cors);
  }
}

export async function hqPasswordDelete(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const row = await env.DB.prepare("SELECT id FROM internal_passwords WHERE id = ?1 LIMIT 1")
    .bind(String(body.password_id ?? "")).first<Row>();
  if (!row) return json(404, { error: "already gone" }, cors);
  await env.DB.prepare("DELETE FROM internal_passwords WHERE id = ?1").bind(row.id).run();
  return json(200, { ok: true }, cors);
}

// ---------------------------------------------------------------------------
// POST /internal/people/code -- mint a login code. Admin only.
// ---------------------------------------------------------------------------
const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
export async function hqPeopleCode(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const actor = got.actor;
  if (!boolDefaultFalse(actor.is_admin)) {
    return json(403, { error: "only an admin can hand out login codes" }, cors);
  }
  const target = await env.DB.prepare("SELECT * FROM internal_people WHERE id = ?1 LIMIT 1")
    .bind(String(body.person_id ?? "")).first<Person>();
  if (!target) return json(404, { error: "no such person" }, cors);

  const bytes = crypto.getRandomValues(new Uint8Array(8));
  let plain = "";
  for (const b of bytes) plain += CROCKFORD[b % 32];

  await env.DB.prepare(
    "UPDATE internal_people SET code_hash = ?1, code_set_at = ?2, updated = ?3 WHERE id = ?4",
  ).bind(await sha256Hex(plain), isoNow(), pbNow(), String(target.id)).run();

  // A RESET SIGNS THE OLD CODE OUT. Rotating code_hash alone would leave every
  // session minted with the previous code alive for up to thirty days, so the
  // reset would look like it worked and change nothing for the one person it
  // was aimed at -- a revoked credential outliving its revocation.
  let killed = 0;
  try {
    const res = await env.DB.prepare("DELETE FROM internal_sessions WHERE person = ?1")
      .bind(String(target.id)).run();
    killed = Number(res.meta?.changes ?? 0);
  } catch { killed = 0; }

  // The code itself never appears here. An activity feed is read by everyone.
  await logActivity(env, actor, "person.code",
    String(actor.name ?? "") + " reset " + String(target.name ?? "") + "'s login code",
    "reset the login code", String(target.id));

  // Shown once, on the admin's screen, and then it only exists in a clipboard.
  return json(200, {
    code: plain.slice(0, 4) + "-" + plain.slice(4),
    signed_out: killed, name: String(target.name ?? ""),
  }, cors);
}

// ---------------------------------------------------------------------------
// POST /internal/notifs/read
// ---------------------------------------------------------------------------
export async function hqNotifsRead(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const mine = String(got.actor.id);

  if (body.all === true) {
    try {
      await env.DB.prepare(
        "UPDATE internal_notifs SET read = 1 WHERE person = ?1 AND read = 0",
      ).bind(mine).run();
    } catch { /* the count below still tells the truth */ }
  } else if (Array.isArray(body.ids)) {
    for (const id of (body.ids as unknown[]).slice(0, 200)) {
      try {
        // MARKING SOMEBODY ELSE'S NOTIFICATION READ would hide a thing they
        // were told, from them, with no trace. The row has to be yours, and
        // that is enforced in the WHERE rather than after the read.
        await env.DB.prepare(
          "UPDATE internal_notifs SET read = 1 WHERE id = ?1 AND person = ?2",
        ).bind(String(id), mine).run();
      } catch { /* one bad id does not fail the batch */ }
    }
  } else {
    return json(400, { error: "which ones? send ids, or all:true" }, cors);
  }

  let unread = 0;
  try {
    const row = await env.DB.prepare(
      "SELECT COUNT(*) n FROM internal_notifs WHERE person = ?1 AND read = 0",
    ).bind(mine).first<{ n: number }>();
    unread = Math.min(Number(row?.n ?? 0), 200);
  } catch { unread = 0; }
  return json(200, { ok: true, unread }, cors);
}

// ---------------------------------------------------------------------------
// POST /internal/settings -- admin only
// ---------------------------------------------------------------------------
export async function hqSettings(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const actor = got.actor;
  if (!boolDefaultFalse(actor.is_admin)) {
    return json(403, { error: "only an admin can change team settings" }, cors);
  }

  const put = async (k: string, v: string) => {
    const row = await env.DB.prepare(
      "SELECT id FROM internal_config WHERE key = ?1 LIMIT 1").bind(k).first<Row>();
    if (row) {
      await env.DB.prepare(
        "UPDATE internal_config SET value = ?1, updated = ?2 WHERE id = ?3",
      ).bind(v, pbNow(), String(row.id)).run();
    } else {
      await env.DB.prepare(
        "INSERT INTO internal_config (id, created, updated, key, value) VALUES (?1,?2,?3,?4,?5)",
      ).bind(newRecordId(), pbNow(), pbNow(), k, v).run();
    }
  };

  if ("team_name" in body) {
    const n = String(body.team_name ?? "").trim().slice(0, 120);
    if (!n) return json(400, { error: "the team needs a name" }, cors);
    await put("team_name", n);
  }
  if ("perm_assign" in body) {
    const v = String(body.perm_assign ?? "");
    if (v !== "everyone" && v !== "admins") {
      return json(400, { error: "everyone, or admins only" }, cors);
    }
    await put("perm_assign", v);
  }
  if ("perm_delete" in body) {
    const v = String(body.perm_delete ?? "");
    if (v !== "admins" && v !== "creator") {
      return json(400, { error: "admins only, or the creator and admins" }, cors);
    }
    await put("perm_delete", v);
  }

  await logActivity(env, actor, "settings.update",
    String(actor.name ?? "") + " changed the team settings",
    "changed the team settings", "");
  return json(200, { ok: true }, cors);
}
