// Anticipy extension service worker.
// Polls the Anticipy backend (PocketBase) for action jobs and executes them in
// the user's own browser using their live logged-in sessions — browser-only,
// no service APIs. Irreversible steps stop at a prefilled page for the user
// (or the phone app) to confirm.

import { createBackgroundTab, modelFetch, runAgentGoal } from "./agent_loop.js";
import {
  MAX_STEPS as READ_MAX_STEPS, leaseLapsed, runSupervisedRead,
} from "./supervised_read.js";
import { backendBase } from "./config.js";
import {
  heartbeatPatch,
  isWorkflowJob,
  markEffectUncertainPatch,
  parseJobParams,
  workflowPatch,
} from "./workflow_state.js";

// Keep an engine marker in the service-worker entry file itself. Updating an
// imported module alone can leave Chrome running a cached worker graph for an
// unpacked extension; changing this entry file forces a fresh registration,
// and the same marker is written into every job trace as runtime proof.
const ENGINE_BUILD = "0.11.0";

const BACKEND_LLM = "backend-proxy";
// Job traffic authenticates as THIS ONE AGENT and nothing more. An earlier
// build also attached the server's master `X-Anticipy-Token` here, for the
// single release that let an already-paired install add its per-agent
// credential. /agent/key has returned `service_token: ""` since, and the save
// erases the stored value, so that branch could only ever send an empty
// header — and a browser carrying the server's master credential at all is
// worth deleting on its own account.
async function writeHeaders(leaseToken = "") {
  const { agentId, agentToken } = await chrome.storage.local.get(
    ["agentId", "agentToken"]);
  const h = { "Content-Type": "application/json" };
  if (agentId) h["X-Anticipy-Agent-ID"] = agentId;
  if (agentToken) h["X-Anticipy-Agent-Token"] = agentToken;
  if (leaseToken) h["X-Anticipy-Lease"] = leaseToken;
  return h;
}

// Chrome only guarantees recurring extension alarms every 30 seconds. Values
// below that can appear to work in development and then disappear after a
// service-worker/browser restart. Keep both wake paths at the supported floor
// and re-assert them whenever this worker boots (see ensureWakeAlarms below).
const WAKE_PERIOD_MINUTES = 0.5;
const WAKE_ALARMS = ["anticipy-poll", "anticipy-heartbeat"];
const LEASE_MS = 2 * 60 * 1000;
// A real task takes minutes: a booking, a spreadsheet, anything spanning two
// sites. Two minutes declared live work abandoned and handed it to the next
// sweep while it was still going. The heartbeat is meant to prevent that, but
// it lives in an in-memory set that a service-worker restart empties.
const STALE_JOB_MS = 8 * 60 * 1000; // running w/ no heartbeat -> requeued
// Retrying is right. Retrying without end is not. A job that has been started
// three times and finished none of them will not finish on the fourth — it
// will just keep opening tabs and typing. On 2026-08-06 the same Priya email
// ran about six times this way, because nothing counted.
const MAX_ATTEMPTS = 3;

// WHAT COUNTS AS THIS BROWSER'S WORK — one definition, two callers.
//
// The claim poll and the stale sweep both have to name the same lanes, and
// they used to do it with two hand-written copies of the same clause. They
// drifted, and the way it presented was brutal: research runs in the WORKER
// on a 120s never-heartbeated lease, so two minutes into every research job
// the sweep saw an expired lease on a row it is FORBIDDEN to write, PATCHed
// it, got 403, and that throw escaped the poll cycle before claimJob ever
// ran. For the whole duration of any research job the browser lane claimed
// nothing at all — while the heartbeat kept the phone showing "Chrome ready".
//
// workflow_id!="" keeps unplanned rows out; lane!="research" keeps out work
// that belongs to the server (roadmap §6: read-only goals run in the worker,
// and the backend's research_lane hook refuses a browser claim anyway).
const BROWSER_LANE = 'workflow_id!="" && lane!="research"';
const ownerLaneFilter = (status, ownerRef) =>
  `status="${status}" && owner_ref="${ownerRef}" && ${BROWSER_LANE}`;

// A SUPERVISED READ IS ITS OWN LANE, and it is invisible to the poll above on
// purpose — twice over. It carries no `workflow_id` (there is no plan to
// approve: the person is standing there watching), and
// `backend/pb_hooks/research_lane.pb.js` now appends `lane != "supervised_read"`
// to any queued poll that does not NAME the lane. That second guard exists
// because an old extension in the wild would otherwise claim a read and run it
// through `runAgentGoal` with the full action vocabulary — clicking and typing
// inside somebody's mailbox, with no narration and nobody watching. So this
// filter names the lane explicitly, exactly as `noteResearchWaiting` does.
const supervisedReadFilter = (ownerRef) =>
  `status="queued" && owner_ref="${ownerRef}" && lane="supervised_read"`;

// ---------------------------------------------------------------- pairing
// Each install registers itself once with a 6-digit pair code. The phone app
// claims the code and writes `owner`; from then on this agent only takes
// that owner's jobs and reports a heartbeat the app turns into "last seen Ns".

async function ensureRegisteredOnce() {
  let { agentId, agentToken, recordId, agentCredentialInstalled } =
    await chrome.storage.local.get(
      ["agentId", "agentToken", "recordId", "agentCredentialInstalled"]);
  agentId = agentId || crypto.randomUUID();
  await chrome.storage.local.set({ agentId });
  if (recordId) {
    if (agentCredentialInstalled && agentToken) return { agentId, agentToken, recordId };
    // Existing installs predate per-agent credentials, and this endpoint is
    // how they were meant to get one. It is authorized by the SERVER's master
    // token (backend/pb_hooks/agent_auth.pb.js:53), which this browser no
    // longer holds — see writeHeaders above. So this call has been answered
    // 403 since that release, and a 403 returns null exactly like any other
    // failed registration. It stays because the alternative, re-registering a
    // fresh identity, would drop the owner pairing this row may already carry.
    // An install stuck here needs a reinstall, not another retry.
    const r = await fetch(`${await backendBase()}/agent/upgrade-credential`, {
      method: "POST", headers: await writeHeaders(),
      body: JSON.stringify({ record_id: recordId, agent_id: agentId }),
    });
    if (!r.ok) return null;
    const upgraded = await r.json();
    agentToken = upgraded.agent_token || "";
    if (!agentToken) return null;
    await chrome.storage.local.set({ agentToken, agentCredentialInstalled: true });
    return { agentId, agentToken, recordId };
  }
  const post = async (id) => fetch(`${await backendBase()}/agent/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: id,
      // The extension version rides along in this existing field so nobody has
      // to guess which build is actually installed. An unpacked extension does
      // not auto-update, so "did you reload it?" has been unanswerable — and it
      // is the single most common cause of the browser arm being dead.
      browser: `${navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] || "Chrome"} ext/${chrome.runtime.getManifest().version}`,
      last_seen: new Date().toISOString(),
    }),
  });
  let r = await post(agentId);
  // 409 means the server already has a row for this agent_id while we hold no
  // recordId — the worker was torn down (or the reply lost) in the gap between
  // saving agentId above and saving the registration result below. Re-POSTing
  // the same id 409s forever, and a null return here is total death: heartbeat
  // stops at !reg, claimJob has no ownerRef, ensureLLMKey has no token. Worse,
  // the setup page then says "Connected to Anticipy" while
  // showing ······ and promising a code that can never arrive, and the one
  // recovery button is hidden because it needs a pair code we never got. A
  // fresh identity is the way out: the orphaned row was never paired to anyone.
  if (r.status === 409) {
    console.warn("Anticipy: this browser's id was already registered without a local record — registering a fresh one");
    agentId = crypto.randomUUID();
    await chrome.storage.local.set({ agentId });
    r = await post(agentId);
  }
  if (!r.ok) return null;
  const rec = await r.json();
  agentToken = rec.agent_token || "";
  const pairCode = rec.pair_code || "";
  if (!agentToken || !pairCode) return null;
  await chrome.storage.local.set({
    agentId, agentToken, recordId: rec.id, pairCode, agentCredentialInstalled: true,
  });
  return { agentId, agentToken, recordId: rec.id };
}

// First install wakes this worker through more than one path: onInstalled and
// the immediate poll both need an identity. Without a single-flight guard they
// can register the same fresh browser twice and race while replacing its local
// record/token. Every caller shares one attempt and a later alarm may retry
// cleanly after that attempt has settled.
let registrationInFlight = null;
export async function ensureRegistered() {
  if (registrationInFlight) return registrationInFlight;
  registrationInFlight = ensureRegisteredOnce();
  try {
    return await registrationInFlight;
  } finally {
    registrationInFlight = null;
  }
}

// Jobs this worker is actively running — their claims get refreshed on every
// heartbeat so the stale-requeue sweep never eats a live job.
const activeJobs = new Map();

// Two writers touch one job at once: the heartbeat alarm renews the lease while
// the run's own trace writer saves the evidence journal, and BOTH re-serialize
// the whole params blob. Interleaved, the heartbeat's older snapshot lands last
// and the row silently reverts to the previous journal — so a worker reclaimed
// in that window resumes having forgotten the last clinics it visited and goes
// back to re-open them. Nothing upstream can catch it: every lease and attempt
// field in that write is perfectly consistent.
//
// One chain per job, and the patch is BUILT INSIDE the chain, so each write is
// computed from what the previous one actually committed.
const jobWriteChains = new Map();
export function withJobWrite(id, build) {
  // The stored tail is always already-caught, so one failed write can never
  // strand every later write for that job.
  const prior = jobWriteChains.get(id) || Promise.resolve();
  const next = prior.then(build);
  jobWriteChains.set(id, next.catch(() => {}));
  return next;
}

// ------------------------------------------------------------- LLM key
// Consumers never paste API keys: once paired, the agent fetches its key from
// the backend. A manually saved key (popup) still wins, so dev overrides work.
async function ensureLLMKey(force = false) {
  const { openrouterKey, agentModel, serviceToken, keyFetchedAt, agentId } =
    await chrome.storage.local.get(["openrouterKey", "agentModel", "serviceToken", "keyFetchedAt", "agentId"]);
  // Refresh when ANY piece is missing or the bundle is stale — not just the
  // key. `serviceToken !== undefined` is not about sending that token any more
  // (writeHeaders no longer does); it is the marker that says this install has
  // been through the CURRENT /agent/key at least once. An install that cached
  // only a key from an older build would otherwise look complete forever and
  // never pick up the model or the owner profile that arrive with it.
  const complete = openrouterKey === BACKEND_LLM
    && agentModel !== undefined && serviceToken !== undefined;
  const fresh = Date.now() - (keyFetchedAt || 0) < 6 * 3600 * 1000;
  if (!force && complete && fresh) return openrouterKey;
  if (!agentId) return complete ? openrouterKey : null;
  try {
    const r = await fetch(`${await backendBase()}/agent/key?agent_id=${encodeURIComponent(agentId)}`,
      { headers: await writeHeaders() });
    // A refresh that fails must never LOSE a key we already hold — a stale
    // bundle plus one backend hiccup would otherwise fail every job with
    // "no LLM key" while a perfectly good key sits in storage.
    if (!r.ok) return complete ? openrouterKey : null;
    const { llm_proxy, model, vision_model, service_token, owner, owner_ref } = await r.json();
    if (llm_proxy) {
      await chrome.storage.local.set({
        // An opaque routing marker, not a vendor credential. This overwrites
        // and removes any long-lived key cached by an older build.
        openrouterKey: BACKEND_LLM,
        agentModel: model || "",
        visionModel: vision_model || "",
        // The server no longer returns its master credential, and nothing in
        // this worker would send it if it did. Writing the empty value is how
        // an upgraded install ERASES the token an older build cached.
        serviceToken: service_token || "",
        ownerProfile: owner || null,
        ownerRef: owner_ref || "",
        keyFetchedAt: Date.now(),
      });
      return BACKEND_LLM;
    }
  } catch (_) { /* backend unreachable; keep whatever we already had */ }
  return complete ? openrouterKey : null;
}

async function heartbeat() {
  const reg = await ensureRegistered();
  if (!reg) return null;
  for (const [id, active] of activeJobs) {
    // A run that outlives the cycle ceiling is hung, and renewing its lease
    // is how a hung run becomes IMMORTAL: the stale-job sweep only recovers
    // work whose lease has expired, so a zombie kept beating would hold its
    // job forever. Stop beating for it and let the sweep hand it back.
    if (active.startedAt
        && Date.now() - active.startedAt > POLL_CYCLE_CEILING_MS) {
      console.warn(`Anticipy: job ${id} has run ${Math.round(
        (Date.now() - active.startedAt) / 1000)}s — dropping its lease so it can be recovered`);
      activeJobs.delete(id);
      continue;
    }
    try {
      active.job = await withJobWrite(id, () => {
        const until = new Date(Date.now() + LEASE_MS);
        const patch = isWorkflowJob(active.job)
          ? heartbeatPatch(active.job, { leaseToken: active.leaseToken, leaseUntil: until })
          : { claimed_at: new Date().toISOString() };
        return updateJob(id, patch, active.leaseToken);
      });
    } catch (e) {
      console.warn(`Anticipy: could not renew lease for ${id}: ${String(e).slice(0, 160)}`);
    }
  }
  const r = await fetch(`${await backendBase()}/api/collections/agents/records/${reg.recordId}`, {
    method: "PATCH",
    headers: await writeHeaders(),
    body: JSON.stringify({
      // Re-stamped on every beat, not just at registration: an agent that
      // registered long ago would otherwise report its old build forever,
      // and "which build is he actually running?" is the question this
      // field exists to answer.
      browser: `${navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] || "Chrome"} ext/${chrome.runtime.getManifest().version}`,
      last_seen: new Date().toISOString(),
    }),
  });
  if (!r.ok) return null;
  const rec = await r.json();
  await chrome.storage.local.set({
    owner: rec.owner || "",
    ownerRef: rec.owner_ref || "",
    paired: !!rec.paired,
  });
  // The moment pairing lands, pull the LLM key so the first job never
  // fails on a missing key.
  if (rec.paired) ensureLLMKey();
  return rec;
}

// If a previous worker died mid-job, its `running` jobs go stale; requeue them
// so no task is ever silently lost to a crash or a closed Chrome.
async function requeueStaleJobs() {
  // Owner-scoped: an unrelated install (a second Chrome profile, someone
  // else entirely) must never rewrite this owner's job rows.
  const { ownerRef } = await chrome.storage.local.get(["ownerRef"]);
  if (!ownerRef) return;
  const filter = encodeURIComponent(ownerLaneFilter("running", ownerRef));
  const r = await fetch(`${await backendBase()}/api/collections/jobs/records?filter=${filter}&perPage=20&sort=claimed_at`,
    { headers: await writeHeaders() });
  if (!r.ok) return;
  const { items } = await r.json();
  const now = Date.now();
  for (const j of items || []) {
   // One poisoned row must never cost the other nineteen their recovery.
   // A single refused PATCH used to throw straight out of this loop.
   try {
    if (activeJobs.has(j.id)) continue; // this worker is running it right now
    const expires = j.lease_until ? Date.parse(j.lease_until) : 0;
    const claimed = j.claimed_at ? Date.parse(j.claimed_at) : Date.parse(j.updated);
    if (expires ? now <= expires : now - claimed <= STALE_JOB_MS) continue;
    const tries = Number(j.attempts) || 0;
    if (isWorkflowJob(j) && j.effect_uncertain) {
      await updateJob(j.id, workflowPatch(j, "needs_user", {
        reason: "I may have already sent that before I lost the page — I could not confirm either way. Check the site before I try again, so you don't end up with two.",
        effectUncertain: true,
      }), j.lease_token);
      continue;
    }
    if (tries >= MAX_ATTEMPTS) {
      // Say so once, plainly, and stop. Leaving it queued would mean the next
      // sweep picks it up again and we are back where we started.
      const result = `I tried this ${tries} times and could not get it done. I have stopped rather than keep going.`;
      const patch = isWorkflowJob(j)
        ? { ...workflowPatch(j, "failed", { reason: result }), result }
        : { status: "failed", claimed_by: "", claimed_at: null, result };
      await updateJob(j.id, patch, j.lease_token);
      continue;
    }
    const patch = isWorkflowJob(j)
      ? workflowPatch(j, "queued", {
          reason: "executor lease expired before a confirmed external effect",
          effectUncertain: false,
        })
      : { status: "queued", claimed_by: "", claimed_at: null };
    await updateJob(j.id, patch, j.lease_token);
   } catch (e) {
     console.warn(`Anticipy: could not recover stale job ${j.id}: ${String(e).slice(0, 160)}`);
   }
  }
}

// ----------------------------------------------- saying why nothing happened
// claimJob returns null on six different refusals, and from the outside every
// one of them looks the same: nothing happens. Five of them said nothing at
// all, or said it to the service-worker console — which is not a place a
// person goes. So each refusal now leaves evidence somewhere findable: on the
// job row when the row can be written, and otherwise in the popup's mirror.
//
// The mirror has ONE slot, so a diagnosis may never displace a live run's
// line, and it deliberately carries NO job id: an id is what the popup's
// Stop/Again buttons key off, and what reconcileCurrentJob needs before it
// will touch the mirror at all.
async function noteBlocked(status, doing, why) {
  if (activeJobs.size) return;
  await setCurrentJob({ id: "", status, doing, result: why, blocked: true });
}

// A diagnosis that outlives its problem is one more lie on the surface, and
// this one would otherwise sit there until the next job ran.
async function clearBlocked() {
  try {
    const { currentJob } = await chrome.storage.local.get(["currentJob"]);
    if (currentJob && currentJob.blocked && !currentJob.id) {
      await chrome.storage.local.set({ currentJob: {} });
    }
  } catch (e) { /* best effort */ }
}

// THE 30-SECOND FLOOR, SAID OUT LOUD. chrome.alarms will not repeat faster
// than every half minute and there is no push channel, so a job can genuinely
// sit for ~30s before Chrome starts. The popup showed that as "Picking this
// up: <errand>" with nothing under it, which reads as a stall — and a stall is
// what makes people reload the extension mid-handshake. Say the wait instead.
const QUEUED_SOON = "It's in the queue. I check for new work every half minute, so I'll start "
  + "within about 30 seconds — and opening this popup nudges me straight away.";

// Rows this worker has already explained, and when. A diagnosis rewritten
// every 30 seconds is noise, but suppressing it FOREVER is worse: the popup
// has one slot, so any real work that arrives behind an unrunnable row
// overwrites the explanation, and without a re-say window the only account of
// a permanently stuck job would be gone for the life of the browser.
const explained = new Map();
const RESAY_MS = 10 * 60 * 1000;

// A job with no canonical plan cannot be run here: workflow_state is the only
// thing that authorises a step and there is nothing to read. Two shapes, two
// honest endings.
async function explainNoPlan(job) {
  if (Date.now() - (explained.get(job.id) || 0) < RESAY_MS) return;
  explained.set(job.id, Date.now());
  console.warn(`Anticipy: refusing job ${job.id} without canonical workflow metadata`);
  const line = "This arrived without the plan Anticipy attaches to real work, so this browser cannot run it.";
  if (!job.workflow_id) {
    // A pre-workflow row is writable — nothing guards it. Ending it is kinder
    // than leaving it queued forever, where anyone reading the queue sees work
    // that looks about to happen and never will.
    try {
      const had = (job.result || "").trim();
      await updateJob(job.id, {
        status: "failed", claimed_by: "", claimed_at: null,
        result: `${had ? had + "\n\n" : ""}${line} Ask me for it again and I will queue it properly.`,
      });
      return;
    } catch (e) {
      console.warn(`Anticipy: could not annotate plan-less job ${job.id}: ${String(e).slice(0, 160)}`);
    }
  }
  // workflow_id is set but the embedded plan is missing or unparseable. EVERY
  // patch to such a row is refused by workflow_guard.pb.js ("canonical
  // workflow is missing from params"), including one that writes nothing but
  // `result` — that is the guard working as designed. The popup is the only
  // place left to say it, so say it there.
  await noteBlocked("needs_user", `I can't run one of the jobs in your queue (${job.id})`,
    `${line} Everything else still runs; that one needs to be called off from the app.`);
}

// A refused read is not "no work". One is a blip; several in a row is a queue
// nobody is reading, with a heartbeat still telling the phone all is well.
let pollFailures = 0;

// Exported for the offline test harness: every refusal below has to be
// provable, and poll() is not something a test can steer.
export async function claimJob() {
  // Owner-scoped: a paired agent takes its owner's jobs; an unpaired agent
  // takes nothing at all.
  const { ownerRef, agentId, paired } = await chrome.storage.local.get(
    ["ownerRef", "agentId", "paired"]);
  // An UNPAIRED agent must not claim anything: it cannot fetch a key, so it
  // would claim the job and then fail it forever — a second Chrome profile
  // silently killing the owner's work.
  if (!ownerRef) {
    // An install that was never paired already says so on its own face: the
    // popup shows "Not linked" and a pair code, which is the whole story, and
    // a second line about it would just be noise. The dangerous shape is the
    // OTHER one — paired:true with no owner_ref, which the popup reads as
    // linked and watching for work while this function refuses everything
    // forever. That is a pairing made before owner_ref existed; /agent/key
    // answers it 409 and nothing else ever mentions it.
    if (paired) {
      await noteBlocked("needs_user", "this browser is linked, but the link has no owner id",
        "Nothing can run until it is paired again: open Anticipy on your phone, forget this browser, then enter the code from the setup page.");
    }
    return null;
  }
  // Same lanes as the sweep, from the same definition — see BROWSER_LANE.
  const cond = ownerLaneFilter("queued", ownerRef);
  // TEN ROWS, NOT ONE. This asked for a single row and gave up on it when it
  // turned out to be unclaimable — so ONE poisoned job at the head of the
  // queue (no plan attached, or three attempts already spent) froze the whole
  // browser lane for as long as it sat there, with nothing running and nothing
  // said anywhere. Read a few, run the first that can be run, and account for
  // the ones that cannot.
  const poll = async () => fetch(
    `${await backendBase()}/api/collections/jobs/records?filter=${encodeURIComponent(cond)}&perPage=10&sort=created`,
    { headers: await writeHeaders() }
  );
  let r = await poll();
  // A REFUSED read is not "no work". This returned null on any !ok, so once the
  // stored token went stale the browser arm went permanently, silently deaf:
  // the 10-second heartbeat kept working — PATCHing last_seen needs no token —
  // so the phone showed "Chrome ready" while every job poll was being turned
  // away. Omar watched a released booking sit in the queue with a live-looking
  // browser and nothing happening. Get a fresh key and try once more.
  if (r.status === 401 || r.status === 403) {
    console.warn("Anticipy: job poll refused - refreshing my key and retrying");
    await ensureLLMKey(true);
    r = await poll();
    if (!r.ok) {
      console.warn("Anticipy: still refused after refresh -", r.status,
                   "- reload this extension from the setup page if it persists");
      // This one never heals on its own: the credential this browser holds is
      // not one the backend will accept, and the heartbeat keeps saying
      // "Chrome ready" the entire time.
      await noteBlocked("needs_user", "I can't read your queue from this browser",
        `Anticipy refused this browser's credential (${r.status}). Reload the extension from the setup page; if that doesn't clear it, pair this browser again.`);
      return null;
    }
  }
  if (!r.ok) {
    pollFailures += 1;
    if (pollFailures >= 3) {
      await noteBlocked("needs_user", "I can't reach your queue right now",
        `Anticipy hasn't answered this browser for ${pollFailures} tries (last: ${r.status}). If you're online, check the backend address under Setup & advanced.`);
    }
    return null;
  }
  pollFailures = 0;
  await clearBlocked();
  const items = (await r.json()).items || [];
  const me = agentId || "unknown";
  for (const job of items) {
    if (activeJobs.has(job.id)) continue;
    if (!isWorkflowJob(job)) { await explainNoPlan(job); continue; }
    // Nothing executes while Chrome is shut, so a job can sit for days.
    // Opening the laptop on Monday should NOT silently fire Friday's errand —
    // the world has moved on. Hand it back and let the owner say whether it
    // still stands.
    //
    // Measured from when it was last QUEUED, not from when the row was
    // created. `created` is immutable in PocketBase, so reading it meant a
    // task that had merely EXISTED for 12 hours was bounced — including one
    // the owner had just this second unblocked by answering. His Cactus
    // booking was created 21h before he supplied his details; every resume
    // would have been refused, forever, while she had already told him "I'll
    // finish the booking now". `updated` is refreshed by the requeue that sets
    // status back to "queued", so a fresh resume reads as fresh and a
    // genuinely abandoned errand does not.
    const STALE_HOURS = 12;
    const queuedAt = Date.parse(job.updated || job.created || "");
    if (queuedAt && Date.now() - queuedAt > STALE_HOURS * 3600 * 1000) {
      const hrs = Math.round((Date.now() - queuedAt) / 3600000);
      // Say only what is observable. The previous wording asserted "my browser
      // was closed" — written by the browser, while running, at the moment it
      // wrote it. And it OVERWROTE `result`, destroying the requirement text
      // ("I need your first name, last name, email…") that the brain matches
      // an answer against, so the task could never be resumed by answering
      // again.
      const had = (job.result || "").trim();
      try {
        await updateJob(job.id, {
          ...workflowPatch(job, "needs_user", {
            reason: `Still queued after ${hrs} hours without running. Does it still stand?`,
          }),
          result: (had ? had + "\n\n" : "") +
            `Still queued after ${hrs} hours without running. Does it still stand?`,
        });
      } catch (e) {
        console.warn(`Anticipy: could not park stale job ${job.id}: ${String(e).slice(0, 160)}`);
      }
      continue;
    }
    // Counted at the claim, which is the only place that means "started".
    // Counting on failure would miss the case that actually bit: a job that
    // never reaches an ending at all and is swept back to queued forever.
    const tries = (Number(job.attempts) || 0) + 1;
    if (tries > MAX_ATTEMPTS) {
      try {
        await updateJob(job.id, {
          ...workflowPatch(job, "cancelled", {
            reason: `stopped after ${tries - 1} attempts`,
          }),
          result: `I tried this ${tries - 1} times and could not get it done. I have stopped rather than keep going.`,
        });
      } catch (e) {
        console.warn(`Anticipy: could not close spent job ${job.id}: ${String(e).slice(0, 160)}`);
      }
      continue;
    }
    // Stamp the claim, then read it back: whoever's stamp survives owns the
    // job. This closes the race where concurrent poll() calls (a wake alarm,
    // the popup's anticipy-ping, and this worker booting can all overlap)
    // would each spawn an agent loop for the same job.
    //
    // The popup's mirror is set BEFORE the run starts, because between the
    // claim and the agent loop's first step there is a model call and a tab to
    // open, and a person watching a blank panel through that gap concludes it
    // is broken.
    await setCurrentJob({ id: job.id, status: "queued",
                          doing: jobLine(job, parseJobParams(job)),
                          result: QUEUED_SOON, blocked: false });
    const leaseToken = crypto.randomUUID();
    let fresh;
    try {
      fresh = await updateJob(job.id, workflowPatch(job, "running", {
        actorId: me,
        leaseToken,
        leaseUntil: new Date(Date.now() + LEASE_MS),
        attempt: tries,
      }));
    } catch (e) {
      // A refused claim is somebody else's win or a guard rejection. Either
      // way the NEXT row may still be ours — one bad row must not cost the
      // rest of the queue its turn.
      console.warn(`Anticipy: could not claim ${job.id}: ${String(e).slice(0, 200)}`);
      continue;
    }
    if (fresh.claimed_by !== me || fresh.status !== "running" || fresh.lease_token !== leaseToken) continue;
    return fresh;
  }
  // Nothing here was runnable. Before going quiet, answer the question the
  // owner is actually asking when they open the popup.
  if (!items.length) await noteResearchWaiting(ownerRef);
  return null;
}

// "Nothing is queued for this browser" and "something is queued somewhere
// else" look identical from in here, and the second one is not this browser's
// fault. A queued RESEARCH job is invisible to the poll above — the server
// hides that lane from browsers on purpose, because read-only work runs in the
// worker — so a stalled brain worker presents to the owner as a dead Chrome.
// One extra read, and only when this browser has nothing of its own to do.
async function noteResearchWaiting(ownerRef) {
  try {
    // Naming `lane` is what keeps research_lane.pb.js from rewriting this
    // filter (it only appends its exclusion to a queued poll that does not
    // mention the lane), and naming owner_ref is what guard.pb.js requires of
    // any list an agent credential is allowed to read.
    const researchCond = `status="queued" && owner_ref="${ownerRef}" && lane="research"`;
    const r = await fetch(
      `${await backendBase()}/api/collections/jobs/records?filter=${encodeURIComponent(researchCond)}&perPage=1&sort=created`,
      { headers: await writeHeaders() });
    if (!r.ok) return;
    const job = ((await r.json()).items || [])[0];
    if (!job) { await clearBlocked(); return; }
    const mins = Math.round((Date.now() - Date.parse(job.updated || job.created || "")) / 60000);
    // The worker normally takes one of these within seconds, so anything
    // under a couple of minutes is not yet a symptom worth a line on screen.
    if (!(mins >= 2)) return;
    // A status the popup has no sentence for on purpose: it renders the line
    // below verbatim instead of forcing this into "I'm picking this up",
    // which is exactly what this browser is NOT going to do.
    await noteBlocked("waiting",
      `Waiting on Anticipy's own side, not on this browser: ${jobLine(job, parseJobParams(job))}`,
      `That one is a look-it-up job, so it runs on Anticipy's server rather than in your browser — and it has been waiting ${mins} minutes. Nothing here is broken.`);
  } catch (e) { /* a diagnosis must never break the poll */ }
}

// What the popup shows. The job row on the server stays the source of truth;
// this is a small local mirror so the machine the work is happening on can
// say what it is doing without a round trip. Best-effort by design — the
// mirror must never be able to break a run.
async function setCurrentJob(patch) {
  try {
    const { currentJob = {} } = await chrome.storage.local.get(["currentJob"]);
    await chrome.storage.local.set({ currentJob: { ...currentJob, ...patch, at: Date.now() } });
  } catch (e) { /* best effort */ }
}

// ---------------------------------------------- never-foreground hand-back
// §9: nothing she does may steal focus, ever. When a run ends needing the
// owner — a login wall, a CAPTCHA, a prefilled page awaiting their OK — the
// tab stays in the background where it is. A badge on the extension icon and
// a notification are how the owner finds it; focus moves ONLY on their click.
// Exported for the offline test harness.
const HANDBACK_NOTIF = "anticipy-handback-";

async function refreshBadge() {
  try {
    const { handBacks = {} } = await chrome.storage.local.get(["handBacks"]);
    const n = Object.keys(handBacks).length;
    await chrome.action.setBadgeBackgroundColor({ color: "#c8a97e" });
    await chrome.action.setBadgeText({ text: n ? String(n) : "" });
  } catch (e) { /* best effort */ }
}

export async function surfaceHandBack(tabId, detail, kind) {
  try {
    let url = "";
    try { url = (await chrome.tabs.get(tabId)).url || ""; } catch (e) { /* gone already */ }
    const { handBacks = {} } = await chrome.storage.local.get(["handBacks"]);
    handBacks[String(tabId)] = { url, detail: String(detail || ""), kind: kind || "needs_user", at: Date.now() };
    await chrome.storage.local.set({ handBacks });
    await refreshBadge();
    let site = "the page";
    try { site = new URL(url).hostname.replace(/^www\./, "") || site; } catch (e) { /* no url yet */ }
    await chrome.notifications.create(`${HANDBACK_NOTIF}${tabId}`, {
      type: "basic",
      iconUrl: chrome.runtime.getURL("icons/icon128.png"),
      title: "Anticipy",
      message: kind === "confirm"
        ? `Ready for your OK on ${site} — click to open.`
        : `I need you on ${site} — click to open.`,
      contextMessage: String(detail || "").replace(/\s+/g, " ").slice(0, 120),
      priority: 2,
      requireInteraction: true,
    });
  } catch (e) {
    // A hand-back that can't notify still shows in the popup (badge/handBacks
    // may have landed) — never let the surface break the job result.
  }
}

export async function openHandBack(tabId) {
  const key = String(tabId);
  const { handBacks = {} } = await chrome.storage.local.get(["handBacks"]);
  const hb = handBacks[key];
  try {
    const t = await chrome.tabs.get(Number(key));
    try { await chrome.tabs.ungroup(t.id); } catch (e) { /* not grouped */ }
    // FOCUS-OK(owner-click): the owner clicked the notification or the popup
    // button — the one gesture that may bring a working tab forward.
    await chrome.tabs.update(t.id, { active: true });
    await chrome.windows.update(t.windowId, { focused: true });
  } catch (e) {
    // The tab is gone (swept, or Chrome restarted) — a click that opens
    // nothing reads as a broken promise, so reopen the page instead.
    if (hb && hb.url) {
      // FOCUS-OK(owner-click): same owner gesture, fresh tab.
      try { await chrome.tabs.create({ url: hb.url, active: true }); } catch (e2) { /* give up quietly */ }
    }
  }
  if (hb) {
    delete handBacks[key];
    await chrome.storage.local.set({ handBacks });
  }
  await refreshBadge();
  try { await chrome.notifications.clear(`${HANDBACK_NOTIF}${key}`); } catch (e) { /* gone */ }
}

chrome.notifications.onClicked.addListener((id) => {
  if (id.startsWith(HANDBACK_NOTIF)) openHandBack(id.slice(HANDBACK_NOTIF.length));
});

// A hand-back tab the owner closes by hand is answered — drop its badge.
chrome.tabs.onRemoved.addListener(async (tabId) => {
  try {
    const { handBacks = {} } = await chrome.storage.local.get(["handBacks"]);
    if (!handBacks[String(tabId)]) return;
    delete handBacks[String(tabId)];
    await chrome.storage.local.set({ handBacks });
    await refreshBadge();
    try { await chrome.notifications.clear(`${HANDBACK_NOTIF}${tabId}`); } catch (e) { /* gone */ }
  } catch (e) { /* best effort */ }
});

// One line a person would recognise as their own errand.
function jobLine(job, params) {
  const t = (params && (params.task || params.query || params.subject)) || job.goal || "a task";
  return String(t).replace(/\s+/g, " ").trim().slice(0, 140);
}

async function fetchJob(id) {
  const r = await fetch(`${await backendBase()}/api/collections/jobs/records/${id}`,
    { headers: await writeHeaders() });
  if (r.status === 404) throw new Error("job gone");
  if (!r.ok) throw new Error(`job read failed (${r.status})`);
  return r.json();
}

async function updateJob(id, fields, leaseToken = "") {
  const r = await fetch(`${await backendBase()}/api/collections/jobs/records/${id}`, {
    method: "PATCH",
    headers: await writeHeaders(leaseToken),
    body: JSON.stringify(fields),
  });
  // A silently-swallowed write meant a job deleted server-side ran to
  // completion while every status update vanished into the void.
  if (!r.ok) {
    if (r.status === 404) { activeJobs.delete(id); throw new Error("job gone"); }
    let detail = "";
    try {
      const error = await r.json();
      const validation = error?.data && typeof error.data === "object"
        ? Object.entries(error.data).map(([field, value]) =>
            `${field}: ${String(value?.message || value || "invalid")}`).join("; ")
        : "";
      detail = [error?.detail, error?.message, validation]
        .map((value) => String(value || "").trim()).filter(Boolean).join("; ");
    } catch (_) {}
    throw new Error(`job update failed (${r.status})${detail ? `: ${detail}` : ""}`);
  }
  return r.json();
}

/// Is this job still ours to run? The owner can cancel from the app or by
/// text while the loop is mid-flight; without this the run continued and
/// then RESURRECTED the cancelled job as done/failed.
async function jobStillLive(id, leaseToken = "") {
  try {
    const r = await fetch(`${await backendBase()}/api/collections/jobs/records/${id}`,
      { headers: await writeHeaders() });
    if (r.status === 404) return false;
    if (!r.ok) return true;   // transient: don't abandon real work
    const j = await r.json();
    if (isWorkflowJob(j)) {
      return j.workflow_state === "running" && j.lease_token === leaseToken;
    }
    return j.status === "running" || j.status === "queued";
  } catch (_) {
    return true;
  }
}

// ----------------------------------------------------- resuming a parked tab
// A parked run's tab IS its state: the site's session, the half-filled form,
// the code the site just sent. So the tab id is written onto the durable job
// row and a resume reattaches to it instead of starting the world over.
//
// But a Chrome tab id is unique only inside ONE browser session and is handed
// out again from the start after a restart. A job parked on Friday and
// answered on Monday would reattach to whatever tab now holds id 847 — the
// owner's banking dashboard, a document they left open — and drive
// chrome.debugger into it, clicking and typing a booking flow into a page that
// has nothing to do with the errand. chrome.storage.session is emptied exactly
// when the browser session ends, so it answers the only question that matters
// here: is that id still ours?
async function browserSessionId() {
  try {
    const store = chrome.storage.session;
    // An install too old for session storage cannot prove the id is still
    // ours, and an unprovable id is a stranger's tab.
    if (!store) return "";
    const { browserSession } = await store.get(["browserSession"]);
    if (browserSession) return browserSession;
    const fresh = crypto.randomUUID();
    await store.set({ browserSession: fresh });
    return fresh;
  } catch (_) { return ""; }
}

// The parked tab id, but only when this browser session is the one that parked
// it. Starting fresh costs a filled form; reattaching to the wrong tab types
// into the owner's own work.
export async function resumableTabId(params) {
  if (!params || params.resume_tab == null) return null;
  const session = await browserSessionId();
  if (!session || params.resume_session !== session) return null;
  return params.resume_tab;
}

// Did the OWNER stop this, or did we merely lose our claim on it? Only the row
// knows. A cancelled row is their decision; a row back in the queue (or claimed
// by another window) is ours to be quiet about.
async function ownerCancelled(id) {
  try {
    const j = await fetchJob(id);
    return isWorkflowJob(j) ? j.workflow_state === "cancelled" : j.status === "cancelled";
  } catch (_) {
    // Deleted, or unreadable right now. A row that is gone was called off.
    return true;
  }
}

// Server state -> the word the popup shows. "cancelled" reads as "stopped"
// because that is what the owner did and the popup has no other line for it.
const MIRROR_FOR_STATE = Object.freeze({
  draft: "awaiting_confirm",
  awaiting_approval: "awaiting_confirm",
  awaiting_confirm: "awaiting_confirm",
  queued: "queued",
  running: "running",
  needs_user: "needs_user",
  succeeded: "done",
  done: "done",
  failed: "failed",
  cancelled: "stopped",
});

// The popup's mirror is written when a run STARTS and never again if this
// worker dies mid-job. Quit Chrome during a booking and the mirror freezes at
// "running": the sweep requeues the row, a retry finishes it, and next morning
// the popup still says "Working on this: book Earls for 4" about work that
// ended yesterday — with a Stop button whose write the state machine refuses,
// because succeeded is terminal. refreshBadge exists precisely because a
// restarted browser comes up with derived state wrong; the mirror comes up
// STALE rather than blank, which is worse, and had no equivalent repair.
export async function reconcileCurrentJob() {
  try {
    const { currentJob } = await chrome.storage.local.get(["currentJob"]);
    if (!currentJob || !currentJob.id) return;
    if (activeJobs.has(currentJob.id)) return; // this worker is running it now
    let row;
    try {
      row = await fetchJob(currentJob.id);
    } catch (e) {
      // Deleted server-side: say so. Any other read failure is transient and
      // must not be turned into an invented status.
      if (String(e).includes("job gone")) await setCurrentJob({ status: "removed", result: "" });
      return;
    }
    const state = isWorkflowJob(row)
      ? String(row.workflow_state || "") : String(row.status || "");
    const status = MIRROR_FOR_STATE[state];
    if (!status || status === currentJob.status) return;
    // A row that is queued again (a requeue, a resume, the owner pressing try
    // again on the phone) has no result of its own yet, and a blank line under
    // "Picking this up" is indistinguishable from a stall for the half minute
    // before the next alarm fires. Say what the wait is.
    const result = String(row.result || "").trim();
    await setCurrentJob({ status, blocked: false,
                          result: result || (status === "queued" ? QUEUED_SOON : "") });
  } catch (e) { /* best effort — the mirror must never break a run */ }
}

// -------------------------------------------------------- the supervised read
// "You open it. I read it once, in the front window, while you watch."
//
// The whole loop lives in `supervised_read.js`, which touches no Chrome API at
// all; this is the wiring, and it is the only place that decides what Chrome
// capabilities a read is handed. Three of them are deliberately absent:
//
//   * NO chrome.debugger, ever. `trustedClick`/`typeText` in `agent_loop.js`
//     work by attaching CDP to the tab; without an attach there is physically
//     no path from this code to a click or a keystroke, whatever any model
//     replies. The action whitelist is the rule and this is the wall behind it.
//   * NO `mapPage`. The browser arm's page map indexes every button, link and
//     field so the loop can operate them. A read has no business learning
//     where the buttons are, so it reads visible text and nothing else.
//   * NO focus. The read runs in an unfocused tab
//     (`PRODUCTION-ROADMAP.md:176-185` §9 — nothing steals focus, ever). The
//     "front window" in the promise is the phone's: `SupervisedReadView` is
//     what has to be on screen, and the lease below is what proves it was.
async function claimSupervisedRead(ownerRef, agentId) {
  const filter = encodeURIComponent(supervisedReadFilter(ownerRef));
  let rows;
  try {
    const r = await fetch(
      `${await backendBase()}/api/collections/jobs/records?filter=${filter}&perPage=3&sort=created`,
      { headers: await writeHeaders() });
    if (!r.ok) return null;
    rows = (await r.json()).items || [];
  } catch (_) { return null; }
  for (const job of rows) {
    if (activeJobs.has(job.id)) continue;
    // THE LEASE DECIDES, NOT THE QUEUE. A read queued four minutes ago is a
    // read nobody is watching any more, and the check is the same one the
    // extension will make before every single action — so make it here too
    // rather than opening a tab to discover it. `watching_until` is written
    // only by the view that is on screen, so this is not a staleness heuristic
    // like the 12-hour rule above; it is the supervision itself.
    if (leaseLapsed(job.watching_until)) continue;
    try {
      // The claim is also lease-guarded server-side: PocketBase answers 403
      // when `watching_until` is missing, unparseable or past. A refusal here
      // is therefore normal — the person put their phone down between the poll
      // and the claim — and it is not worth a word to anybody.
      const fresh = await updateJob(job.id, {
        status: "running", claimed_by: agentId, claimed_at: new Date().toISOString(),
      });
      if (fresh.claimed_by !== agentId || fresh.status !== "running") continue;
      return fresh;
    } catch (e) {
      console.warn(`Anticipy: could not claim supervised read ${job.id}: ${String(e).slice(0, 160)}`);
      continue;
    }
  }
  return null;
}

// What a supervised read is allowed to do with Chrome. Deliberately a NARROWER
// set than `sideTripDeps` (in `agent_loop.js`), which may click one link: a
// read may not click at all, so no clicking dep is passed and none exists.
function supervisedReadDeps(job, { apiKey, model, ownerRef, agentId }) {
  // Pages settle before they are read. Same constant idea as the side trip's
  // STEP_SETTLE_MS: a mailbox that has not finished rendering reads as empty.
  const settle = () => new Promise((r) => setTimeout(r, 1200));
  return {
    openTab: async (url) => (await createBackgroundTab(url)).id,
    // THE PAGE THE PERSON IS LOOKING AT — the only surface an extract-only
    // source ever gets. The query deliberately does NOT ask for the active tab
    // by that property name: `check_never_foreground.mjs` counts every
    // focus-granting literal in this file and a read must never add one. The
    // frontmost tab is picked in JS instead, which asks the same question
    // without asserting focus on anything.
    currentTab: async () => {
      const tabs = await chrome.tabs.query({ lastFocusedWindow: true });
      const front = tabs.find((t) => t.active) || tabs[0];
      return front ? front.id : null;
    },
    readPage: async (tabId) => {
      await settle();
      const [hit] = await chrome.scripting.executeScript({
        target: { tabId },
        // Visible text and the address, and nothing else. No element index, no
        // form fields, no hrefs: the read is not allowed to know where the
        // buttons are, so it is never told.
        func: () => ({
          text: String(document.body ? document.body.innerText : "").slice(0, 20000),
          url: String(location.href),
        }),
      });
      return (hit && hit.result) || { text: "", url: "" };
    },
    // Same site only — the module checks that before calling this, and the
    // update carries no focus property, so the tab stays where it was.
    navigate: async (tabId, url) => { await chrome.tabs.update(tabId, { url }); await settle(); },
    scrollPage: async (tabId) => {
      await chrome.scripting.executeScript({
        target: { tabId },
        // A fixed fraction of the viewport. The model asks to scroll; it never
        // says how far, because a number from a model is a number from a page.
        func: () => window.scrollBy(0, Math.round(window.innerHeight * 0.9)),
      });
      await settle();
    },
    closeTab: async (tabId) => { try { await chrome.tabs.remove(tabId); } catch (_) { /* gone */ } },
    // RE-READ FROM THE ROW, EVERY TIME. Not cached, not passed in as a param:
    // cached supervision is not supervision, and a params flag would mean
    // "another process decided I may read your inbox" (`side_trip.js`, "WHO SAYS
    // THE AGENT MAY OPEN SOMEBODY'S MAIL").
    // A row that has been deleted throws, and the module reads a throw as
    // "nobody is watching" — fail closed.
    leaseUntil: async () => (await fetchJob(job.id)).watching_until,
    askModel: async (system, user) => {
      const r = await modelFetch(apiKey, {
        model, temperature: 0, max_tokens: 1024,
        response_format: { type: "json_object" },
        messages: [{ role: "system", content: system }, { role: "user", content: user }],
      });
      if (!r.ok) throw new Error(`read model call failed: ${r.status}`);
      return (await r.json())?.choices?.[0]?.message?.content || "";
    },
    emit: (event) => pushReadEvent(job, ownerRef, agentId, event),
    // The trace, never the page. `supervised_read.js` is careful to hand this
    // only conclusions and refusals; keep it that way.
    note: (line) => console.log(`Anticipy: ${line}`),
  };
}

// The narration, on its way to the phone.
//
// `goal` carries the job id because that is how `supervisedLines(jobID:)` finds
// these rows, and because the backend now REQUIRES it: guard.pb.js lets an
// agent credential create an event only when the kind is exactly read_line or
// read_fact, `owner_ref` is this agent's owner, and `goal` names a
// supervised_read job of that owner whose lease is still live. Without the id
// the write is refused outright, not merely unfilterable.
//
// WHAT IS NOT HERE IS THE POINT. No page text, no subject line, no message
// body, no URL — `design/LOCAL-FIRST.md:9-11`: only conclusions travel.
// `supervised_read.js` refuses to hand this function anything else, and it
// checks every line, including the ones it wrote itself.
async function pushReadEvent(job, ownerRef, agentId, event) {
  const body = {
    device_id: `chrome-${agentId || "unknown"}`,
    kind: event.kind,
    // 400 IS THE SERVER'S CAP, and it is a privacy bound rather than a column
    // width: guard.pb.js refuses a narration event outside 1–400 characters
    // because the shape of breaking promise 4 ("never the mailbox, never a
    // message, never an attachment") is a read_fact carrying a pasted body,
    // and the page slice this loop works from is ~5,000 characters. In
    // practice nothing is ever cut here — `supervised_read.js` already refuses
    // any line over 140 and any fact over 160 — so this is the belt to that
    // module's braces, and a 403 from it is never retried.
    text: String(event.text || "").slice(0, 400),
    goal: job.id,
    owner_ref: ownerRef,
  };
  // The fence tag, and it must survive the trip: `_UNTRUSTED_SOURCES` in
  // `brain/anticipy_core.py` is keyed on this exact string, and a fact that
  // arrives without it is attacker-controlled text handed to a prompt
  // unfenced. Mail is written by OTHER PEOPLE — anyone can email you.
  if (event.source) body.source = event.source;
  if (event.importance) body.importance = event.importance;
  const r = await fetch(`${await backendBase()}/api/collections/events/records`, {
    method: "POST", headers: await writeHeaders(), body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`narration refused (${r.status})`);
}

async function runSupervisedReadJob(job, params) {
  const source = String(params.source || "");
  const { ownerRef, agentId, agentModel } = await chrome.storage.local.get(
    ["ownerRef", "agentId", "agentModel"]);
  // TWO DETERMINISTIC PRECONDITIONS, BOTH REFUSALS RATHER THAN WARNINGS.
  //
  // `consequence` must say read_only. It is the column the rest of the system
  // already uses to mean "this may not act in the world", and a read whose row
  // does not say so is a row somebody built by hand or by mistake.
  if (job.consequence !== "read_only") {
    const result = "That read didn't arrive marked read-only, so I left it alone.";
    await updateJob(job.id, { status: "failed", result });
    await setCurrentJob({ status: "failed", result });
    return;
  }
  const openrouterKey = await ensureLLMKey(true);
  if (!openrouterKey) {
    const result = "I couldn't start: this browser isn't paired to your phone yet.";
    await updateJob(job.id, { status: "failed", result });
    await setCurrentJob({ status: "failed", result });
    return;
  }
  // A ROW MUST NEVER BE LEFT `running`. The stale sweep above filters on
  // `workflow_id!=""` and a supervised read carries no workflow, so nothing
  // would ever come back for this row — and a read stuck at `running` is a
  // read the person's own app cannot tell from one still in progress. Nothing
  // can ACT on it (the lease has long lapsed, and every claim is lease-guarded
  // server-side), so this is about honesty rather than safety. The write is
  // allowed even with a dead lease because it claims nothing.
  let status = "failed";
  let result = "I couldn't read that one.";
  let trace = `supervised read | source ${source} | engine ${ENGINE_BUILD}`;
  try {
    const out = await runSupervisedRead({
      source,
      // Where the read begins, when the phone named a place. A read of a source
      // whose vocabulary has no `navigate` ignores this entirely and reads the
      // page the person already has open — that check is in the module, where
      // the vocabulary lives.
      startUrl: typeof params.start_url === "string" ? params.start_url : "",
      deps: supervisedReadDeps(job, {
        apiKey: openrouterKey, model: agentModel || undefined, ownerRef, agentId,
      }),
      budget: { steps: READ_MAX_STEPS },
    });
    // A LAPSED LEASE IS A CLEAN ENDING, not a failure: the person backgrounded
    // the app, locked the phone or swiped the view away, and the read stopped
    // itself. Writing `failed` on that would teach them that looking away
    // breaks something, which is the opposite of the lesson. The row still ends
    // terminally — `done` — so nothing is left hanging either way.
    status = out.ok ? "done" : "failed";
    result = out.ok
      ? (out.stopped === "lease"
          ? "You looked away, so I stopped there. Nothing kept."
          : `${out.facts.length} thing${out.facts.length === 1 ? "" : "s"} I didn't know about you.`)
      : (out.reason || "I couldn't read that one.");
    // The trace is what somebody debugs later: how far the pass got, why it
    // ended, and every action the whitelist refused. Never what was on the
    // page.
    trace = [trace,
             `steps ${out.steps} | ended: ${out.stopped} | lines ${out.lines.length} | facts ${out.facts.length}`,
             ...out.refused.map((line) => `refused: ${line}`)].join("\n");
  } catch (e) {
    // The module catches its own failures and returns them, so arriving here
    // means the WIRING broke — a missing Chrome permission, a page that
    // refused injection. Truncated, because an exception from a page can carry
    // page text.
    trace = `${trace}\nthe wiring failed: ${String(e).slice(0, 200)}`;
    if (String(e).includes("job gone")) throw e;
  }
  // STATUS, RESULT, TRACE — AND NOTHING ELSE. Do not "tidy" this into the
  // release shape used everywhere else in this codebase
  // (`{status, claimed_by: "", claimed_at: null}` — background.js:322/331,
  // brain/worker.py:971). The backend's lease guard treats the mere PRESENCE
  // of a claimed_by key as a claim attempt and 403s it when `watching_until`
  // has lapsed — which is exactly the moment this line runs on the abort path.
  // The row would silently stay `running` while the 403 went unread, which is
  // the whole failure this write exists to prevent. A terminal row's stale
  // claimed_by bothers nobody.
  await updateJob(job.id, { status, result, trace: trace.slice(-8000) });
  await setCurrentJob({ status, result });
}

async function runJob(job) {
  const params = parseJobParams(job);
  activeJobs.set(job.id, { job, leaseToken: job.lease_token || "",
                           startedAt: Date.now() });
  await setCurrentJob({ id: job.id, status: "running", doing: jobLine(job, params),
                        result: "", blocked: false });
  try {
    await runJobInner(job, params);
  } catch (e) {
    if (String(e).includes("job gone")) {
      await setCurrentJob({ status: "removed", result: "" });
      console.warn(`Anticipy: job ${job.id} was deleted — stopping.`);
    } else {
      throw e;
    }
  } finally {
    activeJobs.delete(job.id);
    jobWriteChains.delete(job.id);
  }
}

// WHAT THE AGENT MAY TREAT AS A VALUE THE OWNER GAVE.
//
// Rendered into the step prompt as FACTS ALREADY GIVEN, which tells the model
// to set form fields to these — so what lands here is not cosmetic. Extracted
// from the run options so the rule can be stated once and tested directly;
// inline, the only way to check it was to read the call site.
//
// Three exclusions, each paid for:
//
//   * UNDERSCORE-PREFIXED KEYS are this system's own bookkeeping (`_workflow`,
//     `_execution_journal`, `_doing`, `_offer_ref`) and were never something a
//     person said. `_offer_ref` is what makes this load-bearing rather than
//     tidy: it is the proof that a consent question was OURS, and the one
//     model that must never be able to reproduce it is precisely the step
//     model this block is rendered for.
//   * owner_answer* — the answer's content already reaches the model inside
//     the approved scope ("They answered: ..."), where it is authority.
//     Handing the same raw sentence over as a "fact" is how it got typed
//     verbatim into OpenTable's Special Requests box (live, 2026-08-15).
//   * the named bookkeeping keys, and `memory`: background knowledge, NOT a
//     given fact. Without that line a short recollection (<200 chars) falls
//     through into FACTS ALREADY GIVEN and the model sets form fields to it.
export function ownerFactsFromParams(params) {
  const p = params && typeof params === "object" ? params : {};
  const NEVER = ["source", "say", "now", "lane", "missing", "authorized",
                 "approved_scope", "needed", "start_url", "task", "assumption",
                 "note", "memory", "resume_tab", "resume_session",
                 // `procedure`: what the server read off the OPEN WEB about how
                 // this kind of task is done. Background, never a given fact —
                 // the same reason `memory` is on this list, and a stronger one,
                 // because its provenance is a web page rather than something he
                 // said. It is an object, so the type filter below would drop it
                 // today; named anyway, because "it happens not to be a string"
                 // is not a rule anybody can rely on.
                 "procedure"];
  const ownerAnswer = (k) => /^owner_answer/i.test(String(k));
  const bookkeeping = (k) => String(k).startsWith("_");
  if (p._workflow?.facts && typeof p._workflow.facts === "object") {
    return Object.fromEntries(Object.entries(p._workflow.facts)
      .filter(([k]) => !ownerAnswer(k) && !bookkeeping(k)));
  }
  return Object.fromEntries(Object.entries(p)
    .filter(([k, v]) => !bookkeeping(k) && !NEVER.includes(k) && !ownerAnswer(k)
      && (typeof v === "string" || typeof v === "number" || typeof v === "boolean")
      && String(v).length < 200));
}

// THE RECEIPT PHOTO, ON ITS WAY OUT OF THE BROWSER.
//
// The bytes exist for a few seconds inside this extension and nowhere else in
// the product (research/2026-08-24-evidence-host.md §5.1-5.3). This is the
// only thing that puts them anywhere durable.
//
// A DATA URL IS DECODED HERE RATHER THAN fetch()ed. `fetch("data:...")` works
// in a service worker, but it makes the deposit depend on the same global that
// every test in this tree replaces with a scripted model — so the one function
// that must keep working while `fetch` is a stub would be the one that cannot
// be tested. atob is not stubbed by anybody.
export function jpegBytes(dataUrl) {
  const s = String(dataUrl || "");
  const comma = s.indexOf(",");
  if (comma < 0 || !s.startsWith("data:image/jpeg;base64,")) return null;
  let bin;
  try { bin = atob(s.slice(comma + 1)); } catch (_) { return null; }
  // The extension's own capture ceiling and the collection's maxSize are the
  // same number on purpose (agent_loop.js:129, 1700000045_evidence.js:72). A
  // frame that got past the first must not die silently at the second.
  if (!bin.length || bin.length > 400000) return null;
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

/// TAKE the frame off the run's result, so that holding it and forgetting to
/// drop it cannot be two separate mistakes.
///
/// This was `delete out.evidenceShot` inline at the call site, and a mutation
/// that removed that line turned ZERO checks red — the bytes leaked into the
/// job row and nothing noticed. A line no test can see is a line that is not
/// really there, so it became a function with a name and a suite. Unconditional
/// on purpose: the shot is removed on every path, not only on success, because
/// a needs_user hand-back is exactly where `out` gets serialized into `params`.
export function takeEvidenceShot(out) {
  if (!out || typeof out !== "object" || !("evidenceShot" in out)) return "";
  const shot = out.evidenceShot;
  delete out.evidenceShot;
  return typeof shot === "string" ? shot : "";
}

/// Deposit one milestone frame and return the receipt entry that points at it,
/// or "" — and "" is a complete answer. A picture that could not be stored is
/// not a reason to fail an errand that already happened: the owner's table is
/// booked either way, and a done-text with no photo is the product's behaviour
/// as of yesterday. The guard's own refusal shape agrees — `owner_ref` is
/// compared against the credential's owner and refused when it disagrees
/// (backend/pb_hooks/guard.pb.js:342-346), so a wrong claim here fails closed
/// at the door rather than depositing somebody else's page.
export async function depositEvidence(job, shot, deps = {}) {
  const base = deps.backendBase || backendBase;
  const headers = deps.writeHeaders || writeHeaders;
  const send = deps.fetch || ((...a) => fetch(...a));
  const store = deps.storage || chrome.storage.local;
  try {
    const bytes = jpegBytes(shot);
    if (!bytes || !job?.id) return "";
    const { ownerRef } = await store.get(["ownerRef"]);
    // Unowned evidence is a picture nobody can see and nobody can erase
    // (1700000045_evidence.js:55-58). Without an owner there is nothing to
    // deposit, and inventing one is the hole the guard exists to close.
    if (!ownerRef) return "";
    const form = new FormData();
    form.append("owner_ref", ownerRef);
    form.append("job", String(job.id));
    // Bound to the exact effect the receipt names, so a photograph of one
    // action can never end up attached to a different one.
    if (job.effect_key) form.append("effect_key", String(job.effect_key));
    form.append("image", new Blob([bytes], { type: "image/jpeg" }), "receipt.jpg");
    const h = await headers();
    // MULTIPART SETS ITS OWN CONTENT-TYPE, boundary and all. writeHeaders()
    // hardcodes application/json for every other call in this file; leaving it
    // on makes PocketBase parse the body as JSON and reject a valid upload.
    delete h["Content-Type"];
    const r = await send(`${await base()}/api/collections/evidence/records`,
      { method: "POST", headers: h, body: form });
    if (!r.ok) {
      console.log(`evidence: could not deposit the receipt photo (${r.status}) — the errand still stands`);
      return "";
    }
    const row = await r.json();
    return row && row.id ? `evidence:${row.id}` : "";
  } catch (e) {
    console.log(`evidence: could not deposit the receipt photo (${String(e).slice(0, 120)})`);
    return "";
  }
}

// WHAT A PARKED JOB REMEMBERS ABOUT THE QUESTION IT IS PARKED ON.
//
// `_offer_ref` is the consent offer's ref (side_trip.js `mintOfferRef`), and
// it is written on EVERY needs_user hand-back — the minted value when the run
// handed back one of our own consent offers, and "" when it handed back
// anything else. The empty write is the load-bearing half: a ref that outlived
// its question is a ref the step model can quote back out of the approved
// scope, having read it there, and forge a question with.
//
// The resume stamp is separate and conditional, because a tabless park has no
// tab to point at. Gating the ref on the same condition — which is what the
// shape of this patch invites — would leave stale refs alive on every tabless
// park.
export function handBackParamsPatch(out, parkedSession) {
  const patch = {
    _offer_ref: typeof out?.offerRef === "string" ? out.offerRef : "",
  };
  if (out && out.tabId != null) {
    patch.resume_tab = out.tabId;
    patch.resume_session = parkedSession;
  }
  return patch;
}

async function runJobInner(job, params) {
  // THE FIRST BRANCH, ABOVE EVERYTHING. A supervised read may never fall
  // through into the executor below: the rewrite three lines down turns any
  // job into `agent_goal`, which is the full click-and-type loop, and running
  // a read through it would put a model with a keyboard inside somebody's
  // mailbox. The lane is claimed by its own poll, so nothing should arrive
  // here by another route — this is the wall that makes "should" irrelevant.
  if (job.lane === "supervised_read") return runSupervisedReadJob(job, params);


  // Canonical plans all use the same adaptive browser executor: a production
  // plan must not bypass verification merely because its goal string happens
  // to match some historical template name.
  if (isWorkflowJob(job) && job.goal !== "agent_goal") {
    const task = params.task || (params.source
      ? `${job.goal} (context: heard "${params.source}")` : job.goal);
    return runJobInner({ ...job, goal: "agent_goal" }, { ...params, task });
  }

  if (job.goal === "agent_goal") {
    // Autonomous mode: LLM click-loop via chrome.debugger in a background
    // Anticipy tab group (same mechanics as Claude in Chrome / Codex).
    // Model selection is server-controlled and can change during a recovery.
    // Refresh once per job; a failed refresh preserves the last good bundle.
    const openrouterKey = await ensureLLMKey(true);
    if (!openrouterKey) {
      const result = "no LLM key: not paired yet, or the backend has none configured";
      const patch = isWorkflowJob(job)
        ? { ...workflowPatch(job, "failed", { reason: result }), result }
        : { status: "failed", result };
      await updateJob(job.id, patch, job.lease_token);
      await setCurrentJob({ status: "failed", result: "I couldn't start: this browser isn't paired to your phone yet." });
      return;
    }
    try {
      const { agentModel, visionModel, ownerProfile: cachedProfile, agentId: myId } =
        await chrome.storage.local.get(["agentModel", "visionModel", "ownerProfile", "agentId"]);
      // Re-read WHO HE IS at the start of every run. The key bundle is
      // cached for six hours, which is right for a key and wrong for
      // identity: he can add his name and retry in the same minute.
      let ownerProfile = cachedProfile;
      try {
        const pr = await fetch(`${await backendBase()}/agent/key?agent_id=${encodeURIComponent(myId || "")}`,
          { headers: await writeHeaders() });
        if (pr.ok) {
          const fresh = (await pr.json()).owner;
          if (fresh) { ownerProfile = fresh; await chrome.storage.local.set({ ownerProfile: fresh }); }
        }
      } catch (_) { /* keep what we had */ }
      // A resumed job goes back to its own parked tab — session, filled form
      // and all — but only while that id still means the tab we parked.
      const resumeTabId = await resumableTabId(params);
      const out = await runAgentGoal(params.task, {
        apiKey: openrouterKey,
        // WHICH QUESTION THIS JOB IS PARKED ON, if it is parked on one of our
        // consent offers. Minted by the run that handed the offer back, stored
        // here, and checked against the question the brain quotes into
        // approved_scope. This is NOT an authorization flag and cannot become
        // one: with a matching ref and no answer, or an answer a model reads as
        // no, both mailbox doors stay shut. What it settles is only "was the
        // question the owner answered OURS" — which used to be settled by
        // testing his quoted question for a sentence AGENT_SYSTEM instructs the
        // step model to write, and a reviewer opened the owner's Gmail through
        // exactly that gap on 2026-08-24.
        //
        // Params is the right home because of who cannot write here: the owner's
        // words land in approved_scope, and the step model emits actions, not
        // params. Neither can put a value in this key.
        offerRef: typeof params._offer_ref === "string" ? params._offer_ref : "",
        startUrl: params.start_url || undefined,
        resumeTabId,
        stillLive: () => jobStillLive(job.id, job.lease_token),
        ...(agentModel ? { model: agentModel } : {}),
        ...(visionModel ? { visionModel } : {}),
        ownerProfile,
        // The owner already said yes in the app or by text; the gate lives
        // in the job queue, so the browser must not ask a second time.
        // A read-only command is already authorized to perform reversible
        // navigation/search. Its separate readOnly boundary below still
        // mechanically refuses any genuinely consequential control.
        authorized: params.authorized === true || job.consequence === "read_only",
        readOnly: job.consequence === "read_only",
        // Exactly what the owner agreed to, in their own words plus what
        // she told them — the only thing an action is measured against.
        // The model's goal is navigation guidance; the owner's retained words
        // are the authority for exact form values.  A paraphrased goal once
        // turned "battery will not charge" into "battery not charging" and
        // still passed the old combined-scope guard.
        // The owner's later ANSWERS and corrections live only in
        // approved_scope ("You stopped and asked: ... They answered: ...",
        // "They changed: ..."). authority_text alone shadowed them — the
        // browser re-asked questions the owner had already answered (hunt
        // find, 2026-08-15). Verbatim authority stays the base; the Q/A and
        // correction tails ride along.
        scope: (() => {
          const authority = params._workflow?.authority_text || "";
          const approved = String(params.approved_scope || "");
          if (!authority) return approved || params.say || params.source || "";
          const markers = ["You stopped and asked:", "They changed:"];
          const at = markers.map((m) => approved.indexOf(m))
            .filter((i) => i >= 0);
          return at.length
            ? `${authority} ${approved.slice(Math.min(...at))}` : authority;
        })(),
        // Every concrete detail already on the job record (time, party size,
        // an address, an answer he texted) — so the agent SETS them instead
        // of asking for them. Bookkeeping keys are not facts.
        // owner_answer* is excluded from BOTH branches: the answer's content
        // already reaches the model inside the approved scope ("They
        // answered: ..."), where it is authority. Handing the same raw
        // sentence over as a "fact" is how it got typed verbatim into
        // OpenTable's Special Requests box (live, 2026-08-15).
        facts: ownerFactsFromParams(params),
        // WHAT THE BRAIN REMEMBERED, stamped on the row by
        // Anticipy._queue_job. A string, already injection-filtered and length
        // capped brain-side (brain/anticipy_core.py memory_notes) — kept as an
        // opaque string here on purpose: this worker is not the place to decide
        // what is safe to replay, and re-deriving that rule in a second
        // language is how the two copies drift.
        //
        // Read from params, NOT from params._workflow: memory is background,
        // not part of the approved scope, and anything inside _workflow is
        // covered by the digest his approval is bound to.
        memory: typeof params.memory === "string" ? params.memory.slice(0, 1200) : "",
        // WHAT THE SERVER LOOKED UP BEFORE LETTING GO OF THIS ROW.
        //
        // The research gate parks a world-touching errand on the research lane
        // until the worker has read how the task is done, then hands the row
        // back carrying what it read (brain/worker.py run_preflight_research).
        // Without this the browser waits for that read and then pays to do it
        // again itself.
        //
        // Passed through raw and NOT trusted here: runAgentGoal puts it through
        // learn.js's cleanProcedure — the same door a locally-learned procedure
        // goes through — and reads it back out of the cache before using it.
        // Deciding here what is safe to keep would be the second copy of a rule
        // that already exists, in a second file, and that is how two copies
        // drift. Same doctrine as `memory` directly above.
        //
        // Read from params, NOT from params._workflow: a procedure is
        // background, not part of the approved scope, and anything inside
        // _workflow is covered by the digest his approval is bound to.
        procedure: params.procedure && typeof params.procedure === "object"
          && !Array.isArray(params.procedure) ? params.procedure : null,
        // A Manifest V3 worker may be reclaimed during a long research run.
        // Keep its bounded live-page notebook on the canonical job so a
        // lease retry resumes with evidence already earned instead of
        // forgetting two clinics/listings/vendors and starting from zero.
        initialEvidenceJournal: Array.isArray(params._execution_journal)
          ? params._execution_journal : [],
        // The step-by-step trace lands on the job row as the agent works, so
        // a run is auditable after the fact. Throttled: at most one write
        // every few seconds, always carrying the latest tail.
        onTrace: (() => {
          let last = 0;
          const priorTrace = String(job.trace || "").trim();
          const attemptHeader = `=== attempt ${Number(job.attempts) || 1} | engine ${ENGINE_BUILD} ===`;
          return async (history, final = false, checkpoint = {}) => {
            const now = Date.now();
            if (!final && now - last < 4000) return;
            last = now;
            const currentTrace = history.slice(-160).join("\n");
            const trace = [priorTrace, attemptHeader, currentTrace]
              .filter(Boolean).join("\n").slice(-90000);
            const journal = (Array.isArray(checkpoint?.evidenceJournal)
              ? checkpoint.evidenceJournal : []).slice(-18).map((entry) => ({
                fingerprint: String(entry?.fingerprint || "").slice(0, 200),
                url: String(entry?.url || "").slice(0, 500),
                title: String(entry?.title || "").slice(0, 200),
                text: String(entry?.text || "").slice(0, 2500),
                elements: String(entry?.elements || "").slice(0, 1000),
              }));
            if (journal.length) params = { ...params, _execution_journal: journal };
            // THE ONE LINE HE ACTUALLY SEES.
            //
            // The trace beside it is for whoever debugs this later: it is
            // written for engineers ("step 12: llm error", raw JSON) and the
            // phone has never read it. This is the same moment in his own
            // words, and it rides a write that was already happening every
            // four seconds — so telling him what is going on costs nothing.
            //
            // Without it, a forty-minute run shows the words "On it" and
            // nothing else, and a run working perfectly is indistinguishable
            // from one that died twenty minutes ago.
            const doing = String(checkpoint?.doing || "").slice(0, 120);
            const doingChanged = !!doing && doing !== params._doing;
            if (doingChanged) params = { ...params, _doing: doing };
            job = await withJobWrite(job.id, () => updateJob(job.id,
              { trace, ...(journal.length || doingChanged ? {
                params: JSON.stringify(params),
              } : {}) }, job.lease_token));
            const active = activeJobs.get(job.id);
            if (active) active.job = job;
          };
        })(),
        onBeforeExternalEffect: isWorkflowJob(job) ? async () => {
          job = await updateJob(job.id, markEffectUncertainPatch(job), job.lease_token);
          const active = activeJobs.get(job.id);
          if (active) active.job = job;
        } : null,
      });
      // A job the owner called off mid-run keeps their decision — writing
      // done/failed over a cancellation resurrects work they stopped.
      if (out.status === "cancelled") {
        // But the loop cannot tell a cancellation from a lost claim: its one
        // liveness test is "still running AND still my lease token", which is
        // equally false when the owner cancels, when the lease expires and the
        // sweep hands the job back, and when a second Chrome profile claims it.
        // A two-minute wifi drop on a train ended an Earls booking with
        // "Stopped: you called this off" — the owner had called nothing off,
        // nothing was written server-side, and that lie was the only record of
        // what happened. Ask the row which of the two it actually was.
        const stoppedByOwner = await ownerCancelled(job.id);
        if (!stoppedByOwner) {
          console.warn(`Anticipy: job ${job.id} lost its claim mid-run — the row went back to the queue, stopping here`);
        }
        await setCurrentJob({
          status: "stopped",
          result: stoppedByOwner
            ? (out.result || "you called this off — I stopped where I was.")
            : "I lost my hold on this one — my connection dropped or another window picked it up. I stopped where I was and handed it back.",
        });
        return;
      }
      // needs_user (login wall, CAPTCHA, refused site) is NOT the same state
      // as awaiting_confirm (owner go-ahead pending) — conflating them lets a
      // free-form "yes" re-release a stuck job instead of the intended one.
      const status = out.status === "done" ? "done"
        : out.status === "needs_user" ? "needs_user" : "failed";
      const canonicalState = status === "done" ? "succeeded"
        : status === "needs_user" || job.effect_uncertain ? "needs_user" : "failed";
      const result = status === "failed" && job.effect_uncertain
        ? "I may have already sent that before I lost the page — I could not confirm either way. Check the site before I try again, so you don't end up with two."
        : (out.result || "");
      // §9: a kept-back tab never surfaces itself — badge + notification, and
      // the owner's click is what focuses it (openHandBack). Surfaced before
      // the job write so a deleted job row can't strand a hidden tab.
      if (canonicalState === "needs_user" && out.tabId != null) {
        await surfaceHandBack(out.tabId, result, "needs_user");
      }
      const parkedSession = canonicalState === "needs_user" && out.tabId != null
        ? await browserSessionId() : "";
      // THE PHOTO GOES FIRST, and then the bytes stop existing.
      //
      // Deposited before the receipt is written, because the receipt has to be
      // able to name the row. Deleted immediately afterwards, because `out` is
      // handed to handBackParamsPatch and read by the trace writer below, and
      // both of those serialize what they are given into a job row — a
      // 100KB data URL in `params` would be a screenshot of a logged-in page
      // sitting in a text column forever, which is the exact thing
      // evidence.pb.js was built to avoid.
      const shot = takeEvidenceShot(out);
      const shotRef = canonicalState === "succeeded"
        ? await depositEvidence(job, shot) : "";
      const transition = isWorkflowJob(job)
        ? workflowPatch(job, canonicalState, {
            reason: result || (canonicalState === "failed"
              ? "browser execution failed" : "the browser needs the owner"),
            effectUncertain: !!job.effect_uncertain,
            // The session stamp travels with the tab id: it is what lets the
            // resume prove the id still points at the tab we parked.
            // WRITTEN ON EVERY needs_user, INCLUDING WITH NO TAB. `_offer_ref`
            // carries the offer this job is now parked on — and an empty string
            // when the hand-back was not one of our offers, which is how a ref
            // is stopped from outliving its question. Gating that clear on
            // `out.tabId != null`, the way the resume stamp is gated, would
            // leave a stale ref alive on any tabless park, and a stale live ref
            // is one the step model can quote back out of the approved scope.
            ...(canonicalState === "needs_user"
              ? { paramsPatch: handBackParamsPatch(out, parkedSession) } : {}),
            ...(canonicalState === "succeeded" ? {
              summary: result || "completed",
              verified: out.receipt?.verified === true,
              // PREPENDED, not appended. workflow_state.js:116 keeps the first
              // 12 entries, and the pointer to the photograph is the one entry
              // that nothing else in the product can reconstruct — the rest of
              // the array is a proof index the verifier can rebuild.
              evidence: [...(shotRef ? [shotRef] : []), ...(out.receipt?.evidence || [])],
            } : {}),
          })
        : {
            status, result,
            ...(status === "needs_user"
              ? { params: JSON.stringify({
                  ...params, ...handBackParamsPatch(out, parkedSession) }) } : {}),
          };
      job = await updateJob(job.id, { ...transition, result }, job.lease_token);
      // The job row keeps needs_user (the phone offers Try again on it), but
      // in Chrome the honest word for "you cancelled the debugging bar" is
      // stopped, not "I need you".
      await setCurrentJob({
        status: out.stoppedInChrome ? "stopped"
          : canonicalState === "needs_user" ? "needs_user" : status,
        result,
      });
    } catch (e) {
      if (String(e).includes("job gone")) throw e;
      const uncertain = !!job.effect_uncertain;
      const result = uncertain
        ? "I may have already sent that before I lost the page — I could not confirm either way. Check the site before I try again, so you don't end up with two."
        : String(e);
      const patch = isWorkflowJob(job)
        ? { ...workflowPatch(job, uncertain ? "needs_user" : "failed", {
            reason: result, effectUncertain: uncertain,
          }), result }
        : { status: "failed", result };
      await updateJob(job.id, patch, job.lease_token);
      await setCurrentJob({ status: uncertain ? "needs_user" : "failed", result });
    }
    return;
  }

  // Nothing reaches this line by any route the system actually uses. A
  // workflow row whose goal is not agent_goal was rewritten to agent_goal at
  // the top of this function, and a row WITHOUT workflow metadata is refused
  // outright at claim. Only a hand-inserted legacy record can arrive here, and
  // the honest thing to do with one is run it as a free-form task through the
  // same verified executor as everything else.
  //
  // This used to consult an ACTIONS table of prefilled Gmail / Calendar /
  // Google-search URLs that parked the job at awaiting_confirm. Dead code with
  // a dangerous shape: it skipped the exact-fact and stop-before-submit checks
  // the agent_goal path applies, and it did so for whichever goal string
  // happened to collide with a template name the brain still emits
  // (brain/llm.py:202 still produces draft_and_send_document).
  const task = params.source ? `${job.goal} (context: heard "${params.source}")` : job.goal;
  return runJobInner({ ...job, goal: "agent_goal" }, { ...params, task });
}

// Only one poll cycle at a time. There is no push channel: grep extension/ for
// EventSource or WebSocket and you find nothing. The only recurring wake is
// the 0.5-minute chrome.alarms floor — Chrome refuses anything shorter for an
// extension — plus the popup's anticipy-ping and this worker booting. Those
// three still overlap, and overlapping cycles double-claim jobs.
//
// Say the consequence out loud, because a reader who assumes a push channel
// will go looking for one: a job queued a second after a cycle ends waits up
// to ~30s before Chrome starts on it. That is the floor, not a bug to hunt.
//
// The lock is a TIMESTAMP, not a boolean, because a boolean is a permanent
// deafness bug: poll() awaits the whole job run, so a runJob() that never
// settles (a page that never resolves, a debugger command with no reply)
// leaves the flag true forever and every later alarm returns at the guard
// with no log and no recovery. Certification 2026-08-15 caught it exactly:
// case 193 hung in `running` and the next 48 cases were never claimed —
// the same "Chrome says connected but nothing happens" the owner watched
// live. A cycle older than the ceiling is a dead cycle: take the lock.
let pollStartedAt = 0;
// Comfortably longer than the slowest healthy run (certification p100 was
// ~90s over 313 cases) and shorter than a person's patience.
const POLL_CYCLE_CEILING_MS = 12 * 60 * 1000;
async function poll() {
  const now = Date.now();
  if (pollStartedAt && now - pollStartedAt < POLL_CYCLE_CEILING_MS) return;
  if (pollStartedAt) {
    console.warn(`Anticipy: previous poll cycle never finished (${Math.round(
      (now - pollStartedAt) / 1000)}s) — reclaiming the queue`);
  }
  pollStartedAt = now;
  try {
    await heartbeat();
    // Housekeeping may NEVER decide whether real work gets claimed. This was
    // awaited bare, so one refused row aborted the cycle before claimJob().
    await requeueStaleJobs().catch((e) => console.warn(
      `Anticipy: stale-job sweep failed (continuing to claim): ${String(e).slice(0, 200)}`));
    // A SUPERVISED READ GOES FIRST, always. Somebody is holding their phone
    // with the view open, watching for a line to appear; a queued errand is
    // not. And the read's own lease is ~30 seconds long, which is shorter than
    // the 0.5-minute alarm floor this worker is stuck with — so a read that
    // waits behind a forty-minute booking is a read that expires unrun and
    // looks, from the phone, exactly like a product that does nothing.
    const { ownerRef: readOwner, agentId: readAgent } =
      await chrome.storage.local.get(["ownerRef", "agentId"]);
    const read = readOwner ? await claimSupervisedRead(readOwner, readAgent) : null;
    if (read) {
      await runJob(read);
      return;
    }
    const job = await claimJob();
    if (job) await runJob(job);
  } catch (e) {
    // Keep polling on the next alarm, but never again silently: this catch
    // swallowed 23 consecutive claim-path 409s in one live run while the
    // heartbeat kept the phone showing "Chrome ready". A dead pipe must be
    // loud in the worker console even when it cannot be fatal.
    console.warn(`Anticipy: poll cycle failed: ${String(e).slice(0, 300)}`);
  } finally {
    // Only the cycle that owns the lock may clear it. A reclaimed-from
    // cycle finishing later must not unlock the one now running.
    if (pollStartedAt === now) pollStartedAt = 0;
  }
}

// Alarms usually survive a browser restart, but Chrome explicitly documents
// that this is not guaranteed. Creating them only in onInstalled left a live
// Chrome process with no queue consumer. This check is deliberately generic:
// it repairs the executor clock, not any particular site or task.
export async function ensureWakeAlarms() {
  for (const name of WAKE_ALARMS) {
    const alarm = await chrome.alarms.get(name);
    if (alarm && Number(alarm.periodInMinutes) === WAKE_PERIOD_MINUTES) continue;
    const timing = {
      delayInMinutes: WAKE_PERIOD_MINUTES,
      periodInMinutes: WAKE_PERIOD_MINUTES,
    };
    // persistAcrossSessions IS CHROME 150+. Older Chrome does not ignore the
    // unknown key — it throws
    //   Error at parameter 'alarmInfo': Unexpected property: 'persistAcrossSessions'
    // so the alarm is never created AT ALL, and every caller of this function
    // swallows the rejection with .catch(() => {}). Measured live in Chrome
    // 148 on 2026-08-19: alarms.getAll() stayed empty forever, a job queued
    // with no extension page open sat untouched for the full 30s window, and
    // the same job was claimed 194ms after the popup was opened. That is
    // exactly "she does nothing until I open the popup" — the whole browser
    // arm reduced to a manual button, in silence, on every Chrome older than
    // 150. Ask for persistence; take a working alarm over a persistent one.
    try {
      await chrome.alarms.create(name, { ...timing, persistAcrossSessions: true });
    } catch (e) {
      console.warn(`Anticipy: this Chrome has no persistent alarms (${String(e).slice(0, 120)}) — using a plain one`);
      await chrome.alarms.create(name, timing);
    }
    // Read it back. A create that quietly did nothing leaves this browser with
    // no clock, and the only symptom is work that never starts.
    if (!(await chrome.alarms.get(name))) {
      console.warn(`Anticipy: Chrome refused the ${name} wake alarm. This browser will only pick up work while an extension page (the popup or the setup page) is open.`);
    }
  }
}

async function stopJob(id) {
  const job = await fetchJob(id);
  const active = activeJobs.get(id);
  const fields = isWorkflowJob(job)
    ? { ...workflowPatch(job, "cancelled", { reason: "you stopped this from Chrome" }),
        result: "you stopped this from Chrome" }
    : { status: "cancelled", result: "you stopped this from Chrome" };
  return updateJob(id, fields, active?.leaseToken || job.lease_token || "");
}

async function retryJob(id) {
  const job = await fetchJob(id);
  if (!isWorkflowJob(job)) {
    return updateJob(id, { status: "queued", claimed_by: "", claimed_at: null });
  }
  if (job.effect_uncertain) {
    throw new Error("check the site before retrying a possible external effect");
  }
  // AN OWNER'S RETRY IS A NEW GRANT. Attempts survive a requeue, and
  // claimJob cancels anything already at the cap — so pressing "try again"
  // on a job whose three attempts were eaten by worker deaths cancelled it
  // instantly, without running, and reported "I tried this 3 times". The
  // phone-side approval path already resets the budget; this second requeue
  // path did not.
  return updateJob(id, workflowPatch(job, "queued", {
    reason: "the owner asked Chrome to try this approved version again",
    effectUncertain: false,
    attempt: 0,
  }));
}

// The popup's two controls. Both go through updateJob — the same write path
// every other status change uses — so nothing here is a second source of
// truth: a stop lands on the job row, and the running loop's own jobStillLive
// check picks it up within a poll and stops where it is.
chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
  if (!msg || !msg.type) return;
  // The pairing page's pulse. In a brand-new profile Chrome has been observed
  // to create NO alarms at all (probed live 2026-08-14: getAll() still empty
  // 95s after install), and a worker kept alive by DevTools/automation never
  // re-runs its module top level for a message — so relying on the boot path
  // alone left the battery's worker heartbeating exactly once, pre-pairing,
  // and then deaf forever. The handler does the work itself: every ping
  // re-asserts the alarms and IS a poll, whatever the worker's lifecycle.
  if (msg.type === "anticipy-ping") {
    ensureWakeAlarms().catch(() => {});
    poll();
    respond({ ok: true });
    return;
  }
  // A refused write must never be answered "ok". Both of these swallowed the
  // rejection and reported success, so the popup said "Stopping…" and snapped
  // straight back to "Working on this" — every click, forever, with no error
  // anywhere. Repairing the mirror from the row is what makes the refusal
  // visible: it is almost always stale, and the row is the truth.
  const refused = (what) => async (e) => {
    console.warn(`Anticipy: ${what} refused for ${msg.id}: ${String(e).slice(0, 200)}`);
    await reconcileCurrentJob();
    respond({ ok: false, error: String(e).slice(0, 200) });
  };
  if (msg.type === "anticipy-stop" && msg.id) {
    stopJob(msg.id)
      .then(() => setCurrentJob({ status: "stopped", result: "You stopped this. Nothing more was done." }))
      .then(() => respond({ ok: true }))
      .catch(refused("stop"));
    return true;
  }
  if (msg.type === "anticipy-again" && msg.id) {
    retryJob(msg.id)
      // Not a blank line: the owner has just pressed a button and the next
      // alarm may be 30 seconds away, so the panel must say that rather than
      // sit there looking like the press did nothing.
      .then(() => setCurrentJob({ status: "queued", result: QUEUED_SOON, blocked: false }))
      .then(() => respond({ ok: true }))
      .catch(refused("retry"));
    return true;
  }
  // The popup's "Open the page" button: the badge points at the popup, the
  // popup relays the owner's click here — the same owner-gesture path the
  // notification click takes.
  if (msg.type === "anticipy-open-handback" && msg.tabId != null) {
    openHandBack(msg.tabId).finally(() => respond({ ok: true }));
    return true;
  }
  // A pair code that can never be replaced is a dead end. Drop this install's
  // identity and run the same registration POST first install runs.
  if (msg.type === "anticipy-newcode") {
    chrome.storage.local.remove(["recordId", "pairCode", "agentId", "agentToken", "agentCredentialInstalled"])
      .then(() => ensureRegistered())
      .then((reg) => respond({ ok: !!reg }))
      .catch(() => respond({ ok: false }));
    return true;
  }
});

chrome.runtime.onInstalled.addListener((details) => {
  ensureWakeAlarms().catch(() => {});
  ensureRegistered();
  // First-run welcome: a guided setup page, not a paragraph in a README.
  if (details.reason === "install") {
    // FOCUS-OK(owner-install): installing the extension IS the owner's own
    // action — the pairing page is the one thing allowed to open focused.
    chrome.tabs.create({ url: chrome.runtime.getURL("onboarding.html"), active: true });
  }
});
chrome.runtime.onStartup.addListener(() => {
  // Top-level module evaluation normally does this too. Repeating the check on
  // the explicit browser-start event closes the lifecycle gap without risking
  // duplicate jobs: poll() has its own single-flight guard.
  ensureWakeAlarms().catch(() => {});
  poll();
  refreshBadge();
  reconcileCurrentJob();
});
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "anticipy-poll") poll();
  // A network blip during a beat is routine, not an error worth logging —
  // the next alarm retries anyway.
  if (a.name === "anticipy-heartbeat") heartbeat().catch(() => {});
});
// Also poll immediately on worker wake, and re-assert the badge — it is
// derived state, and a restarted browser comes up with it blank. The popup's
// job mirror is the same kind of derived state and comes up STALE instead of
// blank, so it gets read back off the row here too.
ensureWakeAlarms().catch(() => {});
poll();
refreshBadge();
reconcileCurrentJob();
