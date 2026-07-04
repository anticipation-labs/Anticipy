import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy: POST {task, start_url?} -> engine POST /agent/run (the CONNECTED-Chrome arm).
// This drives the user's OWN logged-in Chrome through the extension link (WebVoyagerAgent over
// core.browser_link) and returns a JUDGE-verified result — never a self-claimed done. It is the
// product path, NOT the throwaway browser-use arm (which spins a fresh browser and can never reach
// the user's real accounts). Money, checkout, and login stay hard stops in the runner —
// it never spends or signs in. DIRECT: it always runs the web arm, with no dependence on the brain
// guessing that a line was a web task.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const task = String(body?.task || "").trim();
  if (!task) {
    return Response.json({ error: "missing_task", message: "Tell me what to do on the web." }, { status: 400 });
  }
  // The user gives a TASK, not a site. Start on a web search for the task and let the agent roam to
  // finish it — it figures out where to go. An explicit start_url is honored if one is ever passed.
  let start = String(body?.start_url || "").trim();
  if (start && !/^https?:\/\//i.test(start)) start = "https://" + start;
  // DuckDuckGo, not Google: Google throws a consent/CAPTCHA wall at automated browsers (which the
  // agent won't solve), DDG doesn't — so the open-web roam actually starts cleanly.
  if (!start) start = "https://duckduckgo.com/?q=" + encodeURIComponent(task);
  return privateEngineRequest(request, "/agent/run", {
    method: "POST",
    body: JSON.stringify({ task, start_url: start, max_steps: 18 }),
  });
}
