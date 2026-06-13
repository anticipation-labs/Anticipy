import { engineRequest } from "../_engine";

export async function GET() {
  return engineRequest("/status");
}
