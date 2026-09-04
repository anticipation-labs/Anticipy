/**
 * POST /internal/assistant — internal_hq.pb.js:1465-2014, CONTRACT.md §7.
 *
 * "A little chat button on the side that can control the to-dos — not an
 * AI-first interface." It can talk, or it can take exactly ONE action.
 *
 * THE ASSISTANT WAS BLIND, and fixing that is most of this file's context
 * budget. It used to be handed the team's NAMES and the BOARD NAMES and
 * nothing else — not one todo. Asked "what is on the board right now?" it
 * answered, from inside the dashboard, "I don't have direct visibility into
 * the current live tasks... you can check the dashboard directly." Three
 * different questions, three versions of go-look-yourself. So it gets the
 * board: open items only, newest 60, titles clipped — bounded because this
 * rides on every message and tokens are not free.
 *
 * THE SYSTEM PROMPT IS A WISH; THE BRANCHES BELOW ARE THE GUARANTEE. Every
 * enum the model can emit is re-validated in code. A model that returns
 * stage:"done" must be refused here — "done" on `stage` would silently take
 * the row out of the reminder cron, /internal/state and the board.
 *
 * The assistant gets NO MORE POWER than the person talking to it: delete is
 * creator-or-admin, creating a project is admin-only.
 */
import { newRecordId, pbNow } from "../pb/wire.ts";
import { hqCors, type HqEnv } from "./hq.ts";
import { boolDefaultFalse, isoNow, resolveActor, type Person } from "./hq_data.ts";

const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

type Row = Record<string, unknown>;
const STAGES = ["todo", "doing", "waiting", "blocked"];
const PRIORITIES = ["urgent", "important", "normal", "later"];
const CHANNELS = ["email", "sms", "both"];
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const EVENT_DATE_RE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/;
const REMIND_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const PHONE_RE = /^\+?\d{8,15}$/;

const listOf = (raw: unknown): string[] => {
  try {
    const p = JSON.parse(String(raw ?? "") || "[]");
    return Array.isArray(p) ? p.map(String) : [];
  } catch { return []; }
};

export async function hqAssistant(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  if (!(env.ANTICIPY_INTERNAL_KEY || "")) {
    return json(503, { error: "internal HQ is not configured" }, cors);
  }
  let body: Row = {};
  try { body = (await req.json()) as Row; } catch { /* {} */ }

  const resolved = await resolveActor(req, env, {
    actorId: String(body.actor_id ?? ""), optional: true,
  });
  if (!resolved.ok) return resolved.response;
  const actor = resolved.person;
  if (!actor) return json(400, { error: "pick yourself first" }, cors);

  const msgs = Array.isArray(body.messages) ? (body.messages as Row[]) : [];
  if (!msgs.length || msgs.length > 12) {
    return json(400, { error: "between 1 and 12 messages" }, cors);
  }

  const all = async (sql: string, ...b: unknown[]): Promise<Row[]> => {
    try { return (await env.DB.prepare(sql).bind(...b).all<Row>()).results ?? []; }
    catch { return []; }
  };

  // ---- the meter, shared with the router that used to exist ---------------
  // Never blocking: a meter that cannot be read must not take the assistant
  // down, but a tripped one is a hard 429 with the hour named.
  try {
    const hourNow = new Date().toISOString().slice(0, 13);
    const meter = await env.DB.prepare(
      "SELECT * FROM internal_meter WHERE name = 'llm' LIMIT 1").first<Row>();
    if (meter) {
      const used = String(meter.hour ?? "") === hourNow ? Number(meter.calls) || 0 : 0;
      const ceiling = parseInt(env.ANTICIPY_INTERNAL_LLM_CEILING || "60", 10);
      if (used >= ceiling) {
        return json(429, {
          error: "the team's AI budget for this hour is used up",
          resumes: "top of the hour",
        }, cors);
      }
      await env.DB.prepare(
        "UPDATE internal_meter SET hour = ?1, calls = ?2, updated = ?3 WHERE id = ?4")
        .bind(hourNow, used + 1, pbNow(), String(meter.id)).run();
    }
  } catch (err) {
    console.log("internal_hq: llm meter failed (never blocking): " + err);
  }

  // ---- live context so "flag it to Ari" resolves ---------------------------
  const nowMs = Date.now();
  const nameOf: Record<string, string> = {};
  const peopleLines: string[] = [];
  const contactless: string[] = [];
  for (const p of await all(
    "SELECT id,name,email,phone FROM internal_people WHERE active = 1 ORDER BY created ASC LIMIT 60")) {
    nameOf[String(p.id)] = String(p.name ?? "");
    peopleLines.push(String(p.name ?? ""));
    if (!String(p.email ?? "") && !String(p.phone ?? "")) contactless.push(String(p.name ?? ""));
  }
  const trackName: Record<string, string> = {};
  const trackLines: string[] = [];
  for (const t of await all(
    "SELECT id,name FROM internal_tracks WHERE active = 1 ORDER BY created ASC LIMIT 20")) {
    trackName[String(t.id)] = String(t.name ?? "");
    trackLines.push(String(t.name ?? ""));
  }

  const openRows = await all(
    "SELECT * FROM internal_todos WHERE status = 'open' ORDER BY created ASC LIMIT 60");
  const openCount = openRows.length;
  const boardLines: string[] = [];
  for (const t of openRows) {
    const who = listOf(t.assignees).map((id) => nameOf[id]).filter(Boolean);
    const days = Math.floor((nowMs - new Date(String(t.created ?? "").replace(" ", "T")).getTime()) / 86400000);
    const bits = [
      "- " + String(t.title ?? "").slice(0, 90),
      "[" + (trackName[String(t.track ?? "")] || "?") + "]",
      who.length ? "-> " + who.join(", ") : "-> nobody",
    ];
    // stage and priority ride along because the assistant can SET them, and a
    // tool that can set a field it cannot see will happily "change" a task to
    // the state it is already in and report that it did something.
    const stg = String(t.stage ?? "") || "todo";
    if (stg !== "todo") bits.push("(" + stg + ")");
    const pri = String(t.priority ?? "") || "normal";
    if (pri !== "normal") bits.push("[" + pri + "]");
    if (String(t.due ?? "")) bits.push("due " + String(t.due));
    if (isFinite(days) && days >= 1) bits.push(days + "d old");
    boardLines.push(bits.join(" "));
  }

  const recent = (await all(
    "SELECT subject FROM internal_activity ORDER BY created DESC LIMIT 12"))
    .map((a) => "- " + String(a.subject ?? "").slice(0, 90));

  const tz = env.ANTICIPY_INTERNAL_TZ || "America/New_York";
  const system = [
    "You are the assistant inside Anticipy HQ, a small team dashboard. You can talk, or you can act.",
    "Now (UTC): " + new Date().toISOString() + ". The team's timezone: " + tz + ". Interpret spoken times in that timezone and output remind_at as UTC ISO (YYYY-MM-DDTHH:mm).",
    "Team members: " + (peopleLines.join(", ") || "none yet") + ".",
    "Boards: " + (trackLines.join(", ") || "none") + ".",
    "The person speaking to you is: " + String(actor.name ?? "") + ".",
    "",
    "THE BOARD RIGHT NOW (" + openCount + " open):",
    (boardLines.join("\n") || "- nothing open"),
    "",
    "LATELY:",
    (recent.join("\n") || "- nothing yet"),
    (contactless.length
      ? "\nNOTE: these people have no email and no phone, so no reminder can ever reach them: "
        + contactless.join(", ") + ". Say so if it is relevant to what is being asked."
      : ""),
    "",
    "Answer questions about the board from the list above — you can see it, so never tell",
    "anyone to go and look at the dashboard themselves.",
    "Reply with STRICT JSON only. Either {\"say\":\"...\"} to talk, or ONE action:",
    '{"action":{"type":"create_todo","title":"...","track_name":"...","assignee_names":["..."],"due":"YYYY-MM-DD","notes":"...","remind_at":"...","remind_channel":"email|sms|both"}}',
    '{"action":{"type":"complete_todo","match":"substring of the todo title"}}',
    '{"action":{"type":"assign_todo","match":"...","assignee_names":["..."]}}',
    '{"action":{"type":"set_reminder","match":"...","remind_at":"...","remind_channel":"email|sms|both"}}',
    '{"action":{"type":"create_event","title":"...","date":"YYYY-MM-DD","countdown":true}}',
    '{"action":{"type":"add_person","name":"...","email":"...","phone":"..."}}',
    '{"action":{"type":"set_contact","person_name":"...","email":"...","phone":"..."}}',
    '{"action":{"type":"set_priority","match":"...","priority":"urgent|important|normal|later"}}',
    '{"action":{"type":"set_stage","match":"...","stage":"todo|doing|waiting|blocked","hold_reason":"..."}}',
    '{"action":{"type":"add_subtask","match":"...","text":"..."}}',
    '{"action":{"type":"comment","match":"...","text":"..."}}',
    '{"action":{"type":"create_project","name":"...","desc":"..."}}',
    '{"action":{"type":"delete_todo","match":"..."}}',
    "Optional fields may be omitted. delete_todo is for 'remove/delete this' — it erases the",
    "item; complete_todo is for 'done/finished'. Never guess between them from vague wording.",
    "If a name or match is ambiguous or unknown, do NOT act — say so and ask which one.",
  ].join("\n");

  const messages: Array<{ role: string; content: string }> = [{ role: "system", content: system }];
  let total = 0;
  for (const m of msgs) {
    const role = m.role === "assistant" ? "assistant" : "user";
    const content = String(m.content ?? "").slice(0, 1500);
    total += content.length;
    messages.push({ role, content });
  }
  if (total > 6000) {
    return json(400, { error: "that conversation got long — start fresh" }, cors);
  }

  const orKey = env.OPENROUTER_API_KEY || "";
  if (!orKey) return json(503, { error: "no AI key configured on the server" }, cors);
  const model = env.ANTICIPY_INTERNAL_MODEL || "google/gemini-3.7-flash";

  let text = "";
  try {
    const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + orKey,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://anticipy.ai",
        "X-Title": "Anticipy HQ",
      },
      // JSON MODE AND A GENEROUS CEILING — both are load-bearing.
      //
      // At max_tokens 700 this failed roughly two times in five with
      // finish_reason "length": the model spends REASONING tokens against the
      // same budget, so the JSON was being truncated mid-object and the person
      // just saw "say that again?". Measured: 700 -> 3/5 parsed, 2000 -> 5/5.
      // Billing is by tokens actually used, not the ceiling, so this is free.
      //
      // Do NOT "optimise" by excluding reasoning — tried, drops to 0/5.
      body: JSON.stringify({
        model, messages, temperature: 0, max_tokens: 2000,
        response_format: { type: "json_object" },
      }),
      // $http.send took `timeout: 60`. fetch has no timeout option and
      // AbortSignal is the equivalent; without it a hung upstream holds the
      // whole request open.
      signal: AbortSignal.timeout(60_000),
    });
    const data = await res.json() as Row;
    const choices = (data.choices ?? []) as Row[];
    text = String(((choices[0]?.message ?? {}) as Row).content ?? "");
  } catch {
    return json(502, { error: "the AI didn't answer — try again" }, cors);
  }

  let parsed: Row | null = null;
  try { parsed = JSON.parse(text) as Row; } catch {
    // A model that wrapped its JSON in prose still gets read.
    const a = text.indexOf("{"), b = text.lastIndexOf("}");
    if (a >= 0 && b > a) { try { parsed = JSON.parse(text.slice(a, b + 1)) as Row; } catch { /* no */ } }
  }
  if (!parsed) return json(200, { say: "Sorry — say that again?" }, cors);
  if (parsed.say) return json(200, { say: String(parsed.say).slice(0, 800) }, cors);
  const action = (parsed.action ?? null) as Row | null;
  if (!action || !action.type) return json(200, { say: "Sorry — say that again?" }, cors);

  // ---- resolvers. Ambiguity NEVER acts; it asks. --------------------------
  type Found = { rec?: Row; err?: string };
  const findPersonByName = async (name: unknown): Promise<Found> => {
    const want = String(name ?? "").trim().toLowerCase();
    if (!want) return { err: "no name given" };
    const hits = (await all(
      "SELECT * FROM internal_people WHERE active = 1 ORDER BY name ASC LIMIT 100"))
      .filter((p) => {
        const n = String(p.name ?? "").toLowerCase();
        return n === want || n.indexOf(want) === 0;
      });
    if (hits.length === 1) return { rec: hits[0] };
    if (!hits.length) return { err: "I don't know anyone called " + String(name) };
    return { err: "which " + String(name) + " — " + hits.map((h) => String(h.name)).join(" or ") + "?" };
  };
  const findTrackByName = async (name: unknown): Promise<Found> => {
    const want = String(name ?? "").trim().toLowerCase();
    const hits = (await all(
      "SELECT * FROM internal_tracks WHERE active = 1 ORDER BY created ASC LIMIT 20"))
      .filter((t) => {
        const n = String(t.name ?? "").toLowerCase();
        return n === want || n.indexOf(want) >= 0;
      });
    if (hits.length === 1) return { rec: hits[0] };
    if (!hits.length) return { err: "no board called " + String(name) };
    return { err: "which board — " + hits.map((h) => String(h.name)).join(" or ") + "?" };
  };
  const findTodoByMatch = async (match: unknown): Promise<Found> => {
    const want = String(match ?? "").trim().toLowerCase();
    if (want.length < 3) return { err: "give me a few words of the title" };
    const hits = (await all(
      "SELECT * FROM internal_todos WHERE status = 'open' ORDER BY created DESC LIMIT 200"))
      .filter((t) => String(t.title ?? "").toLowerCase().indexOf(want) >= 0);
    if (hits.length === 1) return { rec: hits[0] };
    if (!hits.length) return { err: "I can't find an open item matching “" + String(match) + "”" };
    return { err: "that matches " + hits.length + " items — be more specific" };
  };
  const logAct = async (act: string, subject: string, ref: string) => {
    try {
      await env.DB.prepare(
        "INSERT INTO internal_activity (id, created, actor, actor_name, action, subject, verb, ref) "
        + "VALUES (?1,?2,?3,?4,?5,?6,'',?7)",
      ).bind(newRecordId(), pbNow(), String(actor.id), String(actor.name ?? ""),
             act, subject, ref || "").run();
    } catch { /* the ledger is not the act */ }
  };
  const say = (s: string) => json(200, { say: s }, cors);
  const done = (summary: string) => json(200, { done: { summary, action } }, cors);

  try {
    const type = String(action.type);

    if (type === "create_todo") {
      const title = String(action.title ?? "").trim().slice(0, 500);
      if (!title) return say("What should the item say?");
      const tr = await findTrackByName(action.track_name ?? "Company");
      if (tr.err) return say(tr.err);
      const ids: string[] = []; const names: string[] = [];
      if (Array.isArray(action.assignee_names)) {
        for (const n of action.assignee_names) {
          const f = await findPersonByName(n);
          if (f.err) return say(f.err);
          ids.push(String(f.rec!.id)); names.push(String(f.rec!.name ?? ""));
        }
      }
      const due = DATE_RE.test(String(action.due ?? "")) ? String(action.due) : "";
      const ra = REMIND_RE.test(String(action.remind_at ?? "")) ? String(action.remind_at) : "";
      const rc = CHANNELS.includes(String(action.remind_channel ?? ""))
        ? String(action.remind_channel) : (ra ? "email" : "");
      const id = newRecordId();
      await env.DB.prepare(
        "INSERT INTO internal_todos (id, created, updated, title, notes, track, assignees, due,"
        + " status, created_by, remind_at, remind_channel, remind_sent_at, followup_sent_at,"
        + " remind_attempts, stage, priority, due_time, repeat_rule, hold_reason, watchers,"
        + " subtasks, attachments, cmt_count, done_at, done_by, research_job_id, position)"
        + " VALUES (?1,?2,?3,?4,?5,?6,?7,?8,'open',?9,?10,?11,'','',0,'todo','normal','','','','[]','[]','[]',0,'','','',0)",
      ).bind(id, pbNow(), pbNow(), title, String(action.notes ?? "").slice(0, 20000),
             String(tr.rec!.id), JSON.stringify(ids), due, String(actor.id),
             ra, ra ? rc : "").run();
      const summary = "Created “" + title + "” on " + String(tr.rec!.name ?? "")
        + (names.length ? " — flagged to " + names.join(", ") : "")
        + (due ? ", due " + due : "") + (ra ? ", reminder armed" : "");
      await logAct("assistant.action", summary, id);
      return done(summary);
    }

    if (type === "complete_todo") {
      const f = await findTodoByMatch(action.match);
      if (f.err) return say(f.err);
      await env.DB.prepare(
        "UPDATE internal_todos SET status = 'done', done_at = ?1, done_by = ?2, updated = ?3 WHERE id = ?4")
        .bind(isoNow(), String(actor.id), pbNow(), String(f.rec!.id)).run();
      const summary = "Marked “" + String(f.rec!.title ?? "") + "” done";
      await logAct("assistant.action", summary, String(f.rec!.id));
      return done(summary);
    }

    if (type === "delete_todo") {
      const f = await findTodoByMatch(action.match);
      if (f.err) return say(f.err);
      // Same rule as the delete button: yours, or an admin's broom. The
      // assistant gets no more power than the person talking to it has.
      const mine = String(f.rec!.created_by ?? "") === String(actor.id);
      if (!mine && !boolDefaultFalse(actor.is_admin)) {
        return say("Only " + (nameOf[String(f.rec!.created_by ?? "")] || "whoever added it")
          + " or an admin can delete “" + String(f.rec!.title ?? "").slice(0, 60) + "”.");
      }
      const title2 = String(f.rec!.title ?? "");
      await env.DB.prepare("DELETE FROM internal_todos WHERE id = ?1").bind(String(f.rec!.id)).run();
      const summary = "Deleted “" + title2.slice(0, 80) + "”";
      await logAct("assistant.action", summary, "");
      return done(summary);
    }

    if (type === "assign_todo") {
      const f = await findTodoByMatch(action.match);
      if (f.err) return say(f.err);
      const ids: string[] = []; const names: string[] = [];
      for (const n of (action.assignee_names as unknown[]) ?? []) {
        const p = await findPersonByName(n);
        if (p.err) return say(p.err);
        ids.push(String(p.rec!.id)); names.push(String(p.rec!.name ?? ""));
      }
      if (!ids.length) return say("Flag it to whom?");
      await env.DB.prepare("UPDATE internal_todos SET assignees = ?1, updated = ?2 WHERE id = ?3")
        .bind(JSON.stringify(ids), pbNow(), String(f.rec!.id)).run();
      const summary = "Flagged “" + String(f.rec!.title ?? "") + "” to " + names.join(", ");
      await logAct("assistant.action", summary, String(f.rec!.id));
      return done(summary);
    }

    if (type === "set_reminder") {
      const f = await findTodoByMatch(action.match);
      if (f.err) return say(f.err);
      const ra = String(action.remind_at ?? "");
      if (!REMIND_RE.test(ra)) return say("When exactly? Give me a date and time.");
      const rc = CHANNELS.includes(String(action.remind_channel ?? ""))
        ? String(action.remind_channel) : "email";
      await env.DB.prepare(
        "UPDATE internal_todos SET remind_at = ?1, remind_channel = ?2, remind_sent_at = '', "
        + "remind_attempts = 0, updated = ?3 WHERE id = ?4")
        .bind(ra, rc, pbNow(), String(f.rec!.id)).run();
      const summary = "Reminder set on “" + String(f.rec!.title ?? "") + "” (" + rc + ")";
      await logAct("assistant.action", summary, String(f.rec!.id));
      return done(summary);
    }

    if (type === "create_event") {
      const title = String(action.title ?? "").trim().slice(0, 300);
      const date = String(action.date ?? "");
      if (!title) return say("What's the event called?");
      if (!EVENT_DATE_RE.test(date)) return say("What date is that? (YYYY-MM-DD)");
      const id = newRecordId();
      await env.DB.prepare(
        "INSERT INTO internal_events (id, created, updated, title, date, notes, countdown, created_by) "
        + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
      ).bind(id, pbNow(), pbNow(), title, date, String(action.notes ?? "").slice(0, 5000),
             action.countdown !== false ? 1 : 0, String(actor.id)).run();
      const summary = "Added event “" + title + "” on " + date;
      await logAct("assistant.action", summary, id);
      return done(summary);
    }

    if (type === "add_person") {
      const name = String(action.name ?? "").trim().slice(0, 120);
      if (!name) return say("What's their name?");
      for (const d of await all(
        "SELECT name FROM internal_people WHERE active = 1 ORDER BY name ASC LIMIT 200")) {
        if (String(d.name ?? "").toLowerCase() === name.toLowerCase()) {
          return say(name + " is already on the team.");
        }
      }
      const email = String(action.email ?? "").trim();
      const phone = String(action.phone ?? "").trim().replace(/[\s()-]/g, "");
      if (email && !EMAIL_RE.test(email)) return say("That email doesn't look right.");
      if (phone && !PHONE_RE.test(phone)) return say("That phone number doesn't look right.");
      const id = newRecordId();
      await env.DB.prepare(
        "INSERT INTO internal_people (id, created, updated, name, email, phone, is_admin, active,"
        + " role, focus, tz, remind_pref, email_on, sms_on, code_hash, code_set_at, last_in)"
        + " VALUES (?1,?2,?3,?4,?5,?6,0,1,'','','','inapp',1,1,'','','')",
      ).bind(id, pbNow(), pbNow(), name, email, phone).run();
      const summary = "Added " + name + " to the team";
      await logAct("assistant.action", summary, id);
      return done(summary);
    }

    // The assistant could DIAGNOSE that nobody on the team is reachable and
    // then do nothing about it — the same inert-insight problem the People
    // view has. If it can name the problem it should be able to close it:
    // "my email is x@y.com" now lands.
    if (type === "set_contact") {
      const who = String(action.person_name ?? "").trim();
      const hits = (await all(
        "SELECT * FROM internal_people WHERE active = 1 ORDER BY name ASC LIMIT 200"))
        .filter((p) => String(p.name ?? "").toLowerCase() === who.toLowerCase());
      if (hits.length > 1) return say("There's more than one " + who + " — which?");
      const target = hits[0];
      if (!target) return say(who ? "I don't know a " + who + " on the team." : "Whose details are these?");

      const hasEmail = "email" in action, hasPhone = "phone" in action;
      if (!hasEmail && !hasPhone) return say("An email, a phone number, or both?");
      const email = String(action.email ?? "").trim();
      const phone = String(action.phone ?? "").trim().replace(/[\s()-]/g, "");
      if (hasEmail && email && !EMAIL_RE.test(email)) return say("That email doesn't look right.");
      if (hasPhone && phone && !PHONE_RE.test(phone)) {
        return say("That phone number doesn't look right — include the country code.");
      }
      const sets: string[] = []; const binds: unknown[] = [];
      if (hasEmail) { sets.push("email = ?" + (binds.length + 1)); binds.push(email); }
      if (hasPhone) { sets.push("phone = ?" + (binds.length + 1)); binds.push(phone); }
      binds.push(pbNow(), String(target.id));
      await env.DB.prepare(
        `UPDATE internal_people SET ${sets.join(", ")}, updated = ?${binds.length - 1} WHERE id = ?${binds.length}`,
      ).bind(...binds).run();
      const bits: string[] = [];
      if (hasEmail && email) bits.push("email");
      if (hasPhone && phone) bits.push("phone");
      const summary = bits.length
        ? "Saved " + String(target.name ?? "") + "'s " + bits.join(" and ") + " — reminders can reach them now"
        : "Cleared " + String(target.name ?? "") + "'s contact details";
      await logAct("assistant.action", summary, String(target.id));
      return done(summary);
    }

    // ---- the five verbs whose enums the MODEL must not be trusted with -----
    // Validated here with the same lists the CRUD routes use. The system
    // prompt above is a wish; this is the guarantee.
    if (type === "set_priority") {
      const f = await findTodoByMatch(action.match);
      if (f.err) return say(f.err);
      const pr = String(action.priority ?? "");
      if (!PRIORITIES.includes(pr)) return say("Urgent, important, normal or later?");
      await env.DB.prepare("UPDATE internal_todos SET priority = ?1, updated = ?2 WHERE id = ?3")
        .bind(pr, pbNow(), String(f.rec!.id)).run();
      const summary = "Set “" + String(f.rec!.title ?? "") + "” to " + pr;
      await logAct("assistant.action", summary, String(f.rec!.id));
      return done(summary);
    }

    if (type === "set_stage") {
      const f = await findTodoByMatch(action.match);
      if (f.err) return say(f.err);
      const st = String(action.stage ?? "");
      // A model that returns stage:"done" is refused HERE. "done" on `stage`
      // would silently take the row out of the reminder cron and the board.
      if (!STAGES.includes(st)) return say("To do, in progress, waiting or blocked?");
      const hr = String(action.hold_reason ?? "").trim().slice(0, 200);
      await env.DB.prepare(
        "UPDATE internal_todos SET stage = ?1, hold_reason = ?2, updated = ?3 WHERE id = ?4")
        .bind(st, (st === "blocked" || st === "waiting") ? hr : "", pbNow(), String(f.rec!.id)).run();
      const summary = "Moved “" + String(f.rec!.title ?? "") + "” to " + st + (hr ? " — " + hr : "");
      await logAct("assistant.action", summary, String(f.rec!.id));
      return done(summary);
    }

    if (type === "add_subtask") {
      const f = await findTodoByMatch(action.match);
      if (f.err) return say(f.err);
      const txt = String(action.text ?? "").trim().slice(0, 200);
      if (!txt) return say("What's the step?");
      let subs: Array<{ t: string; done: boolean }> = [];
      try {
        const p = JSON.parse(String(f.rec!.subtasks ?? "") || "[]");
        if (Array.isArray(p)) subs = p;
      } catch { subs = []; }
      if (subs.length >= 40) {
        return say("That one already has forty steps — it wants to be its own task.");
      }
      subs.push({ t: txt, done: false });
      await env.DB.prepare("UPDATE internal_todos SET subtasks = ?1, updated = ?2 WHERE id = ?3")
        .bind(JSON.stringify(subs), pbNow(), String(f.rec!.id)).run();
      const summary = "Added a step to “" + String(f.rec!.title ?? "") + "”: " + txt;
      await logAct("assistant.action", summary, String(f.rec!.id));
      return done(summary);
    }

    if (type === "comment") {
      const f = await findTodoByMatch(action.match);
      if (f.err) return say(f.err);
      const txt = String(action.text ?? "").trim().slice(0, 4000);
      if (!txt) return say("What should it say?");
      await env.DB.prepare(
        "INSERT INTO internal_comments (id, created, updated, todo, author, author_name, text, parent, edited_at, deleted) "
        + "VALUES (?1,?2,?3,?4,?5,?6,?7,'','',0)",
      ).bind(newRecordId(), pbNow(), pbNow(), String(f.rec!.id), String(actor.id),
             String(actor.name ?? ""), txt).run();
      await env.DB.prepare("UPDATE internal_todos SET cmt_count = ?1, updated = ?2 WHERE id = ?3")
        .bind((Number(f.rec!.cmt_count) || 0) + 1, pbNow(), String(f.rec!.id)).run();
      const summary = "Commented on “" + String(f.rec!.title ?? "") + "”";
      await logAct("assistant.action", summary, String(f.rec!.id));
      return done(summary);
    }

    if (type === "create_project") {
      // Same admin guard POST /internal/tracks has. A misheard "new project
      // called Ari" out of "new task for Ari" creates a container that then
      // swallows work, so the one person who can undo it is the only person
      // who can cause it.
      if (!boolDefaultFalse(actor.is_admin)) {
        return say("Only an admin can start a project — ask Omar.");
      }
      const nm = String(action.name ?? "").trim().slice(0, 120);
      if (!nm) return say("What's the project called?");
      for (const t of await all(
        "SELECT name FROM internal_tracks ORDER BY created ASC LIMIT 50")) {
        if (String(t.name ?? "").toLowerCase() === nm.toLowerCase()) {
          return say("There's already a project called " + nm + ".");
        }
      }
      const id = newRecordId();
      await env.DB.prepare(
        "INSERT INTO internal_tracks (id, created, updated, name, kind, members, active, archived, desc, owner, notes) "
        + "VALUES (?1,?2,?3,?4,'company','[]',1,0,?5,?6,'')",
      ).bind(id, pbNow(), pbNow(), nm, String(action.desc ?? "").trim().slice(0, 300),
             String(actor.id)).run();
      const summary = "Started the project “" + nm + "”";
      await logAct("assistant.action", summary, id);
      return done(summary);
    }
  } catch (err) {
    console.log("internal_hq: assistant action failed: " + err);
    return say("That didn't go through — try it by hand?");
  }
  return say("I don't know how to do that yet.");
}
