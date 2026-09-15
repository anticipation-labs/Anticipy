// Real service-worker handlers + queue execution against the existing local
// Worker/filter rig. Each case gets a fresh module/storage lifetime. No API,
// provider, paid model, installed browser, or user account is touched.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { installRig, flush, until } from "./rig_lifecycle.mjs";

const cases = ["registration", "heartbeat", "key", "key-failure", "job-profile",
  "double-newcode", "storage-refusal", "unpaired-queue", "rejected-registration",
  "old-completion", "old-handback", "unowned-handback", "owned-history",
  "control-owner", "control-race", "owned-retry", "paired-without-owner", "same-owner-mirror",
  "notification-settlement", "notification-clear-refusal", "auth-explicit", "guard-403-hiccup",
  "refusal-streak", "transient-503", "transient-network", "phone-repair", "phone-release",
  "phone-release-legacy", "legacy-handback-hidden", "closed-tab-unpaired", "scope-reads-queue"];
const selected = process.argv[2];
if (!selected) {
  let failures = 0;
  for (const name of cases) {
    const child = spawnSync(process.execPath, [fileURLToPath(import.meta.url), name],
      { encoding: "utf8", timeout: 20_000 });
    if (child.status !== 0) {
      failures++;
      console.error(`FAIL pairing lifecycle ${name}\n${child.stdout || ""}${child.stderr || ""}`);
    } else console.log(`PASS pairing lifecycle ${name}`);
  }
  process.exit(failures ? 1 : 0);
}
assert.ok(cases.includes(selected), "only named offline cases may run");
const rig = installRig();
// A record written by 0.18.2 (no owner tag) has to exist BEFORE the worker boots.
let legacyTab = null;
if (selected === "legacy-handback-hidden") {
  legacyTab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  rig.harness.storageData.handBacks = { [legacyTab.id]: { url: legacyTab.url, detail: "legacy detail", kind: "needs_user", at: 1 } };
}
const background = await import("../background.js");
await flush(80);
const originalFetch = globalThis.fetch;
const old = structuredClone(rig.harness.storageData);
let release, started = false;
const deferred = new Promise(resolve => { release = resolve; });
const reset = () => rig.sendMessage({ type: "anticipy-newcode" });
const setup = () => rig.sendMessage({ type: "anticipy-setup-state" });
const assertUnpaired = () => {
  const state = rig.harness.storageData;
  assert.equal(state.paired, false);
  assert.equal(state.ownerRef, "");
  assert.equal(state.ownerProfile, null);
  assert.equal(state.openrouterKey, "");
  assert.notEqual(state.agentId, old.agentId);
};

if (selected === "registration") {
  Object.assign(rig.harness.storageData, { recordId: "", agentToken: "" });
  let count = 0;
  globalThis.fetch = async (url, options) => {
    if (new URL(String(url)).pathname === "/agent/register") {
      count++;
      const response = await originalFetch(url, options);
      if (count === 1) { started = true; await deferred; }
      return response;
    }
    return originalFetch(url, options);
  };
  const first = setup();
  await until(() => started);
  const replacement = reset();
  await until(() => rig.harness.storageData.agentId !== old.agentId);
  release();
  assert.equal((await first).ok, false, "retired registration reply is not a setup receipt");
  assert.equal((await replacement).ok, true);
  assert.equal(count, 2);
  assertUnpaired();
  assert.equal(rig.harness.storageData.agentId, rig.agents.agent_id);
  assert.equal(rig.harness.storageData.recordId, rig.agents.id);
}
if (selected === "heartbeat") {
  globalThis.fetch = async (url, options) => {
    if (new URL(String(url)).pathname.includes("/agents/records/")) {
      const response = rig.reply({ paired: true, owner_ref: old.ownerRef, owner: old.owner });
      started = true; await deferred; return response;
    }
    return originalFetch(url, options);
  };
  rig.harness.fireAlarm("anticipy-heartbeat");
  await until(() => started);
  assert.equal((await reset()).ok, true);
  release(); await flush(80);
  assertUnpaired();
  assert.equal((await setup()).linked, false);
}
if (["key", "key-failure", "job-profile"].includes(selected)) {
  let keyCalls = 0;
  const target = selected === "job-profile" ? 2 : 1;
  globalThis.fetch = async (url, options) => {
    if (new URL(String(url)).pathname === "/agent/key" && ++keyCalls === target) {
      const response = selected === "key-failure" ? rig.reply({}, 503)
        : await originalFetch(url, options);
      started = true; await deferred; return response;
    }
    return originalFetch(url, options);
  };
  rig.seedJob("pairing-race", { task: "read the public opening hours" });
  rig.harness.fireAlarm("anticipy-poll");
  await until(() => started);
  assert.equal(rig.modelCalls.length, 0);
  assert.equal((await reset()).ok, true);
  release(); await flush(250);
  assertUnpaired();
  assert.equal(rig.modelCalls.length, 0, "retired owner work must not reach a model");
  assert.equal(rig.harness.tabs.size, 0, "retired owner work must not open a browser tab");
  assert.equal(rig.log.filter(entry => entry.path === "/agent/llm").length, 0,
    "even a server-refused old-owner model dispatch is forbidden");
}
if (selected === "double-newcode") {
  const results = await Promise.all([reset(), reset()]);
  assert.ok(results.some(result => result.ok));
  assertUnpaired();
  assert.equal(rig.harness.storageData.agentId, rig.agents.agent_id);
  assert.equal(rig.log.filter(entry => entry.path === "/agent/register").length, 1,
    "overlapping reset messages must publish only the winning generation");
  assert.equal((await setup()).linked, false);
}
if (selected === "storage-refusal") {
  const set = chrome.storage.local.set;
  chrome.storage.local.set = async () => { throw new Error("synthetic storage refusal"); };
  assert.equal((await reset()).ok, false);
  chrome.storage.local.set = set;
  assert.equal(rig.harness.storageData.agentId, old.agentId,
    "a refused atomic reset leaves the previous identity intact, not a half-new identity");
  assert.equal(rig.log.filter(entry => entry.path === "/agent/register").length, 0);
  assert.equal((await reset()).ok, true, "failed local storage must not strand the write chain");
  assertUnpaired();
}
if (selected === "unpaired-queue") {
  rig.seedJob("pairing-race", { task: "read the public opening hours" });
  assert.equal((await reset()).ok, true);
  const before = rig.log.length;
  rig.harness.fireAlarm("anticipy-poll");
  await flush(150);
  assert.equal(rig.row("pairing-race").status, "queued");
  assert.equal(rig.modelCalls.length, 0);
  assert.equal(rig.log.slice(before).filter(entry => entry.path.includes("/jobs/records")).length, 0,
    "a new credential is not permission to query or claim the prior owner's queue");
  assertUnpaired();
}
if (selected === "rejected-registration") {
  for (const body of [{}, { id: "record" }, { id: "record", agent_token: "token" }]) {
    globalThis.fetch = async (url, options) => new URL(String(url)).pathname === "/agent/register"
      ? rig.reply(body) : originalFetch(url, options);
    assert.equal((await reset()).ok, false);
    assert.equal((await setup()).ok, false);
    assert.equal(rig.harness.storageData.recordId, "");
    assertUnpaired();
  }
  globalThis.fetch = async () => rig.reply({}, 503);
  assert.equal((await reset()).ok, false);
  assert.equal((await setup()).linked, false);
  assertUnpaired();
}
if (selected === "old-completion") {
  let afterReset = false, retiredTabStarts = 0;
  const create = chrome.tabs.create;
  chrome.tabs.create = async values => { if (afterReset) retiredTabStarts++; return create(values); };
  globalThis.fetch = async (url, options) => {
    if (new URL(String(url)).pathname === "/agent/llm" && !started) {
      const response = await originalFetch(url, options);
      started = true; await deferred; return response;
    }
    return originalFetch(url, options);
  };
  rig.seedJob("pairing-race", { task: "read the public opening hours" });
  rig.harness.fireAlarm("anticipy-poll");
  await until(() => started);
  assert.equal((await reset()).ok, true);
  afterReset = true;
  const replacementJob = { id: "new-owner-job", ownerRef: "new-owner", status: "running", doing: "new task" };
  Object.assign(rig.harness.storageData, { ownerRef: "new-owner", paired: true, currentJob: replacementJob });
  release(); await flush(2500);
  assert.deepEqual(rig.harness.storageData.currentJob, replacementJob,
    "late completion from the old pairing must not overwrite the replacement owner's mirror");
  assert.equal(retiredTabStarts, 0, "a delayed planner reply must not open a tab after pairing changed");
}
if (selected === "old-handback") {
  const tab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  const get = chrome.tabs.get;
  chrome.tabs.get = async id => { started = true; await deferred; return get(id); };
  const pending = background.surfaceHandBack(tab.id, "old owner private detail", "needs_user");
  await until(() => started);
  assert.equal((await reset()).ok, true);
  release(); await pending;
  assert.equal(rig.harness.notifications.size, 0, "a retired owner callback must not notify");
  assert.equal(Object.keys(rig.harness.storageData.handBacks || {}).length, 0);
}
if (selected === "unowned-handback") {
  const tab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  rig.harness.storageData.handBacks = { [tab.id]: { url: tab.url, detail: "legacy detail" } };
  await background.openHandBack(tab.id);
  assert.equal(rig.harness.focusGrants.length, 0, "unknown legacy ownership is not permission to open a private page");
  assert.ok(rig.harness.storageData.handBacks[tab.id], "legacy evidence remains in storage");
}
if (selected === "owned-history") {
  const tab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  await background.surfaceHandBack(tab.id, "owner detail", "needs_user");
  assert.equal(rig.harness.storageData.handBacks[tab.id]?.ownerRef, old.ownerRef,
    "hand-back history needs a durable owner tag");
  rig.seedJob("pairing-race", { task: "read the public opening hours" });
  const claim = await background.claimJob();
  assert.ok(claim);
  assert.equal(rig.harness.storageData.currentJob?.ownerRef, claim.owner_ref,
    "task mirror must be tagged from the actual row's owner");
}
if (["control-owner", "control-race", "owned-retry"].includes(selected)) {
  rig.seedJob("pairing-race", { task: "read the public opening hours" });
  rig.harness.storageData.currentJob = { id: "pairing-race", ownerRef: old.ownerRef, status: "queued", doing: "fixture task" };
  if (selected === "owned-retry") {
    const row = rig.row("pairing-race");
    const params = JSON.parse(row.params);
    params._workflow.state = "needs_user";
    params._workflow.attempts = 3;
    rig.db.db.prepare("UPDATE jobs SET status='needs_user', workflow_state='needs_user', attempts=3, params=? WHERE id=?")
      .run(JSON.stringify(params), row.id);
    const answer = await rig.sendMessage({ type: "anticipy-again", id: row.id, ownerRef: old.ownerRef });
    assert.equal(answer.ok, true);
    assert.equal(rig.row(row.id).attempts, 0, "the bound owner's retry restores its attempt budget");
    assert.equal(rig.harness.storageData.currentJob.ownerRef, old.ownerRef);
  } else if (selected === "control-owner") {
    const before = rig.log.length;
    for (const ownerRef of [undefined, "another-owner"]) {
      const answer = await rig.sendMessage({ type: "anticipy-stop", id: "pairing-race", ownerRef });
      assert.equal(answer.ok, false);
    }
    assert.equal(rig.log.slice(before).filter(entry => entry.method === "PATCH").length, 0);
    const answer = await rig.sendMessage({ type: "anticipy-stop", id: "pairing-race", ownerRef: old.ownerRef });
    assert.equal(answer.ok, true);
    assert.equal(rig.row("pairing-race").status, "cancelled");
  } else {
    globalThis.fetch = async (url, options) => {
      if (new URL(String(url)).pathname.endsWith("/jobs/records/pairing-race") && !started) {
        const response = await originalFetch(url, options);
        started = true; await deferred; return response;
      }
      return originalFetch(url, options);
    };
    const action = rig.sendMessage({ type: "anticipy-stop", id: "pairing-race", ownerRef: old.ownerRef });
    await until(() => started);
    await reset(); release();
    assert.equal((await action).ok, false);
    assert.equal(rig.row("pairing-race").status, "queued", "stale control must not mutate the job");
  }
}
if (selected === "paired-without-owner") {
  rig.harness.storageData.ownerRef = "";
  rig.harness.storageData.paired = true;
  const state = await setup();
  assert.equal(state.ok, true);
  assert.equal(state.linked, false, "paired bit alone cannot prove a usable owner link");
  assert.equal(await background.claimJob(), null);
  assert.equal(rig.harness.storageData.currentJob, undefined,
    "a pairing problem must not invent ownerless history");
}
if (selected === "same-owner-mirror") {
  rig.seedJob("pairing-race", { task: "read the public opening hours" });
  rig.harness.storageData.currentJob = { id: "pairing-race", ownerRef: old.ownerRef, status: "running", doing: "old task" };
  globalThis.fetch = async (url, options) => {
    if (new URL(String(url)).pathname.endsWith("/jobs/records/pairing-race")) {
      const response = rig.reply({ ...rig.row("pairing-race"), status: "done", workflow_state: "succeeded", result: "old result" });
      started = true; await deferred; return response;
    }
    return originalFetch(url, options);
  };
  const reconciliation = background.reconcileCurrentJob();
  await until(() => started);
  const newest = { id: "new-job", ownerRef: old.ownerRef, status: "running", doing: "new task" };
  rig.harness.storageData.currentJob = newest;
  release(); await reconciliation;
  assert.deepEqual(rig.harness.storageData.currentJob, newest,
    "delayed old-job read must not overwrite a newer task even for the same owner");
}
if (selected === "notification-settlement") {
  const tab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  const create = chrome.notifications.create;
  let displayOwner;
  chrome.notifications.create = async (...args) => {
    started = true; await deferred;
    displayOwner = rig.harness.storageData.ownerRef;
    return create(...args);
  };
  const notification = background.surfaceHandBack(tab.id, "old owner detail", "needs_user");
  await until(() => started);
  let completed = false;
  const replacement = reset().then(result => { completed = true; return result; });
  await flush(80);
  const finishedBeforeNotification = completed;
  release();
  await Promise.all([notification, replacement]);
  assert.equal(finishedBeforeNotification, false,
    "identity retirement must wait for an already-submitted notification and clear it before succeeding");
  assert.equal(displayOwner, old.ownerRef,
    "private notification can never be first presented after identity storage has changed");
  assert.equal(rig.harness.notifications.size, 0);
}
if (selected === "notification-clear-refusal") {
  const tab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  await background.surfaceHandBack(tab.id, "old owner detail", "needs_user");
  const evidence = structuredClone(rig.harness.storageData.handBacks);
  const clear = chrome.notifications.clear;
  chrome.notifications.clear = async () => { throw new Error("synthetic notification API refusal"); };
  assert.equal((await reset()).ok, false, "uncleared private presentation cannot yield a new pairing code");
  assert.equal((await setup()).ok, false, "automatic retry must preserve the presentation fence");
  assert.equal(rig.harness.storageData.pairCode, "");
  assert.deepEqual(rig.harness.storageData.handBacks, evidence);
  chrome.notifications.clear = clear;
  assert.equal((await reset()).ok, true);
  assert.equal(rig.harness.notifications.size, 0);
}
if (["auth-explicit", "guard-403-hiccup", "refusal-streak", "transient-503", "transient-network"].includes(selected)) {
  // The liveness read mid-run. An EXPLICIT credential verdict ends the run; a
  // bare 403 is the guard failing closed on a D1 hiccup (guard.ts recordOwner
  // maps a throw to "" and refuses) and one of them is a blip, not revocation
  // — claimJob itself acts only on three explicit verdicts. A streak still
  // ends the run, bounded, so a dead credential cannot keep a tab alive.
  let checked = false, refusals = 0;
  globalThis.fetch = async (url, options) => {
    if (new URL(String(url)).pathname.endsWith("/jobs/records/pairing-race") && (!options?.method || options.method === "GET")) {
      checked = true;
      if (selected === "transient-network") throw new Error("synthetic connection outage");
      if (selected === "transient-503") return rig.reply({}, 503);
      if (selected === "auth-explicit") return rig.reply({ error: "agent credential is not recognized" }, 403);
      if (selected === "refusal-streak") return rig.reply({ error: "agent is not allowed to access that record" }, 403);
      if (selected === "guard-403-hiccup" && refusals++ === 0) return rig.reply({ error: "agent is not allowed to access that record" }, 403);
    }
    return originalFetch(url, options);
  };
  rig.seedJob("pairing-race", { task: "read the public opening hours" });
  rig.harness.fireAlarm("anticipy-poll");
  await until(() => checked);
  await flush(300);
  if (selected === "auth-explicit") {
    assert.equal(rig.modelCalls.length, 0, "an explicit refusal cannot be treated as a temporary outage");
    assert.equal(rig.harness.tabs.size, 0, "revoked work cannot open a task tab");
  } else if (selected === "refusal-streak") {
    // Bounded: the third bare refusal ends the run. Startup makes two liveness
    // reads before its planner call, so at most that one model call may
    // happen and no task tab may ever open.
    assert.ok(rig.modelCalls.length <= 1, "a streak of refusals must end the run at the bound, not run the errand");
    assert.equal(rig.harness.tabs.size, 0, "a run ended by a refusal streak opens no task tab");
    assert.notEqual(rig.row("pairing-race").status, "done");
  } else {
    assert.ok(rig.modelCalls.length > 0, "ordinary infrastructure errors and a single guard refusal preserve the existing live-work policy");
    assert.equal(rig.harness.storageData.agentId, old.agentId, "transient failure cannot rotate identity");
    assert.notEqual(rig.harness.storageData.currentJob?.status, "stopped", "one refused read must not tell the owner they called it off");
  }
}
console.log(`PASS ${selected}`);

if (selected === "phone-repair" || selected === "phone-release" || selected === "phone-release-legacy") {
  // THE PHONE CHANGES WHO THIS BROWSER BELONGS TO — no New code involved. Owner
  // A's presentation is on screen: a hand-back with its notification, the
  // badge, A's profile and model key. The phone releases the browser (or a
  // second owner claims the same code); the next heartbeat learns the new row.
  const tab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  await background.surfaceHandBack(tab.id, "old owner private detail", "needs_user");
  assert.equal(rig.harness.notifications.size, 1);
  assert.equal(rig.harness.badge.text, "1");
  rig.harness.storageData.ownerProfile = { first_name: "Old", email: "old@example.invalid" };
  rig.harness.storageData.pairCode = "654321";
  // `phone-release-legacy`: an older app, or a release made while signed out,
  // clears `paired` without clearing `owner_ref` (AnticipyBackend.swift:703-704
  // clears it only with an account id). An unpaired row has no owner whatever
  // that column still holds.
  const next = selected === "phone-repair"
    ? { owner_ref: "newownerbbbbbb2", owner: "new", paired: 1 }
    : selected === "phone-release-legacy"
      ? { owner_ref: old.ownerRef, owner: "", paired: 0 }
      : { owner_ref: "", owner: "", paired: 0 };
  Object.assign(rig.agents, next);
  rig.harness.fireAlarm("anticipy-heartbeat");
  await flush(500);
  const s = rig.harness.storageData;
  assert.equal(s.ownerRef, next.paired ? next.owner_ref : "", "an unpaired row has no owner whatever owner_ref still holds");
  assert.equal(!!s.paired, !!next.paired);
  assert.equal(s.agentId, old.agentId, "a phone-driven owner change keeps the credential");
  assert.equal(s.recordId, old.recordId);
  assert.equal(s.pairCode, "654321", "the code stays: the phone can claim this browser again");
  assert.notEqual(s.ownerProfile?.first_name, "Old", "the previous owner's profile must not survive an owner change");
  assert.equal(rig.harness.notifications.size, 0, "the previous owner's notification must not survive an owner change");
  assert.equal(rig.harness.badge.text, "", "the badge must not carry the previous owner's count");
  assert.ok(s.handBacks[tab.id], "evidence stays stored");
  assert.equal(s.handBacks[tab.id].ownerRef, old.ownerRef, "and stays tagged with the owner it belonged to");
  if (selected === "phone-repair") {
    assert.equal(s.openrouterKey, "backend-proxy", "the new owner's key is fetched fresh");
    assert.equal(s.ownerProfile?.first_name, "Owner", "and the new owner's profile replaces the old one");
  } else {
    assert.equal(s.openrouterKey, "", "an unpaired browser holds no model key");
    assert.equal(s.ownerProfile, null);
    assert.equal(s.paired, false);
    assert.equal(s.agentToken, old.agentToken, "the credential stays");
    assert.equal((await setup()).linked, false);
  }
}
if (selected === "legacy-handback-hidden") {
  // An UNTAGGED 0.18.2 record must never be adopted by whoever holds the
  // install now. 0.18.2 rewrote ownerRef in place on a phone-driven owner
  // change and kept handBacks, so "this install had one owner" is false, and
  // adopting would hand owner A's parked page and its URL to owner B on B's
  // first boot -- the cross-owner leak arriving through a convenience.
  await flush(120);
  assert.equal("ownerRef" in (rig.harness.storageData.handBacks[legacyTab.id] || {}), false,
    "an untagged record was stamped with the current owner");
  assert.equal(rig.harness.badge.text, "",
    "an untagged record was counted for an owner who may not be the one who made it");
  assert.equal(await background.openHandBack(legacyTab.id), false,
    "an untagged record was openable by the current owner");
  assert.equal(rig.harness.focusGrants.length, 0, "an unowned parked page was focused");
}
if (selected === "closed-tab-unpaired") {
  const tab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  await background.surfaceHandBack(tab.id, "owner detail", "needs_user");
  assert.ok(rig.harness.storageData.handBacks[tab.id]);
  assert.equal((await reset()).ok, true);
  await chrome.tabs.remove(tab.id);
  await flush(120);
  assert.equal(rig.harness.storageData.handBacks[tab.id], undefined,
    "a closed tab's hand-back is answered whoever owned it — nothing can be shown for a tab that is gone");
  assert.equal(rig.harness.notifications.size, 0);
  assert.equal(rig.harness.badge.text, "");
}
if (selected === "scope-reads-queue") {
  // Between ++identityGeneration and the unpaired write landing, a reader that
  // samples the generation and then reads storage sees the RETIRED owner under
  // the NEW generation — and every fence then accepts it.
  const tab = rig.harness.addTab({ url: "https://fixture.invalid/private-form" });
  await background.surfaceHandBack(tab.id, "old owner detail", "needs_user");
  const create = chrome.notifications.create;
  chrome.notifications.create = async (...args) => { started = true; await deferred; return create(...args); };
  const second = rig.harness.addTab({ url: "https://fixture.invalid/other-form" });
  const held = background.surfaceHandBack(second.id, "second detail", "needs_user");   // holds the identity queue
  await until(() => started);
  const replacement = reset();      // ++identityGeneration now; its unpaired write waits behind the notification
  await flush(30);
  const opening = background.openHandBack(tab.id);
  await flush(50);
  release();
  const [opened] = await Promise.all([opening, held, replacement]);
  assert.equal(opened, false, "a reader in the retirement window must not act for the retired owner");
  assert.equal(rig.harness.focusGrants.length, 0);
}
process.exit(0);
