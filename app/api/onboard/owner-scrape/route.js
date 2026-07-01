import { privateEngineRequest } from "../../_engine";

// Owner-gated proxy: POST {max_chars?} -> engine POST /onboard/owner-scrape.
// This is the full read-only Chrome self-scrape path; the engine reports login walls
// honestly and writes only the synthesized memory profile back to the local ledger.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/onboard/owner-scrape", {
    method: "POST",
    body: JSON.stringify(body || {}),
  });
}
