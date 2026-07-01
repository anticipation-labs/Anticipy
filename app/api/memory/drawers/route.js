import { privateEngineRequest } from "../../_engine";

// Owner-gated read surface for all four memory drawers (profile / derived /
// open loops / history) — what Anticipy actually learned, straight from the engine.
export async function GET(request) {
  return privateEngineRequest(request, "/memory/drawers");
}
