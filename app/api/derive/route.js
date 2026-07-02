import { privateEngineRequest } from "../_engine";

// "Anticipate now" (FIX-07 true proactivity): one derive pass — the engine reads its world
// (memory, open loops, calendar), derives at most 2 UNSPOKEN needs, researches browser-only,
// acts through the one front door, and texts the owner. Quiet day -> {"derived": []}.
export async function POST(request) {
  return privateEngineRequest(request, "/derive/tick", { method: "POST" });
}
