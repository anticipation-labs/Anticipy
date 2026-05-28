import { NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { CRM_FILES_BUCKET, crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { resolveActingUserId } from "@/lib/crm/identity";

export const runtime = "nodejs";
export const maxDuration = 120;

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const url = new URL(req.url);
  const folder = url.searchParams.get("folder");
  const search = url.searchParams.get("q");
  let q = crmDb()
    .from("crm_files")
    .select(
      "*, uploader:crm_users!crm_files_uploaded_by_user_id_fkey(name), vendor:crm_vendors(name), comment_count:crm_file_comments(count)"
    )
    .order("created_at", { ascending: false })
    .limit(500);
  if (folder) q = q.eq("project_folder", folder);
  if (search) {
    q = q.or(`filename.ilike.%${search}%,description.ilike.%${search}%`);
  }
  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ files: data ?? [] });
}

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const me = await resolveActingUserId(req);
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "Expected multipart" }, { status: 400 });
  }
  const folder = String(formData.get("folder") || "other").toLowerCase().trim();
  const description = formData.get("description")?.toString() || null;
  const vendorId = formData.get("vendor_id")?.toString() || null;
  const files = formData.getAll("files").filter((f): f is File => f instanceof File);
  if (files.length === 0) return NextResponse.json({ error: "No files" }, { status: 400 });
  const db = crmDb();
  const created: any[] = [];
  for (const f of files) {
    const safeName = f.name.replace(/[^a-zA-Z0-9._-]/g, "_");
    const path = `manufacturing/${folder}/${randomUUID()}-${safeName}`;
    const buf = Buffer.from(await f.arrayBuffer());
    const { error: upErr } = await db.storage
      .from(CRM_FILES_BUCKET)
      .upload(path, buf, { contentType: f.type || "application/octet-stream", upsert: false });
    if (upErr) {
      return NextResponse.json({ error: upErr.message }, { status: 500 });
    }
    const { data, error } = await db
      .from("crm_files")
      .insert({
        project_folder: folder,
        filename: f.name,
        storage_path: path,
        mime_type: f.type || null,
        size_bytes: f.size,
        uploaded_by_user_id: me,
        description,
        vendor_id: vendorId,
      })
      .select("*")
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    created.push(data);
  }
  return NextResponse.json({ files: created });
}
