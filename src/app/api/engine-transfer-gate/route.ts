import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  GATE_COOKIE_NAME,
  GATE_COOKIE_TTL_SECONDS,
  getExpectedPasscode,
  signGateCookie,
} from "@/lib/engine-transfer-gate";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import crypto from "crypto";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

function safeEqual(a: string, b: string): boolean {
  // Constant-time compare so the response time can't leak whether the
  // wrong attempt was a near-miss or wholly off. Length check first
  // (timingSafeEqual throws on mismatched length), but length itself
  // doesn't carry useful entropy at our keyspace.
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));
}

export async function POST(req: Request) {
  // Brute-force defense: 10 attempts per IP per minute.
  // The legitimate flow is one POST per session; a real user typing the
  // wrong code 2-3 times still has plenty of headroom. An attacker
  // probing the passcode space gets cut off well before they can iterate
  // any meaningful fraction of the keyspace.
  const ip = clientIp(req);
  const limit = rateLimit(`engine-gate:${ip}`, 10, 60_000);
  if (!limit.allowed) {
    return NextResponse.json(
      { ok: false, error: "Too many attempts. Wait a minute and try again." },
      { status: 429 }
    );
  }

  let body: { passcode?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }

  const passcode = typeof body.passcode === "string" ? body.passcode : "";

  if (!safeEqual(passcode, getExpectedPasscode())) {
    return NextResponse.json({ ok: false, error: "Wrong passcode" }, { status: 401 });
  }

  const token = signGateCookie("valid");
  cookies().set({
    name: GATE_COOKIE_NAME,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: GATE_COOKIE_TTL_SECONDS,
  });

  return NextResponse.json({ ok: true });
}

export async function DELETE() {
  cookies().set({
    name: GATE_COOKIE_NAME,
    value: "",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return NextResponse.json({ ok: true });
}
