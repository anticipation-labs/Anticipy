import { engineRequest } from "../../_engine";

export async function POST(request) {
  const body = await request.json();
  return engineRequest("/connections/authorize", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
