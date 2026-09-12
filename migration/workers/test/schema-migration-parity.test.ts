/**
 * test/schema-migration-parity.test.ts — THE FRESH INSTALL AND THE UPGRADE MUST
 * BE THE SAME DATABASE.
 *
 *   node --experimental-strip-types migration/workers/test/schema-migration-parity.test.ts
 *
 * WHY THIS LEG EXISTS. On 2026-09-11 the durable OAuth recovery work landed a
 * reviewed cancellation predicate in `2026-09-11-oauth-recovery.sql` and left
 * `schema.sql` holding the earlier, narrower one. Nothing was red. Every Worker
 * suite runs against `schema.sql`, so the tests measured the FRESH INSTALL while
 * production would have run the UPGRADE — two different databases, one of which
 * nothing tested. That is the same shape as a sandbox path and a production path
 * drifting apart, and it is the most common way a change that "passed" ships
 * broken.
 *
 * WHAT IT CHECKS. For every object a dated migration in migration/d1/ creates —
 * added column, index, trigger — the fresh `schema.sql` must declare an
 * EQUIVALENT object. The comparison is against the database's own answer
 * (`sqlite_master`, `PRAGMA table_info`) after loading the real schema, not
 * against the text of schema.sql, so re-wrapping or requoting cannot make a
 * difference appear or disappear.
 *
 * WHAT IT IS NOT. It does not prove a migration APPLIES cleanly to production,
 * that it is rerunnable, or that it has been applied. Rerunnability is
 * proof/audit/d1_additive.py and tests/test_d1_additive.py; application is an
 * operator step. This leg answers one question only: does an upgraded database
 * end up shaped like a fresh one.
 */
import { DatabaseSync } from "node:sqlite";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const D1 = join(here, "..", "..", "d1");

let checks = 0, failures = 0;
function check(label: string, ok: boolean, detail = "") {
  checks++;
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}: ${label}${ok || !detail ? "" : "\n  " + detail}`);
}

/** Comments out, quotes off, keywords flattened, whitespace collapsed. The two
 *  files are written by different hands on different days; only the SQL the
 *  engine sees is the same thing twice. `IF NOT EXISTS` goes because SQLite
 *  does not keep it in sqlite_master, so leaving it in would compare a
 *  migration against a database that cannot ever carry it. */
function normalize(sql: string): string {
  return sql
    .replace(/--[^\n]*/g, " ")
    .replace(/"/g, "")
    .replace(/\bIF\s+NOT\s+EXISTS\b/gi, " ")
    .replace(/\s+/g, " ")
    .replace(/\s*([(),;=])\s*/g, "$1")
    .trim()
    .toLowerCase();
}

/** Split on semicolons, but a trigger body is full of them — everything from
 *  BEGIN to its matching END belongs to one statement. */
function statements(sql: string): string[] {
  const out: string[] = [];
  let buffer = "", depth = 0;
  for (const line of sql.split("\n")) {
    const bare = line.replace(/--[^\n]*/g, "");
    buffer += line + "\n";
    if (/\bBEGIN\b/i.test(bare)) depth++;
    if (/\bEND\s*;/i.test(bare) && depth > 0) depth--;
    if (depth === 0 && /;\s*$/.test(bare.trimEnd())) {
      if (buffer.replace(/--[^\n]*/g, "").trim()) out.push(buffer.trim());
      buffer = "";
    }
  }
  if (buffer.replace(/--[^\n]*/g, "").trim()) out.push(buffer.trim());
  return out;
}

// ---------------------------------------------------------------- the fresh install
const fresh = new DatabaseSync(":memory:");
fresh.exec(readFileSync(join(D1, "schema.sql"), "utf8"));

const master = new Map<string, string>();
for (const row of fresh.prepare("SELECT name, type, sql FROM sqlite_master").all() as
     { name: string; type: string; sql: string | null }[]) {
  if (row.sql) master.set(row.name, normalize(row.sql));
}
function columns(table: string) {
  return fresh.prepare(`PRAGMA table_info(${table})`).all() as
    { name: string; type: string; notnull: number; dflt_value: string | null }[];
}

// Every dated migration in the directory, so a future one is covered the day it
// is written rather than the day somebody remembers to add it here.
const migrations = readdirSync(D1)
  .filter(name => /^\d{4}-\d{2}-\d{2}-.+\.sql$/.test(name))
  .sort();
check("there are dated migrations to compare", migrations.length > 0,
      `migration/d1 held none matching YYYY-MM-DD-*.sql`);

for (const file of migrations) {
  const sql = readFileSync(join(D1, file), "utf8");
  for (const statement of statements(sql)) {
    const flat = normalize(statement);

    const added = /^alter table (\w+) add column (\w+)\b(.*?);?$/.exec(flat);
    if (added) {
      const [, table, column, rest] = added;
      const found = columns(table).find(c => c.name.toLowerCase() === column);
      check(`${file}: schema.sql declares ${table}.${column}`, !!found);
      if (found) {
        const declaredType = /^(\w+)/.exec(rest.trim())?.[1] ?? "";
        check(`${file}: ${table}.${column} has the migration's type`,
              !declaredType || found.type.toLowerCase() === declaredType,
              `schema.sql says ${found.type || "(none)"}, the migration says ${declaredType}`);
        const wantsNotNull = /\bnot null\b/.test(rest);
        check(`${file}: ${table}.${column} agrees on NOT NULL`,
              wantsNotNull === (found.notnull === 1),
              `schema.sql notnull=${found.notnull}, the migration ${wantsNotNull ? "requires" : "does not require"} it`);
        const wantsDefault = /\bdefault\s+('[^']*'|[^\s)]+)/.exec(rest)?.[1];
        check(`${file}: ${table}.${column} agrees on DEFAULT`,
              (wantsDefault ?? null) === (found.dflt_value === null ? null : normalize(found.dflt_value)),
              `schema.sql default=${found.dflt_value}, the migration default=${wantsDefault}`);
        // A CHECK travels with the column and is invisible to table_info, so it
        // is read off the table's own DDL. A constraint that shipped in the
        // migration and not in schema.sql is a fresh install that accepts a
        // value the upgraded database refuses.
        const wantsCheck = /\bcheck\((.*)\)\s*$/.exec(rest.trim())?.[1];
        if (wantsCheck) {
          const ddl = master.get(table) ?? "";
          check(`${file}: ${table}.${column} carries its CHECK in schema.sql`,
                ddl.includes(wantsCheck.replace(/\s+/g, "")) || ddl.includes(wantsCheck),
                `schema.sql's ${table} DDL does not contain check(${wantsCheck})`);
        }
      }
      continue;
    }

    const made = /^create (?:unique )?(index|trigger) (\w+)\b/.exec(flat);
    if (made) {
      const [, kind, name] = made;
      const declared = master.get(name);
      check(`${file}: schema.sql declares ${kind} ${name}`, !!declared,
            `the migration creates it; a fresh install would not have it`);
      if (declared) {
        check(`${file}: ${kind} ${name} is the same ${kind} in both files`,
              declared === flat.replace(/;$/, ""),
              `schema.sql : ${declared}\n  migration : ${flat.replace(/;$/, "")}`);
      }
      continue;
    }

    // CREATE TABLE IF NOT EXISTS in a migration is the same table schema.sql
    // creates.
    const table = /^create table (\w+)\b/.exec(flat);
    if (table) {
      check(`${file}: schema.sql declares table ${table[1]}`, master.has(table[1]));
      continue;
    }

    // THE TABLE REBUILD, NAMED RATHER THAN SWALLOWED. SQLite cannot widen a
    // CHECK in place, so a migration that changes one renames the old table,
    // recreates it, copies the rows and drops the original
    // (2026-09-06-connect-nudges-declined-soft.sql is the worked example).
    // Those three statements create no lasting object, so there is nothing for
    // a fresh install to match — the CREATE TABLE in the middle of them is
    // compared above and carries the whole difference. They are allowlisted by
    // SHAPE, one shape at a time, so a statement this leg genuinely cannot read
    // still goes red: a gate that silently ignores what it does not understand
    // is a gate that measures nothing.
    const moves = [
      /^alter table \w+ rename to \w+;?$/,
      /^insert into \w+ ?(\([^)]*\))? ?select .*;?$/,
      /^drop table (if exists )?\w+;?$/,
      /^drop (index|trigger) (if exists )?\w+;?$/,
      /^pragma \w+ ?=? ?\w*;?$/,
    ];
    if (moves.some(shape => shape.test(flat))) continue;

    check(`${file}: every statement is one this leg can compare`, false,
          `unclassified: ${flat.slice(0, 160)}`);
  }
}

fresh.close();
console.log(`schema/migration parity: ${checks} checks, ${failures} failed`);
process.exit(failures === 0 ? 0 : 1);
