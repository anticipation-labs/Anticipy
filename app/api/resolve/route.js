import { privateEngineRequest } from "../_engine";

export async function POST(request) {
  const body = await request.json();
  return privateEngineRequest(request, "/resolve", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
