/**
 * HQ's board -- internal_hq.pb.js:611-1109, CONTRACT.md §7.
 *
 *   POST  /internal/todos          create, flag people, arm a reminder
 *   PATCH /internal/todos          changed fields only; done stamps; re-arm
 *   POST  /internal/todos/delete   creator or admin only
 *
 * See hq_data.ts for what is proven here and what is not.
 */
import { newRecordId, pbNow } from "../pb/wire.ts";
import { hqCors, type HqEnv } from "./hq.ts";
import {
  boolDefaultFalse, isoNow, logActivity, resolveActor, type Person,
} from "./hq_data.ts";

const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

const STAGES = ["todo", "doing", "waiting", "blocked"];
const PRIORITIES = ["urgent", "important", "normal", "later"];
/**
 * THREE VALUES, AND ONLY THREE. `doing`, `waiting` and `blocked` are NOT
 * status -- they are `stage`. Accepting them here would take a row out of
 * `status = 'open'` and therefore out of the reminder cron, /internal/state
 * and the assistant's board in one keystroke: a task moved to "In progress"
 * would silently stop being reminded about, with nothing red anywhere.
 */
const STATUSES = ["open", "done", "cancelled"];
const CHANNELS = ["email", "sms", "both"];
const REPEAT_RE = /^(none|daily|weekdays|weekly|monthly|every:[2-9]|every:[12]\d|weekly:(mon|tue|wed|thu|fri|sat|sun))$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^\d{2}:\d{2}$/;
const REMIND_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

const listOf = (raw: unknown): string[] => {
  try {
    const parsed = JSON.parse(String(raw ?? "") || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch { return []; }
};

async function personById(env: HqEnv, id: string): Promise<Person | null> {
  if (!id) return null;
  return await env.DB.prepare("SELECT * FROM internal_people WHERE id = ?1 LIMIT 1")
    .bind(id).first<Person>();
}

/** One inbox row. Never for the person who just acted. */
async function notify(
  env: HqEnv, actorId: string, person: string, kind: string,
  text: string, sub: string, todoId: string,
): Promise<void> {
  if (!person || person === actorId) return;
  try {
    await env.DB.prepare(
      "INSERT INTO internal_notifs (id, created, person, kind, text, sub, todo, actor, read, emailed_at, smsed_at) "
      + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8,0,'','')",
    ).bind(newRecordId(), pbNow(), person, kind, text, sub, todoId, actorId).run();
  } catch { /* an inbox row is not the mutation */ }
}

/** The key/session door plus a REQUIRED actor, with this route's own wording. */
async function actorOr(
  req: Request, env: HqEnv, body: Record<string, unknown>,
  missing: string, cors: Record<string, string>,
): Promise<{ ok: true; actor: Person } | { ok: false; response: Response }> {
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return { ok: false, response: json(503, { error: "internal HQ is not configured" }, cors) };
  }
  const resolved = await resolveActor(req, env, {
    actorId: String(body.actor_id ?? ""), optional: true,
  });
  if (!resolved.ok) return { ok: false, response: resolved.response };
  if (!resolved.person) return { ok: false, response: json(400, { error: missing }, cors) };
  return { ok: true, actor: resolved.person };
}

// ---------------------------------------------------------------------------
// POST /internal/todos
// ---------------------------------------------------------------------------
export async function hqTodoCreate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; } catch { /* {} */ }
  const got = await actorOr(req, env, body, "who is creating this? pick yourself first", cors);
  if (!got.ok) return got.response;
  const actor = got.actor;

  const title = String(body.title ?? "").trim();
  if (!title || title.length > 500) {
    return json(400, { error: "a title between 1 and 500 characters, please" }, cors);
  }

  const track = await env.DB.prepare("SELECT * FROM internal_tracks WHERE id = ?1 LIMIT 1")
    .bind(String(body.track ?? "")).first<Record<string, unknown>>();
  if (!track) return json(400, { error: "that board doesn't exist" }, cors);
  if (!boolDefaultFalse(track.active)) {
    return json(400, { error: "that board is archived" }, cors);
  }

  const assignees: string[] = [];
  if (Array.isArray(body.assignees)) {
    for (const id of body.assignees) {
      const p = await personById(env, String(id));
      if (!p) return json(400, { error: "one of the flagged people doesn't exist" }, cors);
      assignees.push(String(p.id));
    }
  }

  const due = String(body.due ?? "").trim();
  if (due && !DATE_RE.test(due)) {
    return json(400, { error: "due date should be YYYY-MM-DD" }, cors);
  }

  const stage = String(body.stage ?? "todo").trim() || "todo";
  if (!STAGES.includes(stage)) return json(400, { error: "pick a stage" }, cors);
  const priority = String(body.priority ?? "normal").trim() || "normal";
  if (!PRIORITIES.includes(priority)) {
    return json(400, { error: "priority is urgent, important, normal or later" }, cors);
  }
  const dueTime = String(body.due_time ?? "").trim();
  if (dueTime && !TIME_RE.test(dueTime)) {
    return json(400, { error: "a time looks like 14:30" }, cors);
  }
  const repeatRule = String(body.repeat_rule ?? "").trim();
  if (repeatRule && !REPEAT_RE.test(repeatRule)) {
    return json(400, { error: "that repeat isn't one I know" }, cors);
  }
  const holdReason = String(body.hold_reason ?? "").trim().slice(0, 200);

  const watchers: string[] = [];
  if (Array.isArray(body.watchers)) {
    for (const id of body.watchers) {
      const p = await personById(env, String(id));
      if (!p) return json(400, { error: "one of the watchers doesn't exist" }, cors);
      watchers.push(String(p.id));
    }
  }

  // Subtasks are a JSON column, not a collection, on purpose: they are tiny,
  // ordered, always read with the parent, and nobody on a three-person team
  // edits two at once. Comments got their own table precisely because none of
  // that is true of comments.
  const subtasks: Array<{ t: string; done: boolean }> = [];
  if (Array.isArray(body.subtasks)) {
    if (body.subtasks.length > 40) {
      return json(400, {
        error: "forty subtasks is plenty — the rest are their own task",
      }, cors);
    }
    for (const s of body.subtasks as Array<Record<string, unknown>>) {
      const t = String(s?.t ?? "").trim().slice(0, 200);
      if (!t) continue;
      subtasks.push({ t, done: !!s?.done });
    }
  }

  const remindAt = String(body.remind_at ?? "").trim();
  const remindChannel = String(body.remind_channel ?? "").trim();
  if (remindAt) {
    if (!REMIND_RE.test(remindAt)) {
      return json(400, { error: "reminder time looks malformed" }, cors);
    }
    if (!CHANNELS.includes(remindChannel)) {
      return json(400, { error: "pick a reminder channel: email, sms or both" }, cors);
    }
    // THE REMINDER MUST BE ABLE TO REACH SOMEONE, or it is a lie on a card.
    const ids = assignees.length ? assignees : [String(actor.id)];
    const needEmail = remindChannel === "email" || remindChannel === "both";
    const needPhone = remindChannel === "sms" || remindChannel === "both";
    let reachable = false;
    const missing: string[] = [];
    for (const id of ids) {
      const p = await personById(env, id);
      if (!p) continue;
      const email = String(p.email ?? "");
      const phone = String(p.phone ?? "");
      if ((!needEmail || email) || (!needPhone || phone)) reachable = true;
      if (needEmail && !email) missing.push(String(p.name ?? "") + " has no email on file");
      if (needPhone && !phone) missing.push(String(p.name ?? "") + " has no phone number on file");
    }
    if (!reachable) {
      return json(400, {
        error: missing.join("; ") || "nobody flagged has contact details yet",
      }, cors);
    }
  }

  const id = newRecordId();
  await env.DB.prepare(
    "INSERT INTO internal_todos (id, created, updated, title, notes, track, assignees, due,"
    + " status, created_by, remind_at, remind_channel, remind_sent_at, followup_sent_at,"
    + " remind_attempts, stage, priority, due_time, repeat_rule, hold_reason, watchers,"
    + " subtasks, attachments, cmt_count, done_at, done_by, research_job_id, position)"
    + " VALUES (?1,?2,?3,?4,?5,?6,?7,?8,'open',?9,?10,?11,'','',0,?12,?13,?14,?15,?16,?17,?18,'[]',0,'','','',0)",
  ).bind(id, pbNow(), pbNow(), title,
         String(body.notes ?? "").slice(0, 20000), String(track.id), JSON.stringify(assignees),
         due, String(actor.id), remindAt, remindAt ? remindChannel : "",
         stage, priority, dueTime, repeatRule,
         stage === "blocked" || stage === "waiting" ? holdReason : "",
         JSON.stringify(watchers), JSON.stringify(subtasks)).run();

  await logActivity(env, actor, "todo.create",
    String(actor.name ?? "") + " added “" + title.slice(0, 80) + "”",
    "created this task", id);

  // Tell the assignee, unless the assignee is the person typing. Nobody needs
  // an inbox row saying they did the thing they are doing.
  for (const who of assignees) {
    await notify(env, String(actor.id), who, "assign",
      String(actor.name ?? "") + " gave you a task", title.slice(0, 300), id);
  }
  return json(200, { id }, cors);
}

// ---------------------------------------------------------------------------
// PATCH /internal/todos
// ---------------------------------------------------------------------------
export async function hqTodoUpdate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; } catch { /* {} */ }
  const got = await actorOr(req, env, body, "pick yourself first", cors);
  if (!got.ok) return got.response;
  const actor = got.actor;

  const todo = await env.DB.prepare("SELECT * FROM internal_todos WHERE id = ?1 LIMIT 1")
    .bind(String(body.todo_id ?? "")).first<Record<string, unknown>>();
  if (!todo) return json(404, { error: "that item is gone" }, cors);

  // SNAPSHOT BEFORE ANYTHING IS WRITTEN. Every notification below is guarded on
  // a real transition against these values, not on the field merely being
  // present in the body -- otherwise a page that PATCHes its whole form on
  // every keystroke would text the assignee about a deadline that never moved.
  const wasAssignees = String(todo.assignees ?? "") || "[]";
  const wasDue = String(todo.due ?? "");
  const wasStage = String(todo.stage ?? "") || "todo";
  const wasStatus = String(todo.status ?? "");

  const next: Record<string, unknown> = {};
  const bad = (error: string) => json(400, { error }, cors);

  if ("title" in body) {
    const t = String(body.title ?? "").trim();
    if (!t || t.length > 500) return bad("a title between 1 and 500 characters");
    next.title = t;
  }
  if ("notes" in body) next.notes = String(body.notes ?? "").slice(0, 20000);
  if ("due" in body) {
    const due = String(body.due ?? "").trim();
    if (due && !DATE_RE.test(due)) return bad("due date should be YYYY-MM-DD");
    next.due = due;
  }
  if ("assignees" in body && Array.isArray(body.assignees)) {
    const ids: string[] = [];
    for (const id of body.assignees) {
      const p = await personById(env, String(id));
      if (!p) return bad("one of the flagged people doesn't exist");
      ids.push(String(p.id));
    }
    next.assignees = JSON.stringify(ids);
  }
  if ("watchers" in body && Array.isArray(body.watchers)) {
    const ws: string[] = [];
    for (const id of body.watchers) {
      const p = await personById(env, String(id));
      if (!p) return bad("one of the watchers doesn't exist");
      ws.push(String(p.id));
    }
    next.watchers = JSON.stringify(ws);
  }
  if ("stage" in body) {
    const st = String(body.stage ?? "").trim();
    if (!STAGES.includes(st)) return bad("pick a stage");
    next.stage = st;
    // The hold line belongs to the held stages. Leaving a stale "waiting on
    // Jose's dock rig" on a task that is moving again is a chip that lies.
    if (st !== "blocked" && st !== "waiting") next.hold_reason = "";
  }
  if ("hold_reason" in body) {
    next.hold_reason = String(body.hold_reason ?? "").trim().slice(0, 200);
  }
  if ("priority" in body) {
    const pr = String(body.priority ?? "").trim();
    if (!PRIORITIES.includes(pr)) {
      return bad("priority is urgent, important, normal or later");
    }
    next.priority = pr;
  }
  if ("position" in body) {
    // Hand-ordering. A float so a drop writes ONE row (the midpoint of its new
    // neighbours). CLAMPED, not rejected: a NaN from a broken client should
    // become "unordered", never a 400 that kills the rest of the patch.
    let pos = Number(body.position);
    if (!isFinite(pos) || pos < 0) pos = 0;
    next.position = pos;
  }
  if ("due_time" in body) {
    const dt = String(body.due_time ?? "").trim();
    if (dt && !TIME_RE.test(dt)) return bad("a time looks like 14:30");
    next.due_time = dt;
  }
  if ("repeat_rule" in body) {
    const rr = String(body.repeat_rule ?? "").trim();
    if (rr && !REPEAT_RE.test(rr)) return bad("that repeat isn't one I know");
    next.repeat_rule = rr;
  }
  if ("subtasks" in body && Array.isArray(body.subtasks)) {
    if (body.subtasks.length > 40) {
      return bad("forty subtasks is plenty — the rest are their own task");
    }
    const subs: Array<{ t: string; done: boolean }> = [];
    for (const s of body.subtasks as Array<Record<string, unknown>>) {
      const t = String(s?.t ?? "").trim().slice(0, 200);
      if (!t) continue;
      subs.push({ t, done: !!s?.done });
    }
    next.subtasks = JSON.stringify(subs);
  }
  if ("attachments" in body && Array.isArray(body.attachments)) {
    if (body.attachments.length > 20) return bad("twenty links is the ceiling");
    const files: Array<Record<string, unknown>> = [];
    for (const f of body.attachments as Array<Record<string, unknown>>) {
      const n = String(f?.n ?? "").trim().slice(0, 200);
      if (!n) continue;
      // A LINK AND A NAME, NEVER AN UPLOAD. The Railway volume has already
      // been filled once by the activity ledger. Only http(s) is stored, so a
      // pasted javascript: or data: URL cannot become a click target on a page
      // three people trust.
      const url = String(f?.url ?? "").trim().slice(0, 500);
      if (url && !/^https?:\/\//i.test(url)) {
        return bad("a link has to start with http:// or https://");
      }
      files.push({ n, url, by: actor.id, at: isoNow() });
    }
    next.attachments = JSON.stringify(files);
  }
  if ("remind_at" in body) {
    const ra = String(body.remind_at ?? "").trim();
    if (ra && !REMIND_RE.test(ra)) return bad("reminder time looks malformed");
    next.remind_at = ra;
    next.remind_sent_at = "";      // re-arm: a moved reminder fires again
    next.remind_attempts = 0;      // and gets its full retry budget back
    if ("remind_channel" in body) {
      const rc = String(body.remind_channel ?? "");
      if (ra && !CHANNELS.includes(rc)) return bad("pick email, sms or both");
      next.remind_channel = ra ? rc : "";
    }
  }

  // FINISHING SOMETHING IS IDEMPOTENT. Arav's first minutes on the board
  // produced SIX todo.done rows for three todos -- same actor, same second: a
  // double click, or a client retry, sends the mutation twice, and this route
  // logged both and let the second overwrite done_at/done_by. The activity
  // feed is the audit trail; a trail saying a thing happened twice is wrong.
  // Only a real transition counts.
  let justFinished = false;
  if ("status" in body) {
    const s = String(body.status ?? "");
    if (!STATUSES.includes(s)) return bad("status is open, done or cancelled");
    const wasOpen = String(todo.status ?? "") === "open";
    next.status = s;
    if (s !== "open" && wasOpen) {
      // done_at is stamped for a CANCELLATION too -- it is "the day this left
      // the board", and it is what keeps a cancelled row inside
      // /internal/state's fourteen-day window instead of vanishing mid-week.
      next.done_at = isoNow();          // T-format column
      next.done_by = actor.id;
      justFinished = s === "done";
    } else if (s === "open" && !wasOpen) {
      next.done_at = ""; next.done_by = "";
    }
  }

  const cols = Object.keys(next);
  if (cols.length) {
    const binds = cols.map((c) => next[c]);
    binds.push(pbNow(), String(todo.id));
    await env.DB.prepare(
      `UPDATE internal_todos SET ${cols.map((c, i) => `${c} = ?${i + 1}`).join(", ")}, `
      + `updated = ?${binds.length - 1} WHERE id = ?${binds.length}`,
    ).bind(...binds).run();
  }

  const title = String(next.title ?? todo.title ?? "").slice(0, 300);
  const todoId = String(todo.id);
  if (justFinished) {
    await logActivity(env, actor, "todo.done",
      String(actor.name ?? "") + " finished “" + title.slice(0, 80) + "”",
      "finished this", todoId);
  }

  // ---- notifications, ONE PER REAL TRANSITION -----------------------------
  // Written here and nowhere else in this handler, so the snapshot guards are
  // the only thing standing between a form re-submit and someone's phone.
  const nowAssignees = String(next.assignees ?? wasAssignees);
  const nowDue = String(next.due ?? wasDue);
  const nowStage = String(next.stage ?? wasStage) || "todo";
  const watchers = listOf(next.watchers ?? todo.watchers);
  const actorId = String(actor.id);
  const actorName = String(actor.name ?? "");

  if (nowAssignees !== wasAssignees) {
    const had = new Set(listOf(wasAssignees));
    for (const id of listOf(nowAssignees)) {
      if (!had.has(id)) {
        await notify(env, actorId, id, "assign", actorName + " gave you a task", title, todoId);
      }
    }
  }
  if (nowDue !== wasDue) {
    const when = nowDue ? "moved a deadline to " + nowDue : "took the deadline off";
    for (const id of listOf(nowAssignees)) {
      await notify(env, actorId, id, "deadline", actorName + " " + when, title, todoId);
    }
    for (const id of watchers) {
      await notify(env, actorId, id, "deadline", actorName + " " + when, title, todoId);
    }
  }
  if (nowStage === "blocked" && wasStage !== "blocked") {
    await notify(env, actorId, String(todo.created_by ?? ""), "task",
      actorName + " is blocked",
      // The reason if there is one, otherwise the title -- a "blocked" ping
      // with an empty body tells the creator nothing.
      (String(next.hold_reason ?? todo.hold_reason ?? "") || title).slice(0, 300),
      todoId);
  }
  if (justFinished && wasStatus === "open") {
    await notify(env, actorId, String(todo.created_by ?? ""), "done",
      actorName + " finished a task", title, todoId);
    for (const id of watchers) {
      await notify(env, actorId, id, "done", actorName + " finished a task", title, todoId);
    }
  }
  return json(200, { ok: true }, cors);
}

// ---------------------------------------------------------------------------
// POST /internal/todos/delete -- creator or admin only. Destruction stays human.
// ---------------------------------------------------------------------------
export async function hqTodoDelete(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  let body: Record<string, unknown> = {};
  try { body = (await req.json()) as Record<string, unknown>; } catch { /* {} */ }
  const got = await actorOr(req, env, body, "pick yourself first", cors);
  if (!got.ok) return got.response;
  const actor = got.actor;

  const todo = await env.DB.prepare("SELECT * FROM internal_todos WHERE id = ?1 LIMIT 1")
    .bind(String(body.todo_id ?? "")).first<Record<string, unknown>>();
  if (!todo) return json(404, { error: "already gone" }, cors);

  const mine = String(todo.created_by ?? "") === String(actor.id);
  if (!mine && !boolDefaultFalse(actor.is_admin)) {
    return json(403, {
      error: "only the person who added it — or an admin — can delete it",
    }, cors);
  }
  const title = String(todo.title ?? "");
  await env.DB.prepare("DELETE FROM internal_todos WHERE id = ?1").bind(todo.id).run();
  await logActivity(env, actor, "todo.delete",
    String(actor.name ?? "") + " deleted “" + title.slice(0, 80) + "”",
    "", String(todo.id));
  return json(200, { ok: true }, cors);
}
