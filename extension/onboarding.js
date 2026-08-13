// The welcome page. Its whole job is one number: the code that links this
// browser to the owner's phone. Everything else on the page is context.

const DEFAULT_BASE = "https://backend-production-61e0a.up.railway.app";

const el = (id) => document.getElementById(id);
const show = (id, on) => el(id).toggleAttribute("hidden", !on);

// The page repaints every 5 seconds. Writing identical text into a live
// region makes a screen reader announce it again every time, so only touch
// the DOM when the words have actually changed.
function say(id, text) {
  const node = el(id);
  if (node.textContent.trim() !== text) node.textContent = text;
}

async function base() {
  const { backendUrl } = await chrome.storage.local.get(["backendUrl"]);
  return (backendUrl || DEFAULT_BASE).replace(/\/$/, "");
}

// "Copied" has to survive the next repaint, or the confirmation blinks away
// before the person has looked back at their phone.
let holdHintUntil = 0;
function hint(text, holdMs) {
  if (!holdMs && Date.now() < holdHintUntil) return;
  if (holdMs) holdHintUntil = Date.now() + holdMs;
  say("codeHint", text);
}

async function refresh() {
  const dot = el("backendDot");
  try {
    const r = await fetch(`${await base()}/api/health`);
    if (!r.ok) throw new Error("unhealthy");
    dot.classList.add("on");
    say("backendText", "Connected to Anticipy Codex Version.");
  } catch (e) {
    dot.classList.remove("on");
    // Nobody reading this runs a backend. Say what's true and what happens next.
    say("backendText", "I can't reach Anticipy Codex Version from here yet — I'll keep trying. Your code appears the moment I'm through.");
  }

  const { pairCode, paired } = await chrome.storage.local.get(["pairCode", "paired"]);
  const code = el("paircode");

  if (paired) {
    // Step 1 is finished — it must stop giving an instruction that no longer
    // applies, or the page argues with itself.
    say("codeHead", "Your phone and this browser are linked");
    say("codeBody", "Nothing else to do here. You can close this page.");
    code.textContent = "Paired";
    code.disabled = true;
    code.classList.add("done");
    el("codeCard").classList.remove("hero");
    hint("", 0);
    show("newcode", false);
    show("noapp", false);
    say("liveHead", "That's it — live your day.");
    say("liveBody", "When you approve something that needs the web, it happens here.");
    return;
  }

  say("codeHead", "Type this code into the Anticipy Codex Version app on your iPhone");
  say("codeBody", "It's in the app's setup screen, or in Settings if you've already been through setup. This links your phone to this browser.");
  code.classList.remove("done");
  el("codeCard").classList.add("hero");
  code.disabled = !pairCode;
  code.textContent = pairCode || "······";
  hint(pairCode ? "Click the code to copy it." : "Your code appears here as soon as I reach Anticipy Codex Version.", 0);
  show("newcode", !!pairCode);
  show("noapp", true);
  say("liveHead", "Waiting for your phone…");
  say("liveBody", "The moment you type the code in, this page will say so, and I'm live. Nothing runs here until then.");
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
// while unpaired: the worker mints a fresh identity and registers again.
el("newcode").addEventListener("click", async () => {
  hint("Getting you a new one…", 3000);
  el("paircode").disabled = true;
  try { await chrome.runtime.sendMessage({ type: "anticipy-newcode" }); } catch (e) { /* worker asleep */ }
  refresh();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && (changes.pairCode || changes.paired)) refresh();
});

refresh();
setInterval(refresh, 5000);
