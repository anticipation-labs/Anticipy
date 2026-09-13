// "CHROME READY" MUST BE TRUE FOR AS LONG AS CHROME IS ACTUALLY BEATING.
//
// The phone decides readiness from one fact — agents.last_seen — and its
// window used to be `secs < 30` against a beat whose period is Chrome's own
// 30-second alarm floor: zero margin, so every cycle had a tail (upload
// latency, the phone's read, alarm jitter, clock skew) in which the row read
// "Chrome asleep" with Chrome open and beating, and during a running errand
// the beat itself waited behind every lease renewal (up to 20 s each) before
// stamping. Measured 2026-09-12: one 15 s renewal stretched the stamp gap from
// 30 s to 45 s. The brain meanwhile called the same row fresh for 90 s.
//
// Three contracts, read from the shipped sources so they cannot drift apart:
//   (a) the phone's window equals the brain's, and both clear the beat period
//       plus one full request deadline;
//   (b) with an active job whose renewal is slow, the last_seen stamp still
//       lands one beat period apart — the beat precedes the renewals;
//   (c) the renewals still happen after the stamp (nothing was dropped).
//
// Run: node extension/tests/test_heartbeat_window_contract.mjs
import { readFileSync } from "node:fs";
import { fakeClock, installRig, flush, until } from "./rig_lifecycle.mjs";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : "\n     " + detail}`);
  if (!ok) failures++;
};

const clock = fakeClock();
const SLOW_RENEWAL_MS = 15_000;
const held = [];
const rig = installRig({ clock, jobsPatchDelayMs: SLOW_RENEWAL_MS,
  onModel: () => new Promise((resolve) => held.push(resolve)) });
await import("../background.js");
await flush(80);

const alarm = rig.harness.alarms.get("anticipy-heartbeat");
check("the heartbeat alarm exists", !!alarm);
const periodMs = Number(alarm.periodInMinutes) * 60_000;

// (a) The windows, from the sources.
const swift = readFileSync(new URL("../../app/ios/Anticipy/Backend/AnticipyBackend.swift", import.meta.url), "utf8");
const phoneWindow = Number(swift.match(/static let onlineWindowSeconds = (\d+)/)?.[1]);
const phoneBeat = Number(swift.match(/static let heartbeatSeconds = (\d+)/)?.[1]);
const brain = readFileSync(new URL("../../brain/hands.py", import.meta.url), "utf8");
const brainWindow = Number(brain.match(/AGENT_FRESH_SECONDS = (\d+)/)?.[1]);
const transport = readFileSync(new URL("../backend_transport.js", import.meta.url), "utf8");
const requestDeadlineMs = Number(transport.match(/BACKEND_REQUEST_TIMEOUT_MS = (\d+)/)?.[1]);
check("the phone and the brain read one row with ONE window", phoneWindow === brainWindow, `phone ${phoneWindow}, brain ${brainWindow}`);
check("the phone's copy of the beat period is the extension's", phoneBeat * 1000 === periodMs, `phone ${phoneBeat}s, extension ${periodMs / 1000}s`);
check("the window clears one beat plus one full request deadline",
      phoneWindow * 1000 > periodMs + requestDeadlineMs, `${phoneWindow * 1000} <= ${periodMs} + ${requestDeadlineMs}`);

// (b) A running job with a slow renewal must not delay the stamp. Chrome's
//     alarms fire on a FIXED schedule, so each beat is placed at T0 + n*period
//     and the question is how late the stamp lands after its alarm: zero when
//     the beat goes first, one renewal (15 s here, up to a 20 s deadline in
//     production) when the stamp waits behind the renewal loop.
rig.seedJob("job1", { task: "check the happy hour times" });
rig.harness.fireAlarm("anticipy-poll");
await until(() => held.length === 1, { what: "the run to reach its first step" });
const T0 = clock.now;
const lateness = [];
const orders = [];
for (let i = 1; i <= 3; i++) {
  const fired = T0 + i * periodMs;
  clock.set(fired);
  const since = rig.log.length;
  rig.harness.fireAlarm("anticipy-heartbeat");
  await flush(80);
  const beat = rig.log.slice(since).find((e) => e.method === "PATCH" && e.path.includes("/agents/records/"));
  const renewal = rig.log.slice(since).find((e) => e.method === "PATCH" && e.path.endsWith("/jobs/records/job1") && e.body.lease_until);
  lateness.push(Date.parse(beat?.body?.last_seen) - fired);
  orders.push({ beat: beat?.seq, renewal: renewal?.seq });
}
check("with a 15 s renewal in flight the stamp still lands the instant the alarm fires",
      lateness.every((l) => l === 0), `stamp lateness per beat: ${lateness.map((l) => l / 1000 + "s").join(", ")}; behind the renewal it would be ${SLOW_RENEWAL_MS / 1000}s`);
check("the beat precedes the renewal in every cycle",
      orders.every((o) => Number.isInteger(o.beat) && Number.isInteger(o.renewal) && o.beat < o.renewal), JSON.stringify(orders));
// (c) Nothing was dropped: every cycle still renewed the live lease.
check("the renewals still happen after the stamp", orders.every((o) => Number.isInteger(o.renewal)));
// The age the phone can read just before the next stamp is the period plus
// whatever lateness the beat carries; it must stay inside the window.
check("the worst stamp-to-read age stays under the phone's window",
      periodMs + Math.max(...lateness) + requestDeadlineMs < phoneWindow * 1000);

held[0](JSON.stringify({ action: "done", result: "Happy hour runs 3-6pm daily." }));
await flush(200);
console.log(`\nheartbeat window contract: ${failures ? failures + " FAILED" : "all passed"}`);
process.exit(failures ? 1 : 0);
