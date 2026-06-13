import { engineRequest } from "../_engine";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const limit = searchParams.get("limit") || "30";
  return engineRequest(`/glassbox?limit=${encodeURIComponent(limit)}`);
}
