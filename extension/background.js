// Anticipy extension service worker.
// Polls the Anticipy backend (PocketBase) for action jobs and executes them in
// the user's own browser using their live logged-in sessions — browser-only,
// no service APIs. Irreversible steps stop at a prefilled page for the user
// (or the phone app) to confirm.

import { runAgentGoal } from "./agent_loop.js";

const BASE = "http://127.0.0.1:8090"; // dev; production points at the hosted backend
const POLL_SECONDS = 5;
const HEARTBEAT_SECONDS = 10;
const STALE_JOB_MS = 2 * 60 * 1000; // running w/ no heartbeat -> requeued

// ---------------------------------------------------------------- pairing
// Each install registers itself once with a 6-digit pair code. The phone app
// claims the code and writes `owner`; from then on this agent only takes
// that owner's jobs and reports a heartbeat the app turns into "last seen Ns".

async function ensureRegistered() {
  let { agentId, recordId } = await chrome.storage.local.get(["agentId", "recordId"]);
  if (recordId) return { agentId, recordId };
  agentId = agentId || crypto.randomUUID();
  const pairCode = String(Math.floor(100000 + Math.random() * 900000));
  const r = await fetch(`${BASE}/api/collections/agents/records`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      pair_code: pairCode,
      paired: false,
      browser: navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] || "Chrome",
      last_seen: new Date().toISOString(),
    }),
  });
  if (!r.ok) return null;
  const rec = await r.json();
  await chrome.storage.local.set({ agentId, recordId: rec.id, pairCode });
  return { agentId, recordId: rec.id };
}

// Jobs this worker is actively running — their claims get refreshed on every
// heartbeat so the stale-requeue sweep never eats a live job.
const activeJobs = new Set();

async function heartbeat() {
  const reg = await ensureRegistered();
  if (!reg) return null;
  for (const id of activeJobs) {
    await updateJob(id, { claimed_at: new Date().toISOString() });
  }
  const r = await fetch(`${BASE}/api/collections/agents/records/${reg.recordId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ last_seen: new Date().toISOString() }),
  });
  if (!r.ok) return null;
  const rec = await r.json();
  await chrome.storage.local.set({ owner: rec.owner || "", paired: !!rec.paired });
  return rec;
}

// If a previous worker died mid-job, its `running` jobs go stale; requeue them
// so no task is ever silently lost to a crash or a closed Chrome.
async function requeueStaleJobs() {
  const filter = encodeURIComponent('status="running"');
  const r = await fetch(`${BASE}/api/collections/jobs/records?filter=${filter}&perPage=20`);
  if (!r.ok) return;
  const { items } = await r.json();
  const now = Date.now();
  for (const j of items || []) {
    if (activeJobs.has(j.id)) continue; // this worker is running it right now
    const claimed = j.claimed_at ? Date.parse(j.claimed_at) : Date.parse(j.updated);
    if (now - claimed > STALE_JOB_MS) {
      await updateJob(j.id, { status: "queued", claimed_by: "", claimed_at: null });
    }
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
    `&details=${encodeURIComponent(p.details || "Scheduled by Anticipy")}`,
  research_and_report: (p) =>
    p.url || `https://www.google.com/search?q=${encodeURIComponent(p.query || "")}`,
  form_submit_demo: () => "https://the-internet.herokuapp.com/login",
};

async function claimJob() {
  // Owner-scoped: a paired agent takes its owner's jobs (or legacy unowned
  // ones); an unpaired agent only takes unowned jobs.
  const { owner, agentId } = await chrome.storage.local.get(["owner", "agentId"]);
  const cond = owner
    ? `status="queued" && (owner="${owner}" || owner="")`
    : 'status="queued" && owner=""';
  const r = await fetch(
    `${BASE}/api/collections/jobs/records?filter=${encodeURIComponent(cond)}&perPage=1&sort=created`
  );
  if (!r.ok) return null;
  const items = (await r.json()).items;
  if (!items || !items.length) return null;
  const job = items[0];
  if (activeJobs.has(job.id)) return null;
  // Stamp the claim, then read it back: whoever's stamp survives owns the job.
  // This closes the race where concurrent poll() calls (SSE + alarm + worker
  // wake) would each spawn an agent loop for the same job.
  const me = agentId || "unknown";
  await updateJob(job.id, { status: "running", claimed_by: me, claimed_at: new Date().toISOString() });
  const check = await fetch(`${BASE}/api/collections/jobs/records/${job.id}`);
  if (!check.ok) return null;
  const fresh = await check.json();
  if (fresh.claimed_by !== me || fresh.status !== "running") return null;
  return fresh;
}

async function updateJob(id, fields) {
  await fetch(`${BASE}/api/collections/jobs/records/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
}

async function runJob(job) {
  const params = job.params ? JSON.parse(job.params) : {};
  activeJobs.add(job.id);
  try {
    await runJobInner(job, params);
  } finally {
    activeJobs.delete(job.id);
  }
}

async function runJobInner(job, params) {

  if (job.goal === "agent_goal") {
    // Autonomous mode: LLM click-loop via chrome.debugger in a background
    // Anticipy tab group (same mechanics as Claude in Chrome / Codex).
    const { openrouterKey } = await chrome.storage.local.get("openrouterKey");
    if (!openrouterKey) {
      await updateJob(job.id, { status: "failed", result: "no OpenRouter key in extension storage" });
      return;
    }
    try {
      const out = await runAgentGoal(params.task, {
        apiKey: openrouterKey,
        startUrl: params.start_url || undefined,
      });
      // needs_user (login wall, CAPTCHA, refused site) is NOT the same state
      // as awaiting_confirm (owner go-ahead pending) — conflating them lets a
      // free-form "yes" re-release a stuck job instead of the intended one.
      const status = out.status === "done" ? "done"
        : out.status === "needs_user" ? "needs_user" : "failed";
      await updateJob(job.id, { status, result: out.result });
    } catch (e) {
      await updateJob(job.id, { status: "failed", result: String(e) });
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
  const tab = await chrome.tabs.create({ url: build(params), active: false });
  try {
    const group = await chrome.tabs.group({ tabIds: tab.id });
    await chrome.tabGroups.update(group, { title: "Anticipy", color: "yellow", collapsed: true });
  } catch (e) {
    // tab groups unavailable (e.g. incognito) — continue in a plain background tab
  }

  if (job.goal === "form_submit_demo") {
    // Demonstrates in-page acting: fill and submit a real form, read the result.
    await new Promise((res) => setTimeout(res, 3000));
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        document.querySelector("#username").value = "tomsmith";
        document.querySelector("#password").value = "SuperSecretPassword!";
        document.querySelector("button[type=submit]").click();
        return "submitted";
      },
    });
    await new Promise((res) => setTimeout(res, 2500));
    const [{ result: banner }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => (document.querySelector("#flash") || {}).innerText || "no banner",
    });
    await updateJob(job.id, { status: "done", result: `form ${result}; site said: ${banner.trim().split("\n")[0]}` });
  } else {
    // Prefill flows: page is opened ready for the final human confirm.
    await updateJob(job.id, { status: "awaiting_confirm", result: `opened ${job.goal} page in tab ${tab.id}` });
  }
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
    // backend not reachable; try again on next alarm
  } finally {
    pollInFlight = false;
  }
}

// Realtime push: subscribe to job creations over PocketBase SSE so new work
// starts in ~0s instead of on the next poll. Alarms remain as the safety net
// (MV3 service workers sleep; the alarm re-fires poll and re-opens the stream).
let realtimeOpen = false;
async function openRealtime() {
  if (realtimeOpen) return;
  realtimeOpen = true;
  try {
    const es = new EventSource(`${BASE}/api/realtime`);
    let clientId = null;
    es.addEventListener("PB_CONNECT", async (e) => {
      clientId = JSON.parse(e.data).clientId;
      await fetch(`${BASE}/api/realtime`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId, subscriptions: ["jobs"] }),
      });
    });
    es.addEventListener("jobs", () => poll());
    es.onerror = () => { es.close(); realtimeOpen = false; };
  } catch (e) {
    realtimeOpen = false;
  }
}

chrome.runtime.onInstalled.addListener((details) => {
  chrome.alarms.create("anticipy-poll", { periodInMinutes: POLL_SECONDS / 60 });
  chrome.alarms.create("anticipy-heartbeat", { periodInMinutes: HEARTBEAT_SECONDS / 60 });
  ensureRegistered();
  // First-run welcome: a guided setup page, not a paragraph in a README.
  if (details.reason === "install") {
    chrome.tabs.create({ url: chrome.runtime.getURL("onboarding.html") });
  }
});
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "anticipy-poll") { poll(); openRealtime(); }
  if (a.name === "anticipy-heartbeat") heartbeat();
});
// Also poll immediately on worker wake.
poll();
openRealtime();
