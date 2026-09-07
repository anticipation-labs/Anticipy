/** An authenticated operator can fulfill a verified account erasure request.
 * Requires the canonical record AND both of the owner's supplied identifiers.
 * Uses the public erasure implementation, including provider revocation and
 * permanent write fences; never an ad-hoc DELETE or a password change. */
import { eraseVerifiedOwner, type AccountErasureEnv } from "./account_delete.ts";

export async function adminAccountReset(request: Request,
  env: AccountErasureEnv & { ANTICIPY_INTERNAL_KEY?: string }): Promise<Response> {
  const answer = (status: number, error: string) => Response.json({ ok: false, error }, { status });
  if (request.method !== "POST") return answer(405, "POST required");
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return answer(503, "Unavailable");
  const got = request.headers.get("X-Internal-Key") || "";
  let diff = got.length ^ key.length;
  for (let i = 0; i < key.length; i++) diff |= key.charCodeAt(i) ^ (got.charCodeAt(i) || 0);
  if (diff) return answer(401, "Unauthorized");
  let body: Record<string, unknown>;
  try { body = await request.json(); } catch { return answer(400, "Invalid request"); }
  if (!body || body.confirm !== "DELETE PRODUCT ACCOUNT"
      || typeof body.owner_ref !== "string" || !/^[a-z0-9]{15}$/.test(body.owner_ref)
      || typeof body.email !== "string" || !body.email.trim()
      || typeof body.phone !== "string" || !/^\+[1-9][0-9]{7,14}$/.test(body.phone)) {
    return answer(400, "Canonical identity, email, E.164 phone and explicit confirmation required");
  }
  const owner = await env.DB.prepare("SELECT id,email FROM owners WHERE id=?")
    .bind(body.owner_ref).first<{id: string; email: string}>();
  const profile = await env.DB.prepare(
    "SELECT email,phone FROM owner_profile WHERE owner_ref=? ORDER BY updated DESC,created DESC,id DESC LIMIT 1",
  ).bind(body.owner_ref).first<{email: string; phone: string}>();
  const email = body.email.trim().toLowerCase();
  if (!owner || !profile || owner.email.trim().toLowerCase() !== email
      || profile.email.trim().toLowerCase() !== email || profile.phone.trim() !== body.phone) {
    return answer(409, "Account identity did not match; nothing was erased");
  }
  return eraseVerifiedOwner(owner.id, env);
}
