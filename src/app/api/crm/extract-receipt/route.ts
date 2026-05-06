import { NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { CRM_FILES_BUCKET, crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { extractReceipt } from "@/lib/crm/gemini";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "Expected multipart/form-data" }, { status: 400 });
  }

  const files = formData.getAll("files").filter((f): f is File => f instanceof File);
  if (files.length === 0) {
    return NextResponse.json({ error: "No files provided" }, { status: 400 });
  }
  if (files.length > 6) {
    return NextResponse.json({ error: "Up to 6 photos per receipt" }, { status: 400 });
  }

  const db = crmDb();
  const uploadedPaths: string[] = [];
  const images: { mimeType: string; base64: string }[] = [];

  for (const f of files) {
    if (f.size > 15 * 1024 * 1024) {
      return NextResponse.json({ error: `${f.name} exceeds 15MB` }, { status: 400 });
    }
    const buffer = Buffer.from(await f.arrayBuffer());
    const ext = f.name.split(".").pop()?.toLowerCase() || "jpg";
    const path = `receipts/${new Date().toISOString().slice(0, 10)}/${randomUUID()}.${ext}`;
    const { error: upErr } = await db.storage
      .from(CRM_FILES_BUCKET)
      .upload(path, buffer, {
        contentType: f.type || "image/jpeg",
        upsert: false,
      });
    if (upErr) {
      return NextResponse.json({ error: `Upload failed: ${upErr.message}` }, { status: 500 });
    }
    uploadedPaths.push(path);
    images.push({
      mimeType: f.type || "image/jpeg",
      base64: buffer.toString("base64"),
    });
  }

  try {
    const extraction = await extractReceipt(images);
    return NextResponse.json({ storage_paths: uploadedPaths, extraction });
  } catch (e: any) {
    return NextResponse.json(
      {
        storage_paths: uploadedPaths,
        extraction: null,
        error: e?.message || "Extraction failed",
      },
      { status: 200 }
    );
  }
}
