/**
 * GET  /api/crm/users  -> list. Gate required, with no exceptions.
 * POST /api/crm/users  -> admin only. Creates a new user; an initial password
 *                         may be supplied, otherwise the user sets one on
 *                         their first sign-in.
 *
 * SECURITY: this route previously honoured `?for=login`, which skipped the
 * gate entirely and returned every user's id, name, email and whether they
 * had a password set — unauthenticated, to anyone on the internet. It was
 * intended to let a login picker render before sign-in. In combination with
 * the first-login password-claim path in /api/crm/gate, it also told an
 * attacker in real time exactly which account was claimable.
 *
 * The bypass is removed. A login screen must ask the user who they are
 * rather than being handed the directory.
 */
import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmAdmin, requireCrmGate } from "@/lib/crm/auth";
import { hashPassword } from "@/lib/crm/password";
import { rateLimit, clientIp } from "@/lib/crm/rate-limit";

export async function GET(req: Request) {
  const guard = requireCrmGate(req);
  if (guard) return guard;
  const { data, error } = await crmDb()
    .from("crm_users")
    .select("id, name, email, is_admin, created_at, password_hash")
    .order("created_at", { ascending: true });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  const users = (data ?? []).map((u: any) => ({
    id: u.id,
    name: u.name,
    email: u.email,
    is_admin: u.is_admin === true,
    created_at: u.created_at,
    has_password: !!u.password_hash,
  }));
  return NextResponse.json({ users });
}

export async function POST(req: Request) {
  const r = requireCrmAdmin(req);
  if (r.error) return r.error;
  let body: {
    name?: string;
    email?: string | null;
    password?: string;
    is_admin?: boolean;
  } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }
  const name = (body.name || "").trim();
  if (name.length < 1 || name.length > 60) {
    return NextResponse.json({ error: "Name must be 1 to 60 chars" }, { status: 400 });
  }
  const email = body.email && body.email.trim().length > 0 ? body.email.trim() : null;
  const isAdmin = body.is_admin === true;
  const insert: Record<string, any> = { name, email, is_admin: isAdmin };
  if (typeof body.password === "string" && body.password.length > 0) {
    try {
      insert.password_hash = await hashPassword(body.password);
    } catch (e: any) {
      return NextResponse.json({ error: e?.message || "Bad password" }, { status: 400 });
    }
  }
  const { data, error } = await crmDb()
    .from("crm_users")
    .insert(insert)
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
