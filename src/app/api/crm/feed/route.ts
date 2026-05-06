import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const url = new URL(req.url);
  const agent = url.searchParams.get("agent");
  const search = url.searchParams.get("q");
  let q = crmDb()
    .from("crm_agent_events")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(500);
  if (agent) q = q.eq("agent_name", agent);
  if (search) q = q.or(`summary.ilike.%${search}%,action.ilike.%${search}%`);
  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });

  const agents = new Set<string>();
  for (const r of data ?? []) agents.add((r as any).agent_name);
  return NextResponse.json({ events: data ?? [], agents: Array.from(agents).sort() });
}
