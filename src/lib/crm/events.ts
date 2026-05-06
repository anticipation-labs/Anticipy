/**
 * Helper for writing rows into crm_agent_events from server-side code.
 * Used when our own UI / system actions warrant a feed entry, eg "Omar
 * reassigned a todo to Jacob" or "digest cron sent the morning email".
 */
import { crmDb } from "./db";

export async function logAgentEvent(opts: {
  agent_name: string;
  action: string;
  summary: string;
  payload?: unknown;
  related_entity_type?: string | null;
  related_entity_id?: string | null;
}): Promise<void> {
  await crmDb()
    .from("crm_agent_events")
    .insert({
      agent_name: opts.agent_name,
      action: opts.action,
      summary: opts.summary,
      payload_jsonb: opts.payload ?? null,
      related_entity_type: opts.related_entity_type ?? null,
      related_entity_id: opts.related_entity_id ?? null,
    });
}
