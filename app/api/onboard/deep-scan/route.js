import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy: trigger the CONTENT deep-scrape in the user's connected Chrome.
// Consent-gated on the engine side to the services the owner allowed.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/onboard/deep-scan", {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
}
