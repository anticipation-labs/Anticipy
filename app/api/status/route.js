import { privateEngineRequest } from "../_engine";

export async function GET(request) {
  return privateEngineRequest(request, "/status");
}
