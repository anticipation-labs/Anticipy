// The popup is Anticipy's only face on the machine the work actually happens
// on, so it has to answer three questions: can I reach her, is this browser
// hers yet, and what is she doing right now — with a way to stop it.

// Same base the service worker resolves: an override in storage, otherwise
// production. This used to be a hardcoded local PocketBase, so every real
// user was told "Not connected" forever while pairing and jobs worked fine.
const DEFAULT_BASE = "https://backend-production-61e0a.up.railway.app";

const el = (id) => document.getElementById(id);
const show = (id, on) => el(id).toggleAttribute("hidden", !on);

// Only write when the words actually change: a live region that is rewritten
// with identical text on a timer makes a screen reader repeat itself.
function say(id, text) {
  const node = el(id);
  if (node.textContent.trim() !== text) node.textContent = text;
}

async function base() {
  const { backendUrl } = await chrome.storage.local.get(["backendUrl"]);
  return (backendUrl || DEFAULT_BASE).replace(/\/$/, "");
}

async function checkConnection() {
  try {
    const r = await fetch(`${await base()}/api/health`);
    if (!r.ok) throw new Error("unhealthy");
    say("status", "I'm connected and watching for work.");
    el("dot").classList.add("on");
  } catch (e) {
    say("status", "I can't reach Anticipy Codex Version from this browser right now. If you're online, this usually clears by itself in a minute.");
    el("dot").classList.remove("on");
  }
}

function renderPairing({ pairCode, paired }) {
  show("pairedline", !!paired);
  show("pairbox", !paired && !!pairCode);
  if (!paired && pairCode) el("paircode").textContent = pairCode;
}

// What she's doing, mirrored into storage by the worker as each job moves.
const CURRENT = new Set(["running", "queued", "awaiting_confirm"]);
const STOPPABLE = new Set(["running", "queued"]);
// A job waiting on the owner's OK must not be offered "again" — that would
// queue a second copy of something already sitting there prefilled.
const RETRYABLE = new Set(["failed", "needs_user", "stopped"]);
function renderJob(job) {
  if (!job || !job.status) { show("jobbox", false); return; }
  show("jobbox", true);
  const doing = job.doing || "a task";
  el("jobhead").textContent = CURRENT.has(job.status) ? "Right now" : "Last task";

  const lines = {
    running: `Working on this: ${doing}`,
    queued: `Picking this up: ${doing}`,
    awaiting_confirm: `Ready for your OK on your phone: ${doing}`,
    needs_user: `I stopped and I need you: ${doing}`,
    done: `Done: ${doing}`,
    failed: `This didn't work: ${doing}`,
    stopped: `Stopped: ${doing}`,
    removed: `Called off: ${doing}`,
  };
  say("jobdoing", lines[job.status] || `${doing}`);

  const result = (job.result || "").trim();
  show("jobresult", !!result);
  if (result) el("jobresult").textContent = result;

  show("why", job.status === "running");
  show("stop", !!job.id && STOPPABLE.has(job.status));
  show("again", !!job.id && RETRYABLE.has(job.status));
}

// A kept-back tab (a login wall, a page waiting on their OK) never surfaces
// itself — the badge points here, and THIS button is the owner's click that
// opens it. The worker does the focusing so notification and popup share one
// path.
let handBackTab = null;
function renderHandBacks(handBacks) {
  const ids = Object.keys(handBacks || {})
    .sort((a, b) => (handBacks[a].at || 0) - (handBacks[b].at || 0));
  handBackTab = ids.length ? ids[ids.length - 1] : null;
  show("openhb", !!handBackTab);
}

async function refresh() {
  const { pairCode, paired, currentJob, handBacks } = await chrome.storage.local.get(["pairCode", "paired", "currentJob", "handBacks"]);
  renderPairing({ pairCode, paired });
  renderJob(currentJob);
  renderHandBacks(handBacks);
}

el("paircode").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el("paircode").textContent.trim());
    say("copyhint", "Copied. Now type it into the app.");
  } catch (e) {
    say("copyhint", "I couldn't copy it — read it off the screen instead.");
  }
});

// Stop and start-again both go through the worker, which writes the job row
// the same way every other status change does. The running loop checks that
// row as it works, so it stops within a few seconds.
async function tell(type) {
  const { currentJob } = await chrome.storage.local.get(["currentJob"]);
  if (!currentJob || !currentJob.id) return;
  try { await chrome.runtime.sendMessage({ type, id: currentJob.id }); } catch (e) { /* worker asleep */ }
  refresh();
}
el("stop").addEventListener("click", () => {
  say("jobdoing", "Stopping…");
  show("stop", false);
  tell("anticipy-stop");
});
el("again").addEventListener("click", () => {
  say("jobdoing", "Starting it again…");
  show("again", false);
  tell("anticipy-again");
});
el("openhb").addEventListener("click", async () => {
  if (!handBackTab) return;
  try { await chrome.runtime.sendMessage({ type: "anticipy-open-handback", tabId: handBackTab }); } catch (e) { /* worker asleep */ }
  window.close();
});

// Keep the panel honest while the popup is open — a job can finish mid-look.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && (changes.currentJob || changes.paired || changes.pairCode || changes.handBacks)) refresh();
});

checkConnection();
refresh();
