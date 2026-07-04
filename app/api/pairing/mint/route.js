import { privateEngineRequest } from "../../_engine";

// B12 — mint a signed, short-lived per-user pairing code for the SIGNED-IN caller.
//
// The signed-in web app calls this; privateEngineRequest forwards the caller's Supabase bearer
// so the engine's auth middleware binds the request to THEIR user before minting (the engine
// holds ENGINE_INTERNAL_TOKEN and signs the code carrying that user id — the secret never
// leaves the server). The browser page relays the returned code to the extension via the
// pair_device message; the extension claims it at the engine's /ws/pair.
//
// Gated end-to-end behind ANTICIPY_PER_USER_HANDS: while that flag is off the engine returns
// 404 here, so this route is inert and today's single-owner pairing is unchanged.
export async function GET(request) {
  return privateEngineRequest(request, "/ws/pair_code", { method: "GET" });
}
