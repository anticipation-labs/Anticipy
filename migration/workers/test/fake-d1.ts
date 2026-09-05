/**
 * test/fake-d1.ts — a D1Database-shaped binding over node:sqlite.
 *
 * The routes in src/routes/ are transactional SQL against migration/d1/
 * schema.sql, so the honest unit of test is the handler WITH its SQL, not a
 * pure half behind an interface. This fake sits at the one boundary the
 * Worker cannot control — the `DB` binding — and everything above it is the
 * real code: the real handler, the real statements, the real schema (loaded
 * verbatim from migration/d1/schema.sql, partial-unique indexes included), a
 * real HMAC-signed account token from src/pb/auth.ts.
 *
 * What it reproduces of D1, and no more:
 *   prepare(sql).bind(...).first([column]) / .all() / .run() / .raw()
 *   batch([...])      ONE transaction: BEGIN, every statement, COMMIT — and
 *                     ROLLBACK if any throws. That is D1's documented batch
 *                     semantics, and it is what the routes rely on for "the
 *                     transaction rolled back" to mean something.
 *   errors            thrown with the "D1_ERROR: " prefix D1 uses, so the
 *                     column-naming readers in src/pb/records.ts see the same
 *                     text they see in production.
 *
 * `failOn` is how a test says "the database could not answer": a predicate
 * over the SQL text; the matching statement throws instead of running. That
 * is the polarity switch every route here has to get right — an unknown read
 * is never an empty one.
 *
 * Runs under `node --experimental-strip-types` on Node >= 22.13 (node:sqlite
 * unflagged); the repo runs Node 24.
 */
import { DatabaseSync, type StatementSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
/** migration/d1/schema.sql — the same file wrangler applies to the real D1. */
export const SCHEMA_SQL = join(here, "..", "..", "d1", "schema.sql");

export interface FakeD1Meta {
  changes: number;
  last_row_id: number;
  rows_read: number;
  rows_written: number;
  duration: number;
}
export interface FakeD1Result<T = Record<string, unknown>> {
  results: T[];
  success: true;
  meta: FakeD1Meta;
}

type Bindable = string | number | bigint | null | Uint8Array;

export class FakeD1 {
  readonly db: DatabaseSync;
  /** Statements whose SQL satisfies this throw D1_ERROR instead of running. */
  failOn: ((sql: string) => boolean) | null = null;
  /** Every SQL text this binding was asked to run, in order. */
  readonly log: string[] = [];

  constructor(opts: { schema?: boolean } = {}) {
    this.db = new DatabaseSync(":memory:");
    if (opts.schema !== false) this.db.exec(readFileSync(SCHEMA_SQL, "utf8"));
  }

  prepare(sql: string): FakeStatement { return new FakeStatement(this, sql, []); }

  /** D1's batch: one transaction, all or nothing. */
  async batch<T = Record<string, unknown>>(statements: FakeStatement[]): Promise<FakeD1Result<T>[]> {
    this.db.exec("BEGIN");
    try {
      const out: FakeD1Result<T>[] = [];
      for (const s of statements) out.push(await s.all<T>());
      this.db.exec("COMMIT");
      return out;
    } catch (err) {
      this.db.exec("ROLLBACK");
      throw err;
    }
  }

  async exec(sql: string): Promise<{ count: number; duration: number }> {
    this.db.exec(sql);
    return { count: 0, duration: 0 };
  }

  /** A test's own read of the table, outside the binding (never logged, never failed). */
  rows<T = Record<string, unknown>>(sql: string, ...params: Bindable[]): T[] {
    return this.db.prepare(sql).all(...params) as T[];
  }

  /** Mark a statement's SQL as "refused" once it matches `pattern` for the nth time (1-based). */
  failNth(pattern: RegExp, nth: number): void {
    let seen = 0;
    this.failOn = (sql) => pattern.test(sql) && ++seen === nth;
  }
}

function d1Error(err: unknown): Error {
  const msg = (err as Error)?.message ?? String(err);
  return new Error(msg.startsWith("D1_ERROR") ? msg : "D1_ERROR: " + msg);
}

export class FakeStatement {
  // No parameter properties: tsconfig.json is erasable-syntax-only so that
  // `node --experimental-strip-types` can run these sources with no build.
  readonly d1: FakeD1;
  readonly sql: string;
  readonly params: unknown[];

  constructor(d1: FakeD1, sql: string, params: unknown[]) {
    this.d1 = d1; this.sql = sql; this.params = params;
  }

  bind(...values: unknown[]): FakeStatement { return new FakeStatement(this.d1, this.sql, values); }

  private compiled(): StatementSync {
    this.d1.log.push(this.sql);
    if (this.d1.failOn && this.d1.failOn(this.sql)) {
      throw new Error("D1_ERROR: the fake database refused: " + this.sql.replace(/\s+/g, " ").trim().slice(0, 72));
    }
    try { return this.d1.db.prepare(this.sql); } catch (err) { throw d1Error(err); }
  }

  private args(): Bindable[] { return this.params as Bindable[]; }

  private isSelect(): boolean { return /^\s*(?:--[^\n]*\n\s*)*SELECT\b/i.test(this.sql); }

  async first<T = Record<string, unknown>>(column?: string): Promise<T | null> {
    const st = this.compiled();
    let row: Record<string, unknown> | undefined;
    try { row = st.get(...this.args()) as Record<string, unknown> | undefined; } catch (err) { throw d1Error(err); }
    if (!row) return null;
    return (column === undefined ? row : row[column]) as T;
  }

  async all<T = Record<string, unknown>>(): Promise<FakeD1Result<T>> {
    const st = this.compiled();
    let results: T[];
    try { results = st.all(...this.args()) as T[]; } catch (err) { throw d1Error(err); }
    const changes = this.isSelect()
      ? 0
      : Number((this.d1.db.prepare("SELECT changes() AS c").get() as { c: number }).c);
    return {
      results, success: true,
      meta: { changes, last_row_id: 0, rows_read: results.length, rows_written: changes, duration: 0 },
    };
  }

  async run<T = Record<string, unknown>>(): Promise<FakeD1Result<T>> { return this.all<T>(); }

  async raw<T = unknown[]>(): Promise<T[]> {
    const st = this.compiled();
    try { return (st.all(...this.args()) as Record<string, unknown>[]).map((r) => Object.values(r) as unknown as T); }
    catch (err) { throw d1Error(err); }
  }
}

/** The binding as the Worker's types see it. */
export function asD1(db: FakeD1): D1Database { return db as unknown as D1Database; }
