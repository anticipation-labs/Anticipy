/**
 * test/sqlite-d1.ts — a D1Database over node:sqlite, loaded with the REAL
 * migration/d1/schema.sql. Not a test; a fixture the tests share.
 *
 * WHY NOT A HAND-WRITTEN FAKE. The defects these tests pin live in SQL and in
 * the schema, not in TypeScript: a partial unique index that refuses a second
 * live commitment_key (schema.sql:300-301), a `NOT IN (SELECT … ORDER BY …
 * LIMIT n)` retention sweep, a CHECK that refuses an unowned evidence row. A
 * fake that records statements as strings proves the code called something; it
 * cannot tell you the index fired. SQLite is the same engine underneath D1, so
 * these read as the database's own answers.
 *
 * WHAT IT IS NOT: D1's network semantics, its 1101, its batch atomicity or its
 * per-statement limits. The wire half stays migration/spec/contract_tests.py
 * against a real workerd (scripts/*_contract_local.sh).
 *
 * Placeholders: the sources use both `?1, ?2` (records.ts, cron.ts) and bare
 * `?` (password_reset.ts). SQLite binds both by position, so `.bind(...)`
 * forwards its arguments in order for either spelling.
 */
import { DatabaseSync } from "node:sqlite";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
export const SCHEMA_SQL = join(here, "..", "..", "d1", "schema.sql");

type Row = Record<string, unknown>;

/** SQLite hands back only null/number/bigint/string/Uint8Array; D1 does too. */
function bindable(v: unknown): unknown {
  if (v === undefined || v === null) return null;
  if (typeof v === "boolean") return v ? 1 : 0;
  if (typeof v === "number" || typeof v === "string" || typeof v === "bigint") return v;
  if (v instanceof Uint8Array) return v;
  return String(v);
}

export interface TestDb {
  db: D1Database;
  /** Straight to SQLite, for seeding and for reading a row back the way a
   *  live D1 SELECT would — never through the code under test. */
  exec(sql: string): void;
  query<T = Row>(sql: string, ...args: unknown[]): T[];
  close(): void;
}

export function openTestD1(): TestDb {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(readFileSync(SCHEMA_SQL, "utf8"));

  const prepare = (sql: string) => {
    let bound: unknown[] = [];
    const stmt = {
      bind(...args: unknown[]) { bound = args.map(bindable); return stmt; },
      async first<T = Row>(): Promise<T | null> {
        const row = sqlite.prepare(sql).get(...(bound as never[]));
        return (row as T | undefined) ?? null;
      },
      async all<T = Row>(): Promise<{ results: T[]; meta: { changes: number } }> {
        const rows = sqlite.prepare(sql).all(...(bound as never[])) as T[];
        return { results: rows, meta: { changes: rows.length } };
      },
      async run(): Promise<{ meta: { changes: number } }> {
        const r = sqlite.prepare(sql).run(...(bound as never[]));
        return { meta: { changes: Number(r.changes) } };
      },
    };
    return stmt;
  };

  const db = {
    prepare,
    async batch(statements: { run(): Promise<unknown> }[]) {
      // D1's batch is atomic; SQLite's transaction is the same guarantee, and
      // the retention sweep's correctness depends on it (a half-applied prune
      // deletes rows whose R2 objects were never removed).
      sqlite.exec("BEGIN");
      try {
        const out = [];
        for (const s of statements) out.push(await s.run());
        sqlite.exec("COMMIT");
        return out;
      } catch (err) { sqlite.exec("ROLLBACK"); throw err; }
    },
  } as unknown as D1Database;

  return {
    db,
    exec: (sql) => sqlite.exec(sql),
    query: <T = Row>(sql: string, ...args: unknown[]) =>
      sqlite.prepare(sql).all(...(args.map(bindable) as never[])) as T[],
    close: () => sqlite.close(),
  };
}

// ---------------------------------------------------------------------------
// A fake R2 bucket. Only what src/assets.ts and src/cron.ts use.
// ---------------------------------------------------------------------------

export interface FakeR2 {
  bucket: R2Bucket;
  objects: Map<string, { bytes: Uint8Array; contentType: string }>;
  deleted: string[];
  /** Set to make every put throw, the way a bucket with wrong credentials does. */
  failPuts: boolean;
}

export function fakeR2(): FakeR2 {
  const state: FakeR2 = {
    objects: new Map(), deleted: [], failPuts: false,
    bucket: null as unknown as R2Bucket,
  };
  state.bucket = {
    async put(key: string, value: ArrayBuffer | Uint8Array, opts?: { httpMetadata?: { contentType?: string } }) {
      if (state.failPuts) throw new Error("R2 refused the put");
      const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
      state.objects.set(key, { bytes, contentType: opts?.httpMetadata?.contentType ?? "" });
      return { key };
    },
    async get(key: string) {
      const found = state.objects.get(key);
      if (!found) return null;
      return {
        body: new Blob([found.bytes as BlobPart]).stream(),
        httpEtag: `"${key.length}-${found.bytes.length}"`,
        writeHttpMetadata(headers: Headers) {
          if (found.contentType) headers.set("content-type", found.contentType);
        },
      };
    },
    async delete(keys: string | string[]) {
      for (const k of Array.isArray(keys) ? keys : [keys]) {
        state.deleted.push(k);
        state.objects.delete(k);
      }
    },
  } as unknown as R2Bucket;
  return state;
}
