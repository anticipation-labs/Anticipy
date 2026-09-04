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
 *   fields=      0 call sites   brain/, proof/ — see ARCHITECTURE.md §2.3)
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

const UNSUPPORTED = ["expand", "fields", "skipTotal"] as const;

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
  const items = (pageRes.results ?? []).map((r) =>
    rowToRecord(def.name, r as Record<string, unknown>, def.boolColumns));

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
  const body = req.body ?? {};

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
  await env.DB.prepare(
    `INSERT INTO ${quoteIdent(def.name)} (${cols.map(quoteIdent).join(", ")}) ` +
    `VALUES (${placeholders})`,
  ).bind(...vals).run();

  const row = await fetchOne(env, def, id, null);
  return json(200, rowToRecord(def.name, row ?? {}, def.boolColumns));
}

// ---------------------------------------------------------------------------
// UPDATE
// ---------------------------------------------------------------------------

export async function update(env: Env, req: RecordsRequest): Promise<Response> {
  const def = req.collection;
  const body = req.body ?? {};
  const id = req.recordId as string;

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

  const res = await env.DB.prepare(
    `UPDATE ${quoteIdent(def.name)} SET ${sets.join(", ")} WHERE ${where}`,
  ).bind(...vals).run();

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
