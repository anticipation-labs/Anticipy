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
  const row = await fetchOne(env, def, req.recordId as string, req.forcedScope ?? null);
  if (!row) return notFound();
  return json(200, rowToRecord(def.name, row, def.boolColumns));
}

// ---------------------------------------------------------------------------
// CREATE
// ---------------------------------------------------------------------------

export async function create(env: Env, req: RecordsRequest): Promise<Response> {
  const def = req.collection;
  const body = req.body ?? {};

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
