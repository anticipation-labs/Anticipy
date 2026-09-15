// The popup is Anticipy's only face on the machine the work actually happens
// on. It answers three questions, in this order of precedence, and it never
// leaves one of them blank: is this browser hers yet, can she reach her
// backend from here, and what is she doing right now — with a way to stop it.
//
// Every state below shipped as a confusing blank at some point, which is why
// they are enumerated in one place (render) instead of being toggled by four
// independent renderers racing each other. The old file had `checkConnection`
// writing the status line on its own timeline while `refresh` wrote the panels
// on another, so a running job could sit under the words "I can't reach
// Anticipy" and neither line knew about the other.

import { backendBase } from "./config.js";
import { parseJobParams } from "./workflow_state.js";

const el = (id) => document.getElementById(id);
const show = (id, on) => el(id).toggleAttribute("hidden", !on);

// Only write when the words actually change: a live region rewritten with
// identical text on a timer makes a screen reader repeat itself.
function say(id, text) {
  const node = el(id);
  if (node.textContent.trim() !== text) node.textContent = text;
}

// "Copied" has to survive the next repaint, or the confirmation blinks away
// before the person has looked back at their phone. This popup repaints every
// four seconds, so the hint needs a hold; the old one had no timer and so no
// hold, and the message vanished the moment anything else changed.
let hintHeldUntil = 0;
function hint(text, holdMs = 0) {
  if (!holdMs && Date.now() < hintHeldUntil) return;
  if (holdMs) hintHeldUntil = Date.now() + holdMs;
  say("copyhint", text);
}

// ------------------------------------------------------------------ backend
// The same credential the worker sends. guard.pb.js lets an agent read exactly
// one thing beyond its own row — a job belonging to its owner
// (migration/workers/src/policy/guard.ts) — which is the one row this file reads.
// The server-wide service token is deliberately NOT sent: /agent/key has
// returned an empty one for a release and the save erases it, so the header
// could only ever be empty — and a browser holding the server's master
// credential is worth deleting on principle. The per-agent pair is what
// actually authenticates.
function agentHeaders({ agentId, agentToken }) {
  const h = {};
  if (agentId) h["X-Anticipy-Agent-ID"] = agentId;
  if (agentToken) h["X-Anticipy-Agent-Token"] = agentToken;
  return h;
}

// null until the first probe answers: "unreachable" and "not asked yet" are
// different sentences and the second one must never be shown as the first.
let reachable = null;
async function probe() {
  try {
    const r = await fetch(`${await backendBase()}/api/health`);
    reachable = r.ok;
  } catch (e) {
    reachable = false;
  }
}

// What she is doing RIGHT NOW lives on the job row, not in storage. The worker
// mirrors a job's STATUS into chrome.storage as it moves, but `doing` is
// written once when the job is claimed (the errand's own title) and never
// again; the live step narration is params._doing, rewritten on the row every
// four seconds by the run's own checkpoint. Without this read a forty-minute
// booking says one sentence for forty minutes, and a run that died twenty
// minutes ago is indistinguishable from one that is working.
//
// Status is deliberately NOT taken from here. The worker owns that mapping
// (a workflow job's truth is workflow_state, not status) and it repairs the
// storage mirror off the row itself; a second mapping in the popup is how you
// end up with two surfaces confidently disagreeing.
let liveStep = "";
let refreshEpoch = 0;
async function loadLiveStep(s, epoch) {
  try {
    const base = await backendBase();
    const r = await fetch(
      `${base}/api/collections/jobs/records/${encodeURIComponent(s.job.id)}`,
      { headers: agentHeaders(s) });
    // A refusal is an answer: the backend is reachable, the read was denied.
    reachable = true;
    if (!r.ok) return "";
    const row = await r.json();
    // The epoch is NOT the test: a read that outlived the 4 s tick is still
    // true when the job it read is the job on screen. refresh() rechecks the
    // displayed identity and job before painting it (review 2026-09-14).
    if (row?.id !== s.job.id || row?.owner_ref !== s.ownerRef) return "";
    return String(parseJobParams(row)._doing || "").trim();
  } catch (e) {
    // Network-level failure. probe() owns the reachable verdict — a CORS or
    // abort failure here is not proof the backend is down.
    return "";
  }
}

// ------------------------------------------------------------------- state
const STOPPABLE = new Set(["running", "queued"]);
// A job waiting on the owner's OK must not be offered "again" — that would
// queue a second copy of something already sitting there prefilled.
//
// Nor may "failed" or "stopped" be offered here. Those are TERMINAL in the
// workflow contract (deliberately: reviving finished work is the
// resurrection class an audit flagged), so retryJob's patch threw
// "illegal workflow transition failed -> queued" before any network call and
// the click did nothing at all — a button that looked like a way out and
// was not. Starting terminal work over needs a NEW approved plan, which only
// the brain may mint; the phone's "Start a fresh attempt" does exactly that.
const RETRYABLE = new Set(["needs_user"]);
// Heads, not statuses: a job parked on a login wall is not "the last task",
// and calling it that is how a person walks away from work that is waiting on
// them.
const HEADS = {
  running: "Right now", queued: "Right now",
  awaiting_confirm: "Waiting for you", needs_user: "Waiting for you",
  // Work this browser may never touch — a research-lane job runs server-side.
  // Without its own heading it fell through to "Last task", which is the one
  // thing it is not: it is a live row that nothing here will ever claim.
  waiting: "Heads up",
};
const LINES = {
  running: (e) => `Working on this: ${e}`,
  queued: (e) => `Picking this up: ${e}`,
  awaiting_confirm: (e) => `It's filled in and waiting for your OK: ${e}`,
  needs_user: (e) => `I stopped and I need you: ${e}`,
  done: (e) => `Done: ${e}`,
  failed: (e) => `This didn't work: ${e}`,
  stopped: (e) => `Stopped: ${e}`,
  removed: (e) => `Called off: ${e}`,
  // Verbatim. background.js writes a whole explanation here — why this row
  // cannot run in this browser — and a prefix like "Picking this up" would
  // contradict it in the same breath.
  waiting: (e) => e,
};

// A kept-back tab (a login wall, a page waiting on their OK) never surfaces
// itself — the badge points here, and THIS button is the owner's click that
// opens it. The worker does the focusing so the notification and the popup
// share one path.
let handBackTab = null;
// The pressed-but-unanswered action, and the status it was pressed against.
// See render() for why it exists.
let pending = null;
let shownStatus = "";

const IDENTITY_FIELDS = ["ownerRef", "agentId", "agentToken", "recordId", "backendUrl"];
const identityString = value => typeof value === "string" && value.trim() ? value : "";
const sameIdentity = (a, b) => !!a && !!b && a.linked === b.linked &&
  IDENTITY_FIELDS.every(key => a[key] === b[key]);
const sameJobView = (a, b) => sameIdentity(a, b) &&
  a.job?.id === b.job?.id && a.job?.status === b.job?.status;

async function snapshot() {
  const s = await chrome.storage.local.get(
    ["pairCode", "recordId", "paired", "ownerRef", "agentId", "agentToken",
      "backendUrl", "currentJob", "handBacks"]);
  const identity = Object.fromEntries(IDENTITY_FIELDS.map(key => [key, identityString(s[key])]));
  // A paired flag alone does not identify an owner, and a legacy record with
  // no credential cannot authenticate. Recovery must not make its old task
  // text visible while a new phone is being paired.
  const linked = !!identity.ownerRef && !!identity.agentId &&
    !!identity.agentToken && !!identity.recordId;
  // A record paired before Anticipy kept owner ids: the phone claimed it, so
  // its code is spent, and nothing can run under it. The only way out is a
  // fresh identity, which this surface must OFFER rather than hide behind a
  // dead code (review 2026-09-14).
  const pairedWithoutOwner = !!s.paired && !identity.ownerRef && !!identity.recordId && !!identity.agentToken;
  const ids = Object.keys(s.handBacks || {})
    .filter(id => linked && s.handBacks[id]?.ownerRef === identity.ownerRef)
    .sort((a, b) => (s.handBacks[a].at || 0) - (s.handBacks[b].at || 0));
  return {
    ...identity,
    handBackTab: ids.length ? ids[ids.length - 1] : null,
    code: pairedWithoutOwner ? "" : (s.pairCode || ""),
    pairedWithoutOwner,
    linked,
    // Being linked IS proof of registration, and saying otherwise let the two
    // lines on this surface contradict each other: an install whose recordId
    // and pairCode had been cleared (a re-pair, or the newcode path) showed
    // "Linked" in the masthead over the words "Introducing this browser…".
    registered: !!s.pairCode || !!s.recordId || linked,
    // Unknown legacy ownership is not evidence of this person's task. Keep
    // the stored record for recovery; never relabel or delete it here.
    job: linked && s.currentJob?.ownerRef === identity.ownerRef && s.currentJob.status
      ? s.currentJob : null,
  };
}

function clearTaskSurface() {
  for (const id of ["jobdoing", "joberrand", "jobresult", "jobheadtext"]) say(id, "");
  for (const id of ["jobbox", "openhb", "stop", "again", "bars", "why"]) show(id, false);
}

function render(s) {
  const job = s.job;
  handBackTab = s.handBackTab;
  const status = job ? job.status : "";
  const busy = STOPPABLE.has(status) || status === "awaiting_confirm";

  // --- masthead: the pairing truth, in two words, always visible.
  el("linkdot").classList.toggle("on", s.linked);
  el("linkpill").classList.toggle("on", s.linked);
  say("linktext", s.linked ? "Linked" : "Not linked");
  // The browser breathes while it waits to be claimed; once it is hers the
  // dot goes still and the waveform below carries the motion instead.
  document.body.classList.toggle("waiting", !s.linked);

  // --- the one lit sentence.
  let state;
  if (!s.registered) {
    state = reachable === false
      ? "I can't reach Anticipy from this browser, so this browser hasn't been given its code yet. I'll keep trying."
      : "Introducing this browser to Anticipy…";
  } else if (s.pairedWithoutOwner) {
    state = "This browser was paired before Anticipy kept owner ids. Press New code, then pair it again from your iPhone.";
  } else if (!s.linked) {
    state = "This browser isn't linked to your iPhone yet.";
  } else if (busy) {
    state = status === "awaiting_confirm"
      ? "Waiting for your OK before I finish this."
      : "Working in this browser right now.";
  } else if (status === "needs_user") {
    state = "I stopped part-way and I need you.";
  } else if (reachable === false) {
    state = "Linked to your iPhone — but I can't reach Anticipy from this browser right now.";
  } else {
    state = "Linked, and watching for work.";
  }
  say("state", state);

  // --- the code, and the way out of having no code at all.
  show("codebox", !s.linked);
  const codeBtn = el("paircode");
  codeBtn.disabled = !s.code;
  say("paircode", s.code || "······");
  // Only for the actual dead end — an install that registered but never got a
  // code (the 409-orphan path background.js describes). A fresh install has no
  // record either and resolves itself within a poll; offering a reset there
  // would just invite people to churn identities while she was mid-handshake.
  show("getcode", !s.linked && !s.code && s.registered && (reachable !== false || s.pairedWithoutOwner));
  hint(s.code
    ? "Click the code to copy it."
    : reachable === false
      ? "Your code appears here the moment I can reach Anticipy."
      : "Getting your code…");

  // --- the job.
  show("jobbox", !!job);
  if (job) {
    const errand = (job.doing || "a task").trim();
    // A press has to stay acknowledged until the worker's answer lands. The
    // handler used to write "Stopping…" straight into the line and the very
    // next repaint — four seconds later, or sooner — put the running step
    // back, so Stop read as a button that had done nothing while the stop was
    // in fact already on its way. The latch clears itself the moment the
    // status actually moves, or after ten seconds if the worker never answers.
    if (pending && (pending.status !== status || pending.id !== job.id ||
        pending.ownerRef !== s.ownerRef || Date.now() - pending.at > 10000)) pending = null;
    shownStatus = status;
    say("jobheadtext", HEADS[status] || "Last task");
    show("bars", status === "running" && !pending);
    // The live step is the sentence; the errand becomes its context. Without a
    // live step the errand IS the sentence — never a blank line.
    if (pending) {
      say("jobdoing", pending.text);
      show("joberrand", false);
    } else if (liveStep && STOPPABLE.has(status)) {
      say("jobdoing", liveStep);
      say("joberrand", `On: ${errand}`);
      show("joberrand", true);
    } else {
      say("jobdoing", (LINES[status] || ((e) => e))(errand));
      show("joberrand", false);
    }
    const result = String(job.result || "").trim();
    show("jobresult", !!result);
    if (result) say("jobresult", result);
    // One class, one meaning: .bad is the failure colour. Both used to be set
    // on the same condition because .warn drew the bar and .bad recoloured it;
    // with the bar gone that is two rules racing for one line's colour.
    el("jobresult").classList.toggle("bad", status === "failed");

    show("why", status === "running" && !pending);
    show("stop", !pending && !!job.id && STOPPABLE.has(status));
    show("again", !pending && !!job.id && RETRYABLE.has(status));
    // A hand-back is the one thing on this surface that is genuinely blocked on
    // a click, so it leads when the job is parked on it.
    show("openhb", !!handBackTab);
    el("openhb").classList.toggle(
      "filled", status === "needs_user" || status === "awaiting_confirm");
  } else {
    pending = null;
    shownStatus = "";
    liveStep = "";
    clearTaskSurface();
  }

  // --- reachability. The sentence above already says it is unreachable; this
  // line exists only to say what to do about it. Repeating the diagnosis two
  // lines apart is how a small surface starts to read as boilerplate.
  const down = reachable === false && s.registered;
  show("offline", down);
  if (down) {
    // The linked sentence above already names the outage, so that branch only
    // says what to do; the unlinked sentence says "isn't linked yet" and
    // nothing about the network, so this one has to carry the diagnosis or
    // "pairing can't finish" is a riddle.
    say("offline", s.linked
      ? "If you're online, that usually clears by itself in a minute. If you've pointed me at your own backend, check the address under Setup & advanced."
      : "I can't reach Anticipy from this browser, so pairing can't finish. If you've pointed me at your own backend, check the address under Setup & advanced.");
  }
}

// The last snapshot actually painted, so a press can repaint the truth plus
// its own acknowledgement without waiting on a storage read.
let lastSnap = null;

async function refresh() {
  const epoch = ++refreshEpoch;
  let s;
  try { s = await snapshot(); }
  catch {
    if (epoch === refreshEpoch) {
      lastSnap = null; pending = null; liveStep = ""; handBackTab = null;
      clearTaskSurface();
    }
    return;
  }
  if (epoch !== refreshEpoch) return;
  if (!sameJobView(lastSnap, s)) { liveStep = ""; pending = null; }
  lastSnap = s;
  // Paint from storage FIRST: it is already local and already true, and the
  // popup has one job in its first frame, which is to not be empty. The
  // network only ever refines what is already on screen.
  render(s);
  const id = s.job && s.job.id && STOPPABLE.has(s.job.status) ? s.job.id : "";
  if (!id) return;
  const step = await loadLiveStep(s, epoch);
  let current;
  try { current = await snapshot(); } catch { return; }
  // A storage event may not yet have reached the popup. Recheck the captured
  // identity and job before allowing the delayed network read to repaint — that
  // recheck, not the epoch, is what keeps another owner's text off the screen.
  if (!sameJobView(s, current)) { if (epoch === refreshEpoch) return refresh(); return; }
  if (!step) return;
  liveStep = step;
  lastSnap = current;
  render(current);
}

// -------------------------------------------------------------- her buttons
el("paircode").addEventListener("click", async () => {
  const code = el("paircode").textContent.trim();
  if (el("paircode").disabled || !/^\d+$/.test(code)) return;
  try {
    await navigator.clipboard.writeText(code);
    hint("Copied. Now type it into the app.", 12000);
  } catch (e) {
    hint("I couldn't copy it — read it off the screen instead.", 12000);
  }
});

// Stop and start-again both go through the worker, which writes the job row
// the same way every other status change does. The running loop checks that
// row as it works, so it stops within a few seconds.
async function tell(type, displayed) {
  try {
    const current = await snapshot();
    if (!displayed?.job?.id || !sameJobView(displayed, current) || !current.linked) return false;
    const response = await chrome.runtime.sendMessage({ type, id: displayed.job.id, ownerRef: displayed.ownerRef });
    return response?.ok === true;
  } catch (e) { return false; /* worker asleep or storage unavailable */ }
}
// Latch the acknowledgement rather than writing it into the line: the next
// repaint would otherwise overwrite it with the state the worker has not
// answered yet.
const press = async (text, type) => {
  const displayed = lastSnap;
  const allowed = type === "anticipy-stop" ? STOPPABLE : RETRYABLE;
  if (!displayed?.linked || !displayed.job?.id || !allowed.has(displayed.job.status)) return;
  pending = { text, status: shownStatus, id: displayed.job.id, ownerRef: displayed.ownerRef, at: Date.now() };
  render(displayed);
  if (!await tell(type, displayed)) pending = null;
  await refresh();
};
el("stop").addEventListener("click", () => press("Stopping…", "anticipy-stop"));
el("again").addEventListener("click", () => press("Starting it again…", "anticipy-again"));
el("openhb").addEventListener("click", async () => {
  const displayed = lastSnap;
  const tabId = displayed?.handBackTab;
  if (!tabId || !displayed?.linked) return;
  try {
    const current = await snapshot();
    if (!sameIdentity(displayed, current) || current.handBackTab !== tabId) return;
    const response = await chrome.runtime.sendMessage({ type: "anticipy-open-handback", tabId, ownerRef: displayed.ownerRef });
    if (response?.ok === true) window.close();
    else await refresh();
  } catch (e) { /* worker asleep or storage unavailable */ }
});
// A registered install with no pair code used to be a dead end: the only
// recovery is a fresh identity, and the button for it lived on the setup page
// behind a code we never got (background.js says as much where it handles the
// 409). Offered here only while unlinked — the worker mints a new identity and
// registers again, which is safe precisely because nobody has claimed this one.
el("getcode").addEventListener("click", async () => {
  hint("Asking for one…", 4000);
  try { await chrome.runtime.sendMessage({ type: "anticipy-newcode" }); } catch (e) { /* worker asleep */ }
  refresh();
});

// Keep the panel honest while the popup is open — a job can finish mid-look.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (IDENTITY_FIELDS.some(key => changes[key]) || changes.paired) {
    lastSnap = null; pending = null; liveStep = ""; handBackTab = null;
    clearTaskSurface();
  }
  if (changes.currentJob || changes.paired || changes.pairCode || changes.handBacks ||
      IDENTITY_FIELDS.some(key => changes[key])) refresh();
});

// Opening the popup is a wake signal worth spending: reading storage does NOT
// boot the service worker, and a fresh profile has been observed with no
// alarms at all — so this ping is what makes the numbers on screen current.
try { chrome.runtime.sendMessage({ type: "anticipy-ping" }).catch(() => {}); } catch (e) { /* worker context gone */ }

// The live step is rewritten on the row every four seconds; match it, and
// re-probe reachability every fourth pass rather than on every one.
let tick = 0;
probe().then(refresh);
setInterval(async () => {
  if (++tick % 4 === 0) await probe();
  refresh();
}, 4000);
