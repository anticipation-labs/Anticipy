import { privateEngineRequest } from "../../_engine";

// Owner-gated right-to-delete. Default-deny on the engine side: nothing is wiped
// unless the exact confirm phrase is present in the body.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/memory/forget-me", {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
}
