/** Consumes bodies emitted by the ACTUAL Swift transition implementation. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { workflowGuard } from "../src/policy/workflow_guard.ts";
import { researchLane } from "../src/policy/research_lane.ts";
import type { Ctx } from "../src/policy/chain.ts";

const fixture = JSON.parse(readFileSync(process.argv[2], "utf8"));
const url = new URL("https://api.anticipy.ai/api/collections/jobs/records/job-a");
async function check(row: Record<string, unknown>, body: Record<string, unknown>,
                     lease: string, kind = "account"): Promise<number> {
  const headers = lease ? { "X-Anticipy-Lease": lease } : {};
  const ctx = {
    request: new Request(url, { method: "PATCH", headers }), url, path: url.pathname,
    method: "PATCH", body, principal: { kind, id: "owner-a" },
    worker: { fromWorker: false }, storedRow: row,
    db: { prepare() { return { bind() { return { async first() { return row; } }; } }; } },
  } as unknown as Ctx;
  const lane = await researchLane(ctx, {});
  if (lane) return lane.status;
  const response = await workflowGuard(ctx, {});
  if (response) console.error(await response.clone().text());
  return response?.status ?? 200;
}
assert.equal(await check(fixture.queued, fixture.claim, ""), 200, "Swift claim refused");
assert.equal(await check(fixture.before_approval, fixture.queued, ""), 403, "Combined approval+release unexpectedly accepted");
assert.equal(await check(fixture.before_approval, fixture.recorded_approval, ""), 200, "Held approval record refused");
assert.equal(await check({ ...fixture.before_approval, ...fixture.recorded_approval }, fixture.queued, ""), 200, "Separate release refused");
assert.equal(await check(fixture.running, fixture.finish, "lease-a"), 200, "Swift verified receipt refused");
assert.equal(await check(fixture.running, fixture.uncertain, "lease-a"), 200, "Swift uncertain hold refused");
assert.equal(await check(fixture.queued, fixture.claim, "", "agent"), 403, "Browser claimed native job");
assert.notEqual(await check(fixture.running, fixture.finish, "wrong-lease"), 200, "Wrong lease completed");
const noApproval = { ...fixture.queued, approval: "" };
assert.notEqual(await check(noApproval, fixture.claim, ""), 200, "Approval loss was accepted");
console.log("Native calendar Swift-to-Worker: 9 checks passed");
