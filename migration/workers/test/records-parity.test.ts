// records.ts parity with PocketBase on the two shapes the brain and the gates
// send since 2026-09-05: `fields=` projection and a unique-index collision on
// create. Run: node --experimental-strip-types test/records-parity.test.ts
import assert from "node:assert/strict";
import { projectFields, uniqueViolationColumn, missingColumn, fillEmpties } from "../src/pb/records.ts";

let n = 0;
const check = (name: string, fn: () => void) => { fn(); n++; console.log(`PASS: ${name}`); };

const rec = { id: "abc", created: "2026-09-05 00:00:00.000Z", text: "what he said", device_id: "iphone-b122", source: "phone_mic" };

check("no fields param returns the whole record", () => assert.deepEqual(projectFields(rec, null), rec));
check("empty fields returns the whole record", () => assert.deepEqual(projectFields(rec, "  "), rec));
check("* returns the whole record", () => assert.deepEqual(projectFields(rec, "*"), rec));
check("fields=id keeps speech off the wire", () => assert.deepEqual(projectFields(rec, "id"), { id: "abc" }));
check("a comma list projects in the record's own shape", () =>
  assert.deepEqual(projectFields(rec, "created, device_id,source"), { created: rec.created, device_id: "iphone-b122", source: "phone_mic" }));
check("a name the record lacks is ignored, as PocketBase ignores it", () =>
  assert.deepEqual(projectFields(rec, "id,nope"), { id: "abc" }));
check("the projection never invents a column", () => assert.equal("text" in projectFields(rec, "id,created"), false));

check("a D1 UNIQUE message names the column", () =>
  assert.equal(uniqueViolationColumn("D1_ERROR: UNIQUE constraint failed: events.external_event_id: SQLITE_CONSTRAINT"), "external_event_id"));
check("any other error is not a collision", () => assert.equal(uniqueViolationColumn("D1_ERROR: no such table: nope"), null));
check("an empty message is not a collision", () => assert.equal(uniqueViolationColumn(""), null));

check("a D1 'no such column' names the column the map is ahead on", () =>
  assert.equal(missingColumn("D1_ERROR: no such column: heard_ms: SQLITE_ERROR"), "heard_ms"));
check("...with a table prefix too", () =>
  assert.equal(missingColumn("D1_ERROR: no such column: events.heard_calls"), "heard_calls"));
check("any other D1 error is not a missing column", () =>
  assert.equal(missingColumn("D1_ERROR: UNIQUE constraint failed: events.external_event_id"), null));

const eventsDef = { name: "events", createdColumn: "created", updatedColumn: "updated", boolColumns: ["backfill"],
  columns: { id: { type: "text" }, created: { type: "date" }, updated: { type: "date" }, kind: { type: "text" },
             text: { type: "text" }, decision: { type: "text" }, goal: { type: "text" }, seq: { type: "number" },
             backfill: { type: "bool" }, owner_ref: { type: "relation" } } } as any;
check("a line posted the way the phone posts it gets decision \"\" — the brain's filter can see it", () => {
  const row = fillEmpties(eventsDef, { kind: "transcript", text: "hi", owner_ref: "o1" });
  assert.equal(row.decision, ""); assert.equal(row.goal, ""); assert.equal(row.seq, 0); assert.equal(row.backfill, false);
});
check("a value the client sent is never overwritten by the empty", () =>
  assert.equal(fillEmpties(eventsDef, { decision: "act" }).decision, "act"));
check("a column the map knows but the live table lacks is never filled — that was a 1101 on every create", () => {
  const row = fillEmpties(eventsDef, { kind: "transcript" }, new Set(["kind", "text", "decision"]));
  assert.equal(row.decision, ""); assert.equal("goal" in row, false); assert.equal("seq" in row, false);
});
check("SQLite's INSERT wording names the missing column too", () =>
  assert.equal(missingColumn("D1_ERROR: table events has no column named heard_ms: SQLITE_ERROR"), "heard_ms"));
check("id, created and updated are the writer's, not filled here", () => {
  const row = fillEmpties(eventsDef, {}); assert.equal("id" in row, false); assert.equal("created" in row, false);
});

console.log(`records-parity: ${n} checks passed`);
