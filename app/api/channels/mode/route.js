import { privateEngineRequest } from "../../_engine";

// The comms-line mock/live toggle (Settings). GET reads the current mode + whether the
// credentials needed to go live are present; POST flips it {mode: "mock" | "live"}. Mock is the
// default everywhere — nothing real leaves the machine until the owner deliberately goes live.
export async function GET(request) {
  return privateEngineRequest(request, "/channels/mode", { method: "GET" });
}

export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/channels/mode", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
