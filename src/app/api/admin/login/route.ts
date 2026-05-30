/**
 * B056 + B059: server-side wrapper for admin sign-in that adds per-IP
 * rate limiting on top of Supabase's own protections. The previous flow
 * called supabase.auth.signInWithPassword directly from the client,
 * exposing the anon key in DevTools and giving any attacker line-speed
 * brute-force capability against admin accounts.
 *
 * On success this returns { ok: true, access_token, refresh_token } so the
 * client can hand the bearer token to subsequent /api/admin/* calls (the
 * existing verifyAdmin() reads the Authorization header). It deliberately
 * does NOT set a cookie; the client keeps its existing supabase.auth.client
 * setSession() flow for now.
 */
import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const ip = clientIp(request);
  // 5 attempts per IP per 10 minutes is the same posture as the
  // /api/analytics/login fix in B054. Real admins typing the wrong
  // password 2-3 times still have headroom.
  const limit = rateLimit(`admin-login:${ip}`, 5, 10 * 60_000);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: "Too many attempts. Wait 10 minutes and try again." },
      { status: 429 }
    );
  }

  let body: { email?: unknown; password?: unknown } = {};
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const email = typeof body.email === "string" ? body.email.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!email || !password) {
    return NextResponse.json(
      { error: "Email and password required." },
      { status: 400 }
    );
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    return NextResponse.json(
      { error: "Supabase is not configured." },
      { status: 500 }
    );
  }
  const supabase = createClient(url, anonKey);
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });
  if (error || !data?.session) {
    return NextResponse.json({ error: "Invalid credentials." }, { status: 401 });
  }

  // Confirm the signed-in user is in the admin allowlist. Otherwise any
  // Supabase user could authenticate against this endpoint and be told ok.
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!serviceKey) {
    return NextResponse.json(
      { error: "Admin verification not configured." },
      { status: 500 }
    );
  }
  const admin = createClient(url, serviceKey);
  const { data: adminUser } = await admin
    .from("anticipy_admin_users")
    .select("role")
    .eq("id", data.session.user.id)
    .single();
  if (!adminUser) {
    return NextResponse.json({ error: "Not an admin." }, { status: 403 });
  }

  return NextResponse.json({
    ok: true,
    access_token: data.session.access_token,
    refresh_token: data.session.refresh_token,
    role: adminUser.role,
  });
}
