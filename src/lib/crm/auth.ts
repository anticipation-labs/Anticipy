/**
 * Reusable session guards for CRM API routes.
 *
 * The cookie is HMAC-signed with the user's id + admin flag, so we can return
 * the session directly without an extra database hit. Routes that need the
 * latest is_admin (e.g. user management) should re-check the database row.
 */
import { NextResponse } from "next/server";
import { readCrmSessionFromRequest, type CrmSession } from "./gate";

export function requireCrmSession(req: Request):
  | { session: CrmSession; error: null }
  | { session: null; error: NextResponse } {
  const session = readCrmSessionFromRequest(req);
  if (!session) {
    return {
      session: null,
      error: NextResponse.json({ error: "Locked" }, { status: 401 }),
    };
  }
  return { session, error: null };
}

/**
 * Back-compat shim for older routes that just want a 401 if the cookie is bad.
 * Prefer `requireCrmSession` in new code so you can attribute writes to a user.
 */
export function requireCrmGate(req: Request): NextResponse | null {
  const { error } = requireCrmSession(req);
  return error;
}

export function requireCrmAdmin(req: Request):
  | { session: CrmSession; error: null }
  | { session: null; error: NextResponse } {
  const r = requireCrmSession(req);
  if (r.error) return r;
  if (!r.session.is_admin) {
    return {
      session: null,
      error: NextResponse.json({ error: "Admin only" }, { status: 403 }),
    };
  }
  return r;
}
