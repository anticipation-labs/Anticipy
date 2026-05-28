import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { resolveActingUserId } from "@/lib/crm/identity";
import { logAgentEvent } from "@/lib/crm/events";
import { sendEmail } from "@/lib/crm/email";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const url = new URL(req.url);
  const status = url.searchParams.get("status");
  const assignee = url.searchParams.get("assignee");
  const shared = url.searchParams.get("shared");

  let q = crmDb()
    .from("crm_todos")
    .select(
      "*, assignee:crm_users!crm_todos_assignee_user_id_fkey(name, email), creator:crm_users!crm_todos_created_by_user_id_fkey(name)"
    )
    .order("created_at", { ascending: false });

  if (status) q = q.eq("status", status);
  if (assignee === "shared") q = q.eq("is_shared", true);
  else if (assignee) q = q.eq("assignee_user_id", assignee);
  if (shared === "true") q = q.eq("is_shared", true);

  const { data, error } = await q;
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json({ todos: data ?? [] });
}

export async function POST(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  const me = await resolveActingUserId(req);
  const body = await req.json().catch(() => ({}));
  const title = (body.title || "").trim();
  if (!title) return NextResponse.json({ error: "Title required" }, { status: 400 });

  const insert = {
    title,
    description: body.description || null,
    assignee_user_id: body.is_shared ? null : body.assignee_user_id || null,
    is_shared: !!body.is_shared,
    created_by_user_id: me,
    due_date: body.due_date || null,
    status: body.status || "todo",
    priority: body.priority || null,
    related_entity_type: body.related_entity_type || null,
    related_entity_id: body.related_entity_id || null,
  };

  const { data, error } = await crmDb()
    .from("crm_todos")
    .insert(insert)
    .select(
      "*, assignee:crm_users!crm_todos_assignee_user_id_fkey(name, email), creator:crm_users!crm_todos_created_by_user_id_fkey(name)"
    )
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });

  // Notify assignee on creation if applicable.
  if (data?.assignee?.email && !data.is_shared) {
    await sendEmail({
      to: data.assignee.email,
      subject: `New todo for you: ${data.title}`,
      text: `${data.creator?.name || "Someone"} added a todo for you on Anticipy CRM.\n\n${data.title}\n${data.description || ""}\n\nOpen the CRM to view it.`,
    });
  }
  await logAgentEvent({
    agent_name: "manual",
    action: "todo_created",
    summary: `${data.creator?.name || "Someone"} added "${data.title}"`,
    related_entity_type: "todo",
    related_entity_id: data.id,
  });

  return NextResponse.json({ todo: data });
}
