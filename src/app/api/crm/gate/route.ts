/**
 * GET    /api/crm/gate                            -> { ok, session?: {user_id, name, is_admin} }
 * POST   /api/crm/gate { user_id, password }      -> 200 + sets HttpOnly cookie on success
 *                                                   First-time login: if the user has no password
 *                                                   stored yet, the submitted password is set as theirs.
 * DELETE /api/crm/gate                            -> clears cookie.
 */
import { NextResponse } from "next/server";
import { rateLimit, clientIp } from "@/lib/crm/rate-limit";
import {
  buildClearCrmGateHeader,
  buildSetCrmGateHeader,
  readCrmSessionFromRequest,
} from "@/lib/crm/gate";
import { crmDb } from "@/lib/crm/db";
import { hashPassword, verifyPassword } from "@/lib/crm/password";

export async function GET(req: Request) {
  const session = readCrmSessionFromRequest(req);
  if (!session) return NextResponse.json({ ok: false });
  const { data } = await crmDb()
    .from("crm_users")
    .select("id, name, email, is_admin")
    .eq("id", session.user_id)
    .maybeSingle();
  if (!data) return NextResponse.json({ ok: false });
  return NextResponse.json({
    ok: true,
    session: {
      user_id: data.id,
      name: data.name,
      email: data.email,
      is_admin: data.is_admin === true,
    },
  });
}

export async function POST(req: Request) {
  const ip = clientIp(req);
  const limit = rateLimit(`crm-gate:${ip}`, 8, 60 * 1000);
  if (!limit.allowed) {
    return NextResponse.json({ error: "Too many attempts" }, { status: 429 });
  }
  let body: { user_id?: string; password?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }
  const userId = (body.user_id || "").trim();
  const password = body.password || "";
  if (!userId || password.length < 4) {
    return NextResponse.json({ error: "User and password required" }, { status: 400 });
  }
  const db = crmDb();
  const { data: user, error } = await db
    .from("crm_users")
    .select("id, name, password_hash, is_admin")
    .eq("id", userId)
    .maybeSingle();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  if (!user) return NextResponse.json({ error: "Unknown user" }, { status: 401 });

  if (!user.password_hash) {
    // First-time login: set this password as the user's own.
    let hash: string;
    try {
      hash = await hashPassword(password);
    } catch (e: any) {
      return NextResponse.json({ error: e?.message || "Bad password" }, { status: 400 });
    }
    const upd = await db
      .from("crm_users")
      .update({ password_hash: hash })
      .eq("id", user.id);
    if (upd.error) {
      return NextResponse.json({ error: upd.error.message }, { status: 500 });
    }
  } else {
    const ok = await verifyPassword(password, user.password_hash);
    if (!ok) return NextResponse.json({ error: "Wrong password" }, { status: 401 });
  }

  const res = NextResponse.json({
    ok: true,
    session: {
      user_id: user.id,
      name: user.name,
      is_admin: user.is_admin === true,
    },
  });
  res.headers.set(
    "Set-Cookie",
    buildSetCrmGateHeader({ user_id: user.id, is_admin: user.is_admin === true })
  );
  return res;
}

export async function DELETE() {
  const res = new NextResponse(null, { status: 204 });
  res.headers.set("Set-Cookie", buildClearCrmGateHeader());
  return res;
}
