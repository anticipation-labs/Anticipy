/**
 * HQ's calendar, boards, expenses and notes -- internal_hq.pb.js, CONTRACT.md §7.
 *
 *   POST /internal/events            /internal/events/delete
 *   POST /internal/tracks            /internal/tracks/delete
 *   POST /internal/expenses          /internal/expenses/delete
 *   POST /internal/notes             /internal/notes/delete
 *
 * See hq_data.ts for what is proven here and what is not.
 */
import { newRecordId, pbNow } from "../pb/wire.ts";
import { hqCors, type HqEnv } from "./hq.ts";
import { boolDefaultFalse, logActivity, resolveActor, type Person } from "./hq_data.ts";

const json = (status: number, body: unknown, extra?: Record<string, string>) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json", ...(extra ?? {}) },
  });

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const EVENT_DATE_RE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/;

type Row = Record<string, unknown>;

async function readBody(req: Request): Promise<Row> {
  try { return (await req.json()) as Row; } catch { return {}; }
}

/** Key/session door plus a required, ACTIVE actor. */
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
  if (!resolved.person || !boolDefaultFalse(resolved.person.active)) {
    return { ok: false, response: json(400, { error: "pick yourself first" }, cors) };
  }
  return { ok: true, actor: resolved.person };
}

/** Creator-or-admin, the shape every delete in HQ shares. */
function mayDelete(actor: Person, row: Row): boolean {
  return String(row.created_by ?? "") === String(actor.id)
      || boolDefaultFalse(actor.is_admin);
}

// ---------------------------------------------------------------------------
// EVENTS -- calendar entries and countdown chips
// ---------------------------------------------------------------------------
export async function hqEventCreate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  const title = String(body.title ?? "").trim();
  const date = String(body.date ?? "").trim();
  if (!title || title.length > 300) {
    return json(400, { error: "a title between 1 and 300 characters" }, cors);
  }
  if (!EVENT_DATE_RE.test(date)) {
    return json(400, { error: "date should be YYYY-MM-DD (optionally THH:mm)" }, cors);
  }
  const id = newRecordId();
  await env.DB.prepare(
    "INSERT INTO internal_events (id, created, updated, title, date, notes, countdown, created_by) "
    + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
  ).bind(id, pbNow(), pbNow(), title, date,
         String(body.notes ?? "").slice(0, 5000),
         body.countdown ? 1 : 0, String(got.actor.id)).run();

  await logActivity(env, got.actor, "event.create",
    String(got.actor.name ?? "") + " added event “" + title.slice(0, 80) + "” (" + date + ")",
    "", id);
  return json(200, { id }, cors);
}

export async function hqEventDelete(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  const row = await env.DB.prepare("SELECT * FROM internal_events WHERE id = ?1 LIMIT 1")
    .bind(String(body.event_id ?? "")).first<Row>();
  if (!row) return json(404, { error: "already gone" }, cors);
  if (!mayDelete(got.actor, row)) {
    return json(403, { error: "only its creator or an admin can delete it" }, cors);
  }
  await env.DB.prepare("DELETE FROM internal_events WHERE id = ?1").bind(row.id).run();
  return json(200, { ok: true }, cors);
}

// ---------------------------------------------------------------------------
// TRACKS -- the design's Projects, renamed in the UI only. ADMIN ONLY.
// ---------------------------------------------------------------------------
export async function hqTrackUpsert(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const actor = got.actor;
  if (!boolDefaultFalse(actor.is_admin)) {
    return json(403, { error: "only an admin can manage boards" }, cors);
  }

  let members: string[] | null = null;
  if (Array.isArray(body.members)) {
    members = [];
    for (const id of body.members) {
      const p = await env.DB.prepare("SELECT id FROM internal_people WHERE id = ?1 LIMIT 1")
        .bind(String(id)).first<{ id: string }>();
      if (!p) return json(400, { error: "one of those members doesn't exist" }, cors);
      members.push(p.id);
    }
  }

  const sets: Record<string, unknown> = {};
  let id = "";
  let existing: Row | null = null;
  if (body.track_id) {
    existing = await env.DB.prepare("SELECT * FROM internal_tracks WHERE id = ?1 LIMIT 1")
      .bind(String(body.track_id)).first<Row>();
    if (!existing) return json(404, { error: "no such board" }, cors);
    id = String(existing.id);
    if ("name" in body) {
      const n = String(body.name ?? "").trim();
      if (!n) return json(400, { error: "a board needs a name" }, cors);
      sets.name = n;
    }
    if (members !== null) sets.members = JSON.stringify(members);
    if ("active" in body) sets.active = body.active ? 1 : 0;
  } else {
    const n = String(body.name ?? "").trim();
    if (!n || n.length > 120) {
      return json(400, { error: "a board name between 1 and 120 characters" }, cors);
    }
    id = newRecordId();
    sets.name = n;
    sets.kind = String(body.kind ?? "fellowship");
    sets.members = JSON.stringify(members ?? []);
    sets.active = 1;
    sets.archived = 0;
  }

  // `active` and `archived` are DIFFERENT THINGS and both are kept.
  // active=false takes a project out of the New Task picker (POST
  // /internal/todos already refuses "that board is archived"); archived=true
  // only greys the card and drops it from default lists. Collapsing them would
  // mean you cannot put a project away without breaking every task on it.
  if ("desc" in body) sets.desc = String(body.desc ?? "").trim().slice(0, 300);
  if ("archived" in body) sets.archived = body.archived ? 1 : 0;
  if ("notes" in body) sets.notes = String(body.notes ?? "").slice(0, 20000);
  if ("owner" in body) {
    const own = String(body.owner ?? "").trim();
    if (own) {
      const p = await env.DB.prepare("SELECT id FROM internal_people WHERE id = ?1 LIMIT 1")
        .bind(own).first<{ id: string }>();
      if (!p) return json(400, { error: "that owner isn't on the team" }, cors);
      sets.owner = p.id;
    } else {
      sets.owner = "";
    }
  }

  if (existing) {
    const cols = Object.keys(sets);
    if (cols.length) {
      const binds = cols.map((c) => sets[c]);
      binds.push(pbNow(), id);
      await env.DB.prepare(
        `UPDATE internal_tracks SET ${cols.map((c, i) => `${c} = ?${i + 1}`).join(", ")}, `
        + `updated = ?${binds.length - 1} WHERE id = ?${binds.length}`,
      ).bind(...binds).run();
    }
  } else {
    const cols = ["id", "created", "updated", ...Object.keys(sets)];
    const binds = [id, pbNow(), pbNow(), ...Object.keys(sets).map((c) => sets[c])];
    await env.DB.prepare(
      `INSERT INTO internal_tracks (${cols.join(", ")}) `
      + `VALUES (${binds.map((_, i) => `?${i + 1}`).join(", ")})`,
    ).bind(...binds).run();
  }

  const name = String(sets.name ?? existing?.name ?? "");
  await logActivity(env, actor, "track.update",
    String(actor.name ?? "") + " updated board “" + name + "”", "", id);
  return json(200, { id }, cors);
}

export async function hqTrackDelete(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const actor = got.actor;
  if (!boolDefaultFalse(actor.is_admin)) {
    return json(403, { error: "only an admin can remove a project" }, cors);
  }

  const track = await env.DB.prepare("SELECT * FROM internal_tracks WHERE id = ?1 LIMIT 1")
    .bind(String(body.track_id ?? "")).first<Row>();
  if (!track) return json(404, { error: "already gone" }, cors);

  // WHERE THE WORK GOES. Company first, then any other project, and if there is
  // genuinely nowhere to put it the delete is REFUSED.
  //
  // DELETING A PROJECT MUST NEVER DELETE WORK. A todo whose `track` points at a
  // row that no longer exists is invisible on every screen that groups by
  // project -- gone without ever appearing in the activity feed as gone.
  let home: Row | null = null;
  try {
    const all = await env.DB.prepare(
      "SELECT * FROM internal_tracks ORDER BY created ASC LIMIT 50").all<Row>();
    for (const t of all.results ?? []) {
      if (String(t.id) === String(track.id)) continue;
      if (String(t.name ?? "").toLowerCase() === "company") { home = t; break; }
      if (!home) home = t;
    }
  } catch { home = null; }
  if (!home) {
    return json(400, { error: "that's the only project — make another one first" }, cors);
  }

  let moved = 0;
  try {
    const res = await env.DB.prepare(
      "UPDATE internal_todos SET track = ?1, updated = ?2 WHERE track = ?3",
    ).bind(String(home.id), pbNow(), String(track.id)).run();
    moved = Number(res.meta?.changes ?? 0);
  } catch { moved = 0; }

  const name = String(track.name ?? "");
  await env.DB.prepare("DELETE FROM internal_tracks WHERE id = ?1").bind(track.id).run();
  await logActivity(env, actor, "track.delete",
    String(actor.name ?? "") + " removed the project “" + name.slice(0, 80) + "” — "
      + moved + (moved === 1 ? " task moved to " : " tasks moved to ") + String(home.name ?? ""),
    "removed the project " + name.slice(0, 60), String(home.id));
  return json(200, { moved, moved_to: home.id }, cors);
}

// ---------------------------------------------------------------------------
// EXPENSES -- one table, two lenses. Rows carry the person; "Mine" and
// "Company" are filters over the same honest data.
// ---------------------------------------------------------------------------
export async function hqExpenseCreate(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  const title = String(body.title ?? "").trim().slice(0, 200);
  if (!title) return json(400, { error: "what was the expense for?" }, cors);
  const amount = Math.round(Number(body.amount) * 100) / 100;
  if (!isFinite(amount) || amount <= 0) {
    return json(400, { error: "amount has to be a positive number" }, cors);
  }
  const asked = String(body.currency ?? "").toUpperCase();
  const cur = asked === "CAD" || asked === "USD" ? asked : "CAD";
  const date = String(body.date ?? "").trim();
  if (date && !DATE_RE.test(date)) {
    return json(400, { error: "date should be YYYY-MM-DD" }, cors);
  }
  try {
    const id = newRecordId();
    await env.DB.prepare(
      "INSERT INTO internal_expenses (id, created, updated, title, amount, currency, date, track, person, created_by) "
      + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10)",
    ).bind(id, pbNow(), pbNow(), title, amount, cur,
           date || new Date().toISOString().slice(0, 10),
           String(body.track ?? "").slice(0, 32),
           String(got.actor.id), String(got.actor.id)).run();
    return json(200, { ok: true, id }, cors);
  } catch {
    return json(500, { error: "could not save the expense" }, cors);
  }
}

export async function hqExpenseDelete(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  const row = await env.DB.prepare("SELECT * FROM internal_expenses WHERE id = ?1 LIMIT 1")
    .bind(String(body.expense_id ?? "")).first<Row>();
  if (!row) return json(404, { error: "that expense is already gone" }, cors);
  // Your own expenses, or an admin's broom. Same shape as task deletion.
  if (!mayDelete(got.actor, row)) {
    return json(403, {
      error: "only whoever logged it (or an admin) can delete it",
    }, cors);
  }
  await env.DB.prepare("DELETE FROM internal_expenses WHERE id = ?1").bind(row.id).run();
  return json(200, { ok: true }, cors);
}

// ---------------------------------------------------------------------------
// NOTES -- upsert on one route, because the page has one editor
// ---------------------------------------------------------------------------
export async function hqNoteUpsert(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;
  const actor = got.actor;

  let existing: Row | null = null;
  if (body.note_id) {
    existing = await env.DB.prepare("SELECT * FROM internal_notes WHERE id = ?1 LIMIT 1")
      .bind(String(body.note_id)).first<Row>();
    if (!existing) return json(404, { error: "that note is gone" }, cors);
  }

  const title = "title" in body
    ? String(body.title ?? "").trim().slice(0, 200)
    : String(existing?.title ?? "");
  const text = "body" in body
    ? String(body.body ?? "").slice(0, 50000)
    : String(existing?.body ?? "");
  const track = "track" in body
    ? String(body.track ?? "").slice(0, 32)
    : String(existing?.track ?? "");
  // Checked AFTER the merge, so clearing one field of an existing note is
  // fine and only emptying BOTH is refused.
  if (!title && !text) {
    return json(400, { error: "an empty note isn't worth keeping" }, cors);
  }

  try {
    if (existing) {
      await env.DB.prepare(
        "UPDATE internal_notes SET title = ?1, body = ?2, track = ?3, updated_by = ?4, updated = ?5 WHERE id = ?6",
      ).bind(title, text, track, String(actor.id), pbNow(), String(existing.id)).run();
      return json(200, { ok: true, id: existing.id }, cors);
    }
    const id = newRecordId();
    await env.DB.prepare(
      "INSERT INTO internal_notes (id, created, updated, title, body, track, created_by, updated_by) "
      + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
    ).bind(id, pbNow(), pbNow(), title, text, track,
           String(actor.id), String(actor.id)).run();
    return json(200, { ok: true, id }, cors);
  } catch {
    return json(500, { error: "could not save the note" }, cors);
  }
}

export async function hqNoteDelete(req: Request, env: HqEnv): Promise<Response> {
  const cors = hqCors(req, env);
  const body = await readBody(req);
  const got = await actorOf(req, env, body, cors);
  if (!got.ok) return got.response;

  const row = await env.DB.prepare("SELECT * FROM internal_notes WHERE id = ?1 LIMIT 1")
    .bind(String(body.note_id ?? "")).first<Row>();
  if (!row) return json(404, { error: "already gone" }, cors);
  if (!mayDelete(got.actor, row)) {
    return json(403, {
      error: "only whoever started it (or an admin) can delete a note",
    }, cors);
  }
  await env.DB.prepare("DELETE FROM internal_notes WHERE id = ?1").bind(row.id).run();
  return json(200, { ok: true }, cors);
}
