import { NextResponse } from "next/server";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import crypto from "crypto";

export const dynamic = "force-dynamic";

const ACCESS_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // omits I, O, 0, 1
const ACCESS_CODE_LENGTH = 10;

function generateAccessCode(): string {
  const bytes = crypto.randomBytes(ACCESS_CODE_LENGTH);
  let code = "";
  for (let i = 0; i < ACCESS_CODE_LENGTH; i++) {
    code += ACCESS_CODE_ALPHABET[bytes[i] % ACCESS_CODE_ALPHABET.length];
  }
  return code;
}

/**
 * Lazily ensure that an engine_users row exists for this Supabase auth user
 * and return its access_code. Creates the row on first call so brand-new
 * accounts pick up an access code without any out-of-band provisioning.
 */
async function ensureAccessCode(
  supabase: SupabaseClient,
  authUserId: string,
  email: string
): Promise<string | null> {
  const { data: existing } = await supabase
    .from("engine_users")
    .select("id, access_code")
    .eq("email", email)
    .maybeSingle();

  if (existing?.access_code) return existing.access_code;

  const newCode = generateAccessCode();

  if (existing) {
    const { data: updated, error: updateErr } = await supabase
      .from("engine_users")
      .update({ access_code: newCode })
      .eq("id", existing.id)
      .select("access_code")
      .single();
    if (updateErr || !updated) {
      console.error("[access-code] update failed:", updateErr);
      return null;
    }
    return updated.access_code;
  }

  // No row yet — provision one. password_hash is filled with a random opaque
  // string so the Supabase-auth account cannot be impersonated via the
  // legacy username/password endpoint in the Python engine.
  const filler = crypto.randomBytes(32).toString("hex");
  const { data: created, error: insertErr } = await supabase
    .from("engine_users")
    .insert({
      id: authUserId,
      email,
      username: `auth_${authUserId.slice(0, 16)}`,
      password_hash: filler,
      access_code: newCode,
    })
    .select("access_code")
    .single();

  if (created?.access_code) return created.access_code;

  // Concurrent insert race or pre-existing row by id — re-fetch and reuse.
  console.warn("[access-code] insert failed, re-checking:", insertErr);
  const { data: refetched } = await supabase
    .from("engine_users")
    .select("access_code")
    .eq("email", email)
    .maybeSingle();
  return refetched?.access_code ?? null;
}

/**
 * GET /api/extension/access-code
 *
 * Returns the user's unique access code from engine_users table.
 * Requires a valid Supabase auth token in the Authorization header. If the
 * caller is a Supabase auth user without an engine_users row yet, one is
 * provisioned on the fly.
 */
export async function GET(req: Request) {
  const corsHeaders = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };

  const authHeader = req.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return NextResponse.json(
      { error: "Missing or invalid Authorization header" },
      { status: 401, headers: corsHeaders }
    );
  }

  const token = authHeader.slice(7);

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );

  // Verify with Supabase auth — never trust an unsigned JWT payload to look
  // up another user's access_code.
  const { data: { user }, error } = await supabase.auth.getUser(token);
  if (error || !user || !user.email) {
    return NextResponse.json(
      { error: "Invalid or expired session" },
      { status: 401, headers: corsHeaders }
    );
  }

  const code = await ensureAccessCode(supabase, user.id, user.email);
  if (code) {
    return NextResponse.json({ code }, { headers: corsHeaders });
  }

  return NextResponse.json(
    { error: "Could not generate access code. Please try again." },
    { status: 500, headers: corsHeaders }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    },
  });
}
