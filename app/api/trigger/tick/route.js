import { engineRequest } from "../../_engine";

export async function POST() {
  return engineRequest("/trigger/tick", { method: "POST" });
}
