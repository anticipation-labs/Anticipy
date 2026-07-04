import { privateEngineRequest } from "../../_engine";

// Read-only proxy to the engine's memory history drawer (the append-only log of what has
// happened). Strictly DISPLAY: it forwards a GET to /memory/history and never creates, acts,
// or triggers anything — it only surfaces what is already recorded for the memory review.
export async function GET(request) {
  return privateEngineRequest(request, "/memory/history");
}
