/**
 * GET /api/cron/daily-digest
 *
 * Vercel Cron pings this at the schedule in vercel.json. Aggregates yesterday's
 * activity (expenses, todos, files, voice memos, agent events) and emails one
 * digest per recipient via SendGrid (or Resend if configured).
 *
 * Authorization is permissive: any of (a) Vercel's Authorization: Bearer header
 * matches CRON_SECRET, (b) x-cron-secret header matches CRON_SECRET, (c) the
 * caller has a valid CRM gate cookie. This lets Settings expose a "Run now"
 * button without opening the endpoint to the public internet.
 */
import { NextResponse } from "next/server";
import { crmDb } from "@/lib/crm/db";
import { CRM_GATE_COOKIE, verifyCrmGate } from "@/lib/crm/gate";
import { sendEmail } from "@/lib/crm/email";
import { logAgentEvent } from "@/lib/crm/events";

export const runtime = "nodejs";
export const maxDuration = 60;

function authorize(req: Request): boolean {
  const secret = process.env.CRON_SECRET;
  if (secret) {
    const header = req.headers.get("authorization") || "";
    if (header.startsWith("Bearer ") && header.slice(7) === secret) return true;
    const x = req.headers.get("x-cron-secret");
    if (x && x === secret) return true;
  }
  const cookie = req.headers
    .get("cookie")
    ?.split(";")
    .find((s) => s.trim().startsWith(`${CRM_GATE_COOKIE}=`))
    ?.split("=")[1]
    ?.trim();
  if (verifyCrmGate(cookie)) return true;
  // If neither secret nor gate, allow only if no CRON_SECRET is set yet
  // (so a fresh deploy still ticks). In production, set CRON_SECRET.
  return !secret;
}

export async function GET(req: Request) {
  if (!authorize(req)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const db = crmDb();

  const now = new Date();
  const yesterday = new Date(now.getTime() - 86400 * 1000);
  const yIso = yesterday.toISOString().slice(0, 10);
  const yStart = `${yIso}T00:00:00.000Z`;
  const yEnd = `${yIso}T23:59:59.999Z`;

  const [expenses, todosCompleted, todosCreated, files, memos, events] = await Promise.all([
    db
      .from("crm_expenses")
      .select("amount_cents, currency, status, vendor:crm_vendors(name), category")
      .eq("date", yIso),
    db
      .from("crm_todos")
      .select("title, assignee:crm_users(name), is_shared, completed_at")
      .gte("completed_at", yStart)
      .lte("completed_at", yEnd),
    db
      .from("crm_todos")
      .select("title")
      .gte("created_at", yStart)
      .lte("created_at", yEnd),
    db
      .from("crm_files")
      .select("filename, project_folder")
      .gte("created_at", yStart)
      .lte("created_at", yEnd),
    db
      .from("crm_voice_memos")
      .select("transcript, user:crm_users(name)")
      .eq("recorded_date", yIso),
    db
      .from("crm_agent_events")
      .select("agent_name, action")
      .gte("created_at", yStart)
      .lte("created_at", yEnd),
  ]);

  const expRows = expenses.data ?? [];
  const expTotalCents = expRows.reduce((a: number, r: any) => a + (r.amount_cents || 0), 0);
  const pending = expRows.filter((r: any) => r.status === "pending_review").length;
  const top: any = expRows.length
    ? [...(expRows as any[])].sort((a, b) => (b.amount_cents || 0) - (a.amount_cents || 0))[0]
    : null;

  const completed = todosCompleted.data ?? [];
  const created = todosCreated.data ?? [];
  const completedByOwner: Record<string, number> = {};
  for (const t of completed as any[]) {
    const owner = t.is_shared ? "Shared" : t.assignee?.name || "Unassigned";
    completedByOwner[owner] = (completedByOwner[owner] || 0) + 1;
  }

  const filesByFolder: Record<string, number> = {};
  for (const f of files.data ?? []) {
    filesByFolder[(f as any).project_folder] = (filesByFolder[(f as any).project_folder] || 0) + 1;
  }
  const lastFile = (files.data ?? []).at(-1) as any | undefined;

  const memoRows = memos.data ?? [];

  const eventByAgent: Record<string, number> = {};
  for (const e of events.data ?? []) {
    eventByAgent[(e as any).agent_name] = (eventByAgent[(e as any).agent_name] || 0) + 1;
  }

  // Build text body, omitting empty sections.
  const lines: string[] = [];
  lines.push("Yesterday at Anticipy.\n");

  if (expRows.length > 0) {
    lines.push("EXPENSES");
    lines.push(`- ${formatMoney(expTotalCents)} total across ${expRows.length} receipt${expRows.length === 1 ? "" : "s"}`);
    if (top) {
      lines.push(`- Top: ${top.vendor?.name || "n/a"} ${formatMoney(top.amount_cents || 0)} for ${top.category || "n/a"}`);
    }
    if (pending > 0) lines.push(`- ${pending} still pending review`);
    lines.push("");
  }

  if (completed.length + created.length > 0) {
    lines.push("TODOS");
    for (const [k, v] of Object.entries(completedByOwner)) {
      lines.push(`- ${v} completed by ${k}`);
    }
    if (created.length > 0) lines.push(`- ${created.length} new todos created`);
    lines.push("");
  }

  if ((files.data ?? []).length > 0) {
    lines.push("MANUFACTURING ROOM");
    for (const [folder, count] of Object.entries(filesByFolder)) {
      lines.push(`- ${count} file${count === 1 ? "" : "s"} uploaded to ${folder}`);
    }
    if (lastFile) lines.push(`- ${lastFile.filename}`);
    lines.push("");
  }

  if (memoRows.length > 0) {
    lines.push("VOICE MEMOS");
    for (const m of memoRows as any[]) {
      const who = m.user?.name || "Someone";
      const t = (m.transcript || "").slice(0, 60).trim();
      lines.push(`- ${who}: ${t || "(no transcript)"}.`);
    }
    lines.push("");
  }

  if (Object.keys(eventByAgent).length > 0) {
    lines.push("AGENT ACTIVITY");
    for (const [k, v] of Object.entries(eventByAgent)) {
      lines.push(`- ${k}: ${v} events`);
    }
    lines.push("");
  }

  // Open items.
  const { count: openPending } = await db
    .from("crm_expenses")
    .select("id", { count: "exact", head: true })
    .eq("status", "pending_review");
  const { count: dueToday } = await db
    .from("crm_todos")
    .select("id", { count: "exact", head: true })
    .eq("due_date", new Date().toISOString().slice(0, 10))
    .neq("status", "done");
  const open: string[] = [];
  if ((openPending ?? 0) > 0) open.push(`- ${openPending} pending receipt review${openPending === 1 ? "" : "s"}`);
  if ((dueToday ?? 0) > 0) open.push(`- ${dueToday} todo${dueToday === 1 ? "" : "s"} due today`);
  if (open.length > 0) {
    lines.push("OPEN");
    lines.push(...open);
    lines.push("");
  }

  const headlineParts: string[] = [];
  if (expRows.length > 0) headlineParts.push(`${expRows.length} expense${expRows.length === 1 ? "" : "s"}`);
  if (completed.length > 0) headlineParts.push(`${completed.length} todo${completed.length === 1 ? "" : "s"} done`);
  if ((files.data ?? []).length > 0) headlineParts.push(`${(files.data ?? []).length} file${(files.data ?? []).length === 1 ? "" : "s"}`);
  const headline = headlineParts.join(", ") || "quiet day";
  const subject = `Anticipy yesterday: ${headline}`;
  const body = lines.join("\n");

  // Recipients: every CRM user with a non-null email.
  const { data: recipientsData } = await db
    .from("crm_users")
    .select("email, name")
    .not("email", "is", null);
  const recipients = (recipientsData ?? []).filter((u: any) => u.email);
  if (recipients.length === 0) {
    return NextResponse.json({ ok: false, reason: "no recipients with email" });
  }

  const sent: string[] = [];
  const errors: string[] = [];
  for (const r of recipients) {
    const res = await sendEmail({ to: r.email, subject, text: body });
    if (res.sent) sent.push(r.email);
    else errors.push(`${r.email}: ${res.reason || "unknown"}`);
  }

  await logAgentEvent({
    agent_name: "digest_cron",
    action: "sent",
    summary: `${headline} (${sent.length}/${recipients.length})`,
    payload: { sent, errors, subject },
  });

  return NextResponse.json({ ok: true, sent, errors, subject });
}

function formatMoney(cents: number): string {
  return (cents / 100).toLocaleString("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 0,
  });
}
