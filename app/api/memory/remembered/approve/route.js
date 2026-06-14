import { privateEngineRequest } from "../../../_engine";

// Owner-gated press-go proxy. This is the ONE write the review surface can trigger:
// it forwards a single {line_id} POST to the engine's default-deny press-go route
// (/memory/remembered/approve). It executes nothing itself — the engine decides,
// runs ONLY the three whitelisted reversible intents through its read-back gate, and
// hands everything else back. No body field here can route a non-whitelisted item to
// execution; the proxy just relays the owner's explicit per-line approval.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/memory/remembered/approve", {
    method: "POST",
    body: JSON.stringify({ line_id: body?.line_id }),
  });
}
