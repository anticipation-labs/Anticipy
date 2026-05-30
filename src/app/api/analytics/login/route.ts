import { NextRequest, NextResponse } from "next/server";
import {
  checkAnalyticsPassword,
  getSessionToken,
  ANALYTICS_COOKIE_NAME,
} from "@/lib/analytics-auth";
import { rateLimit, clientIp } from "@/lib/rate-limit";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  // B054: 5 attempts per IP per 10 min. Without this, the literal-fallback
  // password (B053) was trivially brute-forceable in seconds.
  const ip = clientIp(request);
  const limit = rateLimit(`analytics-login:${ip}`, 5, 10 * 60_000);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: "Too many attempts. Wait 10 minutes and try again." },
      { status: 429 }
    );
  }

  let body: { password?: unknown } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  if (!checkAnalyticsPassword(body.password)) {
    return NextResponse.json(
      { error: "Wrong password." },
      { status: 401 }
    );
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(ANALYTICS_COOKIE_NAME, getSessionToken(), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 30,
    path: "/",
  });
  return res;
}
