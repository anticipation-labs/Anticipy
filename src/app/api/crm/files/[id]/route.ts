import { NextResponse } from "next/server";
import { CRM_FILES_BUCKET, crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const { data, error } = await crmDb()
    .from("crm_files")
    .select(
      "*, uploader:crm_users!crm_files_uploaded_by_user_id_fkey(name), vendor:crm_vendors(name)"
    )
    .eq("id", params.id)
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 404 });
  return NextResponse.json({ file: data });
}

export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const body = await req.json().catch(() => ({}));
  const { error } = await crmDb()
    .from("crm_files")
    .update({
      description: body.description ?? null,
      vendor_id: body.vendor_id ?? null,
      project_folder: body.project_folder ?? undefined,
    })
    .eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true });
}

export async function DELETE(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const db = crmDb();
  const { data: row } = await db.from("crm_files").select("storage_path").eq("id", params.id).maybeSingle();
  await db.from("crm_files").delete().eq("id", params.id);
  if (row?.storage_path) {
    await db.storage.from(CRM_FILES_BUCKET).remove([row.storage_path]);
  }
  return new NextResponse(null, { status: 204 });
}
