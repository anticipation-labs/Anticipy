// A RUN INSIDE ITS OWN BUDGET IS NOT ABANDONED BY ITS OWN WORKER, and when a
// run IS handed back and re-claimed by the same worker, the live attempt keeps
// its lease.
//
// Measured 2026-09-12 with the real modules under this rig: background.js
// kept a 12-minute poll ceiling while agent_loop.js declared a 16.27-minute
// worst case (and said background.js imported it). At 12:00 the beat dropped
// the run's lease, the sweep handed the row back once lease_until lapsed, and
// the SAME worker re-claimed it as attempt 2 while attempt 1 was still inside
// a step. Attempt 1's hand-back was refused 409 (wrong lease) and its teardown
// deleted activeJobs by JOB ID — attempt 2's entry — so nothing renewed the
// live attempt (0 renewals) while the popup said "another window picked it up".
//
// Run: node extension/tests/test_same_worker_reclaim_keeps_live_lease.mjs
import { fakeClock, installRig, flush, until } from "./rig_lifecycle.mjs";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : "\n     " + detail}`);
  if (!ok) failures++;
};
const MIN = 60_000;
const clock = fakeClock();
const T0 = clock.now;

// Step calls: hold the FIRST step of each loop until the suite releases it.
const held = [];
const rig = installRig({ clock, onModel: (call) => new Promise((resolve) => held.push({ resolve, call })) });
await import("../background.js");
await flush(80);
const { RUN_WALL_CEILING_MS } = await import("../agent_loop.js");

rig.seedJob("job1", { task: "check the happy hour times" });
rig.harness.fireAlarm("anticipy-poll");
await until(() => held.length === 1, { what: "attempt 1 to reach its first model step" });
const L1 = rig.row("job1").lease_token;
check("attempt 1 claimed the row with a lease", rig.row("job1").status === "running" && Number(rig.row("job1").attempts) === 1 && !!L1);

const renewalsFor = (lease, since = 0) => rig.log.slice(since).filter((e) => e.method === "PATCH"
  && e.path.endsWith("/jobs/records/job1") && e.headers["X-Anticipy-Lease"] === lease && e.body.lease_until).length;

// 1. Thirteen minutes in — inside the loop's declared worst case — the beat
//    still renews the lease. The old ceiling dropped it here.
clock.set(T0 + 13 * MIN);
const before13 = rig.log.length;
rig.harness.fireAlarm("anticipy-heartbeat");
await flush(60);
check("13 min in, inside the loop's own ceiling: the lease is still renewed, not dropped",
      renewalsFor(L1, before13) >= 1 && held.length === 1,
      `renewals ${renewalsFor(L1, before13)}, loops started ${held.length}`);

// 2. Past the loop's own worst case the beat may call the run abandoned. The
//    sweep hands the row back once lease_until lapses and the same worker
//    re-claims it as attempt 2 while attempt 1 is still mid-step.
clock.set(T0 + RUN_WALL_CEILING_MS + 0.5 * MIN);
rig.harness.fireAlarm("anticipy-heartbeat");
await flush(60);
clock.set(T0 + RUN_WALL_CEILING_MS + 3 * MIN);   // lease_until (last renewal + 2 min) has lapsed
rig.harness.fireAlarm("anticipy-poll");
await until(() => held.length === 2, { what: "attempt 2 to be claimed by the same worker", tries: 200 });
const L2 = rig.row("job1").lease_token;
check("past the ceiling the row was handed back and re-claimed as attempt 2 with a new lease",
      L2 && L2 !== L1 && Number(rig.row("job1").attempts) === 2);

// 3. Attempt 1's step returns; it is over budget, its hand-back is refused for
//    the wrong lease, and its teardown must NOT take attempt 2's entry with it.
held[0].resolve(JSON.stringify({ action: "scroll", dy: 400 }));
await until(() => rig.log.some((e) => e.status === 409 && e.headers["X-Anticipy-Lease"] === L1),
  { what: "attempt 1's write to be refused for the wrong lease" });
await flush(300);
const before = rig.log.length;
clock.set(T0 + RUN_WALL_CEILING_MS + 3.5 * MIN);
rig.harness.fireAlarm("anticipy-heartbeat");
await flush(80);
check("the next beat still renews the LIVE attempt 2 after attempt 1's teardown",
      renewalsFor(L2, before) >= 1 && held.length === 2,
      `renewals for attempt 2: ${renewalsFor(L2, before)} (the old teardown deleted its entry by job id)`);
check("the beat itself landed", rig.log.slice(before).some((e) => e.method === "PATCH" && e.path.includes("/agents/records/")));

held[1].resolve(JSON.stringify({ action: "done", result: "Happy hour runs 3-6pm daily." }));
await flush(300);
console.log(`\nsame-worker reclaim keeps the live lease: ${failures ? failures + " FAILED" : "all passed"}`);
process.exit(failures ? 1 : 0);
