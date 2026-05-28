import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { resolveActingUserId } from "@/lib/crm/identity";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const url = new URL(req.url);
  const search = url.searchParams.get("q");
  const tag = url.searchParams.get("tag");
  let q = crmDb()
    .from("crm_decisions")
    .select("*, decided_by:crm_users(name)")
    .order("decided_at", { ascending: false })
    .limit(500);
  if (search) q = q.or(`title.ilike.%${search}%,body.ilike.%${search}%`);
  if (tag) q = q.contains("tags", [tag]);
  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ decisions: data ?? [] });
}

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const me = await resolveActingUserId(req);
  const body = await req.json().catch(() => ({}));
  const title = (body.title || "").trim();
  if (!title) return NextResponse.json({ error: "title required" }, { status: 400 });
  const { data, error } = await crmDb()
    .from("crm_decisions")
    .insert({
      title,
      body: body.body || null,
      decided_at: body.decided_at || new Date().toISOString().slice(0, 10),
      decided_by_user_id: me,
      tags: Array.isArray(body.tags) ? body.tags : [],
    })
    .select("*, decided_by:crm_users(name)")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ decision: data });
}
