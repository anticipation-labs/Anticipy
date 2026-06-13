import { engineRequest } from "../../_engine";

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const limit = searchParams.get("limit") || "50";
  return engineRequest(`/owner/cards?limit=${encodeURIComponent(limit)}`);
}
