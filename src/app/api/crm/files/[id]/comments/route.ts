import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { resolveActingUserId } from "@/lib/crm/identity";

export async function GET(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const { data, error } = await crmDb()
    .from("crm_file_comments")
    .select("*, author:crm_users!crm_file_comments_author_user_id_fkey(name)")
    .eq("file_id", params.id)
    .order("created_at", { ascending: true });
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ comments: data ?? [] });
}

export async function POST(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const me = await resolveActingUserId(req);
  const body = await req.json().catch(() => ({}));
  const text = (body.body || "").trim();
  if (!text) return NextResponse.json({ error: "Empty comment" }, { status: 400 });
  const { data, error } = await crmDb()
    .from("crm_file_comments")
    .insert({ file_id: params.id, author_user_id: me, body: text })
    .select("*, author:crm_users!crm_file_comments_author_user_id_fkey(name)")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ comment: data });
}
