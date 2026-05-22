import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { exchangeHandoffToken } from "@/lib/handoff-token";
import { createSupabaseHandoffStore } from "@/lib/handoff-token-store";

export const dynamic = "force-dynamic";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

/**
 * POST /api/auth/exchange
 *
 * Body:    { token: string }   // the handoff token from anticipy://session?token=...
 * Returns: { access_token, refresh_token, user }
 *
 * The Mac app calls this once at first launch after the OS routes the
 * anticipy://session deep link. Each token is single use and expires five
 * minutes after mint; replays or stale tokens return 410 Gone.
 */
export async function POST(req: Request) {
  let body: { token?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400, headers: corsHeaders }
    );
  }
  const token = typeof body.token === "string" ? body.token : "";
  if (!token) {
    return NextResponse.json(
      { error: "Missing token" },
      { status: 400, headers: corsHeaders }
    );
  }

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );

  let result;
  try {
    result = await exchangeHandoffToken({
      store: createSupabaseHandoffStore(supabase),
      token,
    });
  } catch (e) {
    console.error("[auth/exchange]", e);
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "Exchange failed" },
      { status: 500, headers: corsHeaders }
    );
  }

  if (result.kind === "not_found") {
    return NextResponse.json(
      { error: "Unknown token" },
      { status: 404, headers: corsHeaders }
    );
  }
  if (result.kind === "gone") {
    return NextResponse.json(
      { error: result.reason === "expired" ? "Token expired" : "Token already used" },
      { status: 410, headers: corsHeaders }
    );
  }

  const { data: userData, error: userErr } = await supabase.auth.getUser(
    result.access_token
  );
  const user = userErr || !userData?.user ? { id: result.user_id } : userData.user;

  return NextResponse.json(
    {
      access_token: result.access_token,
      refresh_token: result.refresh_token,
      user,
    },
    { headers: corsHeaders }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: corsHeaders });
}
