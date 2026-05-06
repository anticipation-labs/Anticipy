/**
 * Server-side helper to read the acting user from the x-crm-user-* request
 * headers. The picker on the client populates these on every fetch via
 * crmFetch. Trusted only because the gate cookie has already been verified
 * upstream of the route handler.
 */
import { crmDb } from "./db";

export interface ActingUser {
  id: string | null;
  name: string | null;
}

export function readActingUser(req: Request): ActingUser {
  const id = req.headers.get("x-crm-user-id");
  const name = req.headers.get("x-crm-user-name");
  return {
    id: id && id.length === 36 ? id : null,
    name: name || null,
  };
}

export async function resolveActingUserId(req: Request): Promise<string | null> {
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
