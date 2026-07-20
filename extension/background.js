// Anticipy extension service worker.
// Polls the Anticipy backend (PocketBase) for action jobs and executes them in
// the user's own browser using their live logged-in sessions — browser-only,
// no service APIs. Irreversible steps stop at a prefilled page for the user
// (or the phone app) to confirm.

const BASE = "http://127.0.0.1:8090"; // dev; production points at the hosted backend
const POLL_SECONDS = 5;

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
  const r = await fetch(
    `${BASE}/api/collections/jobs/records?filter=${encodeURIComponent('status="queued"')}&perPage=1&sort=created`
  );
  if (!r.ok) return null;
  const items = (await r.json()).items;
  return items && items.length ? items[0] : null;
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
  const build = ACTIONS[job.goal];
  if (!build) {
    await updateJob(job.id, { status: "failed", result: `unknown goal ${job.goal}` });
    return;
  }
  await updateJob(job.id, { status: "running" });
  const tab = await chrome.tabs.create({ url: build(params), active: true });

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

async function poll() {
  try {
    const job = await claimJob();
    if (job) await runJob(job);
  } catch (e) {
    // backend not reachable; try again on next alarm
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("anticipy-poll", { periodInMinutes: POLL_SECONDS / 60 });
});
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "anticipy-poll") poll();
});
// Also poll immediately on worker wake.
poll();
