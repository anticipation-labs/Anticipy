import { NextResponse } from "next/server";
import { requireSupabaseUser } from "@/lib/require-auth";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const dynamic = "force-dynamic";

function str(value: unknown, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function obj(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function arr(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function num(value: unknown, fallback = 0) {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export async function POST(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  }

  const body = (await req.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body || typeof body !== "object") {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }

  const ingestId = str(body.ingest_id).slice(0, 120);
  const transcript = str(body.transcript).slice(0, 8000);
  if (!ingestId || !transcript) {
    return NextResponse.json(
      { ok: false, error: "ingest_id and transcript are required" },
      { status: 400 }
    );
  }

  const row = {
    user_id: user.id,
    ingest_id: ingestId,
    source: str(body.source, "unknown").slice(0, 80),
    transcript,
    reference: str(body.reference).slice(0, 120),
    resolved_to: str(body.resolved_to) || null,
    layer_used: Math.max(0, Math.floor(num(body.layer_used))),
    confidence: Math.max(0, Math.min(1, num(body.confidence))),
    confirm_card_surfaced: Boolean(body.confirm_card_surfaced),
    candidates: arr(body.candidates),
    plan: obj(body.plan),
  };

  const { data, error } = await supabaseAdmin
    .from("resolution_traces")
    .insert(row)
    .select("id")
    .single();

  if (error) {
    return NextResponse.json(
      { ok: false, error: error.message },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true, id: data?.id, ingest_id: ingestId });
}
