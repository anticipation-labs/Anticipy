import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const url = new URL(req.url);
  const search = url.searchParams.get("q");
  const source = url.searchParams.get("source");
  let q = crmDb()
    .from("crm_contacts")
    .select("*")
    .order("name", { ascending: true })
    .limit(2000);
  if (source) q = q.eq("source", source);
  if (search) q = q.or(`name.ilike.%${search}%,email.ilike.%${search}%,role.ilike.%${search}%`);
  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ contacts: data ?? [] });
}

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const body = await req.json().catch(() => ({}));
  const name = (body.name || "").trim();
  if (!name) return NextResponse.json({ error: "name required" }, { status: 400 });
  const { data, error } = await crmDb()
    .from("crm_contacts")
    .insert({
      name,
      email: body.email || null,
      phone: body.phone || null,
      role: body.role || null,
      source: body.source || "manual",
      notes: body.notes || null,
    })
    .select("*")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ contact: data });
}
