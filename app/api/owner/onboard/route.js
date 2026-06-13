import { privateEngineRequest } from "../../_engine";

export async function POST(request) {
  const body = await request.json();
  return privateEngineRequest(request, "/owner/onboard", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
