/**
 * Runs with no dependencies:
 *
 *   node --experimental-strip-types migration/workers/test/filter-dsl.test.ts
 *
 * (Node 22.6+ / 23+. The source is erasable-syntax-only on purpose so that it
 * needs no build step to be tested, and so esbuild/wrangler can consume it
 * unchanged.)
 *
 * Every case below is either (a) a filter string that a real client in this
 * tree actually sends, with the file:line that sends it, or (b) an adversarial
 * input aimed at the authorization path.
 */
import assert from "node:assert/strict";
import {
  parseFilter, filterToSQL, provesOwnerScope, legacyOwnedList,
  mentionsField, andNot, compileFilter, FilterError,
  type CollectionSchema,
} from "../filter-dsl.ts";

// The `jobs` columns this suite touches, typed as migration/d1/schema.sql
// declares them (schema.sql:262-317).
const JOBS: CollectionSchema = {
  id: { type: "text" },
  created: { type: "date" },
  updated: { type: "date" },
  owner_ref: { type: "relation" },
  status: { type: "text" },
  goal: { type: "text" },
  lane: { type: "text" },
  workflow_id: { type: "text" },
  workflow_state: { type: "text" },
  watching_until: { type: "date" },
  claimed_by: { type: "text" },
  claimed_at: { type: "date" },
  attempts: { type: "number" },
  lineage_key: { type: "text" },
  params: { type: "text" },
};

const AGENTS: CollectionSchema = {
  id: { type: "text" },
  agent_id: { type: "text" },
  agent_token: { type: "text" },
  owner: { type: "text" },
  owner_ref: { type: "relation" },
  pair_code: { type: "text" },
  paired: { type: "bool" },
  browser: { type: "text" },
  last_seen: { type: "date" },
};

let passed = 0;
const failures: string[] = [];
function t(name: string, fn: () => void) {
  try { fn(); passed++; }
  catch (e) { failures.push(`${name}\n    ${(e as Error).message.split("\n")[0]}`); }
}

// ---------------------------------------------------------------------------
// 1. The filters real clients send
// ---------------------------------------------------------------------------

t("extension claim poll — extension/background.js:77-78", () => {
  const src = 'status="queued" && owner_ref="OWN123" && workflow_id!="" && lane!="research"';
  const { sql, params } = filterToSQL(src, { schema: JOBS });
  assert.equal(sql,
    '(((("status" = ?1) AND ("owner_ref" = ?2)) AND ("workflow_id" <> ?3)) '
    + 'AND ("lane" <> ?4))');
  assert.deepEqual(params, ["queued", "OWN123", "", "research"]);
});

t("extension supervised-read poll — extension/background.js:89-90", () => {
  const src = 'status="queued" && owner_ref="OWN123" && lane="supervised_read"';
  const { params } = filterToSQL(src, { schema: JOBS });
  assert.deepEqual(params, ["queued", "OWN123", "supervised_read"]);
});

t("brain _scoped_filter parenthesises its base — brain/worker.py:124-127", () => {
  const src = '(status="queued") && owner_ref="OWN123"';
  const { params } = filterToSQL(src, { schema: JOBS });
  assert.deepEqual(params, ["queued", "OWN123"]);
});

t("brain sends paired=true and D1 stores 0/1 — brain/worker.py:1302", () => {
  const { sql, params } = filterToSQL('paired=true && owner_ref="OWN123"', { schema: AGENTS });
  assert.deepEqual(params, [1, "OWN123"], "true must bind as INTEGER 1, not JS true");
  assert.ok(sql.includes('"paired" = ?1'));
});

t("pair-code lookup — guard.pb.js:493", () => {
  const { params } = filterToSQL('pair_code="123456"', { schema: AGENTS });
  assert.deepEqual(params, ["123456"]);
});

t("the one ~ in the tree — proof/day_zero_20.py:368", () => {
  const { sql, params } = filterToSQL('browser~"rig/abc"', { schema: AGENTS });
  assert.ok(sql.includes("LIKE"));
  assert.deepEqual(params, ["%rig/abc%"], "PocketBase wraps a %-free ~ value");
});

t("date range — brain sends created>= and updated<=", () => {
  const { params } = filterToSQL(
    'owner_ref="O" && created>="2026-01-01 00:00:00.000Z" && updated<="2026-02-01 00:00:00.000Z"',
    { schema: JOBS });
  assert.deepEqual(params, ["O", "2026-01-01 00:00:00.000Z", "2026-02-01 00:00:00.000Z"]);
});

t("numbers bind as numbers, not strings", () => {
  const { params } = filterToSQL("attempts>=3", { schema: JOBS });
  assert.deepEqual(params, [3]);
  assert.equal(typeof params[0], "number");
});

t("a filter naming no field at all still parses as owner scope", () => {
  const { params } = filterToSQL('owner_ref="O"', { schema: JOBS });
  assert.deepEqual(params, ["O"]);
});

// ---------------------------------------------------------------------------
// 2. Nothing is ever interpolated
// ---------------------------------------------------------------------------

t("a quote in a value cannot escape into SQL", () => {
  const { sql, params } = filterToSQL(`goal="a\\" OR 1=1 --"`, { schema: JOBS });
  assert.ok(!sql.includes("OR 1=1"), "the payload must live in params, never in sql");
  assert.deepEqual(params, ['a" OR 1=1 --']);
});

t("a semicolon in a value cannot escape into SQL", () => {
  const { sql, params } = filterToSQL(`goal="x'; DROP TABLE jobs; --"`, { schema: JOBS });
  assert.ok(!/DROP/i.test(sql));
  assert.deepEqual(params, ["x'; DROP TABLE jobs; --"]);
});

t("an unknown field is refused, never passed through", () => {
  assert.throws(() => filterToSQL('jobs) UNION SELECT 1 --="x"', { schema: JOBS }), FilterError);
  assert.throws(() => filterToSQL('secret_column="x"', { schema: JOBS }),
    (e: unknown) => e instanceof FilterError && /unknown field/.test(e.message));
});

t("every emitted placeholder has exactly one bound value", () => {
  const { sql, params } = filterToSQL(
    'owner_ref="O" && (status="queued" || status="running") && attempts<3', { schema: JOBS });
  const holes = (sql.match(/\?\d+/g) ?? []);
  assert.equal(holes.length, params.length);
  assert.deepEqual(holes, ["?1", "?2", "?3", "?4"]);
});

t("startIndex splices into a larger query without colliding", () => {
  const { sql, params } = filterToSQL('status="queued"', { schema: JOBS, startIndex: 5 });
  assert.ok(sql.includes("?5"));
  assert.equal(params.length, 1);
});

// ---------------------------------------------------------------------------
// 3. Precedence and grouping
// ---------------------------------------------------------------------------

t("&& binds tighter than ||", () => {
  const ast = parseFilter('a="1" || b="2" && c="3"');
  assert.equal(ast.kind, "or");
  assert.equal((ast as any).right.kind, "and");
});

t("parens override precedence", () => {
  const ast = parseFilter('(a="1" || b="2") && c="3"');
  assert.equal(ast.kind, "and");
  assert.equal((ast as any).left.kind, "or");
});

t("an unclosed paren is a 400, not a crash", () => {
  assert.throws(() => parseFilter('(a="1"'), FilterError);
});

t("a lone && is a 400", () => {
  assert.throws(() => parseFilter('a="1" &&'), FilterError);
});

t("a single & is named, not silently accepted", () => {
  assert.throws(() => parseFilter('a="1" & b="2"'),
    (e: unknown) => e instanceof FilterError && /did you mean/.test(e.message));
});

// ---------------------------------------------------------------------------
// 4. The != / NULL subtlety
//    backend/pb_migrations/1700000043_owner_profile_needs_owner.js:27-30
// ---------------------------------------------------------------------------

t("NOT NULL column: != emits bare <>, which an index can serve", () => {
  const { sql } = filterToSQL('workflow_id!=""', { schema: JOBS });
  assert.equal(sql, '("workflow_id" <> ?1)');
  assert.ok(!sql.includes("COALESCE"), "a NOT NULL column must not be wrapped");
});

t("nullable column: NULL is folded to '' in BOTH directions", () => {
  const NULLABLE: CollectionSchema = { note: { type: "text", nullable: true } };
  assert.equal(filterToSQL('note!=""', { schema: NULLABLE }).sql,
    `(COALESCE("note", '') <> ?1)`);
  assert.equal(filterToSQL('note=""', { schema: NULLABLE }).sql,
    `(COALESCE("note", '') = ?1)`);
});

t("an explicit null literal is IS / IS NOT, and is not COALESCEd away", () => {
  assert.equal(filterToSQL("goal=null", { schema: JOBS }).sql, '("goal" IS NULL)');
  assert.equal(filterToSQL("goal!=null", { schema: JOBS }).sql, '("goal" IS NOT NULL)');
});

// ---------------------------------------------------------------------------
// 5. @request macros
// ---------------------------------------------------------------------------

t("@request.auth.id binds the session id — owners listRule, 1700000008:50", () => {
  const OWNERS: CollectionSchema = { id: { type: "text" }, email: { type: "email" } };
  const { params } = filterToSQL("id = @request.auth.id",
    { schema: OWNERS, ctx: { auth: { id: "OWN123", collectionName: "owners" } } });
  assert.deepEqual(params, ["OWN123"]);
});

t("@request.auth.id with no session is NULL, so `id = @request.auth.id` matches nothing", () => {
  const OWNERS: CollectionSchema = { id: { type: "text" } };
  const { sql } = filterToSQL("id = @request.auth.id", { schema: OWNERS, ctx: { auth: null } });
  assert.equal(sql, '("id" IS NULL)', "anonymous must not match every row");
});

t("an absent @request.body field behaves as '' — measured at 1700000043:27-30", () => {
  // The createRule is `@request.body.owner_ref != ""`. Both an absent field
  // and an explicit "" must FAIL it.
  const S: CollectionSchema = { probe: { type: "text" } };
  const evaluate = (body: Record<string, unknown>) =>
    filterToSQL('@request.body.owner_ref != probe', { schema: S, ctx: { body } }).params[0];
  assert.equal(evaluate({}), "", "absent must resolve to '' so `!= \"\"` is false");
  assert.equal(evaluate({ owner_ref: "" }), "");
  assert.equal(evaluate({ owner_ref: "OWN123" }), "OWN123");
});

t("an unsupported macro is a 400, not a pass-through", () => {
  assert.throws(() => filterToSQL('id=@collection.other.id', { schema: JOBS }), FilterError);
});

// ---------------------------------------------------------------------------
// 6. THE AUTHORIZATION BYPASS — the reason this file exists
// ---------------------------------------------------------------------------

t("LIVE BUG: a string literal satisfies the substring rule while constraining nothing", () => {
  // guard.pb.js:45-50 authorises this list. It has no `||`, and it contains the
  // literal substring owner_ref="OWN123". What it actually asks the database
  // for is EVERY job row belonging to EVERY owner.
  const attack = `goal != 'owner_ref="OWN123"'`;
  assert.equal(legacyOwnedList(attack, "OWN123"), true,
    "the deployed guard accepts this — that is the finding");
  assert.equal(provesOwnerScope(parseFilter(attack), "OWN123"), false,
    "the AST check must refuse it");
});

t("a comment could hide the same substring — so comments are refused outright", () => {
  assert.throws(() => parseFilter(`id!="" // owner_ref="OWN123"`), FilterError);
});

t("the honest filters all pass the AST check", () => {
  for (const src of [
    'owner_ref="OWN123"',
    'status="queued" && owner_ref="OWN123" && workflow_id!="" && lane!="research"',
    '(status="queued") && owner_ref="OWN123"',
    'owner_ref="OWN123" && (status="queued" || status="running")',
  ]) {
    assert.equal(provesOwnerScope(parseFilter(src), "OWN123"), true, src);
  }
});

t("the AST check is a strict widening on the || case the substring rule refused", () => {
  const src = '(owner_ref="OWN123" && status="queued") || (owner_ref="OWN123" && status="running")';
  assert.equal(legacyOwnedList(src, "OWN123"), false, "legacy refuses any ||");
  assert.equal(provesOwnerScope(parseFilter(src), "OWN123"), true,
    "every disjunct names the owner, so it is sound");
});

t("a || that widens the owner set is refused by both", () => {
  const src = 'owner_ref="OWN123" || owner_ref="OTHER"';
  assert.equal(legacyOwnedList(src, "OWN123"), false);
  assert.equal(provesOwnerScope(parseFilter(src), "OWN123"), false);
});

t("owner_ref under an OR at the top of a conjunct proves nothing", () => {
  const src = 'status="queued" && (owner_ref="OWN123" || status="running")';
  assert.equal(provesOwnerScope(parseFilter(src), "OWN123"), false);
});

t("a different owner's id never proves this owner's scope", () => {
  assert.equal(provesOwnerScope(parseFilter('owner_ref="OTHER"'), "OWN123"), false);
});

t("an empty ownerRef can never be proved", () => {
  assert.equal(provesOwnerScope(parseFilter('owner_ref=""'), ""), false);
});

// ---------------------------------------------------------------------------
// 7. research_lane's rewrite, done structurally
//    backend/pb_hooks/research_lane.pb.js:437-443
// ---------------------------------------------------------------------------

t("mentionsField is exact where the regex was approximate", () => {
  assert.equal(mentionsField(parseFilter('lane="research"'), "lane"), true);
  assert.equal(mentionsField(parseFilter('goal="pick a lane"'), "lane"), false,
    "research_lane.pb.js:279 uses /\\blane\\b/ on the raw string and says true here");
});

t("the lane exclusion becomes an AND node, not a concatenated string", () => {
  const base = parseFilter('status="queued" && owner_ref="OWN123"');
  let ast = andNot(base, "lane", "research");
  ast = andNot(ast, "lane", "supervised_read");
  ast = andNot(ast, "lane", "device_calendar");
  const { sql, params } = compileFilter(ast, { schema: JOBS });
  assert.deepEqual(params,
    ["queued", "OWN123", "research", "supervised_read", "device_calendar"]);
  assert.ok(sql.includes('"lane" <> ?3'));
  // And the injected clause survives an adversarial base, which the text
  // rewrite `"(" + filter + ") && …"` also does — but only by luck of the
  // parens. On the AST it cannot be escaped at all.
  const hostile = andNot(parseFilter(`goal="\\") || (\\""`), "lane", "research");
  const out = compileFilter(hostile, { schema: JOBS });
  assert.ok(out.sql.includes('"lane" <> ?2'));
  assert.ok(!out.sql.includes("OR"), "no OR may appear from a value");
});

// ---------------------------------------------------------------------------
// 8. Operator coverage
// ---------------------------------------------------------------------------

t("all ten required operators compile", () => {
  const cases: Array<[string, string]> = [
    ['status="q"',   '("status" = ?1)'],
    ['status!="q"',  '("status" <> ?1)'],
    ["attempts>1",   '("attempts" > ?1)'],
    ["attempts>=1",  '("attempts" >= ?1)'],
    ["attempts<1",   '("attempts" < ?1)'],
    ["attempts<=1",  '("attempts" <= ?1)'],
    ['goal~"x"',     `("goal" LIKE ?1 ESCAPE '\\')`],
    ['goal!~"x"',    `("goal" NOT LIKE ?1 ESCAPE '\\')`],
    ['status?="q"',  '("status" = ?1)'],
    ['status?!="q"', '("status" <> ?1)'],
  ];
  for (const [src, want] of cases) {
    assert.equal(filterToSQL(src, { schema: JOBS }).sql, want, src);
  }
});

t("?= is only safe because no column in this schema is multi-valued", () => {
  const MULTI: CollectionSchema = { tags: { type: "text", multi: true } };
  assert.throws(() => filterToSQL('tags?="a"', { schema: MULTI }),
    (e: unknown) => e instanceof FilterError && /json_each/.test(e.message));
});

t("the field may be on either side", () => {
  assert.equal(filterToSQL('"q"=status', { schema: JOBS }).sql, '("status" = ?1)');
  assert.equal(filterToSQL("3>attempts", { schema: JOBS }).sql, '("attempts" < ?1)',
    "the operator must mirror when the sides swap");
});

t("literal OP literal is refused rather than given a truth value", () => {
  assert.throws(() => filterToSQL('"a"="a"', { schema: JOBS }), FilterError);
});

t("field OP field compiles without binding anything", () => {
  const { sql, params } = filterToSQL("created=updated", { schema: JOBS });
  assert.equal(sql, '("created" = "updated")');
  assert.deepEqual(params, []);
});

t("a % in a ~ value is treated as an author-written pattern", () => {
  assert.deepEqual(filterToSQL('goal~"a%b"', { schema: JOBS }).params, ["a%b"]);
  assert.deepEqual(filterToSQL('goal~"50_off"', { schema: JOBS }).params, ["%50\\_off%"],
    "an underscore in a plain value must be escaped, not left as a wildcard");
});

// ---------------------------------------------------------------------------

console.log(`\n${passed} passed, ${failures.length} failed`);
for (const f of failures) console.error("  FAIL " + f);
if (failures.length) process.exit(1);
