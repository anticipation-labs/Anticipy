import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import { notificationPolicy, notificationPolicyAt } from "../src/routes/notification_policy.ts";
import { QUIET_HOURS_START, QUIET_HOURS_END } from "../src/connections/nudge.ts";

const at = (stamp: string, zone = "America/Vancouver") => notificationPolicyAt(new Date(stamp), zone);
for (const [stamp, quiet] of [
  ["2026-09-07T04:59:59Z", false], // 21:59:59
  ["2026-09-07T05:00:00Z", true],  // 22:00
  ["2026-09-07T07:30:00Z", true],  // the reported midnight use
  ["2026-09-07T14:59:59Z", true],
  ["2026-09-07T15:00:00Z", false], // 08:00
  ["2026-11-01T08:30:00Z", true],  // daylight-saving fall-back
  ["2026-11-01T09:30:00Z", true],
  ["2026-03-08T14:59:59Z", true],  // daylight-saving spring-forward
  ["2026-03-08T15:00:00Z", false],
] as const) assert.equal(at(stamp).quietHoursActive, quiet, stamp);
assert.equal(at("2026-09-07T07:30:00Z", "Asia/Kolkata").quietHoursActive, false);
assert.equal(at("2026-09-07T14:59:59Z").expiresAt, Date.parse("2026-09-07T15:00:00Z") / 1000);
assert.throws(() => at("2026-09-07T07:30:00Z", "invalid/zone"));

// The API must describe the brain's actual schedule, not a second schedule.
const worker = readFileSync(new URL("../../../brain/worker.py", import.meta.url), "utf8");
assert.match(worker, new RegExp(`CLOCK_QUIET_START, CLOCK_QUIET_END = ${QUIET_HOURS_START}, ${QUIET_HOURS_END}\\b`));

const db = new FakeD1();
const env = { DB: asD1(db), ANTICIPY_AUTH_SECRET: "notification-policy-test" };
const stamp = "2026-09-07 07:00:00.000Z";
for (const [id, zone] of [["policyowner00001", "America/Vancouver"], ["policyowner00002", "Asia/Tokyo"]]) {
  db.db.prepare(`INSERT INTO owners (id, created, updated, email, emailVisibility, verified,
    password, tokenKey, phone, legacy_uuid) VALUES (?,?,?,?,0,0,'',?,'','')`)
    .run(id, stamp, stamp, id + "@example.invalid", id + "-key");
  db.db.prepare("INSERT INTO owner_profile (id, owner_id, owner_ref, timezone, created, updated) VALUES (?,?,?,?,?,?)")
    .run("profile" + id.slice(-8), id, id, zone, stamp, stamp);
}
const req = (token = "", method = "GET") => new Request("https://api.anticipy.ai/me/notification-policy?owner=policyowner00002", {
  method, headers: { Authorization: token },
});
assert.equal((await notificationPolicy(req(), env)).status, 401);
const token = await issueToken(env, "policyowner00001", "policyowner00001-key");
const response = await notificationPolicy(req(token), env);
assert.equal(response.status, 200);
assert.equal(response.headers.get("cache-control"), "no-store");
const body = await response.json() as ReturnType<typeof notificationPolicyAt>;
assert.equal(body.timeZone, "America/Vancouver", "query parameter cannot select another owner's zone");
assert.equal(body.startHour, 22);
assert.equal(body.endHour, 8);
assert.equal((await notificationPolicy(req(token, "POST"), env)).status, 405);
db.db.prepare("UPDATE owner_profile SET timezone = 'broken/zone' WHERE owner_ref = ?").run("policyowner00001");
assert.equal((await notificationPolicy(req(token), env)).status, 503);
db.db.prepare("DELETE FROM owners WHERE id = ?").run("policyowner00001");
assert.equal((await notificationPolicy(req(token), env)).status, 401);
console.log("notification policy: clock boundaries, DST, cache expiry, identity, and unknown state passed");
