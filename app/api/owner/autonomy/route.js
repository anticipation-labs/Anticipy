import { privateEngineRequest } from "../../_engine";

// FIX-04 (2026-07-02): the REAL autonomy dial. The settings dropdown previously wrote only a
// local display store while the engine's gate (/owner/autonomy_mode) sat untouched — the trust
// dial literally did nothing. GET reads the live mode; POST sets it {mode: limited|regular|full_send}.
export async function GET(request) {
  return privateEngineRequest(request, "/owner/autonomy_mode", { method: "GET" });
}

export async function POST(request) {
  const body = await request.json();
  return privateEngineRequest(request, "/owner/autonomy_mode", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
