import { privateEngineRequest } from "../../_engine";

// Read-only SEMANTIC recall proxy ("what do you know that's relevant to <query>?"). Forwards a
// {query,k} POST to the engine's /memory/recall route, which runs the hybrid retriever
// (semantic + keyword + recency + importance) over the fuzzy drawers and returns the ranked
// items plus the best relevance score. Pure READ: the engine writes nothing and fires no
// action; this proxy only relays the owner's search box query.
export async function POST(request) {
  const body = await request.json().catch(() => ({}));
  return privateEngineRequest(request, "/memory/recall", {
    method: "POST",
    body: JSON.stringify({ query: body?.query || "", k: body?.k || 8 }),
  });
}
