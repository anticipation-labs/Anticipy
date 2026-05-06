/**
 * Server-side helper to read the acting user from the signed session cookie.
 * The cookie binds {user_id, is_admin}, so the route handler does not need to
 * trust client-provided headers for attribution.
 *
 * Falls back to the legacy x-crm-user-* headers only if the cookie is missing
 * a user_id (older sessions); after the next login the cookie is authoritative.
 */
import { crmDb } from "./db";
import { readCrmSessionFromRequest } from "./gate";

export interface ActingUser {
  id: string | null;
  name: string | null;
}

export function readActingUser(req: Request): ActingUser {
  const session = readCrmSessionFromRequest(req);
  if (session?.user_id) {
    return { id: session.user_id, name: null };
  }
  const id = req.headers.get("x-crm-user-id");
  const name = req.headers.get("x-crm-user-name");
  return {
    id: id && id.length === 36 ? id : null,
    name: name || null,
  };
}

export async function resolveActingUserId(req: Request): Promise<string | null> {
  const session = readCrmSessionFromRequest(req);
  if (session?.user_id) return session.user_id;
  const { id, name } = readActingUser(req);
  if (id) return id;
  if (!name) return null;
  const { data } = await crmDb()
    .from("crm_users")
    .select("id")
    .eq("name", name)
    .maybeSingle();
  return data?.id ?? null;
}
