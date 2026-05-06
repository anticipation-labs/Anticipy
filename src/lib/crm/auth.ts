/**
 * Reusable gate-cookie guard for CRM API routes.
 */
import { NextResponse } from "next/server";
import { CRM_GATE_COOKIE, verifyCrmGate } from "./gate";

export function requireCrmGate(req: Request): NextResponse | null {
  const c = req.headers
    .get("cookie")
    ?.split(";")
    .find((s) => s.trim().startsWith(`${CRM_GATE_COOKIE}=`))
    ?.split("=")[1]
    ?.trim();
  if (!verifyCrmGate(c)) {
    return NextResponse.json({ error: "Locked" }, { status: 401 });
  }
  return null;
}
