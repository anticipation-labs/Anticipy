import { privateEngineRequest } from "../../_engine";

// FIX-03 (2026-07-02): the REAL 4-layer onboarding loop, finally reachable from the UI.
// Before this, "Go deeper" called only the shallow extension snapshot while the genuine
// CDP scroll+read loop (/onboard/loop — now self-expanding, FIX-11) had no app route at all.
// The loop's wall-clock budget is 300s, so this proxy must not be edge-cached or time-limited.
export const maxDuration = 300;

export async function POST(request) {
  const body = await request.text();
  return privateEngineRequest(request, "/onboard/loop", {
    method: "POST",
    body: body || "{}",
  });
}
