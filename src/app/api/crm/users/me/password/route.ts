/**
 * POST /api/crm/users/me/password { current_password, new_password }
 * Allows any signed-in user to rotate their own password. Requires the
 * current password; rate-limited by IP to slow brute-force attempts.
 */
import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmSession } from "@/lib/crm/auth";
import { hashPassword, verifyPassword } from "@/lib/crm/password";
import { rateLimit, clientIp } from "@/lib/crm/rate-limit";

export async function POST(req: Request) {
  const r = requireCrmSession(req);
  if (r.error) return r.error;
  const ip = clientIp(req);
  const limit = rateLimit(`crm-pw:${ip}`, 12, 60 * 1000);
  if (!limit.allowed) {
    return NextResponse.json({ error: "Too many attempts" }, { status: 429 });
  }
  let body: { current_password?: string; new_password?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }
  const cur = body.current_password || "";
  const next = body.new_password || "";
  if (next.length < 4) {
    return NextResponse.json(
      { error: "New password must be at least 4 characters" },
      { status: 400 }
    );
  }
  const db = crmDb();
  const { data: user } = await db
    .from("crm_users")
    .select("password_hash")
    .eq("id", r.session.user_id)
    .maybeSingle();
  if (!user) return NextResponse.json({ error: "Unknown user" }, { status: 404 });
  if (user.password_hash) {
    const ok = await verifyPassword(cur, user.password_hash);
    if (!ok) {
      return NextResponse.json({ error: "Wrong current password" }, { status: 401 });
    }
  }
  let hash: string;
  try {
    hash = await hashPassword(next);
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "Bad password" }, { status: 400 });
  }
  const { error } = await db
    .from("crm_users")
    .update({ password_hash: hash })
    .eq("id", r.session.user_id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true });
}
