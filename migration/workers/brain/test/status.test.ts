import assert from "node:assert/strict";
import { fleetStatus, type FleetObservation } from "../src/fleet_status.ts";
import { adminBrainStatus } from "../../src/routes/admin_brain_status.ts";
import { requireRuntimeSource } from "../src/runtime_refresh.ts";

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

const expected = "a".repeat(64);
const values = new Map<string, unknown>();
const state = { async get<T>(key: string) { return values.get(key) as T | undefined; },
                async put(key: string, value: unknown) { values.set(key, value); } };
let stopped = 0;
const stop = async () => { stopped++; };
await requireRuntimeSource(expected, expected, state, async () => null, stop, 200_000);
assert.equal(stopped, 0, "a current image awaiting its first snapshot must not restart");
await assert.rejects(requireRuntimeSource(expected, undefined, state, async () => null, stop, 200_000));
await assert.rejects(requireRuntimeSource(expected, undefined, state,
  async () => ({ uploaded: new Date(0), size: 4096 }), stop, 200_000));
assert.equal(stopped, 0, "missing/stale durable state cannot trigger a restart");
await assert.rejects(requireRuntimeSource(expected, undefined, state,
  async () => ({ uploaded: new Date(190_000), size: 4096 }), stop, 200_000));
await assert.rejects(requireRuntimeSource(expected, undefined, state,
  async () => ({ uploaded: new Date(190_000), size: 4096 }), stop, 200_000));
assert.equal(stopped, 1, "only one SIGTERM may be sent while an old image flushes");
await requireRuntimeSource(expected, expected, state, async () => null, stop, 201_000);
console.log("runtime refresh: current, missing/stale snapshot, graceful stop and signal coalescing passed");
