// Anticipy extension service worker.
// Polls the Anticipy backend (PocketBase) for action jobs and executes them in
// the user's own browser using their live logged-in sessions — browser-only,
// no service APIs. Irreversible steps stop at a prefilled page for the user
// (or the phone app) to confirm.

import { runAgentGoal } from "./agent_loop.js";

// Production backend; override via chrome.storage.local `backendUrl` for dev.
const DEFAULT_BASE = "https://backend-production-61e0a.up.railway.app";
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
async function writeHeaders() {
  const { serviceToken } = await chrome.storage.local.get(["serviceToken"]);
  const h = { "Content-Type": "application/json" };
  if (serviceToken) h["X-Anticipy-Token"] = serviceToken;
  return h;
}

const POLL_SECONDS = 5;
const HEARTBEAT_SECONDS = 10;
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

async function ensureRegistered() {
  let { agentId, recordId } = await chrome.storage.local.get(["agentId", "recordId"]);
  if (recordId) return { agentId, recordId };
  agentId = agentId || crypto.randomUUID();
  const pairCode = String(Math.floor(100000 + Math.random() * 900000));
  const r = await fetch(`${BASE}/api/collections/agents/records`, {
    method: "POST",
    headers: await writeHeaders(),
    body: JSON.stringify({
      agent_id: agentId,
      pair_code: pairCode,
      paired: false,
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
  await chrome.storage.local.set({ agentId, recordId: rec.id, pairCode });
  return { agentId, recordId: rec.id };
}

// Jobs this worker is actively running — their claims get refreshed on every
// heartbeat so the stale-requeue sweep never eats a live job.
const activeJobs = new Set();

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
  const complete = openrouterKey && agentModel !== undefined && serviceToken !== undefined;
  const fresh = Date.now() - (keyFetchedAt || 0) < 6 * 3600 * 1000;
  if (!force && complete && fresh) return openrouterKey;
  if (!agentId) return openrouterKey || null;
  try {
    const r = await fetch(`${BASE}/agent/key?agent_id=${encodeURIComponent(agentId)}`);
    // A refresh that fails must never LOSE a key we already hold — a stale
    // bundle plus one backend hiccup would otherwise fail every job with
    // "no LLM key" while a perfectly good key sits in storage.
    if (!r.ok) return openrouterKey || null;
    const { openrouter_key, model, vision_model, service_token, owner } = await r.json();
    if (openrouter_key) {
      await chrome.storage.local.set({
        openrouterKey: openrouter_key,
        agentModel: model || "",
        visionModel: vision_model || "",
        serviceToken: service_token || "",
        ownerProfile: owner || null,
        keyFetchedAt: Date.now(),
      });
      return openrouter_key;
    }
  } catch (_) { /* backend unreachable; keep whatever we already had */ }
  return openrouterKey || null;
}

async function heartbeat() {
  const reg = await ensureRegistered();
  if (!reg) return null;
  for (const id of activeJobs) {
    await updateJob(id, { claimed_at: new Date().toISOString() });
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
  await chrome.storage.local.set({ owner: rec.owner || "", paired: !!rec.paired });
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
  const { owner } = await chrome.storage.local.get(["owner"]);
  if (!owner) return;
  const filter = encodeURIComponent(`status="running" && owner="${owner}"`);
  const r = await fetch(`${BASE}/api/collections/jobs/records?filter=${filter}&perPage=20&sort=claimed_at`,
    { headers: await writeHeaders() });
  if (!r.ok) return;
  const { items } = await r.json();
  const now = Date.now();
  for (const j of items || []) {
    if (activeJobs.has(j.id)) continue; // this worker is running it right now
    const claimed = j.claimed_at ? Date.parse(j.claimed_at) : Date.parse(j.updated);
    if (now - claimed <= STALE_JOB_MS) continue;
    const tries = Number(j.attempts) || 0;
    if (tries >= MAX_ATTEMPTS) {
      // Say so once, plainly, and stop. Leaving it queued would mean the next
      // sweep picks it up again and we are back where we started.
      await updateJob(j.id, {
        status: "failed", claimed_by: "", claimed_at: null,
        result: `I tried this ${tries} times and could not get it done. I have stopped rather than keep going.`,
      });
      continue;
    }
    await updateJob(j.id, { status: "queued", claimed_by: "", claimed_at: null });
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
  // An UNPAIRED agent must not claim anything: it cannot fetch a key, so it
  // would claim the job and then fail it forever — a second Chrome profile
  // silently killing the owner's work.
  if (!owner) return null;
  // A PAIRED agent still takes unowned jobs: if the brain ever queues one
  // without an owner stamp, dropping this clause would leave it queued
  // forever with nothing reporting a problem. Silent dead-queue is worse
  // than the narrow case this clause admits.
  // The research lane is NOT ours: read-only goals run server-side in the
  // worker (roadmap §6) — his browser is only for work that needs his
  // logged-in sessions. The backend's research_lane hook enforces the same
  // exclusion for extensions older than this line.
  const cond = `status="queued" && (owner="${owner}" || owner="") && lane!="research"`;
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
      status: "needs_user",
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
      status: "failed", claimed_by: "", claimed_at: null,
      result: `I tried this ${tries - 1} times and could not get it done. I have stopped rather than keep going.`,
    });
    return null;
  }
  await updateJob(job.id, { status: "running", claimed_by: me, attempts: tries, claimed_at: new Date().toISOString() });
  const check = await fetch(`${BASE}/api/collections/jobs/records/${job.id}`,
    { headers: await writeHeaders() });
  if (!check.ok) return null;
  const fresh = await check.json();
  if (fresh.claimed_by !== me || fresh.status !== "running") return null;
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

async function updateJob(id, fields) {
  const r = await fetch(`${BASE}/api/collections/jobs/records/${id}`, {
    method: "PATCH",
    headers: await writeHeaders(),
    body: JSON.stringify(fields),
  });
  // A silently-swallowed write meant a job deleted server-side ran to
  // completion while every status update vanished into the void.
  if (!r.ok) {
    if (r.status === 404) { activeJobs.delete(id); throw new Error("job gone"); }
    console.warn(`Anticipy: job ${id} update failed (${r.status})`);
  }
  return r;
}

/// Is this job still ours to run? The owner can cancel from the app or by
/// text while the loop is mid-flight; without this the run continued and
/// then RESURRECTED the cancelled job as done/failed.
async function jobStillLive(id) {
  try {
    const r = await fetch(`${BASE}/api/collections/jobs/records/${id}`,
      { headers: await writeHeaders() });
    if (r.status === 404) return false;
    if (!r.ok) return true;   // transient: don't abandon real work
    const j = await r.json();
    return j.status === "running" || j.status === "queued";
  } catch (_) {
    return true;
  }
}

async function runJob(job) {
  const params = job.params ? JSON.parse(job.params) : {};
  activeJobs.add(job.id);
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

  if (job.goal === "agent_goal") {
    // Autonomous mode: LLM click-loop via chrome.debugger in a background
    // Anticipy tab group (same mechanics as Claude in Chrome / Codex).
    const openrouterKey = await ensureLLMKey();
    if (!openrouterKey) {
      await updateJob(job.id, { status: "failed", result: "no LLM key: not paired yet, or the backend has none configured" });
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
        const pr = await fetch(`${BASE}/agent/key?agent_id=${encodeURIComponent(myId || "")}`);
        if (pr.ok) {
          const fresh = (await pr.json()).owner;
          if (fresh) { ownerProfile = fresh; await chrome.storage.local.set({ ownerProfile: fresh }); }
        }
      } catch (_) { /* keep what we had */ }
      const out = await runAgentGoal(params.task, {
        apiKey: openrouterKey,
        startUrl: params.start_url || undefined,
        stillLive: () => jobStillLive(job.id),
        ...(agentModel ? { model: agentModel } : {}),
        ...(visionModel ? { visionModel } : {}),
        ownerProfile,
        // The owner already said yes in the app or by text; the gate lives
        // in the job queue, so the browser must not ask a second time.
        authorized: params.authorized === true,
        // Exactly what the owner agreed to, in their own words plus what
        // she told them — the only thing an action is measured against.
        scope: params.approved_scope || params.say || params.source || "",
        // Every concrete detail already on the job record (time, party size,
        // an address, an answer he texted) — so the agent SETS them instead
        // of asking for them. Bookkeeping keys are not facts.
        facts: Object.entries(params)
          .filter(([k, v]) => !["source", "say", "now", "lane", "missing",
                                "authorized", "approved_scope", "needed",
                                "start_url", "task", "assumption", "note"].includes(k)
                              && (typeof v === "string" || typeof v === "number")
                              && String(v).length < 200)
          .map(([k, v]) => `  ${k.replace(/_/g, " ")}: ${v}`).join("\n"),
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
      // §9: a kept-back tab never surfaces itself — badge + notification, and
      // the owner's click is what focuses it (openHandBack). Surfaced before
      // the job write so a deleted job row can't strand a hidden tab.
      if (status === "needs_user" && out.tabId != null) {
        await surfaceHandBack(out.tabId, out.result, "needs_user");
      }
      await updateJob(job.id, { status, result: out.result });
      // The job row keeps needs_user (the phone offers Try again on it), but
      // in Chrome the honest word for "you cancelled the debugging bar" is
      // stopped, not "I need you".
      await setCurrentJob({ status: out.stoppedInChrome ? "stopped" : status, result: out.result || "" });
    } catch (e) {
      if (String(e).includes("job gone")) throw e;
      await updateJob(job.id, { status: "failed", result: String(e) });
      await setCurrentJob({ status: "failed", result: "Something went wrong partway through. Nothing was sent." });
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
    await setCurrentJob({ status: "done", result: `The site said: ${banner.trim().split("\n")[0]}` });
    // Nothing for a human to look at — close it. Leaving working tabs open is
    // how fifty of them piled up in the owner's window.
    try { await chrome.tabs.remove(tab.id); } catch (e) { /* gone */ }
  } else {
    // Prefill flows: the page IS the thing the owner acts on, so it stays —
    // but in the background (§9), never surfacing itself. The badge and
    // notification are how they find it; their click is what opens it.
    await surfaceHandBack(tab.id, jobLine(job, params), "confirm");
    await updateJob(job.id, { status: "awaiting_confirm", result: `opened ${job.goal} page in tab ${tab.id}` });
    await setCurrentJob({ status: "awaiting_confirm", result: "It's filled in and waiting quietly in my tab group — click my notification (or Open below) to see it." });
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
        headers: await writeHeaders(),
        body: JSON.stringify({ clientId, subscriptions: ["jobs"] }),
      });
    });
    es.addEventListener("jobs", () => poll());
    es.onerror = () => { es.close(); realtimeOpen = false; };
  } catch (e) {
    realtimeOpen = false;
  }
}

// The popup's two controls. Both go through updateJob — the same write path
// every other status change uses — so nothing here is a second source of
// truth: a stop lands on the job row, and the running loop's own jobStillLive
// check picks it up within a poll and stops where it is.
chrome.runtime.onMessage.addListener((msg, _sender, respond) => {
  if (!msg || !msg.type) return;
  if (msg.type === "anticipy-stop" && msg.id) {
    updateJob(msg.id, { status: "cancelled", result: "you stopped this from Chrome" })
      .then(() => setCurrentJob({ status: "stopped", result: "You stopped this. Nothing more was done." }))
      .catch(() => {})
      .finally(() => respond({ ok: true }));
    return true;
  }
  if (msg.type === "anticipy-again" && msg.id) {
    updateJob(msg.id, { status: "queued", claimed_by: "", claimed_at: null })
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
    chrome.storage.local.remove(["recordId", "pairCode", "agentId"])
      .then(() => ensureRegistered())
      .then((reg) => respond({ ok: !!reg }))
      .catch(() => respond({ ok: false }));
    return true;
  }
});

chrome.runtime.onInstalled.addListener((details) => {
  chrome.alarms.create("anticipy-poll", { periodInMinutes: POLL_SECONDS / 60 });
  chrome.alarms.create("anticipy-heartbeat", { periodInMinutes: HEARTBEAT_SECONDS / 60 });
  ensureRegistered();
  // First-run welcome: a guided setup page, not a paragraph in a README.
  if (details.reason === "install") {
    // FOCUS-OK(owner-install): installing the extension IS the owner's own
    // action — the pairing page is the one thing allowed to open focused.
    chrome.tabs.create({ url: chrome.runtime.getURL("onboarding.html"), active: true });
  }
});
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "anticipy-poll") { poll(); openRealtime(); }
  if (a.name === "anticipy-heartbeat") heartbeat();
});
// Also poll immediately on worker wake, and re-assert the badge — it is
// derived state, and a restarted browser comes up with it blank.
poll();
openRealtime();
refreshBadge();
