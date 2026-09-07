import assert from "node:assert/strict";
import { fleetStatus, type FleetObservation } from "../src/fleet_status.ts";
import { adminBrainStatus } from "../../src/routes/admin_brain_status.ts";

const good: FleetObservation = { checked_at: 1000, served: 1, unserved: [], failed: [], workers: [], cleanup_failed: 0 };
assert.equal(fleetStatus(undefined, 1000).ok, false);
assert.equal(fleetStatus(good, 2000).ok, true);
assert.equal(fleetStatus(good, 182000).ok, false);
assert.equal(fleetStatus({ ...good, failed: ["owner-failed"] }, 2000).ok, false);
assert.equal(fleetStatus({ ...good, unserved: ["owner-at-cap"] }, 2000).ok, false);
let calls = 0;
const env = { ANTICIPY_INTERNAL_KEY: "private-test-key", BRAIN: {
  async fetch(request: Request) {
    calls++;
    assert.equal(request.method, "GET");
    assert.equal(request.url, "https://brain/health");
    assert.equal(request.headers.get("X-Internal-Key"), null);
    return Response.json({ ok: false }, { status: 503 });
  },
} as unknown as Fetcher };
const req = (key: string, method = "GET") => new Request("https://api/admin/brain/status", {
  method, headers: { "X-Internal-Key": key },
});
assert.equal((await adminBrainStatus(req(""), env)).status, 401);
assert.equal((await adminBrainStatus(req("wrong"), env)).status, 401);
assert.equal((await adminBrainStatus(req("private-test-key", "POST"), env)).status, 405);
assert.equal(calls, 0);
assert.equal((await adminBrainStatus(req("private-test-key"), env)).status, 503);
assert.equal(calls, 1);
console.log("fleet status: stale, failed, missing, capacity and authenticated transport checks passed");
