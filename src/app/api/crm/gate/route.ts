/**
 * POST /api/crm/gate { password } -> 204 + sets HttpOnly cookie on success.
 * DELETE /api/crm/gate            -> clears cookie.
 * GET    /api/crm/gate            -> { ok: boolean } reflecting cookie state.
 */
import { NextResponse } from "next/server";
import { rateLimit, clientIp } from "@/lib/crm/rate-limit";
import {
  CRM_GATE_COOKIE,
  buildClearCrmGateHeader,
  buildSetCrmGateHeader,
  getExpectedPassword,
  verifyCrmGate,
} from "@/lib/crm/gate";

export async function GET(req: Request) {
  const cookie = req.headers
    .get("cookie")
    ?.split(";")
    .find((c) => c.trim().startsWith(`${CRM_GATE_COOKIE}=`))
    ?.split("=")[1];
  return NextResponse.json({ ok: verifyCrmGate(cookie) });
}

export async function POST(req: Request) {
  const ip = clientIp(req);
  const limit = rateLimit(`crm-gate:${ip}`, 8, 60 * 1000);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: "Too many attempts" },
      { status: 429 }
    );
  }
  let body: { password?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }
  if (typeof body.password !== "string" || body.password.length === 0) {
    return NextResponse.json({ error: "Password required" }, { status: 400 });
  }
  if (body.password !== getExpectedPassword()) {
    return NextResponse.json({ error: "Wrong password" }, { status: 401 });
  }
  const res = new NextResponse(null, { status: 204 });
  res.headers.set("Set-Cookie", buildSetCrmGateHeader());
  return res;
}

export async function DELETE() {
  const res = new NextResponse(null, { status: 204 });
  res.headers.set("Set-Cookie", buildClearCrmGateHeader());
  return res;
}
