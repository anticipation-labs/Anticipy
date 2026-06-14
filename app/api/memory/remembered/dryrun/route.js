import { privateEngineRequest } from "../../../_engine";

// Owner-gated DRY-RUN proxy (trust-before-connect). This forwards a single {line_id}
// POST to the engine's /memory/remembered/dryrun route, which shows EXACTLY what
// press-go WOULD do for that remembered line WITHOUT doing it: the planned intent +
// tool + the exact args for a whitelisted (auto-executable) line, or the handback
// description for everything else. The engine route builds NO Goal, calls NO
// orchestrator, writes NO memory, and touches NO api/browser hands — it only PLANS and
// SHOWS, so the owner can preview his day's real actions before connecting any account.
// This proxy executes nothing itself; it just relays the owner's preview request.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/memory/remembered/dryrun", {
    method: "POST",
    body: JSON.stringify({ line_id: body?.line_id }),
  });
}
