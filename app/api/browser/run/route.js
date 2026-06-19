import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy: POST {task, start_url} -> engine POST /agent/act (the open-source browser_use
// arm). The agent drives a real Chrome on the given site and reports what it found/did. Money,
// checkout, and login are HARD STOPS in the runner's action guard — it never spends or signs in.
// This is the DIRECT path: it always runs the browser arm, with no dependence on the brain guessing
// that a line was a web task.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const task = String(body?.task || "").trim();
  if (!task) {
    return Response.json({ error: "missing_task", message: "Tell me what to do on the web." }, { status: 400 });
  }
  // The user gives a TASK, not a site. Start the agent on a web search for the task and let it roam
  // anywhere public to finish (open_web) — it figures out where to go. An explicit start_url is still
  // honored if one is ever passed.
  let start = String(body?.start_url || "").trim();
  if (start && !/^https?:\/\//i.test(start)) start = "https://" + start;
  // DuckDuckGo, not Google: Google throws a consent/CAPTCHA wall at automated browsers (which the
  // agent won't solve), DDG doesn't — so the open-web roam actually starts cleanly.
  if (!start) start = "https://duckduckgo.com/?q=" + encodeURIComponent(task);
  return privateEngineRequest(request, "/agent/act", {
    method: "POST",
    body: JSON.stringify({ task, start_url: start, max_steps: 18, open_web: true }),
  });
}
