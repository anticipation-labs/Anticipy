// The installed-extension journey, end to end, against loopback only.
//
//   node proof/audit/installed_extension/run.mjs [--headed] [--scenario NAME,...]
//
// Prerequisites (each loopback, each started separately so their logs survive):
//   python3 -m proof.audit.installed_extension.local_worker up      (:8791)
//   node    proof/audit/installed_extension/fake_provider.mjs        (:8796)
//   node    proof/audit/installed_extension/fixture_site.mjs         (:8797)
//
// Scenarios, in order, each writing a row to work/installed-extension/results.json:
//   install    fresh profile → the extension registers itself → the stand-in phone
//              pairs it → the heartbeat teaches it its owner and model.
//   task       a read-only browser job minted through the real brain engine is
//              claimed by the extension, run against the fixture site (two-hop
//              iframe), and lands `done` with a verified receipt; the SITE saw
//              exactly one click on the widget button.
//   restart    Chrome is closed and relaunched on the same profile: same
//              identity (no second agents row), heartbeat resumes, a second task runs.
//   outage     the Worker is stopped for ~100 s and restarted: identity is NOT
//              rotated, the popup says the queue is unreachable, then recovers,
//              and a third task runs — still one agents row.
//   separation the phone unpairs; a second owner claims a NEW code after the
//              owner presses "New code"; the popup shows none of owner A's task
//              text; a job minted for owner A is never claimed by the browser now
//              paired to owner B.
import { writeFileSync, readFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { launch, storage, setStorage, openSetup, waitFor, popupText, sleep, REPO, cdpTargets } from "./chrome.mjs";

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d; };
const HEADED = process.argv.includes("--headed");
const ONLY = (arg("scenario", "") || "").split(",").filter(Boolean);
const BASE = "http://127.0.0.1:8791";
const SITE = "http://127.0.0.1:8797";
const WORK = join(REPO, "work/installed-extension");
mkdirSync(WORK, { recursive: true });
// The stand-in phone and the worker controller are stdlib-only Python; any
// python3 will do. ANTICIPY_PYTHON wins, then a repo-local venv, then PATH.
const PY = process.env.ANTICIPY_PYTHON
  || [join(REPO, ".venv/bin/python")].find((candidate) => existsSync(candidate))
  || "python3";
const results = [];
const record = (row) => { results.push({ at: new Date().toISOString(), ...row }); writeFileSync(join(WORK, "results.json"), JSON.stringify(results, null, 2)); console.log(JSON.stringify(row)); };

function phone(args) {
  const out = spawnSync(PY, ["-m", "proof.audit.installed_extension.phone", ...args, "--base", BASE],
    { cwd: REPO, encoding: "utf8", env: { ...process.env, PYTHONPATH: REPO, PYTHON_DOTENV_DISABLED: "1" } });
  if (out.status !== 0) throw new Error(`phone ${args[0]} failed: ${out.stderr || out.stdout}`);
  return JSON.parse(out.stdout.trim().split("\n").pop());
}
function workerCtl(cmd) {
  return spawnSync(PY, ["-m", "proof.audit.installed_extension.local_worker", cmd, "--port", "8791", "--provider-port", "8796"],
    { cwd: REPO, encoding: "utf8", env: { ...process.env, PYTHONPATH: REPO, PYTHON_DOTENV_DISABLED: "1" } });
}
const svc = async (path, init = {}) => (await fetch(BASE + path, { ...init, headers: { "content-type": "application/json", "X-Anticipy-Token": "installed-extension-local-only", ...(init.headers || {}) } })).json();
const agentsRows = async () => (await svc("/api/collections/agents/records?perPage=50")).items || [];
// Only THIS browser's rows count: the rig may carry rows from an HTTP smoke or an earlier run.
const myRows = async (agentId) => (await agentsRows()).filter((r) => r.agent_id === agentId);
const siteClicks = async () => (await fetch(SITE + "/__clicks")).json();
const siteReset = () => fetch(SITE + "/__reset", { method: "POST" });

const PROVIDER = "http://127.0.0.1:8796";
async function runTask(context, extId, ownerFile, label) {
  await siteReset();
  await fetch(PROVIDER + "/__reset", { method: "POST" });   // fresh click ledger for this job
  const minted = phone(["mint", "--owner-file", ownerFile, "--start-url", `${SITE}/two-hop`, "--task", `Reveal the slots on the venue page (${label}). Read only.`]);
  const t0 = Date.now();
  // Nudge the poll the way a person does: open the setup page once.
  await openSetup(context, extId);
  let row = null;
  const deadline = Date.now() + 240_000;
  while (Date.now() < deadline) {
    row = phone(["job", "--id", minted.job]);
    if (["done", "failed", "cancelled", "needs_user"].includes(row.status)) break;
    await sleep(3000);
  }
  const clicks = await siteClicks();
  return { job: minted.job, plan_id: minted.plan_id, final: row, seconds: Math.round((Date.now() - t0) / 1000), siteClicks: clicks.map((c) => c.id) };
}

const want = (name) => !ONLY.length || ONLY.includes(name);
let rig = null, extId = "", profile = "", ownerA = join(WORK, "owner-a.json"), ownerB = join(WORK, "owner-b.json"), agentRecord = "";
try {
  // ---------------------------------------------------------------- install
  rig = await launch({ headed: HEADED });
  extId = rig.extId; profile = rig.userDataDir;
  record({ scenario: "launch", extId, blackhole: rig.reach, chrome: rig.bin, profile });
  const before = await storage(rig.context, extId, ["backendUrl", "recordId", "agentId", "pairCode", "ownerRef"]);
  await setStorage(rig.context, extId, { backendUrl: BASE });
  record({ scenario: "launch:targets", targets: await cdpTargets(rig.cdp) });
  await openSetup(rig.context, extId);
  const reg = await waitFor(rig.context, extId, ["recordId", "agentId", "pairCode", "agentToken"], (s) => s.recordId && s.pairCode && s.agentToken, { timeoutMs: 90_000 });
  const rowsAfterRegister = await myRows(reg.agentId);
  record({ scenario: "install:register", ok: !reg.timedOut, storedBefore: { recordId: before.recordId || "", pairCode: before.pairCode || "" },
    recordId: reg.recordId || "", agentsRows: rowsAfterRegister.length, pairCodeLength: String(reg.pairCode || "").length });
  if (reg.timedOut) throw new Error("the extension never registered against the loopback Worker");
  const owner = phone(["owner", "--label", "owner-a", "--owner-file", ownerA]);
  const paired = phone(["pair", "--owner-file", ownerA, "--code", reg.pairCode]);
  agentRecord = paired.agent_record;
  const learned = await waitFor(rig.context, extId, ["ownerRef", "paired", "openrouterKey", "agentModel"], (s) => s.ownerRef === owner.id && s.paired && s.openrouterKey, { timeoutMs: 120_000 });
  record({ scenario: "install:pair", ok: !learned.timedOut, ownerRefMatches: learned.ownerRef === owner.id, paired: !!learned.paired,
    modelKey: learned.openrouterKey || "", model: learned.agentModel || "", waitedFor: "heartbeat to teach the owner (30 s alarm floor)" });
  if (learned.timedOut) throw new Error("the extension never learned its owner from the heartbeat");

  // ------------------------------------------------------------------- task
  if (want("task")) {
    const t = await runTask(rig.context, extId, ownerA, "first");
    record({ scenario: "task", ok: t.final?.status === "done" && t.final?.receipt && t.siteClicks.length === 1 && t.siteClicks[0] === "widget-target", ...t });
  }
  // ---------------------------------------------------------------- restart
  if (want("restart")) {
    const idBefore = await storage(rig.context, extId, ["agentId", "recordId"]);
    await rig.context.close();
    rig = await launch({ headed: HEADED, profile });
    if (rig.extId !== extId) record({ scenario: "restart:extId", before: extId, after: rig.extId });
    extId = rig.extId;
    const idAfter = await storage(rig.context, extId, ["agentId", "recordId", "ownerRef", "paired"]);
    const rows = await myRows(idAfter.agentId);
    const t = await runTask(rig.context, extId, ownerA, "after restart");
    record({ scenario: "restart", ok: idBefore.agentId === idAfter.agentId && idBefore.recordId === idAfter.recordId && rows.length === 1 && t.final?.status === "done" && t.siteClicks.length === 1,
      sameAgentId: idBefore.agentId === idAfter.agentId, sameRecordId: idBefore.recordId === idAfter.recordId, agentsRows: rows.length, stillPaired: !!idAfter.paired, task: t });
  }
  // ----------------------------------------------------------------- outage
  if (want("outage")) {
    const idBefore = await storage(rig.context, extId, ["agentId", "recordId", "agentToken"]);
    workerCtl("down");
    await sleep(100_000);   // three 30 s poll cycles fail
    const during = await storage(rig.context, extId, ["agentId", "recordId", "agentToken", "currentJob"]);
    const popupDuring = await popupText(rig.context, extId);
    const up = workerCtl("up");
    if (up.status !== 0) throw new Error("could not restart the Worker: " + up.stderr);
    // The local D1 persists under --persist-to, so the owner, agent row and jobs survive the restart.
    const rows = await myRows(during.agentId);
    const t = await runTask(rig.context, extId, ownerA, "after outage");
    record({ scenario: "outage", ok: during.agentId === idBefore.agentId && during.recordId === idBefore.recordId && during.agentToken === idBefore.agentToken && rows.length === 1 && t.final?.status === "done",
      identityKeptDuringOutage: during.agentId === idBefore.agentId && during.agentToken === idBefore.agentToken,
      mirrorDuring: during.currentJob ? { status: during.currentJob.status, blocked: !!during.currentJob.blocked } : null,
      popupDuring: popupDuring.body, agentsRowsAfter: rows.length, task: t });
  }
  // ------------------------------------------------------------- separation
  if (want("separation")) {
    const popupA = await popupText(rig.context, extId);
    phone(["unpair", "--owner-file", ownerA, "--agent-record", agentRecord]);
    // The owner presses New code on the setup page: a fresh unpaired identity.
    const setup = await openSetup(rig.context, extId, { keepOpen: true });
    const oldId = await storage(rig.context, extId, ["agentId", "recordId"]);
    const clicked = await setup.evaluate(() => { const b = document.getElementById("newcode") || [...document.querySelectorAll("button")].find((x) => /new code/i.test(x.textContent)); if (!b) return false; b.click(); return true; });
    const fresh = await waitFor(rig.context, extId, ["agentId", "recordId", "pairCode", "ownerRef", "paired"], (s) => s.recordId && s.recordId !== oldId.recordId && s.pairCode && !s.ownerRef, { timeoutMs: 90_000 });
    await setup.close();
    const ownerBRec = phone(["owner", "--label", "owner-b", "--owner-file", ownerB]);
    phone(["pair", "--owner-file", ownerB, "--code", fresh.pairCode]);
    const learnedB = await waitFor(rig.context, extId, ["ownerRef", "paired"], (s) => s.ownerRef === ownerBRec.id && s.paired, { timeoutMs: 120_000 });
    const popupB = await popupText(rig.context, extId);
    // A job for owner A must never be claimed by a browser now paired to B.
    const aJob = phone(["mint", "--owner-file", ownerA, "--start-url", `${SITE}/plain`, "--task", "Owner A's private errand. Read only."]);
    await openSetup(rig.context, extId);
    await sleep(70_000);
    const aRow = phone(["job", "--id", aJob.job]);
    const leakedText = /first|after restart|after outage|Owner A/.test(popupB.body);
    record({ scenario: "separation", ok: clicked && !fresh.timedOut && !learnedB.timedOut && aRow.status === "queued" && !aRow.claimed_by && !leakedText,
      newCodePressed: clicked, freshIdentity: !fresh.timedOut, pairedToB: !learnedB.timedOut, ownerAJobAfter70s: { status: aRow.status, claimed_by: aRow.claimed_by || "" },
      popupBeforeUnpair: popupA.body, popupAfterB: popupB.body, leakedOwnerAText: leakedText });
  }
  // ------------------------------------------------------------ phone-repair
  // The phone alone changes who this browser belongs to: B (the current owner
  // after `separation`) releases it from the app, then owner A claims the SAME
  // code the extension still holds — no New code pressed. B's profile, model
  // key, task text and badge must not reach A.
  if (want("phone-repair")) {
    const beforeRelease = await storage(rig.context, extId, ["ownerRef", "ownerProfile", "openrouterKey", "pairCode", "recordId", "agentId"]);
    const bRecord = (await agentsRows()).find((row) => row.agent_id === beforeRelease.agentId);
    phone(["unpair", "--owner-file", ownerB, "--agent-record", bRecord.id]);
    const released = await waitFor(rig.context, extId, ["ownerRef", "paired", "ownerProfile", "openrouterKey"], (s) => !s.ownerRef && !s.paired, { timeoutMs: 120_000 });
    const popupReleased = await popupText(rig.context, extId);
    // Owner A claims the same code (the row is unpaired again; the code was never rotated).
    phone(["pair", "--owner-file", ownerA, "--code", beforeRelease.pairCode]);
    const ownerARec = JSON.parse(readFileSync(ownerA, "utf8"));
    const learnedA = await waitFor(rig.context, extId, ["ownerRef", "paired", "ownerProfile", "openrouterKey", "agentId", "recordId"], (s) => s.ownerRef === ownerARec.id && s.paired && s.openrouterKey, { timeoutMs: 120_000 });
    const popupA = await popupText(rig.context, extId);
    const t = await runTask(rig.context, extId, ownerA, "after phone re-pair");
    // A's popup may show A's OWN errand (queued during `separation`, runnable
    // again the moment A owns this browser): that is the job surviving the
    // ownership change, not a leak. What must NOT reappear is the presentation
    // retired when B took over -- A's pre-separation task labels.
    const staleA = /after outage|after restart|first/.test(popupA.body);
    record({ scenario: "phone-repair", ok: !released.timedOut && released.openrouterKey === "" && released.ownerProfile === null
        && !learnedA.timedOut && learnedA.agentId === beforeRelease.agentId && learnedA.recordId === beforeRelease.recordId
        && !staleA && t.final?.status === "done" && t.siteClicks.length === 1,
      releaseTimedOut: !!released.timedOut, repairTimedOut: !!learnedA.timedOut, releaseShape: "app (owner_ref cleared)",
      stalePreSeparationText: staleA, ownerErrandRanAfterRepair: /Owner A's private errand/.test(popupA.body),
      releasedWipedKey: released.openrouterKey === "", releasedWipedProfile: released.ownerProfile === null,
      popupReleasedNotLinked: /Not linked/.test(popupReleased.body),
      sameCredentialAfterRepair: learnedA.agentId === beforeRelease.agentId && learnedA.recordId === beforeRelease.recordId,
      popupReleased: popupReleased.body, popupAfterA: popupA.body, task: t });
  }
  // ----------------------------------------------------- phone-release-legacy
  // The same release, but the shape an older app (or a signed-out release)
  // produces: `paired:false` with `owner_ref` left on the row. An unpaired row
  // has no owner whatever that column still holds — the extension must wipe
  // A's profile/key and read "Not linked"; then A re-pairs with the same code.
  if (want("phone-release-legacy")) {
    const before = await storage(rig.context, extId, ["ownerRef", "pairCode", "recordId", "agentId"]);
    const rec = (await agentsRows()).find((row) => row.agent_id === before.agentId);
    phone(["unpair", "--legacy", "--owner-file", ownerA, "--agent-record", rec.id]);
    const rowAfter = (await agentsRows()).find((row) => row.id === rec.id);
    const released = await waitFor(rig.context, extId, ["ownerRef", "paired", "ownerProfile", "openrouterKey"], (s) => !s.ownerRef && !s.paired, { timeoutMs: 120_000 });
    const popupReleased = await popupText(rig.context, extId);
    phone(["pair", "--owner-file", ownerA, "--code", before.pairCode]);
    const ownerARec = JSON.parse(readFileSync(ownerA, "utf8"));
    const learned = await waitFor(rig.context, extId, ["ownerRef", "paired", "openrouterKey", "agentId", "recordId"], (s) => s.ownerRef === ownerARec.id && s.paired && s.openrouterKey, { timeoutMs: 120_000 });
    const t = await runTask(rig.context, extId, ownerA, "after legacy release");
    record({ scenario: "phone-release-legacy", ok: rowAfter.owner_ref === before.ownerRef && !rowAfter.paired
        && !released.timedOut && released.openrouterKey === "" && released.ownerProfile === null && /Not linked/.test(popupReleased.body)
        && !learned.timedOut && learned.agentId === before.agentId && learned.recordId === before.recordId
        && t.final?.status === "done" && t.siteClicks.length === 1,
      rowKeptResidualOwnerRef: rowAfter.owner_ref === before.ownerRef, releaseTimedOut: !!released.timedOut, repairTimedOut: !!learned.timedOut,
      releasedWipedKey: released.openrouterKey === "", releasedWipedProfile: released.ownerProfile === null,
      popupReleasedNotLinked: /Not linked/.test(popupReleased.body),
      sameCredentialAfterRepair: learned.agentId === before.agentId && learned.recordId === before.recordId,
      popupReleased: popupReleased.body, task: t });
  }
} catch (e) {
  record({ scenario: "error", error: String(e).slice(0, 500) });
  process.exitCode = 1;
} finally {
  try { await rig?.context?.close(); } catch { /* gone */ }
}
const failed = results.filter((r) => r.ok === false || r.scenario === "error");
console.log(`\n${results.length} rows, ${failed.length} failed → ${join(WORK, "results.json")}`);
process.exit(failed.length ? 1 : 0);
