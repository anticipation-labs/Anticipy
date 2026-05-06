import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { requireCrmGate } from "@/lib/crm/auth";
import { resolveActingUserId } from "@/lib/crm/identity";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;

  const db = crmDb();
  const userId = await resolveActingUserId(req);
  const todayIso = new Date().toISOString().slice(0, 10);
  const monthStart = new Date();
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);

  const [
    myTodos,
    sharedTodos,
    events,
    monthExpenses,
    todayMemo,
    pendingExpenses,
  ] = await Promise.all([
    userId
      ? db
          .from("crm_todos")
          .select("id, title, status, due_date, priority, created_at")
          .eq("assignee_user_id", userId)
          .neq("status", "done")
          .order("created_at", { ascending: false })
          .limit(5)
      : Promise.resolve({ data: [] as any[], error: null }),
    db
      .from("crm_todos")
      .select("id, title, status, due_date, priority, created_at")
      .eq("is_shared", true)
      .neq("status", "done")
      .order("created_at", { ascending: false })
      .limit(5),
    db
      .from("crm_agent_events")
      .select("id, agent_name, action, summary, created_at")
      .order("created_at", { ascending: false })
      .limit(5),
    db
      .from("crm_expenses")
      .select("amount_cents")
      .gte("date", monthStart.toISOString().slice(0, 10)),
    userId
      ? db
          .from("crm_voice_memos")
          .select("id, transcript, duration_seconds, audio_storage_path")
          .eq("user_id", userId)
          .eq("recorded_date", todayIso)
          .maybeSingle()
      : Promise.resolve({ data: null, error: null }),
    db
      .from("crm_expenses")
      .select("id", { count: "exact", head: true })
      .eq("status", "pending_review"),
  ]);

  const burnCents = (monthExpenses.data || []).reduce(
    (acc, r: any) => acc + (r.amount_cents || 0),
    0
  );

  return NextResponse.json({
    myTodos: myTodos.data || [],
    sharedTodos: sharedTodos.data || [],
    events: events.data || [],
    burnCents,
    todayMemo: todayMemo.data || null,
    pendingReviewCount: (pendingExpenses as any).count || 0,
  });
}
