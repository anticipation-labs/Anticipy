import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy: POST {name, sources:[urls]} -> engine POST /onboarding/profile.
// Read-only scraping; the engine builds a structured, trust-graded profile (or
// degrades honestly when no browser is available). No login, no writes, no money.
export async function POST(request) {
  const body = await request.json();
  return privateEngineRequest(request, "/onboarding/profile", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
