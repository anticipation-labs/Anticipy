import { NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { CRM_FILES_BUCKET, crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { resolveActingUserId } from "@/lib/crm/identity";
import { transcribe } from "@/lib/crm/deepgram";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const url = new URL(req.url);
  const userId = url.searchParams.get("user_id");
  let q = crmDb()
    .from("crm_voice_memos")
    .select("*, user:crm_users(name)")
    .order("recorded_date", { ascending: false })
    .order("created_at", { ascending: false })
    .limit(120);
  if (userId) q = q.eq("user_id", userId);
  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ memos: data ?? [] });
}

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const me = await resolveActingUserId(req);
  if (!me) return NextResponse.json({ error: "Pick a user first" }, { status: 400 });

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "Expected multipart" }, { status: 400 });
  }
  const file = formData.get("audio");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "audio file required" }, { status: 400 });
  }
  if (file.size > 10 * 1024 * 1024) {
    return NextResponse.json({ error: "Recording too large" }, { status: 413 });
  }

  const buf = Buffer.from(await file.arrayBuffer());
  const today = new Date().toISOString().slice(0, 10);
  const ext = (file.type.split("/")[1] || "webm").split(";")[0] || "webm";
  const path = `voice/${today}/${me}/${randomUUID()}.${ext}`;

  const db = crmDb();
  const { error: upErr } = await db.storage
    .from(CRM_FILES_BUCKET)
    .upload(path, buf, { contentType: file.type || "audio/webm", upsert: false });
  if (upErr) return NextResponse.json({ error: upErr.message }, { status: 500 });

  let transcript = "";
  let duration: number | null = null;
  try {
    const t = await transcribe(buf, file.type || "audio/webm");
    transcript = t.transcript;
    duration = t.duration;
  } catch (e: any) {
    transcript = "";
  }

  const { data, error } = await db
    .from("crm_voice_memos")
    .insert({
      user_id: me,
      audio_storage_path: path,
      transcript,
      duration_seconds: duration,
      recorded_date: today,
    })
    .select("*")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ memo: data });
}
