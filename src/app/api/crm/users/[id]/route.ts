/**
 * PATCH  /api/crm/users/:id    -> admin only. Update name, email, is_admin.
 * DELETE /api/crm/users/:id    -> admin only. Refuses to delete the last admin
 *                                  or the caller themselves.
 */
import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmAdmin } from "@/lib/crm/auth";

export async function PATCH(
  req: Request,
  { params }: { params: { id: string } }
) {
  const r = requireCrmAdmin(req);
  if (r.error) return r.error;
  let body: { name?: string; email?: string | null; is_admin?: boolean } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }
  const update: Record<string, any> = {};
  if (typeof body.name === "string") {
    const n = body.name.trim();
    if (n.length < 1 || n.length > 60) {
      return NextResponse.json({ error: "Name must be 1 to 60 chars" }, { status: 400 });
    }
    update.name = n;
  }
  if (body.email !== undefined) {
    update.email = body.email && body.email.trim().length > 0 ? body.email.trim() : null;
  }
  if (typeof body.is_admin === "boolean") {
    if (!body.is_admin) {
      // Refuse to demote the last admin.
      const db = crmDb();
      const { count } = await db
        .from("crm_users")
        .select("id", { count: "exact", head: true })
        .eq("is_admin", true);
      if ((count ?? 0) <= 1) {
        return NextResponse.json(
          { error: "Cannot remove the last admin" },
          { status: 400 }
        );
      }
    }
    update.is_admin = body.is_admin;
  }
  if (Object.keys(update).length === 0) {
    return NextResponse.json({ error: "Nothing to update" }, { status: 400 });
  }
  const { data, error } = await crmDb()
    .from("crm_users")
    .update(update)
    .eq("id", params.id)
    .select("id, name, email, is_admin, password_hash, created_at")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({
    user: {
      id: data.id,
      name: data.name,
      email: data.email,
      is_admin: data.is_admin === true,
      has_password: !!data.password_hash,
      created_at: data.created_at,
    },
  });
}

export async function DELETE(
  req: Request,
  { params }: { params: { id: string } }
) {
  const r = requireCrmAdmin(req);
  if (r.error) return r.error;
  if (params.id === r.session.user_id) {
    return NextResponse.json(
      { error: "You cannot delete yourself" },
      { status: 400 }
    );
  }
  const db = crmDb();
  const { data: target } = await db
    .from("crm_users")
    .select("id, is_admin")
    .eq("id", params.id)
    .maybeSingle();
  if (!target) return NextResponse.json({ error: "Not found" }, { status: 404 });
  if (target.is_admin === true) {
    const { count } = await db
      .from("crm_users")
      .select("id", { count: "exact", head: true })
      .eq("is_admin", true);
    if ((count ?? 0) <= 1) {
      return NextResponse.json(
        { error: "Cannot delete the last admin" },
        { status: 400 }
      );
    }
  }
  const { error } = await db.from("crm_users").delete().eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true });
}
