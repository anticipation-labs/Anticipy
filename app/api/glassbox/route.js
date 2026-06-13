import { privateEngineRequest } from "../_engine";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const limit = searchParams.get("limit") || "30";
  return privateEngineRequest(request, `/glassbox?limit=${encodeURIComponent(limit)}`);
}
