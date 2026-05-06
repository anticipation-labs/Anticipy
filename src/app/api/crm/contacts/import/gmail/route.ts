/**
 * Phase 2 stub. The full implementation requires a Google Cloud OAuth client
 * (GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET + GMAIL_REFRESH_TOKEN) and the
 * googleapis SDK; deferred from Phase 1 by design. The endpoint returns 501
 * with a descriptive message so the UI can show "coming soon".
 */
import { NextResponse } from "next/server";
import { requireCrmGate } from "@/lib/crm/auth";

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  return NextResponse.json(
    {
      error: "Gmail import is not wired in Phase 1.",
      hint:
        "Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, and GMAIL_REFRESH_TOKEN, then re-deploy. Manual contacts work fully today.",
    },
    { status: 501 }
  );
}
