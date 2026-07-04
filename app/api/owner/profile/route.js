import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy for the STATED onboarding basics (name / one-sentence summary / phone /
// timezone / trust dial / always-ask). Reads from and writes to the ENGINE's durable profile
// memory drawer (survives serverless + the brain reads it), replacing the old ephemeral local-file
// /api/profile store that Vercel serverless threw away between requests.
export async function GET(request) {
  return privateEngineRequest(request, "/owner/profile");
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/owner/profile", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
