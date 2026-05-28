import { NextResponse } from "next/server";
import { requireSupabaseUser } from "@/lib/require-auth";
import { supabaseAdmin } from "@/lib/supabase-admin";

export const dynamic = "force-dynamic";

function objectOrEmpty(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function arrayOrEmpty(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function countFacts(value: unknown): number {
  if (value === null || value === undefined || value === "") return 0;
  if (Array.isArray(value)) {
    return value.reduce((sum, item) => sum + countFacts(item), 0);
  }
  if (typeof value === "object") {
    return Object.values(value as Record<string, unknown>).reduce<number>(
      (sum, item) => sum + countFacts(item),
      0
    );
  }
  return 1;
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

  const profile = objectOrEmpty(body.profile);
  if (!Object.keys(profile).length) {
    return NextResponse.json({ ok: false, error: "Missing profile" }, { status: 400 });
  }

  const pronounMap = objectOrEmpty(body.pronoun_map);
  const people = objectOrEmpty(body.people ?? profile.people);
  const doNotTouch = arrayOrEmpty(body.do_not_touch ?? profile.do_not_touch);
  const fieldCount = Math.max(
    Number.isFinite(body.field_count as number) ? Number(body.field_count) : 0,
    countFacts(profile) + countFacts(pronounMap)
  );

  const row = {
    user_id: user.id,
    profile,
    pronoun_map: pronounMap,
    people,
    do_not_touch: doNotTouch,
    source: "local_engine",
    field_count: fieldCount,
    updated_at: new Date().toISOString(),
  };

  const { error } = await supabaseAdmin
    .from("dossiers")
    .upsert(row, { onConflict: "user_id" });

  if (error) {
    return NextResponse.json(
      { ok: false, error: error.message },
      { status: 500 }
    );
  }

  return NextResponse.json({
    ok: true,
    user_id: user.id,
    field_count: fieldCount,
  });
}
