import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  GATE_COOKIE_NAME,
  buildSetCookieHeader,
  verifyGateCookie,
} from "@/lib/gate-cookie";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  let body: { passcode?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const expected = "123";
  const provided = (body.passcode || "").trim();

  if (provided !== expected) {
    // Uniform error — don't leak whether env override is set.
    return NextResponse.json({ error: "Wrong code" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.headers.set("Set-Cookie", buildSetCookieHeader());
  return res;
}

/**
 * GET /api/internal-gate
 *
 * Returns whether the current request already has a valid gate cookie.
 * Used by /demo and /internal pages to skip re-prompting on refresh.
 */
export async function GET() {
  const c = cookies().get(GATE_COOKIE_NAME)?.value;
  return NextResponse.json({ unlocked: verifyGateCookie(c) });
}
