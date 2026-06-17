import { privateEngineRequest } from "../../_engine";

// STOP control for an AUTO_DO_WITH_OPT_OUT chore: the owner pressed STOP on an
// "On it — you can stop me" card. Halts the in-flight reversible chore.
export async function POST(request) {
  const body = await request.json();
  return privateEngineRequest(request, "/owner/stop", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
