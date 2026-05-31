const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const $ = (id) => document.getElementById(id);
function show(state) {
  for (const s of ["idle", "running", "done"]) {
    $(s).classList.toggle("hidden", s !== state);
  }
}

function friendlyStatus(s) {
  const k = String(s || "").toLowerCase();
  if (k === "success" || k === "ok") return "Done";
  if (k === "running" || k === "in_progress" || k === "in-progress") return "Working on it";
  if (k === "ask_user" || k === "ask") return "Needs your okay";
  if (k === "notify_user" || k === "notify") return "Heads up sent";
  if (k === "timed_out") return "Took too long, stopped";
  if (k === "error" || k === "failed" || k === "fail") return "Could not finish";
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function startRun() {
  const task = $("task").value.trim();
  if (!task) return;
  $("feed").innerHTML = "";
  // BNEW-002: the legacy run_task Tauri command was removed in cycle
  // 122. The polished popover (popover.html) is the only valid
  // surface; this index.html / main.js pair is kept only so a
  // historical Tauri config pointing at it doesn't crash. Show a
  // calm copy directing the user to the menu bar.
  $("current").textContent = "This window is no longer used. Open Anticipy from the menu bar.";
  show("running");
}

function addFeed(text) {
  const li = document.createElement("li");
  li.textContent = text;
  $("feed").appendChild(li);
  $("feed").scrollTop = $("feed").scrollHeight;
}

window.addEventListener("DOMContentLoaded", () => {
  show("idle");
  $("run").addEventListener("click", startRun);
  $("again").addEventListener("click", () => { $("task").value = ""; show("idle"); });
  $("cancel").addEventListener("click", () => show("idle"));

  listen("agent-event", (e) => {
    const ev = e.payload || {};
    if (ev.kind === "start") {
      $("current").textContent = "Opening the Anticipy work area";
      addFeed("Started: " + (ev.task || ""));
    } else if (ev.kind === "step") {
      const a = ev.action || "step";
      const t = ev.target ? " on " + ev.target : "";
      const v = ev.verdict && ev.verdict !== "-" ? "  (" + ev.verdict + ")" : "";
      $("current").textContent = "Step " + ev.iteration + ": " + a + t + v;
      addFeed("Step " + ev.iteration + ": " + a + t + v +
        (ev.detail ? "  (" + ev.detail + ")" : ""));
    } else if (ev.kind === "log") {
      addFeed(ev.line);
    } else if (ev.kind === "done" || ev.kind === "result") {
      const ok = ev.status === "SUCCESS";
      $("done-title").textContent = ok ? "Done" : friendlyStatus(ev.status);
      $("done-title").className = ok ? "ok" : "fail";
      $("answer").textContent = ev.answer || "";
      $("evidence").textContent = ev.evidence || ev.error || "";
      const bits = [];
      if (ev.n_iterations != null) bits.push(ev.n_iterations + " steps");
      $("meta").textContent = bits.join("  ,  ");
      show("done");
    }
  });
});
