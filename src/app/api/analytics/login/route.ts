import { NextRequest, NextResponse } from "next/server";
import {
  checkAnalyticsPassword,
  getSessionToken,
  ANALYTICS_COOKIE_NAME,
} from "@/lib/analytics-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
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
