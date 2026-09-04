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
 */
import { verifyToken, type AuthEnv } from "../pb/auth.ts";

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

export async function authClaim(req: Request, env: ServiceEnv): Promise<Response> {
  const auth = await verifyToken(env, req.headers.get("Authorization") || "");
  if (!auth) return signIn();
  return json(503, { ok: false, message: "claim not yet ported" });
}

export async function phoneRemove(req: Request, env: ServiceEnv): Promise<Response> {
  const auth = await verifyToken(env, req.headers.get("Authorization") || "");
  if (!auth) return signIn();
  return json(503, { ok: false, message: "phone removal not yet ported" });
}

export async function profileUpsert(req: Request, env: ServiceEnv): Promise<Response> {
  const auth = await verifyToken(env, req.headers.get("Authorization") || "");
  if (!auth) return signIn();
  return json(503, { ok: false, message: "profile upsert not yet ported" });
}
