import { NextResponse } from "next/server";
import { requireSupabaseUser } from "@/lib/require-auth";
import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  hashPin,
  sanitizeAssistantName,
  toPublicProfile,
  validatePhoneE164,
  validatePin,
  type ProfileRow,
} from "@/lib/profile";

export const dynamic = "force-dynamic";

/**
 * GET  /api/onboarding/profile
 * POST /api/onboarding/profile
 *
 * Per-user profile surface for the multi-tenant Twilio broker.
 * Authenticated via Supabase session bearer token (same pattern as
 * /api/twilio/relay and /api/engine/model).
 *
 * GET returns the current profile shape with caps the engine should
 * respect. POST upserts assistant_name and/or pin and/or phone_e164;
 * any field omitted from the body is left unchanged.
 *
 * The PIN is bcrypt-hashed server-side before any database write. The
 * client never sees the hash on GET; only a has_pin boolean.
 *
 * Phone format is enforced at the API surface so an inbound voice
 * webhook can always match the From field against the stored
 * phone_e164 without ambiguity. We do not auto-verify phones here.
 * phone_verified_at stays null until a future SMS-loop verification
 * route writes it (out of scope for this milestone, but the column
 * exists for the upgrade).
 */

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

async function loadOrCreateProfile(userId: string): Promise<ProfileRow | null> {
  // SELECT-then-INSERT covers two cases the upsert idiom hides:
  //  1. brand new user without a profile row (Supabase signup does not
  //     create one); we want a sensible default row visible on first GET.
  //  2. existing row; we just return it, no update needed.
  const existing = await supabaseAdmin
    .from("anticipy_profiles")
    .select("*")
    .eq("id", userId)
    .maybeSingle();
  if (existing.error) {
    console.error("[onboarding-profile] select failed", existing.error);
    return null;
  }
  if (existing.data) {
    return existing.data as ProfileRow;
  }
  const inserted = await supabaseAdmin
    .from("anticipy_profiles")
    .insert({ id: userId })
    .select("*")
    .single();
  if (inserted.error) {
    console.error("[onboarding-profile] insert failed", inserted.error);
    return null;
  }
  return inserted.data as ProfileRow;
}

export async function GET(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json(
      { ok: false, error: "Unauthorized" },
      { status: 401, headers: corsHeaders },
    );
  }
  const row = await loadOrCreateProfile(user.id);
  if (!row) {
    return NextResponse.json(
      { ok: false, error: "Profile lookup failed" },
      { status: 500, headers: corsHeaders },
    );
  }
  return NextResponse.json(
    { ok: true, profile: toPublicProfile(row) },
    { headers: corsHeaders },
  );
}

interface PostBody {
  assistant_name?: unknown;
  pin?: unknown;
  phone_e164?: unknown;
}

export async function POST(req: Request) {
  const user = await requireSupabaseUser(req);
  if (!user) {
    return NextResponse.json(
      { ok: false, error: "Unauthorized" },
      { status: 401, headers: corsHeaders },
    );
  }

  let raw: PostBody;
  try {
    raw = (await req.json()) as PostBody;
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON body" },
      { status: 400, headers: corsHeaders },
    );
  }
  if (!raw || typeof raw !== "object") {
    return NextResponse.json(
      { ok: false, error: "Invalid body shape" },
      { status: 400, headers: corsHeaders },
    );
  }

  const update: Record<string, unknown> = { updated_at: new Date().toISOString() };

  if (raw.assistant_name !== undefined) {
    const sanitized = sanitizeAssistantName(raw.assistant_name);
    if (!sanitized.ok) {
      return NextResponse.json(
        { ok: false, error: sanitized.error },
        { status: 400, headers: corsHeaders },
      );
    }
    update.assistant_name = sanitized.name;
  }

  if (raw.pin !== undefined) {
    const validated = validatePin(raw.pin);
    if (!validated.ok) {
      return NextResponse.json(
        { ok: false, error: validated.error },
        { status: 400, headers: corsHeaders },
      );
    }
    update.pin_hash = await hashPin(validated.pin as string);
    update.pin_set_at = new Date().toISOString();
  }

  if (raw.phone_e164 !== undefined) {
    if (raw.phone_e164 === null || raw.phone_e164 === "") {
      update.phone_e164 = null;
      update.phone_verified_at = null;
    } else {
      const phoneCheck = validatePhoneE164(raw.phone_e164);
      if (!phoneCheck.ok) {
        return NextResponse.json(
          { ok: false, error: phoneCheck.error },
          { status: 400, headers: corsHeaders },
        );
      }
      update.phone_e164 = phoneCheck.phone;
      // New phone is unverified until we run an SMS loop against it.
      update.phone_verified_at = null;
    }
  }

  // Ensure a row exists before we try to update it.
  const seeded = await loadOrCreateProfile(user.id);
  if (!seeded) {
    return NextResponse.json(
      { ok: false, error: "Profile lookup failed" },
      { status: 500, headers: corsHeaders },
    );
  }

  const { data: updated, error: updateErr } = await supabaseAdmin
    .from("anticipy_profiles")
    .update(update)
    .eq("id", user.id)
    .select("*")
    .single();

  if (updateErr) {
    // 23505 = unique violation on phone_e164. Surface a clear message
    // so the onboarding UI can say "that number belongs to another
    // account" rather than a generic 500.
    const code = (updateErr as { code?: string }).code;
    if (code === "23505") {
      return NextResponse.json(
        {
          ok: false,
          error: "That phone number is already attached to another Anticipy account.",
        },
        { status: 409, headers: corsHeaders },
      );
    }
    console.error("[onboarding-profile] update failed", updateErr);
    return NextResponse.json(
      { ok: false, error: "Profile update failed" },
      { status: 500, headers: corsHeaders },
    );
  }
  return NextResponse.json(
    { ok: true, profile: toPublicProfile(updated as ProfileRow) },
    { headers: corsHeaders },
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: corsHeaders });
}
