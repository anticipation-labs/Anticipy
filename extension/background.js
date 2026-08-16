// Anticipy extension service worker.
// Polls the Anticipy backend (PocketBase) for action jobs and executes them in
// the user's own browser using their live logged-in sessions — browser-only,
// no service APIs. Irreversible steps stop at a prefilled page for the user
// (or the phone app) to confirm.

import { createBackgroundTab, runAgentGoal } from "./agent_loop.js";
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
const ENGINE_BUILD = "0.7.1";

// Production backend; override via chrome.storage.local `backendUrl` for dev.
const DEFAULT_BASE = "https://backend-production-61e0a.up.railway.app";
const BACKEND_LLM = "backend-proxy";
let BASE = DEFAULT_BASE;
chrome.storage.local.get("backendUrl").then(({ backendUrl }) => {
  if (backendUrl) BASE = backendUrl.replace(/\/$/, "");
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.backendUrl) {
    BASE = (changes.backendUrl.newValue || DEFAULT_BASE).replace(/\/$/, "");
  }
});
// Every write carries the service token when the backend has one; the guard
// hook ignores it until enforcement is switched on, so this is safe to ship
// ahead of the flip.
async function writeHeaders(leaseToken = "") {
  const { serviceToken, agentId, agentToken } = await chrome.storage.local.get(
    ["serviceToken", "agentId", "agentToken"]);
  const h = { "Content-Type": "application/json" };
  // serviceToken is read only for the one-release migration that lets an
  // already-paired install add its private credential. /agent/key clears it;
  // normal job traffic authenticates as this one agent, never as the server.
  if (serviceToken) h["X-Anticipy-Token"] = serviceToken;
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
    // Existing installs predate per-agent credentials. Their cached service
    // token authorizes this one migration write; the next key fetch erases it.
    const r = await fetch(`${BASE}/agent/upgrade-credential`, {
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
  const r = await fetch(`${BASE}/agent/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      // The extension version rides along in this existing field so nobody has
      // to guess which build is actually installed. An unpacked extension does
      // not auto-update, so "did you reload it?" has been unanswerable — and it
      // is the single most common cause of the browser arm being dead.
      browser: `${navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] || "Chrome"} ext/${chrome.runtime.getManifest().version}`,
      last_seen: new Date().toISOString(),
    }),
  });
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

// ------------------------------------------------------------- LLM key
// Consumers never paste API keys: once paired, the agent fetches its key from
// the backend. A manually saved key (popup) still wins, so dev overrides work.
async function ensureLLMKey(force = false) {
  const { openrouterKey, agentModel, serviceToken, keyFetchedAt, agentId } =
    await chrome.storage.local.get(["openrouterKey", "agentModel", "serviceToken", "keyFetchedAt", "agentId"]);
  // Refresh when ANY piece is missing or the bundle is stale — not just the
  // key. An install that cached only a key would otherwise never learn the
  // service token, and switching backend enforcement on would permanently
  // brick it with no way back except a manual reinstall.
  const complete = openrouterKey === BACKEND_LLM
    && agentModel !== undefined && serviceToken !== undefined;
  const fresh = Date.now() - (keyFetchedAt || 0) < 6 * 3600 * 1000;
  if (!force && complete && fresh) return openrouterKey;
  if (!agentId) return complete ? openrouterKey : null;
  try {
    const r = await fetch(`${BASE}/agent/key?agent_id=${encodeURIComponent(agentId)}`,
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
        // The server no longer returns its master credential. Saving an empty
        // value also erases the migration token on upgraded installations.
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
    try {
      const until = new Date(Date.now() + LEASE_MS);
      const patch = isWorkflowJob(active.job)
        ? heartbeatPatch(active.job, { leaseToken: active.leaseToken, leaseUntil: until })
        : { claimed_at: new Date().toISOString() };
      active.job = await updateJob(id, patch, active.leaseToken);
    } catch (e) {
      console.warn(`Anticipy: could not renew lease for ${id}: ${String(e).slice(0, 160)}`);
    }
  }
  const r = await fetch(`${BASE}/api/collections/agents/records/${reg.recordId}`, {
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
  const filter = encodeURIComponent(`status="running" && owner_ref="${ownerRef}" && workflow_id!=""`);
  const r = await fetch(`${BASE}/api/collections/jobs/records?filter=${filter}&perPage=20&sort=claimed_at`,
    { headers: await writeHeaders() });
  if (!r.ok) return;
  const { items } = await r.json();
  const now = Date.now();
  for (const j of items || []) {
    if (activeJobs.has(j.id)) continue; // this worker is running it right now
    const expires = j.lease_until ? Date.parse(j.lease_until) : 0;
    const claimed = j.claimed_at ? Date.parse(j.claimed_at) : Date.parse(j.updated);
    if (expires ? now <= expires : now - claimed <= STALE_JOB_MS) continue;
    const tries = Number(j.attempts) || 0;
    if (isWorkflowJob(j) && j.effect_uncertain) {
      await updateJob(j.id, workflowPatch(j, "needs_user", {
        reason: "The browser stopped after a possible external action. Check the site before trying again.",
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
  }
}

// Browser-only action templates: everything is a real website the user could
// have opened themselves. Gmail compose and Calendar templates prefill via URL.
const ACTIONS = {
  draft_and_send_document: (p) =>
    `https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(p.to || "")}` +
    `&su=${encodeURIComponent(p.subject || "Following up")}` +
    `&body=${encodeURIComponent(p.body || "")}`,
  create_calendar_event: (p) =>
    `https://calendar.google.com/calendar/render?action=TEMPLATE` +
    `&text=${encodeURIComponent(p.title || "Meeting")}` +
    `&dates=${encodeURIComponent(p.dates || "")}` +
    `&details=${encodeURIComponent(p.details || "Scheduled by Anticipy Claude Version")}`,
  research_and_report: (p) =>
    p.url || `https://www.google.com/search?q=${encodeURIComponent(p.query || "")}`,
};

async function claimJob() {
  // Owner-scoped: a paired agent takes its owner's jobs (or legacy unowned
  // ones); an unpaired agent only takes unowned jobs.
  const { ownerRef, agentId } = await chrome.storage.local.get(["ownerRef", "agentId"]);
  // An UNPAIRED agent must not claim anything: it cannot fetch a key, so it
  // would claim the job and then fail it forever — a second Chrome profile
  // silently killing the owner's work.
  if (!ownerRef) return null;
  // The research lane is NOT ours: read-only goals run server-side in the
  // worker (roadmap §6) — his browser is only for work that needs his
  // logged-in sessions. The backend's research_lane hook enforces the same
  // exclusion for extensions older than this line.
  const cond = `status="queued" && owner_ref="${ownerRef}" && workflow_id!="" && lane!="research"`;
  const poll = async () => fetch(
    `${BASE}/api/collections/jobs/records?filter=${encodeURIComponent(cond)}&perPage=1&sort=created`,
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
      return null;
    }
  }
  if (!r.ok) return null;
  const items = (await r.json()).items;
  if (!items || !items.length) return null;
  const job = items[0];
  if (activeJobs.has(job.id)) return null;
  if (!isWorkflowJob(job)) {
    console.warn(`Anticipy: refusing job ${job.id} without canonical workflow metadata`);
    return null;
  }
  // Nothing executes while Chrome is shut, so a job can sit for days. Opening
  // the laptop on Monday should NOT silently fire Friday's errand — the world
  // has moved on. Hand it back and let the owner say whether it still stands.
  //
  // Measured from when it was last QUEUED, not from when the row was created.
  // `created` is immutable in PocketBase, so reading it meant a task that had
  // merely EXISTED for 12 hours was bounced — including one the owner had just
  // this second unblocked by answering. His Cactus booking was created 21h
  // before he supplied his details; every resume would have been refused,
  // forever, while she had already told him "I'll finish the booking now".
  // `updated` is refreshed by the requeue that sets status back to "queued",
  // so a fresh resume reads as fresh and a genuinely abandoned errand does not.
  const STALE_HOURS = 12;
  const queuedAt = Date.parse(job.updated || job.created || "");
  if (queuedAt && Date.now() - queuedAt > STALE_HOURS * 3600 * 1000) {
    const hrs = Math.round((Date.now() - queuedAt) / 3600000);
    // Say only what is observable. The previous wording asserted "my browser
    // was closed" — written by the browser, while running, at the moment it
    // wrote it. And it OVERWROTE `result`, destroying the requirement text
    // ("I need your first name, last name, email…") that the brain matches an
    // answer against, so the task could never be resumed by answering again.
    const had = (job.result || "").trim();
    await updateJob(job.id, {
      ...workflowPatch(job, "needs_user", {
        reason: `Still queued after ${hrs} hours without running. Does it still stand?`,
      }),
      result: (had ? had + "\n\n" : "") +
        `Still queued after ${hrs} hours without running. Does it still stand?`,
    });
    return null;
  }
  // Stamp the claim, then read it back: whoever's stamp survives owns the job.
  // This closes the race where concurrent poll() calls (SSE + alarm + worker
  // wake) would each spawn an agent loop for the same job.
  const me = agentId || "unknown";
  // Counted at the claim, which is the only place that means "started".
  // Counting on failure would miss the case that actually bit: a job that
  // never reaches an ending at all and is swept back to queued forever.
  const tries = (Number(job.attempts) || 0) + 1;
  if (tries > MAX_ATTEMPTS) {
    await updateJob(job.id, {
      ...workflowPatch(job, "cancelled", {
        reason: `stopped after ${tries - 1} attempts`,
      }),
      result: `I tried this ${tries - 1} times and could not get it done. I have stopped rather than keep going.`,
    });
    return null;
  }
  const leaseToken = crypto.randomUUID();
  const fresh = await updateJob(job.id, workflowPatch(job, "running", {
    actorId: me,
    leaseToken,
    leaseUntil: new Date(Date.now() + LEASE_MS),
    attempt: tries,
  }));
  if (fresh.claimed_by !== me || fresh.status !== "running" || fresh.lease_token !== leaseToken) return null;
  return fresh;
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
      title: "Anticipy Claude Version",
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
  const r = await fetch(`${BASE}/api/collections/jobs/records/${id}`,
    { headers: await writeHeaders() });
  if (r.status === 404) throw new Error("job gone");
  if (!r.ok) throw new Error(`job read failed (${r.status})`);
  return r.json();
}

async function updateJob(id, fields, leaseToken = "") {
  const r = await fetch(`${BASE}/api/collections/jobs/records/${id}`, {
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
    const r = await fetch(`${BASE}/api/collections/jobs/records/${id}`,
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

async function runJob(job) {
  const params = parseJobParams(job);
  activeJobs.set(job.id, { job, leaseToken: job.lease_token || "" });
  await setCurrentJob({ id: job.id, status: "running", doing: jobLine(job, params), result: "" });
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
  }
}

async function runJobInner(job, params) {

  // Canonical plans all use the same adaptive browser executor.  The old
  // ACTIONS table remains only for draining pre-workflow rows; a production
  // plan must not bypass verification merely because its goal string happens
  // to match a historical template.
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
        const pr = await fetch(`${BASE}/agent/key?agent_id=${encodeURIComponent(myId || "")}`,
          { headers: await writeHeaders() });
        if (pr.ok) {
          const fresh = (await pr.json()).owner;
          if (fresh) { ownerProfile = fresh; await chrome.storage.local.set({ ownerProfile: fresh }); }
        }
      } catch (_) { /* keep what we had */ }
      const out = await runAgentGoal(params.task, {
        apiKey: openrouterKey,
        startUrl: params.start_url || undefined,
        // A resumed job goes back to its own parked tab — session, filled
        // form and all — instead of starting the world over in a fresh one.
        resumeTabId: params.resume_tab != null ? params.resume_tab : null,
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
        facts: (params._workflow?.facts && typeof params._workflow.facts === "object")
          ? Object.fromEntries(Object.entries(params._workflow.facts)
              .filter(([k]) => !/^owner_answer/i.test(k)))
          : Object.fromEntries(Object.entries(params)
              .filter(([k, v]) => !["source", "say", "now", "lane", "missing",
                                    "authorized", "approved_scope", "needed",
                                    "start_url", "task", "assumption", "note",
                                    "resume_tab"].includes(k)
                                  && !/^owner_answer/i.test(k)
                                  && (typeof v === "string" || typeof v === "number"
                                      || typeof v === "boolean")
                                  && String(v).length < 200)),
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
            job = await updateJob(job.id,
              { trace, ...(journal.length ? {
                params: JSON.stringify(params),
              } : {}) }, job.lease_token);
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
        await setCurrentJob({ status: "stopped", result: out.result || "you called this off — I stopped where I was." });
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
        ? "The browser stopped after a possible external action. Check the site before trying again."
        : (out.result || "");
      // §9: a kept-back tab never surfaces itself — badge + notification, and
      // the owner's click is what focuses it (openHandBack). Surfaced before
      // the job write so a deleted job row can't strand a hidden tab.
      if (canonicalState === "needs_user" && out.tabId != null) {
        await surfaceHandBack(out.tabId, result, "needs_user");
      }
      const transition = isWorkflowJob(job)
        ? workflowPatch(job, canonicalState, {
            reason: result || (canonicalState === "failed"
              ? "browser execution failed" : "the browser needs the owner"),
            effectUncertain: !!job.effect_uncertain,
            ...(out.tabId != null && canonicalState === "needs_user"
              ? { paramsPatch: { resume_tab: out.tabId } } : {}),
            ...(canonicalState === "succeeded" ? {
              summary: result || "completed",
              verified: out.receipt?.verified === true,
              evidence: out.receipt?.evidence || [],
            } : {}),
          })
        : {
            status, result,
            ...(out.tabId != null && status === "needs_user"
              ? { params: JSON.stringify({ ...params, resume_tab: out.tabId }) } : {}),
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
        ? "The browser stopped after a possible external action. Check the site before trying again."
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

  const build = ACTIONS[job.goal];
  if (!build) {
    // Free-form goal from the brain: run it autonomously, same as agent_goal.
    const task = params.source ? `${job.goal} (context: heard "${params.source}")` : job.goal;
    return runJobInner({ ...job, goal: "agent_goal" }, { ...params, task });
  }
  // Work quietly: background tab inside a collapsed "Anticipy" tab group,
  // same as the agent_goal path — never steals the user's focus.
  const tab = await createBackgroundTab(build(params));
  try {
    const group = await chrome.tabs.group({ tabIds: tab.id });
    await chrome.tabGroups.update(group, { title: "Anticipy Claude Version", color: "yellow", collapsed: true });
  } catch (e) {
    // tab groups unavailable (e.g. incognito) — continue in a plain background tab
  }

  // Prefill flows: the page IS the thing the owner acts on, so it stays —
  // but in the background (§9), never surfacing itself. The badge and
  // notification are how they find it; their click is what opens it.
  await surfaceHandBack(tab.id, jobLine(job, params), "confirm");
  await updateJob(job.id, { status: "awaiting_confirm", result: `opened ${job.goal} page in tab ${tab.id}` });
  await setCurrentJob({ status: "awaiting_confirm", result: "It's filled in and waiting quietly in my tab group — click my notification (or Open below) to see it." });
}

// Only one poll cycle at a time — SSE events, alarms, and worker wake can all
// fire poll() concurrently, and overlapping cycles double-claim jobs.
let pollInFlight = false;
async function poll() {
  if (pollInFlight) return;
  pollInFlight = true;
  try {
    await heartbeat();
    await requeueStaleJobs();
    const job = await claimJob();
    if (job) await runJob(job);
  } catch (e) {
    // Keep polling on the next alarm, but never again silently: this catch
    // swallowed 23 consecutive claim-path 409s in one live run while the
    // heartbeat kept the phone showing "Chrome ready". A dead pipe must be
    // loud in the worker console even when it cannot be fatal.
    console.warn(`Anticipy: poll cycle failed: ${String(e).slice(0, 300)}`);
  } finally {
    pollInFlight = false;
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
    await chrome.alarms.create(name, {
      delayInMinutes: WAKE_PERIOD_MINUTES,
      periodInMinutes: WAKE_PERIOD_MINUTES,
      persistAcrossSessions: true,
    });
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
  return updateJob(id, workflowPatch(job, "queued", {
    reason: "the owner asked Chrome to try this approved version again",
    effectUncertain: false,
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
  if (msg.type === "anticipy-stop" && msg.id) {
    stopJob(msg.id)
      .then(() => setCurrentJob({ status: "stopped", result: "You stopped this. Nothing more was done." }))
      .catch(() => {})
      .finally(() => respond({ ok: true }));
    return true;
  }
  if (msg.type === "anticipy-again" && msg.id) {
    retryJob(msg.id)
      .then(() => setCurrentJob({ status: "queued", result: "" }))
      .catch(() => {})
      .finally(() => respond({ ok: true }));
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
});
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "anticipy-poll") poll();
  // A network blip during a beat is routine, not an error worth logging —
  // the next alarm retries anyway.
  if (a.name === "anticipy-heartbeat") heartbeat().catch(() => {});
});
// Also poll immediately on worker wake, and re-assert the badge — it is
// derived state, and a restarted browser comes up with it blank.
ensureWakeAlarms().catch(() => {});
poll();
refreshBadge();
