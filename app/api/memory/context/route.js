import { privateEngineRequest } from "../../_engine";

// The ONE context seam, surfaced to the UI: shows the exact ContextPack the brain would
// assemble for a moment (decide / act / speak) — the same builder the decider, hands, and
// voice all read through. Proxies straight to the engine's /memory/context.
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const about = searchParams.get("about") || "";
  const purpose = searchParams.get("purpose") || "decide";
  return privateEngineRequest(
    request,
    `/memory/context?about=${encodeURIComponent(about)}&purpose=${encodeURIComponent(purpose)}`,
  );
}
