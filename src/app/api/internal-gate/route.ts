import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  GATE_COOKIE_NAME,
  buildSetCookieHeader,
  verifyGateCookie,
} from "@/lib/gate-cookie";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import crypto from "crypto";

export const dynamic = "force-dynamic";

function expectedPasscode(): string | null {
  const env = process.env.GATE_PASSCODE_INTERNAL;
  if (!env || env.length === 0) {
    if (process.env.NODE_ENV === "production") {
      // Fail-secure: refuse to unlock anything in production when the
      // env is missing, but return null instead of throwing so the
      // route responds with a clean 401, not an uncaught 500 that
      // leaks a stack trace and signals a config gap to attackers.
      return null;
    }
    return "123";
  }
  if (env.length < 6 && process.env.NODE_ENV === "production") {
    // Same fail-secure posture for a misconfigured (too-short) value.
    return null;
  }
  return env;
}

function safeEqual(a: string, b: string): boolean {
  // Constant-time compare so the response time doesn't leak whether
  // the wrong attempt was a near-miss or wholly off. Pad to the
  // longer of the two so timingSafeEqual doesn't throw on length
  // mismatch — the .length === .length pre-check handles correctness.
  if (a.length !== b.length) return false;
  const ab = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  return crypto.timingSafeEqual(ab, bb);
}

export async function POST(req: Request) {
  // Brute-force defense: 10 attempts per IP per minute. Same posture
  // as engine-transfer-gate (84c603d). Real users typing the wrong
  // code 2-3 times still have headroom.
  const ip = clientIp(req);
  const limit = rateLimit(`internal-gate:${ip}`, 10, 60_000);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: "Too many attempts. Wait a minute and try again." },
      { status: 429 }
    );
  }

  let body: { passcode?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  // Strip whitespace + lowercase for input forgiveness, but keep the
  // exact compare to avoid encoding edge cases.
  const raw = (body.passcode || "").toString();
  const stripped = raw.replace(/\s+/g, "").toLowerCase();
  const expectedRaw = expectedPasscode();
  if (expectedRaw === null) {
    // Fail-secure when env is missing or misconfigured in production.
    // Same 401 surface as a wrong passcode; do not leak the config gap.
    return NextResponse.json({ error: "Wrong code" }, { status: 401 });
  }
  const expected = expectedRaw.toLowerCase();
  if (!safeEqual(stripped, expected)) {
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
