import { NextResponse } from "next/server";
import { getGoogleAuthUrl } from "@/lib/google-calendar";
import { createClient } from "@supabase/supabase-js";
import crypto from "crypto";

export const dynamic = "force-dynamic";

/**
 * GET /api/auth/google?token=<supabase_access_token>
 *
 * Starts Google OAuth. We tie the flow to a specific app user by:
 *  1. Validating the Supabase access token from the `token` query param.
 *  2. Setting a short-lived, httpOnly cookie with the user's email.
 *  3. Reading that cookie in the callback to key the stored tokens by app
 *     email rather than Google email.
 *
 * The token is passed in the URL because this endpoint is called as a plain
 * <a href> from the client (browsers don't send Authorization headers on
 * top-level navigation). It is single-use and discarded after the redirect.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const token = url.searchParams.get("token");

  if (!token) {
    return NextResponse.json(
      { error: "Missing auth token" },
      { status: 401 }
    );
  }

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? ""
  );
  const { data, error } = await supabase.auth.getUser(token);
  if (error || !data.user?.email) {
    return NextResponse.json(
      { error: "Invalid or expired session" },
      { status: 401 }
    );
  }

  const state = crypto.randomUUID();
  const authUrl = getGoogleAuthUrl(state);

  const response = NextResponse.redirect(authUrl);
  // Cookie expires in 10 minutes — long enough to complete OAuth, short
  // enough that a stolen cookie has minimal value.
  response.cookies.set("anticipy_oauth_email", data.user.email, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 600,
    path: "/",
  });
  response.cookies.set("anticipy_oauth_state", state, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 600,
    path: "/",
  });
  return response;
}
