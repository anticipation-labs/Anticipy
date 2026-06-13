import { engineRequest } from "../../_engine";

export async function POST(request) {
  const body = await request.json();
  return engineRequest("/memory/open-loops/resolve", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
