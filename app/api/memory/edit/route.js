import { privateEngineRequest } from "../../_engine";

// Correct one remembered fact in place (the "fix a wrong fact on the Who-I-Am page" surface).
// The engine replaces the text on the same item id and re-embeds it, so every recall —
// semantic or keyword — sees the corrected fact immediately.
export async function POST(request) {
  const body = await request.text();
  return privateEngineRequest(request, "/memory/edit", {
    method: "POST",
    body: body || "{}",
  });
}
