import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { mintHandoffToken } from "@/lib/handoff-token";
import { createSupabaseHandoffStore } from "@/lib/handoff-token-store";

export const dynamic = "force-dynamic";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

/**
 * POST /api/auth/handoff/mint
 *
 * Headers: Authorization: Bearer <supabase access token>
 * Body:    { refresh_token: string }
 * Returns: { token, deep_link, expires_at }
 *
 * The browser holds a real Supabase session after signup but cannot pass a
 * JWT to the Mac app safely through a URL. Instead we mint a single use
 * handoff token, stash the access and refresh tokens against it for five
 * minutes, and hand the Mac app the deep link. The Mac app then calls
 * /api/auth/exchange to swap the token for the real session.
 */
export async function POST(req: Request) {
  const auth = req.headers.get("authorization") || req.headers.get("Authorization");
  if (!auth?.toLowerCase().startsWith("bearer ")) {
    return NextResponse.json(
      { error: "Missing or invalid Authorization header" },
      { status: 401, headers: corsHeaders }
    );
  }
  const accessToken = auth.slice(7).trim();
  if (!accessToken) {
    return NextResponse.json(
      { error: "Empty bearer token" },
      { status: 401, headers: corsHeaders }
    );
  }

  let body: { refresh_token?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400, headers: corsHeaders }
    );
  }
  const refreshToken =
    typeof body.refresh_token === "string" ? body.refresh_token : "";
  if (!refreshToken) {
    return NextResponse.json(
      { error: "Missing refresh_token" },
      { status: 400, headers: corsHeaders }
    );
  }

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );

  const { data: userData, error: userErr } = await supabase.auth.getUser(
    accessToken
  );
  if (userErr || !userData?.user) {
    return NextResponse.json(
      { error: "Invalid or expired session" },
      { status: 401, headers: corsHeaders }
    );
  }

  try {
    const result = await mintHandoffToken({
      store: createSupabaseHandoffStore(supabase),
      user_id: userData.user.id,
      access_token: accessToken,
      refresh_token: refreshToken,
    });
    return NextResponse.json(result, { headers: corsHeaders });
  } catch (e) {
    console.error("[auth/handoff/mint]", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Mint failed" },
      { status: 500, headers: corsHeaders }
    );
  }
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: corsHeaders });
}
