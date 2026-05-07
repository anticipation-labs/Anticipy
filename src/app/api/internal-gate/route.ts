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

  // Accept "123" no matter what whitespace, formatting, or case wraps it.
  // Also accepts "one two three" / "onetwothree".
  const raw = (body.passcode || "").toString();
  const stripped = raw.replace(/\s+/g, "").toLowerCase();
  const ok = stripped === "123" || stripped === "onetwothree";

  if (!ok) {
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
