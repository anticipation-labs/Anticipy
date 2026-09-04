/**
 * HQ's comment threads, reminders and calendar feed -- internal_hq.pb.js.
 *
 *   POST  /internal/comments   PATCH /internal/comments   POST /comments/delete
 *   POST  /internal/reminders  POST /internal/reminders/delete
 *   GET   /internal/cal/{token}.ics
 *
 * See hq_data.ts for what is proven here and what is not.
 */
import { sha256Hex } from "../llm.ts";
import { newRecordId, pbNow } from "../pb/wire.ts";
import { hqCors, type HqEnv } from "./hq.ts";
import {
  boolDefaultFalse, isoNow, logActivity, resolveActor, timingEqual, type Person,
} from "./hq_data.ts";

const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

type Row = Record<string, unknown>;
const readBody = async (req: Request): Promise<Row> => {
  try { return (await req.json()) as Row; } catch { return {}; }
};
const listOf = (raw: unknown): string[] => {
  try {
    const p = JSON.parse(String(raw ?? "") || "[]");
    return Array.isArray(p) ? p.map(String) : [];
  } catch { return []; }
};

async function actorOf(
  req: Request, env: HqEnv, body: Row, cors: Record<string, string>,
): Promise<{ ok: true; actor: Person } | { ok: false; response: Response }> {
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return { ok: false, response: json(503, { error: "internal HQ is not configured" }, cors) };
  }
  const resolved = await resolveActor(req, env, {
    actorId: String(body.actor_id ?? ""), optional: true,
  });
  if (!resolved.ok) return { ok: false, response: resolved.response };
  if (!resolved.person) {
    return { ok: false, response: json(400, { error: "pick yourself first" }, cors) };
  }
  if (!boolDefaultFalse(resolved.person.active)) {
    return { ok: false, response: json(400, { error: "that person is deactivated" }, cors) };
  }
  return { ok: true, actor: resolved.person };
}

// ---------------------------------------------------------------------------
// POST /internal/comments
// ---------------------------------------------------------------------------
export async function hqCommentCreate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const actor = got.actor;

  const todo = await env.DB.prepare("SELECT * FROM internal_todos WHERE id = ?1 LIMIT 1")
    .bind(String(body.todo_id ?? "")).first<Row>();
  if (!todo) return json(404, { error: "that item is gone" }, cors);
  const text = String(body.text ?? "").trim().slice(0, 4000);
  if (!text) return json(400, { error: "say something first" }, cors);

  let parent = "";
  if (body.parent) {
    const p = await env.DB.prepare("SELECT * FROM internal_comments WHERE id = ?1 LIMIT 1")
      .bind(String(body.parent)).first<Row>();
    if (!p) return json(404, { error: "that comment is gone" }, cors);
    // A REPLY BELONGS TO THE THREAD IT WAS WRITTEN IN. Letting one point at a
    // comment on a different task would put somebody's sentence under a task
    // they never opened.
    if (String(p.todo ?? "") !== String(todo.id)) {
      return json(400, { error: "that reply doesn't belong to this task" }, cors);
    }
    parent = String(p.id);
  }

  const id = newRecordId();
  const created = pbNow();
  await env.DB.prepare(
    "INSERT INTO internal_comments (id, created, updated, todo, author, author_name, text, parent, edited_at, deleted) "
    + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8,'',0)",
  ).bind(id, created, pbNow(), String(todo.id), String(actor.id),
         // Denormalised for the same reason internal_activity.actor_name is:
         // the thread has to still read right after somebody is deactivated.
         String(actor.name ?? ""), text, parent).run();

  try {
    await env.DB.prepare(
      "UPDATE internal_todos SET cmt_count = ?1, updated = ?2 WHERE id = ?3",
    ).bind((Number(todo.cmt_count) || 0) + 1, pbNow(), String(todo.id)).run();
  } catch { /* the comment landed; the badge can lag */ }

  // ---- mentions, then everybody else, and NEVER BOTH ----------------------
  const told = new Set<string>([String(actor.id)]);   // never notify yourself
  const push = async (person: string, kind: string, what: string) => {
    if (!person || told.has(person)) return;
    told.add(person);
    try {
      await env.DB.prepare(
        "INSERT INTO internal_notifs (id, created, person, kind, text, sub, todo, actor, read, emailed_at, smsed_at) "
        + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8,0,'','')",
      ).bind(newRecordId(), pbNow(), person, kind,
             String(actor.name ?? "") + " " + what, text.slice(0, 300),
             String(todo.id), String(actor.id)).run();
    } catch { /* one inbox row is not the comment */ }
  };

  // @Name against ACTIVE people only, LONGEST NAME FIRST so "@Jose" inside
  // "@Joseph" cannot claim the wrong person.
  let people: Row[] = [];
  try {
    const res = await env.DB.prepare(
      "SELECT id,name FROM internal_people WHERE active = 1 ORDER BY name ASC LIMIT 100").all<Row>();
    people = res.results ?? [];
  } catch { people = []; }
  people.sort((a, b) => String(b.name ?? "").length - String(a.name ?? "").length);
  const hay = text.toLowerCase();
  for (const p of people) {
    const full = String(p.name ?? "").toLowerCase();
    const first = full.split(/\s+/)[0];
    if (!first) continue;
    if (hay.includes("@" + full) || hay.includes("@" + first)) {
      await push(String(p.id), "mention", "mentioned you");
    }
  }
  for (const id2 of listOf(todo.assignees)) {
    await push(id2, "comment", "commented on your task");
  }
  for (const id2 of listOf(todo.watchers)) {
    await push(id2, "comment", "commented on a task you're watching");
  }

  await logActivity(env, actor, "todo.comment",
    String(actor.name ?? "") + " commented on “" + String(todo.title ?? "").slice(0, 80) + "”",
    "commented", String(todo.id));
  return json(200, { id, created }, cors);
}

// ---------------------------------------------------------------------------
// PATCH /internal/comments -- the author, and ONLY the author.
// ---------------------------------------------------------------------------
export async function hqCommentUpdate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  const c = await env.DB.prepare("SELECT * FROM internal_comments WHERE id = ?1 LIMIT 1")
    .bind(String(body.comment_id ?? "")).first<Row>();
  if (!c) return json(404, { error: "that comment is gone" }, cors);
  // EDITING IS NOT AN ADMIN POWER. An admin can remove a comment; putting
  // different words in somebody else's mouth is a different thing entirely.
  if (String(c.author ?? "") !== String(got.actor.id)) {
    return json(403, { error: "only the person who wrote it can edit it" }, cors);
  }
  if (boolDefaultFalse(c.deleted)) return json(404, { error: "that comment is gone" }, cors);
  const text = String(body.text ?? "").trim().slice(0, 4000);
  if (!text) return json(400, { error: "say something first" }, cors);

  await env.DB.prepare(
    // edited_at is the mark that makes the thread honest: an edited sentence
    // says so.
    "UPDATE internal_comments SET text = ?1, edited_at = ?2, updated = ?3 WHERE id = ?4",
  ).bind(text, isoNow(), pbNow(), String(c.id)).run();
  return json(200, { ok: true }, cors);
}

// ---------------------------------------------------------------------------
// POST /internal/comments/delete -- author or admin. A TOMBSTONE, not a DELETE.
// ---------------------------------------------------------------------------
export async function hqCommentDelete(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const actor = got.actor;

  const c = await env.DB.prepare("SELECT * FROM internal_comments WHERE id = ?1 LIMIT 1")
    .bind(String(body.comment_id ?? "")).first<Row>();
  if (!c) return json(404, { error: "already gone" }, cors);
  if (String(c.author ?? "") !== String(actor.id) && !boolDefaultFalse(actor.is_admin)) {
    return json(403, {
      error: "only the person who wrote it — or an admin — can remove it",
    }, cors);
  }
  if (boolDefaultFalse(c.deleted)) return json(200, { ok: true }, cors);   // idempotent

  // A TOMBSTONE. Deleting the row would orphan every reply hanging off it, and
  // an orphaned reply is a sentence with no question above it -- the thread
  // stops making sense and nobody can tell why. The TEXT is blanked, which is
  // the part that actually needed to go.
  await env.DB.prepare(
    "UPDATE internal_comments SET deleted = 1, text = '', updated = ?1 WHERE id = ?2",
  ).bind(pbNow(), String(c.id)).run();
  try {
    const todo = await env.DB.prepare("SELECT * FROM internal_todos WHERE id = ?1 LIMIT 1")
      .bind(String(c.todo ?? "")).first<Row>();
    if (todo) {
      const n = Number(todo.cmt_count) || 0;
      await env.DB.prepare("UPDATE internal_todos SET cmt_count = ?1, updated = ?2 WHERE id = ?3")
        .bind(n > 0 ? n - 1 : 0, pbNow(), String(todo.id)).run();
    }
  } catch { /* the badge can lag */ }
  return json(200, { ok: true }, cors);
}

// ---------------------------------------------------------------------------
// POST /internal/reminders -- the ones remind_at cannot express.
// ---------------------------------------------------------------------------
const RULES = ["at", "one_hour_before", "one_day_before", "when_overdue", "daily_until_done"];
const CHANNELS = ["inapp", "email", "sms", "both"];

export async function hqReminderCreate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const actor = got.actor;

  const todo = await env.DB.prepare("SELECT * FROM internal_todos WHERE id = ?1 LIMIT 1")
    .bind(String(body.todo_id ?? "")).first<Row>();
  if (!todo) return json(404, { error: "that item is gone" }, cors);

  const rule = String(body.rule ?? "").trim();
  if (!RULES.includes(rule)) {
    return json(400, { error: "I don't know that kind of reminder" }, cors);
  }
  const channel = String(body.channel ?? "inapp").trim();
  if (!CHANNELS.includes(channel)) {
    return json(400, { error: "reminders are in-app, email, sms or both" }, cors);
  }

  let person = "";
  if (body.person) {
    const p = await env.DB.prepare("SELECT id FROM internal_people WHERE id = ?1 LIMIT 1")
      .bind(String(body.person)).first<Row>();
    if (!p) return json(400, { error: "that person isn't on the team" }, cors);
    person = String(p.id);
  }

  // ---- WHO WOULD THIS ACTUALLY REACH -------------------------------------
  // A reminder that cannot reach anybody is a lie printed on a card. In-app
  // always reaches: it is a row in their tray, so the check is skipped.
  //
  // NOTE the predicate is `need && has`, which is NOT the `!need || has` used
  // by POST /internal/todos. They are genuinely different rules -- this one
  // demands a channel that was actually asked for, the other passes anything
  // not asked for -- and both are transcribed as written rather than
  // normalised to whichever looks tidier.
  if (channel !== "inapp") {
    const ids: string[] = [];
    if (person) ids.push(person);
    else {
      for (const id of listOf(todo.assignees)) ids.push(id);
      if (!ids.length && String(todo.created_by ?? "")) ids.push(String(todo.created_by));
    }
    const needEmail = channel === "email" || channel === "both";
    const needPhone = channel === "sms" || channel === "both";
    let reachable = false;
    const missing: string[] = [];
    for (const id of ids) {
      const p = await env.DB.prepare("SELECT * FROM internal_people WHERE id = ?1 LIMIT 1")
        .bind(id).first<Row>();
      if (!p) continue;
      const email = String(p.email ?? "");
      const phone = String(p.phone ?? "");
      if ((needEmail && !!email) || (needPhone && !!phone)) reachable = true;
      if (needEmail && !email) missing.push(String(p.name ?? "") + " has no email on file");
      if (needPhone && !phone) missing.push(String(p.name ?? "") + " has no phone number on file");
    }
    if (!reachable) {
      return json(400, {
        error: missing.join("; ") || "nobody on this has contact details yet",
      }, cors);
    }
  }

  // ---- when does it fire, in UTC -----------------------------------------
  // THE OFFSET COMES FROM THE BROWSER, deliberately. The PocketBase runtime had
  // no timezone database, so the choice was a hand-maintained table of zone
  // offsets -- wrong twice a year, silently -- or asking the one participant
  // that genuinely knows: the page, which computes the recipient's real offset
  // including DST. workerd DOES have Intl, and that is knowingly not used here:
  // this port's job is to answer identically to the file it replaces. Changing
  // the source of truth for somebody's reminder hour is a decision to make
  // once, on both, on purpose.
  let offMin = 0;
  if ("tz_offset" in body) {
    const o = parseInt(String(body.tz_offset), 10);
    // Validated so a malformed or hostile value cannot push a reminder years
    // away. +/- 840 minutes is the real range of world offsets.
    if (isNaN(o) || o < -840 || o > 840) {
      return json(400, { error: "that timezone offset isn't a real one" }, cors);
    }
    offMin = o;
  }

  let anchor = NaN;
  if (String(body.at ?? "")) {
    let s = String(body.at).trim().replace(" ", "T");
    if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(s)) s += "Z";
    anchor = Date.parse(s);
    if (isNaN(anchor)) return json(400, { error: "that time looks malformed" }, cors);
  } else {
    const due = String(todo.due ?? "");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) {
      return json(400, {
        error: "give the task a deadline first, or tell me a time",
      }, cors);
    }
    const dueTime = String(todo.due_time ?? "");
    const hm = /^\d{2}:\d{2}$/.test(dueTime) ? dueTime : "09:00";
    const p = due.split("-"); const t = hm.split(":");
    anchor = Date.UTC(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10),
                      parseInt(t[0], 10), parseInt(t[1], 10), 0) - offMin * 60000;
  }

  let fire = anchor;
  let label = "At the deadline";
  if (rule === "one_hour_before") { fire = anchor - 3600000; label = "One hour before"; }
  else if (rule === "one_day_before") { fire = anchor - 86400000; label = "One day before"; }
  else if (rule === "when_overdue") { fire = anchor + 60000; label = "When it goes overdue"; }
  else if (rule === "daily_until_done") { label = "Every day until it's done"; }
  // A reminder armed for a moment already gone would fire on the very next
  // sweep and read as a bug. Push it to the next sweep boundary instead, so
  // "one hour before" on something due in ten minutes still says something.
  if (fire < Date.now()) fire = Date.now() + 60000;

  const id = newRecordId();
  const fireAt = new Date(fire).toISOString();
  await env.DB.prepare(
    "INSERT INTO internal_reminders (id, created, updated, todo, person, rule, fire_at, channel, label, sent_at, attempts, created_by) "
    + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,'',0,?10)",
  ).bind(id, pbNow(), pbNow(), String(todo.id), person, rule, fireAt, channel,
         label.slice(0, 60), String(actor.id)).run();
  return json(200, { id, fire_at: fireAt, label: label.slice(0, 60) }, cors);
}

export async function hqReminderDelete(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  const rem = await env.DB.prepare("SELECT * FROM internal_reminders WHERE id = ?1 LIMIT 1")
    .bind(String(body.reminder_id ?? "")).first<Row>();
  if (!rem) return json(404, { error: "already gone" }, cors);
  if (String(rem.created_by ?? "") !== String(got.actor.id)
      && !boolDefaultFalse(got.actor.is_admin)) {
    return json(403, {
      error: "only the person who set it — or an admin — can take it off",
    }, cors);
  }
  await env.DB.prepare("DELETE FROM internal_reminders WHERE id = ?1").bind(rem.id).run();
  return json(200, { ok: true }, cors);
}

// ---------------------------------------------------------------------------
// GET /internal/cal/{token}.ics -- a per-person feed any calendar can subscribe
// to, with zero OAuth.
//
// AUTH IS THE TOKEN ITSELF: sha256(teamKey + personId). Deterministic on
// purpose -- no new column, no minting flow, and rotating the team key revokes
// every feed at once. The cost, stated honestly: a leaked feed URL stays valid
// until the key rotates. For a three-person team whose feed contains task
// titles, that trade is taken knowingly.
// ---------------------------------------------------------------------------
export async function hqCalendar(req: Request, env: HqEnv, token: string): Promise<Response> {
  const cors = hqCors(req, env);
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return json(503, { error: "internal HQ is not configured" }, cors);

  let tok = String(token ?? "");
  if (tok.slice(-4) === ".ics") tok = tok.slice(0, -4);
  if (!/^[0-9a-f]{64}$/.test(tok)) return json(404, { error: "not found" }, cors);

  let person: Row | null = null;
  try {
    const res = await env.DB.prepare(
      "SELECT id,name FROM internal_people WHERE active = 1 ORDER BY name ASC LIMIT 200").all<Row>();
    for (const p of res.results ?? []) {
      if (timingEqual(await sha256Hex(key + String(p.id)), tok)) { person = p; break; }
    }
  } catch { person = null; }
  // The same 404 for a malformed token and an unmatched one: this must not
  // become an oracle for which person ids exist.
  if (!person) return json(404, { error: "not found" }, cors);

  // ICS wants CRLF, escaped text, and dates as YYYYMMDD. All-day entries on the
  // due date: a feed that guesses at hours puts wrong hours on somebody's
  // phone, and an all-day banner never lies.
  const esc = (t: unknown) => String(t ?? "")
    .replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,")
    .replace(/\r?\n/g, "\\n").slice(0, 250);
  const day = (d: unknown) => String(d ?? "").replace(/-/g, "");
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Anticipy//HQ//EN",
    "CALSCALE:GREGORIAN", "X-WR-CALNAME:Anticipy HQ", "METHOD:PUBLISH",
  ];
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";

  try {
    const res = await env.DB.prepare(
      "SELECT id,title,due,assignees FROM internal_todos "
      + "WHERE status = 'open' AND due != '' ORDER BY due ASC LIMIT 500").all<Row>();
    for (const t of res.results ?? []) {
      if (!listOf(t.assignees).includes(String(person.id))) continue;
      lines.push("BEGIN:VEVENT",
        "UID:todo-" + String(t.id) + "@anticipy-hq",
        "DTSTAMP:" + stamp,
        "DTSTART;VALUE=DATE:" + day(t.due),
        "SUMMARY:" + esc("HQ: " + String(t.title ?? "")),
        "END:VEVENT");
    }
  } catch { /* a feed with fewer entries beats a 500 in a calendar client */ }

  try {
    const res = await env.DB.prepare(
      "SELECT id,title,date FROM internal_events WHERE date != '' ORDER BY date ASC LIMIT 200").all<Row>();
    for (const ev of res.results ?? []) {
      lines.push("BEGIN:VEVENT",
        "UID:event-" + String(ev.id) + "@anticipy-hq",
        "DTSTAMP:" + stamp,
        "DTSTART;VALUE=DATE:" + day(ev.date),
        "SUMMARY:" + esc(ev.title),
        "END:VEVENT");
    }
  } catch { /* ditto */ }

  lines.push("END:VCALENDAR");
  return new Response(lines.join("\r\n") + "\r\n", {
    status: 200,
    headers: { "content-type": "text/calendar; charset=utf-8", ...cors },
  });
}
