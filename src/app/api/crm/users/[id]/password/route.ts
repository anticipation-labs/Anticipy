/**
 * POST /api/crm/users/:id/password { password } -> admin only. Sets a new
 * password for the target user. To clear a password (so the next sign-in
 * re-runs first-time setup), pass { clear: true }.
 */
import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmAdmin } from "@/lib/crm/auth";
import { hashPassword } from "@/lib/crm/password";

export async function POST(
  req: Request,
  { params }: { params: { id: string } }
) {
  const r = requireCrmAdmin(req);
  if (r.error) return r.error;
  let body: { password?: string; clear?: boolean } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }
  if (body.clear === true) {
    const { error } = await crmDb()
      .from("crm_users")
      .update({ password_hash: null })
      .eq("id", params.id);
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true, cleared: true });
  }
  if (typeof body.password !== "string" || body.password.length < 4) {
    return NextResponse.json(
      { error: "Password must be at least 4 characters" },
      { status: 400 }
    );
  }
  let hash: string;
  try {
    hash = await hashPassword(body.password);
  } catch (e: any) {
    return NextResponse.json({ error: e?.message || "Bad password" }, { status: 400 });
  }
  const { error } = await crmDb()
    .from("crm_users")
    .update({ password_hash: hash })
    .eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true });
}
