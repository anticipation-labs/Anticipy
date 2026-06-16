import { privateEngineRequest } from "../_engine";

// Owner-gated proxy: POST {} -> engine POST /onboard/scan_api.
//
// The engine looks at the accounts the owner is already signed into and reports back,
// in plain language, what it found — which accounts are connected, and a few honest
// facts it could read from them (e.g. "You have 25 events in the next two weeks.").
// It NEVER invents a fact, never sends or spends anything, and never returns a secret
// value — only presence and the real facts it read. Same token discipline as every
// private engine route.
export async function POST(request) {
  // Accept an optional body but never require one — the engine's scan takes no input.
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/onboard/scan_api", {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
}
