import { privateEngineRequest } from "../../_engine";

// The trace view: everything one user action did, end to end, from one trace id
// (the x-anticipy-trace header every /api response echoes back).
export async function GET(request, { params }) {
  const { id } = await params;
  return privateEngineRequest(request, `/trace/${encodeURIComponent(id)}`);
}
