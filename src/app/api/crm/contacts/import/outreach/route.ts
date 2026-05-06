/**
 * Phase 2 stub. Pulls recipients from the hello@anticipy.ai outreach agent's
 * Supabase tables. The agent service location is not wired into the CRM today;
 * deferred to Phase 2. The endpoint responds 501 with guidance.
 */
import { NextResponse } from "next/server";
import { requireCrmGate } from "@/lib/crm/auth";

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  return NextResponse.json(
    {
      error: "Outreach list import is not wired in Phase 1.",
      hint:
        "Provide the outreach agent's Supabase table or shared schema, then this endpoint will sync into crm_contacts.",
    },
    { status: 501 }
  );
}
