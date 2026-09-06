/**
 * GET /hands/api/tools?toolkit=<slug> — the vendor's tool catalog for one
 * toolkit, served to the BRAIN so the planner (brain/hands.py choose_tool)
 * can name a tool from the vendor's own list rather than from anything of
 * ours. Service-token only, the same tokenOk shape as hands_api.ts.
 *
 * WHY IT EXISTS (2026-09-06): the planner was built to read
 * API_HAND_TOOLS_PATH and nothing served it. On live the brain would GET a
 * 404, read the catalog as UNKNOWN, and every api verdict would fall to the
 * browser — the planner working in every test and blind in production. The
 * grip verifier caught it as its one HIGH finding before the deploy.
 *
 * NO OWNER RIDES ON THIS. The vendor's global catalog names nobody, so the
 * request carries a toolkit and a token and nothing else; a body or query
 * naming an owner is ignored, not honoured. The reply is provider.tools()'s
 * CatalogTool rows verbatim — vendor order, vendor tags, deprecated rows
 * carried not hidden — because the brain's read_catalog already holds
 * provider.ts's two rules (a row naming another toolkit fails the scoping;
 * an unreadable page is not an empty catalog) and must see what the vendor
 * said, not a tidier version.
 */
import { connectionsFromEnv, type ConnectionsEnv } from "../connections/provider.ts";

export const HANDS_API_TOOLS_PATH = "/hands/api/tools";

export type HandsApiToolsEnv = ConnectionsEnv & { ANTICIPY_SERVICE_TOKEN?: string };

const TOOLKIT = /^[a-z0-9_-]{1,64}$/;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json; charset=utf-8" },
  });
}

/** Copied from hands_api.ts tokenOk, not re-decided. */
function tokenOk(env: HandsApiToolsEnv, req: Request): boolean {
  const want = env.ANTICIPY_SERVICE_TOKEN || "";
  const got = req.headers.get("X-Anticipy-Token") || "";
  if (!want || got.length !== want.length) return false;
  let d = 0;
  for (let i = 0; i < got.length; i++) d |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return d === 0;
}

export async function handsApiTools(req: Request, env: HandsApiToolsEnv): Promise<Response> {
  if (req.method !== "GET") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "GET" } });
  }
  if (!tokenOk(env, req)) return json(401, { ok: false, message: "unauthorized" });
  const toolkit = (new URL(req.url).searchParams.get("toolkit") || "").trim().toLowerCase();
  if (!TOOLKIT.test(toolkit)) return json(400, { ok: false, message: "toolkit must be an app slug" });
  // connectionsFromEnv never returns null: an unset key is a thrown
  // ConnectionsUnconfigured on the first call, which the catch below turns
  // into a non-2xx -- the brain reads any non-2xx as UNKNOWN, never as "no tools".
  const provider = connectionsFromEnv(env);
  try {
    const items = await provider.tools(toolkit as never);
    return json(200, { ok: true, toolkit, items });
  } catch (err) {
    // The brain reads a non-2xx as UNKNOWN, never as "no tools". A vendor
    // outage must not become an empty allow-list.
    return json(502, { ok: false, message: "the catalog could not be read: " + String((err as Error)?.message || err).slice(0, 160) });
  }
}
