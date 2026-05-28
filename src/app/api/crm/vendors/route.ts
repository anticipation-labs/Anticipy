import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const { data, error } = await crmDb()
    .from("crm_vendors")
    .select("*, contact:crm_contacts(name, email)")
    .order("name", { ascending: true });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ vendors: data ?? [] });
}

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const body = await req.json().catch(() => ({}));
  const name = (body.name || "").trim();
  if (!name) return NextResponse.json({ error: "name required" }, { status: 400 });
  const { data, error } = await crmDb()
    .from("crm_vendors")
    .upsert({ name, contact_id: body.contact_id || null, notes: body.notes || null }, { onConflict: "name" })
    .select("*")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ vendor: data });
}
