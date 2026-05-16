const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const $ = (id) => document.getElementById(id);
function show(state) {
  for (const s of ["idle", "running", "done"]) {
    $(s).classList.toggle("hidden", s !== state);
  }
}

function startRun() {
  const task = $("task").value.trim();
  if (!task) return;
  $("feed").innerHTML = "";
  $("current").textContent = "Starting...";
  show("running");
  invoke("run_task", { task });
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
      $("current").textContent = "Opening Anticipy Agent window...";
      addFeed("start: " + (ev.task || ""));
    } else if (ev.kind === "step") {
      const a = ev.action || "?";
      const t = ev.target ? " -> " + ev.target : "";
      const v = ev.verdict && ev.verdict !== "-" ? "  [" + ev.verdict + "]" : "";
      $("current").textContent = "s" + ev.subtask + " i" + ev.iteration +
        ": " + a + t + v;
      addFeed("i" + ev.iteration + " " + a + t + v +
        (ev.detail ? "  (" + ev.detail + ")" : ""));
    } else if (ev.kind === "log") {
      addFeed(ev.line);
    } else if (ev.kind === "done" || ev.kind === "result") {
      const ok = ev.status === "SUCCESS";
      $("done-title").textContent = ok ? "Done" : (ev.status || "Failed");
      $("done-title").className = ok ? "ok" : "fail";
      $("answer").textContent = ev.answer || "";
      $("evidence").textContent = ev.evidence || ev.error || "";
      $("meta").textContent =
        (ev.n_iterations != null ? ev.n_iterations + " iterations" : "") +
        (ev.trajectory_dir ? "  -  " + ev.trajectory_dir : "");
      show("done");
    }
  });
});
