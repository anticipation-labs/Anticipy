import { privateEngineRequest } from "../_engine";

// Proxy for the engine's guided connect-your-accounts checklist. Owner-gated by the
// same token discipline as every private engine route; the engine itself only ever
// reports presence/absence of config, never a secret value.
export async function GET(request) {
  return privateEngineRequest(request, "/readiness");
}
