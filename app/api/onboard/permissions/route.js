import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy for the per-service allow gate (allow Gmail, allow Calendar, ...).
// Nothing is read from an account until the owner allows it here.
export async function GET(request) {
  return privateEngineRequest(request, "/onboard/permissions");
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/onboard/permissions", {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
}
