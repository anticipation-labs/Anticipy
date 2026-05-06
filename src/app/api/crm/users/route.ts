import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { CRM_GATE_COOKIE, verifyCrmGate } from "@/lib/crm/gate";

function requireGate(req: Request): NextResponse | null {
  const c = req.headers
    .get("cookie")
    ?.split(";")
    .find((s) => s.trim().startsWith(`${CRM_GATE_COOKIE}=`))
    ?.split("=")[1];
  if (!verifyCrmGate(c)) {
    return NextResponse.json({ error: "Locked" }, { status: 401 });
  }
  return null;
}

export async function GET(req: Request) {
  const guard = requireGate(req);
  if (guard) return guard;
  const { data, error } = await crmDb()
    .from("crm_users")
    .select("*")
    .order("created_at", { ascending: true });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ users: data ?? [] });
}

export async function POST(req: Request) {
  const guard = requireGate(req);
  if (guard) return guard;
  let body: { name?: string; email?: string | null } = {};
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
  const { data, error } = await crmDb()
    .from("crm_users")
    .insert({ name, email })
    .select("*")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ user: data });
}
