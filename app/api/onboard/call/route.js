import { privateEngineRequest } from "../../_engine";

// The onboarding "can I call you?" arm. The engine plans the gap questions from the newest
// inhale dossier and places the call (mock records the simulated conversation; live dials
// Twilio). A live two-way call can take a while to set up, so give it headroom.
export const maxDuration = 120;

export async function POST(request) {
  const body = await request.text();
  return privateEngineRequest(request, "/onboard/call", {
    method: "POST",
    body: body || "{}",
  });
}
