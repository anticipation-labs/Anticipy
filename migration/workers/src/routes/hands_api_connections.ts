/**
 * GET /hands/api/connections?owner=<owner row id> supplies the brain with the
 * connection facts needed to choose a hand. This is a read-only service route,
 * not a generic records collection: connections has a different schema and
 * exposing it there would also expose create/update/delete operations.
 *
 * The shared service token deliberately serves all brain owners. Every read
 * still requires one explicit owner row id; the store binds that id in SQL and
 * refuses mixed-owner results. Only the four planning fields leave this route,
 * never vendor account ids, credentials or unrelated connection metadata.
 * The owner echoed beside items lets the brain reject a mismatched response.
 */
import { createD1Store, ownerId } from "../connections/store.ts";

export const HANDS_API_CONNECTIONS_PATH = "/hands/api/connections";

export interface HandsApiConnectionsEnv {
  DB: D1Database;
  ANTICIPY_SERVICE_TOKEN?: string;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function tokenOk(env: HandsApiConnectionsEnv, req: Request): boolean {
  const want = env.ANTICIPY_SERVICE_TOKEN || "";
  const got = req.headers.get("X-Anticipy-Token") || "";
  if (!want || got.length !== want.length) return false;
  let difference = 0;
  for (let i = 0; i < got.length; i++) difference |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return difference === 0;
}

export async function handsApiConnections(req: Request, env: HandsApiConnectionsEnv): Promise<Response> {
  if (req.method !== "GET") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "GET" } });
  }
  if (!tokenOk(env, req)) return json(401, { ok: false, message: "service token required" });
  const query = new URL(req.url).searchParams;
  if (query.getAll("owner").length !== 1 || [...query.keys()].some(key => key !== "owner")) {
    return json(400, { ok: false, message: "exactly one owner row id is required" });
  }
  let owner: ReturnType<typeof ownerId>;
  try {
    owner = ownerId(query.get("owner") || "");
  } catch {
    return json(400, { ok: false, message: "owner must be an owner row id" });
  }
  try {
    const rows = await createD1Store(env).connectionsForOwner(owner);
    const items = rows.map(row => ({
      toolkit: row.toolkit,
      alias: row.alias ?? "",
      status: row.status,
      writes_enabled: row.writes_enabled,
    }));
    return json(200, { ok: true, owner, items });
  } catch {
    // Neither storage failure nor a broken scope is evidence of no connections.
    // Do not return the storage exception: it may include another owner's row.
    return json(503, { ok: false, message: "connections could not be read" });
  }
}
