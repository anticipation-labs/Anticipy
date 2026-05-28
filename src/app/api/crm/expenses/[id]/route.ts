import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const body = await req.json().catch(() => ({}));
  const allowed = [
    "vendor_id",
    "amount_cents",
    "currency",
    "date",
    "category",
    "payment_method",
    "paid_by_user_id",
    "product_tag",
    "reimbursable",
    "gst_cents",
    "pst_cents",
    "receipt_storage_paths",
    "status",
    "missing_fields",
    "notes",
  ];
  const update: Record<string, unknown> = {};
  for (const k of allowed) {
    if (k in body) update[k] = body[k];
  }
  const { data, error } = await crmDb()
    .from("crm_expenses")
    .update(update)
    .eq("id", params.id)
    .select("*")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ expense: data });
}

export async function DELETE(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const { error } = await crmDb().from("crm_expenses").delete().eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return new NextResponse(null, { status: 204 });
}
