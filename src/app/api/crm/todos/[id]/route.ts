import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { resolveActingUserId } from "@/lib/crm/identity";
import { logAgentEvent } from "@/lib/crm/events";
import { sendEmail } from "@/lib/crm/email";

const ALLOWED = [
  "title",
  "description",
  "assignee_user_id",
  "is_shared",
  "due_date",
  "status",
  "priority",
  "related_entity_type",
  "related_entity_id",
];

export async function PATCH(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const me = await resolveActingUserId(req);
  const body = await req.json().catch(() => ({}));
  const update: Record<string, unknown> = {};
  for (const k of ALLOWED) if (k in body) update[k] = body[k];
  if (update.status === "done") update.completed_at = new Date().toISOString();
  if (update.status && update.status !== "done") update.completed_at = null;

  const db = crmDb();
  const { data: prev } = await db
    .from("crm_todos")
    .select("assignee_user_id, title")
    .eq("id", params.id)
    .maybeSingle();

  const { data, error } = await db
    .from("crm_todos")
    .update(update)
    .eq("id", params.id)
    .select(
      "*, assignee:crm_users!crm_todos_assignee_user_id_fkey(name, email), creator:crm_users!crm_todos_created_by_user_id_fkey(name)"
    )
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });

  // If assignee changed, notify the new assignee and log it.
  if (
    "assignee_user_id" in update &&
    update.assignee_user_id &&
    prev &&
    prev.assignee_user_id !== update.assignee_user_id &&
    data.assignee?.email
  ) {
    const meName = me ? (await db.from("crm_users").select("name").eq("id", me).maybeSingle()).data?.name : "Someone";
    await sendEmail({
      to: data.assignee.email,
      subject: `${meName || "Someone"} assigned you a todo: ${data.title}`,
      text: `${meName || "Someone"} reassigned a todo to you on Anticipy CRM.\n\n${data.title}\n\nOpen the CRM to view it.`,
    });
    await logAgentEvent({
      agent_name: "manual",
      action: "todo_reassigned",
      summary: `${meName || "Someone"} reassigned "${data.title}" to ${data.assignee?.name || "someone"}`,
      related_entity_type: "todo",
      related_entity_id: data.id,
    });
  }

  return NextResponse.json({ todo: data });
}

export async function DELETE(req: Request, { params }: { params: { id: string } }) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const { error } = await crmDb().from("crm_todos").delete().eq("id", params.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return new NextResponse(null, { status: 204 });
}
