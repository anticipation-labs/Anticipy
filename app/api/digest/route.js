import { privateEngineRequest } from "../_engine";

// "Send my digest now" (NF10): delivers the day's accumulated non-urgent items as ONE
// message and clears the queue. A quiet day returns {sent:false, reason:"quiet day"}.
// Wired 2026-07-02 (FIX-01 Phase 3) — the engine's deliver_digest previously had no caller.
export async function POST(request) {
  return privateEngineRequest(request, "/digest/deliver", { method: "POST" });
}
