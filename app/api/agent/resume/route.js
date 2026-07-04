import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy: POST {task, start_url, resume_token?} -> engine POST /agent/resume.
// The wall-handoff continue: when a connected-Chrome run pauses on a login/verification wall, it
// texts the owner and hands back honestly (never a fake done). After the owner clears the wall in
// their OWN browser, the board's "Continue" control POSTs here so the agent picks up from the
// now-unblocked page — it never types credentials, clears the wall itself, spends, or checks out.
// A missing resume_token resumes cold: it re-reads the page and continues, never re-touching the wall.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  const task = String(body?.task || "").trim();
  let start = String(body?.start_url || "").trim();
  if (!task || !start) {
    return Response.json(
      { error: "missing_fields", message: "I need the task and the page you cleared to pick it back up." },
      { status: 400 },
    );
  }
  if (!/^https?:\/\//i.test(start)) start = "https://" + start;
  return privateEngineRequest(request, "/agent/resume", {
    method: "POST",
    body: JSON.stringify({ task, start_url: start, resume_token: String(body?.resume_token || "") }),
  });
}
