/**
 * Public agent-event receiver.
 *
 * Per the build plan: POST `/api/log` (root, not under /api/crm/) accepts
 *   { agent_name, action, summary, payload?, related_entity_type?, related_entity_id? }
 * and writes one row into crm_agent_events.
 *
 * Authorization is intentionally light: either a shared-secret header
 * (AGENT_LOG_SECRET) or a valid CRM gate cookie (so a signed-in operator can
 * test the endpoint from within the app). The endpoint is rate-limited per IP.
 */
import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { CRM_GATE_COOKIE, verifyCrmGate } from "@/lib/crm/gate";
import { rateLimit, clientIp } from "@/lib/crm/rate-limit";

function authorize(req: Request): boolean {
  const secret = process.env.AGENT_LOG_SECRET;
  if (secret) {
    const provided = req.headers.get("x-anticipy-log-secret");
    if (provided && provided === secret) return true;
  }
  const cookie = req.headers
    .get("cookie")
    ?.split(";")
    .find((s) => s.trim().startsWith(`${CRM_GATE_COOKIE}=`))
    ?.split("=")[1]
    ?.trim();
  if (verifyCrmGate(cookie)) return true;
  return false;
}

export async function POST(req: Request) {
  const ip = clientIp(req);
  const limit = rateLimit(`log:${ip}`, 120, 60 * 1000);
  if (!limit.allowed) {
    return NextResponse.json({ error: "Rate limited" }, { status: 429 });
  }
  if (!authorize(req)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: any = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const agent_name = String(body.agent_name || "").slice(0, 80).trim();
  const action = String(body.action || "").slice(0, 80).trim();
  const summary = String(body.summary || "").slice(0, 500).trim();
  if (!agent_name || !action || !summary) {
    return NextResponse.json(
      { error: "agent_name, action, and summary are required" },
      { status: 400 }
    );
  }

  const { data, error } = await crmDb()
    .from("crm_agent_events")
    .insert({
      agent_name,
      action,
      summary,
      payload_jsonb: body.payload ?? null,
      related_entity_type: body.related_entity_type ?? null,
      related_entity_id: body.related_entity_id ?? null,
    })
    .select("id")
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ event_id: data.id });
}
