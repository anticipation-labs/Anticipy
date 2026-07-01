import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy: persist that the owner confirmed their dossier.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/onboard/complete", {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
}
