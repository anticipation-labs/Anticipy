import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const dynamic = "force-dynamic";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

/**
 * POST /api/auth/signup
 *
 * Body:    { email: string, password: string }
 * Returns: { access_token, refresh_token, user }
 *
 * The browser form posts here. The server uses the service role key to
 * call auth.admin.createUser with email_confirm=true, which inserts a
 * confirmed row into auth.users with no email send. We then sign the new
 * user in with their password so the response carries a real session.
 * This keeps the front door honest (real auth.users row, real session)
 * while sidestepping the project's email rate limit on the public signup
 * endpoint.
 */
export async function POST(req: Request) {
  let body: { email?: unknown; password?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400, headers: corsHeaders }
    );
  }

  const email = typeof body.email === "string" ? body.email.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!email || !password) {
    return NextResponse.json(
      { error: "Missing email or password" },
      { status: 400, headers: corsHeaders }
    );
  }
  if (password.length < 8) {
    return NextResponse.json(
      { error: "Password must be at least 8 characters" },
      { status: 400, headers: corsHeaders }
    );
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY ?? "";
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";
  if (!supabaseUrl || !serviceKey || !anonKey) {
    return NextResponse.json(
      { error: "Supabase not configured on the server" },
      { status: 500, headers: corsHeaders }
    );
  }

  const admin = createClient(supabaseUrl, serviceKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });

  const { data: created, error: createErr } = await admin.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  });

  if (createErr) {
    const msg = createErr.message || "Signup failed";
    const lower = msg.toLowerCase();
    const conflict =
      lower.includes("already") ||
      lower.includes("exist") ||
      lower.includes("registered");
    return NextResponse.json(
      { error: msg },
      { status: conflict ? 409 : 400, headers: corsHeaders }
    );
  }
  if (!created?.user) {
    return NextResponse.json(
      { error: "Signup did not return a user" },
      { status: 500, headers: corsHeaders }
    );
  }

  const userClient = createClient(supabaseUrl, anonKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
  const { data: signedIn, error: signInErr } =
    await userClient.auth.signInWithPassword({ email, password });
  if (signInErr || !signedIn?.session) {
    return NextResponse.json(
      {
        user: { id: created.user.id, email: created.user.email },
        access_token: null,
        refresh_token: null,
      },
      { headers: corsHeaders }
    );
  }

  return NextResponse.json(
    {
      user: { id: created.user.id, email: created.user.email },
      access_token: signedIn.session.access_token,
      refresh_token: signedIn.session.refresh_token,
      expires_in: signedIn.session.expires_in,
      expires_at: signedIn.session.expires_at,
      token_type: signedIn.session.token_type,
    },
    { headers: corsHeaders }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: corsHeaders });
}
