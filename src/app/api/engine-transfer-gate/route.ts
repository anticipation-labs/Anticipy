import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  GATE_COOKIE_NAME,
  GATE_COOKIE_TTL_SECONDS,
  getExpectedPasscode,
  signGateCookie,
} from "@/lib/engine-transfer-gate";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(req: Request) {
  let body: { passcode?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }

  const passcode = typeof body.passcode === "string" ? body.passcode : "";

  if (passcode !== getExpectedPasscode()) {
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
