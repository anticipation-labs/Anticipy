/**
 * src/pb/records.ts — the generic records API, on D1.
 *
 *   GET    /api/collections/{name}/records          list
 *   GET    /api/collections/{name}/records/{id}     view
 *   POST   /api/collections/{name}/records          create
 *   PATCH  /api/collections/{name}/records/{id}     update
 *   DELETE /api/collections/{name}/records/{id}     delete
 *
 * This is option (A) from ARCHITECTURE.md §2: reimplement the surface so that
 * no client changes. It is deliberately SMALL, because the audit measured how
 * much of PocketBase's records API this product actually uses:
 *
 *   expand=      0 call sites  (verified: grep across clients/, extension/,
 *   fields=      USED by overnight/are_the_ears_live.py since 2026-09-05 — projected below)
 *   skipTotal=   0 call sites
 *   back-relations / dotted traversal: 0
 *
 * So this file implements filter, sort, page, perPage and nothing else. Every
 * one of those omissions is a 400 with a named parameter, never a silent
 * ignore — a silently-ignored `expand` returns a record with a missing field
 * and the client renders a blank name.
 */
import { filterToSQL, FilterError, compileFilter, type Node } from "../../filter-dsl.ts";
import { COLLECTIONS, parseSort, type CollectionDef } from "./schema.ts";
import {
  json, notFound, badRequest, newRecordId, pbNow, rowToRecord, type ListResponse,
} from "./wire.ts";
import type { Principal } from "../policy/chain.ts";
import bcrypt from "bcryptjs";

export interface Env {
  DB: D1Database;
}

/** PocketBase's default and ceiling. A caller may not ask for more than 500. */
const DEFAULT_PER_PAGE = 30;
const MAX_PER_PAGE = 500;

const UNSUPPORTED = ["expand", "skipTotal"] as const;

// `fields=` IS used now — by the gates, not the phone or the extension:
// overnight/are_the_ears_live.py counts rows with `fields=id` so that not one
// line of speech crosses the wire for a count, and reads the newest row with
// `fields=created,device_id,owner_ref,source` for the same reason. Until
// 2026-09-05 this file answered those with 400 "No client in this product uses
// fields", and the ears gate read UNPROVEN against Cloudflare on every run.
// PocketBase's semantics, kept exactly: a comma list of top-level names;
// names the record does not have are ignored; `*` is everything. Never a
// column the caller could not have read anyway — projection runs on the row
// the rules already released.
export function projectFields(record: Record<string, unknown>, fieldsParam: string | null): Record<string, unknown> {
  const raw = String(fieldsParam ?? "").trim();
  if (!raw || raw === "*") return record;
  const wanted = raw.split(",").map((f) => f.trim()).filter(Boolean);
  if (wanted.includes("*")) return record;
  const out: Record<string, unknown> = {};
  for (const name of wanted) if (name in record) out[name] = record[name];
  return out;
}

// A D1 UNIQUE violation, read from the error's text — the only place SQLite
// tells you which column collided. PocketBase answers a unique-index collision
// on create with 400 { data: { <column>: validation_not_unique } }, and
// brain/worker.py's reserve_uninvited_text (Omi port 10b) reads exactly that:
// a 400 means "slot n is taken, read it back"; anything else means "do not
// text". Until 2026-09-05 the INSERT here threw straight through as a 500, so
// on Cloudflare a collision would have muted the text instead of naming the
// slot. This reads an SQLite message, not a word of the owner's — structure.
// D1 "no such column: X" — the map in schema.ts is ahead of the live table.
// 2026-09-05: the brain's decision stamp (Omi port 06, heard_ms/heard_calls)
// hit exactly this — the map knew the columns, D1 did not — and the UPDATE
// threw straight through as a Cloudflare 1101, which the brain's fail-safe
// (keyed on a 400) never saw; every decided line stayed unstamped and was
// re-heard by the sweep every ten minutes, minting a duplicate job each time.
// A skew between the map and the table is a 400 with the column's name, the
// same shape create() and update() already give an unknown field.
export function missingColumn(message: string): string | null {
  // Two spellings from SQLite: UPDATE/SELECT say "no such column: X",
  // INSERT says "table T has no column named X". Both are the same fact.
  const text = String(message || "");
  const m = /no such column:\s*(?:[A-Za-z0-9_]+\.)?([A-Za-z0-9_]+)/i.exec(text)
    || /has no column named\s+([A-Za-z0-9_]+)/i.exec(text);
  return m ? m[1] : null;
}

// EVERY FIELD HAS A VALUE. PocketBase fills a field the client did not send
// with the field's empty value ("" for text, 0 for number, false for bool) at
// write time, so a row never carries NULL. The live D1 events table was
// created without the NOT NULL DEFAULT '' that migration/d1/schema.sql
// declares, and this file inserted only the keys a client sent — so a row
// posted without `decision` stored NULL, and brain/worker.py's poll
// (`decision=""`) never saw it. The phone never sends `decision` or `goal`
// (AnticipyBackend.swift sets keys conditionally). Measured 2026-09-05 on
// api.anticipy.ai: a line posted as the phone posts it was NULL-decision and
// unheard for ten minutes; the same line with decision:"" was heard in 15 s.
// The fix belongs here, not in a table rebuild: fill the empties the way the
// backend this replaces did, for every mapped column the body omits.
// `live` is the set of columns the table actually has (liveColumns below):
// the map in schema.ts can be AHEAD of the live table — it was on
// 2026-09-05, by heard_ms/heard_calls — and filling a column the table
// lacks turns every create into a 1101, which is exactly what happened for
// two minutes before this parameter existed. Only what both know gets filled.
export function fillEmpties(def: CollectionDef, body: Record<string, unknown>, live?: Set<string>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...body };
  for (const [name, spec] of Object.entries(def.columns)) {
    if (name === "id" || name === def.createdColumn || name === def.updatedColumn) continue;
    if (name in out) continue;
    if (live && !live.has(name)) continue;
    out[name] = spec.type === "number" ? 0 : spec.type === "bool" ? false : "";
  }
  return out;
}

// The live table's columns, asked of SQLite once per isolate per table.
const LIVE_COLUMNS = new Map<string, Set<string>>();
export async function liveColumns(env: Env, table: string): Promise<Set<string>> {
  const cached = LIVE_COLUMNS.get(table);
  if (cached) return cached;
  const res = await env.DB.prepare(`SELECT name FROM pragma_table_info(?1)`).bind(table).all<{ name: string }>();
  const set = new Set((res.results ?? []).map((r) => String(r.name)));
  if (set.size) LIVE_COLUMNS.set(table, set);
  return set;
}

export function uniqueViolationColumn(message: string): string | null {
  const m = /UNIQUE constraint failed:\s*([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)/.exec(String(message || ""));
  return m ? m[2] : null;
}

// ---------------------------------------------------------------------------
// THE MODEL HOOK THIS FILE HAS TO CARRY, because D1 has nowhere else to put it.
//
// backend/pb_hooks/job_commitment_identity.pb.js is nine lines: on create and
// on update of a `jobs` row, a terminal status releases `commitment_key`.
// `idx_jobs_active_commitment` (migration/d1/schema.sql:300-301) is UNIQUE over
// every row whose key is non-empty, and it is the only thing stopping two
// processes both reading "no active promise" and both minting one. PocketBase's
// index validator accepts a nonempty partial predicate but not
// `status IN (...)`, so the predicate cannot say "while active" — the hook has
// to empty the key instead.
//
// WITHOUT IT the key is held FOREVER by a row that has finished, and the next
// mint for the same promise collides with a corpse. Measured on live D1
// (2026-09-05, audit F15): six `done` rows still keyed, all one owner, all
// minted on Cloudflare that afternoon. brain/anticipy_core.py:1413-1431 derives
// the key from tenant + memory node alone, so a retry after a FAILED run mints
// the same key, records.ts turns the collision into 400 validation_not_unique,
// the brain's handler (:4349-4380) searches only ACTIVE statuses, finds nothing,
// and returns QUEUE_WRITE_FAILED — hear() then drops the goal. The clock
// re-tries it every window, silently, forever.
//
// D1 HAS NO TRIGGERS in this schema and no model layer, so create() and
// update() are the boundary every writer crosses. Same reason the auth-collection
// validation and fillEmpties live here.
//
// THE ONE PLACE THIS IS NARROWER THAN THE HOOK, said plainly: PocketBase reads
// the MERGED record, so it re-clears the key on any save of an already-terminal
// row. This reads the STATUS IN THE WRITE. That is enough to hold the invariant
// — a row can only become terminal on a write that names the terminal status,
// and from that moment its key is empty — and it costs no extra read on the
// hottest write path in the product. What it does not do is re-clear a key that
// something PATCHes back onto a row that is already terminal; nothing in the
// tree does that (`grep -rn commitment_key` finds one writer, at mint time),
// and if something ever does, the row it makes is exactly what the live-release
// SELECT in the F15 report looks for.
const TERMINAL_STATUSES = ["done", "failed", "cancelled"];

export function releasesCommitment(def: CollectionDef, body: Record<string, unknown>): boolean {
  if (def.name !== "jobs") return false;
  return TERMINAL_STATUSES.includes(String(body.status ?? ""));
}

export interface RecordsRequest {
  collection: CollectionDef;
  recordId: string | null;
  method: string;
  url: URL;
  body: Record<string, unknown> | null;
  principal: Principal;
  /**
   * Set by the policy chain. The compiled filter is AND-ed with
   * `owner_ref = ?` before it ever reaches D1, so a filter that slips past the
   * predicate check still cannot read another owner's rows.
   * ARCHITECTURE.md §3.5.
   */
  forcedScope?: { column: string; value: string } | null;
  /** Extra clauses the policy chain injected (research_lane's lane exclusion). */
  extraAst?: Node | null;
}

export function resolveCollection(name: string): CollectionDef | null {
  return COLLECTIONS[name] ?? null;
}

// ---------------------------------------------------------------------------
// COLLECTION ACCESS RULES — PocketBase's listRule/viewRule, which the guard is
// NOT a substitute for.
//
// Read off production 2026-09-04 with a superuser session:
//
//     owners   listRule = "id = @request.auth.id"   viewRule = same
//     every other exposed collection      ""        (public; the guard is the
//                                                    only gate, by design)
//
// `owners` is the one collection carrying a rule, and it is the one holding
// email and phone. Without it the Worker answered a SERVICE TOKEN with all 31
// owner records including both fields, while production answered the identical
// request with totalItems 0 — the rule matched nothing, because a service token
// is not an auth record. The guard let it through on BOTH; only the rule
// stopped it on one.
//
// That is why this lives here and not in the guard: the guard decides whether a
// request may RUN, the rule decides which ROWS it may see, and a port that
// implements one and not the other looks correct on every status code.
//
// The service token still reads owners the way brain/ actually does, through
// GET /worker/owners, which projects exactly {id, legacy_uuid} and nothing else.
// ---------------------------------------------------------------------------

type RowRule =
  | { kind: "all" }
  | { kind: "none" }
  | { kind: "own"; column: string; value: string };

function rowRule(def: CollectionDef, principal: Principal): RowRule {
  if (def.name !== "owners") return { kind: "all" };
  // PocketBase evaluates rules for everyone EXCEPT a superuser, who bypasses.
  if (principal.kind === "superuser") return { kind: "all" };
  if (principal.kind === "account") {
    return { kind: "own", column: "id", value: principal.ownerId };
  }
  // service, agent, anonymous: @request.auth.id is empty, so `id = ""` matches
  // nothing. Production returns an empty PAGE rather than a 403, and so does
  // this — the difference is visible to callers and worth preserving.
  return { kind: "none" };
}

// ---------------------------------------------------------------------------
// LIST
// ---------------------------------------------------------------------------

export async function list(env: Env, req: RecordsRequest): Promise<Response> {
  const def = req.collection;
  const q = req.url.searchParams;

  for (const p of UNSUPPORTED) {
    if (q.has(p)) {
      return badRequest(
        `the ${p} parameter is not implemented`,
        { [p]: { code: "unsupported_parameter",
                 message: `No client in this product uses ${p}. If one now does, ` +
                          `implement it here rather than letting it be ignored.` } });
    }
  }

  const page = Math.max(1, Number(q.get("page") ?? 1) || 1);
  const perPageRaw = Number(q.get("perPage") ?? DEFAULT_PER_PAGE) || DEFAULT_PER_PAGE;
  const perPage = Math.min(MAX_PER_PAGE, Math.max(1, perPageRaw));

  let where = "";
  let params: unknown[] = [];
  try {
    const built = buildWhere(def, q.get("filter") ?? "", req);
    where = built.sql;
    params = built.params;
  } catch (e) {
    if (e instanceof FilterError) {
      return badRequest("invalid filter", {
        filter: { code: "invalid_filter", message: e.message, offset: e.offset },
      });
    }
    throw e;
  }

  let order = "";
  try {
    order = parseSort(q.get("sort") ?? "", def).sql;
  } catch (e) {
    return badRequest("invalid sort", {
      sort: { code: "invalid_sort", message: (e as Error).message },
    });
  }

  // The collection's own listRule, applied on top of whatever the guard scoped.
  const rule = rowRule(def, req.principal);
  if (rule.kind === "none") {
    return json(200, { page, perPage, totalItems: 0, totalPages: 0, items: [] });
  }
  if (rule.kind === "own") {
    where = where ? `(${where}) AND ${quoteIdent(rule.column)} = ?${params.length + 1}`
                  : `${quoteIdent(rule.column)} = ?${params.length + 1}`;
    params = [...params, rule.value];
  }

  const table = quoteIdent(def.name);
  const clause = where ? ` WHERE ${where}` : "";

  // Two statements, one batch. D1's batch is a single round trip; two awaited
  // .all() calls are two, and this is the hottest path in the product (the
  // extension polls it every 30s per install — extension/background.js:1721-1729).
  const [countRes, pageRes] = await env.DB.batch([
    env.DB.prepare(`SELECT COUNT(*) AS n FROM ${table}${clause}`).bind(...params),
    env.DB.prepare(
      `SELECT * FROM ${table}${clause}${order} LIMIT ?${params.length + 1} OFFSET ?${params.length + 2}`,
    ).bind(...params, perPage, (page - 1) * perPage),
  ]);

  const totalItems = Number((countRes.results?.[0] as { n?: number })?.n ?? 0);
  const fields = q.get("fields");
  const items = (pageRes.results ?? []).map((r) =>
    projectFields(rowToRecord(def.name, r as Record<string, unknown>, def.boolColumns), fields));

  const body: ListResponse = {
    page, perPage, totalItems,
    totalPages: perPage > 0 ? Math.ceil(totalItems / perPage) : 0,
    items,
  };
  return json(200, body);
}

// ---------------------------------------------------------------------------
// VIEW
// ---------------------------------------------------------------------------

export async function view(env: Env, req: RecordsRequest): Promise<Response> {
  const def = req.collection;
  // viewRule is the same expression as listRule on owners, so the same gate.
  const vrule = rowRule(def, req.principal);
  if (vrule.kind === "none") return notFound();
  if (vrule.kind === "own" && String(req.recordId) !== vrule.value) return notFound();

  const row = await fetchOne(env, def, req.recordId as string, req.forcedScope ?? null);
  if (!row) return notFound();
  return json(200, rowToRecord(def.name, row, def.boolColumns));
}

// ---------------------------------------------------------------------------
// CREATE
// ---------------------------------------------------------------------------

/**
 * PocketBase's field validation for an AUTH collection, which the generic
 * record writer has no idea about.
 *
 * Without this the Worker accepted `POST /api/collections/owners/records` with
 * an EMPTY BODY and wrote a row with a null email and no password at all —
 * unauthenticated, from anywhere. 24 such rows accumulated in D1 during one
 * afternoon of testing while production refused every equivalent request with
 * `validation_required`. An account that has no password can never be signed
 * into and can never be deleted by its owner; it is landfill with a row id.
 *
 * It was also broken in the other direction: `passwordConfirm` is not a COLUMN,
 * so the generic writer rejected it as `unknown_field` — meaning the iPhone's
 * real signup call (AnticipyBackend.swift:444, which sends email + password +
 * passwordConfirm + legacy_uuid) could not create an account on the Worker AT
 * ALL. New-user signup was simply dead.
 *
 * Every message below was read off production, not invented:
 *
 *   {} .................. password, passwordConfirm  validation_required
 *                                                    "Cannot be blank."
 *   no email ............ email                      validation_required
 *   password "abc" ...... password  validation_min_text_constraint
 *                                   "Must be at least 8 character(s)."
 *   confirm mismatch .... passwordConfirm  validation_values_mismatch
 *                                          "Values don't match."
 *   envelope ............ {"data":…,"message":"Failed to create record.","status":400}
 *
 * The iPhone reads `data.email`, `data.phone` and `data.legacy_uuid` to tell a
 * taken address from a taken number from a taken device
 * (AnticipyBackend.swift:459-462), so uniqueness has to report under those
 * exact field names or the app shows the wrong message.
 */
const MIN_PASSWORD = 8;

function failedToCreate(data: Record<string, unknown>): Response {
  return json(400, { data, message: "Failed to create record.", status: 400 });
}

const REQUIRED = { code: "validation_required", message: "Cannot be blank." };
const NOT_UNIQUE = { code: "validation_not_unique", message: "Value must be unique." };

async function createOwner(env: Env, req: RecordsRequest): Promise<Response> {
  const def = req.collection;
  const body = req.body ?? {};
  const str = (k: string) => String(body[k] ?? "").trim();

  const email = str("email").toLowerCase();
  const password = String(body.password ?? "");
  const confirm = String(body.passwordConfirm ?? "");

  // VALIDATION ORDER IS PART OF THE CONTRACT, and it is not the obvious one.
  // Production on a blank body reports ONLY password and passwordConfirm — no
  // email error at all — and reports the email error only once the password
  // fields are filled in. Measured on both, side by side:
  //
  //   {}                                  -> password, passwordConfirm
  //   {password, passwordConfirm}         -> email
  //
  // Collecting all three at once looked tidier and was wrong: the iPhone shows
  // one message at a time, so the field it names first is the field the person
  // is told to fix, and a signup that says "email required" while the real
  // first problem is the password sends them to the wrong box.
  const pwErrs: Record<string, unknown> = {};
  if (!password) pwErrs.password = REQUIRED;
  if (!confirm) pwErrs.passwordConfirm = REQUIRED;
  if (Object.keys(pwErrs).length) return failedToCreate(pwErrs);
  if (!email) return failedToCreate({ email: REQUIRED });

  if (password.length < MIN_PASSWORD) {
    return failedToCreate({ password: {
      code: "validation_min_text_constraint",
      message: `Must be at least ${MIN_PASSWORD} character(s).`,
    } });
  }
  if (password !== confirm) {
    return failedToCreate({ passwordConfirm: {
      code: "validation_values_mismatch", message: "Values don't match.",
    } });
  }

  // Uniqueness, under the field names the iPhone branches on.
  const phone = str("phone");
  const legacy = str("legacy_uuid");
  const dupes: Record<string, unknown> = {};
  const taken = async (col: string, val: string) => {
    if (!val) return false;
    const row = await env.DB.prepare(
      `SELECT id FROM "owners" WHERE lower(${quoteIdent(col)}) = ?1 LIMIT 1`,
    ).bind(val.toLowerCase()).first();
    return !!row;
  };
  if (await taken("email", email)) dupes.email = NOT_UNIQUE;
  if (phone && await taken("phone", phone)) dupes.phone = NOT_UNIQUE;
  if (legacy && await taken("legacy_uuid", legacy)) dupes.legacy_uuid = NOT_UNIQUE;
  if (Object.keys(dupes).length) return failedToCreate(dupes);

  // $2a$ at cost 10 — Go's bcrypt.DefaultCost, so a digest written here is one
  // PocketBase would also accept if traffic ever moves back. src/pb/auth.ts.
  const digest = await bcrypt.hash(password, 10);
  const tokenKey = newRecordId() + newRecordId();   // 30 chars, per-record salt

  const id = typeof body.id === "string" && body.id ? body.id : newRecordId();
  const now = pbNow();
  await env.DB.prepare(
    `INSERT INTO "owners" (id, created, updated, email, emailVisibility, verified,
       password, tokenKey, phone, legacy_uuid)
     VALUES (?1,?2,?3,?4,0,0,?5,?6,?7,?8)`,
  ).bind(id, now, now, email, digest, tokenKey, phone, legacy).run();

  const row = await fetchOne(env, def, id, null);
  // rowToRecord already drops password and tokenKey (pb/wire.ts) — the same
  // projection PocketBase applies. Asserted by the contract suite.
  return json(200, rowToRecord(def.name, row ?? {}, def.boolColumns));
}

export async function create(env: Env, req: RecordsRequest): Promise<Response> {
  const def = req.collection;
  const live = await liveColumns(env, def.name);
  const body = fillEmpties(def, req.body ?? {}, live);

  // job_commitment_identity.pb.js, the create half. A row BORN terminal never
  // holds the key: workflow_guard refuses that entry for workflow rows
  // (ENTRY_STATUSES), but a legacy row with no workflow_id skips that file
  // entirely, so the hook's create leg is not redundant. Guarded on the live
  // column set for the same reason fillEmpties is: the map can be ahead of the
  // table, and writing a column the table lacks is a 1101 on every create.
  if (releasesCommitment(def, body) && live.has("commitment_key")) {
    body.commitment_key = "";
  }

  // owners is an AUTH collection and does not go through the generic writer.
  if (def.name === "owners") return createOwner(env, req);

  const cols: string[] = [];
  const vals: unknown[] = [];

  const id = typeof body.id === "string" && body.id ? body.id : newRecordId();
  cols.push("id"); vals.push(id);

  const now = pbNow();
  if (def.createdColumn) { cols.push(def.createdColumn); vals.push(now); }
  if (def.updatedColumn) { cols.push(def.updatedColumn); vals.push(now); }

  for (const [k, v] of Object.entries(body)) {
    if (k === "id" || k === def.createdColumn || k === def.updatedColumn) continue;
    const spec = def.columns[k];
    // An unknown field is a 400. PocketBase ignores it; ignoring it here means
    // a client that renamed a column writes a row missing that value and
    // finds out weeks later. Say no at the door.
    if (!spec) {
      return badRequest("failed to create record", {
        [k]: { code: "unknown_field", message: `${def.name} has no field ${k}` },
      });
    }
    cols.push(k);
    vals.push(toColumn(spec.type, v));
  }

  const placeholders = vals.map((_, i) => `?${i + 1}`).join(", ");
  try {
    await env.DB.prepare(
      `INSERT INTO ${quoteIdent(def.name)} (${cols.map(quoteIdent).join(", ")}) ` +
      `VALUES (${placeholders})`,
    ).bind(...vals).run();
  } catch (e) {
    const msg = (e as Error)?.message ?? String(e);
    const missing = missingColumn(msg);
    if (missing) {
      return badRequest("failed to create record", {
        [missing]: { code: "unknown_field", message: `${def.name} has no column ${missing} on this database` },
      });
    }
    const column = uniqueViolationColumn(msg);
    if (!column) throw e;
    return json(400, {
      data: { [column]: NOT_UNIQUE },
      message: "Failed to create record.",
      status: 400,
    });
  }

  const row = await fetchOne(env, def, id, null);
  return json(200, rowToRecord(def.name, row ?? {}, def.boolColumns));
}

// ---------------------------------------------------------------------------
// UPDATE
// ---------------------------------------------------------------------------

export async function update(env: Env, req: RecordsRequest): Promise<Response> {
  const def = req.collection;
  let body = req.body ?? {};
  const id = req.recordId as string;

  // job_commitment_identity.pb.js, the update half — AND THE ONE THAT MATTERS,
  // because a job reaches `done`/`failed`/`cancelled` by being PATCHed there.
  // The key must join `sets` even though the client never sent it: the caller
  // marking work finished has no idea this column exists, and PocketBase's
  // model hook was what emptied it. Skipped when the live table has no such
  // column, so a database behind the map answers as it did before rather than
  // failing the write that finishes an errand.
  if (releasesCommitment(def, body)) {
    const live = await liveColumns(env, def.name);
    if (live.has("commitment_key")) body = { ...body, commitment_key: "" };
  }

  const sets: string[] = [];
  const vals: unknown[] = [];

  for (const [k, v] of Object.entries(body)) {
    if (k === "id") continue;
    const spec = def.columns[k];
    if (!spec) {
      return badRequest("failed to update record", {
        [k]: { code: "unknown_field", message: `${def.name} has no field ${k}` },
      });
    }
    sets.push(`${quoteIdent(k)} = ?${vals.length + 1}`);
    vals.push(toColumn(spec.type, v));
  }
  if (def.updatedColumn) {
    sets.push(`${quoteIdent(def.updatedColumn)} = ?${vals.length + 1}`);
    vals.push(pbNow());
  }
  if (!sets.length) return notFound();

  // The scope is part of the WHERE, not a pre-check. A pre-check plus an
  // unscoped write is a TOCTOU: two requests interleave and the second writes
  // a row the first proved was owned. Make the database do the proving.
  let where = `${quoteIdent("id")} = ?${vals.length + 1}`;
  vals.push(id);
  if (req.forcedScope) {
    where += ` AND ${quoteIdent(req.forcedScope.column)} = ?${vals.length + 1}`;
    vals.push(req.forcedScope.value);
  }

  let res;
  try {
    res = await env.DB.prepare(
      `UPDATE ${quoteIdent(def.name)} SET ${sets.join(", ")} WHERE ${where}`,
    ).bind(...vals).run();
  } catch (e) {
    // The map knows a column the live table lacks: a 400 that names it, the
    // shape an unknown field already gets above — not a 1101. See
    // missingColumn for the day this was a ten-minute duplicate-job loop.
    const missing = missingColumn((e as Error)?.message ?? String(e));
    if (!missing) throw e;
    return badRequest("failed to update record", {
      [missing]: { code: "unknown_field", message: `${def.name} has no column ${missing} on this database` },
    });
  }

  if (!res.meta.changes) return notFound();

  const row = await fetchOne(env, def, id, null);
  return json(200, rowToRecord(def.name, row ?? {}, def.boolColumns));
}

// ---------------------------------------------------------------------------
// DELETE
// ---------------------------------------------------------------------------

export async function remove(env: Env, req: RecordsRequest): Promise<Response> {
  const def = req.collection;
  const vals: unknown[] = [req.recordId as string];
  let where = `${quoteIdent("id")} = ?1`;
  if (req.forcedScope) {
    where += ` AND ${quoteIdent(req.forcedScope.column)} = ?2`;
    vals.push(req.forcedScope.value);
  }
  const res = await env.DB.prepare(
    `DELETE FROM ${quoteIdent(def.name)} WHERE ${where}`,
  ).bind(...vals).run();
  if (!res.meta.changes) return notFound();
  return new Response(null, { status: 204 });
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

function quoteIdent(name: string): string {
  return '"' + name.replace(/"/g, '""') + '"';
}

/**
 * Compose the client filter, the policy chain's injected clauses, and the
 * forced owner scope into ONE parameterised WHERE.
 *
 * Order matters for readability of the emitted SQL only; all three are ANDs.
 */
function buildWhere(
  def: CollectionDef, raw: string, req: RecordsRequest,
): { sql: string; params: unknown[] } {
  const parts: string[] = [];
  const params: unknown[] = [];

  const nextIndex = () => params.length + 1;

  if (raw) {
    const c = filterToSQL(raw, {
      schema: def.columns,
      ctx: {
        auth: req.principal.kind === "account"
          ? { id: req.principal.ownerId, collectionName: "owners" }
          : null,
        body: req.body ?? {},
        method: req.method,
      },
      startIndex: nextIndex(),
    });
    parts.push(c.sql);
    params.push(...c.params);
  }

  if (req.extraAst) {
    const c = compileFilter(req.extraAst, { schema: def.columns, startIndex: nextIndex() });
    parts.push(c.sql);
    params.push(...c.params);
  }

  if (req.forcedScope) {
    parts.push(`${quoteIdent(req.forcedScope.column)} = ?${nextIndex()}`);
    params.push(req.forcedScope.value);
  }

  return { sql: parts.join(" AND "), params };
}

async function fetchOne(
  env: Env, def: CollectionDef, id: string,
  scope: { column: string; value: string } | null,
): Promise<Record<string, unknown> | null> {
  const vals: unknown[] = [id];
  let where = `${quoteIdent("id")} = ?1`;
  if (scope) { where += ` AND ${quoteIdent(scope.column)} = ?2`; vals.push(scope.value); }
  const row = await env.DB.prepare(
    `SELECT * FROM ${quoteIdent(def.name)} WHERE ${where} LIMIT 1`,
  ).bind(...vals).first();
  return (row as Record<string, unknown> | null) ?? null;
}

/**
 * Wire value -> D1 column value.
 *
 * `bool -> 0/1` is the one that bites. Everything else is pass-through
 * because migration/d1/schema.sql keeps JSON payloads as TEXT holding a JSON
 * string (params, trace, receipt, approval, …) rather than as a PB json field
 * — so a client that PATCHes `{"params": "{...}"}` sends a string and it is
 * stored as one, unchanged.
 */
function toColumn(type: string, v: unknown): unknown {
  if (v === null || v === undefined) return type === "number" ? 0 : "";
  if (type === "bool") return v === true || v === 1 || v === "true" ? 1 : 0;
  if (type === "number") return typeof v === "number" ? v : Number(v) || 0;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
