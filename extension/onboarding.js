// The setup page. Its whole job is one number and one live truth: the code that
// links this browser to the owner's phone, and whether it has landed yet.
//
// It used to show the code and a static instruction, which meant a first-timer
// had no way to tell "waiting for you" from "broken", and no idea the phone was
// the thing that claims the code. So every sentence on the page is now driven
// by state, and the state changes by itself: the heartbeat writes `paired` and
// `ownerRef` into storage within about thirty seconds of the phone claiming
// this browser, and this page is watching both.

import { backendBase } from "./config.js";

const el = (id) => document.getElementById(id);
const show = (id, on) => el(id).toggleAttribute("hidden", !on);

// The page repaints every 5 seconds. Writing identical text into a live
// region makes a screen reader announce it again every time, so only touch
// the DOM when the words have actually changed.
function say(id, text) {
  const node = el(id);
  if (node.textContent.trim() !== text) node.textContent = text;
}

// "Copied" has to survive the next repaint, or the confirmation blinks away
// before the person has looked back at their phone.
let holdHintUntil = 0;
function hint(text, holdMs) {
  if (!holdMs && Date.now() < holdHintUntil) return;
  if (holdMs) holdHintUntil = Date.now() + holdMs;
  say("codehint", text);
}

// ------------------------------------------------------------- the backend
// null until the first probe answers: "unreachable" and "not asked yet" are
// different sentences, and the second one must never be shown as the first.
let reachable = null;
async function probe() {
  try {
    const r = await fetch(`${await backendBase()}/api/health`);
    reachable = r.ok;
  } catch (e) {
    reachable = false;
  }
}

// A URL that looks right and quietly breaks everything is what this guards.
// Every call site in the extension builds `${base}/api/...`, so a trailing
// path silently becomes /api/api/health; a scheme Chrome won't fetch, or a
// hostname with no scheme at all, produces a throw inside the service worker
// where nobody ever sees it. Until this field existed the only way to point an
// install at a local rig was typing chrome.storage.local.set(...) into the
// service-worker console, so nobody was in a position to notice either.
function parseBase(raw) {
  const text = String(raw || "").trim();
  if (!text) return { error: "Type an address, or use the default." };
  let u;
  try { u = new URL(text); } catch (e) {
    return { error: "That isn't a full address. It has to start with http:// or https://." };
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    // The likely mistake by far is a missing scheme: "localhost:8090" parses
    // as the SCHEME "localhost:" with no host at all, so reporting that Chrome
    // can't fetch localhost: is both true and useless.
    return { error: text.includes("//")
      ? `Chrome can't fetch ${u.protocol} from here. Use http:// or https://.`
      : `Put http:// in front — like http://${text}.` };
  }
  if (!u.hostname) return { error: "That address has no host in it." };
  if (u.pathname !== "/" && u.pathname !== "") {
    return { error: "Leave the path off — just the host and port, like http://127.0.0.1:8090." };
  }
  if (u.search || u.hash) {
    return { error: "Leave the ? and # parts off — just the host and port." };
  }
  // origin normalises away the trailing slash the rest of the extension would
  // otherwise have to strip at every call site.
  return { base: u.origin };
}

function backendMsg(text, kind) {
  const node = el("backendmsg");
  node.classList.toggle("bad", kind === "bad");
  node.classList.toggle("ok", kind === "ok");
  say("backendmsg", text);
}

async function renderBackend() {
  const [{ backendUrl }, resolved] = await Promise.all([
    chrome.storage.local.get(["backendUrl"]),
    backendBase(),
  ]);
  const field = el("backend");
  // The resolved address is the placeholder, so the field shows what this
  // browser is ACTUALLY talking to even when there is no override to display.
  field.placeholder = resolved;
  if (document.activeElement !== field) field.value = backendUrl ? String(backendUrl) : "";
  say("backendnow", `In use now: ${resolved}${backendUrl ? "" : " (default)"}`);
}

el("backendsave").addEventListener("click", async () => {
  const { base, error } = parseBase(el("backend").value);
  const field = el("backend");
  if (error) {
    // Refuse loudly. A silently rejected address is how you end up convinced
    // the backend is down when the extension never tried to reach it.
    field.setAttribute("aria-invalid", "true");
    field.focus();
    backendMsg(error, "bad");
    return;
  }
  field.removeAttribute("aria-invalid");
  await chrome.storage.local.set({ backendUrl: base });
  backendMsg(`Saved. This browser now talks to ${base}.`, "ok");
  reachable = null;
  await probe();
  await renderBackend();
  refresh();
});

el("backendreset").addEventListener("click", async () => {
  el("backend").removeAttribute("aria-invalid");
  // Removing the key, not writing an empty string: config.js reads an absent
  // or empty override as "use production", but leaving an empty value behind
  // makes the field look like it holds a setting when it holds nothing.
  await chrome.storage.local.remove("backendUrl");
  el("backend").value = "";
  reachable = null;
  await probe();
  await renderBackend();
  backendMsg("Back to the production backend.", "ok");
  refresh();
});

// Someone arriving from the popup's "Setup & advanced" link is coming here for
// exactly one control; make them look for nothing.
if (location.hash === "#advanced") {
  el("advanced").open = true;
}

// -------------------------------------------------------------- the state
// Remembering the last verdict is what makes the peak moment possible: the
// celebration must fire on the TRANSITION into linked, never on every one of
// the repaints that follow it.
let wasLinked = null;

async function refresh() {
  // Wake the service worker. Reading storage from this page does NOT boot it,
  // and a fresh profile can have no alarms at all (probed live 2026-08-14) —
  // so while this page is open, this ping is what keeps her ears on: each one
  // boots the worker, and every boot re-asserts alarms and polls.
  try { chrome.runtime.sendMessage({ type: "anticipy-ping" }).catch(() => {}); } catch (e) { /* worker context gone */ }

  const s = await chrome.storage.local.get(["pairCode", "recordId", "paired", "ownerRef"]);
  const code = s.pairCode || "";
  // Either one is proof the phone claimed this browser: the heartbeat writes
  // both from the same record, and ownerRef is the one that actually gates
  // work (claimJob returns null without it). An install carrying an ownerRef
  // and a stale paired:false is linked, whatever the older flag says.
  const linked = !!s.paired || !!s.ownerRef;
  // Being linked IS proof of registration. Without this the first beat sat on
  // "waiting" while beats two and three were done, because a re-pair clears
  // recordId and pairCode and leaves only the ownerRef behind.
  const registered = !!code || !!s.recordId || linked;

  document.body.classList.toggle("waiting", !linked);
  document.body.classList.toggle("linked", linked);
  if (wasLinked === false && linked) {
    // Two devices finding each other is the one moment on this page worth a
    // flourish, and it gets exactly one.
    document.body.classList.add("justlinked");
    setTimeout(() => document.body.classList.remove("justlinked"), 900);
  }
  wasLinked = linked;

  // --- the headline and the state line, which must never contradict.
  if (linked) {
    say("head", "This browser is hers.");
    say("state", reachable === false
      ? "Linked to your iPhone — but I can't reach Anticipy Claude Version from this browser right now."
      : "Linked to your iPhone. She's live here.");
  } else if (!registered) {
    say("head", "One step left: link this browser to your iPhone.");
    say("state", reachable === false
      ? "I can't reach Anticipy Claude Version from this browser yet, so there's no code to show. I'll keep trying."
      : "Introducing this browser to Anticipy Claude Version…");
  } else {
    say("head", "One step left: link this browser to your iPhone.");
    say("state", "Waiting for your phone. This page will say so by itself the moment the code lands.");
  }
  el("statedot").classList.toggle("on", linked || (registered && reachable !== false));

  // --- the code.
  const codeBtn = el("paircode");
  codeBtn.disabled = linked || !code;
  codeBtn.classList.toggle("done", linked);
  say("paircode", linked ? "Linked" : (code || "······"));
  if (linked) hint("", 0);
  else hint(code
    ? "Click the code to copy it."
    : reachable === false
      ? "Your code appears here the moment I can reach Anticipy Claude Version."
      : "Getting your code…", 0);

  // Step one is finished — it must stop giving an instruction that no longer
  // applies, or the page argues with itself.
  // Both of these tell someone how to type a code, so neither may be on screen
  // before there IS one: "type these six digits" over six placeholder dots is
  // an instruction to type nothing.
  show("where", !linked && !!code);
  show("firstrun", !linked && !!code);
  show("donenote", linked);
  show("newcode", !linked && !!code);
  show("noapp", !linked);

  // --- the three beats. Real progress, not a picture of a wizard.
  const beat = (id, state) => el(id).setAttribute("data-state", state);
  beat("beat1", registered ? "done" : (reachable === false ? "wait" : "now"));
  beat("beat2", linked ? "done" : (registered ? "now" : "wait"));
  beat("beat3", linked ? "done" : "wait");
  say("beat1text", registered
    ? "This browser introduced itself to Anticipy Claude Version"
    : reachable === false
      ? "This browser can't reach Anticipy Claude Version to introduce itself"
      : "This browser is introducing itself to Anticipy Claude Version");
  say("beat3text", linked
    ? "She's live here — work you approve happens in this browser"
    : "She's live here, and work you approve happens in this browser");

  // The tab title is the only thing a person sees when this page is in the
  // background, which is exactly where it will be while they hold their phone.
  const title = linked
    ? "Anticipy Claude Version — linked"
    : "Anticipy Claude Version — link your browser";
  if (document.title !== title) document.title = title;
}

el("paircode").addEventListener("click", async () => {
  const code = el("paircode").textContent.trim();
  if (el("paircode").disabled || !/^\d+$/.test(code)) return;
  try {
    await navigator.clipboard.writeText(code);
    hint("Copied. Now type it into the app on your phone.", 12000);
  } catch (e) {
    hint("I couldn't copy it — read it off the screen instead.", 12000);
  }
});

// A code that can never be replaced is a dead end for anyone who typed it
// wrong somewhere else, or who's setting up a second machine. Only offered
// while unlinked: the worker mints a fresh identity and registers again.
el("newcode").addEventListener("click", async () => {
  hint("Getting you a new one…", 3000);
  el("paircode").disabled = true;
  try { await chrome.runtime.sendMessage({ type: "anticipy-newcode" }); } catch (e) { /* worker asleep */ }
  refresh();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.pairCode || changes.paired || changes.ownerRef || changes.recordId) refresh();
  if (changes.backendUrl) renderBackend();
});

renderBackend();
probe().then(refresh);
setInterval(async () => {
  await probe();
  refresh();
}, 5000);
