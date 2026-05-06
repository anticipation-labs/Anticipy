import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const { data } = await crmDb()
    .from("crm_agent_events")
    .select("created_at, summary")
    .eq("agent_name", "digest_cron")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  return NextResponse.json({ lastRun: data?.created_at || null, lastSummary: data?.summary || null });
}
