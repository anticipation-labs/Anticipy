import { NextResponse } from "next/server";
import * as XLSX from "xlsx";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;

  const url = new URL(req.url);
  const format = (url.searchParams.get("format") || "xlsx").toLowerCase();
  const from = url.searchParams.get("from");
  const to = url.searchParams.get("to");

  let q = crmDb()
    .from("crm_expenses")
    .select(
      "date, amount_cents, currency, category, payment_method, product_tag, reimbursable, gst_cents, pst_cents, status, notes, vendor:crm_vendors(name), paid_by:crm_users!crm_expenses_paid_by_user_id_fkey(name)"
    )
    .order("date", { ascending: false, nullsFirst: false });
  if (from) q = q.gte("date", from);
  if (to) q = q.lte("date", to);

  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const rows = (data ?? []).map((r: any) => ({
    Date: r.date,
    Vendor: r.vendor?.name ?? "",
    Amount: (r.amount_cents ?? 0) / 100,
    Currency: r.currency,
    Category: r.category,
    "Payment method": r.payment_method,
    "Paid by": r.paid_by?.name ?? "",
    "Product tag": r.product_tag,
    Reimbursable: r.reimbursable ? "yes" : "no",
    GST: r.gst_cents == null ? "" : r.gst_cents / 100,
    PST: r.pst_cents == null ? "" : r.pst_cents / 100,
    Status: r.status,
    Notes: r.notes ?? "",
  }));

  const today = new Date().toISOString().slice(0, 10);

  if (format === "csv") {
    const ws = XLSX.utils.json_to_sheet(rows);
    const csv = XLSX.utils.sheet_to_csv(ws);
    return new NextResponse(csv, {
      status: 200,
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": `attachment; filename="anticipy-expenses-${today}.csv"`,
      },
    });
  }

  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.json_to_sheet(rows);
  XLSX.utils.book_append_sheet(wb, ws, "Expenses");
  const buf = XLSX.write(wb, { type: "buffer", bookType: "xlsx" });
  return new NextResponse(buf, {
    status: 200,
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="anticipy-expenses-${today}.xlsx"`,
    },
  });
}
