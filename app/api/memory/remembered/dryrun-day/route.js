import { privateEngineRequest } from "../../../_engine";

// Owner-gated WHOLE-DAY DRY-RUN proxy (trust-before-connect). Read-only: it forwards a
// GET to the engine's /memory/remembered/dryrun-day route, which dry-runs EVERY
// remembered line through the SAME default-deny press-go mapping and returns the
// per-line previews plus how many WOULD execute on connect — with NO execution, NO
// Goal, NO orchestrator call, NO memory write, NO hands touched. This lets the owner see
// his entire day's planned real actions before connecting any account. The proxy
// triggers nothing; it only relays the preview pull.
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const limit = searchParams.get("limit") || "50";
  return privateEngineRequest(
    request,
    `/memory/remembered/dryrun-day?limit=${encodeURIComponent(limit)}`,
  );
}
