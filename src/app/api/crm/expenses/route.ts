import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;

  const url = new URL(req.url);
  const from = url.searchParams.get("from");
  const to = url.searchParams.get("to");
  const category = url.searchParams.get("category");
  const status = url.searchParams.get("status");
  const productTag = url.searchParams.get("product_tag");
  const paidBy = url.searchParams.get("paid_by");
  const limit = Math.min(parseInt(url.searchParams.get("limit") || "200"), 1000);

  let q = crmDb()
    .from("crm_expenses")
    .select("*, vendor:crm_vendors(name), paid_by:crm_users!crm_expenses_paid_by_user_id_fkey(name)")
    .order("date", { ascending: false, nullsFirst: false })
    .order("created_at", { ascending: false })
    .limit(limit);

  if (from) q = q.gte("date", from);
  if (to) q = q.lte("date", to);
  if (category) q = q.eq("category", category);
  if (status) q = q.eq("status", status);
  if (productTag) q = q.eq("product_tag", productTag);
  if (paidBy) q = q.eq("paid_by_user_id", paidBy);

  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ expenses: data ?? [] });
}

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;

  let body: any = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  const db = crmDb();

  // Auto-create vendor if a name was provided.
  let vendorId: string | null = body.vendor_id ?? null;
  if (!vendorId && body.vendor_name && typeof body.vendor_name === "string") {
    const name = body.vendor_name.trim();
    if (name) {
      const { data: existing } = await db
        .from("crm_vendors")
        .select("id")
        .eq("name", name)
        .maybeSingle();
      if (existing?.id) {
        vendorId = existing.id;
      } else {
        const { data: created, error: vErr } = await db
          .from("crm_vendors")
          .insert({ name })
          .select("id")
          .single();
        if (vErr) {
          return NextResponse.json({ error: vErr.message }, { status: 400 });
        }
        vendorId = created?.id ?? null;
      }
    }
  }

  const insert = {
    vendor_id: vendorId,
    amount_cents: clampInt(body.amount_cents, 0, 1_000_000_00) ?? 0,
    currency: typeof body.currency === "string" ? body.currency : "CAD",
    date: typeof body.date === "string" ? body.date : null,
    category: body.category ?? null,
    payment_method: body.payment_method ?? null,
    paid_by_user_id: body.paid_by_user_id ?? null,
    product_tag: body.product_tag ?? "anticipy",
    reimbursable: !!body.reimbursable,
    gst_cents: clampInt(body.gst_cents, 0, 1_000_000_00),
    pst_cents: clampInt(body.pst_cents, 0, 1_000_000_00),
    receipt_storage_paths: Array.isArray(body.receipt_storage_paths)
      ? body.receipt_storage_paths.filter((s: any) => typeof s === "string")
      : [],
    raw_extraction_jsonb: body.raw_extraction_jsonb ?? null,
    extraction_confidence:
      typeof body.extraction_confidence === "number" ? body.extraction_confidence : null,
    status: body.status ?? "confirmed",
    missing_fields: Array.isArray(body.missing_fields) ? body.missing_fields : [],
    notes: typeof body.notes === "string" ? body.notes : null,
  };

  const { data, error } = await db
    .from("crm_expenses")
    .insert(insert)
    .select("*")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ expense: data });
}

function clampInt(v: unknown, lo: number, hi: number): number | null {
  if (v == null) return null;
  if (typeof v !== "number" || !Number.isFinite(v)) return null;
  return Math.max(lo, Math.min(hi, Math.round(v)));
}
