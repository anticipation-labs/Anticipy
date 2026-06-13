import { privateEngineRequest } from "../../_engine";

// Read-only proxy to the engine's inert remember-list. Strictly DISPLAY:
// it only forwards a GET to /memory/remembered and never creates, acts, or
// triggers anything (the engine endpoint is on no background loop and the
// remembered_lines table carries no due/remind/trigger field).
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const limit = searchParams.get("limit") || "50";
  return privateEngineRequest(request, `/memory/remembered?limit=${encodeURIComponent(limit)}`);
}
