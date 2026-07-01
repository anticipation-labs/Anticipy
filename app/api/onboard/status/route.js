import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy: read the durable "onboarding done" marker.
export async function GET(request) {
  return privateEngineRequest(request, "/onboard/status");
}
