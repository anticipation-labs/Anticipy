import { privateEngineRequest } from "../../_engine";

export async function POST(request) {
  return privateEngineRequest(request, "/listen/start", { method: "POST" });
}
