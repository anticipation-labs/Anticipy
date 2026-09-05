// Who gets a brain: the allowlist serves outside the cap and the cap still only
// turns owners away. Run: node --experimental-strip-types migration/workers/brain/test/plan-fleet.test.ts
import assert from "node:assert/strict";
import { planFleet, parseCap } from "../src/plan.ts";

const o = (id: string) => ({ id, legacy_uuid: "" });
const real = [o("43dl3t9oz7q34qc"), o("4i2vafx1g01nlia"), o("7wiaachujzqe5e9"), o("sxkotd1h02qb6gw")];
let n = 0;
const check = (name: string, fn: () => void) => { fn(); n++; console.log(`PASS: ${name}`); };

check("cap 1, no allowlist: the first real owner and only it", () => {
  const r = planFleet(real, [], 1);
  assert.deepEqual(r.serve.map((x) => x.id), ["43dl3t9oz7q34qc"]);
  assert.deepEqual(r.unserved, ["4i2vafx1g01nlia", "7wiaachujzqe5e9", "sxkotd1h02qb6gw"]);
});
check("the probe owner is served outside the cap; the first real owner keeps its slot", () => {
  const r = planFleet(real, [o("qeuy6sv1raof9rw")], 1);
  assert.deepEqual(r.serve.map((x) => x.id), ["qeuy6sv1raof9rw", "43dl3t9oz7q34qc"]);
  assert.equal(r.unserved.length, 3);
});
check("an owner in both lists is served once and spends no cap", () => {
  const r = planFleet(real, [o("43dl3t9oz7q34qc")], 1);
  assert.deepEqual(r.serve.map((x) => x.id), ["43dl3t9oz7q34qc", "4i2vafx1g01nlia"]);
});
check("cap 0 with an allowlist serves the allowlist and turns everyone else away", () => {
  const r = planFleet(real, [o("qeuy6sv1raof9rw")], 0);
  assert.deepEqual(r.serve.map((x) => x.id), ["qeuy6sv1raof9rw"]);
  assert.equal(r.unserved.length, 4);
});
check("the cap never evicts: raising it only adds", () => {
  const a = planFleet(real, [], 1).serve.map((x) => x.id);
  const b = planFleet(real, [], 3).serve.map((x) => x.id);
  assert.deepEqual(b.slice(0, a.length), a);
});
check("cap 0 is zero, not 100 — the deploy that served four real owners by mistake", () => {
  assert.equal(parseCap("0"), 0); assert.equal(parseCap(0), 0);
});
check("absent, empty, junk or negative fall back to 100", () => {
  assert.equal(parseCap(undefined), 100); assert.equal(parseCap(""), 100); assert.equal(parseCap("lots"), 100); assert.equal(parseCap("-3"), 100);
});
check("a real number is itself", () => assert.equal(parseCap("2"), 2));
console.log(`plan-fleet: ${n} checks passed`);
