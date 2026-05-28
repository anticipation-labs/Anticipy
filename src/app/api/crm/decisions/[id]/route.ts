import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const body = await req.json().catch(() => ({}));
  const update: Record<string, unknown> = {};
  for (const k of ["title", "body", "decided_at", "tags"]) if (k in body) update[k] = body[k];
  const { error } = await crmDb().from("crm_decisions").update(update).eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true });
}

export async function DELETE(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const { error } = await crmDb().from("crm_decisions").delete().eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return new NextResponse(null, { status: 204 });
}
