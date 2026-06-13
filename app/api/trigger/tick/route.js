import { privateEngineRequest } from "../../_engine";

export async function POST(request) {
  return privateEngineRequest(request, "/trigger/tick", { method: "POST" });
}
