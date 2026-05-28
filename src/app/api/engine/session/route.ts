import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { requireSupabaseUser } from "@/lib/require-auth";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabaseAdmin
    .from("anticipy_sessions")
    .insert({
      status: "recording",
      user_id: user.id,
      user_email: user.email ?? null,
    })
    .select("id")
    .single();

  if (error) {
    console.error("Session insert error:", error);
    return NextResponse.json(
      { error: "Could not create session." },
      { status: 500 }
    );
  }

  return NextResponse.json({ sessionId: data.id });
}

export async function PATCH(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { sessionId, status, totalAudioSeconds } = await req.json();
  if (!sessionId || typeof sessionId !== "string") {
    return NextResponse.json({ error: "Missing sessionId" }, { status: 400 });
  }

  // Only allow updating sessions owned by this user. Without this check, any
  // authed user who knows another user's session UUID could end their
  // recording or rewrite their status field.
  const { data: existing } = await supabaseAdmin
    .from("anticipy_sessions")
    .select("user_id")
    .eq("id", sessionId)
    .single();
  if (!existing || (existing.user_id && existing.user_id !== user.id)) {
    return NextResponse.json({ error: "Session not found" }, { status: 404 });
  }

  const update: Record<string, unknown> = {};
  if (status) update.status = status;
  if (totalAudioSeconds != null) update.total_audio_seconds = totalAudioSeconds;
  if (status === "ended") update.ended_at = new Date().toISOString();

  const { error } = await supabaseAdmin
    .from("anticipy_sessions")
    .update(update)
    .eq("id", sessionId);

  if (error) {
    console.error("Session update error:", error);
    return NextResponse.json(
      { error: "Could not update session." },
      { status: 500 }
    );
  }

  return NextResponse.json({ ok: true });
}
